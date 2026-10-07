import os
import requests
from bs4 import BeautifulSoup

# Ссылка на публичное веб-превью канала Сумыоблэнерго
TELEGRAM_CHANNEL_URL = "https://t.me/s/SumyEnergo"

# Имя файла картинки в корне репозитория
IMAGE_FILENAME = "light_banner.jpg"

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
        
        posts = soup.find_all("div", class_="tgme_widget_message")
        if not posts:
            print("Не удалось найти сообщения на странице канала.")
            return None

        keywords = ["гпв", "гав", "вимкнення", "графік", "черга", "світло", "обленерго"]
        
        for post in reversed(posts):
            text_element = post.find("div", class_="tgme_widget_message_text")
            if text_element:
                post_text = text_element.get_text(separator="\n", strip=True)
                
                if any(key in post_text.lower() for key in keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text

        return None

    except Exception as e:
        print(f"Ошибка при парсинге Telegram-канала: {e}")
        return None

def send_telegram_local_photo(photo_path, caption_text):
    """
    Отправляет локальный файл изображения с подписью в Telegram
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return

    if not os.path.exists(photo_path):
        print(f"Ошибка: Файл изображения '{photo_path}' не найден в репозитории!")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    with open(photo_path, "rb") as photo_file:
        payload = {
            "chat_id": chat_id,
            "caption": caption_text,
            "parse_mode": "HTML"
        }
        files = {
            "photo": photo_file
        }
        response = requests.post(url, data=payload, files=files, timeout=20)

    if response.status_code == 200:
        print("Успешно отправлено баннер-сообщение в Telegram!")
    else:
        print(f"Ошибка отправки в Telegram: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("Проверяем свежие посты в канале Сумыоблэнерго (@SumyEnergo)...")
    latest_post = get_latest_telegram_post()

    if latest_post:
        caption = (
            f"<b>⚡ Оперативна інформація від Сумиобленерго</b>\n\n"
            f"{latest_post}\n\n"
            f"🔗 <a href='https://t.me/SumyEnergo'>Джерело: АТ Сумиобленерго</a>\n\n"
            f"#Суми #СвітлоСуми #ГПВ #Обленерго"
        )
        send_telegram_local_photo(IMAGE_FILENAME, caption)
    else:
        print("Свежих целевых новостей в канале не найдено.")