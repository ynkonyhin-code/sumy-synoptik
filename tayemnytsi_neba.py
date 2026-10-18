#!/usr/bin/env python3
"""
tayemnytsi_neba — цикл «Таємниці неба: від давніх прикмет до штучного інтелекту» для «Сумського синоптика».

Виходить 2 рази на тиждень (вівторок і п'ятниця), ввечері: 18:00 + випадкові 0–60 хв за Києвом.
Випуски йдуть по порядку; після останнього сезон завершується і скрипт нічого не публікує.
Потрібні змінні середовища: BOT_TOKEN, CHAT_ID.
Необов'язково: TEST_POST=true (надіслати випуск зараз, без збереження стану), TEST_ISSUE=N (номер випуску для тесту).
"""
import html
import json
import os
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from tayemnytsi_neba_data import ISSUES, SEASON

KYIV = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tayemnytsi_neba_state.json")

POST_WEEKDAYS = (1, 4)   # 0=понеділок … 1=вівторок, 4=п'ятниця
START_HOUR = 18          # початок вікна публікації (Київ)
SPREAD_MIN = 60          # випадкове зміщення 0–60 хв
LATEST_HOUR, LATEST_MIN = 20, 30   # пізніше — вже не публікуємо
BASE_TAGS = "#ТаємниціНеба #погода #СумськийСиноптик #Суми"


def esc(s):
    return html.escape(s, quote=False)


def build_post(idx):
    it = ISSUES[idx]
    lines = [
        "🌅 <b>ТАЄМНИЦІ НЕБА</b>",
        "<i>від давніх прикмет до штучного інтелекту</i>",
        f"Сезон {SEASON} · Випуск {idx + 1} з {len(ISSUES)} · {esc(it['act'])}",
        "",
        f"<b>«{esc(it['title'])}»</b>",
        "",
        esc(it["intro"]),
        "",
    ]
    for heading, text in it["blocks"]:
        lines += [f"<b>{esc(heading)}</b>", esc(text), ""]
    lines += [
        "👀 <b>Перевір сам</b>", esc(it["check"]), "",
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


def main():
    token, chat_id = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    if not token or not chat_id:
        print("[error] BOT_TOKEN / CHAT_ID не задані")
        return 1

    test = os.environ.get("TEST_POST", "").lower() == "true"
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
        if now.weekday() not in POST_WEEKDAYS:
            print("[skip] сьогодні не день публікації")
            return 0
        if state.get("last_date") == today:
            print("[skip] сьогодні вже опубліковано")
            return 0
        start = now.replace(hour=START_HOUR, minute=0, second=0, microsecond=0)
        target = start + timedelta(minutes=random.Random(f"neba-{today}").randint(0, SPREAD_MIN))
        if now < target:
            print(f"[wait] час публікації сьогодні — {target:%H:%M} (Київ)")
            return 0
        if now > now.replace(hour=LATEST_HOUR, minute=LATEST_MIN, second=0, microsecond=0):
            print("[skip] занадто пізно для публікації")
            return 0

    text = build_post(idx)
    if len(text) > 4096:
        print(f"[error] випуск {idx + 1} задовгий: {len(text)} символів")
        return 1

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"[error] Telegram: {r.status_code} {r.text}")
        return 1
    print(f"[ok] опубліковано випуск {idx + 1}: {ISSUES[idx]['title']}")

    if not test:
        state.update(last_date=today, next_index=idx + 1)
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
