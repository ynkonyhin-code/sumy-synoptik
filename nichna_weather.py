#!/usr/bin/env python3
"""
nichna_weather — «Зведення тиші»: нічна погода + небо (nichna_sky.py) від Сови для Сумського синоптика.

Джерело за замовчуванням — Open-Meteo (безкоштовно, без ключа), координати Сум.
Якщо у weather_daily.py дані беруться з іншого джерела, замініть лише fetch_hourly():
вона має повернути словник списків з ключами, як нижче (час у Києві, формат "YYYY-MM-DDTHH:MM").
"""
import random
from datetime import datetime, timedelta

import requests

LAT, LON = 50.9077, 34.7981   # Суми
HOURLY = ("temperature_2m,precipitation_probability,precipitation,weather_code,"
          "cloud_cover,wind_speed_10m,wind_gusts_10m,visibility")


def fetch_hourly(timeout=15):
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON, "hourly": HOURLY,
        "wind_speed_unit": "ms", "timezone": "Europe/Kyiv", "forecast_days": 2,
    }, timeout=timeout)
    r.raise_for_status()
    return r.json()["hourly"]


def night_window(h, now):
    """Індекси годин від поточної до 07:00 наступного ранку (за Києвом)."""
    end = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if now.hour >= 7:
        end += timedelta(days=1)
    start = now.replace(minute=0, second=0, microsecond=0)
    out = []
    for i, t in enumerate(h["time"]):
        dt = datetime.fromisoformat(t).replace(tzinfo=now.tzinfo)
        if start <= dt <= end:
            out.append(i)
    return out


def _vals(h, key, idx):
    return [h[key][i] for i in idx if h.get(key) and h[key][i] is not None]


def summarize(h, now):
    idx = night_window(h, now)
    if len(idx) < 2:
        return None
    t = _vals(h, "temperature_2m", idx)
    if not t:
        return None
    codes = set(int(c) for c in _vals(h, "weather_code", idx))
    return {
        "tmin": min(t), "tmax": max(t),
        "wind": max(_vals(h, "wind_speed_10m", idx) or [0]),
        "gust": max(_vals(h, "wind_gusts_10m", idx) or [0]),
        "pprob": max(_vals(h, "precipitation_probability", idx) or [0]),
        "precip": sum(_vals(h, "precipitation", idx)),
        "cloud": sum(_vals(h, "cloud_cover", idx) or [50]) / max(1, len(_vals(h, "cloud_cover", idx))),
        "vis": min(_vals(h, "visibility", idx) or [20000]),
        "snow": bool(codes & {71, 73, 75, 77, 85, 86}),
        "rain": bool(codes & {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}),
        "fog": bool(codes & {45, 48}),
        "storm": bool(codes & {95, 96, 99}),
    }


def is_notable(s):
    """Чи варта погода обов'язкової згадки."""
    return bool(s["tmin"] <= 0 or s["gust"] >= 12 or s["storm"] or s["fog"]
                or s["snow"] or s["rain"] or s["pprob"] >= 60)


def build_block(s, rnd=random, footer_on=False):
    """Текст «Зведення тиші» (HTML для Telegram)."""
    sky = ("небо переважно ясне" if s["cloud"] < 30 else
           "місцями прояснення" if s["cloud"] < 70 else "небо затягнуте хмарами")
    lines = [
        "🌙 <b>Зведення тиші</b> <i>(нічна погода від Сови)</i>",
        (f"🌡 Температура: близько {s['tmin']:+.0f}°" if round(s['tmin']) == round(s['tmax'])
         else f"🌡 Температура: від {s['tmin']:+.0f}° до {s['tmax']:+.0f}°"),
        f"💨 Вітер до {s['wind']:.0f} м/с, пориви до {s['gust']:.0f} м/с",
        f"☁️ {sky[0].upper() + sky[1:]}",
    ]
    if s["storm"]:
        lines.append("⛈ Можлива гроза, будьте обережні.")
    elif s["snow"]:
        lines.append("❄️ Очікується сніг.")
    elif s["rain"] or s["pprob"] >= 60:
        lines.append(f"🌧 Можливі опади (імовірність до {s['pprob']:.0f}%).")
    if s["fog"] or s["vis"] < 1000:
        lines.append("🌫 Можливий туман, на дорогах обережніше.")
    if s["tmin"] <= 0:
        lines.append("🧊 Температура опускається до нуля й нижче: може бути слизько.")
    if s["gust"] >= 15:
        lines.append("🌬 Сильні пориви: закріпіть усе, що може злетіти.")
    if footer_on:
        lines += ["", footer(rnd)]
    return "\n".join(lines)


QUIPS = [
    "Сова киває: так, ніч буде саме такою.",
    "Сова примружила одне око: прогноз перевірений.",
    "Сова поправила окуляри й дописала в журнал вахти.",
    "Сова каже: хто виглянув у вікно, той усе бачив і сам.",
]


def footer(rnd=random):
    return "\n".join([
        f"🦉 {rnd.choice(QUIPS)}",
        "<i>Це лише про погоду та небо. Про тривоги дивіться офіційні сповіщення.</i>",
    ])


def get_block(now, rnd=random, force=False, chance=0.5):
    """«Зведення тиші»: погода + небо. Повертає текст або None. Ніколи не кидає виняток.
    Небо рахується локально, тож блок працює навіть коли погодне джерело недоступне."""
    hourly, s = None, None
    try:
        hourly = fetch_hourly()
        s = summarize(hourly, now)
    except Exception as e:  # мережа, формат, будь-що
        print(f"[warn] нічна погода недоступна: {e}")

    sky_text, sky_notable = None, False
    try:
        import nichna_sky
        sky_text, sky_notable = nichna_sky.build_block(now, hourly, rnd)
    except Exception as e:
        print(f"[warn] небо недоступне: {e}")

    if not s and not sky_text:
        return None
    notable = (s is not None and is_notable(s)) or sky_notable
    if not (force or notable or rnd.random() < chance):
        return None
    parts = []
    if s:
        parts.append(build_block(s, rnd))
    if sky_text:
        parts.append(sky_text)
    parts.append(footer(rnd))
    return "\n\n".join(parts)
