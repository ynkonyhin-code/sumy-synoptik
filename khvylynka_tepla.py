from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from khvylynka_tepla_sources import validate_sources

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "khvylynka_tepla.json"
HISTORY_PATH = BASE_DIR / "khvylynka_tepla_history.json"
KYIV = ZoneInfo("Europe/Kyiv")
TELEGRAM_LIMIT = 3500

MONTHS_UK = (
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
)


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default.copy()
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: очікувався JSON-об'єкт")
    return value


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)


def date_uk(date: datetime) -> str:
    return f"{date.day} {MONTHS_UK[date.month - 1]} {date.year} року"


def select_entry(entries: list[dict], history: dict, today: str) -> dict:
    if not entries:
        raise ValueError("У JSON-бібліотеці немає придатних текстів")

    published = history.get("published", [])
    recent_ids = {
        item.get("entry_id")
        for item in published[-14:]
        if isinstance(item, dict) and item.get("date") != today
    }
    candidates = [entry for entry in entries if entry["id"] not in recent_ids]
    if not candidates:
        candidates = entries

    # Выбор на один день стабилен даже при повторном запуске.
    rng = random.Random(today)
    return rng.choice(candidates)


def compose_post(entry: dict, now: datetime, max_length: int) -> str:
    lines = [
        "🌤️ Хвилинка тепла від Сумського синоптика",
        f"📅 {date_uk(now)}",
        "",
        entry["text"].strip(),
        "",
        entry.get("closing", "Нехай сьогодні знайдеться привід усміхнутися 💛"),
    ]

    sources = entry.get("sources", [])
    if sources:
        lines.extend(["", "🔎 Джерела:"])
        lines.extend(source["url"] for source in sources[:2])

    post = "\n".join(lines).strip()
    if len(post) > max_length:
        raise ValueError(
            f"Текст ({len(post)} символів) довший за дозволений ліміт "
            f"({max_length})"
        )
    return post


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API відхилив повідомлення: {payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Публікація короткого теплого допису")
    parser.add_argument(
        "--test",
        action="store_true",
        help="показати допис у консолі, не надсилати його",
    )
    parser.add_argument(
        "--scheduled",
        action="store_true",
        help="перевірити локальний час для запуску за розкладом",
    )
    args = parser.parse_args()

    try:
        config = load_json(CONFIG_PATH, {})
        history = load_json(HISTORY_PATH, {"published": []})
        now = datetime.now(KYIV)
        today = now.date().isoformat()

        # Workflow має два UTC-розклади для сезонного переходу.
        if args.scheduled and now.hour != 10:
            print(f"Пропуск: зараз у Києві {now:%H:%M}, не година публікації.")
            return 0

        published = history.get("published", [])
        if any(item.get("date") == today for item in published if isinstance(item, dict)):
            print(f"Публікацію за {today} вже зареєстровано; повтор не надсилаю.")
            return 0

        entries = config.get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("Поле entries у JSON має бути списком")

        valid_entries = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id") or not entry.get("text"):
                continue
            if not validate_sources(entry):
                print(f"Пропуск запису з некоректними джерелами: {entry.get('id')}")
                continue
            valid_entries.append(entry)

        entry = select_entry(valid_entries, history, today)
        message = compose_post(
            entry,
            now,
            int(config.get("max_message_length", TELEGRAM_LIMIT)),
        )

        if args.test or os.getenv("TEST_MODE", "").lower() in {"1", "true", "yes"}:
            print("ТЕСТОВИЙ РЕЖИМ — повідомлення не надіслано:\n")
            print(message)
            return 0

        token = os.getenv("BOT_TOKEN", "").strip()
        chat_id = os.getenv("CHAT_ID", "").strip()
        if not token or not chat_id:
            raise RuntimeError("Потрібні змінні середовища BOT_TOKEN і CHAT_ID")

        send_telegram_message(token, chat_id, message)

        # Записуем дату только после успешного ответа Telegram.
        published.append({
            "date": today,
            "entry_id": entry["id"],
            "sent_at": now.isoformat(),
        })
        history["published"] = published[-120:]
        save_json(HISTORY_PATH, history)
        print(f"Публікацію за {today} надіслано.")
        return 0

    except (OSError, ValueError, requests.RequestException, RuntimeError) as error:
        print(f"Помилка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
