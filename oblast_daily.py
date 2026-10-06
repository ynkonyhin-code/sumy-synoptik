import os
import json
import uuid
import urllib.request
import urllib.parse
import urllib.error
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

# ============================================================
# СУМЩИНА — ЗВЕДЕННЯ ПРОГНОЗУ ПО ОБЛАСТІ (WeatherAPI.com)
# Публікація одного допису з картинкою раз на добу (~06:00).
#
# Змінні середовища:
#   WEATHERAPI_KEY   — ключ WeatherAPI
#   SUMY_BOT_TOKEN   — токен Telegram-бота
#   SUMY_CHANNEL     — канал для публікації
#   DRY_RUN=1        — не надсилати в Telegram, лише зберегти картинку
#                      oblast_forecast.png і вивести текст у лог
# ============================================================

TIMEZONE = "Europe/Kyiv"

CITIES = [
    ("Суми", 50.9077, 34.7981),
    ("Шостка", 51.8633, 33.4792),
    ("Конотоп", 51.2417, 33.2028),
    ("Ромни", 50.7517, 33.4750),
    ("Охтирка", 50.3103, 34.8988),
    ("Глухів", 51.6781, 33.9100),
]

WEATHERAPI_KEY = os.environ.get("WEATHERAPI_KEY")
BOT_TOKEN = os.environ.get("SUMY_BOT_TOKEN")
CHANNEL = os.environ.get("SUMY_CHANNEL")
DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")

if not WEATHERAPI_KEY:
    print("ПОМИЛКА: не знайдено змінну WEATHERAPI_KEY")
    raise SystemExit(1)

if not DRY_RUN and (not BOT_TOKEN or not CHANNEL):
    print("ПОМИЛКА: не знайдено змінні SUMY_BOT_TOKEN або SUMY_CHANNEL")
    raise SystemExit(1)

IMAGE_PATH = "oblast_forecast.png"


# ------------------------------------------------------------
# Коди погоди WeatherAPI -> (категорія, текст українською)
# Категорії: clear, partly, cloudy, fog, rain, heavy_rain, snow, sleet, thunder
# ------------------------------------------------------------

CODE_MAP = {
    1000: ("clear", "Ясно"),
    1003: ("partly", "Мінлива хмарність"),
    1006: ("cloudy", "Хмарно"),
    1009: ("cloudy", "Похмуро"),
    1030: ("fog", "Серпанок"),
    1063: ("rain", "Можливий дощ"),
    1066: ("snow", "Можливий сніг"),
    1069: ("sleet", "Можливий мокрий сніг"),
    1072: ("rain", "Можлива крижана мряка"),
    1087: ("thunder", "Можлива гроза"),
    1114: ("snow", "Хуртовина"),
    1117: ("snow", "Заметіль"),
    1135: ("fog", "Туман"),
    1147: ("fog", "Паморозний туман"),
    1150: ("rain", "Невелика мряка"),
    1153: ("rain", "Мряка"),
    1168: ("rain", "Крижана мряка"),
    1171: ("rain", "Сильна крижана мряка"),
    1180: ("rain", "Невеликий дощ"),
    1183: ("rain", "Невеликий дощ"),
    1186: ("rain", "Дощ"),
    1189: ("rain", "Дощ"),
    1192: ("heavy_rain", "Сильний дощ"),
    1195: ("heavy_rain", "Сильний дощ"),
    1198: ("rain", "Крижаний дощ"),
    1201: ("heavy_rain", "Сильний крижаний дощ"),
    1204: ("sleet", "Мокрий сніг"),
    1207: ("sleet", "Сильний мокрий сніг"),
    1210: ("snow", "Невеликий сніг"),
    1213: ("snow", "Невеликий сніг"),
    1216: ("snow", "Сніг"),
    1219: ("snow", "Сніг"),
    1222: ("snow", "Сильний сніг"),
    1225: ("snow", "Сильний сніг"),
    1237: ("snow", "Льодова крупа"),
    1240: ("rain", "Короткочасний дощ"),
    1243: ("heavy_rain", "Злива"),
    1246: ("heavy_rain", "Сильна злива"),
    1249: ("sleet", "Мокрий сніг"),
    1252: ("sleet", "Мокрий сніг"),
    1255: ("snow", "Снігопад"),
    1258: ("snow", "Сильний снігопад"),
    1261: ("snow", "Льодова крупа"),
    1264: ("snow", "Льодова крупа"),
    1273: ("thunder", "Дощ з грозою"),
    1276: ("thunder", "Сильний дощ з грозою"),
    1279: ("thunder", "Сніг з грозою"),
    1282: ("thunder", "Сильний сніг з грозою"),
}

CATEGORY_TEXT = {
    "clear": "Ясно",
    "partly": "Мінлива хмарність",
    "cloudy": "Хмарно",
    "fog": "Туман",
    "rain": "Дощ",
    "heavy_rain": "Сильний дощ",
    "snow": "Сніг",
    "sleet": "Мокрий сніг",
    "thunder": "Гроза",
}

# Чим вище число — тим «важливіша» погода для заголовка
SEVERITY = {
    "clear": 0,
    "partly": 1,
    "cloudy": 2,
    "fog": 3,
    "rain": 4,
    "sleet": 5,
    "snow": 5,
    "heavy_rain": 6,
    "thunder": 7,
}

CATEGORY_EMOJI = {
    "clear": "☀️",
    "partly": "⛅",
    "cloudy": "☁️",
    "fog": "🌫",
    "rain": "🌧",
    "heavy_rain": "🌧",
    "snow": "❄️",
    "sleet": "🌨",
    "thunder": "⛈",
}


def classify(code):
    return CODE_MAP.get(code, ("cloudy", "Змінна погода"))


def dominant_category(categories):
    """Найбільш значуща погода: опади/гроза, якщо вони тривають 2+ години,
    інакше — найчастіша категорія."""
    if not categories:
        return "cloudy"
    counts = Counter(categories)
    significant = [
        c for c, n in counts.items()
        if SEVERITY[c] >= 4 and (n >= 2 or c == "thunder")
    ]
    if significant:
        return max(significant, key=lambda c: SEVERITY[c])
    return counts.most_common(1)[0][0]


# ------------------------------------------------------------
# Запит до WeatherAPI
# ------------------------------------------------------------

def fetch_city(name, lat, lon):
    params = {
        "key": WEATHERAPI_KEY,
        "q": f"{lat},{lon}",
        "days": 1,
        "aqi": "no",
        "alerts": "no",
    }
    url = "https://api.weatherapi.com/v1/forecast.json?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # URL не друкуємо — у ньому ключ
        print(f"  {name}: помилка HTTP {e.code}")
    except Exception as e:
        print(f"  {name}: помилка запиту ({type(e).__name__})")
    return None


def hours_of(data):
    hours = []
    for h in data["forecast"]["forecastday"][0]["hour"]:
        dt = datetime.strptime(h["time"], "%Y-%m-%d %H:%M")
        hours.append((dt, h))
    return hours


def analyze_city(name, data):
    all_hours = hours_of(data)
    # «Весь день» — з 06:00 до кінця доби
    day = [(dt, h) for dt, h in all_hours if dt.hour >= 6]
    if not day:
        return None

    temps = [h["temp_c"] for _, h in day]
    winds = [h["wind_kph"] / 3.6 for _, h in day]
    gusts = [h.get("gust_kph", h["wind_kph"]) / 3.6 for _, h in day]
    chances = [max(h.get("chance_of_rain", 0), h.get("chance_of_snow", 0)) for _, h in day]
    precip_mm = sum(h.get("precip_mm", 0) or 0 for _, h in day)
    categories = [classify(h["condition"]["code"])[0] for _, h in day]

    category = dominant_category(categories)

    return {
        "name": name,
        "tmin": round(min(temps)),
        "tmax": round(max(temps)),
        "wind_max": round(max(winds)),
        "gust_max": round(max(gusts)),
        "chance": int(max(chances)),
        "precip_mm": precip_mm,
        "category": category,
        "text": CATEGORY_TEXT[category],
        "hours": day,
    }


print("Отримуємо прогноз WeatherAPI по містах області...")

results = []
for name, lat, lon in CITIES:
    data = fetch_city(name, lat, lon)
    if not data:
        continue
    try:
        info = analyze_city(name, data)
    except (KeyError, IndexError, TypeError) as e:
        print(f"  {name}: неочікуваний формат даних ({type(e).__name__})")
        info = None
    if info:
        results.append(info)
        print(f"  {name}: ок")

if not results:
    print("Не вдалося отримати прогноз жодного міста.")
    raise SystemExit(1)

if len(results) < len(CITIES):
    print(f"Увага: отримано {len(results)} з {len(CITIES)} міст.")

now = datetime.now(ZoneInfo(TIMEZONE))
date_text = now.strftime("%d.%m.%Y")


# ------------------------------------------------------------
# Зведення по області за частинами доби
# ------------------------------------------------------------

PERIODS = [
    ("🌅", "Ранок", 6, 12),
    ("☀️", "День", 12, 18),
    ("🌆", "Вечір", 18, 24),
]


def temp_range(tmin, tmax):
    if tmin == tmax:
        return f"{tmin:+d}°C"
    return f"{tmin:+d}…{tmax:+d}°C"


def period_summary(start, end):
    temps, cats, chances = [], [], []
    for r in results:
        for dt, h in r["hours"]:
            if start <= dt.hour < end:
                temps.append(h["temp_c"])
                cats.append(classify(h["condition"]["code"])[0])
                chances.append(max(h.get("chance_of_rain", 0), h.get("chance_of_snow", 0)))
    if not temps:
        return None
    category = dominant_category(cats)
    return {
        "range": temp_range(round(min(temps)), round(max(temps))),
        "category": category,
        "text": CATEGORY_TEXT[category],
        "chance": int(max(chances)) if chances else 0,
    }


# ------------------------------------------------------------
# Текст для підпису під картинкою
# ------------------------------------------------------------

lines = [
    "🇺🇦 <b>СУМЩИНА · ПРОГНОЗ НА ДЕНЬ</b>",
    f"📅 {date_text}",
    "",
]

for icon, label, start, end in PERIODS:
    s = period_summary(start, end)
    if not s:
        continue
    extra = ""
    if SEVERITY[s["category"]] >= 4 and s["chance"] > 0:
        extra = f" · опади до {s['chance']}%"
    lines.append(
        f"{icon} <b>{label}:</b> {s['range']} · "
        f"{CATEGORY_EMOJI[s['category']]} {s['text']}{extra}"
    )

lines.append("")

rainy = sorted(
    [r for r in results if r["chance"] >= 30 or r["precip_mm"] >= 0.2],
    key=lambda r: r["chance"],
    reverse=True,
)
if rainy:
    cities_text = ", ".join(f"{r['name']} ({r['chance']}%)" for r in rainy)
    lines.append(f"🌧 <b>Опади:</b> {cities_text}")
else:
    lines.append("🌧 <b>Опади:</b> не очікуються")

windiest = max(results, key=lambda r: r["gust_max"])
lines.append(
    f"💨 <b>Вітер:</b> найсильніший — {windiest['name']}, "
    f"пориви до {windiest['gust_max']} м/с"
)

warmest = max(results, key=lambda r: r["tmax"])
coldest = min(results, key=lambda r: r["tmax"])
if warmest["tmax"] == coldest["tmax"]:
    lines.append(f"🌡 <b>Вдень:</b> до {warmest['tmax']:+d}°C по всій області")
else:
    lines.append(
        f"🌡 <b>Найтепліше:</b> {warmest['name']} {warmest['tmax']:+d}°C · "
        f"<b>найпрохолодніше:</b> {coldest['name']} {coldest['tmax']:+d}°C"
    )

lines.append("")
lines.append("🕒 Дані WeatherAPI.com")

caption = "\n".join(lines)


# ------------------------------------------------------------
# Малюємо картинку
# ------------------------------------------------------------

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]


def load_font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    print("ПОМИЛКА: не знайдено шрифт з підтримкою кирилиці (DejaVu/Liberation).")
    raise SystemExit(1)


def font_bold(size):
    return load_font(FONT_CANDIDATES_BOLD, size)


def font_regular(size):
    return load_font(FONT_CANDIDATES_REGULAR, size)


WIDTH = 1080
HEADER_H = 230
ROW_H = 132
ROW_GAP = 16
FOOTER_H = 90
HEIGHT = HEADER_H + len(results) * (ROW_H + ROW_GAP) + FOOTER_H


def gradient_background(width, height, top, bottom):
    img = Image.new("RGB", (width, height), top)
    px = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        px.line([(0, y), (width, y)], fill=color)
    return img


# --- Іконки ---------------------------------------------------

def draw_sun(d, cx, cy, r, color=(255, 205, 60)):
    import math
    for k in range(8):
        a = math.radians(k * 45)
        x1 = cx + math.cos(a) * (r + 6)
        y1 = cy + math.sin(a) * (r + 6)
        x2 = cx + math.cos(a) * (r + 16)
        y2 = cy + math.sin(a) * (r + 16)
        d.line([(x1, y1), (x2, y2)], fill=color, width=5)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def draw_cloud(d, cx, cy, s=1.0, color=(236, 241, 247)):
    w = int(34 * s)
    d.ellipse([cx - 2 * w, cy - w // 2, cx - w // 4, cy + w], fill=color)
    d.ellipse([cx - w, cy - w - w // 3, cx + w, cy + w // 2 + 6], fill=color)
    d.ellipse([cx + w // 4, cy - w // 2, cx + 2 * w, cy + w], fill=color)
    d.rounded_rectangle([cx - 2 * w + 8, cy, cx + 2 * w - 8, cy + w], radius=w // 2, fill=color)


def draw_icon(d, category, cx, cy):
    if category == "clear":
        draw_sun(d, cx, cy, 26)
    elif category == "partly":
        draw_sun(d, cx - 16, cy - 14, 20)
        draw_cloud(d, cx + 4, cy + 8, 0.8)
    elif category == "cloudy":
        draw_cloud(d, cx, cy, 0.9, (214, 222, 232))
    elif category == "fog":
        for i, off in enumerate((-20, -6, 8, 22)):
            d.line([(cx - 36 + (i % 2) * 8, cy + off), (cx + 36 - (i % 2) * 8, cy + off)],
                   fill=(200, 210, 222), width=6)
    elif category in ("rain", "heavy_rain"):
        draw_cloud(d, cx, cy - 12, 0.85, (190, 200, 214))
        n = 3 if category == "rain" else 4
        for k in range(n):
            x = cx - 28 + k * (56 // (n - 1))
            d.line([(x, cy + 22), (x - 7, cy + 40)], fill=(90, 170, 255), width=5)
    elif category in ("snow", "sleet"):
        draw_cloud(d, cx, cy - 12, 0.85, (200, 210, 224))
        for k in range(3):
            x = cx - 26 + k * 26
            d.ellipse([x - 5, cy + 26, x + 5, cy + 36], fill=(255, 255, 255))
        if category == "sleet":
            d.line([(cx + 30, cy + 22), (cx + 24, cy + 38)], fill=(90, 170, 255), width=4)
    elif category == "thunder":
        draw_cloud(d, cx, cy - 14, 0.85, (150, 160, 178))
        bolt = [(cx + 4, cy + 4), (cx - 14, cy + 28), (cx - 2, cy + 28),
                (cx - 10, cy + 48), (cx + 16, cy + 20), (cx + 3, cy + 20)]
        d.polygon(bolt, fill=(255, 214, 64))


# --- Сам малюнок -----------------------------------------------

img = gradient_background(WIDTH, HEIGHT, (22, 52, 96), (10, 24, 48)).convert("RGBA")
overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
od = ImageDraw.Draw(overlay)

# Картки під рядки (напівпрозорі)
for i in range(len(results)):
    y0 = HEADER_H + i * (ROW_H + ROW_GAP)
    od.rounded_rectangle([40, y0, WIDTH - 40, y0 + ROW_H], radius=28, fill=(255, 255, 255, 30))

img = Image.alpha_composite(img, overlay)
d = ImageDraw.Draw(img)

# Заголовок
d.text((60, 52), "СУМЩИНА", font=font_bold(78), fill=(255, 255, 255))
d.text((62, 150), f"Прогноз на день · {date_text}", font=font_regular(36), fill=(190, 208, 232))

# Стрічка кольорів прапора
d.rectangle([WIDTH - 130, 60, WIDTH - 60, 85], fill=(0, 91, 187))
d.rectangle([WIDTH - 130, 85, WIDTH - 60, 110], fill=(255, 213, 0))

f_city = font_bold(44)
f_text = font_regular(28)
f_temp = font_bold(50)
f_small = font_regular(27)

for i, r in enumerate(results):
    y0 = HEADER_H + i * (ROW_H + ROW_GAP)

    draw_icon(d, r["category"], 120, y0 + ROW_H // 2)

    d.text((200, y0 + 20), r["name"], font=f_city, fill=(255, 255, 255))
    d.text((202, y0 + 78), r["text"], font=f_text, fill=(190, 208, 232))

    temp = temp_range(r["tmin"], r["tmax"])
    d.text((WIDTH - 70, y0 + 18), temp, font=f_temp, fill=(255, 255, 255), anchor="ra")

    if r["chance"] > 0:
        rain_text = f"опади {r['chance']}%"
    else:
        rain_text = "без опадів"
    wind_text = f"вітер до {r['wind_max']} м/с"
    d.text((WIDTH - 70, y0 + 82), f"{rain_text} · {wind_text}",
           font=f_small, fill=(160, 190, 225), anchor="ra")

footer_y = HEIGHT - FOOTER_H + 28
d.text((60, footer_y), "Дані: WeatherAPI.com", font=font_regular(26), fill=(130, 158, 196))
d.text((WIDTH - 60, footer_y), "Сумський синоптик",
       font=font_regular(26), fill=(130, 158, 196), anchor="ra")

img.convert("RGB").save(IMAGE_PATH, "PNG", optimize=True)
print(f"Картинку збережено: {IMAGE_PATH} ({WIDTH}x{HEIGHT})")


# ------------------------------------------------------------
# Надсилання в Telegram
# ------------------------------------------------------------

print(f"Довжина підпису: {len(caption)} символів")

if DRY_RUN:
    print("DRY_RUN: у Telegram не надсилаємо.\n")
    print(caption)
    raise SystemExit(0)


def multipart_body(fields, file_field, file_name, file_bytes, mime):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for key, value in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += str(value).encode("utf-8") + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += (
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{file_name}"\r\n'
    ).encode()
    body += f"Content-Type: {mime}\r\n\r\n".encode()
    body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def telegram_call(method, data, headers=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    request = urllib.request.Request(url, data=data, method="POST", headers=headers or {})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


# Ліміт підпису під фото в Telegram — 1024 символи.
# Якщо не вміщається, відправляємо фото без підпису, а текст окремим повідомленням.
CAPTION_LIMIT = 1024
send_text_separately = len(caption) > CAPTION_LIMIT

with open(IMAGE_PATH, "rb") as f:
    image_bytes = f.read()

fields = {"chat_id": CHANNEL}
if not send_text_separately:
    fields["caption"] = caption
    fields["parse_mode"] = "HTML"

body, content_type = multipart_body(fields, "photo", IMAGE_PATH, image_bytes, "image/png")

print("Надсилаємо картинку в Telegram...")

try:
    result = telegram_call("sendPhoto", body, {"Content-Type": content_type})
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", errors="replace")
    print("ПОМИЛКА TELEGRAM:", e.code, detail)
    raise SystemExit(1)
except Exception as e:
    print("ПОМИЛКА TELEGRAM:", type(e).__name__)
    raise SystemExit(1)

if not result.get("ok"):
    print("Telegram повернув помилку:")
    print(result)
    raise SystemExit(1)

if send_text_separately:
    print("Підпис задовгий для фото, надсилаємо текст окремо...")
    payload = urllib.parse.urlencode({
        "chat_id": CHANNEL,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    try:
        result = telegram_call("sendMessage", payload)
    except Exception as e:
        print("ПОМИЛКА TELEGRAM:", type(e).__name__)
        raise SystemExit(1)
    if not result.get("ok"):
        print("Telegram повернув помилку:")
        print(result)
        raise SystemExit(1)

print()
print("=" * 40)
print("  ЗВЕДЕННЯ ПО ОБЛАСТІ ОПУБЛІКОВАНО!")
print("=" * 40)
print(f"Канал: {CHANNEL}")
