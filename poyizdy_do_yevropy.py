#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Щоденний пост «Поїзди до Європи без пересадок: що відправляється сьогодні»
для Telegram-каналу «Сумський синоптик» — https://t.me/sumskoy_sinoptik

Як це працює
  1. poyizdy_do_yevropy_routes.json — перевірений довідник прямих рейсів
     (номер, маршрут, дні руху: щодня / парні / непарні, ціни «від»).
  2. Скрипт щодня звіряє довідник з офіційною сторінкою Укрзалізниці
     (uz-vezemo.uz.gov.ua) і ПІДТЯГУЄ з неї актуальний час відправлення/прибуття.
     Якщо рейсу на сторінці немає — це видно в логу (GitHub warning).
  3. Для сьогоднішньої дати відбираються рейси за парністю числа і публікується
     картка + текст.

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  FORCE_RUN=1, AUTO_SYNC=0 (не підтягувати час з офіційної сторінки)

Запуск:
    python poyizdy_do_yevropy.py --dry-run            # без відправки
    python poyizdy_do_yevropy.py --dry-run --date 2026-10-18
    python poyizdy_do_yevropy.py --audit              # звірка ВСІХ рейсів (і вимкнених)
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from poyizdy_do_yevropy_card import render_card

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
POST_HOUR = 8                       # публікуємо о 08:xx за Києвом (до ранкових відправлень)
ROUTES_FILE = Path(__file__).with_name("poyizdy_do_yevropy_routes.json")
CARD_PATH = "poyizdy_do_yevropy_card.png"
UZ_URL = "https://uz-vezemo.uz.gov.ua/"
UZ_APP = "app.uz.gov.ua"
AUTO_SYNC = os.getenv("AUTO_SYNC", "1") != "0"

WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sumskoy-sinoptik-bot/1.0)"}
log = logging.getLogger("poyizdy")

HASHTAGS_BASE = "#СумськийСиноптик #ПоїздиДоЄвропи #Укрзалізниця #Залізниця #ПрямийПоїзд"
COUNTRY_TAGS = {"PL": "#Польща #Перемишль", "HU": "#Угорщина", "SK": "#Словаччина",
                "AT": "#Австрія", "MD": "#Молдова"}


# ── Довідник ───────────────────────────────────────────────────────────────
def load_routes() -> dict:
    return json.loads(ROUTES_FILE.read_text(encoding="utf-8"))


def runs_on(route: dict, day: date) -> bool:
    rule = route.get("days", "daily")
    if rule == "daily":
        return True
    return (day.day % 2 == 1) == (rule == "odd")


# ── Офіційна сторінка УЗ: звірка і підтягування часу ───────────────────────
_TIME = re.compile(r"^\d{1,2}:\d{2}$")
_TRAIN = re.compile(r"^(?:(?:[ІI][СC]|EC|EN|RJX?|R)\+?\s*)?0*(\d{1,4})$")
_ARROWS = {"➔", "→", "➜", "➝", "›"}


def _norm_time(t: str) -> str:
    h, m = t.split(":")
    return f"{int(h):02d}:{m}"


def fetch_official_tokens() -> list[str]:
    """Сторінка → плоский список текстових фрагментів без стрілок."""
    last: Exception | None = None
    for i in range(3):
        try:
            r = requests.get(UZ_URL, headers=HEADERS, timeout=25)
            r.raise_for_status()
            text = BeautifulSoup(r.text, "html.parser").get_text("\n")
            return [t.strip() for t in text.split("\n") if t.strip() and t.strip() not in _ARROWS]
        except requests.RequestException as e:
            last = e
            log.warning("Офіційна сторінка УЗ недоступна (спроба %d/3): %s", i + 1, e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Не вдалося отримати {UZ_URL}: {last}")


def find_official(route: dict, tokens: list[str]) -> Optional[tuple[str, str]]:
    """Шукає блок «№ | Звідки | відпр. | Куди | прибуття» → (відпр., приб.)."""
    frm, to = route["from"].lower()[:4], route["to"].lower()[:4]
    for i, tok in enumerate(tokens[:-4]):
        m = _TRAIN.match(tok)
        if not m or m.group(1) != route["uz"]:
            continue
        a, dep, b, arr = tokens[i + 1], tokens[i + 2], tokens[i + 3], tokens[i + 4]
        if (a.lower().startswith(frm) and b.lower().startswith(to)
                and _TIME.match(dep) and _TIME.match(arr)):
            return _norm_time(dep), _norm_time(arr)
    return None


def sync_with_official(routes: list[dict], tokens: Optional[list[str]]) -> dict[str, str]:
    """Оновлює час у маршрутах з офіційної сторінки. Повертає {id: статус}."""
    status: dict[str, str] = {}
    for r in routes:
        if tokens is None:
            status[r["id"]] = "офіційна сторінка недоступна"
            continue
        off = find_official(r, tokens)
        if not off:
            status[r["id"]] = "НЕ ЗНАЙДЕНО на офіційній сторінці"
            continue
        if off == (r["dep"], r["arr"]):
            status[r["id"]] = "ок"
            continue
        status[r["id"]] = f"час на сторінці {off[0]} → {off[1]} (у довіднику {r['dep']} → {r['arr']})"
        if AUTO_SYNC:
            r["dep"], r["arr"] = off
            status[r["id"]] += " — оновлено автоматично"
    return status


# ── Розрахунки ─────────────────────────────────────────────────────────────
def _minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def duration_text(r: dict, tz_shift: int) -> str:
    """Реальний час у дорозі з урахуванням різниці поясів (Польща й ін. — на 1 год позаду)."""
    total = r["arr_day"] * 1440 + _minutes(r["arr"]) + tz_shift - _minutes(r["dep"])
    if total <= 0:
        total += 1440
    h, m = divmod(total, 60)
    return f"{h} г {m:02d} хв" if m else f"{h} г"


def money(x: int) -> str:
    return f"{x:,}".replace(",", "\u00a0")


def prices_text(r: dict) -> str:
    parts = [f"{k} від {money(v)}" for k, v in (r.get("prices") or {}).items() if v]
    return (" · ".join(parts) + " грн") if parts else ""


# ── Збірка даних ───────────────────────────────────────────────────────────
def collect(day: date, with_official: bool = True) -> tuple[dict, dict]:
    cfg = load_routes()
    countries = cfg["countries"]
    routes = [r for r in cfg["routes"] if r.get("enabled")]

    tokens = None
    if with_official:
        try:
            tokens = fetch_official_tokens()
        except Exception as e:
            log.warning("%s — використовуємо довідник без звірки", e)
    status = sync_with_official(cfg["routes"], tokens)
    enabled_ids = {r["id"] for r in routes}
    for rid, st in status.items():
        if st != "ок" and rid in enabled_ids:     # про вимкнені рейси — лише в --audit
            print(f"::warning title=Рейс {rid}::{st}")
            log.warning("Рейс %s: %s", rid, st)

    today = [r for r in routes if runs_on(r, day)]
    today.sort(key=lambda r: (list(countries).index(r["country"]), _minutes(r["dep"])))
    trains = []
    for r in today:
        c = countries[r["country"]]
        trains.append({
            "code": r["country"], "country": c["name"], "emoji": c["emoji"],
            "train": r["train"], "kind": r["kind"], "from": r["from"], "to": r["to"],
            "dep": r["dep"], "arr": r["arr"], "arr_day": r["arr_day"],
            "duration": duration_text(r, c["tz_shift"]),
            "prices": prices_text(r), "note": r.get("note"),
        })
    data = {
        "date_short": day.strftime("%d.%m.%Y"),
        "weekday": WEEKDAYS[day.weekday()],
        "parity": "непарне" if day.day % 2 else "парне",
        "prices_checked": cfg["meta"].get("prices_checked"),
        "trains": trains,
    }
    return data, status


# ── Текст посту ────────────────────────────────────────────────────────────
def build_text(data: dict) -> str:
    e = html.escape
    L = [
        "🚆 <b>Поїзди до Європи без пересадок</b>",
        f"📅 {data['weekday'].capitalize()}, {data['date_short']} · {data['parity']} число",
        "",
    ]
    if not data["trains"]:
        L += ["Сьогодні за нашим довідником прямих рейсів з України немає.",
              f"Розклад на інші дні — у застосунку «Укрзалізниці» ({UZ_APP})."]
    else:
        L.append("<b>Сьогодні відправляються:</b>")
        current = None
        for t in data["trains"]:
            if t["country"] != current:
                current = t["country"]
                L += ["", f"{t['emoji']} <b>{e(current)}</b>"]
            nxt = f" <i>(+{t['arr_day']} дн.)</i>" if t["arr_day"] else ""
            L.append(f"🚆 <b>{e(t['train'])}</b> · {e(t['from'])} → {e(t['to'])}")
            L.append(f"    🕒 {t['dep']} → {t['arr']}{nxt} · в дорозі {t['duration']} · {e(t['kind'])}")
            if t["prices"]:
                L.append(f"    💰 {e(t['prices'])}")
            if t["note"]:
                L.append(f"    ℹ️ <i>{e(t['note'])}</i>")

    L += [
        "",
        "⏱ <i>Час — місцевий на станції. Польща, Угорщина, Словаччина та Австрія на 1 годину "
        "відстають від України.</i>",
        f"🎟 <i>Квитки та наявність місць — у застосунку «Укрзалізниці» ({UZ_APP}).</i>",
    ]
    if any(t["prices"] for t in data["trains"]):
        when = f" станом на {data['prices_checked']}" if data.get("prices_checked") else ""
        L.append(f"💰 <i>Ціни — орієнтовні, «від»{when}; фактична залежить від дати та наявності місць.</i>")

    tags = [HASHTAGS_BASE] + sorted({COUNTRY_TAGS.get(t["code"], "") for t in data["trains"]} - {""})
    L += ["", " ".join(tags)]
    return "\n".join(L)


# ── Telegram ───────────────────────────────────────────────────────────────
def tg(method: str, token: str, **kw) -> dict:
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def publish(token: str, chat_id: str, card: str, text: str) -> None:
    with open(card, "rb") as f:
        tg("sendPhoto", token, data={"chat_id": chat_id}, files={"photo": f})
    tg("sendMessage", token, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"})


# ── main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати в Telegram")
    ap.add_argument("--force", action="store_true", help="ігнорувати перевірку години")
    ap.add_argument("--audit", action="store_true", help="звірити всі рейси з офіційною сторінкою")
    ap.add_argument("--date", help="дата для тесту, YYYY-MM-DD")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    now = datetime.now(TZ)
    day = date.fromisoformat(args.date) if args.date else now.date()

    if args.audit:
        cfg = load_routes()
        try:
            status = sync_with_official(cfg["routes"], fetch_official_tokens())
        except Exception as e:
            log.error("%s", e)
            return 1
        for r in cfg["routes"]:
            flag = "✅ увімкнено" if r.get("enabled") else "⏸ вимкнено"
            print(f"{r['id']:>4} {r['from']} → {r['to']:<10} {flag:<14} {status[r['id']]}")
        return 0

    force = args.force or args.dry_run or os.getenv("FORCE_RUN") == "1"
    if not force and now.hour != POST_HOUR:
        log.info("У Києві зараз %s — не час публікації, вихід.", now.strftime("%H:%M"))
        return 0

    data, _ = collect(day)
    render_card(data, CARD_PATH)
    text = build_text(data)

    if args.dry_run:
        print(re.sub(r"</?(b|i)>", "", text))
        log.info("Dry-run: картку збережено в %s", CARD_PATH)
        return 0

    token, chat_id = os.getenv("BOT_TOKEN"), os.getenv("CHAT_ID")
    if not token or not chat_id:
        log.error("Не задано BOT_TOKEN / CHAT_ID")
        return 1
    publish(token, chat_id, CARD_PATH, text)
    log.info("Опубліковано.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
