#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dsns_sumy.py

Берёт публикации из публичного канала «ДСНС Сумщини» (t.me/dsns_sumy),
отбирает их по ключевым фразам и публикует в канале «Суський синоптик».

- Копирует текст и картинки (альбомы тоже).
- Полностью убирает ссылки, @упоминания, призывы подписаться и соцсети.
- Добавляет тематические теги.
- Не допускает повторных публикаций (id постов хранятся в dsns_sumy_posted.txt).

Переменные окружения: BOT_TOKEN, CHAT_ID (секреты GitHub).
Необязательные: FIRST_RUN_POST=1 (при первом запуске опубликовать и старые посты),
                MAX_AGE_HOURS (по умолчанию 48), MAX_POSTS_PER_RUN (по умолчанию 10).
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #
SOURCE_CHANNEL = "dsns_sumy"
SOURCE_URL = f"https://t.me/s/{SOURCE_CHANNEL}"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "dsns_sumy_posted.txt"
STATE_LIMIT = 500  # сколько последних id хранить

MAX_AGE_HOURS = int(os.environ.get("MAX_AGE_HOURS", "48"))
MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "10"))
FIRST_RUN_POST = os.environ.get("FIRST_RUN_POST", "0") == "1"

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096

KEYWORDS = [
    "Увага! Попередження про небезпечні погодні явища на Сумщині",
    "м. Суми опинилося під атакою російських БПЛА",
    "ліквідували пожежу після влучання ворожого БпЛА",
    "які виникли через влучання російських безпілотників",
    "російські безпілотники атакували",
    "ворожий дрон влучив в легкову автівку",
    "ворог атакував транспортний засіб",
    "ворожий БпЛА атакував вантажівку",
    "фахівці ДСНС працювали на місці ранкової атаки",
    "під ударами російських безпілотників опинився",
    "ворожий дрон атакував місто Суми",
]

# Базовые теги + теги по теме (regex по тексту -> теги)
BASE_TAGS = ["#Суми", "#Сумщина", "#ДСНС"]
TOPIC_TAGS = [
    (r"попередження|погодні\s+явища|небезпечні\s+погодні", ["#попередження", "#погода", "#небезпечна_погода", "#синоптик"]),
    (r"вітер|шквал|гроза|град|злива|дощ|сніг|ожеледиц|ожеледь|мороз|спека|туман|налипання", ["#негода"]),
    (r"БпЛА|БПЛА|безпілотник|дрон", ["#БпЛА", "#атака_дронів", "#наслідки_атаки"]),
    (r"атак|удар|влучан|обстріл", ["#атака", "#війна"]),
    (r"пожеж|загоран|горіл|палал", ["#пожежа", "#гасіння_пожежі"]),
    (r"легков\w*\s+автівк|автомобіл|транспортн\w*\s+засіб|вантажівк|авто\b", ["#автівка", "#транспорт"]),
    (r"фахівці\s+ДСНС|рятувальник|ліквідув|працювали\s+на\s+місці", ["#рятувальники", "#ліквідація_наслідків"]),
    (r"ранков", ["#ранкова_атака"]),
    (r"будинк|житлов|квартир", ["#житловий_сектор"]),
    (r"тривог|укриття", ["#безпека", "#повітряна_тривога"]),
]

# Строки, которые не нужны (подписка, соцсети) – удаляются целиком
JUNK_LINE_RE = re.compile(
    r"підписуйтесь|підписуйтеся|підписатися|підпишіться|приєднуйтесь|приєднуйтеся|"
    r"слідкуйте|соцмереж|facebook|instagram|youtube|viber|tiktok|telegram|телеграм|"
    r"фейсбук|інстаграм|ютуб|вайбер",
    re.IGNORECASE,
)
URL_RE = re.compile(r"(https?://\S+|www\.\S+|t\.me/\S+|\b[\w-]+\.(?:com|ua|net|org|gov\.ua|me)\b\S*)", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w+")
LINK_MARK = "\uE000"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SumskyiSynoptykBot/1.0)"}


# --------------------------------------------------------------------------- #
# Утилиты
# --------------------------------------------------------------------------- #
def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[«»“”„\"'’`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


NORMALIZED_KEYWORDS = [normalize(k) for k in KEYWORDS]


def matches_keywords(text: str) -> bool:
    n = normalize(text)
    return any(k in n for k in NORMALIZED_KEYWORDS)


def load_state() -> list:
    if not STATE_FILE.exists():
        return []
    ids = []
    for line in STATE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    return ids


def save_state(ids: list) -> None:
    ids = sorted(set(ids))[-STATE_LIMIT:]
    STATE_FILE.write_text("\n".join(map(str, ids)) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Парсинг канала
# --------------------------------------------------------------------------- #
def fetch_messages() -> list:
    r = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    messages = []
    for m in soup.select(".tgme_widget_message[data-post]"):
        try:
            post_id = int(m["data-post"].split("/")[-1])
        except (ValueError, KeyError):
            continue

        text_el = m.select_one(".tgme_widget_message_text")

        photos = []
        for a in m.select("a.tgme_widget_message_photo_wrap"):
            found = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", a.get("style", ""))
            if found:
                photos.append(found.group(1))

        dt = None
        time_el = m.select_one(".tgme_widget_message_date time")
        if time_el and time_el.get("datetime"):
            try:
                dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
            except ValueError:
                dt = None

        messages.append({
            "id": post_id,
            "el": text_el,
            "raw_text": text_el.get_text(" ", strip=True) if text_el else "",
            "photos": photos,
            "dt": dt,
        })

    messages.sort(key=lambda x: x["id"])
    return messages


def clean_text(el) -> str:
    """Текст поста без ссылок, @упоминаний и призывов подписаться."""
    if el is None:
        return ""

    # работаем с копией разметки, чтобы не портить исходное дерево
    el = BeautifulSoup(str(el), "html.parser")
    for br in el.find_all("br"):
        br.replace_with("\n")
    for a in el.find_all("a"):
        a.replace_with(LINK_MARK)

    lines = []
    for line in el.get_text().split("\n"):
        had_link = LINK_MARK in line
        line = line.replace(LINK_MARK, "")
        line = URL_RE.sub("", line)
        line = MENTION_RE.sub("", line)
        line = re.sub(r"[ \t]+", " ", line).strip(" \t|•·")

        if had_link:
            # строка состояла из ссылок/иконок/разделителей
            if not re.search(r"\w", line):
                continue
            # подпись-«заглушка» перед ссылкой: «Детальніше:», «Читайте тут ➡️»
            letters = re.sub(r"[^\w]", "", line)
            if len(letters) <= 30 and re.search(r"[:\-–—➡️👉▶️]\s*$", line):
                continue
        if JUNK_LINE_RE.search(line):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def build_tags(text: str) -> str:
    tags = list(BASE_TAGS)
    for pattern, extra in TOPIC_TAGS:
        if re.search(pattern, text, re.IGNORECASE):
            tags.extend(extra)
    seen, result = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return " ".join(result)


# --------------------------------------------------------------------------- #
# Отправка в Telegram
# --------------------------------------------------------------------------- #
def tg_call(method: str, data=None, files=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    for attempt in range(3):
        r = requests.post(url, data=data, files=files, timeout=90)
        if r.status_code == 429:
            wait = r.json().get("parameters", {}).get("retry_after", 5)
            log(f"Telegram просит подождать {wait} c")
            time.sleep(wait + 1)
            continue
        if not r.ok:
            raise RuntimeError(f"{method}: {r.status_code} {r.text}")
        return r.json()
    raise RuntimeError(f"{method}: превышено число попыток")


def download(url: str) -> bytes:
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.content


def send_post(text: str, tags: str, photo_urls: list) -> None:
    full = f"{text}\n\n{tags}" if text else tags

    if not photo_urls:
        tg_call("sendMessage", {
            "chat_id": CHAT_ID,
            "text": full[:MESSAGE_LIMIT],
            "disable_web_page_preview": True,
        })
        return

    photo_urls = photo_urls[:10]
    caption_fits = len(full) <= CAPTION_LIMIT
    caption = full if caption_fits else None

    if len(photo_urls) == 1:
        data = {"chat_id": CHAT_ID}
        if caption:
            data["caption"] = caption
        tg_call("sendPhoto", data, files={"photo": ("photo.jpg", download(photo_urls[0]))})
    else:
        media, files = [], {}
        for i, url in enumerate(photo_urls):
            key = f"photo{i}"
            files[key] = (f"{key}.jpg", download(url))
            item = {"type": "photo", "media": f"attach://{key}"}
            if i == 0 and caption:
                item["caption"] = caption
            media.append(item)
        tg_call("sendMediaGroup", {"chat_id": CHAT_ID, "media": json.dumps(media)}, files=files)

    # длинный текст не помещается в подпись – отправляем отдельным сообщением
    if not caption_fits:
        tg_call("sendMessage", {
            "chat_id": CHAT_ID,
            "text": full[:MESSAGE_LIMIT],
            "disable_web_page_preview": True,
        })


# --------------------------------------------------------------------------- #
# Основная логика
# --------------------------------------------------------------------------- #
def collect_album(messages: list, idx: int) -> tuple:
    """Фото из соседних постов-картинок без текста (альбом) + их id."""
    base = messages[idx]
    photos = list(base["photos"])
    ids = [base["id"]]

    def same_album(other, prev_id):
        if other["el"] is not None and other["raw_text"]:
            return False
        if not other["photos"] or other["id"] != prev_id:
            return False
        if base["dt"] and other["dt"]:
            return abs((base["dt"] - other["dt"]).total_seconds()) <= 60
        return True

    # назад
    prev_id = base["id"]
    j = idx - 1
    before = []
    while j >= 0 and same_album(messages[j], prev_id - 1):
        before = messages[j]["photos"] + before
        ids.append(messages[j]["id"])
        prev_id = messages[j]["id"]
        j -= 1
    # вперёд
    prev_id = base["id"]
    j = idx + 1
    after = []
    while j < len(messages) and same_album(messages[j], prev_id + 1):
        after += messages[j]["photos"]
        ids.append(messages[j]["id"])
        prev_id = messages[j]["id"]
        j += 1

    return before + photos + after, ids


def main() -> int:
    if not BOT_TOKEN or not CHAT_ID:
        log("ОШИБКА: не заданы BOT_TOKEN и/или CHAT_ID")
        return 1

    first_run = not STATE_FILE.exists()
    posted = load_state()
    posted_set = set(posted)

    messages = fetch_messages()
    log(f"Получено постов с канала: {len(messages)}")

    # Первый запуск: запоминаем текущие посты, чтобы не засыпать канал архивом
    if first_run and not FIRST_RUN_POST:
        save_state([m["id"] for m in messages])
        log("Первый запуск: текущие посты помечены как просмотренные.")
        return 0

    now = datetime.now(timezone.utc)
    sent = 0

    for idx, msg in enumerate(messages):
        if sent >= MAX_POSTS_PER_RUN:
            break
        if msg["id"] in posted_set or not msg["raw_text"]:
            continue
        if msg["dt"] and now - msg["dt"] > timedelta(hours=MAX_AGE_HOURS):
            continue
        if not matches_keywords(msg["raw_text"]):
            continue

        text = clean_text(msg["el"])
        photos, ids = collect_album(messages, idx)
        tags = build_tags(msg["raw_text"])

        try:
            send_post(text, tags, photos)
        except Exception as e:  # не помечаем как отправленный – повторим в следующий раз
            log(f"Ошибка отправки поста {msg['id']}: {e}")
            continue

        posted.extend(ids)
        posted_set.update(ids)
        save_state(posted)
        sent += 1
        log(f"Опубликован пост {msg['id']}")
        time.sleep(2)

    if not STATE_FILE.exists():
        save_state(posted)
    log(f"Готово. Новых публикаций: {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
