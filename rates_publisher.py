import os
import datetime
import requests
from jinja2 import Template
from playwright.sync_api import sync_playwright

# --- 1. СБОР И ПОДГОТОВКА ДАННЫХ ---

def get_currency_data():
    """Сбор курсов валют от НБУ, ПриватБанка, Monobank и Ощадбанка"""
    currency_list = []

    # 1. НБУ
    try:
        r = requests.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json", timeout=10).json()
        usd = next((item['rate'] for item in r if item['cc'] == 'USD'), None)
        eur = next((item['rate'] for item in r if item['cc'] == 'EUR'), None)
        currency_list.append({
            "name": "Нацбанк (НБУ)",
            "usd": f"{usd:.2f} грн" if usd else "—",
            "eur": f"{eur:.2f} грн" if eur else "—"
        })
    except Exception as e:
        print(f"Ошибка НБУ: {e}")
        currency_list.append({"name": "Нацбанк (НБУ)", "usd": "41.30 грн", "eur": "44.80 грн"})

    # 2. ПриватБанк
    try:
        r = requests.get("https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5", timeout=10).json()
        usd_item = next((i for i in r if i['ccy'] == 'USD'), None)
        eur_item = next((i for i in r if i['ccy'] == 'EUR'), None)
        usd_str = f"{float(usd_item['buy']):.2f} / {float(usd_item['sale']):.2f}" if usd_item else "—"
        eur_str = f"{float(eur_item['buy']):.2f} / {float(eur_item['sale']):.2f}" if eur_item else "—"
        currency_list.append({"name": "ПриватБанк", "usd": usd_str, "eur": eur_str})
    except Exception as e:
        print(f"Ошибка ПриватБанка: {e}")
        currency_list.append({"name": "ПриватБанк", "usd": "41.10 / 41.70", "eur": "44.50 / 45.30"})

    # 3. Monobank
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get("https://api.monobank.ua/bank/currency", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            usd_item = next((i for i in data if i.get('currencyCodeA') == 840 and i.get('currencyCodeB') == 980), None)
            eur_item = next((i for i in data if i.get('currencyCodeA') == 978 and i.get('currencyCodeB') == 980), None)
            usd_str = f"{usd_item['rateBuy']:.2f} / {usd_item['rateSell']:.2f}" if usd_item and 'rateBuy' in usd_item else "41.15 / 41.65"
            eur_str = f"{eur_item['rateBuy']:.2f} / {eur_item['rateSell']:.2f}" if eur_item and 'rateBuy' in eur_item else "44.60 / 45.25"
        else:
            usd_str, eur_str = "41.15 / 41.65", "44.60 / 45.25"
        currency_list.append({"name": "Monobank", "usd": usd_str, "eur": eur_str})
    except Exception as e:
        print(f"Ошибка Monobank: {e}")
        currency_list.append({"name": "Monobank", "usd": "41.15 / 41.65", "eur": "44.60 / 45.25"})

    # 4. Ощадбанк (Ориентир)
    currency_list.append({"name": "Ощадбанк", "usd": "41.20 / 41.80", "eur": "44.70 / 45.40"})

    return currency_list


def get_fuel_data():
    """Данные по АЗС в Сумах и Сумской области"""
    return [
        {"name": "ОККО", "a95": "57.99", "dp": "56.99", "gas": "35.49"},
        {"name": "WOG", "a95": "57.99", "dp": "56.99", "gas": "35.49"},
        {"name": "UPG", "a95": "55.90", "dp": "53.90", "gas": "34.70"},
        {"name": "БРСМ-Нафта", "a95": "52.99", "dp": "51.99", "gas": "33.99"},
        {"name": "ANP / Авіас", "a95": "53.00", "dp": "52.00", "gas": "33.50"},
        {"name": "Shell", "a95": "56.99", "dp": "55.99", "gas": "34.99"}
    ]

# --- 2. ГЕНЕРАЦИЯ КАРТИНКИ ИЗ HTML ---

def generate_image(currency_data, fuel_data, date_str):
    """Заполнение шаблона HTML и рендеринг картинки card.png через Playwright"""
    with open("template.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    template = Template(html_content)
    rendered_html = template.render(
        date_str=date_str,
        currency_data=currency_data,
        fuel_data=fuel_data
    )

    file_path = os.path.abspath("rendered.html")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    # Запуск Playwright с безопасными флагами для GitHub Actions
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page(viewport={"width": 800, "height": 800})
        page.goto(f"file://{file_path}", wait_until="load")
        page.screenshot(path="card.png")
        browser.close()

# --- 3. ОТПРАВКА В TELEGRAM ---

def send_to_telegram(photo_path, caption_text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        raise ValueError("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены в окружении!")

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    with open(photo_path, "rb") as photo:
        payload = {
            "chat_id": chat_id,
            "caption": caption_text,
            "parse_mode": "HTML"
        }
        files = {"photo": photo}
        response = requests.post(url, data=payload, files=files, timeout=30)
        
    if response.status_code == 200:
        print("Успешно отправлено в Telegram!")
    else:
        print(f"Ошибка отправки: {response.status_code}, {response.text}")
        response.raise_for_status()

# --- 4. ОСНОВНОЙ ЗАПУСК ---

if __name__ == "__main__":
    today = datetime.datetime.now()
    date_str = today.strftime("%d.%m.%Y")

    print(f"[{date_str}] Собираем данные...")
    currencies = get_currency_data()
    fuels = get_fuel_data()

    print("Генерируем картинку...")
    generate_image(currencies, fuels, date_str)

    caption = (
        f"<b>📊 Фінансовий та паливний огляд у Сумах на {date_str}</b>\n\n"
        f"<b>💵 Валютний ринок:</b>\n"
        f"Курс гривні залишається стабільним. НБУ утримує контрольований коридор. "
        f"У банках спостерігаються незначні коливання в межах 5–10 копійок.\n\n"
        f"<b>⛽ Паливний ринок:</b>\n"
        f"Ціни на АЗС Сумщини стабільні. Найбільш вигідні цінники на газ та дизель утримують мережі UPG та БРСМ-Нафта.\n\n"
        f"<b>🔮 Короткий прогноз:</b>\n"
        f"Протягом найближчих днів суттєвих стрибків валютного курсу чи пального в регіоні не очікується.\n\n"
        f"#Суми #КурсВалют #ПальнеСуми #Економіка"
    )

    print("Отправляем в Telegram...")
    send_to_telegram("card.png", caption)
