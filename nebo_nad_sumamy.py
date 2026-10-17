#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Щоденний пост «Небо над Сумами» для Telegram-каналу «Сумський синоптик»
https://t.me/sumskoy_sinoptik

Усе рахується астрономічною бібліотекою ephem для координат Сум — без парсингу сайтів:
  • Місяць: фаза, освітленість, вік, схід/захід, найближчі фази;
  • Сонце: схід/захід, тривалість дня і її зміна;
  • планети, видимі неозброєним оком ввечері та завтра вранці (напрямок, висота);
  • Місяць поруч із планетою, протистояння, зворотний рух;
  • метеорні потоки, рівнодення/сонцестояння;
Додатково (м'яко, без збою посту, якщо сервіс недоступний):
  • хмарність увечері (Open-Meteo);
  • прольоти МКС (дані TLE з CelesTrak).

Змінні середовища (GitHub Secrets):  BOT_TOKEN, CHAT_ID
Необов'язкові:  FORCE_RUN=1

Запуск:
    python nebo_nad_sumamy.py --dry-run
    python nebo_nad_sumamy.py --dry-run --date 2026-10-21
"""
from __future__ import annotations

import argparse
import html
import logging
import math
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import ephem
import requests

from nebo_nad_sumamy_card import render_card

# ── Налаштування ───────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
UTC = timezone.utc
LAT, LON, ELEV = 50.9077, 34.7981, 170            # Суми
POST_HOUR = 16                                      # публікація о 16:xx за Києвом
CARD_PATH = "nebo_nad_sumamy_card.png"
MIN_ALT = 8.0                                       # мінімальна висота планети, °

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
          "вересня", "жовтня", "листопада", "грудня"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя"]
COMPASS = ["північ", "північний схід", "схід", "південний схід",
           "південь", "південний захід", "захід", "північний захід"]
CONST_UA = {"Ari": "Овен", "Tau": "Телець", "Gem": "Близнюки", "Cnc": "Рак", "Leo": "Лев",
            "Vir": "Діва", "Lib": "Терези", "Sco": "Скорпіон", "Oph": "Змієносець",
            "Sgr": "Стрілець", "Cap": "Козеріг", "Aqr": "Водолій", "Psc": "Риби",
            "Cet": "Кит", "Ori": "Оріон", "Sex": "Секстант", "Crv": "Ворон"}

# (ephem-клас, назва, колір на картці)
PLANETS = [
    (ephem.Mercury, "Меркурій", (190, 190, 200)),
    (ephem.Venus, "Венера", (240, 225, 170)),
    (ephem.Mars, "Марс", (232, 112, 82)),
    (ephem.Jupiter, "Юпітер", (225, 190, 140)),
    (ephem.Saturn, "Сатурн", (215, 195, 120)),
]

# Метеорні потоки: (назва, (місяць, день піку), ZHR «до»)
SHOWERS = [
    ("Квадрантиди", (1, 4), 80), ("Ліриди", (4, 22), 18), ("Ета-Аквариди", (5, 6), 50),
    ("Південні Дельта-Аквариди", (7, 30), 20), ("Персеїди", (8, 12), 100),
    ("Оріоніди", (10, 22), 20), ("Південні Тауриди", (11, 5), 5), ("Леоніди", (11, 17), 15),
    ("Гемініди", (12, 14), 120), ("Урсиди", (12, 22), 10),
]

HASHTAGS = ("#СумськийСиноптик #НебоНадСумами #Астрономія #Місяць #Космос "
            "#Планети #ЗоряненебоСуми #Суми")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sumskoy-sinoptik-bot/1.0)"}
log = logging.getLogger("nebo")


# ── Час і спостерігач ──────────────────────────────────────────────────────
def E(dt: datetime) -> ephem.Date:
    return ephem.Date(dt.astimezone(UTC).replace(tzinfo=None))


def L(d) -> datetime:
    return ephem.Date(d).datetime().replace(tzinfo=UTC).astimezone(TZ)


def hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def observer(when: Optional[datetime] = None) -> ephem.Observer:
    o = ephem.Observer()
    o.lat, o.lon, o.elevation = str(LAT), str(LON), ELEV
    o.pressure, o.horizon = 0, "-0:34"              # як у USNO для сходу/заходу
    if when:
        o.date = E(when)
    return o


def local_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=TZ)


def fnum(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}".replace(".", ",").replace("-", "−")


def fmt_date(dt: datetime) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]}"


def minutes_text(m: int) -> str:
    h, mm = divmod(abs(m), 60)
    return f"{h} г {mm:02d} хв"


# ── Сонце ──────────────────────────────────────────────────────────────────
def sun_times(day: date) -> tuple[datetime, datetime]:
    o = observer(local_midnight(day))
    sun = ephem.Sun()
    return L(o.next_rising(sun)), L(o.next_setting(sun))


def sun_info(day: date) -> dict:
    rise, sset = sun_times(day)
    p_rise, p_set = sun_times(day - timedelta(days=1))
    length = int((sset - rise).total_seconds() // 60)
    prev = int((p_set - p_rise).total_seconds() // 60)
    d = length - prev
    delta = f"{'+' if d > 0 else '−'}{abs(d)} хв до вчора" if d else "як учора"
    return {"rise": hm(rise), "set": hm(sset), "length": minutes_text(length), "delta": delta,
            "_rise": rise, "_set": sset, "_len": length, "_d": d}


# ── Місяць ─────────────────────────────────────────────────────────────────
def moon_name(psi: float, illum: float) -> str:
    if illum < 2:
        return "Новий місяць"
    if illum > 98:
        return "Повний місяць"
    if psi < 85:
        return "Зростаючий серп"
    if psi < 95:
        return "Перша чверть"
    if psi < 175:
        return "Зростаючий Місяць"
    if psi < 185:
        return "Повний місяць"
    if psi < 265:
        return "Спадаючий Місяць"
    if psi < 275:
        return "Остання чверть"
    return "Спадаючий серп"


def moon_events(day: date, kind: str) -> str:
    """Схід/захід Місяця у межах календарної доби (може не бути)."""
    o = observer(local_midnight(day))
    moon = ephem.Moon()
    try:
        t = L(o.next_rising(moon) if kind == "rise" else o.next_setting(moon))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        return "—"
    return hm(t) if t.date() == day else "—"


def moon_info(day: date, t_ref: datetime) -> dict:
    o = observer(t_ref)
    moon = ephem.Moon()
    moon.compute(o)
    psi = math.degrees(moon.elong) % 360
    illum = moon.phase
    age = o.date - ephem.previous_new_moon(o.date)
    return {"name": moon_name(psi, illum), "illum": round(illum), "age": fnum(age),
            "elong": psi, "rise": moon_events(day, "rise"), "set": moon_events(day, "set")}


def next_phases(t_ref: datetime, n: int = 2) -> list[str]:
    start = E(t_ref)
    items = [("Новий місяць", ephem.next_new_moon(start)),
             ("Перша чверть", ephem.next_first_quarter_moon(start)),
             ("Повня", ephem.next_full_moon(start)),
             ("Остання чверть", ephem.next_last_quarter_moon(start))]
    items.sort(key=lambda x: x[1])
    return [f"{name} · {fmt_date(L(d))} о {hm(L(d))}" for name, d in items[:n]]


def moon_illum_at(dt: datetime) -> int:
    m = ephem.Moon()
    m.compute(observer(dt))
    return round(m.phase)


# ── Планети ────────────────────────────────────────────────────────────────
def compass(az: float) -> str:
    return COMPASS[int(((az % 360) + 22.5) // 45) % 8]


def planets_at(t: datetime) -> list[dict]:
    o = observer(t)
    out = []
    for cls, name, color in PLANETS:
        p = cls()
        p.compute(o)
        alt, az = math.degrees(p.alt), math.degrees(p.az)
        if alt < MIN_ALT:
            continue
        abbr = ephem.constellation(p)[0]
        out.append({"name": name, "mag": ("+" if p.mag >= 0 else "") + fnum(p.mag),
                    "_mag": p.mag, "dir": compass(az), "alt": round(alt),
                    "fists": max(1, round(alt / 10)), "const": CONST_UA.get(abbr, ephem.constellation(p)[1]),
                    "color": list(color), "_body": p})
    out.sort(key=lambda x: x["_mag"])
    return out


def planet_events(t_eve: datetime, visible: list[dict]) -> list[dict]:
    extras = []
    o = observer(t_eve)
    moon = ephem.Moon()
    moon.compute(o)
    # Місяць поруч із планетою
    for p in visible:
        b = p["_body"]
        b.compute(o)
        sep = math.degrees(float(ephem.separation((moon.ra, moon.dec), (b.ra, b.dec))))
        if sep < 5:
            extras.append({"kind": "event",
                           "text": f"Місяць поруч із планетою {p['name']}: відстань ≈ {round(sep)}° "
                                   f"({p['dir']}). Гарний орієнтир для пошуку!"})
    # Протистояння і зворотний рух
    retro = []
    for cls, name, _ in PLANETS:
        p = cls()
        p.compute(o)
        if cls in (ephem.Mars, ephem.Jupiter, ephem.Saturn) and abs(math.degrees(p.elong)) >= 177:
            extras.append({"kind": "event",
                           "text": f"{name} у протистоянні: планета на небі всю ніч, найближча до Землі "
                                   f"й найяскравіша за рік."})
        o2 = observer(t_eve + timedelta(days=1))
        p2 = cls()
        p2.compute(o2)
        lon1, lon2 = ephem.Ecliptic(p).lon, ephem.Ecliptic(p2).lon
        if (lon2 - lon1 + math.pi) % (2 * math.pi) - math.pi < 0:
            retro.append(name)
    if retro:
        extras.append({"kind": "retro",
                       "text": "Зворотний рух: " + ", ".join(retro) + " — видимий ефект орбітального руху."})
    return extras


# ── Події календаря ────────────────────────────────────────────────────────
def upcoming_events(day: date) -> list[dict]:
    extras = []
    for name, (mo, dd), zhr in SHOWERS:
        peak = date(day.year, mo, dd)
        if peak < day:
            peak = date(day.year + 1, mo, dd)
        delta = (peak - day).days
        if 0 <= delta <= 10:
            ill = moon_illum_at(local_midnight(peak) + timedelta(hours=2))
            cond = ("небо темне, умови добрі" if ill <= 30 else
                    "трохи заважає" if ill <= 60 else "його світло заважає")
            when = "сьогодні" if delta == 0 else f"через {delta} дн." if delta > 1 else "завтра"
            extras.append({"kind": "shower",
                           "text": f"{name}: пік {when} (≈ {peak.day} {MONTHS[peak.month - 1]}), до {zhr} метеорів/год. "
                                   f"Місяць {ill} % — {cond}."})
            break
    start = E(local_midnight(day))
    for fn, label in ((ephem.next_equinox, "рівнодення"), (ephem.next_solstice, "сонцестояння")):
        t = L(fn(start))
        if 0 <= (t.date() - day).days <= 14:
            kind = {3: "весняне", 9: "осіннє", 6: "літнє", 12: "зимове"}.get(t.month, "")
            extras.append({"kind": "event",
                           "text": f"{kind.capitalize()} {label}: {fmt_date(t)} о {hm(t)}."})
    return extras


# ── Хмарність (Open-Meteo) ─────────────────────────────────────────────────
def cloud_cover(day: date, t_from: datetime, t_to: datetime) -> Optional[dict]:
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", headers=HEADERS, timeout=20, params={
            "latitude": LAT, "longitude": LON, "hourly": "cloud_cover",
            "timezone": "Europe/Kyiv", "forecast_days": 2})
        r.raise_for_status()
        h = r.json()["hourly"]
        vals = [v for t, v in zip(h["time"], h["cloud_cover"])
                if v is not None and t_from <= datetime.fromisoformat(t).replace(tzinfo=TZ) <= t_to]
        if not vals:
            return None
        avg = round(sum(vals) / len(vals))
    except Exception as e:
        log.warning("Хмарність недоступна: %s", e)
        return None
    if avg <= 20:
        verdict = "ясно, чудові умови для спостережень"
    elif avg <= 50:
        verdict = "малохмарно, небо переважно видно"
    elif avg <= 80:
        verdict = "мінлива хмарність, прояснення можливі"
    else:
        verdict = "суцільна хмарність, зірок майже не буде видно"
    return {"kind": "cloud", "text": f"Хмарність увечері: ≈ {avg} % — {verdict}."}


# ── МКС (CelesTrak) ────────────────────────────────────────────────────────
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle"


def fetch_tle() -> Optional[list[str]]:
    try:
        r = requests.get(TLE_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        lines = [x.strip() for x in r.text.splitlines() if x.strip()]
        if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
            return lines[:3]
    except Exception as e:
        log.warning("TLE МКС недоступний: %s", e)
    return None


def iss_passes(t_from: datetime, t_to: datetime, tle: list[str], limit: int = 2) -> list[dict]:
    """Видимі прольоти: макс. висота ≥ 20°, МКС освітлена Сонцем, Сонце нижче −6°."""
    iss = ephem.readtle(*tle)
    o = observer(t_from)
    o.horizon = "0"
    sun = ephem.Sun()
    out = []
    for _ in range(25):
        try:
            rise, _, tmax, alt_max, tset, _ = o.next_pass(iss)
        except (ValueError, ephem.CircumpolarError):
            break
        if L(rise) > t_to:
            break
        o.date = tmax
        iss.compute(o)
        sun.compute(o)
        if (not iss.eclipsed and math.degrees(sun.alt) < -6 and math.degrees(alt_max) >= 20):
            out.append({"time": hm(L(tmax)), "alt": round(math.degrees(alt_max)),
                        "dir": compass(math.degrees(iss.az)),
                        "dur": max(1, round((float(tset) - float(rise)) * 1440))})
        o.date = tset + ephem.minute
        if len(out) >= limit:
            break
    return out


# ── Збірка даних ───────────────────────────────────────────────────────────
def collect(day: date) -> dict:
    sun = sun_info(day)
    t_eve = sun["_set"] + timedelta(minutes=90)
    next_rise, _ = sun_times(day + timedelta(days=1))
    t_morn = next_rise - timedelta(minutes=90)

    moon = moon_info(day, t_eve)
    eve, morn = planets_at(t_eve), planets_at(t_morn)

    extras: list[dict] = []
    cl = cloud_cover(day, t_eve - timedelta(minutes=30), min(t_eve + timedelta(hours=4),
                                                            local_midnight(day) + timedelta(hours=26)))
    if cl:
        extras.append(cl)
    tle = fetch_tle()
    if tle:
        try:
            passes = iss_passes(sun["_set"], t_morn, tle)
        except Exception as e:
            log.warning("Розрахунок МКС не вдався: %s", e)
            passes = []
        for p in passes:
            extras.append({"kind": "iss",
                           "text": f"МКС: {p['time']}, максимум {p['alt']}° ({p['dir']}), "
                                   f"над горизонтом ≈ {p['dur']} хв — яскрава «зірка», що рухається без миготіння."})
    extras += planet_events(t_eve, eve)
    extras += upcoming_events(day)

    def clean(lst):
        return [{k: v for k, v in p.items() if not k.startswith("_")} for p in lst]

    return {
        "date_long": f"{day.day} {MONTHS[day.month - 1]} {day.year}",
        "weekday": WEEKDAYS[day.weekday()],
        "moon": moon,
        "sun": {k: v for k, v in sun.items() if not k.startswith("_")},
        "phases": next_phases(t_eve),
        "windows": [
            {"label": f"Сьогодні ввечері, о {hm(t_eve)}", "planets": clean(eve)},
            {"label": f"Завтра вранці, о {hm(t_morn)}", "planets": clean(morn)},
        ],
        "extras": extras,
        "_dark_hint": moon["illum"],
    }


# ── Текст посту ────────────────────────────────────────────────────────────
def build_text(data: dict) -> str:
    e = html.escape
    m, s = data["moon"], data["sun"]
    L_ = [
        "🔭 <b>Небо над Сумами</b>",
        f"📅 {data['weekday'].capitalize()}, {data['date_long']}",
        "",
        f"🌙 <b>{m['name']}</b> · освітлено {m['illum']} % · вік {m['age']} доби",
        f"    Схід {m['rise']} · захід {m['set']}",
        f"☀️ <b>Сонце:</b> схід {s['rise']} · захід {s['set']}",
        f"    День {s['length']} ({s['delta']})",
        "",
        "✨ <b>Що видно без телескопа</b>",
    ]
    any_planet = False
    for w in data["windows"]:
        if not w["planets"]:
            continue
        any_planet = True
        L_.append(f"<i>{e(w['label'])}</i>")
        for p in w["planets"]:
            L_.append(f"🪐 <b>{p['name']}</b> ({p['mag']}) — {p['dir']}, {p['alt']}° над горизонтом "
                      f"(≈ {p['fists']} {'кулак' if p['fists'] == 1 else 'кулаки' if p['fists'] < 5 else 'кулаків'}), "
                      f"сузір’я {p['const']}")
    if not any_planet:
        L_.append("Яскравих планет над горизонтом у ці години немає.")
    else:
        L_.append("<i>Кулак на витягнутій руці ≈ 10° — так легко оцінити висоту.</i>")

    if data["extras"]:
        L_ += ["", "📌 <b>Умови та події</b>"]
        icons = {"cloud": "☁️", "iss": "🛰", "event": "⭐", "retro": "↩️", "shower": "☄️"}
        for ex in data["extras"]:
            L_.append(f"{icons.get(ex['kind'], '•')} {e(ex['text'])}")

    L_ += ["", f"🗓 <b>Найближчі фази Місяця:</b> {'; '.join(data['phases'])}.",
           "", "<i>Розрахунок для координат Сум (50,91° пн. ш., 34,80° сх. д.), час київський.</i>",
           "", HASHTAGS]
    return "\n".join(L_)


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
