import os
import requests
from bs4 import BeautifulSoup

# Ссылка на публичное веб-превью канала Сумыоблэнерго
TELEGRAM_CHANNEL_URL = "https://t.me/s/SumyEnergo"

# Имя файла картинки в корне репозитория
IMAGE_FILENAME = "light_banner.jpg"

def get_latest_telegram_post():
    """
    Парсит посты и ищет ТОЛЬКО те, которые касаются ГПВ или аварийных отключений (ГАВ / СГАВ)
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
            return None, None

        # Ключевые слова для ГПВ (почасовые)
        gpv_keywords = [
            "графік погодинних",
            "графіки погодинних",
            "погодинних відключень",
            "гпв"
        ]

        # Ключевые слова для Аварийных отключений (ГАВ / СГАВ / Аварийные)
        emergency_keywords = [
            "гав",
            "сгав",
            "аварійних відключень",
            "аварійне вимкнення",
            "аварійні вимкнення",
            "аварійне відключення"
        ]
        
        # Проверяем посты с конца (самые свежие)
        for post in reversed(posts):
            text_element = post.find("div", class_="tgme_widget_message_text")
            if text_element:
                post_text = text_element.get_text(separator="\n", strip=True)
                post_text_lower = post_text.lower()
                
                # 1. Проверяем аварийные отключения
                if any(key in post_text_lower for key in emergency_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, "EMERGENCY"

                # 2. Проверяем плановые ГПВ
                if any(key in post_text_lower for key in gpv_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, "GPV"

        return None, None

    except Exception as e:
        print(f"Ошибка при парсинге Telegram-канала: {e}")
        return None, None

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
        print("Успешно отправлено сообщение в Telegram!")
    else:
        print(f"Ошибка отправки в Telegram: {response.status_code} - {response.text}")

if __name__ == "__main__":
    print("Проверяем наличие постов ГПВ и ГАВ в канале Сумыоблэнерго (@SumyEnergo)...")
    latest_post, post_type = get_latest_telegram_post()

    if latest_post:
        # Динамический заголовок в зависимости от типа новости
        if post_type == "EMERGENCY":
            header = "<b>🚨 АВАРІЙНЕ ВІДКЛЮЧЕННЯ СВІТЛА (ГАВ / СГАВ) — Суми</b>\n\n"
            hashtags = "#Суми #СвітлоСуми #ГАВ #АварійнеВідключення"
        else:
            header = "<b>⚡ Графіки погодинних відключень (ГПВ) — Суми</b>\n\n"
            hashtags = "#Суми #СвітлоСуми #ГПВ #ГрафікВідключень"

        caption = (
            f"{header}"
            f"{latest_post}\n\n"
            f"🔗 <a href='https://t.me/SumyEnergo'>Джерело: АТ Сумиобленерго</a>\n\n"
            f"{hashtags}"
        )
        send_telegram_local_photo(IMAGE_FILENAME, caption)
    else:
        print("Свежих постов про ГПВ или аварийные отключения в канале не найдено.")