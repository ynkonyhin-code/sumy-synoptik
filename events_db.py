"""Журнал событий канала «Сумський синоптик» (SQLite) + недельный итог.

Использование из любого вашего скрипта:
    from events_db import log_event, save_daily_weather
    if log_event("alert", "Повітряна тривога", key="alert-2026-10-15T08:12"):
        ...  # событие новое, можно публиковать (дедупликация бесплатно)
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).with_name("synoptic.db")

# Типы событий: подберите под свои скрипты
TYPE_TITLES = {
    "alert": "Повітряні тривоги",
    "water": "Аварії водоканалу",
    "power": "Зміни графіків світла",
    "space": "Космічна погода",
    "other": "Інше",
}


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
                (datetime.now().isoformat(timespec="seconds"), etype, text, key),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def save_daily_weather(day: str, tmax, tmin, precip, wind_max):
    """Раз в сутки (вечером): day='2026-10-15'. Повторный вызов обновит запись."""
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO daily_weather VALUES(?,?,?,?,?)",
            (day, tmax, tmin, precip, wind_max),
        )


def weekly_digest(end: datetime | None = None, days: int = 7) -> str:
    end = end or datetime.now()
    start = end - timedelta(days=days)
    with _conn() as c:
        counts = dict(c.execute(
            "SELECT type, COUNT(*) FROM events WHERE ts>=? AND ts<=? GROUP BY type",
            (start.isoformat(), end.isoformat())).fetchall())
        weather = c.execute(
            "SELECT day,tmax,tmin,precip,wind_max FROM daily_weather "
            "WHERE day>? AND day<=? ORDER BY day",
            (start.date().isoformat(), end.date().isoformat())).fetchall()

    lines = [f"📊 <b>Підсумок тижня</b> ({start:%d.%m}–{end:%d.%m})", ""]

    if weather:
        warm = max(weather, key=lambda r: r[1] if r[1] is not None else -99)
        cold = min(weather, key=lambda r: r[2] if r[2] is not None else 99)
        rain = sum(r[3] or 0 for r in weather)
        wet_days = sum(1 for r in weather if (r[3] or 0) >= 0.5)
        windy = max(weather, key=lambda r: r[4] if r[4] is not None else -1)
        lines += [
            "🌤 <b>Погода</b>",
            f"Найтепліший день: {warm[0][8:]}.{warm[0][5:7]} ({warm[1]:+.0f}°)",
            f"Найхолодніша ніч: {cold[0][8:]}.{cold[0][5:7]} ({cold[2]:+.0f}°)",
            f"Опади: {rain:.1f} мм, дощових днів: {wet_days}",
            f"Найсильніший вітер: {windy[4]:.0f} м/с ({windy[0][8:]}.{windy[0][5:7]})",
            "",
        ]

    lines.append("📌 <b>Події</b>")
    for etype, title in TYPE_TITLES.items():
        if counts.get(etype):
            lines.append(f"{title}: {counts[etype]}")
    if len(lines) == 0 or lines[-1].startswith("📌"):
        lines.append("Даних за тиждень поки немає")
    return "\n".join(lines)


if __name__ == "__main__":
    print(weekly_digest())
