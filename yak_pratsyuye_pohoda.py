#!/usr/bin/env python3
"""
yak_pratsyuye_pohoda — підцикл «Як працює погода» (доповнення до «Таємниць неба») для «Сумського синоптика».

Раз на тиждень, у неділю вранці (09:00 + випадкові 0–60 хв за Києвом): схема-картинка з коротким
поясненням «Простими словами», а слідом — повний текст випуску. Випуски йдуть по порядку;
після останнього сезон завершується.

Потрібні змінні середовища: BOT_TOKEN, CHAT_ID.
Тестування:
  TEST_POST=true        — надіслати випуск зараз, не чекаючи неділі; стан не зберігається.
  TEST_ISSUE=N          — номер випуску для тесту (порожньо = наступний за чергою).
  TEST_CHAT_ID=<id>     — у тесті надсилати сюди (наприклад, у ваш особистий чат з ботом), а не в канал.
  DRY_RUN=true          — нічого не надсилати: зберегти схему у файл та вивести текст у консоль (для локальної перевірки).
"""
import html
import json
import os
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from yak_pratsyuye_pohoda_data import ISSUES, SEASON

KYIV = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yak_pratsyuye_pohoda_state.json")

POST_WEEKDAY = 6          # 6 = неділя
START_HOUR = 9            # початок вікна публікації (Київ)
SPREAD_MIN = 60           # випадкове зміщення 0–60 хв
LATEST_HOUR = 11          # після цього часу вже не публікуємо
NUMBERS = ["1️⃣", "2️⃣", "3️⃣"]
BASE_TAGS = "#ЯкПрацюєПогода #ТаємниціНеба #погода #СумськийСиноптик #Суми"


def esc(s):
    return html.escape(s, quote=False)


def build_caption(idx, test=False):
    it = ISSUES[idx]
    lines = []
    if test:
        lines += ["🧪 <i>тестовий пост</i>", ""]
    lines += [
        "🌦 <b>ЯК ПРАЦЮЄ ПОГОДА</b>",
        "<i>підцикл «Таємниць неба» · зрозуміло про природні явища</i>",
        f"Сезон {SEASON} · Випуск {idx + 1} з {len(ISSUES)}",
        "",
        f"<b>«{esc(it['title'])}»</b>",
        "",
        f"💬 <b>Простими словами:</b> {esc(it['simple'])}",
    ]
    return "\n".join(lines)


def build_text(idx):
    it = ISSUES[idx]
    lines = ["🎈 <b>Аналогія</b>", esc(it["analogy"]), "", "⚙️ <b>Як це відбувається</b>"]
    for i, s in enumerate(it["steps"]):
        lines.append(f"{NUMBERS[i]} {esc(s)}")
    lines += [
        "",
        "🧩 <b>Міф чи факт?</b>", esc(it["myth"]), "",
        "👀 <b>Перевір сам</b>", esc(it["check"]), "",
        esc(it["see_also"]), "",
        f"🔜 <b>Далі:</b> {esc(it['next'])}", "",
        f"{BASE_TAGS} {it['tags']}",
    ]
    return "\n".join(lines)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def api(token, method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def main():
    token, channel = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    dry = os.environ.get("DRY_RUN", "").lower() == "true"
    if not dry and (not token or not channel):
        print("[error] BOT_TOKEN / CHAT_ID не задані")
        return 1

    test = os.environ.get("TEST_POST", "").lower() == "true" or dry
    state = load_state()
    now = datetime.now(KYIV)
    today = now.date().isoformat()

    if test:
        raw = os.environ.get("TEST_ISSUE", "").strip()
        idx = int(raw) - 1 if raw.isdigit() else state.get("next_index", 0)
        if not 0 <= idx < len(ISSUES):
            print(f"[error] немає випуску з таким номером (усього {len(ISSUES)})")
            return 1
    else:
        idx = state.get("next_index", 0)
        if idx >= len(ISSUES):
            print("[done] сезон завершено, публікувати більше нічого")
            return 0
        if now.weekday() != POST_WEEKDAY:
            print("[skip] сьогодні не неділя")
            return 0
        if state.get("last_date") == today:
            print("[skip] сьогодні вже опубліковано")
            return 0
        start = now.replace(hour=START_HOUR, minute=0, second=0, microsecond=0)
        target = start + timedelta(minutes=random.Random(f"pohoda-{today}").randint(0, SPREAD_MIN))
        if now < target:
            print(f"[wait] час публікації сьогодні — {target:%H:%M} (Київ)")
            return 0
        if now > now.replace(hour=LATEST_HOUR, minute=0, second=0, microsecond=0):
            print("[skip] занадто пізно для ранкової публікації")
            return 0

    caption = build_caption(idx, test)
    text = build_text(idx)
    if len(caption) > 1024 or len(text) > 4096:
        print(f"[error] випуск {idx + 1} задовгий: підпис {len(caption)}, текст {len(text)}")
        return 1

    image = None
    try:
        from yak_pratsyuye_pohoda_images import render_issue
        image = render_issue(ISSUES[idx], idx + 1, len(ISSUES))
    except Exception as e:  # схема не повинна блокувати публікацію тексту
        print(f"[warn] не вдалося створити схему: {e}")

    if dry:
        if image:
            with open("yak_pratsyuye_pohoda_test.jpg", "wb") as f:
                f.write(image)
            print("[dry] схему збережено: yak_pratsyuye_pohoda_test.jpg")
        print("\n--- ПІДПИС ---\n" + caption + "\n\n--- ТЕКСТ ---\n" + text)
        return 0

    chat = (os.environ.get("TEST_CHAT_ID") or channel) if test else channel
    if image:
        api(token, "sendPhoto", data={"chat_id": chat, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("yak_pratsyuye_pohoda.jpg", image, "image/jpeg")})
        api(token, "sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                         "disable_web_page_preview": True})
    else:
        api(token, "sendMessage", data={"chat_id": chat, "text": caption + "\n\n" + text, "parse_mode": "HTML",
                                         "disable_web_page_preview": True})
    print(f"[ok] випуск {idx + 1}: {ISSUES[idx]['title']} → чат {'тестовий' if chat != channel else 'канал'}")

    if not test:
        state.update(last_date=today, next_index=idx + 1)
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
