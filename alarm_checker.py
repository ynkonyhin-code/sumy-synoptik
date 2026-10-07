import os
import requests
from bs4 import BeautifulSoup

# Официальная страница веб-превью канала Сирены Сумского района
TELEGRAM_CHANNEL_URL = "https://t.me/s/surenasumy"

# Имена файлов баннеров и кэша в репозитории
START_BANNER = "alert_start_banner.jpg"
END_BANNER = "alert_end_banner.jpg"
CACHE_FILE = "last_alarm_post_id.txt"

def get_last_sent_id():
    """Считывает ID последнего отправленного поста о тревоге"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_sent_id(post_id):
    """Сохраняет ID последнего отправленного поста"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(str(post_id))

def get_latest_alarm_post():
    """
    Парсит посты с каналов тревог Сум и определяет тип события: ТРЕВОГА или ОТБОЙ
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
            print("Не удалось найти сообщения на странице канала тревог.")
            return None, None, None

        # Ключевые слова для объявления ТРЕВОГИ
        start_keywords = [
            "повітряна тривога",
            "тривога",
            "ракетна небезпека",
            "загроза",
            "червоний рівень",
            "увага"
        ]

        # Ключевые слова для ОТБОЯ
        end_keywords = [
            "відбій",
            "зелений рівень",
            "загроза минула"
        ]
        
        last_sent_id = get_last_sent_id()

        for post in reversed(posts):
            post_id = post.get("data-post", "")
            text_element = post.find("div", class_="tgme_widget_message_text")
            
            if text_element and post_id:
                post_text = text_element.get_text(separator="\n", strip=True)
                post_text_lower = post_text.lower()
                
                # Если этот пост уже публиковался — пропускаем
                if post_id == last_sent_id:
                    print(f"Пост тревоги {post_id} уже обрабатывался. Пропускаем.")
                    return None, None, None

                # 1. Проверяем сначала сигналы ОТБОЯ
                if any(key in post_text_lower for key in end_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, "END", post_id

                # 2. Проверяем сигналы ТРЕВОГИ
                if any(key in post_text_lower for key in start_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, "START", post_id

        return None, None, None

    except Exception as e:
        print(f"Ошибка при парсинге канала тревог: {e}")
        return None, None, None

def send_telegram_local_photo(photo_path, caption_text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return False

    # Если локального баннера нет, высылаем форматированный текст
    if not os.path.exists(photo_path):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": caption_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        response = requests.post(url, json=payload, timeout=15)
        return response.status_code == 200

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(photo_path, "rb") as photo_file:
        payload = {
            "chat_id": chat_id,
            "caption": caption_text,
            "parse_mode": "HTML"
        }
        files = {"photo": photo_file}
        response = requests.post(url, data=payload, files=files, timeout=20)

    return response.status_code == 200

if __name__ == "__main__":
    print("Проверяем свежие посты в канале Сумы — Сирена (@surenasumy)...")
    latest_post, status_type, post_id = get_latest_alarm_post()

    if latest_post and post_id:
        if status_type == "START":
            header = "<b>🚨 УВАГА! ПОВІТРЯНА ТРИВОГА — Сумський район</b>\n\n"
            banner_file = START_BANNER
            hashtags = "#Суми #Сумщина #Тривога #ППО"
        else:
            header = "<b>🟢 ВІДБІЙ ПОВІТРЯНОЇ ТРИВОГИ — Сумський район</b>\n\n"
            banner_file = END_BANNER
            hashtags = "#Суми #Сумщина #Відбій"

        caption = (
            f"{header}"
            f"{latest_post}\n\n"
            f"🔗 <a href='https://t.me/surenasumy'>Джерело: Сирена Сумський район</a>\n\n"
            f"{hashtags}"
        )
        
        if send_telegram_local_photo(banner_file, caption):
            save_last_sent_id(post_id)
            print(f"Сообщение о статусе [{status_type}] успешно отправлено!")
    else:
        print("Новых обновлений статуса тревоги не найдено.")