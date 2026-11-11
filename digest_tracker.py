# -*- coding: utf-8 -*-
"""Журнал публікацій за розкладом + тижневий підсумок.

Кожен скрипт, що виходить строго за розкладом, після УСПІШНОЇ публікації робить:

    from digest_tracker import track
    track("rates", "Курси валют і пальне", detail="НБУ 45,50 · EUR 51,08")

Історія лежить у journal/posted/<YYYY-MM-DD>.json — по одному файлу на день,
формат {ключ: {"title": ..., "ts": ..., "detail": ...}}. Ключ — стабільний
(«rates», «metals», «kalendar»…), тож повторна публікація того ж дня перезаписує
запис, а не дублює його. Файли на день не конфліктують у git між workflow.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

JOURNAL_DIR = Path(__file__).resolve().parent / "journal"
POSTED_DIR = JOURNAL_DIR / "posted"

# Стабільні назви рубрик (порядок = порядок у підсумку)
TITLES = {
    "weather": "Погода на день",
    "tomorrow": "Прогноз на 3 дні (Tomorrow.io)",
    "kalendar": "Щоденний календар",
    "horoskop": "Гороскоп дня",
    "rates": "Курси валют і пальне",
    "metals": "Курс дорогоцінних металів",
    "crypto": "Курс криптовалют",
    "trains": "Поїзди до Європи",
    "oblast": "Сумщина: прогноз на день",
    "space": "Магнітне поле Землі",
    "weather_day": "Цей день у погоді",
    "sky": "Небо над Сумами",
    "warm": "Хвилинка тепла",
    "meaning": "Погода, яка має значення",
    "weekend": "Погода на вихідні",
    "losses": "Бойові втрати",
    "legends": "Таємниці неба",
    "omens": "Забобони світу",
    "how_weather": "Як працює погода",
    "trolley": "Рух тролейбусів",
}


def track(key: str, title: str | None = None, detail: str = "", when: datetime | None = None) -> bool:
    """Записати публікацію. Ніколи не кидає помилок — журнал не має ламати пост."""
    try:
        when = when or datetime.now()
        path = POSTED_DIR / f"{when.date().isoformat()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[key] = {
            "title": title or TITLES.get(key, key),
            "ts": when.strftime("%H:%M"),
            "detail": detail[:160],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
                        encoding="utf-8")
        return True
    except Exception as e:
        print(f"track: не вдалося записати: {e}")
        return False


def _read_day(day: date) -> dict:
    path = POSTED_DIR / f"{day.isoformat()}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_week(first_day: date, last_day: date) -> dict:
    """{день: {ключ: запис}} за проміжок."""
    out, d = {}, first_day
    while d <= last_day:
        out[d.isoformat()] = _read_day(d)
        d += timedelta(days=1)
    return out


def published_days(keys: list[str] | None = None) -> int:
    """Скільки днів із журналу містять хоч одну з рубрик (для тестів/звітів)."""
    if not POSTED_DIR.is_dir():
        return 0
    n = 0
    for p in POSTED_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not keys or any(k in data for k in keys):
            n += 1
    return n


def commit_posted() -> None:
    """Зберегти journal/posted у git (лише в GitHub Actions). Ніколи не кидає помилок."""
    if os.getenv("GITHUB_ACTIONS") != "true" or not POSTED_DIR.exists():
        return
    import subprocess

    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=POSTED_DIR.parent.parent)

    try:
        git("config", "user.name", "synoptic-bot")
        git("config", "user.email", "bot@users.noreply.github.com")
        git("add", "journal/posted")
        if git("diff", "--cached", "--quiet", "--", "journal/posted").returncode == 0:
            return
        if git("commit", "-m", "update posted journal", "--", "journal/posted").returncode != 0:
            return
        for _ in range(3):
            if git("push").returncode == 0:
                return
            if git("pull", "--rebase", "--autostash").returncode != 0:
                git("rebase", "--abort")
    except Exception as e:
        print(f"track: помилка збереження: {e}")
