#!/usr/bin/env python3
"""
viktoryna_opytuvannia — «Вікторина» і «Опитування» для «Київського не гідрометцентру».

  • Вікторина — неділя, о 18:00 + випадкові 0–45 хв за Києвом. Це «режим вікторини» Telegram: читач натискає
    відповідь, одразу бачить, правильно чи ні, і пояснення (спливає підказка), а ще — відсотки решти учасників.
  • Опитування — понеділок, о 18:00 + випадкові 0–45 хв. Звичайне голосування без «правильної» відповіді:
    так ми дізнаємось, що цікаво читачам.
  • Перед новою публікацією попередню (минулого тижня) закриваємо й, якщо проголосувало достатньо людей
    (SUMMARY_MIN), коротко підбиваємо підсумок окремим повідомленням.

Питання йдуть по порядку з viktoryna_opytuvannia_data.py; після останнього починається коло знову.
Варіанти відповідей у вікторині перемішуються (правильна не завжди перша).

Потрібні змінні середовища: TELEGRAM_BOT_TOKEN (або BOT_TOKEN), CHAT_ID.
Необов'язково: TEST_POST=true (надіслати зараз, без перевірок часу й без збереження стану), KIND=quiz|poll|auto,
INDEX=N (номер питання з 0 — для пробного запуску).
Запуск без відправки: python viktoryna_opytuvannia.py --dry-run [--kind quiz|poll] [--index N]
"""
import argparse
import html
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from viktoryna_opytuvannia_data import POLLS, QUIZ

KYIV = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viktoryna_opytuvannia_state.json")
KINDS = {"quiz": {"weekday": 6, "bank": QUIZ, "icon": "🧠", "name": "Вікторина"},     # неділя
         "poll": {"weekday": 0, "bank": POLLS, "icon": "🗳", "name": "Опитування"}}   # понеділок
BASE, SPREAD_MIN, LATEST = (18, 0), 45, (20, 30)
SILENT = True            # без звуку (False — зі звуком)
SUMMARY_MIN = 5          # підсумок минулого тижня публікуємо, лише якщо проголосувало щонайменше стільки людей
MAX_QUESTION, MAX_OPTION, MAX_EXPL = 300, 100, 200


def esc(s):
    return html.escape(s, quote=False)


# ── Побудова питання ───────────────────────────────────────────────────────
def build(kind, idx, issue_no):
    """Повертає словник для sendPoll і службові поля для підсумку."""
    bank = KINDS[kind]["bank"]
    item = bank[idx % len(bank)]
    icon, name = KINDS[kind]["icon"], KINDS[kind]["name"]
    question = f"{icon} {name} №{issue_no} · {item['q']}"
    if kind == "quiz":
        options = [item["right"]] + list(item["wrong"])
        random.Random(f"quiz-{issue_no}-{idx}").shuffle(options)
        spec = {"question": question, "options": options, "type": "quiz",
                "correct": options.index(item["right"]), "explanation": item["expl"], "multiple": False}
    else:
        spec = {"question": question, "options": list(item["options"]), "type": "regular",
                "correct": None, "explanation": None, "multiple": bool(item.get("multiple"))}
    check(spec)
    return spec


def check(spec):
    """Обмеження Telegram: питання ≤300, варіант ≤100, пояснення ≤200, 2–10 варіантів."""
    assert len(spec["question"]) <= MAX_QUESTION, f"питання задовге ({len(spec['question'])}): {spec['question']}"
    assert 2 <= len(spec["options"]) <= 10, "кількість варіантів має бути від 2 до 10"
    assert len(set(spec["options"])) == len(spec["options"]), "варіанти не повинні повторюватись"
    for o in spec["options"]:
        assert 1 <= len(o) <= MAX_OPTION, f"варіант задовгий ({len(o)}): {o}"
    if spec["type"] == "quiz":
        assert spec["explanation"] and len(spec["explanation"]) <= MAX_EXPL, f"пояснення задовге: {spec['explanation']}"


# ── Telegram ───────────────────────────────────────────────────────────────
def tg(method, token, **data):
    for attempt in (1, 2, 3):
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=60)
        if r.status_code == 429 and attempt < 3:
            time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
            continue
        if not r.ok:
            raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text[:200]}")
        return r.json()["result"]
    raise RuntimeError("Telegram: вичерпано спроби")


def send_poll(token, chat, spec):
    data = {"chat_id": chat, "question": spec["question"],
            "options": json.dumps([{"text": o} for o in spec["options"]], ensure_ascii=False),
            "disable_notification": "true" if SILENT else "false"}
    if spec["type"] == "quiz":
        data.update(type="quiz", correct_option_id=spec["correct"], explanation=spec["explanation"])
    else:
        data["allows_multiple_answers"] = "true" if spec["multiple"] else "false"
    return tg("sendPoll", token, **data)["message_id"]


def summary_of_previous(kind, last, token, chat):
    """Закрити минулу вікторину/опитування й повернути текст підсумку (або None, якщо мало голосів/помилка)."""
    if not last or not last.get("message_id"):
        return None
    try:
        res = tg("stopPoll", token, chat_id=chat, message_id=last["message_id"])
    except Exception as ex:                                  # повідомлення видалено чи вже закрито — не критично
        print(f"[warn] не вдалося закрити минулий опитувальник: {ex}")
        return None
    total = int(res.get("total_voter_count", 0))
    if total < SUMMARY_MIN:
        return None
    opts = res.get("options", [])
    q = esc(last["q"])
    if kind == "quiz":
        right = opts[last["correct"]]["voter_count"] if last.get("correct") is not None and last["correct"] < len(opts) else 0
        pct = round(100 * right / total)
        return (f"🧠 <b>Підсумки минулої вікторини</b>\n«{q}»\n"
                f"Правильно відповіли {pct}% із {total} учасників. Правильна відповідь: <b>{esc(last['answer'])}</b>.")
    top = max(opts, key=lambda o: o["voter_count"])
    pct = round(100 * top["voter_count"] / total)
    return (f"🗳 <b>Підсумки минулого опитування</b>\n«{q}»\n"
            f"Найпопулярніша відповідь — <b>«{esc(top['text'])}»</b>: {pct}% із {total} учасників.")


# ── Стан ───────────────────────────────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def pick_kind(now, wanted):
    if wanted in KINDS:
        return wanted
    return next((k for k, v in KINDS.items() if v["weekday"] == now.weekday()), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--kind", default=os.environ.get("KIND", "auto"), choices=["auto", "quiz", "poll"])
    ap.add_argument("--index", default=os.environ.get("INDEX", ""))
    args = ap.parse_args()
    test = os.environ.get("TEST_POST", "").lower() == "true"
    now = datetime.now(KYIV)
    today = now.date().isoformat()
    state = load_state()

    kind = pick_kind(now, args.kind)
    if kind is None:
        print("[skip] сьогодні не день вікторини (неділя) чи опитування (понеділок)")
        return 0
    ks = state.get(kind, {})

    if args.dry_run:
        idx = int(args.index) if str(args.index).strip().isdigit() else ks.get("next_index", 0)
        spec = build(kind, idx, ks.get("issue_no", 0) + 1)
        print(f"[dry-run] {KINDS[kind]['name']} · питання з номером {idx % len(KINDS[kind]['bank'])} (з 0)\n")
        print(spec["question"])
        for i, o in enumerate(spec["options"]):
            mark = "  ✅" if spec["correct"] == i else ""
            print(f"  {'○' if not spec['multiple'] else '☐'} {o}{mark}")
        if spec["explanation"]:
            print(f"\nПояснення після відповіді: {spec['explanation']}")
        print(f"\n[dry-run] режим Telegram: {spec['type']}" + (", можна обрати кілька" if spec["multiple"] else ""))
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    chat = os.environ.get("CHAT_ID")
    if not token or not chat:
        print("[error] TELEGRAM_BOT_TOKEN / CHAT_ID не задані")
        return 1

    if not test:
        if ks.get("last_date") == today:
            print(f"[skip] {KINDS[kind]['name']} за сьогодні вже опубліковано")
            return 0
        base = now.replace(hour=BASE[0], minute=BASE[1], second=0, microsecond=0)
        target = base + timedelta(minutes=random.Random(f"{kind}-{today}").randint(0, SPREAD_MIN))
        if now < target:
            print(f"[wait] сьогоднішній час публікації — {target:%H:%M} (Київ)")
            return 0
        if now > now.replace(hour=LATEST[0], minute=LATEST[1], second=0, microsecond=0):
            print("[skip] занадто пізно для цієї рубрики")
            return 0

    size = len(KINDS[kind]["bank"])
    idx = int(args.index) % size if str(args.index).strip().isdigit() else ks.get("next_index", 0) % size
    issue_no = ks.get("issue_no", 0) + 1
    spec = build(kind, idx, issue_no)

    if not test:                                   # підсумки минулого разу — лише в «бойовому» режимі
        text = summary_of_previous(kind, ks.get("last"), token, chat)
        if text:
            tg("sendMessage", token, chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview="true",
               disable_notification="true" if SILENT else "false")
    msg_id = send_poll(token, chat, spec)
    print(f"[ok] {KINDS[kind]['name']} №{issue_no} опубліковано (message_id={msg_id})")
    if not test:
        state[kind] = {"next_index": (idx + 1) % size, "issue_no": issue_no, "last_date": today,
                       "last": {"message_id": msg_id, "q": bank_q(kind, idx), "correct": spec["correct"],
                                "answer": spec["options"][spec["correct"]] if spec["correct"] is not None else None}}
        save_state(state)
    return 0


def bank_q(kind, idx):
    bank = KINDS[kind]["bank"]
    return bank[idx % len(bank)]["q"]


if __name__ == "__main__":
    sys.exit(main())
