import os
import requests
from bs4 import BeautifulSoup

# ОФИЦИАЛЬНЫЙ канал КП «Міськводоканал» Сумской городской рады
TELEGRAM_CHANNEL_URL = "https://t.me/s/vodokanalSMR"

# Баннер и файл для сохранения ID последнего поста
IMAGE_FILENAME = "water_banner.jpg"
CACHE_FILE = "last_water_post_id.txt"

def get_last_sent_id():
    """Считывает ID последнего отправленного поста Водоканала"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_last_sent_id(post_id):
    """Сохраняет ID последнего отправленного поста"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(str(post_id))

def get_latest_water_post():
    """
    Парсит посты из @vodokanalSMR и ищет ТОЛЬКО посты про отключения / ремонтные работы
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
            print("Не удалось найти сообщения на странице Водоканала.")
            return None, None

        # Ключевые слова для фильтрации официальных аварийных сообщений
        water_keywords = [
            "припинено водопостачання",
            "обмежено водопостачання",
            "відключення води",
            "аварійні роботи",
            "ремонтні роботи",
            "порив",
            "витікання",
            "знеструмлення",
            "тиск води",
            "водопостачання"
        ]
        
        last_sent_id = get_last_sent_id()

        for post in reversed(posts):
            post_id = post.get("data-post", "")
            text_element = post.find("div", class_="tgme_widget_message_text")
            
            if text_element and post_id:
                post_text = text_element.get_text(separator="\n", strip=True)
                post_text_lower = post_text.lower()
                
                # Если пост уже был опубликован — пропускаем
                if post_id == last_sent_id:
                    print(f"Пост {post_id} уже отправлялся. Пропускаем.")
                    return None, None

                # Проверяем совпадение по ключевым словам
                if any(key in post_text_lower for key in water_keywords):
                    if len(post_text) > 750:
                        post_text = post_text[:750] + "...\n\n<i>(Читати повністю в джерелі)</i>"
                    return post_text, post_id

        return None, None

    except Exception as e:
        print(f"Ошибка при парсинге канала Водоканала: {e}")
        return None, None

def send_telegram_local_photo(photo_path, caption_text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return False

    # Если баннера нет, отправляем простым текстом
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
    print("Проверяем свежие сообщения КП «Міськводоканал» (@vodokanalSMR)...")
    latest_post, post_id = get_latest_water_post()

    if latest_post and post_id:
        caption = (
            f"<b>💧 Оперативна інформація від КП «Міськводоканал»</b>\n\n"
            f"{latest_post}\n\n"
            f"🔗 <a href='https://t.me/vodokanalSMR'>Джерело: КП Міськводоканал Суми</a>\n\n"
            f"#Суми #ВодаСуми #Міськводоканал #АварійніРоботи"
        )
        
        if send_telegram_local_photo(IMAGE_FILENAME, caption):
            save_last_sent_id(post_id)
            print("Сообщение с официального канала Водоканала отправлено!")
    else:
        print("Новых целевых постов про воду не найдено.")