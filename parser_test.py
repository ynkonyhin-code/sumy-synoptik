
import json
import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = (
    "https://www.soe.com.ua/consumers/shutdowns"
    "?tab=hourly-schedules"
)

HEADERS = {
    "User-Agent": "SumySynoptik/1.0 (schedule parser)"
}

QUEUE_RE = re.compile(r"Черга\s*(\d+\.\d+)", re.IGNORECASE)

INTERVAL_RE = re.compile(
    r"(?<!\d)(\d{1,2}:\d{2})\s*[–—-]\s*"
    r"(\d{1,2}:\d{2})(?!\d)"
)

UPDATED_RE = re.compile(
    r"Оновлено дані по відключенням на:\s*"
    r"(\d{2}\.\d{2}\.\d{4},?\s*\d{2}:\d{2})",
    re.IGNORECASE,
)


def main():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    updated = UPDATED_RE.search(text)
    queues = list(QUEUE_RE.finditer(text))

    if not updated:
        raise RuntimeError(
            "Не найдена дата обновления. "
            "Структура страницы могла измениться."
        )

    if len(queues) < 6:
        raise RuntimeError(
            f"Найдено слишком мало очередей: {len(queues)}. "
            "Проверь HTML страницы вручную."
        )

    result = {
        "source": URL,
        "checked_at_utc": datetime.utcnow().isoformat() + "Z",
        "source_updated": updated.group(1),
        "queues": {},
    }

    for i, match in enumerate(queues):
        queue = match.group(1)
        start = match.end()

        end = (
            queues[i + 1].start()
            if i + 1 < len(queues)
            else len(text)
        )

        section = text[start:end]

        intervals = [
            {
                "from": begin,
                "to": finish,
            }
            for begin, finish in INTERVAL_RE.findall(section)
        ]

        result["queues"][queue] = intervals

    if not any(result["queues"].values()):
        raise RuntimeError(
            "Очереди найдены, но интервалы не извлечены."
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        sys.exit(1)
