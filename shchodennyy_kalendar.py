import os
import requests
from datetime import datetime
from Shchodennyy_kalendar_card import generate_calendar_card

# Отримання секретів з оточення GitHub Actions
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def get_moon_phase(date_obj):
    # Простий алгоритм розрахунку фази місяця (наближений)
    # Базова дата відомого молодика (напр., 11 січня 2024)
    known_new_moon = datetime(2024, 1, 11)
    diff = (date_obj - known_new_moon).days
    cycle = 29.53058770576
    phase = (diff % cycle) / cycle
    
    if phase < 0.03 or phase > 0.97:
        return "Молодик 🌑"
    elif phase < 0.22:
        return "Зростаючий місяць 🌒"
    elif phase < 0.28:
        return "Перша чверть 🌓"
    elif phase < 0.47:
        return "Зростаючий місяць 🌔"
    elif phase < 0.53:
        return "Повний місяць 🌕"
    elif phase < 0.72:
        return "Спадний місяць 🌖"
    elif phase < 0.78:
        return "Остання чверть 🌗"
    else:
        return "Спадний місяць 🌘"

def get_calendar_data(date_obj):
    # Приклад словника статичних/тематичних даних на конкретні дати або шаблон
    # Ключ у форматі "MM-DD"
    date_key = date_obj.strftime("%m-%d")
    
    # База даних свят та легенд (можна доповнювати)
    database = {
        "10-16": {
            "holiday": "Всесвітній день продовольства та День боса. У народі вшановують пам'ять святого Лонгина Сотника.",
            "name_days": "Денис, Іван, Павло, Петро, Степан, Яків.",
            "legend": "📜 Легенда Сумщини: Перекази про старовинні козацькі криниці та підземні ходи у місті Суми, що з'єднували колишні фортеці та монастирі."
        },
        # Можна додати інші ключі або дефолтний шаблон нижче
    }
    
    default_data = {
        "holiday": f"День гарного настрою та спостереження за природою на Сумщині.",
        "name_days": "Усіх іменників за церковним календарем.",
        "legend": "📜 Народні прикмети: Якщо ранковий туман над Пслом стелиться низько — на ясну та сонячну погоду вдень."
    }
    
    return database.get(date_key, default_data)

def send_telegram_post(photo_path, caption_text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as photo:
        payload = {
            "chat_id": CHAT_ID,
            "caption": caption_text,
            "parse_mode": "Markdown"
        }
        files = {"photo": photo}
        response = requests.post(url, data=payload, files=files)
        if response.status_code != 200:
            raise Exception(f"Помилка відправки в Telegram: {response.text}")
        print("Пост успішно опубліковано!")

def main():
    today = datetime.now()
    moon = get_moon_phase(today)
    data = get_calendar_data(today)
    
    # Генерація картинки
    photo_path = generate_calendar_card(today, data["holiday"], moon)
    
    # Формування текст посту для Telegram
    months_ua_genitive = [
        "січня", "лютого", "березня", "квітня", "травиня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
    ]
    date_formatted = f"{today.day} {months_ua_genitive[today.month - 1]} {today.year}"
    
    caption = (
        f"📅 **Календар дня: {date_formatted}**\n\n"
        f"✨ **Свята та події:**\n{data['holiday']}\n\n"
        f"👤 **Іменини:** {data['name_days']}\n\n"
        f"🌙 **Фаза місяця:** {moon}\n\n"
        f"{data['legend']}\n\n"
        f"—————————————————\n"
        f"📍 *Сумський синоптик — завжди в курсі подій та погоди!*\n\n"
        f"#СумськийСиноптик #Календар #Суми #ПодіїДня #ЩоденнийКалендар"
    )
    
    send_telegram_post(photo_path, caption)

if __name__ == "__main__":
    main()