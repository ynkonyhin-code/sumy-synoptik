import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def generate_calendar_card(date_obj, holiday_text, moon_phase_text, output_path="calendar_card.jpg"):
    # Розміри картки (формат Instagram/Telegram 4:5)
    width, height = 1080, 1350
    
    # Створюємо зображення з глибоким стильним градієнтом/фоном (наприклад, темно-синій нічний/ранковий небосхил)
    image = Image.new("RGB", (width, height), color="#1A2238")
    draw = ImageDraw.Draw(image)
    
    # Додаємо декоративні елементи (наприклад, світловий акцент або рамку)
    draw.rectangle([40, 40, width - 40, height - 40], outline="#4E65FF", width=4)
    
    # Шрифти (використовуємо стандартні або системні кросплатформні шляхи, наприклад DejaVuSans або Arial)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_date = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", 36)
    except IOError:
        # Запасний варіант, якщо шрифти не знайдуться у контейнері GitHub Actions
        font_title = ImageFont.load_default()
        font_date = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Форматування дати українською
    months_ua = [
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
    ]
    days_ua = [
        "Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"
    ]
    
    day_of_week = days_ua[date_obj.weekday()]
    day_num = date_obj.day
    month_str = months_ua[date_obj.month - 1]
    year_str = date_obj.year
    
    date_str = f"{day_num} {month_str} {year_str}"
    
    # Малюємо шапку каналу
    draw.text((80, 90), "СУМСЬКИЙ СИНОПТИК", fill="#00F2FE", font=font_title)
    draw.text((80, 160), "ЩОДЕННИЙ КАЛЕНДАР", fill="#FFFFFF", font=font_small)
    
    # Блок дати
    draw.rectangle([80, 240, width - 80, 420], fill="#253358")
    draw.text((120, 270), date_str, fill="#FFFFFF", font=font_date)
    draw.text((120, 360), f"({day_of_week})", fill="#A0AEC0", font=font_body)
    
    # Фаза місяця
    draw.text((80, 490), f"🌙 Місяць: {moon_phase_text}", fill="#E2E8F0", font=font_body)
    
    # Головне свято / подія дня
    draw.text((80, 600), "Головна подія / свято:", fill="#00F2FE", font=font_small)
    
    # Оберт тексту для свята (розбиваємо по рядках, якщо довгий)
    margin = 80
    max_width = width - 160
    lines = []
    words = holiday_text.split()
    current_line = ""
    for word in words:
        test_line = current_line + " " + word if current_line else word
        # Приблизна перевірка ширини
        if len(test_line) * 24 < max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
        
    y_text = 660
    for line in lines[:5]: # Максимум 5 рядків
        draw.text((margin, y_text), line, fill="#FFFFFF", font=font_body)
        y_text += 60

    # Нижня плашка / вотермарка
    draw.text((80, height - 120), "t.me/sumskoy_sinoptik", fill="#718096", font=font_small)
    
    image.save(output_path, "JPEG", quality=95)
    return output_path

if __name__ == "__main__":
    generate_calendar_card(datetime.now(), "День української писемності та мови. Покровительство і традиції.", "Зростаючий місяць")