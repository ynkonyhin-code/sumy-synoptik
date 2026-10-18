#!/usr/bin/env python3
"""
rukh_troleybusiv — інформер про рух тролейбусів у Сумах для каналу «Сумський синоптик».

Читає публічний канал КП СМР «Електроавтотранс» (https://t.me/sumy_elektroavtotrans),
розпізнає статус руху, генерує картинку (радісну / сумну) та публікує власний пост.
Потрібні змінні середовища: BOT_TOKEN, CHAT_ID. Необов'язково: TEST_LATEST=true.
"""
import html
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from rukh_troleybusiv_images import generate_image

CHANNEL = "sumy_elektroavtotrans"
SOURCE_URL = f"https://t.me/s/{CHANNEL}"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rukh_troleybusiv_state.json")
KYIV = ZoneInfo("Europe/Kyiv")
UA = "Mozilla/5.0 (compatible; rukh_troleybusiv/1.0; +https://t.me/sumskoy_sinoptik)"

MIN_REPEAT_SEC = 30 * 60      # не повторювати той самий статус частіше ніж раз на 30 хв
MAX_POST_AGE_SEC = 3 * 3600   # занадто старі пости ігноруємо

# ───────────── Розпізнавання статусу ─────────────
# Порядок має значення: перше співпадіння визначає статус.
RULES = [
    ("restoring", ["рух тролейбусів поступово відновлюється", "поступово відновлюється",
                   "рух тролейбусів відновлено", "рух відновлено"]),
    ("suspended", ["рух тролейбусів по місту призупинено", "рух тролейбусів призупинено",
                   "рух по місту призупинено", "призупинено", "не курсують"]),
    ("delay",     ["рух тролейбусів відбувається з порушенням розкладу", "з порушенням розкладу руху",
                   "з порушенням розкладу"]),
    ("suspended", ["у зв'язку з технічними пошкодженнями контактної мережі",
                   "у зв'язку з проблемами в контактній мережі"]),
]
CAUSE_WORDS = ["контактної мережі", "контактній мережі"]
STD_PATTERNS = [
    r"до уваги пасажирів[!.]?",
    r"у зв.язку з проблемами в контактній мережі рух тролейбусів по місту призупинено[.!]?",
    r"рух тролейбусів поступово відновлюється[.!]?",
    r"рух тролейбусів відбувається з порушенням розкладу(?: руху)?[.!]?",
    r"рух тролейбусів по місту призупинено[.!]?",
]


def norm(text):
    t = text.lower()
    for ch in "’ʼ`‘´":
        t = t.replace(ch, "'")
    return re.sub(r"\s+", " ", t)


def classify(text):
    t = norm(text)
    for status, keys in RULES:
        if any(k in t for k in keys):
            return status
    return None


def has_cause(text):
    t = norm(text)
    return any(w in t for w in CAUSE_WORDS)


def extract_details(text):
    t = text
    for pat in STD_PATTERNS:
        t = re.sub(pat, "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .!-–—\n")
    return t if len(t) >= 25 else ""


# ───────────── Власні фрази ─────────────
PHRASES = {
    "suspended": {
        "mood": "sad",
        "titles": ["🚎💤 Тролейбуси на паузі", "🔌😴 Електротранспорт тимчасово зупинився",
                   "🚏🛑 Тролейбуси стоять без струму"],
        "bodies": ["Рух тролейбусів по місту призупинено — електротранспорту бракує живлення ⚡",
                   "Тролейбуси сумують на зупинках: рух по місту наразі призупинено 😢",
                   "Тролейбусний рух у Сумах тимчасово призупинено, лінії без живлення 🔋"],
        "tips": ["🚶 Плануйте поїздку із запасом часу або оберіть інший спосіб пересування.",
                 "🕰 Не стійте на зупинках дарма — перевіряйте новини перед виходом.",
                 "🧭 Подумайте про альтернативні маршрути — тролейбусів поки не чекаємо."],
        "footer": "🔔 Щойно рух відновиться — ми одразу повідомимо!",
        "tags": ["#рух_призупинено"],
    },
    "restoring": {
        "mood": "happy",
        "titles": ["🚎💚 Тролейбуси знову на лінії!", "🎉⚡ Струм є — тролейбуси їдуть!",
                   "🌈🚎 Добра новина для пасажирів"],
        "bodies": ["Рух електротранспорту поступово відновлюється — тролейбуси повертаються на маршрути 😊",
                   "Контактна мережа оживає, і тролейбуси неквапом повертаються до роботи ✨",
                   "Тролейбуси знову їдуть до вас — рух по місту поступово налагоджується 💫"],
        "tips": ["⏳ Рух відновлюється поступово, тому на зупинках можливі затримки.",
                 "🕒 Наберіться терпіння — тролейбуси вже в дорозі!",
                 "🚏 Інтервали можуть бути збільшеними, але ми вже їдемо! 😉"],
        "footer": "💙💛 Гарної та безпечної дороги, Суми!",
        "tags": ["#рух_відновлюється"],
    },
    "delay": {
        "mood": "sad",
        "titles": ["🚎⏱ Тролейбуси їдуть, але не поспішають", "🕰🚎 Розклад сьогодні «гуляє»",
                   "🚏⌛ Тролейбуси з запізненням"],
        "bodies": ["Рух тролейбусів відбувається з порушенням розкладу — транспорт доведеться почекати довше 🙈",
                   "Тролейбуси курсують, проте розклад не дотримується — запасіться терпінням 🫶"],
        "tips": ["🕰 Закладайте додатковий час на дорогу.",
                 "📲 Слідкуйте за оновленнями — ми повідомимо, коли все налагодиться."],
        "footer": "🔔 Тримаємо руку на пульсі й повідомимо про зміни!",
        "tags": ["#порушення_розкладу"],
    },
}
BASE_TAGS = ["#СумськийСиноптик", "#Суми", "#Сумщина", "#тролейбус", "#Електроавтотранс",
             "#громадський_транспорт"]


def build_caption(status, post, details, cause):
    ph = PHRASES[status]
    t = post["dt"].astimezone(KYIV).strftime("%H:%M")
    parts = [f"<b>{random.choice(ph['titles'])}</b>", "", random.choice(ph["bodies"])]
    if cause and status == "suspended":
        parts += ["", "🔧 Причина: проблеми з контактною мережею."]
    if details:
        parts += ["", f"📝 <i>Уточнення від перевізника:</i> {html.escape(details[:300])}"]
    parts += ["", random.choice(ph["tips"]), "", ph["footer"], "",
              f"🕒 Дані від {t} · 📡 <a href=\"{post['url']}\">КП СМР «Електроавтотранс»</a>", "",
              " ".join(ph["tags"] + BASE_TAGS)]
    caption = "\n".join(parts)
    if len(caption) > 1000 and details:  # ліміт підпису Telegram — 1024
        return build_caption(status, post, "", cause)
    return caption[:1024]


# ───────────── Telegram ─────────────
def fetch_posts():
    r = None
    for attempt in range(3):
        try:
            r = requests.get(SOURCE_URL, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            break
        except requests.RequestException as e:
            print(f"[warn] fetch attempt {attempt + 1} failed: {e}")
            r = None
            time.sleep(5)
    if r is None:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for m in soup.select("div.tgme_widget_message[data-post]"):
        try:
            pid = int(m["data-post"].split("/")[-1])
        except ValueError:
            continue
        el = m.select_one(".tgme_widget_message_text")
        if not el:
            continue
        for br in el.find_all("br"):
            br.replace_with("\n")
        time_el = m.select_one("a.tgme_widget_message_date time")
        try:
            dt = datetime.fromisoformat(time_el["datetime"])
        except (TypeError, KeyError, ValueError):
            dt = datetime.now(timezone.utc)
        posts.append({"id": pid, "text": el.get_text().strip(), "dt": dt,
                      "url": f"https://t.me/{CHANNEL}/{pid}"})
    return posts


def send_photo(token, chat_id, image, caption):
    api = f"https://api.telegram.org/bot{token}"
    r = requests.post(f"{api}/sendPhoto",
                      data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                      files={"photo": ("rukh_troleybusiv.jpg", image, "image/jpeg")}, timeout=60)
    if not r.ok:
        print(f"[warn] sendPhoto failed: {r.status_code} {r.text}")
        r = requests.post(f"{api}/sendMessage",
                          data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=30)
        r.raise_for_status()


# ───────────── Стан ─────────────
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ───────────── Основна логіка ─────────────
def main():
    token, chat_id = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    if not token or not chat_id:
        print("[error] BOT_TOKEN / CHAT_ID не задані")
        return 1

    test = os.environ.get("TEST_LATEST", "").lower() == "true"
    state = load_state()
    posts = fetch_posts()
    if not posts:
        print("[info] постів не отримано — пропускаю цей запуск")
        return 0
    posts.sort(key=lambda p: p["id"])
    max_id = posts[-1]["id"]
    last_id = state.get("last_post_id")

    if last_id is None and not test:
        state["last_post_id"] = max_id
        save_state(state)
        print(f"[init] базова точка: пост #{max_id}, нічого не публікую")
        return 0

    now = time.time()
    relevant = []
    for p in posts:
        if not test and p["id"] <= last_id:
            continue
        status = classify(p["text"])
        if not status:
            continue
        if not test and now - p["dt"].timestamp() > MAX_POST_AGE_SEC:
            continue
        p["status"] = status
        relevant.append(p)

    new_last_id = max(max_id, last_id or 0)
    if not relevant:
        print("[info] нових відповідних постів немає")
        if new_last_id != last_id:
            state["last_post_id"] = new_last_id
            save_state(state)
        return 0

    post = relevant[-1]  # якщо накопичилось кілька — беремо найсвіжіший
    status = post["status"]
    if (not test and status == state.get("last_status")
            and now - state.get("last_sent_ts", 0) < MIN_REPEAT_SEC):
        print(f"[skip] статус «{status}» уже опубліковано нещодавно")
        state["last_post_id"] = new_last_id
        save_state(state)
        return 0

    ph = PHRASES[status]
    variants = state.get("last_variant", {})
    image, variant = generate_image(ph["mood"], avoid=variants.get(ph["mood"]))
    caption = build_caption(status, post, extract_details(post["text"]), has_cause(post["text"]))
    send_photo(token, chat_id, image, caption)
    print(f"[ok] опубліковано: пост #{post['id']} → {status}, картинка «{variant}»")

    variants[ph["mood"]] = variant
    state.update(last_post_id=new_last_id, last_status=status,
                 last_sent_ts=now, last_variant=variants)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
