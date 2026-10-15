import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def get_season_theme(month):
    """Повертає кольори та тематичну назву пори року"""
    if month in [12, 1, 2]:
        return {"name": "Зима ❄️", "bg_start": "#0F2027", "bg_end": "#203A43", "accent": "#00D2FF"}
    elif month in [3, 4, 5]:
        return {"name": "Весна 🌿", "bg_start": "#134E5E", "bg_end": "#71B280", "accent": "#A8FF78"}
    elif month in [6, 7, 8]:
        return {"name": "Літо ☀️", "bg_start": "#2980B9", "bg_end": "#6DD5FA", "accent": "#FFD200"}
    else:
        # Осінь
        return {"name": "Осінь 🍂", "bg_start": "#2C3E50", "bg_end": "#FD746C", "accent": "#FF8C00"}

def create_gradient_background(width, height, start_hex, end_hex):
    """Генерує м'який вертикальний градієнт для фону"""
    base = Image.new('RGB', (width, height), start_hex)
    top = Image.new('RGB', (width, height), end_hex)
    mask = Image.new('L', (width, height))
    mask_draw = ImageDraw.Draw(mask)
    for y in range(height):
        mask_draw.line([(0, y), (width, y)], fill=int(255 * (y / height)))
    base.paste(top, (0, 0), mask)
    return base

def wrap_text(text, font, max_width, draw):
    """Переносити текст за реальними розмірами шрифту"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        # getlength для точного визначення ширини рядка
        try:
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
        except AttributeError:
            w = draw.textlength(test_line, font=font) if hasattr(draw, 'textlength') else len(test_line) * 20
            
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def generate_calendar_card(date_obj, holiday_text, moon_phase_text, output_path="calendar_card.jpg"):
    width, height = 1080, 1350
    season = get_season_theme(date_obj.month)
    
    # Створення градієнтного фону під пору року
    image = create_gradient_background(width, height, season["bg_start"], season["bg_end"])
    draw = ImageDraw.Draw(image)
    
    # Декоративна рамка
    draw.rectangle([35, 35, width - 35, height - 35], outline=season["accent"], width=3)
    
    # Завантаження шрифтів
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font_path_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        
        font_title = ImageFont.truetype(font_path, 48)
        font_subtitle = ImageFont.truetype(font_path_reg, 32)
        font_date = ImageFont.truetype(font_path, 58)
        font_day = ImageFont.truetype(font_path_reg, 38)
        font_section = ImageFont.truetype(font_path, 34)
        font_body = ImageFont.truetype(font_path_reg, 32)
        font_footer = ImageFont.truetype(font_path_reg, 28)
    except IOError:
        font_title = font_subtitle = font_date = font_day = font_section = font_body = font_footer = ImageFont.load_default()

    # Дати українською
    months_ua = ["січня", "лютого", "березня", "квітня", "травня", "червня",
                 "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
    days_ua = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    
    date_str = f"{date_obj.day} {months_ua[date_obj.month - 1]} {date_obj.year}"
    day_str = days_ua[date_obj.weekday()]

    # Хедер
    draw.text((70, 70), "СУМСЬКИЙ СИНОПТИК", fill=season["accent"], font=font_title)
    draw.text((70, 130), f"Щоденний календар • Пора року: {season['name']}", fill="#FFFFFF", font=font_subtitle)

    # Картка дати
    draw.rectangle([70, 190, width - 70, 330], fill=(0, 0, 0, 100))
    draw.rectangle([70, 190, width - 70, 330], outline="#FFFFFF", width=1)
    draw.text((100, 210), date_str, fill="#FFFFFF", font=font_date)
    draw.text((100, 275), f"День тижня: {day_str}", fill=season["accent"], font=font_day)

    # Інформаційний блок: Місяць
    y_curr = 370
    draw.text((70, y_curr), f"Фаза Місяця: {moon_phase_text}", fill="#E2E8F0", font=font_section)
    
    # Інформаційний блок: Свята
    y_curr += 60
    draw.text((70, y_curr), "Головні події та свята дня:", fill=season["accent"], font=font_section)
    
    y_curr += 45
    lines = wrap_text(holiday_text, font_body, width - 140, draw)
    for line in lines[:8]:  # До 8 рядків з точним перенесенням
        draw.text((70, y_curr), line, fill="#FFFFFF", font=font_body)
        y_curr += 42

    # Футер
    draw.text((70, height - 90), "t.me/sumskoy_sinoptik", fill="#E2E8F0", font=font_footer)

    image.save(output_path, "JPEG", quality=95)
    return output_path