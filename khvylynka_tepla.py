#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«Хвилинка тепла від Сумського синоптика» — щоденний короткий добрий пост
для Telegram-каналу https://t.me/sumskoy_sinoptik  ·  публікація о 19:00 за Києвом.

Рубрики за днями тижня (дописи лежать у khvylynka_tepla_posts.json і редагуються вручну):
  пн — маленька мудрість          пт — цікаво про Україну
  вт — факт про Суми та Сумщину   сб — рецепт від смутку (маленька справа)
  ср — сезонне спостереження/прикмета   нд — слова підтримки
  чт — добрий гумор

Вибір допису детермінований: за номером тижня, тож без бази й без повторів, поки є що
показувати (скільки днів до повтору — дивіться `python khvylynka_tepla.py --check`).
Сезонні дописи (поле months) показуються лише у відповідні місяці.
Про війну та політику дописів немає за задумом.

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  FORCE_RUN=1

Запуск:
    python khvylynka_tepla.py --dry-run
    python khvylynka_tepla.py --dry-run --date 2026-10-20
    python khvylynka_tepla.py --check
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from khvylynka_tepla_card import render_card, season_of

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
POST_HOUR = 19                                  # публікація о 19:xx за Києвом
POSTS_FILE = Path(__file__).with_name("khvylynka_tepla_posts.json")
CARD_PATH = "khvylynka_tepla_card.png"
CAPTION_LIMIT = 1000                            # ліміт Telegram для підпису до фото — 1024

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
          "вересня", "жовтня", "листопада", "грудня"]
SEASON_TAG = {"autumn": "#Осінь", "winter": "#Зима", "spring": "#Весна", "summer": "#Літо"}
BASE_TAGS = "#СумськийСиноптик #ХвилинкаТепла"
SIGNATURE = "— ваш Сумський синоптик ☀️"
log = logging.getLogger("teplo")


# ── Вибір допису ───────────────────────────────────────────────────────────
def load_posts() -> dict:
    return json.loads(POSTS_FILE.read_text(encoding="utf-8"))


def eligible(cat: dict, month: int) -> list[dict]:
    items = [p for p in cat["posts"] if not p.get("months") or month in p["months"]]
    return items or cat["posts"]                # якщо під сезон нічого немає — беремо все


def pick_post(day: date, cfg: dict) -> tuple[dict, dict, str]:
    """Повертає (допис, рубрика, ключ_рубрики)."""
    for sp in cfg.get("special", []):           # окремі дописи на конкретну дату
        if sp.get("month") == day.month and sp.get("day") == day.day:
            return sp, {"label": sp.get("label", "Хвилинка тепла"), "tag": sp.get("tag", "")}, "special"
    key, cat = next((k, c) for k, c in cfg["categories"].items() if c["weekday"] == day.weekday())
    items = eligible(cat, day.month)
    week = day.toordinal() // 7
    return items[week % len(items)], cat, key


# ── Текст ──────────────────────────────────────────────────────────────────
def build_caption(day: date, post: dict, cat: dict) -> str:
    e = html.escape
    season = season_of(day.month)
    tags = " ".join(x for x in (BASE_TAGS, cat.get("tag", ""), SEASON_TAG[season]) if x)
    parts = [f"🧡 <b>Хвилинка тепла</b> · <i>{e(cat['label'])}</i>", "", e(post["text"])]
    if post.get("source"):
        parts += ["", f"📚 <i>Джерело: {e(post['source'])}</i>"]
    parts += ["", SIGNATURE, "", tags]
    return "\n".join(parts)


# ── Telegram ───────────────────────────────────────────────────────────────
def tg(method: str, token: str, **kw) -> dict:
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def publish(token: str, chat_id: str, card: str, caption: str) -> None:
    plain_len = len(re.sub(r"<[^>]+>", "", caption))
    with open(card, "rb") as f:
        if plain_len <= CAPTION_LIMIT:          # коротко: картка з підписом — одне повідомлення
            tg("sendPhoto", token, data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
               files={"photo": f})
            return
        tg("sendPhoto", token, data={"chat_id": chat_id}, files={"photo": f})
    tg("sendMessage", token, data={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"})


# ── Перевірка запасу дописів ───────────────────────────────────────────────
def check(cfg: dict, today: date) -> None:
    print("Запас дописів (скільки тижнів до першого повтору в цій рубриці — у поточному сезоні):\n")
    low = False
    for key, cat in cfg["categories"].items():
        n_all, n_now = len(cat["posts"]), len(eligible(cat, today.month))
        flag = "  ⚠️ мало — додайте нових" if n_now < 5 else ""
        low |= n_now < 5
        print(f"  {cat['label']:<28} усього {n_all:>2}, зараз доречних {n_now:>2} → повтор через {n_now} тижн.{flag}")
    if low:
        print("::warning title=Мало дописів::У деяких рубриках мало свіжих дописів — час поповнити khvylynka_tepla_posts.json")
    print("\nПерегляд на найближчі 14 днів:")
    for i in range(14):
        d = today + timedelta(days=i)
        post, cat, _ = pick_post(d, cfg)
        print(f"  {d:%d.%m %a}: [{cat['label']}] {post['title']}")


# ── main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати в Telegram")
    ap.add_argument("--force", action="store_true", help="ігнорувати перевірку години")
    ap.add_argument("--check", action="store_true", help="показати запас дописів і найближчі 14 днів")
    ap.add_argument("--date", help="дата для тесту, YYYY-MM-DD")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    now = datetime.now(TZ)
    day = date.fromisoformat(args.date) if args.date else now.date()
    cfg = load_posts()

    if args.check:
        check(cfg, day)
        return 0

    force = args.force or args.dry_run or os.getenv("FORCE_RUN") == "1"
    if not force and now.hour != POST_HOUR:
        log.info("У Києві зараз %s — не час публікації, вихід.", now.strftime("%H:%M"))
        return 0

    post, cat, _ = pick_post(day, cfg)
    render_card({"title": post["title"], "label": cat["label"],
                 "date_long": f"{day.day} {MONTHS[day.month - 1]} {day.year}", "month": day.month}, CARD_PATH)
    caption = build_caption(day, post, cat)

    if args.dry_run:
        print(re.sub(r"</?(b|i)>", "", caption))
        log.info("Dry-run: символів у підписі %d, картку збережено в %s",
                 len(re.sub(r"<[^>]+>", "", caption)), CARD_PATH)
        return 0

    token, chat_id = os.getenv("BOT_TOKEN"), os.getenv("CHAT_ID")
    if not token or not chat_id:
        log.error("Не задано BOT_TOKEN / CHAT_ID")
        return 1
    publish(token, chat_id, CARD_PATH, caption)
    log.info("Опубліковано: %s", post["title"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
