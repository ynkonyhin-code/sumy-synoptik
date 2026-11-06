#!/usr/bin/env python3
"""
nichna_zmina — «Нічна зміна» для Сумського синоптика.

Кіт (денна зміна) вечорі здає варту Сові. Уночі Сова розповідає байки тим, хто не спить.
Вранці Сова здає зміну Коту, і він далі інформує читачів удень.

Розклад (за Києвом, «ніч» рахується від вечора):
  22:00  вечірня передача зміни (Кіт -> Сова)
  23:40  байка №1
  01:20  байка №2
  03:00  байка №3
  07:00  ранкова передача зміни (Сова -> Кіт)
До кожного часу додається випадковий зсув. Вікна «догонові»: якщо GitHub запустив розклад із запізненням,
пост усе одно вийде (вечір до ~00:30, байки до ~1,5 год, ранок до ~10:00), але не раніше ніж
через 50 хв після попереднього поста.

Для байок додається «Зведення тиші» (нічна погода + небо: Місяць, зорі, планети, метеори; nichna_weather.py, nichna_sky.py): інколи, а за помітної погоди
(мороз, вітер, опади, туман) завжди.

Потрібні змінні середовища: BOT_TOKEN, CHAT_ID.
Необов'язково: TEST_KIND=evening|tale|morning (надіслати зараз, без збереження стану).
Аргументи: --dry-run (лише показати текст), --kind evening|tale|morning (з --dry-run).

Картинки (необов'язково, лежать поруч зі скриптом): zmina_vechir.jpg, zmina_ranok.jpg, bayka_sovy.jpg.
Якщо файлу немає, надсилається лише текст.
"""
import argparse
import html
import json
import os
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from nichna_zmina_data import EVENING, MORNING, TALES
import nichna_weather

KYIV = ZoneInfo("Europe/Kyiv")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "nichna_zmina_state.json")

# (ім'я слоту, тип, хвилини від 00:00 дня початку ночі, макс. зсув, вікно публікації)
# (ім'я слоту, тип, хвилини від 00:00 дня початку ночі, макс. зсув, вікно «догону» у хвилинах)
# Вікно навмисно широке: GitHub Actions інколи запускає розклад із запізненням на години.
# Вечір не можна відкладати надто довго (інакше «передача зміни» о 4 ранку виглядає дивно),
# байки й ранкова передача можуть «наздоганяти» довше. Якщо вікно минуло, пост пропускається.
SLOTS = [
    ("evening", "evening", 22 * 60,           10, 150),   # 22:00, наздоганяє до ~00:30
    ("tale1",   "tale",    23 * 60 + 40,      20, 90),    # 23:40
    ("tale2",   "tale",    25 * 60 + 20,      20, 90),    # 01:20
    ("tale3",   "tale",    27 * 60,           20, 90),    # 03:00
    ("morning", "morning", 31 * 60,           10, 180),   # 07:00, наздоганяє до ~10:00
]
MIN_GAP_MIN = 50   # мінімум між двома постами: якщо відкладені запуски стартують «пачкою», вийде лише один
IMAGES = {"evening": "zmina_vechir.jpg", "morning": "zmina_ranok.jpg", "tale": "bayka_sovy.jpg"}
TAGS = "#СумськийСиноптик #Суми"


def esc(s):
    return html.escape(s, quote=False)


def build_post(kind, idx, tale_no=0, weather_block=None):
    if kind == "evening":
        return EVENING[idx % len(EVENING)] + f"\n\n#НічнаЗміна #ЗмінаВарти {TAGS}"
    if kind == "morning":
        return MORNING[idx % len(MORNING)] + f"\n\n#НічнаЗміна #ЗмінаВарти {TAGS}"
    title, text = TALES[idx % len(TALES)]
    return "\n".join([
        f"🦉 <b>Нічна байка від Сови №{tale_no}</b>",
        "<i>Для тих, хто не спить</i>",
        "",
        f"📖 <b>{esc(title)}</b>",
        "",
        esc(text),
        "",
    ] + ([weather_block, ""] if weather_block else []) + [
        "🌙 Добраніч, а хто не спить, тримайтесь, я поруч.",
        "",
        f"#НічнаБайка #БайкиСови {TAGS}",
    ])


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send(token, chat_id, kind, text):
    """Надсилає картинку (якщо є) окремо, потім текст. Повертає True/False."""
    img = os.path.join(BASE, IMAGES[kind])
    if os.path.exists(img):
        with open(img, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                              data={"chat_id": chat_id}, files={"photo": f}, timeout=60)
        if not r.ok:
            print(f"[warn] фото не надіслано: {r.status_code} {r.text}")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"[error] Telegram: {r.status_code} {r.text}")
        return False
    return True


def pick_slot(state, now):
    """Повертає (ім'я, тип) слота, який зараз треба опублікувати, або None."""
    night = (now - timedelta(hours=12)).date()
    night_s = night.isoformat()
    done = state.get("done", []) if state.get("night") == night_s else []
    midnight = datetime(night.year, night.month, night.day, tzinfo=KYIV)
    for name, kind, minutes, jitter, window in SLOTS:
        if name in done:
            continue
        shift = random.Random(f"zmina-{night_s}-{name}").randint(0, jitter)
        target = midnight + timedelta(minutes=minutes + shift)
        if target <= now <= target + timedelta(minutes=window):
            last = state.get("last_post_at")
            try:
                last_dt = datetime.fromisoformat(last) if last else None
            except ValueError:
                last_dt = None
            if last_dt and now - last_dt < timedelta(minutes=MIN_GAP_MIN):
                print(f"[wait] попередній пост був {last_dt:%H:%M}, пауза {MIN_GAP_MIN} хв перед «{name}»")
                return None
            return night_s, done, name, kind
        if now < target:
            print(f"[wait] наступний пост «{name}» о {target:%H:%M} (Київ)")
            return None
    print("[skip] зараз нічого публікувати")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--kind", choices=["evening", "tale", "morning"])
    ap.add_argument("--weather", action="store_true", help="у dry-run додати «Зведення тиші» (потрібен інтернет)")
    args = ap.parse_args()

    state = load_state()

    if args.dry_run:
        kinds = [args.kind] if args.kind else ["evening", "tale", "morning"]
        for k in kinds:
            idx = state.get("tale_index", 0) if k == "tale" else random.randrange(3)
            wb = nichna_weather.get_block(datetime.now(KYIV), force=True) if (args.weather and k == "tale") else None
            print(build_post(k, idx, state.get("tale_no", 0) + 1, wb), "\n" + "-" * 40)
        return 0

    token, chat_id = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    if not token or not chat_id:
        print("[error] BOT_TOKEN / CHAT_ID не задані")
        return 1

    test_kind = os.environ.get("TEST_KIND", "").lower()
    if test_kind in ("evening", "tale", "morning"):
        wb = nichna_weather.get_block(datetime.now(KYIV), force=True) if test_kind == "tale" else None
        text = build_post(test_kind, random.randrange(10), state.get("tale_no", 0) + 1, wb)
        return 0 if send(token, chat_id, test_kind, text) else 1

    now = datetime.now(KYIV)
    slot = pick_slot(state, now)
    if not slot:
        return 0
    night_s, done, name, kind = slot

    if kind == "tale":
        idx = state.get("tale_index", 0) % len(TALES)
        tale_no = state.get("tale_no", 0) + 1
    else:
        idx = state.get("evening_index" if kind == "evening" else "morning_index", 0)
        tale_no = 0
    wb = None
    if kind == "tale":
        rnd = random.Random(f"zvedennia-{night_s}-{name}")
        wb = nichna_weather.get_block(now, rnd)   # «іноді»: ~50% ночей + завжди при помітній погоді
    text = build_post(kind, idx, tale_no, wb)
    if len(text) > 4096 and wb:
        print(f"[warn] пост {len(text)} символів, публікую без «Зведення тиші»")
        text = build_post(kind, idx, tale_no, None)
    if len(text) > 4096:
        print(f"[error] пост задовгий: {len(text)}")
        return 1
    if not send(token, chat_id, kind, text):
        return 1

    done.append(name)
    state.update(night=night_s, done=done, last_post_at=now.isoformat())
    if kind == "tale":
        state.update(tale_index=(idx + 1) % len(TALES), tale_no=tale_no)
    elif kind == "evening":
        state["evening_index"] = (idx + 1) % len(EVENING)
    else:
        state["morning_index"] = (idx + 1) % len(MORNING)
    save_state(state)
    print(f"[ok] опубліковано «{name}»")
    return 0


if __name__ == "__main__":
    sys.exit(main())
