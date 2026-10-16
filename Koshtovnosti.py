import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from Koshtovnosti_card import create_card


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

KYIV = ZoneInfo("Europe/Kyiv")

# API курсов НБУ
NBU_URL = "https://bank.gov.ua/NBU_Exchange/exchange_site"

# Коды банковских металлов
METALS = {
    "XAU": "Золото",
    "XAG": "Срібло",
    "XPT": "Платина",
    "XPD": "Паладій",
}

# В API НБУ курс банковских металлов указан за тройскую унцию.
GRAMS_PER_TROY_OUNCE = 31.10348


def fetch_nbu_rates():
    """Получает курсы НБУ и переводит их в гривны за грамм."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "KoshtovnostiTelegramBot/1.0"
    })

    today = datetime.now(KYIV).date()

    # Если сегодня выходной или данных ещё нет, проверяем предыдущие дни.
    for days_back in range(8):
        requested_date = today - timedelta(days=days_back)
        date_string = requested_date.strftime("%Y%m%d")

        rates = {}
        actual_date = None

        for metal_code in METALS:
            params = {
                "start": date_string,
                "end": date_string,
                "valcode": metal_code,
                "sort": "exchangedate",
                "order": "desc",
                "json": "",
            }

            response = session.get(
                NBU_URL,
                params=params,
                timeout=30,
            )
            response.raise_for_status()

            try:
                rows = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    f"НБУ повернув відповідь не у форматі JSON "
                    f"для металу {metal_code}."
                ) from exc

            if not isinstance(rows, list) or not rows:
                logging.info(
                    "НБУ не повернув даних для %s за %s",
                    metal_code,
                    date_string,
                )
                continue

            row = rows[0]

            # В API НБУ курс обычно находится в поле rate.
            raw_rate = row.get("rate")
            if raw_rate is None:
                logging.warning(
                    "У відповіді НБУ немає поля rate для %s: %s",
                    metal_code,
                    row,
                )
                continue

            try:
                rate_per_troy_ounce = float(raw_rate)
            except (TypeError, ValueError):
                logging.warning(
                    "Не вдалося прочитати курс %s: %r",
                    metal_code,
                    raw_rate,
                )
                continue

            # Переводим гривны за тройскую унцию в гривны за грамм.
            rates[metal_code] = rate_per_troy_ounce / GRAMS_PER_TROY_OUNCE

            actual_date = (
                row.get("exchangedate")
                or row.get("date")
                or requested_date.strftime("%d.%m.%Y")
            )

        # Не отправляем публикацию, если не получили ни одного курса.
        if rates:
            if len(rates) < len(METALS):
                missing = [
                    METALS[code]
                    for code in METALS
                    if code not in rates
                ]
                logging.warning(
                    "Неповний набір курсів НБУ. Відсутні: %s",
                    ", ".join(missing),
                )

            return rates, str(actual_date)

    raise RuntimeError(
        "Не вдалося отримати курси банківських металів НБУ "
        "за останні 8 днів."
    )


def format_price(value):
    """Форматирует число с запятой в качестве десятичного разделителя."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def build_caption(rates, rate_date):
    """Создаёт текст публикации на украинском языке."""
    lines = [
        "✨ <b>КОШТОВНОСТІ: офіційний курс НБУ</b>",
        f"📅 Дата курсу: <b>{rate_date}</b>",
        "",
    ]

    for code, name in METALS.items():
        if code in rates:
            lines.append(
                f"▫️ {name}: <b>{format_price(rates[code])} грн/г</b>"
            )

    missing = [
        name
        for code, name in METALS.items()
        if code not in rates
    ]

    if missing:
        lines.extend([
            "",
            "⚠️ НБУ не надав дані для: " + ", ".join(missing) + ".",
        ])

    lines.extend([
        "",
        "🏦 <b>Курси банків</b>",
        "Дані банків поки не підключені.",
        "",
        "💍 <b>Приймання виробів як брухту в ломбардах</b>",
        "Перевірені тарифи окремих ломбардів поки не підключені.",
        "",
        "ℹ️ Курс НБУ — офіційний орієнтир для банківських металів, "
        "а не гарантована ціна викупу ювелірних виробів.",
        "",
        "#СумськийСиноптик #Коштовності #БанківськіМетали "
        "#Золото #Срібло #Платина #Паладій #КурсНБУ #Україна",
    ])

    return "\n".join(lines)


def send_to_telegram(image_path, caption):
    """Отправляет карточку и подпись в Telegram."""
    token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    if not token:
        raise RuntimeError("Не задано GitHub Secret BOT_TOKEN.")

    if not chat_id:
        raise RuntimeError("Не задано GitHub Secret CHAT_ID.")

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    with open(image_path, "rb") as photo:
        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={
                "photo": (
                    os.path.basename(image_path),
                    photo,
                    "image/png",
                )
            },
            timeout=60,
        )

    response.raise_for_status()

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Telegram повернув відповідь не у форматі JSON."
        ) from exc

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API не прийняв публікацію: {result}"
        )

    logging.info("Публікацію успішно надіслано в Telegram.")


def main():
    logging.info("Отримую курси банківських металів НБУ...")
    rates, rate_date = fetch_nbu_rates()

    logging.info("Створюю картку...")
    image_path = create_card(rates, rate_date)

    logging.info("Надсилаю публікацію в Telegram...")
    caption = build_caption(rates, rate_date)
    send_to_telegram(image_path, caption)


if __name__ == "__main__":
    main()
