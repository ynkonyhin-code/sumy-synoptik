#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zahalni_boyovi_vtraty.py

Берёт из канала Генштаба ЗСУ (t.me/GeneralStaffZSU) посты со сводкой
«Загальні бойові втрати противника з ...» и публикует их в свой канал:
текст + картинка, без ссылок, с тематическими тегами.
Опубликованные посты запоминаются в zahalni_boyovi_vtraty_posted.txt.

Переменные окружения: BOT_TOKEN, CHAT_ID (секреты GitHub).
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

HISTORY_FILE = "zahalni_boyovi_vtraty_posted.txt"
SOURCE_CHANNEL_URL = "https://t.me/s/GeneralStaffZSU"
KEY_PHRASE = "Загальні бойові втрати противника з"

MAX_AGE_HOURS = 48       # старые посты не публикуем (защита при пустой истории)
HISTORY_LIMIT = 500      # сколько последних id хранить
CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096

# Базовые теги (всегда) и теги по содержанию сводки
BASE_TAGS = ["#втративорога", "#зсу", "#генштаб", "#статистика", "#війна", "#україна",
             "#загальні_бойові_втрати"]
TOPIC_TAGS = [
    (r"особов\w+\s+склад", ["#особовий_склад"]),
    (r"танк", ["#танки"]),
    (r"бойов\w+\s+броньован|ббм|броньован", ["#бронетехніка"]),
    (r"артилерійськ|артсистем|рсзв", ["#артилерія"]),
    (r"ппо", ["#ППО"]),
    (r"літак|гелікоптер|вертольот", ["#авіація"]),
    (r"бпла|безпілотн", ["#БпЛА"]),
    (r"крилат\w+\s+ракет|ракет", ["#ракети"]),
    (r"корабл|катер|підводн\w+\s+човн", ["#флот"]),
    (r"автомобільн|автоцистерн|спеціальн\w+\s+техніка", ["#техніка"]),
]

# Строки с призывами подписаться / соцсетями удаляются целиком
JUNK_LINE_RE = re.compile(
    r"підписуйтесь|підписуйтеся|підписатися|підпишіться|приєднуйтесь|приєднуйтеся|"
    r"слідкуйте|соцмереж|facebook|instagram|youtube|viber|tiktok|telegram|телеграм|"
    r"фейсбук|інстаграм|ютуб|вайбер|twitter|х\.com",
    re.IGNORECASE,
)
URL_RE = re.compile(
    r"(https?://\S+|www\.\S+|t\.me/\S+|\b[\w-]+\.(?:com|ua|net|org|gov\.ua|me)\b\S*)",
    re.IGNORECASE,
)
MENTION_RE = re.compile(r"@\w+")
LINK_MARK = "\uE000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


# --------------------------------------------------------------------------- #
# История опубликованных постов
# --------------------------------------------------------------------------- #
def load_posted_ids() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def save_posted_id(post_id: str) -> None:
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{post_id}\n")


def trim_history() -> None:
    ids = load_posted_ids()
    if len(ids) > HISTORY_LIMIT:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(ids[-HISTORY_LIMIT:]) + "\n")


# --------------------------------------------------------------------------- #
# Обработка текста
# --------------------------------------------------------------------------- #
def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[«»“”„\"'’`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_clean_text(el) -> str:
    """Текст поста без ссылок, @упоминаний и призывов подписаться."""
    el = BeautifulSoup(str(el), "html.parser")
    for br in el.find_all("br"):
        br.replace_with("\n")
    for a in el.find_all("a"):
        a.replace_with(LINK_MARK)  # любая ссылка (в т.ч. хэштеги-ссылки) убирается

    lines = []
    for line in el.get_text().split("\n"):
        had_link = LINK_MARK in line
        line = line.replace(LINK_MARK, "")
        line = URL_RE.sub("", line)
        line = MENTION_RE.sub("", line)
        line = re.sub(r"[ \t]+", " ", line).strip(" \t|•·")

        if had_link:
            if not re.search(r"\w", line):          # строка состояла из ссылок
                continue
            letters = re.sub(r"[^\w]", "", line)
            if len(letters) <= 12 or (len(letters) <= 30 and re.search(r"[:\-–—➡️👉▶️]\s*$", line)):
                continue                              # «Детальніше:», «на канал» и т.п.
        if JUNK_LINE_RE.search(line):
            continue
        lines.append(line)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def build_tags(text: str) -> str:
    tags = list(BASE_TAGS)
    low = text.lower()
    for pattern, extra in TOPIC_TAGS:
        if re.search(pattern, low):
            tags.extend(extra)
    seen, result = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            result.append(t)
    return " ".join(result)


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
def tg_call(method: str, data=None, files=None) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    for _ in range(3):
        r = requests.post(url, data=data, files=files, timeout=90)
        if r.status_code == 429:
            wait = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(wait + 1)
            continue
        result = r.json()
        if not result.get("ok"):
            raise RuntimeError(f"{method}: {result}")
        return result
    raise RuntimeError(f"{method}: превышено число попыток")


def send_post(text: str, tags: str, photo_url) -> None:
    full = f"{text}\n\n{tags}" if text else tags

    if photo_url:
        img = requests.get(photo_url, headers=HEADERS, timeout=60)
        img.raise_for_status()
        fits = len(full) <= CAPTION_LIMIT
        data = {"chat_id": CHAT_ID}
        if fits:
            data["caption"] = full
        tg_call("sendPhoto", data, files={"photo": ("photo.jpg", img.content)})
        if fits:
            return
    # нет картинки или текст не помещается в подпись – отдельное сообщение
    tg_call("sendMessage", {
        "chat_id": CHAT_ID,
        "text": full[:MESSAGE_LIMIT],
        "disable_web_page_preview": True,
    })


# --------------------------------------------------------------------------- #
# Основная логика
# --------------------------------------------------------------------------- #
def main() -> int:
    if not BOT_TOKEN or not CHAT_ID:
        print("Ошибка: BOT_TOKEN или CHAT_ID не найдены в переменных окружения.")
        return 1

    posted = set(load_posted_ids())

    res = requests.get(SOURCE_CHANNEL_URL, headers=HEADERS, timeout=30)
    if res.status_code != 200:
        print(f"Не удалось загрузить страницу канала. Статус: {res.status_code}")
        return 1

    soup = BeautifulSoup(res.text, "html.parser")
    posts = soup.select(".tgme_widget_message[data-post]")  # порядок: от старых к новым
    key = normalize(KEY_PHRASE)
    now = datetime.now(timezone.utc)
    sent = 0

    for post in posts:
        post_id = post.get("data-post")
        if not post_id or post_id in posted:
            continue

        text_div = post.select_one(".tgme_widget_message_text")
        if not text_div:
            continue
        raw_text = text_div.get_text(" ", strip=True)
        if key not in normalize(raw_text):
            continue

        time_el = post.select_one(".tgme_widget_message_date time")
        if time_el and time_el.get("datetime"):
            try:
                dt = datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
                if now - dt > timedelta(hours=MAX_AGE_HOURS):
                    continue
            except ValueError:
                pass

        photo_url = None
        photo_a = post.select_one("a.tgme_widget_message_photo_wrap")
        if photo_a:
            m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", photo_a.get("style", ""))
            if m:
                photo_url = m.group(1)

        text = extract_clean_text(text_div)
        tags = build_tags(raw_text)

        print(f"Найден новый пост: {post_id}")
        try:
            send_post(text, tags, photo_url)
        except Exception as e:  # не записываем в историю – повторим при следующем запуске
            print(f"Ошибка отправки поста {post_id}: {e}")
            continue

        save_posted_id(post_id)
        posted.add(post_id)
        sent += 1
        print(f"Пост {post_id} успешно опубликован!")
        time.sleep(2)

    trim_history()
    print(f"Готово. Новых публикаций: {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
