import os
import requests
from bs4 import BeautifulSoup

# --- НАСТРОЙКИ ---
# Ссылка на страницу с отключениями (например, раздел новостей/графиков АО Сумыоблэнерго или официальный портал)
SOURCE_URL = "https://www.soe.com.ua"  # При необходимости подставим точный адрес нужной страницы

def get_latest_power_status():
    """
    Функция заходит на сайт и ищет последние новости/статусы об отключениях.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=15)
        response.raise_for_status() # Проверяем, что сайт ответил успешно (код 200)
        
        # Разбираем HTML-код страницы
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ищем ключевые слова на странице (ГПВ, ГАВ, вимкнення, Суми)
        # Находим первый релевантный заголовок или блок с текстом
        keywords = ["ГПВ", "ГАВ", "аварійне вимкнення", "графік"]
        
        # Пример поиска по тегам <p> или <div> с текстом
        found_info = []
        for p in soup.find_all(['p', 'a', 'div']):
            text = p.get_text(strip=True)
            if any(key.lower() in text.lower() for key in keywords):
                if len(text) > 20 and text not in found_info: # Фильтруем слишком короткие обрывки
                    found_info.append(text)
                    if len(found_info) >= 3: # Берем 3 самых свежих упоминания
                        break
                        
        return found_info
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None

def send_telegram_message(text):
    """
    Отправка текстового сообщения в Telegram-канал.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы!")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Сообщение успешно отправлено в Telegram!")
    else:
        print(f"Ошибка отправки в Telegram: {response.status_code}, {response.text}")

if __name__ == "__main__":
    print("Проверяем статус энергосистемы Сум...")
    status_updates = get_latest_power_status()

    if status_updates:
        # Формируем красивое сообщение для Telegram
        message = "<b>⚡ Моніторинг електромережі м. Суми</b>\n\n"
        message += "<b>Останні оновлення та оперативна інформація:</b>\n\n"
        
        for idx, item in enumerate(status_updates, 1):
            message += f"• {item}\n\n"
            
        message += "📌 <i>Дані оновлюються автоматично.</i>\n"
        message += "#Суми #СвітлоСуми #ГПВ #Обленерго"

        print("Отправляем сводку...")
        send_telegram_message(message)
    else:
        print("Новых обновлений по ключевым словам не найдено.")