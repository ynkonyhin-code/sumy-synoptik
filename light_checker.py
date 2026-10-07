import os
import requests
from bs4 import BeautifulSoup

# Ссылка на публичное веб-превью канала Сумыоблэнерго
TELEGRAM_CHANNEL_URL = "https://t.me/s/SumyEnergo"

# Имя файла картинки и файла истории в репозитории
IMAGE_FILENAME = "light_banner.jpg"
CACHE_FILE = "last_post_id.txt"

def get_last_sent_id():
    """Считывает ID последнего отправленного поста из файла"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_sent_id(post_id):
    """Сохраняет ID последнего отправленного поста в файл"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(str(post_id))

def get_latest_telegram_post():
    """
    Парсит посты и ищет ТОЛЬКО новые посты про ГПВ или ГАВ
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
            return None, None, None

        gpv_keywords = ["графік погодинних", "графіки погодинних", "погодинних відключень", "гпв"]
        emergency_keywords = ["гав", "сгав", "аварійних відключень", "аварійне вимкнення", "аварійні вимкнення", "аварійне відключення"]
        
        last_sent_id = get_last_sent_id()

        # Проверяем посты с конца (самые свежие)
        for post in reversed(posts):
            # Получаем уникальный ID поста из атрибута data-post (например, "SumyEnergo/1234")
            post_id = post.get("data-post", "")
            
            text_element = post.find("div", class_="tgme_widget_message_text")
            if text_element and post_id:
                post_text = text_element.get_text(separator="\n", strip=True)
                post_text_lower = post_text.lower()
                
                # Если этот пост уже отправлялся ранее — пропускаем
                if post_id == last_sent_id:
                    print(f"Пост {post_id} уже был отправлен ранее. Пропускаем.")
                    return None, None, None

                # 1. Проверяем аварийные отключения
                if any(key in post_text_lower for key in emergency_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, "EMERGENCY", post_id

                # 2. Проверяем плановые ГПВ
                if any(key in post_text_lower for key in gpv_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, "GPV", post_id

        return None, None, None

    except Exception as e:
        print(f"Ошибка при парсинге Telegram-канала: {e}")
        return None, None, None

def send_telegram_local_photo(photo_path, caption_text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return False

    if not os.path.exists(photo_path):
        print(f"Ошибка: Файл изображения '{photo_path}' не найден в репозитории!")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    with open(photo_path, "rb") as photo_file:
        payload = {
            "chat_id": chat_id,
            "caption": caption_text,
            "parse_mode": "HTML"
        }
        files = {"photo": photo_file}
        response = requests.post(url, data=payload, files=files, timeout=20)

    if response.status_code == 200:
        print("Успешно отправлено сообщение в Telegram!")
        return True
    else:
        print(f"Ошибка отправки в Telegram: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    print("Проверяем наличие НОВЫХ постов ГПВ и ГАВ в Сумыоблэнерго...")
    latest_post, post_type, post_id = get_latest_telegram_post()

    if latest_post and post_id:
        if post_type == "EMERGENCY":
            header = "<b>🚨 АВАРІЙНЕ ВІДКЛЮЧЕННЯ СВІТЛА (ГАВ / СГАВ) — Суми</b>\n\n"
            hashtags = "#Суми #СвітлоСуми #ГАВ #АварійнеВідключення"
        else:
            header = "<b>⚡ Графіки погодинних відключений (ГПВ) — Суми</b>\n\n"
            hashtags = "#Суми #СвітлоСуми #ГПВ #ГрафікВідключень"

        caption = (
            f"{header}"
            f"{latest_post}\n\n"
            f"🔗 <a href='https://t.me/SumyEnergo'>Джерело: АТ Сумиобленерго</a>\n\n"
            f"{hashtags}"
        )
        
        # Отправляем в Telegram и запоминаем ID поста только при успешной отправке
        if send_telegram_local_photo(IMAGE_FILENAME, caption):
            save_last_sent_id(post_id)
    else:
        print("Новых необработанных постов про ГПВ или ГАВ не найдено.")