import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from Koshtovnosti_card import create_card


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

KYIV = ZoneInfo("Europe/Kyiv")

# API НБУ. Курсы металлов в ответе указываются за тройскую унцию.
NBU_URL = "https://bank.gov.ua/NBU_Exchange/exchange_site"
GRAMS_PER_TROY_OUNCE = 31.10348

METALS = {
    "XAU": "Золото",
    "XAG": "Срібло",
    "XPT": "Платина",
    "XPD": "Паладій",
}

# Страница Prostobank со сравнением банковского золота за 1 грамм.
PROSTOBANK_GOLD_URL = (
    "https://www.prostobank.ua/spravochniki/bankovskie_metally/1/1"
)

# Ищем эти банки в таблице Prostobank.
BANKS_TO_SHOW = {
    "приватбанк": "ПриватБанк",
    "коминбанк": "КОМІНБАНК",
    "индустриалбанк": "Індустріалбанк",
    "мтб банк": "МТБ БАНК",
}

# Проба показывает долю чистого металла в изделии.
GOLD_ASSAYS = {
    375: "375",
    585: "585",
    750: "750",
    999: "999",
}


def parse_number(value):
    """Преобразует число с точкой или запятой в float."""
    if value is None:
        return None

    cleaned = str(value).replace("\xa0", " ").strip()
    cleaned = cleaned.replace(" ", "").replace(",", ".")

    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def fetch_nbu_rates():
    """Получает курсы НБУ и переводит их в гривны за грамм."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 KoshtovnostiTelegramBot/1.0"
    })

    today = datetime.now(KYIV).date()

    # На выходных и праздниках пробуем взять последний доступный курс.
    for days_back in range(8):
        requested_date = today - timedelta(days=days_back)
        date_string = requested_date.strftime("%Y%m%d")

        rates = {}
        rate_date = None

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

            rows = response.json()
            if not isinstance(rows, list) or not rows:
                continue

            row = rows[0]
            raw_rate = row.get("rate")

            if raw_rate is None:
                logging.warning(
                    "У відповіді НБУ немає курсу для %s: %s",
                    metal_code,
                    row,
                )
                continue

            try:
                rate_per_ounce = float(raw_rate)
            except (TypeError, ValueError):
                logging.warning(
                    "Не вдалося прочитати курс НБУ для %s: %r",
                    metal_code,
                    raw_rate,
                )
                continue

            rates[metal_code] = rate_per_ounce / GRAMS_PER_TROY_OUNCE
            rate_date = (
                row.get("exchangedate")
                or row.get("date")
                or requested_date.strftime("%d.%m.%Y")
            )

        # Не переходим к старым датам, если на эту дату уже получили курсы.
        if rates:
            missing = [code for code in METALS if code not in rates]
            if missing:
                logging.warning(
                    "НБУ не повернув курси для металів: %s",
                    ", ".join(missing),
                )

            return rates, str(rate_date)

    raise RuntimeError(
        "Не вдалося отримати курси металів НБУ за останні 8 днів."
    )


def fetch_prostobank_gold_rates():
    """
    Загружает таблицу Prostobank и возвращает курсы покупки/продажи
    золота за грамм для выбранных банков.
    """
    response = requests.get(
        PROSTOBANK_GOLD_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/130 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    found = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cell_texts = [
                cell.get_text(" ", strip=True)
                for cell in cells
            ]
            joined_text = " ".join(cell_texts).lower()

            matched_bank = None
            for search_name, display_name in BANKS_TO_SHOW.items():
                if search_name in joined_text:
                    matched_bank = display_name
                    break

            if not matched_bank:
                continue

            # Собираем числовые значения из ячеек после названия банка.
            # На страницах Prostobank обычно следуют:
            # покупка за грамм, покупка за слиток,
            # продажа за грамм, продажа за слиток.
            numbers = []
            for cell_text in cell_texts:
                number = parse_number(cell_text)
                if number is not None:
                    numbers.append(number)

            # Если таблица начинается с номера строки, убираем его.
            if numbers and numbers[0] in (1, 2, 3, 4, 5):
                numbers = numbers[1:]

            if len(numbers) >= 4:
                buy_per_gram = numbers[0]
                sell_per_gram = numbers[2]
            elif len(numbers) >= 2:
                buy_per_gram = numbers[0]
                sell_per_gram = numbers[1]
            else:
                continue

            # Отсекаем очевидно неподходящие или пустые значения.
            if buy_per_gram <= 0 or sell_per_gram <= 0:
                continue

            found[matched_bank] = {
                "buy": buy_per_gram,
                "sell": sell_per_gram,
            }

    return found


def format_price(value):
    """Форматирует цену украинским способом: 1 234,56."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def build_caption(nbu_rates, rate_date, bank_rates):
    """Создаёт текст поста на украинском языке."""
    lines = [
        "✨ <b>КОШТОВНОСТІ • ЩОДЕННИЙ ОГЛЯД</b>",
        f"📅 Дата курсу НБУ: <b>{rate_date}</b>",
        "",
        "🏛 <b>Банківські метали за курсом НБУ</b>",
    ]

    for code, name in METALS.items():
        if code in nbu_rates:
            lines.append(
                f"▫️ {name}: <b>{format_price(nbu_rates[code])} грн/г</b>"
            )

    lines.extend([
        "",
        "🏦 <b>Золото в банках, грн/г</b>",
    ])

    if bank_rates:
        for bank_name in BANKS_TO_SHOW.values():
            quote = bank_rates.get(bank_name)
            if quote:
                lines.append(
                    f"▫️ {bank_name}: купівля "
                    f"<b>{format_price(quote['buy'])}</b> · продаж "
                    f"<b>{format_price(quote['sell'])}</b>"
                )
            else:
                lines.append(f"▫️ {bank_name}: дані не знайдено")
    else:
        lines.append("Дані Prostobank наразі недоступні.")

    lines.extend([
        "",
        "💍 <b>Розрахункова вартість золота за пробою</b>",
    ])

    gold_rate = nbu_rates.get("XAU")
    if gold_rate:
        for assay, assay_label in GOLD_ASSAYS.items():
            estimated_value = gold_rate * assay / 1000
            lines.append(
                f"▫️ Проба {assay_label}: "
                f"<b>{format_price(estimated_value)} грн/г</b>"
            )
    else:
        lines.append("Немає курсу золота НБУ для розрахунку.")

    lines.extend([
        "",
        "🧮 Формула: курс НБУ за 1 г × проба ÷ 1000.",
        "⚠️ Це вартість чистого металу у виробі, а не гарантований тариф ломбарду. "
        "Фактичну суму визначає ломбард після оцінювання.",
        "",
        "📊 Дані банків — Prostobank. Банківські курси стосуються злитків "
        "і можуть відрізнятися від умов викупу прикрас.",
        "",
        "#СумськийСиноптик #Коштовності #БанківськіМетали "
        "#Золото #Срібло #Платина #Паладій #Ломбард #КурсНБУ #Україна",
    ])

    return "\n".join(lines)


def send_to_telegram(image_path, caption):
    """Отправляет изображение с подписью в Telegram."""
    token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    if not token:
        raise RuntimeError("Не задано GitHub Secret BOT_TOKEN.")

    if not chat_id:
        raise RuntimeError("Не задано GitHub Secret CHAT_ID.")

    # Telegram ограничивает подпись к изображению 1024 символами.
    if len(caption) > 1024:
        raise RuntimeError(
            f"Підпис задовгий для фото в Telegram: {len(caption)} символів."
        )

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
    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(f"Помилка Telegram API: {result}")

    logging.info("Публікацію успішно надіслано в Telegram.")


def main():
    logging.info("Отримую курси НБУ...")
    nbu_rates, rate_date = fetch_nbu_rates()

    logging.info("Отримую курси банків із Prostobank...")
    try:
        bank_rates = fetch_prostobank_gold_rates()
        if not bank_rates:
            logging.warning(
                "Не вдалося розібрати банківські курси на Prostobank."
            )
    except requests.RequestException:
        logging.exception(
            "Не вдалося завантажити дані Prostobank. "
            "Публікую курс НБУ та розрахунок за пробами."
        )
        bank_rates = {}

    logging.info("Створюю картку...")
    image_path = create_card(nbu_rates, rate_date)

    logging.info("Формую текст і надсилаю пост...")
    caption = build_caption(nbu_rates, rate_date, bank_rates)
    send_to_telegram(image_path, caption)


if __name__ == "__main__":
    main()
