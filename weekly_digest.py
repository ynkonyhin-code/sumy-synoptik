"""Публикация недельного итога в канал.

    python weekly_digest.py          # отправить в канал (текст + карточка)
    python weekly_digest.py --dry    # только показать текст и собрать карточку
    python weekly_digest.py --no-card

Переменные окружения: BOT_TOKEN, CHAT_ID
"""
import os
import re
import sys
from datetime import date, timedelta

import requests

from events_db import TYPE_TITLES, _fmt_dur, _read_weather, alert_durations, kyiv_now, weekly_digest
from digest_tracker import commit_posted, track

# Хештеги поста: меняйте как нравится
TAGS = "#Суми #СумськийСиноптик #Погода #ПідсумокТижня"
CARD_PATH = os.getenv("CARD_OUT", "output/digest.png")


def _plain(html: str) -> str:
    """HTML-разметка поста -> чистый текст для карточки."""
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"</?[^>]+>", "", text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def card_data(last_day: date, days: int = 7) -> dict:
    """Данные для карточки: расписание, события, погода."""
    from events_db import JOURNAL_DIR, _count_events, _read_ts  # локально: нужен только здесь

    first_day = last_day - timedelta(days=days - 1)
    t0 = __import__("datetime").datetime.combine(first_day, __import__("datetime").time.min)
    t1 = __import__("datetime").datetime.combine(last_day + timedelta(days=1), __import__("datetime").time.min)

    stats = __import__("events_db").schedule_stats(first_day, last_day, days)
    rows = [{"title": r["title"], "days": r["days"], "expected": r.get("expected", days)}
            for r in stats["rows"] if r["days"] > 0][:8]

    events = []
    for etype, title in TYPE_TITLES.items():
        n = _count_events(etype, t0, t1)
        if not n:
            continue
        if etype == "alert":
            durs = alert_durations(t0, t1)
            value = f"{n}"
            if durs:
                value += f" · {_fmt_dur(sum(durs))}"
            title = "Повітряні тривоги"
        else:
            value = str(n)
            title = re.sub(r"^[^A-Za-zА-Яа-яЇїІіЄєҐґ]+\s*", "", title)
            title = title.replace("(Сумський район)", "").strip()
        events.append({"title": title, "value": value})

    weather_lines = []
    wx = _read_weather(first_day, last_day)
    hot = [r for r in wx if r[1] is not None]
    cold = [r for r in wx if r[2] is not None]
    if hot and cold:
        warm = max(hot, key=lambda r: r[1])
        chill = min(cold, key=lambda r: r[2])
        weather_lines.append(f"Найтепліший день: {warm[0][8:10]}.{warm[0][5:7]} ({warm[1]:+.0f}°)")
        weather_lines.append(f"Найхолодніша ніч: {chill[0][8:10]}.{chill[0][5:7]} ({chill[2]:+.0f}°)")
        rain = sum(r[3] or 0 for r in wx)
        weather_lines.append(f"Опади за тиждень: {rain:.1f} мм")

    return {
        "period": f"{first_day:%d.%m}–{last_day:%d.%m.%Y}",
        "days": days,
        "rows": rows,
        "events": events[:6],
        "weather": weather_lines,
    }


def send_photo(token: str, chat_id: str, path: str, caption: str) -> None:
    with open(path, "rb") as fh:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": fh}, timeout=60)
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Telegram: {r.text[:200]}")


def main():
    last_day = kyiv_now().date() - timedelta(days=1)
    text = weekly_digest() + "\n\n" + TAGS

    # ── карточка ──────────────────────────────────────────────────────────
    card_path = None
    if "--no-card" not in sys.argv:
        try:
            from weekly_digest_card import render_card
            card_path = render_card(card_data(last_day), CARD_PATH)
            print(f"— картка: {card_path}")
        except Exception as exc:                       # карточка не должна съесть пост
            print(f"⚠️  Картку не створено ({exc}). Публікую лише текст.", file=sys.stderr)
            print(f"::warning title=Картка підсумку не створена::{exc}")

    if "--dry" in sys.argv:
        print(text)
        return

    token, chat_id = os.environ["BOT_TOKEN"], os.environ["CHAT_ID"]

    # картинка первой — короткий подпись, полный текст отдельным сообщением
    if card_path and os.path.exists(card_path):
        plain = _plain(text)
        caption = "📊 <b>Підсумок тижня</b>\n"
        m = re.search(r"\((\d{2}\.\d{2}–\d{2}\.\d{2})\)", text)
        if m:
            caption += f"<i>{m.group(1)}</i>\n"
        caption += "Що виходило за розкладом, події та погода — у тексті нижче ⬇️"
        try:
            send_photo(token, chat_id, card_path, caption[:1024])
        except Exception as exc:
            print(f"⚠️  Фото не надіслано ({exc}). Публікую лише текст.", file=sys.stderr)
            print(f"::warning title=Фото підсумку не надіслано::{exc}")

    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30)
    r.raise_for_status()

    track("digest", detail=f"{last_day:%d.%m.%Y}")
    commit_posted()
    print("✅ Опубліковано підсумок тижня")


if __name__ == "__main__":
    main()
