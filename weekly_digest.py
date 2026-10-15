"""Публикация недельного итога в канал.

    python weekly_digest.py          # отправить в канал
    python weekly_digest.py --dry    # только показать текст, ничего не отправлять
Переменные окружения: BOT_TOKEN, CHAT_ID
"""
import os
import sys

import requests

from events_db import weekly_digest

# Хештеги поста: меняйте как нравится
TAGS = "#Суми #СумськийСиноптик #Погода #ПідсумокТижня"


def main():
    text = weekly_digest() + "\n\n" + TAGS
    if "--dry" in sys.argv:
        print(text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/sendMessage",
        data={"chat_id": os.environ["CHAT_ID"], "text": text, "parse_mode": "HTML"},
        timeout=30)
    r.raise_for_status()


if __name__ == "__main__":
    main()
