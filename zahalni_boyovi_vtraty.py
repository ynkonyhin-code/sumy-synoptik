import os
import re
import requests
from bs4 import BeautifulSoup

# Конфигурация из GitHub Secrets
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Имена файлов
HISTORY_FILE = "zahalni_boyovi_vtraty_posted.txt"
SOURCE_CHANNEL_URL = "https://t.me/s/GeneralStaffZSU"
KEY_PHRASE = "Загальні бойові втрати противника з"

# Теги для публикации
TAGS = "\n\n#втративорога #зсу #генштаб #статистика #війна #україна"

def load_posted_ids():
    """Загрузка ID уже опубликованных постов."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted_id(post_id):
    """Сохранение ID опубликованного поста в файл."""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{post_id}\n")

def clean_text(text):
    """
    Очистка текста: удаление любых URL-ссылок (http, https, t.me) 
    и форматирование перед добавлением хэштегов.
    """
    # Удаляем URL-ссылки вида http://, https://, t.me/...
    text_no_urls = re.sub(r'https?://\S+|t\.me/\S+', '', text)
    
    # Убираем лишние пробелы в концах строк
    lines = [line.rstrip() for line in text_no_urls.splitlines()]
    cleaned_text = "\n".join(lines).strip()
    
    # Добавляем тематические хэштеги
    final_text = f"{cleaned_text}{TAGS}"
    return final_text

def send_telegram_photo(photo_url, caption):
    """Отправка фото с подписью в Telegram-канал."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    # Telegram имеет лимит на caption в 1024 символа
    if len(caption) > 1024:
        caption = caption[:1020] + "..."

    payload = {
        "chat_id": CHAT_ID,
        "photo": photo_url,
        "caption": caption
    }
    
    response = requests.post(url, data=payload)
    return response.json()

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Ошибка: BOT_TOKEN или CHAT_ID не найдены в переменных окружения.")
        return

    posted_ids = load_posted_ids()
    
    # Загружаем публичную страницу канала
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    res = requests.get(SOURCE_CHANNEL_URL, headers=headers)
    if res.status_code != 200:
        print(f"Не удалось загрузить страницу канала. Статус: {res.status_code}")
        return

    # Используем встроенный html.parser без внешних зависимостей
    soup = BeautifulSoup(res.text, "html.parser")
    posts = soup.find_all("div", class_="tgme_widget_message")

    for post in reversed(posts):  # Обрабатываем от старых к новым
        post_id = post.get("data-post")
        if not post_id or post_id in posted_ids:
            continue

        # Поиск текста
        text_div = post.find("div", class_="tgme_widget_message_text")
        if not text_div:
            continue

        raw_text = text_div.get_text(separator="\n")

        # Проверка ключевой фразы
        if KEY_PHRASE.lower() not in raw_text.lower():
            continue

        # Поиск изображения
        photo_div = post.find("a", class_="tgme_widget_message_photo_wrap")
        photo_url = None
        if photo_div and "style" in photo_div.attrs:
            # Извлекаем URL картинки из background-image: url('...')
            style = photo_div["style"]
            match = re.search(r"background-image:url\('(.*?)'\)", style)
            if match:
                photo_url = match.group(1)

        cleaned_caption = clean_text(raw_text)

        print(f"Найден новый пост: {post_id}")
        
        if photo_url:
            result = send_telegram_photo(photo_url, cleaned_caption)
            if result.get("ok"):
                print(f"Пост {post_id} успешно опубликован!")
                save_posted_id(post_id)
            else:
                print(f"Ошибка отправки в Telegram: {result}")
        else:
            print(f"Изображение для поста {post_id} не найдено, пропуск.")

if __name__ == "__main__":
    main()