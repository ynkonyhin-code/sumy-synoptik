# -*- coding: utf-8 -*-
"""Вікно публікації для постів із фіксованим часом.

GitHub Actions виконує schedule-cron із затримкою — від хвилин до кількох годин
(у листопаді 2026 запуск «Щоденного календаря» приходив о 15:46–17:56 замість 10:05).
Тому перевірка «зараз рівно POST_HOUR» відкидала майже всі запуски.

Тут публікація дозволена в будь-який момент вікна [POST_HOUR, POST_HOUR + WINDOW_HOURS)
за київським часом. Від дублів у межах одного дня захищає різна година в cron-слотах
(літній/зимовий час) — а якщо вона не спрацює, скрипт усе одно має власний стан
або перевірку «вже опубліковано».

    from publish_window import in_window, window_note
    if not force and not in_window(POST_HOUR):
        print(window_note(POST_HOUR)); return 0
"""
from __future__ import annotations

from datetime import datetime

WINDOW_HOURS = 3          # скільки годин після POST_HOUR ще публікуємо


def in_window(post_hour: int, hours: int = WINDOW_HOURS, now: datetime | None = None) -> bool:
    """Чи зараз час публікації: [post_hour, post_hour + hours) за київським часом."""
    now = now or datetime.now()
    return post_hour <= now.hour < post_hour + hours


def window_note(post_hour: int, hours: int = WINDOW_HOURS, now: datetime | None = None) -> str:
    now = now or datetime.now()
    return (f"Зараз {now:%H:%M} за Києвом — поза вікном публікації "
            f"({post_hour}:00–{post_hour + hours}:00). Пропускаю.")
