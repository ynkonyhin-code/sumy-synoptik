"""Журнал событий канала «Сумський синоптик» (SQLite) + недельный итог.

Использование из любого вашего скрипта:
    from events_db import log_event
    if log_event("water", "Аварія на вул. Харківській", key="water-<уникальный id>"):
        ...  # событие новое, можно публиковать (дубли отсекаются сами)
"""
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).with_name("synoptic.db")
TZ = ZoneInfo("Europe/Kyiv")

# Типы событий: подберите под свои скрипты
TYPE_TITLES = {
    "alert": "🚨 Повітряних тривог",
    "water": "🚰 Аварій водоканалу",
    "power": "💡 Змін графіків світла",
    "space": "🧲 Магнітних бур",
}


def kyiv_now() -> datetime:
    """Текущее киевское время (GitHub-сервер живёт по UTC)."""
    return datetime.now(TZ).replace(tzinfo=None)


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        type TEXT NOT NULL,
        text TEXT NOT NULL,
        dedup_key TEXT UNIQUE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS daily_weather(
        day TEXT PRIMARY KEY,
        tmax REAL, tmin REAL, precip REAL, wind_max REAL)""")
    return c


def log_event(etype: str, text: str, key: str | None = None) -> bool:
    """Записать событие. Возвращает False, если такой key уже есть (дубль)."""
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO events(ts,type,text,dedup_key) VALUES(?,?,?,?)",
                (kyiv_now().isoformat(timespec="seconds"), etype, text, key),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def save_daily_weather(day: str, tmax, tmin, precip, wind_max):
    """day='2026-10-15'. Повторный вызов обновит запись."""
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO daily_weather VALUES(?,?,?,?,?)",
            (day, tmax, tmin, precip, wind_max),
        )


def _dm(day: str) -> str:
    return f"{day[8:10]}.{day[5:7]}"


def weekly_digest(last_day: date | None = None, days: int = 7) -> str:
    """Итог за `days` полных суток, заканчивая last_day (по умолчанию вчера)."""
    last_day = last_day or (kyiv_now().date() - timedelta(days=1))
    first_day = last_day - timedelta(days=days - 1)
    t0 = datetime.combine(first_day, time.min).isoformat()
    t1 = datetime.combine(last_day + timedelta(days=1), time.min).isoformat()

    with _conn() as c:
        counts = dict(c.execute(
            "SELECT type, COUNT(*) FROM events WHERE ts>=? AND ts<? GROUP BY type",
            (t0, t1)).fetchall())
        weather = c.execute(
            "SELECT day,tmax,tmin,precip,wind_max FROM daily_weather "
            "WHERE day BETWEEN ? AND ? ORDER BY day",
            (first_day.isoformat(), last_day.isoformat())).fetchall()

    lines = [f"📊 <b>Підсумок тижня</b> ({first_day:%d.%m}–{last_day:%d.%m})", ""]

    hot = [r for r in weather if r[1] is not None]
    cold = [r for r in weather if r[2] is not None]
    if hot and cold:
        warm = max(hot, key=lambda r: r[1])
        chill = min(cold, key=lambda r: r[2])
        both = [(r[1] + r[2]) / 2 for r in weather if r[1] is not None and r[2] is not None]
        rain = sum(r[3] or 0 for r in weather)
        wet_days = sum(1 for r in weather if (r[3] or 0) >= 0.5)
        lines += [
            "🌤 <b>Погода</b>",
            f"🔥 Найтепліший день: {_dm(warm[0])} ({warm[1]:+.0f}°)",
            f"❄️ Найхолодніша ніч: {_dm(chill[0])} ({chill[2]:+.0f}°)",
        ]
        if both:
            lines.append(f"🌡 Середня температура: {sum(both) / len(both):+.0f}°")
        lines.append(f"🌧 Опади: {rain:.1f} мм (дощових днів: {wet_days})")
        winds = [r for r in weather if r[4] is not None]
        if winds:
            windy = max(winds, key=lambda r: r[4])
            lines.append(f"💨 Найсильніший вітер: {windy[4]:.0f} м/с ({_dm(windy[0])})")
        if len(weather) < days:
            lines.append(f"<i>Дані за {len(weather)} з {days} днів</i>")
        lines.append("")

    ev = [f"{title}: {counts[t]}" for t, title in TYPE_TITLES.items() if counts.get(t)]
    if ev:
        lines += ["📌 <b>Події</b>"] + ev + [""]

    if len(lines) <= 2:
        lines.append("За цей тиждень даних поки немає.")
    return "\n".join(lines).rstrip()


if __name__ == "__main__":
    print(weekly_digest())
