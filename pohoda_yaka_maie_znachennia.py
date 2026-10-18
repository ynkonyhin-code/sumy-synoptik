#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«Погода, яка має значення» — щовечірній практичний пост про ЗАВТРАШНЮ погоду
для Telegram-каналу «Сумський синоптик»  ·  https://t.me/sumskoy_sinoptik  ·  ~21:00 за Києвом.

Що відповідає пост: чи потрібна шапка й парасолька, чи буде слизько, чи чекати туману
та сильного вітру, коли найкраще вийти на прогулянку. До нього додається рубрика
«Народний синоптик»: народна прикмета з жартом і чесним поясненням метеорологів.
ПРИКМЕТА ЗАВЖДИ ВІДОКРЕМЛЕНА ВІД ПРОГНОЗУ: прогноз — блок «Практично», прикмета —
окремий блок із вердиктом науки (є пояснення / частково / скоріше традиція).

Дані: прогнозна модель Open-Meteo для координат Сум (безкоштовно, без ключа).
Це НЕ офіційне попередження — про це сказано в кожному пості.

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  FORCE_RUN=1

Запуск:
    python pohoda_yaka_maie_znachennia.py --dry-run
    python pohoda_yaka_maie_znachennia.py --check
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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from pohoda_yaka_maie_znachennia_card import render_card

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
LAT, LON = 50.9077, 34.7981                      # Суми
POST_HOUR = 21
DATA_FILE = Path(__file__).with_name("pohoda_yaka_maie_znachennia_data.json")
CARD_PATH = "pohoda_yaka_maie_znachennia_card.png"
API = "https://api.open-meteo.com/v1/forecast"
HOURLY = ("temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,precipitation_probability,"
          "precipitation,snowfall,weather_code,cloud_cover,visibility,wind_speed_10m,wind_gusts_10m")

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
          "вересня", "жовтня", "листопада", "грудня"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя"]
STATUS = {0: "✅", 1: "⚠️", 2: "❗"}               # свідомо не 🟢🟡🔴 — щоб не плутати зі статусами тривог
HASHTAGS = "#СумськийСиноптик #ПогодаЯкаМаєЗначення #НароднийСиноптик #ПогодаСуми"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sumskoy-sinoptik-bot/1.0)"}
log = logging.getLogger("pohoda")


# ── Дані ───────────────────────────────────────────────────────────────────
def load_db() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def fetch_forecast() -> dict:
    params = {"latitude": LAT, "longitude": LON, "hourly": HOURLY, "wind_speed_unit": "ms",
              "timezone": "Europe/Kyiv", "forecast_days": 3}
    last: Exception | None = None
    for i in range(4):
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=25)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            log.warning("Open-Meteo не відповів (спроба %d/4): %s", i + 1, e)
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Не вдалося отримати прогноз: {last}")


def hours_for(forecast: dict, target: date) -> dict[int, dict]:
    h = forecast["hourly"]
    out: dict[int, dict] = {}
    for i, ts in enumerate(h["time"]):
        dt = datetime.fromisoformat(ts)
        if dt.date() != target:
            continue

        def g(key, default=0.0):
            v = h.get(key, [None] * len(h["time"]))[i]
            return default if v is None else v
        out[dt.hour] = {"t": g("temperature_2m"), "app": g("apparent_temperature"), "rh": g("relative_humidity_2m", 70),
                        "dew": g("dew_point_2m"), "pop": g("precipitation_probability"), "precip": g("precipitation"),
                        "snow": g("snowfall"), "code": int(g("weather_code")), "cloud": g("cloud_cover"),
                        "vis": g("visibility", 20000), "wind": g("wind_speed_10m"), "gust": g("wind_gusts_10m")}
    if len(out) < 20:
        raise RuntimeError(f"У прогнозі на {target} лише {len(out)} годин — дані неповні")
    return out


# ── Допоміжне ──────────────────────────────────────────────────────────────
def pick(pool: list, seed: int, k: int = 0):
    return pool[(seed * 7 + k * 5) % len(pool)]


def rng(H: dict, a: int, b: int) -> list[dict]:
    return [H[h] for h in range(a, b) if h in H]


def avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def temp(x: float) -> str:
    v = round(x)
    return "0°" if v == 0 else f"{'+' if v > 0 else '−'}{abs(v)}°"


def hh(h: int) -> str:
    return f"{h % 24:02d}:00"


ICON_BY_CODE = {0: "clear", 1: "partly", 2: "partly", 3: "cloudy", 45: "fog", 48: "fog",
                51: "drizzle", 53: "drizzle", 55: "drizzle", 56: "drizzle", 57: "drizzle",
                61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain", 80: "rain", 81: "rain", 82: "rain",
                71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow", 86: "snow",
                95: "thunder", 96: "thunder", 99: "thunder"}
SEVERITY = ["clear", "partly", "cloudy", "fog", "drizzle", "rain", "snow", "thunder"]


def block_icon(hours: list[dict]) -> str:
    icons = [ICON_BY_CODE.get(h["code"], "cloudy") for h in hours]
    return max(icons, key=SEVERITY.index) if icons else "cloudy"


# ── Практичні поради ───────────────────────────────────────────────────────
def advice_hat(H, phr, seed, month) -> dict:
    a_min = min(h["app"] for h in rng(H, 6, 23))
    a_max = max(h["app"] for h in rng(H, 6, 23))
    if a_min >= 10:
        tier, lvl, short = "none", 0, "не потрібна"
    elif a_min >= 4:
        tier, lvl, short = "optional", 0, "за бажанням"
    elif a_min >= 0:
        tier, lvl, short = "advised", 1, "краще взяти"
    elif a_min >= -8:
        tier, lvl, short = "needed", 1, "потрібна"
    else:
        tier, lvl, short = "must", 2, "обов’язково"
    text = pick(phr["hat"][tier], seed, 1)
    if a_max >= 28:
        text += " А от легкий головний убір від сонця — не завадить."
    return {"key": "hat", "title": "Шапка?", "answer": short, "level": lvl, "text": text, "emoji": "🧢",
            "hint": f"найхолодніше відчуватиметься {temp(a_min)}"}


def advice_umbrella(H, phr, seed) -> dict:
    day = rng(H, 7, 23)
    pmax = max(h["pop"] for h in day)
    psum = sum(h["precip"] for h in day)
    ssum = sum(h["snow"] for h in day)
    tmean = avg([h["t"] for h in day])
    if ssum >= 0.2 and tmean < 1.5 and pmax >= 30:
        tier, lvl, short = "snow", 1, "краще капюшон"
    elif pmax < 25 and psum < 0.3:
        tier, lvl, short = "none", 0, "не потрібна"
    elif pmax < 50 and psum < 1:
        tier, lvl, short = "maybe", 0, "про всяк випадок"
    elif pmax < 75 and psum < 5:
        tier, lvl, short = "yes", 1, "візьміть"
    else:
        tier, lvl, short = "must", 2 if psum >= 15 else 1, "обов’язково"
    hint = f"опади до {psum:.1f} мм".replace(".", ",") if psum >= 0.3 else ""
    return {"key": "umbrella", "title": "Парасолька?", "answer": short, "level": lvl, "emoji": "☂️",
            "text": pick(phr["umbrella"][tier], seed, 2), "hint": hint, "pmax": pmax, "psum": psum, "ssum": ssum}


def advice_slippery(H, phr, seed, month, psum, ssum) -> dict:
    ice = any(h["precip"] > 0.1 and -3 <= h["t"] <= 1 for h in rng(H, 0, 24)) or \
        any(h["code"] in (56, 57, 66, 67) for h in rng(H, 0, 24))
    frost_hours = [h for hr, h in H.items() if (hr <= 10 or hr >= 18) and h["t"] <= 0.5 and
                   (h["rh"] >= 85 or (h["t"] - h["dew"]) <= 1.5)]
    wet_leaves = month in (9, 10, 11) and (psum >= 0.5 or max((h["rh"] for h in rng(H, 6, 10)), default=0) >= 98) \
        and min(h["t"] for h in rng(H, 6, 23)) > 1
    if ice:
        tier, lvl, short = "ice", 2, "можлива ожеледь"
    elif ssum >= 0.5:
        tier, lvl, short = "snow", 1, "сніг на доріжках"
    elif frost_hours:
        tier, lvl, short = "frost", 1, "можливий іній"
    elif wet_leaves:
        tier, lvl, short = "leaves", 1, "мокре листя"
    else:
        tier, lvl, short = "none", 0, "ні"
    return {"key": "slippery", "title": "Слизько?", "answer": short, "level": lvl, "emoji": "🧊",
            "text": pick(phr["slippery"][tier], seed, 3), "hint": ""}


def fog_window(H) -> Optional[tuple[int, int, float]]:
    flagged = []
    for hr in range(5, 22):                      # практичний час: від 05:00 до 22:00
        h = H.get(hr)
        if not h:
            continue
        night_morning = hr <= 9
        misty = h["rh"] >= 96 and h["wind"] < 2.5 and (h["t"] - h["dew"]) <= 1.0 and night_morning
        if h["vis"] < 1000 or misty:
            flagged.append(hr)
    if not flagged:
        return None
    runs, cur = [], [flagged[0]]
    for x in flagged[1:]:
        if x == cur[-1] + 1:
            cur.append(x)
        else:
            runs.append(cur)
            cur = [x]
    runs.append(cur)
    best = max(runs, key=len)
    return best[0], best[-1] + 1, min(H[x]["vis"] for x in best)


def advice_fog(H, phr, seed) -> dict:
    fw = fog_window(H)
    if not fw:
        return {"key": "fog", "title": "Туман?", "answer": "ні", "level": 0, "emoji": "🌫️",
                "text": pick(phr["fog"]["none"], seed, 4), "hint": "", "window": None}
    a, b, vmin = fw
    tier, lvl = ("dense", 2) if vmin < 400 else ("maybe", 1)
    text = pick(phr["fog"][tier], seed, 4).format(a=hh(a), b=hh(b))
    return {"key": "fog", "title": "Туман?", "answer": f"між {hh(a)} і {hh(b)}",
            "level": lvl, "emoji": "🌫️", "text": text, "hint": "густий" if tier == "dense" else "", "window": (a, b)}


def advice_wind(H, phr, seed) -> dict:
    gmax = max(h["gust"] for h in rng(H, 6, 23))
    g = f"{gmax:.0f}"
    if gmax < 8:
        tier, lvl, short = "calm", 0, "слабкий"
    elif gmax < 12:
        tier, lvl, short = "moderate", 0, "помірний"
    elif gmax < 17:
        tier, lvl, short = "gusty", 1, "поривчастий"
    else:
        tier, lvl, short = "strong", 2, "сильний"
    return {"key": "wind", "title": "Вітер?", "answer": short, "level": lvl, "emoji": "💨",
            "text": pick(phr["wind"][tier], seed, 5).format(g=g), "hint": f"пориви до {g} м/с" if gmax >= 5 else "",
            "gmax": gmax}


# ── Прогулянка ─────────────────────────────────────────────────────────────
def hour_score(h: dict) -> float:
    pen = 0.0
    a = h["app"]
    if a < 14:
        pen += (14 - a) * 0.045
    if a > 27:
        pen += (a - 27) * 0.06
    pen += h["pop"] / 100 * 0.5 + min(h["precip"], 3) / 3 * 0.35
    pen += max(0, h["gust"] - 6) * 0.04
    pen += 0.6 if h["vis"] < 1000 else 0.3 if h["vis"] < 2000 else 0.0
    return max(0.0, 1.0 - pen)


def best_walk(H) -> dict:
    scores = {hr: hour_score(H[hr]) for hr in range(6, 24) if hr in H}
    lo, hi = min(scores.values()), max(scores.values())
    norm = [(hr, (s - lo) / (hi - lo) if hi - lo > 0.08 else 0.5) for hr, s in sorted(scores.items())]
    cands = [(sum(scores[x] for x in range(s, s + 3)), s) for s in range(8, 19) if all(x in scores for x in range(s, s + 3))]
    total, s = max(cands)
    win = [H[x] for x in range(s, s + 3)]
    parts = []
    if max(w["pop"] for w in win) < 25 and sum(w["precip"] for w in win) < 0.2:
        parts.append("сухо")
    elif max(w["pop"] for w in win) >= 60:
        parts.append("найменше опадів за день")
    if max(w["gust"] for w in win) < 7:
        parts.append("без сильного вітру")
    day_best = max(range(8, 21), key=lambda x: H[x]["app"] if x in H else -99)
    if s <= day_best <= s + 2 or avg([w["app"] for w in win]) >= max(H[x]["app"] for x in range(8, 21)) - 1.0:
        parts.insert(0, "найтепліше")
    if not parts:
        parts = ["найспокійніший відрізок дня"]
    reason = (", ".join(parts[:-1]) + " й " + parts[-1]) if len(parts) > 1 else parts[0]
    return {"window": f"{hh(s)}–{hh(s + 3)}", "reason": reason, "hours": norm, "start": s, "end": s + 3,
            "avg_score": total / 3}


# ── Заголовок і прикмета ───────────────────────────────────────────────────
def headline(H, phr, seed) -> tuple[str, dict]:
    tmin, tmax = min(h["t"] for h in H.values()), max(h["t"] for h in H.values())
    t7 = H[7]["t"] if 7 in H else tmin
    if tmax <= 5:
        prof = "frosty" if tmin <= -2 else "cold"
    elif tmax <= 12:
        prof = "cool_rising" if tmax - t7 >= 4 else "cool"
    elif tmax <= 18:
        prof = "mild"
    elif tmax <= 25:
        prof = "warm"
    else:
        prof = "hot"
    base = pick(phr["headline"][prof], seed)
    day = rng(H, 7, 23)
    pmax = max(h["pop"] for h in day)
    psum = sum(h["precip"] for h in day)
    ssum = sum(h["snow"] for h in day)
    codes = {h["code"] for h in day}
    if codes & {95, 96, 99}:
        ov = "thunder"
    elif ssum >= 0.3 and psum - ssum * 0.1 >= 0.5 and any(h["t"] > 0.5 and h["precip"] > 0.1 for h in day):
        ov = "sleet"
    elif ssum >= 0.3:
        ov = "snow"
    elif psum >= 10:
        ov = "rain_heavy"
    elif psum >= 2 or pmax >= 70:
        ov = "rain"
    elif pmax >= 40 or psum >= 0.5:
        ov = "rain_light"
    else:
        ov = None
    extras = []
    if ov:
        extras.append(pick(phr["overlay"][ov], seed, 6))
    gmax = max(h["gust"] for h in day)
    if gmax >= 12:
        extras.append(pick(phr["overlay"]["wind_strong" if gmax >= 17 else "wind_mod"], seed, 7))
    if fog_window(H) and len(extras) < 2:
        extras.append(pick(phr["overlay"]["fog"], seed, 8))
    tags = set()
    if ov in ("rain", "rain_heavy", "rain_light", "thunder") and psum >= 1:
        tags.add("rain")
    if ov in ("snow", "sleet"):
        tags.add("snow")
    if tmin <= 0.5:
        tags.add("frost")
    if gmax >= 12:
        tags.add("wind")
    if fog_window(H):
        tags.add("fog")
    if pmax < 20 and avg([h["cloud"] for h in day]) < 40:
        tags.add("clear")
    if tmax >= 20:
        tags.add("warm")
    if tmax - tmin >= 9:
        tags.add("change")
    return " ".join([base] + extras[:2]), {"profile": prof, "tags": tags, "tmin": tmin, "tmax": tmax}


def pick_sign(db: dict, target: date, tags: set) -> dict:
    items = [s for s in db["signs"] if not s.get("months") or target.month in s["months"]] or db["signs"]
    matched = [s for s in items if set(s.get("cond", [])) & tags]
    pool = matched if matched and target.toordinal() % 3 != 0 else items
    n = len(pool)
    stride = next(p for p in (7, 11, 13, 17, 19, 23, 29) if n % p)
    return pool[(target.toordinal() * stride) % n]


# ── Збірка ─────────────────────────────────────────────────────────────────
def build(H: dict, db: dict, target: date) -> dict:
    phr, seed = db["phrases"], target.toordinal()
    head, meta = headline(H, phr, seed)
    um = advice_umbrella(H, phr, seed)
    items = [advice_hat(H, phr, seed, target.month), um,
             advice_slippery(H, phr, seed, target.month, um["psum"], um["ssum"]),
             advice_fog(H, phr, seed), advice_wind(H, phr, seed)]
    walk = best_walk(H)
    sign = pick_sign(db, target, meta["tags"])
    tg_ = meta["tags"]
    contradicted = {"rain": not (tg_ & {"rain", "snow"}), "clear": bool(tg_ & {"rain", "snow"}),
                    "frost": "frost" not in tg_, "wind": "wind" not in tg_}
    rel = [c for c in sign.get("cond", []) if c in contradicted]
    conflict = bool(rel) and all(contradicted[c] for c in rel)

    blocks = [("Ранок", "06–11", 6, 11), ("День", "11–18", 11, 18), ("Вечір", "18–23", 18, 23)]
    periods = []
    for label, hrs, a, b in blocks:
        hs = rng(H, a, b)
        periods.append({"label": label, "hours": hrs, "temp": avg([h["t"] for h in hs]),
                        "feels": avg([h["app"] for h in hs]), "icon": block_icon(hs),
                        "pop": round(max(h["pop"] for h in hs) / 5) * 5,
                        "night": label == "Вечір" and target.month in (9, 10, 11, 12, 1, 2, 3)})
    return {
        "date_long": f"{target.day} {MONTHS[target.month - 1]} {target.year}",
        "weekday": WEEKDAYS[target.weekday()], "headline": head, "tmin": meta["tmin"], "tmax": meta["tmax"],
        "periods": periods, "practical": items, "walk": walk,
        "folk": {**sign, "verdict_text": db["verdicts"][sign["verdict"]], "conflict": conflict},
        "tags": sorted(meta["tags"]),
    }


def build_text(data: dict, target: date) -> str:
    e = html.escape
    P = data["periods"]
    L = ["🌙 <b>Погода, яка має значення</b>",
         f"📅 Завтра, {data['weekday']}, {target.day} {MONTHS[target.month - 1]} · Суми", "",
         f"<b>Коротко:</b> {e(data['headline'])}", "",
         f"🌡️ Ранок {temp(P[0]['temp'])} · День {temp(P[1]['temp'])} · Вечір {temp(P[2]['temp'])}",
         f"<i>Протягом доби від {temp(data['tmin'])} до {temp(data['tmax'])}; "
         f"відчувається вдень як {temp(P[1]['feels'])}</i>", "", "<b>Практично:</b>"]
    for it in data["practical"]:
        L.append(f"{it['emoji']} <b>{it['title']}</b> {STATUS[it['level']]} {e(it['text'])}")
    w = data["walk"]
    L.append(f"🚶 <b>Найкраще вийти:</b> {w['window']} — {e(w['reason'])}")
    f = data["folk"]
    L += ["", "🪶 <b>Народний синоптик</b>", f"«{e(f['sign'])}» {e(f['joke'])}".strip(),
          f"🔬 <b>Що кажуть метеорологи:</b> {e(f['science'])}", f"<b>Вердикт науки:</b> {f['verdict_text']}",
          "<i>Прикмета — це традиція, а не прогноз: прогноз — у блоці «Практично».</i>"]
    if f.get("conflict"):
        L.append("<i>Цього разу прогноз каже інакше, ніж прикмета: довіряйте прогнозу, а прикметі подякуйте за колорит. 😉</i>")
    L += ["",
          "ℹ️ <i>Дані: прогнозна модель Open-Meteo для Сум. Це не офіційне попередження — "
          "за ним звертайтеся до Укргідрометцентру.</i>", "", HASHTAGS]
    return "\n".join(L)


# ── Telegram ───────────────────────────────────────────────────────────────
def tg(method: str, token: str, **kw) -> dict:
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def publish(token: str, chat_id: str, card: str, caption: str, text: str) -> None:
    with open(card, "rb") as f:
        tg("sendPhoto", token, data={"chat_id": chat_id, "caption": caption}, files={"photo": f})
    tg("sendMessage", token, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"})


# ── Перевірка бази ─────────────────────────────────────────────────────────
def check(db: dict, today: date) -> None:
    from collections import Counter
    signs = db["signs"]
    print(f"Прикмет у базі: {len(signs)} · вердикти: {dict(Counter(s['verdict'] for s in signs))}\n")
    print("Скільки прикмет доречні в кожному місяці (≈ стільки днів до першого повтору):")
    for m in range(1, 13):
        n = len([s for s in signs if not s.get("months") or m in s["months"]])
        print(f"  {MONTHS[m - 1]:<10} {n:>3}{'   ⚠️ мало — поповніть' if n < 40 else ''}")
        if n < 40:
            print("::warning title=Мало прикмет::У місяці", MONTHS[m - 1], "лише", n, "доречних прикмет")
    print("\nНаступні 10 днів (без прив’язки до прогнозу):")
    for i in range(10):
        d = today + timedelta(days=i)
        print(f"  {d:%d.%m}: {pick_sign(db, d, set())['sign']}")


# ── main ───────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати в Telegram")
    ap.add_argument("--force", action="store_true", help="ігнорувати перевірку години")
    ap.add_argument("--check", action="store_true", help="показати запас прикмет")
    ap.add_argument("--target", help="для якої дати робити прогноз (YYYY-MM-DD); за замовчуванням — завтра")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    now = datetime.now(TZ)
    db = load_db()
    if args.check:
        check(db, now.date())
        return 0
    force = args.force or args.dry_run or os.getenv("FORCE_RUN") == "1"
    if not force and now.hour != POST_HOUR:
        log.info("У Києві зараз %s — не час публікації, вихід.", now.strftime("%H:%M"))
        return 0

    target = date.fromisoformat(args.target) if args.target else now.date() + timedelta(days=1)
    H = hours_for(fetch_forecast(), target)
    data = build(H, db, target)
    render_card({**data, "folk": {"sign": data["folk"]["sign"], "verdict": data["folk"]["verdict"]}}, CARD_PATH)
    text = build_text(data, target)
    caption = f"🌙 Погода, яка має значення · завтра, {data['weekday']}, {target.day} {MONTHS[target.month - 1]}"

    if args.dry_run:
        print(re.sub(r"</?(b|i)>", "", text))
        log.info("Dry-run: символів %d, картку збережено в %s", len(text), CARD_PATH)
        return 0
    token, chat_id = os.getenv("BOT_TOKEN"), os.getenv("CHAT_ID")
    if not token or not chat_id:
        log.error("Не задано BOT_TOKEN / CHAT_ID")
        return 1
    publish(token, chat_id, CARD_PATH, caption, text)
    log.info("Опубліковано.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
