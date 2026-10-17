#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Щоденний пост «Курс криптовалют» для Telegram-каналу «Сумський синоптик»
https://t.me/sumskoy_sinoptik   ·   публікація о 12:00 за Києвом

Джерела:
  • CoinGecko  — ціни в USD і UAH, зміна за 24 год і 7 днів, 7-денний графік;
  • НБУ        — офіційний курс USD;
  • Alternative.me — індекс «страху й жадібності» (настрій ринку).

«Прогноз»: цін криптовалют ніхто не може передбачити, тому замість прогнозів пост дає
технічний огляд — тренд за тиждень, положення ціни в тижневому діапазоні, волатильність —
та індекс настрою ринку. Це інформація, а не інвестиційна порада.

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  COINGECKO_API_KEY (безкоштовний Demo-ключ — менше обмежень), FORCE_RUN=1

Запуск:
    python kurs_kryptovalyut.py --dry-run
"""
from __future__ import annotations

import argparse
import html
import logging
import os
import re
import statistics
import sys
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from kurs_kryptovalyut_card import fmt_num, fmt_pct, fmt_usd, render_card

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
POST_HOUR = 12
CARD_PATH = "kurs_kryptovalyut_card.png"
CG = "https://api.coingecko.com/api/v3"
API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

# (id у CoinGecko, тікер, назва, колір на картці)
COINS = [
    ("bitcoin", "BTC", "Bitcoin", (247, 147, 26)),
    ("ethereum", "ETH", "Ethereum", (130, 150, 230)),
    ("tether", "USDT", "Tether", (80, 190, 150)),
    ("binancecoin", "BNB", "BNB", (240, 200, 70)),
    ("solana", "SOL", "Solana", (150, 100, 240)),
    ("ripple", "XRP", "XRP", (200, 205, 215)),
    ("the-open-network", "TON", "Toncoin", (70, 160, 240)),
    ("dogecoin", "DOGE", "Dogecoin", (225, 190, 90)),
]
MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
          "вересня", "жовтня", "листопада", "грудня"]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sumskoy-sinoptik-bot/1.0)", "Accept": "application/json"}
HASHTAGS = ("#СумськийСиноптик #Криптовалюта #КурсКриптовалют #Біткоїн #Ethereum "
            "#Крипта #BTC #ETH #USDT")
log = logging.getLogger("krypto")


# ── HTTP ───────────────────────────────────────────────────────────────────
def get_json(url: str, params: Optional[dict] = None, tries: int = 4, cg: bool = False):
    headers = dict(HEADERS)
    if cg and API_KEY:
        headers["x-cg-demo-api-key"] = API_KEY
    last: Exception | None = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=25)
            if r.status_code == 429:                       # ліміт CoinGecko — чекаємо і пробуємо ще
                wait = int(r.headers.get("Retry-After", 0)) or 20 * (i + 1)
                log.warning("429 від %s, чекаємо %d с (спроба %d/%d)", url, wait, i + 1, tries)
                time.sleep(min(wait, 90))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            log.warning("GET %s не вдалося (спроба %d/%d): %s", url, i + 1, tries, e)
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Не вдалося отримати {url}: {last}")


# ── Дані ───────────────────────────────────────────────────────────────────
def fetch_markets(vs: str, sparkline: bool) -> dict[str, dict]:
    ids = ",".join(c[0] for c in COINS)
    rows = get_json(f"{CG}/coins/markets", cg=True, params={
        "vs_currency": vs, "ids": ids, "order": "market_cap_desc", "per_page": 50,
        "sparkline": "true" if sparkline else "false", "price_change_percentage": "24h,7d"})
    return {r["id"]: r for r in rows}


def fetch_nbu_usd() -> Optional[float]:
    try:
        data = get_json("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange",
                        params={"valcode": "USD", "json": ""}, tries=2)
        return float(data[0]["rate"])
    except Exception as e:
        log.warning("Курс НБУ недоступний: %s", e)
        return None


FNG_LABELS = [(24, "Екстремальний страх"), (44, "Страх"), (55, "Нейтрально"),
              (75, "Жадібність"), (100, "Екстремальна жадібність")]


def fetch_fear_greed() -> Optional[dict]:
    try:
        data = get_json("https://api.alternative.me/fng/", params={"limit": 2}, tries=2)["data"]
        val = int(data[0]["value"])
        label = next(lbl for lim, lbl in FNG_LABELS if val <= lim)
        y = int(data[1]["value"]) if len(data) > 1 else None
        return {"value": val, "label": label, "yesterday": y, "delta": None if y is None else val - y}
    except Exception as e:
        log.warning("Індекс страху й жадібності недоступний: %s", e)
        return None


# ── Технічний огляд ────────────────────────────────────────────────────────
def analyze(price: float, series: list[float]) -> Optional[dict]:
    if not series or len(series) < 24:
        return None
    sma7, sma24 = statistics.fmean(series), statistics.fmean(series[-24:])
    lo, hi = min(series + [price]), max(series + [price])
    pos = (price - lo) / (hi - lo) if hi > lo else 0.5
    spread = (hi - lo) / lo * 100
    if price > sma7 * 1.015 and sma24 > sma7:
        trend = "висхідний"
    elif price < sma7 * 0.985 and sma24 < sma7:
        trend = "низхідний"
    else:
        trend = "бічний"
    return {"trend": trend, "lo": lo, "hi": hi, "pos": pos, "spread": spread,
            "pos_text": "нижній третині" if pos < 0.33 else "середній третині" if pos < 0.66 else "верхній третині",
            "vol": "низька" if spread < 5 else "помірна" if spread < 12 else "висока"}


def summary_for(coin: dict, a: Optional[dict], name: str) -> str:
    if not a:
        return "Недостатньо даних для технічного огляду."
    ch7 = coin.get("price_change_percentage_7d_in_currency")
    ch = f" ({fmt_pct(ch7)})" if ch7 is not None else ""
    return (f"{name} за тиждень{ch}: {a['trend']} рух. Ціна у {a['pos_text']} тижневого діапазону "
            f"{fmt_usd(a['lo'])}–{fmt_usd(a['hi'])}, волатильність {a['vol']}.")


# ── Збірка ─────────────────────────────────────────────────────────────────
def collect() -> dict:
    usd = fetch_markets("usd", True)
    time.sleep(2)                                           # м'яко щодо ліміту CoinGecko
    uah = fetch_markets("uah", False)
    nbu = fetch_nbu_usd()
    fg = fetch_fear_greed()
    now = datetime.now(TZ)

    coins = []
    for cid, sym, name, color in COINS:
        u, h = usd.get(cid), uah.get(cid)
        if not u:
            log.warning("Немає даних для %s", sym)
            continue
        price_uah = (h or {}).get("current_price") or (u["current_price"] * (nbu or 0))
        coins.append({
            "id": cid, "symbol": sym, "name": name, "color": list(color),
            "price_usd": u["current_price"], "price_uah": price_uah,
            "change_24h": u.get("price_change_percentage_24h_in_currency") or u.get("price_change_percentage_24h"),
            "change_7d": u.get("price_change_percentage_7d_in_currency"),
            "spark": (u.get("sparkline_in_7d") or {}).get("price") or [],
        })
    if not coins:
        raise RuntimeError("CoinGecko не повернув жодної монети")

    by = {c["symbol"]: c for c in coins}
    analysis = {s: analyze(c["price_usd"], c["spark"]) for s, c in by.items() if s != "USDT"}

    exchange = []
    if nbu:
        exchange.append(("USD · курс НБУ", f"{fmt_num(nbu)} ₴"))
    if "USDT" in by:
        exchange.append(("USDT ≈", f"{fmt_num(by['USDT']['price_uah'])} ₴"))
    for s in ("BTC", "ETH"):
        if s in by:
            p = by[s]["price_uah"]
            exchange.append((f"1 {s} ≈", f"{fmt_num(p, 0 if p >= 1000 else 2)} ₴"))
    if "USDT" in by and by["USDT"]["price_uah"]:
        exchange.append(("10 000 ₴ ≈", f"{fmt_num(10000 / by['USDT']['price_uah'], 1)} USDT"))

    btc_raw = usd.get("bitcoin", {})
    summary = summary_for(btc_raw, analysis.get("BTC"), "BTC") if "BTC" in by else ""
    return {
        "date_long": f"{now.day} {MONTHS[now.month - 1]} {now.year}",
        "coins": coins, "fear_greed": fg, "exchange": exchange,
        "summary": summary, "analysis": analysis, "nbu": nbu,
    }


# ── Текст посту ────────────────────────────────────────────────────────────
def trend_icon(t: str) -> str:
    return {"висхідний": "📈", "низхідний": "📉"}.get(t, "↔️")


def build_text(data: dict) -> str:
    e = html.escape
    L = ["₿ <b>Курс криптовалют</b>", f"📅 {data['date_long']} · станом на 12:00", ""]

    fg = data.get("fear_greed")
    if fg:
        mood = f"🧭 <b>Настрій ринку:</b> {fg['value']}/100 — {fg['label'].lower()}"
        if fg["delta"] is not None:
            mood += f" (вчора {fg['yesterday']})"
        L += [mood, ""]

    # Таблиця у моноширинному блоці — рівні колонки
    rows = []
    for c in data["coins"]:
        ch, ch7 = c["change_24h"], c["change_7d"]
        arrow = "▲" if (ch or 0) > 0 else "▼" if (ch or 0) < 0 else "■"
        rows.append(f"{c['symbol']:<5}{fmt_usd(c['price_usd']).replace(chr(160), ' '):>10}  "
                    f"{arrow}{fmt_pct(ch):>7}  {fmt_pct(ch7):>7}")
    L.append("<b>Ціна в USD · 24 год · 7 днів</b>")
    L.append("<pre>" + e("\n".join(rows)) + "</pre>")

    if data["exchange"]:
        L += ["", "💱 <b>Обмін на гривню</b> <i>(ринкові ціни CoinGecko)</i>"]
        for label, val in data["exchange"]:
            L.append(f"▪️ {e(label)} <b>{e(val)}</b>")

    L += ["", "🔭 <b>Технічний огляд</b> <i>(не прогноз цін)</i>"]
    for sym in ("BTC", "ETH"):
        a = data["analysis"].get(sym)
        if a:
            L.append(f"{trend_icon(a['trend'])} <b>{sym}:</b> тиждень — {a['trend']} рух, ціна у {a['pos_text']} "
                     f"діапазону {fmt_usd(a['lo'])}–{fmt_usd(a['hi'])}, волатильність {a['vol']}.")
    if fg:
        L.append("🧭 <i>Індекс страху й жадібності показує настрій учасників ринку, а не майбутню ціну.</i>")

    L += ["",
          "⚠️ <i>Це інформаційний огляд, а не інвестиційна порада. Курс криптовалют дуже мінливий, "
          "ризики — на вас. Реальні курси в обмінниках і на біржах відрізняються від ринкових на спред.</i>",
          "", HASHTAGS]
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
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    now = datetime.now(TZ)
    force = args.force or args.dry_run or os.getenv("FORCE_RUN") == "1"
    if not force and now.hour != POST_HOUR:
        log.info("У Києві зараз %s — не час публікації, вихід.", now.strftime("%H:%M"))
        return 0

    data = collect()                       # якщо CoinGecko недоступний — виняток, пост не виходить
    render_card(data, CARD_PATH)
    text = build_text(data)

    if args.dry_run:
        print(re.sub(r"</?(b|i|pre)>", "", text))
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
