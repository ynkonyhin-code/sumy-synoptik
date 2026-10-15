import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import zoneinfo
from Shchodennyy_kalendar_card import generate_calendar_card

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def get_kyiv_date():
    """Отримання точного часу та дати в часовому поясі Києва"""
    try:
        tz = zoneinfo.ZoneInfo("Europe/Kyiv")
        return datetime.now(tz)
    except Exception:
        return datetime.now()

def fetch_day_info(date_obj):
    """Парсинг актуальних свят та іменин з українських джерел або новоюліанського календаря"""
    day = date_obj.day
    month = date_obj.month
    
    # Автоматичний HTTP-запит до українського джерела новин/календаря
    url = f"https://www.rbc.ua/ukr/styler/yake-sogodni-svyato-{day}-{month}-all.html"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    holidays = []
    name_days = ""
    legend = ""
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # Знаходження основних заголовків свят
            headers_tags = soup.find_all(["h2", "p", "strong"])
            for tag in headers_tags:
                txt = tag.get_text().strip()
                if "іменини" in txt.lower() or "день ангела" in txt.lower():
                    name_days = txt
                elif len(txt) > 15 and ("день" in txt.lower() or "свято" in txt.lower()):
                    if len(holidays) < 3:
                        holidays.append(txt)
    except Exception as e:
        print(f"Парсинг зовнішнього сайту пройшов з зауваженням: {e}")

    # Резервна локальна база новоюліанського церковного календаря та свят України
    calendar_db = {
        "10-16": {
            "holiday": "День працівників харчової промисловості України. Всесвітній день анестезіолога. Вшанування святого мученика Лонгина Сотника (за новоюліанським календарем).",
            "name_days": "Денис, Іван, Леонтій, Лонгин, Марк, Терезія.",
            "legend": "📜 Прикмета Сумщини: Якщо листя з берези ще не опало повністю — сніг випаде пізно, а зима буде м'якою."
        },
        "10-17": {
            "holiday": "Міжнародний день боротьби за ліквідацію злиднів. Вшанування пророка Осії та преподобного Андрія Критського.",
            "name_days": "Андрій, Антон, Дем'ян, Йосип, Кузьма, Леонтій, Осій.",
            "legend": "📜 Народний переказ: Якщо в цей день гуси летять високо — чекайте тривалої та погожої осені."
        }
    }
    
    key = f"{month:02d}-{day:02d}"
    fallback = calendar_db.get(key, {
        "holiday": f"Всеукраїнський день народних прикмет та вшанування пам'ятних подій дня.",
        "name_days": "Усі іменинники, які святкують День Ангела за новоюліанським календарем.",
        "legend": "📜 Легенда Сумщини: Перекази про давні козацькі сторожові вежі вздовж річки Псел."
    })
    
    final_holiday = " • ".join(holidays) if holidays else fallback["holiday"]
    final_names = name_days if name_days else fallback["name_days"]
    final_legend = fallback["legend"]
    
    return {
        "holiday": final_holiday,
        "name_days": final_names,
        "legend": final_legend
    }

def get_moon_phase(date_obj):
    """Визначення фази місяця без спецемодзі для стабільності шрифтів"""
    known_new_moon = datetime(2024, 1, 11)
    diff = (date_obj.replace(tzinfo=None) - known_new_moon).days
    cycle = 29.53058770576
    phase = (diff % cycle) / cycle
    
    if phase < 0.03 or phase > 0.97:
        return "Молодик (New Moon)"
    elif phase < 0.22:
        return "Зростаючий місяць (Waxing Crescent)"
    elif phase < 0.28:
        return "Перша чверть (First Quarter)"
    elif phase < 0.47:
        return "Зростаючий місяць (Waxing Gibbous)"
    elif phase < 0.53:
        return "Повний місяць (Full Moon)"
    elif phase < 0.72:
        return "Спадний місяць (Waning Gibbous)"
    elif phase < 0.78:
        return "Остання чверть (Last Quarter)"
    else:
        return "Спадний місяць (Waning Crescent)"

def send_telegram_post(photo_path, caption_text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as photo:
        payload = {
            "chat_id": CHAT_ID,
            "caption": caption_text,
            "parse_mode": "Markdown"
        }
        files = {"photo": photo}
        res = requests.post(url, data=payload, files=files)
        if res.status_code != 200:
            raise Exception(f"Помилка відправки в Telegram: {res.text}")
        print("Пост успішно опубліковано!")

def main():
    today = get_kyiv_date()
    moon = get_moon_phase(today)
    data = fetch_day_info(today)
    
    # Генерація збалансованої картки
    photo_path = generate_calendar_card(today, data["holiday"], moon)
    
    months_ua_genitive = [
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
    ]
    days_ua = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    
    date_formatted = f"{today.day} {months_ua_genitive[today.month - 1]} {today.year} року ({days_ua[today.weekday()]})"
    
    caption = (
        f"📅 **Щоденний календар: {date_formatted}**\n\n"
        f"🎉 **Свята та визначні події:**\n{data['holiday']}\n\n"
        f"👤 **День Ангела (Іменини):**\n{data['name_days']}\n\n"
        f"🌙 **Фаза місяця:** {moon}\n\n"
        f"{data['legend']}\n\n"
        f"—————————————————\n"
        f"📍 *Сумський синоптик — погода, традиції та події Сумщини*\n\n"
        f"#СумськийСиноптик #Календар #Суми #ПодіїДня #Іменини"
    )
    
    send_telegram_post(photo_path, caption)

if __name__ == "__main__":
    main()