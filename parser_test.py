
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
}

KEYWORDS = (
    "shutdown", "hourly", "schedule", "outage",
    "відключ", "погодин", "черга", "графік",
    "api", "graphql", "__next_f", "__next_data"
)


def main():
    print("Загрузка:", URL)

    response = requests.get(URL, headers=HEADERS, timeout=30)
    print("HTTP:", response.status_code)
    print("HTML length:", len(response.text))
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    print("\n=== TITLE ===")
    print(soup.title.get_text(" ", strip=True) if soup.title else "Нет title")

    print("\n=== SCRIPT FILES ===")
    scripts = soup.find_all("script")
    print("Всего script-тегов:", len(scripts))

    for script in scripts:
        src = script.get("src")
        if src:
            print("JS:", src)

    print("\n=== KEYWORDS IN RAW HTML ===")
    lower_html = html.lower()

    for keyword in KEYWORDS:
        positions = [
            m.start()
            for m in re.finditer(re.escape(keyword.lower()), lower_html)
        ]
        print(f"\n{keyword}: {len(positions)} совпадений")

        for pos in positions[:2]:
            excerpt = html[max(0, pos - 180):pos + 350]
            print(re.sub(r"\s+", " ", excerpt))

    print("\n=== INLINE SCRIPT PREVIEW ===")
    shown = 0

    for script in scripts:
        if script.get("src"):
            continue

        content = script.get_text(" ", strip=False).strip()
        if content:
            print("\n--- Inline script ---")
            print(content[:1800])
            shown += 1

        if shown >= 5:
            break

    print("\n=== LINKS RELATED TO SCHEDULES ===")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        label = link.get_text(" ", strip=True)
        combined = (href + " " + label).lower()

        if any(word in combined for word in KEYWORDS):
            print(f"{label[:100]} -> {href}")

    print("\nПроверка завершена:", datetime.now(timezone.utc).isoformat())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ОШИБКА: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
