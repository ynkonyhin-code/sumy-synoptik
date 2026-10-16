import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from Koshtovnosti_card import create_card


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

KYIV = ZoneInfo("Europe/Kyiv")
NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/bankmetals"

METALS = {
    "XAU": "Золото",
    "XAG": "Срібло",
    "XPT": "Платина",
    "XPD": "Паладій",
}


def fetch_nbu_rates():
    """Пробует получить курс НБУ за сегодня; при отсутствии данных — за предыдущие дни."""
    session = requests.Session()
    session.headers.update({"User-Agent": "KoshtovnostiTelegramBot/1.0"})

    today = datetime.now(KYIV).date()

    for days_back in range(0, 8):
        requested_date = today - timedelta(days=days_back)
        params = {
            "date": requested_date.strftime("%Y%m%d"),
            "json": "",
        }

        response = session.get(NBU_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list) or not payload:
            continue

        rates = {}
        actual_date = None

        for row in payload:
            code = str(
                row.get("code")
                or row.get("cc")
                or row.get("metal")
                or row.get("r030")
                or ""
            ).upper()

            # В ответах НБУ код металла может называться иначе.
            # Сопоставляем также по украинскому/английскому названию.
            description = str(
                row.get("txt")
                or row.get("name")
                or row.get("metal_name")
                or ""
            ).lower()

            if code not in METALS:
                for metal_code, metal_name in METALS.items():
                    if metal_name.lower() in description:
                        code = metal_code
                        break

            if code not in METALS:
                continue

            raw_rate = (
                row.get("rate")
                or row.get("value")
                or row.get("rate_per_gram")
            )
            if raw_rate is None:
                continue

            try:
                value = float(raw_rate)
            except (TypeError, ValueError):
                continue

            # НБУ может возвращать цену за единицу металла, а не за грамм.
            # Если API указывает unit/units, нормализуем к цене за 1 г.
            units = row.get("units") or row.get("unit") or 1
            try:
                units = float(units)
            except (TypeError, ValueError):
                units = 1

            rates[code] = value / units
            actual_date = (
                row.get("date")
                or row.get("exchangedate")
                or row.get("exchangeDate")
                or requested_date.strftime("%d.%m.%Y")
            )

        if rates:
            # Не публикуем частичный набор как полный: оставляем только
            # реально полученные металлы, а в посте укажем их наличие.
            return rates, str(actual_date)

    raise RuntimeError("НБУ не повернув курси банківських металів за останні 8 днів.")


def build_caption(rates, rate_date):
    lines = [
        "✨ <b>КОШТОВНОСТІ: офіційний курс НБУ</b>",
        f"📅 Дата курсу: <b>{rate_date}</b>",
        "",
    ]

    for code, title in METALS.items():
        if code in rates:
            lines.append(f"▫️ {title}: <b>{rates[code]:,.2f} грн/г</b>".replace(",", " "))

    lines.extend([
        "",
        "🏦 <b>Курси банків</b>",
        "Дані банків поки не підключені.",
        "",
        "💍 <b>Приймання виробів як брухту в ломбардах</b>",
        "Тарифи залежать від ломбарду, проби та стану виробу; перевірені локальні ціни поки не підключені.",
        "",
        "ℹ️ Курс НБУ — офіційний орієнтир для банківських металів, а не гарантована ціна викупу ювелірних виробів.",
        "",
        "#СумськийСиноптик #Коштовності #БанківськіМетали #Золото #Срібло #Платина #Паладій #КурсНБУ #Україна",
    ])
    return "\n".join(lines)


def send_to_telegram(image_path, caption):
    token = os.environ["BOT_TOKEN"]
    chat_id = os.environ["CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(image_path, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={"photo": photo},
            timeout=60,
        )

    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")

    logging.info("Публікацію успішно надіслано.")


def main():
    rates, rate_date = fetch_nbu_rates()
    image_path = create_card(rates, rate_date)
    caption = build_caption(rates, rate_date)
    send_to_telegram(image_path, caption)


if __name__ == "__main__":
    main()
