#!/usr/bin/env python3
"""
nichna_sky — «Небо цієї ночі»: астрономічна частина «Зведення тиші» від Сови.

Усе рахується локально бібліотекою ephem, без зовнішніх API (крім необов'язкового Kp-індексу NOAA).
Що показує:
  • фаза Місяця, освітленість, вік, схід/захід, наступні новий і повний місяць;
  • тривалість повної (астрономічної) темряви та «безмісячні» години;
  • видимість зір (хмарність із погодних даних + заважання Місяця) і найясніша година;
  • видимі планети (час, напрям, висота) та зближення Місяця з планетою;
  • метеорні потоки поблизу максимуму;
  • що шукати на небі цього місяця;
  • магнітна буря / шанс сяйва (за наявності Kp від NOAA).
"""
import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import ephem
import requests

KYIV = ZoneInfo("Europe/Kyiv")
LAT, LON, ELEV = "50.9077", "34.7981", 130   # Суми

PLANETS = [("Меркурій", ephem.Mercury), ("Венера", ephem.Venus), ("Марс", ephem.Mars),
           ("Юпітер", ephem.Jupiter), ("Сатурн", ephem.Saturn)]
COMPASS = ["пн", "пн-сх", "сх", "пд-сх", "пд", "пд-зх", "зх", "пн-зх"]

# (назва, місяць, день максимуму, радіант, метеорів/год за ідеальних умов)
SHOWERS = [
    ("Квадрантиди", 1, 4, "Волопас", 110), ("Ліриди", 4, 22, "Ліра", 18),
    ("Ета-Аквариди", 5, 6, "Водолій", 40), ("Персеїди", 8, 12, "Персей", 100),
    ("Драконіди", 10, 8, "Дракон", 10), ("Оріоніди", 10, 21, "Оріон", 20),
    ("Тауріди", 11, 5, "Бик", 5), ("Леоніди", 11, 17, "Лев", 15),
    ("Геміниди", 12, 14, "Близнюки", 150), ("Урсиди", 12, 22, "Мала Ведмедиця", 10),
]

# Що шукати на небі ввечері (для ~51° пн.ш.)
TIPS = {
    1: ["Оріон і Сіріус на півдні", "Плеяди високо над головою", "Капела майже в зеніті"],
    2: ["Близнюки (Кастор і Поллукс) на півдні", "Оріон хилиться на захід", "Лев сходить на сході"],
    3: ["Рак і Малий Пес із Проціоном", "Велика Ведмедиця майже в зеніті", "Близнюки на заході"],
    4: ["Лев високо на півдні", "Арктур сходить на сході", "Велика Ведмедиця в зеніті"],
    5: ["Волопас з Арктуром", "Діва зі Спікою на півдні", "Ліра з Вегою сходить на сході"],
    6: ["Літній трикутник: Вега, Денеб, Альтаїр", "Короткі ночі, зорі проявляються пізно", "Арктур на заході"],
    7: ["Літній трикутник високо", "Чумацький Шлях Лебедем через небо", "Скорпіон низько на півдні"],
    8: ["Чумацький Шлях за містом", "Лебідь з Денебом у зеніті", "Персеїди в серпні"],
    9: ["Лебідь і Орел, Чумацький Шлях", "Пегас сходить на сході", "Вега хилиться на захід"],
    10: ["Квадрат Пегаса на півдні", "Андромеда й галактика за містом", "Плеяди сходять на сході"],
    11: ["Кассіопея високо, Андромеда поруч", "Плеяди й Капела високо", "Оріон виходить пізно ввечері"],
    12: ["Оріон із трьома зірками пояса", "Бик з Альдебараном і Плеядами", "Сіріус яскраво сходить на сході"],
}
EMOJI = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]


# ───────────── утиліти часу ─────────────
def _local(d):
    return ephem.Date(d).datetime().replace(tzinfo=timezone.utc).astimezone(KYIV)


def _eph(dt):
    return ephem.Date(dt.astimezone(timezone.utc).replace(tzinfo=None))


def _obs(dt=None, horizon="0"):
    o = ephem.Observer()
    o.lat, o.lon, o.elevation, o.horizon = LAT, LON, ELEV, horizon
    if dt is not None:
        o.date = _eph(dt)
    return o


def _hm(dt):
    return f"{dt:%H:%M}"


def _dur(a, b):
    m = int((b - a).total_seconds() // 60)
    return f"{m // 60} год {m % 60:02d} хв"


def night_window(now):
    """(початок ночі = захід Сонця, кінець = схід) та вікно повної темряви (або None)."""
    sun = ephem.Sun()
    o = _obs(now)
    sun.compute(o)
    if sun.alt > 0:
        start = o.next_setting(sun)
    else:
        start = o.previous_setting(sun)
    o.date = start
    end = o.next_rising(sun)
    dark = None
    try:
        o2 = _obs(horizon="-18")
        o2.date = start
        ds = o2.next_setting(sun, use_center=True)
        o2.date = ds
        de = o2.next_rising(sun, use_center=True)
        if de <= end + ephem.hour:
            dark = (_local(ds), _local(de))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        dark = None
    return _local(start), _local(end), dark


# ───────────── Місяць ─────────────
def moon_info(now, start, end, dark):
    o = _obs(start)
    m = ephem.Moon(o)
    illum = m.phase
    age = o.date - ephem.previous_new_moon(o.date)
    frac = age / 29.530588
    idx = int(((frac * 8) + 0.5) % 8)
    names = ["новий Місяць", "молодий серп", "перша чверть", "зростаючий Місяць",
             "повний Місяць", "спадаючий Місяць", "остання чверть", "старий серп"]
    # уточнення назв «серп/горбатий» за освітленістю
    if idx == 3:
        names[3] = "зростаючий Місяць (більше половини диска)"
    if idx == 5:
        names[5] = "спадаючий Місяць (більше половини диска)"
    d = {"emoji": EMOJI[idx], "name": names[idx], "illum": illum, "age": age}
    # схід / захід у межах ночі
    rise = set_ = None
    try:
        r = o.next_rising(ephem.Moon())
        if _local(r) <= end:
            rise = _local(r)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass
    try:
        s = o.next_setting(ephem.Moon())
        if _local(s) <= end:
            set_ = _local(s)
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass
    d["rise"], d["set"] = rise, set_
    d["up_at_start"] = m.alt > 0
    d["next_new"] = _local(ephem.next_new_moon(o.date))
    d["next_full"] = _local(ephem.next_full_moon(o.date))
    # частка темних годин, коли Місяць над горизонтом
    frac_up, total = 0, 0
    if dark:
        t = dark[0]
        while t <= dark[1]:
            om = _obs(t)
            mm = ephem.Moon(om)
            total += 1
            frac_up += mm.alt > 0
            t += timedelta(minutes=15)
    d["frac_up"] = (frac_up / total) if total else (1.0 if d["up_at_start"] else 0.0)
    d["moonless_min"] = int((total - frac_up) * 15) if total else None
    return d


def moon_lines(d):
    lines = [f"{d['emoji']} Місяць: {d['name']}, освітлено {d['illum']:.0f}% (вік {d['age']:.0f} діб)"]
    if d["rise"] and d["set"]:
        lines.append(f"   схід {_hm(d['rise'])}, захід {_hm(d['set'])}")
    elif d["rise"]:
        lines.append(f"   сходить о {_hm(d['rise'])}, до цього небо без Місяця")
    elif d["set"]:
        lines.append(f"   заходить о {_hm(d['set'])}, після цього небо темне")
    elif d["up_at_start"]:
        lines.append("   Місяць на небі всю ніч")
    else:
        lines.append("   Місяця на небі не буде всю ніч")
    lines.append(f"   наступний новий: {d['next_new']:%d.%m}, повний: {d['next_full']:%d.%m}")
    return lines


# ───────────── планети ─────────────
def planets_info(start, end):
    out, conj = [], []
    t_samples = []
    t = start
    while t <= end:
        t_samples.append(t)
        t += timedelta(minutes=30)
    sun = ephem.Sun()
    for name, cls in PLANETS:
        best = None
        for t in t_samples:
            o = _obs(t)
            sun.compute(o)
            if math.degrees(sun.alt) > -6:        # ще надто світло
                continue
            p = cls(o)
            alt = math.degrees(p.alt)
            if alt < 8 or p.mag > 3.0:
                continue
            mo = ephem.Moon(o)
            sep = math.degrees(ephem.separation((p.az, p.alt), (mo.az, mo.alt))) if mo.alt > 0 else None
            if best is None or alt > best["alt"]:
                best = {"name": name, "alt": alt, "t": t, "az": math.degrees(p.az), "mag": p.mag}
            if sep is not None and sep < 5:
                conj.append((name, sep, t))
        if best:
            out.append(best)
    out.sort(key=lambda b: b["mag"])
    best_conj = {}
    for n, s, t in conj:
        if n not in best_conj or s < best_conj[n][0]:
            best_conj[n] = (s, t)
    return out[:4], best_conj


def planet_lines(planets, conj, cloudy=False):
    lines = []
    if planets:
        lines.append("🪐 Планети на небі (цієї ночі їх, найімовірніше, сховають хмари):" if cloudy
                     else "🪐 Планети, які видно неозброєним оком:")
        for p in planets:
            d = COMPASS[int(((p["az"] + 22.5) % 360) // 45)]
            lines.append(f"   • {p['name']} ({p['mag']:+.1f}ᵐ): найкраще о {_hm(p['t'])}, {d}, {p['alt']:.0f}° над обрієм")
    else:
        lines.append("🪐 Яскравих планет цієї ночі на небі практично не видно.")
    for n, (s_, t) in conj.items():
        lines.append(f"💫 Місяць зблизився з планетою {n} (≈{s_:.0f}° між ними), найкраще о {_hm(t)}")
    return lines


# ───────────── метеори ─────────────
def meteor_line(start, pen, cloudy=False):
    day = start.date()
    for name, m, dd, radiant, zhr in SHOWERS:
        for y in (day.year - 1, day.year, day.year + 1):
            try:
                peak = datetime(y, m, dd).date()
            except ValueError:
                continue
            delta = (day - peak).days
            if abs(delta) <= 2:
                when = "максимум цієї ночі" if delta == 0 else f"максимум {peak:%d.%m}"
                moon = ("Місяць не заважатиме" if pen < 0.15 else
                        "Місяць трохи заважатиме" if pen < 0.4 else "яскравий Місяць заважатиме")
                strong = zhr >= 15
                return (f"☄️ Метеорний потік {name}: {when}, до ~{zhr} метеорів/год за ідеальних умов "
                        f"(радіант у сузір'ї «{radiant}»). {moon}."
                        + (" Але хмари, схоже, усе сховають." if cloudy else "")), strong
    return None, False


# ───────────── видимість зір ─────────────
def star_visibility(hourly, dark, moon):
    """(рядки, оцінка 0–100 або None)."""
    pen = (moon["illum"] / 100.0) * moon["frac_up"]
    if not hourly or not dark:
        return [], None, pen
    cl, best = [], None
    for i, t in enumerate(hourly["time"]):
        dt = datetime.fromisoformat(t).replace(tzinfo=KYIV)
        if dark[0] - timedelta(minutes=30) <= dt <= dark[1]:
            c = hourly["cloud_cover"][i]
            if c is None:
                continue
            cl.append(c)
            if best is None or c < best[0]:
                best = (c, dt)
    if not cl:
        return [], None, pen
    mean_cloud = sum(cl) / len(cl)
    score = max(0.0, 100 - mean_cloud * 0.85 - pen * 35)
    label = ("відмінна ✨" if score >= 80 else "добра" if score >= 55 else
             "так собі" if score >= 30 else "погана, зорі ховаються")
    lines = [f"✨ Видимість зір: {label} (хмарність у темряві ≈{mean_cloud:.0f}%)"]
    if best and mean_cloud < 90 and best[0] < mean_cloud - 10:
        lines.append(f"   найясніше близько {_hm(best[1])} (хмарність ≈{best[0]:.0f}%)")
    return lines, score, pen


# ───────────── Kp (необов'язково) ─────────────
def kp_max(start, end, timeout=10):
    try:
        r = requests.get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json",
                         timeout=timeout)
        r.raise_for_status()
        rows = r.json()
        head = [str(x).lower() for x in rows[0]]
        ti, ki = head.index("time_tag"), head.index("kp")
        vals = []
        for row in rows[1:]:
            t = datetime.fromisoformat(row[ti].replace("T", " ")[:19]).replace(tzinfo=timezone.utc)
            if start - timedelta(hours=3) <= t <= end:
                vals.append(float(row[ki]))
        return max(vals) if vals else None
    except Exception as e:
        print(f"[warn] Kp недоступний: {e}")
        return None


# ───────────── збірка блоку ─────────────
def build_block(now, hourly=None, rnd=random, with_kp=True):
    """Повертає (html_текст, чи_помітна_ніч). Працює і без погоди та інтернету."""
    start, end, dark = night_window(now)
    moon = moon_info(now, start, end, dark)
    lines = ["🔭 <b>Небо цієї ночі</b>"]
    notable = False

    lines += moon_lines(moon)
    if moon["age"] < 1 or moon["age"] > 28.5 or abs(moon["age"] - 14.77) < 0.8:
        notable = True

    if dark:
        extra = ""
        if moon["moonless_min"] is not None and moon["moonless_min"] > 0 and moon["illum"] > 5:
            extra = f", із них {moon['moonless_min'] // 60} год {moon['moonless_min'] % 60:02d} хв без Місяця"
        lines.append(f"🌌 Повна темрява: {_hm(dark[0])}–{_hm(dark[1])} ({_dur(*dark)}{extra})")
    else:
        lines.append("🌌 Повної темряви немає: світлі ночі, сутінки до самого ранку")

    vis_lines, score, pen = star_visibility(hourly, dark, moon)
    lines += vis_lines
    if score is not None and score >= 80:
        notable = True
    if score is not None and score >= 75 and pen < 0.2 and moon["illum"] < 40:
        lines.append("   🌠 Чумацький Шлях і слабкі зорі шукайте за містом, подалі від ліхтарів")

    planets, conj = planets_info(start, end)
    lines += planet_lines(planets, conj, cloudy=(score is not None and score < 30))
    if conj:
        notable = True

    mline, mnot = meteor_line(start, pen, cloudy=(score is not None and score < 30))
    if mline:
        lines.append(mline)
        notable = notable or mnot

    if with_kp:
        kp = kp_max(start, end)
        if kp is not None and kp >= 5:
            lines.append(f"🧲 Геомагнітне збурення (Kp до {kp:.0f})")
            if kp >= 7:
                lines.append("   🌌 Є невеликий шанс північного сяйва низько над північним обрієм")
            notable = notable or kp >= 6

    tips = TIPS.get(start.month, [])
    pick = rnd.sample(tips, k=min(2, len(tips))) if tips else []
    pick.append("Полярна зоря й «ківш» Великої Ведмедиці видно завжди, коли небо чисте")
    lines.append("🧭 Що шукати: " + "; ".join(pick[:3]) + ".")
    return "\n".join(lines), notable


if __name__ == "__main__":
    import sys
    when = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=KYIV) if len(sys.argv) > 1 else datetime.now(KYIV)
    print(build_block(when, None, random, with_kp=False)[0])
