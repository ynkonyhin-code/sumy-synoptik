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

from events_db import commit_journal, log_event

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
KP_ALERT = 5.0  # G1 и выше

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
KP_FORECAST_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
SUN_IMG_URL = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0304.jpg"

# (мин. Kp, значок, заголовок, что это значит, совет)
LEVELS = [
    (8, "🔴", "сильна магнітна буря",
     "Це природне явище, і для життя воно не небезпечне. Але метеозалежні люди можуть відчувати себе помітно гірше: сильний головний біль, тиск, безсоння, слабкість.",
     "Не перевантажуйтесь, пийте воду, високий тиск вимірюйте вчасно, ліки приймайте за призначенням лікаря."),
    (6, "🟠", "помірна магнітна буря",
     "Це природне явище, небезпеки для життя немає. Люди, чутливі до погоди, можуть відчути головний біль, сонливість, перепади тиску.",
     "Більше води та спокою, менше кави, не відкладайте звичні ліки."),
    (5, "🟠", "слабка магнітна буря",
     "Це природне явище, небезпеки немає. Більшість людей нічого не помітить, а метеозалежні можуть відчути легкий головний біль або втому.",
     "Пийте воду, лягайте спати вчасно."),
    (4, "🟡", "невеликі коливання",
     "Магнітне поле трохи неспокійне. Більшість людей нічого не відчує, лише дуже чутливі можуть помітити легку втому.",
     ""),
    (0, "🟢", "спокійне",
     "Магнітних бур немає, на самопочуття вони не вплинуть. Живемо як зазвичай.",
     ""),
]


def describe(kp: float):
    return next(lv for lv in LEVELS if kp >= lv[0])


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


def build_text(kp_now: float, kp_peak: float | None, alert: bool) -> str:
    worst = max(kp_now, kp_peak or 0)
    _, emoji, title, meaning, tip = describe(worst)
    when = "Сьогодні на Землі" if alert else "Магнітне поле Землі сьогодні"
    head = f"{emoji} <b>{when}: {title}</b>"
    parts = [head, "", meaning]
    if tip:
        parts += ["", f"💡 <b>Порада:</b> {tip}"]
    parts += ["", "☀️ Так зараз виглядає Сонце (знімок NASA)", ""]
    tech = f"Kp-індекс: зараз {kp_now:.0f}"
    if kp_peak is not None:
        tech += f", найближчі 24 год до {kp_peak:.0f}"
    tech += ". Шкала від 0 до 9, помітний вплив починається з 5. Дані: NOAA, NASA."
    parts.append(f"<i>{tech}</i>")
    return "\n".join(parts)


def run_alert():
    kp, t = current_kp()
    if kp < KP_ALERT:
        return
    # один пост на (дата, уровень): повторные запуски дублей не дадут
    key = f"kp-{t[:10]}-{int(kp)}"
    if log_event("space", f"Kp {kp}", key=key):
        send(build_text(kp, None, alert=True))
        commit_journal()


def run_daily():
    kp, _ = current_kp()
    peak = forecast_peak()
    send(build_text(kp, peak[0] if peak else None, alert=False))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "alert"
    {"alert": run_alert, "daily": run_daily}[mode]()
