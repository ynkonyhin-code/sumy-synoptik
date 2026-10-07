import os
import requests
from bs4 import BeautifulSoup

# Ссылка на публичное веб-превью канала Сумыоблэнерго
TELEGRAM_CHANNEL_URL = "https://t.me/s/SumyEnergo"

def get_latest_telegram_post():
    """
    Парсит последние посты с веб-страницы https://t.me/s/SumyEnergo
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(TELEGRAM_CHANNEL_URL, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Находим все блоки сообщений на странице канала
        posts = soup.find_all("div", class_="tgme_widget_message")
        if not posts:
            print("Не удалось найти сообщения на странице канала.")
            return None

        # Проверяем посты с конца (самые свежие)
        keywords = ["гпв", "гав", "вимкнення", "графік", "черга", "світло", "обленерго"]
        
        for post in reversed(posts):
            text_element = post.find("div", class_="tgme_widget_message_text")
            if text_element:
                # Получаем текст сообщения (с сохранением переносов строк)
                post_text = text_element.get_text(separator="\n", strip=True)
                
                # Проверяем наличие ключевых слов
                if any(key in post_text.lower() for key in keywords):
                    # Обрезаем слишком длинные посты (до 800 символов), чтобы не перегружать ленту
                    if len(post_text) > 800:
                        post_text = post_text[:800] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text

        return None

    except Exception as e:
        print(f"Ошибка при парсинге Telegram-канала: {e}")
        return None

def send_telegram_message(text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
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
        print(f"Ошибка отправки в Telegram: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("Проверяем свежие посты в канале Сумыоблэнерго (@SumyEnergo)...")
    latest_post = get_latest_telegram_post()

    if latest_post:
        message = (
            f"<b>⚡ Оперативна інформація від Сумиобленерго</b>\n\n"
            f"{latest_post}\n\n"
            f"🔗 <a href='https://t.me/SumyEnergo'>Джерело: АТ Сумиобленерго</a>\n\n"
            f"#Суми #СвітлоСуми #ГПВ #Обленерго"
        )
        send_telegram_message(message)
    else:
        print("Свежих целевых новостей в канале не найдено.")