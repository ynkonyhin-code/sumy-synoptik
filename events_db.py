"""Журнал подій каналу «Сумський синоптик» + тижневий підсумок.

Як це влаштовано: папка journal/ з маленькими JSON-файлами,
по одному файлу на подію  (journal/events/<тип>/<ключ>.json)
і по одному на день погоди (journal/weather/<дата>.json).
Різні скрипти ніколи не правлять один і той самий файл, тому в git не буває конфліктів.

Підключення до будь-якого скрипта (вгорі файлу):
    try:
        from events_db import commit_journal, safe_log
    except Exception:
        def safe_log(*a, **k): return False
        def commit_journal(): return None
Далі в коді:
    safe_log("water", "короткий текст", key="water-12345")   # одразу після УСПІШНОЇ публікації
    commit_journal()                                          # один раз наприкінці роботи скрипта
"""
import hashlib
import json
import os
import re
import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JOURNAL_DIR = Path(__file__).resolve().parent / "journal"
TZ = ZoneInfo("Europe/Kyiv")

# тип події -> рядок у підсумку (порядок = порядок у пості)
TYPE_TITLES = {
    "alert": "🚨 Повітряних тривог (Сумський район)",
    "water": "🚰 Відключень та аварій на водоканалі",
    "power": "💡 Оновлень графіків світла",
    "gas": "🔥 Повідомлень про газопостачання",
    "dsns": "🚒 Повідомлень ДСНС",
    "space": "🧲 Магнітних бур",
}


def kyiv_now() -> datetime:
    """Поточний київський час (сервер GitHub живе за UTC)."""
    return datetime.now(TZ).replace(tzinfo=None)


def to_kyiv(dt: datetime) -> datetime:
    """Будь-який час -> київський без таймзони. «Голий» час вважаємо вже київським."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(TZ).replace(tzinfo=None)


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)[:150]


def log_event(etype: str, text: str, key: str | None = None, when: datetime | None = None) -> bool:
    """Записати подію. Повертає False, якщо подія з таким key уже є (дубль)."""
    when = to_kyiv(when) if when else kyiv_now()
    if not key:
        key = when.strftime("%Y%m%dT%H%M%S") + "-" + hashlib.md5(text.encode()).hexdigest()[:6]
    path = JOURNAL_DIR / "events" / _safe_name(etype) / f"{_safe_name(key)}.json"
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ts": when.isoformat(timespec="seconds"), "text": text},
                               ensure_ascii=False), encoding="utf-8")
    return True


def safe_log(*args, **kwargs) -> bool:
    """Те саме, що log_event, але НІКОЛИ не кидає помилку: журнал не повинен ламати публікацію."""
    try:
        return log_event(*args, **kwargs)
    except Exception as e:
        print(f"journal: не вдалося записати подію: {e}")
        return False


def save_daily_weather(day: str, tmax, tmin, precip, wind_max):
    """day='2026-10-15'. Повторний виклик перезапише день."""
    path = JOURNAL_DIR / "weather" / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([tmax, tmin, precip, wind_max]), encoding="utf-8")


def commit_journal() -> None:
    """Зберегти папку journal у git (лише в GitHub Actions). Ніколи не кидає помилок."""
    if os.getenv("GITHUB_ACTIONS") != "true" or not JOURNAL_DIR.exists():
        return

    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=JOURNAL_DIR.parent)

    try:
        git("config", "user.name", "synoptic-bot")
        git("config", "user.email", "bot@users.noreply.github.com")
        git("add", "journal")
        if git("diff", "--cached", "--quiet", "--", "journal").returncode == 0:
            return                                   # нових записів немає
        r = git("commit", "-m", "update journal", "--", "journal")
        if r.returncode != 0:
            print(f"journal: commit не вдався: {r.stderr.strip()[:200]}")
            return
        for _ in range(3):
            if git("push").returncode == 0:
                return
            if git("pull", "--rebase", "--autostash").returncode != 0:
                git("rebase", "--abort")
        print("journal: не вдалося відправити журнал у git "
              "(перевірте, що в workflow є permissions: contents: write)")
    except Exception as e:
        print(f"journal: помилка збереження: {e}")


# ------------------------------------------------------------------ тижневий підсумок
def _dm(day: str) -> str:
    return f"{day[8:10]}.{day[5:7]}"


def _count_events(etype: str, t0: datetime, t1: datetime) -> int:
    folder = JOURNAL_DIR / "events" / etype
    n = 0
    if folder.is_dir():
        for p in folder.glob("*.json"):
            try:
                ts = datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["ts"])
            except Exception:
                continue
            if t0 <= ts < t1:
                n += 1
    return n


def _read_weather(first_day: date, last_day: date) -> list:
    rows, d = [], first_day
    while d <= last_day:
        p = JOURNAL_DIR / "weather" / f"{d.isoformat()}.json"
        if p.exists():
            try:
                tmax, tmin, precip, wind = json.loads(p.read_text(encoding="utf-8"))
                rows.append((d.isoformat(), tmax, tmin, precip, wind))
            except Exception:
                pass
        d += timedelta(days=1)
    return rows


def _read_ts(etype: str, lo: datetime, hi: datetime) -> list:
    """Час усіх подій типу etype у проміжку [lo, hi)."""
    folder = JOURNAL_DIR / "events" / etype
    out = []
    if folder.is_dir():
        for p in folder.glob("*.json"):
            try:
                ts = datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["ts"])
            except Exception:
                continue
            if lo <= ts < hi:
                out.append(ts)
    return out


def alert_durations(t0: datetime, t1: datetime) -> list:
    """Тривалості (в секундах) тривог у Сумському районі всередині [t0, t1).

    Складаємо пари «початок -> відбій». Тривога, що почалась до t0 або триває
    після t1, обрізається по межах тижня. Відбій без початку ігноруємо.
    """
    lo = t0 - timedelta(days=3)
    points = ([(ts, "s") for ts in _read_ts("alert", lo, t1)]
              + [(ts, "e") for ts in _read_ts("alert_end", lo, t1)])
    points.sort()
    spans, begin = [], None
    for ts, kind in points:
        if kind == "s":
            if begin is None:
                begin = ts
        elif begin is not None:
            spans.append((begin, ts))
            begin = None
    if begin is not None:                       # тривога ще не закінчилась
        spans.append((begin, min(t1, kyiv_now())))
    result = []
    for b, e in spans:
        b, e = max(b, t0), min(e, t1)
        if e > b:
            result.append((e - b).total_seconds())
    return result


def _fmt_dur(sec: float) -> str:
    minutes = round(sec / 60)
    h, m = divmod(minutes, 60)
    return f"{h} год {m:02d} хв" if h else f"{m} хв"


def weekly_digest(last_day: date | None = None, days: int = 7) -> str:
    """Підсумок за `days` повних діб, що закінчуються last_day (за замовчуванням вчора)."""
    last_day = last_day or (kyiv_now().date() - timedelta(days=1))
    first_day = last_day - timedelta(days=days - 1)
    t0 = datetime.combine(first_day, time.min)
    t1 = datetime.combine(last_day + timedelta(days=1), time.min)

    counts = {t: _count_events(t, t0, t1) for t in TYPE_TITLES}
    weather = _read_weather(first_day, last_day)

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
    durations = alert_durations(t0, t1)
    if durations:
        line = (f"⏱ Загалом у тривозі: {_fmt_dur(sum(durations))} "
                f"(найдовша — {_fmt_dur(max(durations))})")
        pos = 1 if counts.get("alert") else 0   # одразу під рядком про кількість тривог
        ev.insert(pos, line)
    if ev:
        lines += ["📌 <b>Події</b>"] + ev + [""]

    if len(lines) <= 2:
        lines.append("За цей тиждень даних поки немає.")
    return "\n".join(lines).rstrip()


if __name__ == "__main__":
    print(weekly_digest())
