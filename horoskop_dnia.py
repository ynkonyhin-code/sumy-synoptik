#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Щоденний «Гороскоп на сьогодні» (змішаний формат) для Telegram-каналу
«Сумський синоптик» — https://t.me/sumskoy_sinoptik

Астрономія рахується реально (бібліотека ephem): знак Місяця й Сонця, фаза, зворотний
рух Меркурія, рівнодення/сонцестояння. Для кожного знаку береться аспект Місяця
(сполучення, секстиль, квадрат, трин, опозиція) і складається жартівливий текст
із файлу horoskop_dnia_texts.json (його можна вільно редагувати й доповнювати).
Народна частина — прикмети про погоду з науковим коментарем, місячні традиції та
народні звичаї навколо рівнодень і сонцестоянь.

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  FORCE_RUN=1

Запуск:
    python horoskop_dnia.py --dry-run
    python horoskop_dnia.py --dry-run --date 2026-12-21
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import math
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import ephem
import requests

from horoskop_dnia_card import render_card

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
UTC = timezone.utc
LAT, LON, ELEV = 50.9077, 34.7981, 170
POST_HOUR = 7                                   # публікація о 07:xx за Києвом
TEXTS_FILE = Path(__file__).with_name("horoskop_dnia_texts.json")
CARD_PATH = "horoskop_dnia_card.png"

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
          "вересня", "жовтня", "листопада", "грудня"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя"]
SCORE = {"conjunction": 4, "sextile": 4, "square": 3, "trine": 5, "opposition": 3, "quiet": 3}
HASHTAGS = ("#СумськийСиноптик #Гороскоп #ГороскопНаСьогодні #ЗнакиЗодіаку "
            "#НародніПрикмети #Місяць #Астрономія")
MAX_MSG = 3900                                  # ліміт Telegram — 4096
log = logging.getLogger("horoskop")


# ── Допоміжне ──────────────────────────────────────────────────────────────
def load_texts() -> dict:
    return json.loads(TEXTS_FILE.read_text(encoding="utf-8"))


def E(dt: datetime) -> ephem.Date:
    return ephem.Date(dt.astimezone(UTC).replace(tzinfo=None))


def L(d) -> datetime:
    return ephem.Date(d).datetime().replace(tzinfo=UTC).astimezone(TZ)


def observer(when: datetime) -> ephem.Observer:
    o = ephem.Observer()
    o.lat, o.lon, o.elevation = str(LAT), str(LON), ELEV
    o.pressure, o.horizon = 0, "-0:34"
    o.date = E(when)
    return o


def ecl_lon(cls, when: datetime) -> float:
    """Еклиптична довгота тіла в системі «на дату» (тропічний зодіак), градуси."""
    o = observer(when)
    b = cls()
    b.compute(o)
    eq = ephem.Equatorial(b.g_ra, b.g_dec, epoch=o.date)
    return math.degrees(ephem.Ecliptic(eq, epoch=o.date).lon) % 360


def sign_idx(cls, when: datetime) -> int:
    return int(ecl_lon(cls, when) // 30) % 12


def pick(items: list, seed: int, k: int = 0, salt: int = 0):
    return items[(seed * 7 + k * 13 + salt) % len(items)]


def fmt_dt(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]}"


# ── Астрономія дня ─────────────────────────────────────────────────────────
def moon_name(psi: float, illum: float) -> str:
    if illum < 2:
        return "Новий місяць"
    if illum > 98:
        return "Повний місяць"
    for lim, name in ((85, "Зростаючий серп"), (95, "Перша чверть"), (175, "Зростаючий Місяць"),
                      (185, "Повний місяць"), (265, "Спадаючий Місяць"), (275, "Остання чверть")):
        if psi < lim:
            return name
    return "Спадаючий серп"


def phase_kind(psi: float, illum: float) -> str:
    if illum < 8:
        return "new"
    if illum > 97:
        return "full"
    return "waxing" if psi < 180 else "waning"


def moon_state(noon: datetime) -> dict:
    o = observer(noon)
    m = ephem.Moon()
    m.compute(o)
    psi = math.degrees(m.elong) % 360
    return {"psi": psi, "illum": round(m.phase), "name": moon_name(psi, m.phase),
            "kind": phase_kind(psi, m.phase)}


def moon_sign_change(day: date) -> tuple[int, datetime] | None:
    """Якщо Місяць змінює знак протягом доби — (новий індекс знаку, час)."""
    start = datetime(day.year, day.month, day.day, tzinfo=TZ)
    prev = sign_idx(ephem.Moon, start)
    for h in range(1, 25):
        t = start + timedelta(hours=h)
        cur = sign_idx(ephem.Moon, t)
        if cur != prev:
            for mnt in range(60):                         # уточнюємо до хвилини
                tt = start + timedelta(hours=h - 1, minutes=mnt + 1)
                if sign_idx(ephem.Moon, tt) == cur:
                    return cur, tt
            return cur, t
    return None


def mercury_retro(noon: datetime) -> bool:
    a, b = ecl_lon(ephem.Mercury, noon), ecl_lon(ephem.Mercury, noon + timedelta(days=1))
    return (b - a + 180) % 360 - 180 < 0


def aspect_of(sign_i: int, moon_i: int) -> str:
    diff = (moon_i - sign_i) % 12
    return {0: "conjunction", 2: "sextile", 10: "sextile", 3: "square", 9: "square",
            4: "trine", 8: "trine", 6: "opposition"}.get(diff, "quiet")


def season_event(day: date) -> str | None:
    """Рівнодення/сонцестояння в межах ±1 доби від дня."""
    mid = datetime(day.year, day.month, day.day, 12, tzinfo=TZ)
    start = E(mid)
    names = {3: "spring", 9: "autumn", 6: "summer", 12: "winter"}
    for fn in (ephem.previous_equinox, ephem.next_equinox, ephem.previous_solstice, ephem.next_solstice):
        t = L(fn(start))
        if abs((t.date() - day).days) <= 1 and t.month in names:
            return names[t.month]
    return None


# ── Збірка даних ───────────────────────────────────────────────────────────
def collect(day: date) -> dict:
    T = load_texts()
    signs = T["signs"]
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=TZ)
    seed = day.toordinal()

    moon_i, sun_i = sign_idx(ephem.Moon, noon), sign_idx(ephem.Sun, noon)
    ms = moon_state(noon)
    retro = mercury_retro(noon)
    change = moon_sign_change(day)

    moon_phrase = f"Місяць {signs[moon_i]['moon_loc']}"
    out_signs = []
    used: dict[str, int] = {}                     # скільки знаків уже мають цей аспект
    for i, s in enumerate(signs):
        asp = aspect_of(i, moon_i)
        c = used.get(asp, 0)
        used[asp] = c + 1
        # знаки з однаковим аспектом отримують різні формулювання
        aspect_line = pick(T["aspects"][asp], seed, 0, c).format(moon=moon_phrase)
        quip = pick(T["sign_quips"][s["name"]], seed, i, 3)
        out_signs.append({
            "symbol": s["symbol"], "name": s["name"], "dates": s["dates"], "aspect": asp,
            "label": T["aspect_labels"][asp], "score": SCORE[asp], "is_sun": i == sun_i,
            "text": f"{aspect_line} {quip}", "element": s["element"],
        })

    # Народна частина
    folk_lines: list[str] = []
    ev = season_event(day)
    if ev:
        folk_lines.append(("🌾", T["equinox_folk"][ev]))
    for fd in T.get("folk_dates", []):
        if fd.get("month") == day.month and fd.get("day") == day.day:
            folk_lines.append(("🎋", fd["text"]))
    folk_lines.append(("🌙", pick(T["moon_lore"][ms["kind"]], seed)))
    candidates = [f for f in T["folk_signs"] if not f["months"] or day.month in f["months"]]
    fs = pick(candidates, seed, 5)

    theme_full = signs[moon_i]["moon_theme"]            # «Місяць у Тельці: день затишку…»
    moon_theme = theme_full.split(": ", 1)[-1]
    moon_theme = moon_theme[0].upper() + moon_theme[1:]
    change_note = None
    if change:
        ci, ct = change
        change_note = f"о {ct.strftime('%H:%M')} Місяць переходить у знак «{signs[ci]['name']}»"

    tip = pick(T["tips"][signs[moon_i]["element"]], seed, 0, 1)
    return {
        "date_long": f"{day.day} {MONTHS[day.month - 1]} {day.year}",
        "weekday": WEEKDAYS[day.weekday()],
        "sun_sign": signs[sun_i]["name"],
        "retro": retro,
        "retro_text": pick(T["mercury_retro"], seed) if retro else None,
        "moon": {"sign_loc": signs[moon_i]["moon_loc"], "name": ms["name"], "illum": ms["illum"],
                 "elong": ms["psi"], "theme": moon_theme, "change": change_note,
                 "phase_note": T["phase_notes"][ms["kind"]]},
        "signs": out_signs,
        "folk_lines": folk_lines,
        "folk_sign": fs,
        "folk": f"{fs['sign']} {fs['science']}",
        "tip": tip,
    }


# ── Текст посту ────────────────────────────────────────────────────────────
def build_text(data: dict) -> str:
    e = html.escape
    m = data["moon"]
    L_ = [
        "🔮 <b>Гороскоп на сьогодні</b> <i>(розважальний формат)</i>",
        f"📅 {data['weekday'].capitalize()}, {data['date_long']}",
        "",
        f"🌙 <b>Місяць {e(m['sign_loc'])}</b> · {m['name'].lower()}, освітлено {m['illum']} %",
        f"{e(m['theme'])}",
    ]
    if m["change"]:
        L_.append(f"<i>Цікаво: {e(m['change'])}.</i>")
    L_.append(f"<i>{e(m['phase_note'])}</i>")
    L_.append(f"☀️ Сонце зараз у знаку «{data['sun_sign']}».")
    if data["retro"]:
        L_.append(f"↺ {e(data['retro_text'])}")
    L_ += ["", "<b>Що кажуть зорі (жартома)</b>", ""]
    for s in data["signs"]:
        mark = " ☀️" if s["is_sun"] else ""
        L_.append(f"{s['symbol']} <b>{s['name']}</b>{mark} <i>({s['dates']})</i> — {e(s['label'])}")
        L_.append(e(s["text"]))
        L_.append("")
    L_.append(f"💡 <b>Порада дня:</b> {e(data['tip'])}")
    L_.append("")
    L_.append("🌾 <b>Народна мудрість</b>")
    for icon, txt in data["folk_lines"]:
        L_.append(f"{icon} {e(txt)}")
    fs = data["folk_sign"]
    L_.append(f"🌦 <b>Прикмета:</b> {e(fs['sign'])}")
    L_.append(f"🔬 <i>Що кажуть метеорологи: {e(fs['science'])}</i>")
    L_ += ["", "<i>Гороскоп — жарт для настрою, а не прогноз долі. Знаки зодіаку — це не сузір’я: "
               "Місяць і Сонце розраховано за реальними астрономічними даними.</i>",
           "", HASHTAGS]
    return "\n".join(L_)


def split_text(text: str, limit: int = MAX_MSG) -> list[str]:
    """Ділить пост за порожніми рядками на повідомлення ≤ limit символів."""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > limit:
            parts.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts


# ── Telegram ───────────────────────────────────────────────────────────────
def tg(method: str, token: str, **kw) -> dict:
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def publish(token: str, chat_id: str, card: str, text: str) -> None:
    with open(card, "rb") as f:
        tg("sendPhoto", token, data={"chat_id": chat_id}, files={"photo": f})
    for part in split_text(text):
        tg("sendMessage", token, data={"chat_id": chat_id, "text": part, "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"})


# ── main ───────────────────────────────────────────────────────────────────
def card_data(data: dict) -> dict:
    return {**data, "moon": {**data["moon"]}, "folk": data["folk"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="не надсилати в Telegram")
    ap.add_argument("--force", action="store_true", help="ігнорувати перевірку години")
    ap.add_argument("--date", help="дата для тесту, YYYY-MM-DD")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    now = datetime.now(TZ)
    day = date.fromisoformat(args.date) if args.date else now.date()
    force = args.force or args.dry_run or os.getenv("FORCE_RUN") == "1"
    if not force and now.hour != POST_HOUR:
        log.info("У Києві зараз %s — не час публікації, вихід.", now.strftime("%H:%M"))
        return 0

    data = collect(day)
    render_card(card_data(data), CARD_PATH)
    text = build_text(data)

    if args.dry_run:
        print(re.sub(r"</?(b|i)>", "", text))
        log.info("Символів: %d, повідомлень: %d. Картку збережено в %s",
                 len(text), len(split_text(text)), CARD_PATH)
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
