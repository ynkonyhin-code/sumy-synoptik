#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Щоденний пост «Курс дорогоцінних металів в Україні» для Telegram-каналу
«Сумський синоптик» — https://t.me/sumskoy_sinoptik

Джерела:
  1. НБУ (офіційний JSON API)  — основа посту + динаміка до вчора.
  2. Finance.ua (зведені таблиці tables.finance.ua) — злитки золота: Комінбанк,
     Індустріалбанк, МТБ Банк, ЄПБ. Якщо банку немає в таблиці — він пропускається.
  3. Ломбарди — ОРІЄНТОВНИЙ розрахунок від ціни НБУ за пробами
     (стабільного публічного API у ломбардів немає). Коефіцієнти — в налаштуваннях.

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  FORCE_RUN=1, LOMBARD_GOLD_K, LOMBARD_SILVER_K

Запуск:
    python kurs_dorohotsinnykh_metaliv.py --dry-run     # без відправки
    python kurs_dorohotsinnykh_metaliv.py --force       # ігнорувати перевірку часу
"""
from __future__ import annotations

import argparse
import html
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from kurs_dorohotsinnykh_metaliv_card import fmt_money, render_card

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
POST_HOUR = 11                      # о котрій годині за Києвом публікуємо
CARD_PATH = "kurs_dorohotsinnykh_metaliv_card.png"
TROY_OZ = 31.1034768                # грамів у тройській унції

NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
METALS = {                          # код НБУ → (назва, емодзі)
    "XAU": ("Золото", "🥇"),
    "XAG": ("Срібло", "🥈"),
    "XPT": ("Платина", "💎"),
    "XPD": ("Паладій", "🔹"),
}

# Банки: (назва в пості, можливі написання в таблиці Finance.ua, у нижньому регістрі).
# ПриватБанк у зведених таблицях Finance.ua не публікує ціни, тому його тут немає.
BANKS = [
    ("Комінбанк", ("комінбанк", "коминбанк")),
    ("Індустріалбанк", ("індустріалбанк", "индустриалбанк")),
    ("МТБ Банк", ("мтб банк", "мтб")),
    ("ЄПБ", ("єпб", "епб")),
]
# Зведені таблиці Finance.ua: код номіналу злитка → підпис.
# Перевірені: 70 = тр. унція, 80 = 50 г, 40 = 5 г, 10 = 1 г.
# Беремо перший номінал, за яким знайдено хоча б один банк.
BAR_CODES = [("70", "тр. унція"), ("80", "50 г"), ("40", "5 г"), ("10", "1 г")]
TABLE_URLS = [
    "https://tables.finance.ua/ua/metals/cash/-/ua/xau/{code}",
    "https://tables.finance.ua/ru/metals/cash/-/ua/xau/{code}",
]

# Ломбарди: яку частку вартості «чистого» металу, як правило, дають за лом.
# Це оціночний діапазон (мін, макс); реальна ціна залежить від ломбарду, ваги, стану.
LOMBARD_GOLD_K = tuple(float(x) for x in os.getenv("LOMBARD_GOLD_K", "0.70,0.85").split(","))
LOMBARD_SILVER_K = tuple(float(x) for x in os.getenv("LOMBARD_SILVER_K", "0.55,0.75").split(","))
LOMBARD_ITEMS = [  # (підпис, метал, проба)
    ("Золото 375 проби", "XAU", 375),
    ("Золото 585 проби", "XAU", 585),
    ("Золото 750 проби", "XAU", 750),
    ("Срібло 925 проби", "XAG", 925),
]

HASHTAGS = (
    "#СумськийСиноптик #КурсМеталів #ДорогоцінніМетали #Золото #Срібло "
    "#Платина #Паладій #Ломбард #НБУ #Суми #Україна"
)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sumskoy-sinoptik-bot/1.0)"}
log = logging.getLogger("kurs")


# ── HTTP ───────────────────────────────────────────────────────────────────
def http_get(url: str, params: Optional[dict] = None, tries: int = 3) -> requests.Response:
    last: Exception | None = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            log.warning("GET %s не вдалося (спроба %d/%d): %s", url, i + 1, tries, e)
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Не вдалося отримати {url}: {last}")


# ── НБУ ────────────────────────────────────────────────────────────────────
def fetch_nbu(day: Optional[datetime] = None) -> dict[str, float]:
    """Повертає {код: курс} для металів. Порожній словник, якщо даних немає."""
    params = {"json": ""}
    if day:
        params["date"] = day.strftime("%Y%m%d")
    items = http_get(NBU_URL, params=params).json()
    return {i["cc"]: float(i["rate"]) for i in items if i.get("cc") in METALS}


def to_gram(rates: dict[str, float]) -> dict[str, float]:
    """НБУ публікує метали за тройську унцію; страхуємось евристикою,
    якщо раптом формат зміниться (ціна золота за унцію в грн ≫ 30 000)."""
    per_oz = rates.get("XAU", 0) > 30_000
    return {k: (v / TROY_OZ if per_oz else v) for k, v in rates.items()}


def build_nbu(today: datetime) -> dict:
    cur = to_gram(fetch_nbu())
    if not cur:
        raise RuntimeError("НБУ не повернув курси металів")
    prev: dict[str, float] = {}
    for back in range(1, 6):          # шукаємо найближчий попередній день з даними
        try:
            prev = to_gram(fetch_nbu(today - timedelta(days=back)))
        except Exception as e:  # динаміка — не критично
            log.warning("Попередній курс НБУ недоступний: %s", e)
            break
        if prev:
            break
    out = {}
    for cc, (name, _) in METALS.items():
        if cc not in cur:
            continue
        p = prev.get(cc)
        delta = cur[cc] - p if p else None
        pct = (delta / p * 100) if p else None
        out[cc] = {"name": name, "per_gram": cur[cc], "delta": delta, "pct": pct}
    return out


# ── Банки (зведені таблиці Finance.ua) ─────────────────────────────────────
_NUM = re.compile(r"\d{1,3}(?:[\s\u00a0]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?")
_HAS_LETTER = re.compile(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]")


def _num(text: str) -> Optional[float]:
    m = _NUM.fullmatch(text.strip())
    if not m:
        return None
    return float(re.sub(r"[\s\u00a0]", "", m.group(0)).replace(",", "."))


def parse_table(html_text: str, gold_gram: float) -> list[dict]:
    """Рядки таблиці: Час | Купівля | Продаж | Назва | Телефон | Місто."""
    soup = BeautifulSoup(html_text, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        texts = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        texts = [t for t in texts if t]
        name_i = next((i for i, t in enumerate(texts) if _HAS_LETTER.search(t) and ":" not in t), None)
        if name_i is None:
            continue
        nums = [_num(t) for t in texts[:name_i] if ":" not in t]
        nums = [x for x in nums if x is not None]
        if len(nums) != 2:               # потрібні і купівля, і продаж
            continue
        buy, sell = nums
        if not (0.5 * gold_gram <= buy <= sell <= 2.0 * gold_gram):
            continue
        rows.append({"name": texts[name_i], "buy": buy, "sell": sell})
    return rows


def _load_rows(code: str, gold_gram: float) -> list[dict]:
    for tpl in TABLE_URLS:
        try:
            rows = parse_table(http_get(tpl.format(code=code), tries=2).text, gold_gram)
        except Exception as e:
            log.warning("Таблиця %s недоступна: %s", tpl.format(code=code), e)
            continue
        if rows:
            return rows
        log.warning("У таблиці %s не знайдено рядків з цінами", tpl.format(code=code))
    return []


def build_banks(gold_gram: float) -> list[dict]:
    for code, label in BAR_CODES:
        rows = _load_rows(code, gold_gram)
        result = []
        for title, aliases in BANKS:
            row = next((r for r in rows if r["name"].lower().startswith(aliases)), None)
            if row:
                result.append({"name": title, "bar": label, "buy": row["buy"], "sell": row["sell"]})
        if result:
            log.info("Банки: номінал «%s», знайдено %d; у таблиці: %s", label, len(result),
                     ", ".join(r["name"] for r in rows[:8]))
            return result
        if rows:
            log.warning("Номінал «%s»: банки не впізнано; у таблиці: %s", label,
                        ", ".join(r["name"] for r in rows[:8]))
    return []


# ── Ломбарди (розрахунок) ──────────────────────────────────────────────────
def _round(x: float) -> float:
    return round(x / 10) * 10 if x >= 100 else round(x)


def build_lombard(nbu: dict) -> list[dict]:
    out = []
    for label, cc, fineness in LOMBARD_ITEMS:
        if cc not in nbu:
            continue
        pure = nbu[cc]["per_gram"] * fineness / 1000
        k_low, k_high = LOMBARD_GOLD_K if cc == "XAU" else LOMBARD_SILVER_K
        out.append({"label": label, "low": _round(pure * k_low), "high": _round(pure * k_high)})
    return out


# ── Текст посту ────────────────────────────────────────────────────────────
def _delta_text(m: dict) -> str:
    d = m.get("delta")
    if d is None:
        return ""
    if abs(d) < 0.005:
        return " ➖ <i>без змін</i>"
    arrow, sign = ("🔺", "+") if d > 0 else ("🔻", "−")
    return f" {arrow} <i>{sign}{fmt_money(abs(d))} ({sign}{fmt_money(abs(m['pct']), 1)}%)</i>"


def build_text(data: dict) -> str:
    e = html.escape
    L = [
        "🏆 <b>Курс дорогоцінних металів в Україні</b>",
        f"📅 {data['date']} · станом на 11:00",
        "",
        "🏛 <b>Офіційний курс НБУ</b> <i>(грн за 1 г)</i>",
    ]
    for cc, m in data["nbu"].items():
        L.append(f"{METALS[cc][1]} {m['name']} — <b>{fmt_money(m['per_gram'])}</b>{_delta_text(m)}")

    L += ["", "🏦 <b>Банки: злитки золота</b> <i>(грн за 1 г)</i>"]
    if data["banks"]:
        for b in data["banks"]:
            L.append(
                f"▪️ {e(b['name'])} <i>({b['bar']})</i>: купівля <b>{fmt_money(b['buy'], 0)}</b>"
                f" · продаж <b>{fmt_money(b['sell'], 0)}</b>"
            )
    else:
        L.append("<i>Дані банків тимчасово недоступні</i>")

    L += ["", "♻️ <b>Ломбарди: прийом лому</b> <i>(грн за 1 г, орієнтовно)</i>"]
    for it in data["lombard"]:
        L.append(f"▪️ {e(it['label'])}: <b>{fmt_money(it['low'], 0)} – {fmt_money(it['high'], 0)}</b>")

    L += [
        "",
        "ℹ️ <i>Курс НБУ — офіційний. Банківські ціни — за даними Finance.ua, "
        "ломбардні — розрахунок: остаточну ціну визначає оцінювач за пробою, вагою і станом виробу.</i>",
        "",
        HASHTAGS,
    ]
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
    tg("sendMessage", token, data={
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })


# ── main ───────────────────────────────────────────────────────────────────
def collect() -> dict:
    now = datetime.now(TZ)
    nbu = build_nbu(now)
    return {
        "date": now.strftime("%d.%m.%Y"),
        "nbu": nbu,
        "banks": build_banks(nbu["XAU"]["per_gram"]) if "XAU" in nbu else [],
        "lombard": build_lombard(nbu),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати в Telegram")
    ap.add_argument("--force", action="store_true", help="ігнорувати перевірку години")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    force = args.force or os.getenv("FORCE_RUN") == "1"
    now = datetime.now(TZ)
    # Cron у GitHub працює в UTC, тому запускається двічі (літній/зимовий час);
    # публікуємо лише коли у Києві справді 11:xx.
    if not force and not args.dry_run and now.hour != POST_HOUR:
        log.info("У Києві зараз %s — не час публікації, вихід.", now.strftime("%H:%M"))
        return 0

    data = collect()
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
