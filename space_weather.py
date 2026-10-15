"""Космічна погода: Kp-індекс (NOAA SWPC) + знімок Сонця (NASA SDO).

Режимы:
    python3 space_weather.py daily   # ежедневный короткий прогноз (cron, напр. 09:00)
    python3 space_weather.py alert   # проверка бури, шлёт только при Kp >= порога (cron каждые 30 мин)

Переменные окружения: BOT_TOKEN, CHAT_ID (например @sumy_synoptic)
Зависимость: pip install requests
"""
import os
import sys
from datetime import datetime, timezone

import requests

from events_db import log_event

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
KP_ALERT = 5.0  # G1 и выше

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
KP_FORECAST_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
SUN_IMG_URL = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0304.jpg"

SCALE = [(9, "G5 екстремальна"), (8, "G4 сильна"), (7, "G3 помірна+"),
         (6, "G2 помірна"), (5, "G1 слабка"), (4, "активно"), (0, "спокійно")]


def level(kp: float) -> str:
    return next(name for thr, name in SCALE if kp >= thr)


def _rows(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    # NOAA меняла формат: список списков (с заголовком) или список словарей
    if data and isinstance(data[0], list):
        head, *body = data
        data = [dict(zip(head, row)) for row in body]
    return data


def current_kp():
    row = _rows(KP_URL)[-1]
    return float(row["Kp"]), row["time_tag"]


def forecast_peak():
    """Максимальный прогнозный Kp на ближайшие сутки (по таблице NOAA)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    best = None
    for row in _rows(KP_FORECAST_URL):
        if row.get("observed") != "predicted":
            continue
        t = datetime.fromisoformat(row["time_tag"].replace("Z", ""))
        if 0 <= (t - now).total_seconds() <= 86400:
            kp = float(row["kp"])
            if best is None or kp > best[0]:
                best = (kp, t)
    return best


def send(text: str, with_sun=True):
    api = f"https://api.telegram.org/bot{BOT_TOKEN}"
    if with_sun:
        img = requests.get(SUN_IMG_URL, timeout=60)
        img.raise_for_status()
        r = requests.post(f"{api}/sendPhoto",
                          data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                          files={"photo": ("sun.jpg", img.content)}, timeout=60)
    else:
        r = requests.post(f"{api}/sendMessage",
                          data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
                          timeout=30)
    r.raise_for_status()


def run_alert():
    kp, t = current_kp()
    if kp < KP_ALERT:
        return
    # один пост на (дата, уровень): повторные запуски cron дублей не дадут
    key = f"kp-{t[:10]}-{int(kp)}"
    text = (f"🧲 <b>Магнітна буря: Kp {kp:.0f} ({level(kp)})</b>\n"
            f"Дані NOAA на {t[11:16]} UTC. Метеозалежним: бережіть себе, "
            f"менше навантажень, більше води.\n\n"
            f"☀️ Сонце зараз (SDO, 304 Å)")
    if log_event("space", f"Kp {kp}", key=key):
        send(text)


def run_daily():
    kp, t = current_kp()
    peak = forecast_peak()
    lines = [f"🧲 <b>Космічна погода</b>",
             f"Зараз: Kp {kp:.0f} ({level(kp)})"]
    if peak:
        lines.append(f"Прогноз на 24 год: до Kp {peak[0]:.0f} ({level(peak[0])})")
    lines += ["", "☀️ Сонце зараз (SDO, 304 Å)", "<i>Джерело: NOAA SWPC, NASA SDO</i>"]
    send("\n".join(lines))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "alert"
    {"alert": run_alert, "daily": run_daily}[mode]()
