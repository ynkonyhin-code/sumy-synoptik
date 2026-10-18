#!/usr/bin/env python3
"""
zabobony_svitu — щоденна обідня рубрика «Найцікавіші забобони світу» для «Сумського синоптика».

Текстовий пост із гумором: 3 забобони з науковим поясненням, коротка історична довідка
і анонс «завтра розглянемо забобони з…». Час публікації щодня різний: 12:00 + випадкові 0–90 хв (за Києвом).
Потрібні змінні середовища: BOT_TOKEN, CHAT_ID. Необов'язково: TEST_POST=true (надіслати наступний випуск зараз, без збереження стану).
"""
import html
import json
import os
import random
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from zabobony_svitu_data import POSTS

KYIV = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zabobony_svitu_state.json")
NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
BASE_TAGS = "#НайцікавішіЗабобониСвіту #забобони #цікаво #СумськийСиноптик #Суми"


def esc(s):
    return html.escape(s, quote=False)


def build_post(idx, issue_no):
    p = POSTS[idx % len(POSTS)]
    nxt = [POSTS[(idx + k) % len(POSTS)] for k in (1, 2, 3)]
    lines = [
        "🍀 <b>НАЙЦІКАВІШІ ЗАБОБОНИ СВІТУ</b> 🍀",
        f"<i>Випуск №{issue_no}</i>",
        "",
        f"{p['flag']} <b>Сьогодні: забобони з {esc(p['from'])}</b>",
        "",
        esc(p["intro"]),
        "",
    ]
    for i, (title, belief, science) in enumerate(p["items"]):
        lines += [f"{NUMBERS[i]} <b>{esc(title)}</b>", esc(belief), f"🔬 <i>Що каже наука:</i> {esc(science)}", ""]
    lines += [
        "📜 <b>Трохи історії</b>", esc(p["history"]), "",
        f"😄 {esc(p['outro'])}", "",
        f"🔜 <b>Завтра розглянемо забобони з {esc(nxt[0]['from'])}</b> {nxt[0]['flag']}",
        f"А далі на нас чекають: {nxt[1]['flag']} {esc(nxt[1]['name'])}, {nxt[2]['flag']} {esc(nxt[2]['name'])} та інші. Не пропустіть! 👀", "",
        f"{BASE_TAGS} {p['tag']}",
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

    if not test:
        if state.get("last_date") == today:
            print("[skip] сьогодні вже опубліковано")
            return 0
        noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
        target = noon + timedelta(minutes=random.Random(f"zabobony-{today}").randint(0, 90))
        if now < target:
            print(f"[wait] сьогоднішній час публікації — {target:%H:%M} (Київ)")
            return 0
        if now > noon.replace(hour=14, minute=30):
            print("[skip] занадто пізно для обіднього посту")
            return 0

    idx = state.get("next_index", 0) % len(POSTS)
    issue_no = state.get("issue_no", 0) + 1
    text = build_post(idx, issue_no)
    if len(text) > 4096:
        print(f"[error] пост задовгий: {len(text)} символів")
        return 1

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"[error] Telegram: {r.status_code} {r.text}")
        return 1
    print(f"[ok] опубліковано випуск №{issue_no}: {POSTS[idx]['name']}")

    if not test:
        state.update(last_date=today, next_index=(idx + 1) % len(POSTS), issue_no=issue_no)
        save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
