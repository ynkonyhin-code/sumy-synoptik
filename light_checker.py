import os
import requests
from bs4 import BeautifulSoup

# Ссылка на страницу новостей/графиков
SOURCE_URL = "https://www.soe.com.ua"

def get_latest_power_status():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(SOURCE_URL, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        keywords = ["ГПВ", "ГАВ", "аварійне вимкнення", "графік", "черга"]
        
        found_info = []
        for p in soup.find_all(['p', 'a', 'div', 'h3', 'h4']):
            text = p.get_text(strip=True)
            if any(key.lower() in text.lower() for key in keywords):
                if len(text) > 25 and text not in found_info:
                    found_info.append(text)
                    if len(found_info) >= 3:
                        break
                        
        return found_info
    except Exception as e:
        print(f"Помилка під час отримання даних: {e}")
        return None

def send_telegram_message(text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты не найдены!")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    response = requests.post(url, json=payload, timeout=15)
    if response.status_code == 200:
        print("Успешно отправлено в Telegram!")
    else:
        print(f"Ошибка отправки: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("Проверяем статус энергосистемы Сум...")
    status_updates = get_latest_power_status()

    if status_updates:
        message = "<b>⚡ Оперативна інформація щодо електропостачання (м. Суми)</b>\n\n"
        message += "<b>Останні сповіщення:</b>\n\n"
        
        for item in status_updates:
            message += f"• {item}\n\n"
            
        message += "📌 <i>Дані оновлюються автоматично з офіційних джерел.</i>\n"
        message += "#Суми #СвітлоСуми #ГПВ #Обленерго"

        send_telegram_message(message)
    else:
        print("Свежих обновлений не найдено. Пропуск отправки.")