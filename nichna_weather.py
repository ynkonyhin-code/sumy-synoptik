#!/usr/bin/env python3
"""
nichna_weather — «Зведення тиші»: коротка нічна погода від Сови для Сумського синоптика.

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


def build_block(s, rnd=random):
    """Текст «Зведення тиші» (HTML для Telegram)."""
    sky = ("зорі видно добре" if s["cloud"] < 30 else
           "місцями прояснення" if s["cloud"] < 70 else "небо затягнуте хмарами")
    lines = [
        "🌙 <b>Зведення тиші</b> <i>(нічна погода від Сови)</i>",
        f"🌡 Температура: від {s['tmin']:+.0f}° до {s['tmax']:+.0f}°",
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
    quips = [
        "Сова киває: так, ніч буде саме такою.",
        "Сова примружила одне око: прогноз перевірений.",
        "Сова поправила окуляри й дописала в журнал вахти.",
        "Сова каже: хто виглянув у вікно, той усе бачив і сам.",
    ]
    lines += ["", f"🦉 {rnd.choice(quips)}",
              "<i>Це лише про погоду. Про тривоги дивіться офіційні сповіщення.</i>"]
    return "\n".join(lines)


def get_block(now, rnd=random, force=False, chance=0.5):
    """Повертає текст блоку або None (не ця ніч / джерело недоступне). Ніколи не кидає виняток."""
    try:
        s = summarize(fetch_hourly(), now)
    except Exception as e:  # мережа, формат, будь-що
        print(f"[warn] нічна погода недоступна: {e}")
        return None
    if not s:
        return None
    if force or is_notable(s) or rnd.random() < chance:
        return build_block(s, rnd)
    return None
