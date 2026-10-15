import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def get_season_theme(month):
    """Возвращает цветовую гамму по времени года без эмодзи"""
    if month in [12, 1, 2]:
        return {"name": "Зима", "bg_start": (15, 32, 39), "bg_end": (32, 58, 67), "accent": "#00D2FF"}
    elif month in [3, 4, 5]:
        return {"name": "Весна", "bg_start": (19, 78, 94), "bg_end": (113, 178, 128), "accent": "#A8FF78"}
    elif month in [6, 7, 8]:
        return {"name": "Літо", "bg_start": (41, 128, 185), "bg_end": (109, 213, 250), "accent": "#FFD200"}
    else:
        # Осень
        return {"name": "Осінь", "bg_start": (44, 62, 80), "bg_end": (211, 84, 0), "accent": "#FF9F43"}

def create_styled_background(width, height, season):
    """Создает атмосферный фон с размытыми светящимися элементами (Боке)"""
    # Базовый вертикальный градиент
    base = Image.new('RGB', (width, height), season["bg_start"])
    top = Image.new('RGB', (width, height), season["bg_end"])
    mask = Image.new('L', (width, height))
    mask_draw = ImageDraw.Draw(mask)
    for y in range(height):
        mask_draw.line([(0, y), (width, y)], fill=int(255 * (y / height)))
    base.paste(top, (0, 0), mask)
    
    # Рисуем круги для эффекта размытого фона (Bokeh)
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    
    # Светящиеся акцентные круги
    draw_ov.ellipse([-100, -100, 500, 500], fill=(255, 255, 255, 30))
    draw_ov.ellipse([width - 400, height // 2 - 200, width + 200, height // 2 + 400], fill=(255, 255, 255, 20))
    draw_ov.ellipse([100, height - 300, 600, height + 200], fill=(0, 0, 0, 40))
    
    # Размываем эти круги
    overlay = overlay.filter(ImageFilter.GaussianBlur(80))
    
    # Объединяем
    base.paste(overlay, (0, 0), overlay)
    return base

def wrap_text(text, font, max_width, draw):
    """Надежный перенос строк по фактической ширине пикселей"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
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
    
    # 1. Генерация стильного фона
    image = create_styled_background(width, height, season)
    draw = ImageDraw.Draw(image)
    
    # Рамка по периметру
    draw.rectangle([35, 35, width - 35, height - 35], outline=season["accent"], width=3)
    
    # 2. Шрифты
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font_path_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        
        font_title = ImageFont.truetype(font_path, 46)
        font_subtitle = ImageFont.truetype(font_path_reg, 30)
        font_date = ImageFont.truetype(font_path, 54)
        font_day = ImageFont.truetype(font_path_reg, 36)
        font_section = ImageFont.truetype(font_path, 32)
        font_body = ImageFont.truetype(font_path_reg, 30)
        font_footer = ImageFont.truetype(font_path_reg, 26)
    except IOError:
        font_title = font_subtitle = font_date = font_day = font_section = font_body = font_footer = ImageFont.load_default()

    # Даты
    months_ua = ["січня", "лютого", "березня", "квітня", "травня", "червня",
                 "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
    days_ua = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    
    date_str = f"{date_obj.day} {months_ua[date_obj.month - 1]} {date_obj.year}"
    day_str = days_ua[date_obj.weekday()]

    # 3. Шапка
    draw.text((70, 65), "СУМСЬКИЙ СИНОПТИК", fill=season["accent"], font=font_title)
    draw.text((70, 125), f"Щоденний календар • Пора року: {season['name']}", fill="#E2E8F0", font=font_subtitle)

    # 4. Блок Даты (Темная плашка с аккуратным скруглением)
    draw.rectangle([70, 185, width - 70, 320], fill=(15, 23, 42))
    draw.rectangle([70, 185, width - 70, 320], outline=season["accent"], width=1)
    draw.text((100, 205), date_str, fill="#FFFFFF", font=font_date)
    draw.text((100, 268), f"День тижня: {day_str}", fill=season["accent"], font=font_day)

    # 5. Блок Фазы Луны (с автоматическим переносом)
    y_curr = 350
    moon_full_text = f"Фаза Місяця: {moon_phase_text}"
    moon_lines = wrap_text(moon_full_text, font_section, width - 140, draw)
    for m_line in moon_lines:
        draw.text((70, y_curr), m_line, fill="#E2E8F0", font=font_section)
        y_curr += 40

    # Декоративная линия-разделитель
    y_curr += 15
    draw.line([(70, y_curr), (width - 70, y_curr)], fill=season["accent"], width=2)
    y_curr += 25

    # 6. Заголовок событий
    draw.text((70, y_curr), "Головні події та свята дня:", fill=season["accent"], font=font_section)
    y_curr += 45
    
    # Главный блок событий в темной полупрозрачной карточке
    card_top = y_curr - 10
    card_bottom = height - 120
    draw.rectangle([70, card_top, width - 70, card_bottom], fill=(15, 23, 42))
    draw.rectangle([70, card_top, width - 70, card_bottom], outline=(255, 255, 255, 50), width=1)

    # Текст праздников с переносом
    lines = wrap_text(holiday_text, font_body, width - 180, draw)
    y_text = card_top + 25
    for line in lines:
        if y_text + 40 < card_bottom - 20: # Чтобы не вылезти за нижнюю границу плашки
            draw.text((95, y_text), f"• {line}" if line == lines[0] else f"  {line}", fill="#FFFFFF", font=font_body)
            y_text += 42

    # 7. Футер
    draw.text((70, height - 85), "t.me/sumskoy_sinoptik", fill="#E2E8F0", font=font_footer)

    image.save(output_path, "JPEG", quality=95)
    return output_path