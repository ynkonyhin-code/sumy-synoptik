
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL = (
    "https://www.soe.com.ua/consumers/shutdowns"
    "?tab=hourly-schedules"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SumySynoptik/1.0)"
}


def main():
    print("Проверяем официальный сайт:", URL)

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30,
    )

    print("HTTP status:", response.status_code)
    print("Final URL:", response.url)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("HTML length:", len(response.text))

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    page_title = soup.title.get_text(" ", strip=True) if soup.title else "(нет title)"
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    print("\n=== TITLE ===")
    print(page_title)

    print("\n=== SEARCH FOR UPDATE TEXT ===")
    for word in ("Оновлено", "відключенням", "Черга", "погодинних"):
        positions = [
            m.start()
            for m in re.finditer(re.escape(word), text, re.IGNORECASE)
        ]
        print(f"{word}: {len(positions)} совпадений")
        for pos in positions[:3]:
            print("  ...", text[max(0, pos - 100):pos + 250], "...")

    print("\n=== FIRST 4000 CHARACTERS OF PAGE TEXT ===")
    print(text[:4000])

    print("\n=== HTML PREVIEW ===")
    print(response.text[:1500])

    print("\nChecked at UTC:", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ОШИБКА: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
