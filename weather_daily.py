import os
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import Counter

# ============================================================
# СУМСЬКИЙ СИНОПТИК — ПРОГНОЗ ТРИЧІ НА ДОБУ
#   07:00  morning — прогноз на поточну добу
#   13:00  noon    — оновлення прогнозу
#   19:00  evening — вечір + ніч + наступна доба
# Режим береться зі змінної середовища MODE.
# Якщо вона не задана — визначається за поточним часом.
# ============================================================

LATITUDE = 50.9077
LONGITUDE = 34.7981
TIMEZONE = "Europe/Kyiv"

BOT_TOKEN = os.environ.get("SUMY_BOT_TOKEN")
CHANNEL = os.environ.get("SUMY_CHANNEL")

if not BOT_TOKEN or not CHANNEL:
    print("ПОМИЛКА: не знайдено змінні SUMY_BOT_TOKEN або SUMY_CHANNEL")
    raise SystemExit(1)


# ------------------------------------------------------------
# Налаштування режимів
# Блок: (зсув у днях, значок, назва, година початку, година кінця, секція)
# Секція None — основна частина, "ЗАВТРА" — окремий розділ із заголовком
# ------------------------------------------------------------

MODES = {
    "morning": {
        "header": "🌅 <b>ДОБРОГО РАНКУ, СУМИ!</b>",
        "title": "Прогноз на сьогодні, {d0}",
        "blocks": [
            (0, "🌅", "РАНОК", 6, 12, None),
            (0, "☀️", "ДЕНЬ", 12, 18, None),
            (0, "🌆", "ВЕЧІР", 18, 24, None),
        ],
    },
    "noon": {
        "header": "☀️ <b>ОНОВЛЕННЯ ПРОГНОЗУ</b>",
        "title": "Що чекає на Суми далі, {d0}",
        "blocks": [
            (0, "☀️", "ДЕНЬ", 12, 18, None),
            (0, "🌆", "ВЕЧІР", 18, 24, None),
            (1, "🌙", "НІЧ", 0, 6, None),
        ],
    },
    "evening": {
        "header": "🌙 <b>ВЕЧІР, НІЧ ТА ЗАВТРА</b>",
        "title": "Прогноз від {d0}",
        "blocks": [
            (0, "🌆", "ВЕЧІР", 18, 24, None),
            (1, "🌙", "НІЧ", 0, 6, None),
            (1, "🌅", "РАНОК", 6, 12, "ЗАВТРА"),
            (1, "☀️", "ДЕНЬ", 12, 18, "ЗАВТРА"),
            (1, "🌆", "ВЕЧІР", 18, 24, "ЗАВТРА"),
        ],
    },
}


# ------------------------------------------------------------
# Опис погодних кодів Open-Meteo
# ------------------------------------------------------------

WEATHER_CODES = {
    0: "Ясно",
    1: "Переважно ясно",
    2: "Мінлива хмарність",
    3: "Хмарно",
    45: "Туман",
    48: "Туман",
    51: "Мряка",
    53: "Мряка",
    55: "Сильна мряка",
    56: "Крижана мряка",
    57: "Крижана мряка",
    61: "Невеликий дощ",
    63: "Дощ",
    65: "Сильний дощ",
    66: "Крижаний дощ",
    67: "Крижаний дощ",
    71: "Невеликий сніг",
    73: "Сніг",
    75: "Сильний сніг",
    77: "Снігові зерна",
    80: "Короткочасний дощ",
    81: "Злива",
    82: "Сильна злива",
    85: "Невеликий сніг",
    86: "Сильний сніг",
    95: "Гроза",
    96: "Гроза з градом",
    99: "Гроза з сильним градом",
}

WEATHER_ICONS = {
    "Ясно": "☀️",
    "Переважно ясно": "🌤",
    "Мінлива хмарність": "⛅",
    "Хмарно": "☁️",
    "Туман": "🌫",
    "Мряка": "🌦",
    "Сильна мряка": "🌧",
    "Крижана мряка": "🌧",
    "Невеликий дощ": "🌦",
    "Дощ": "🌧",
    "Сильний дощ": "🌧",
    "Крижаний дощ": "🌧",
    "Невеликий сніг": "🌨",
    "Сніг": "❄️",
    "Сильний сніг": "❄️",
    "Снігові зерна": "🌨",
    "Короткочасний дощ": "🌦",
    "Злива": "🌧",
    "Сильна злива": "⛈",
    "Гроза": "⛈",
    "Гроза з градом": "⛈",
    "Гроза з сильним градом": "⛈",
}


# ------------------------------------------------------------
# Напрямок вітру
# ------------------------------------------------------------

def wind_direction(degrees):
    directions = [
        "Північний",
        "Північно-східний",
        "Східний",
        "Південно-східний",
        "Південний",
        "Південно-західний",
        "Західний",
        "Північно-західний",
    ]
    index = int((degrees + 22.5) / 45) % 8
    return directions[index]


# ------------------------------------------------------------
# Визначаємо режим
# ------------------------------------------------------------

now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)

mode = os.environ.get("MODE", "").strip().lower()

if mode not in MODES:
    if mode:
        print(f"Невідомий режим '{mode}', визначаємо за часом.")
    if now.hour < 10:
        mode = "morning"
    elif now.hour < 16:
        mode = "noon"
    else:
        mode = "evening"

config = MODES[mode]
print(f"Режим: {mode} | Київський час: {now:%d.%m.%Y %H:%M}")

# Відсікаємо години, що вже минули (до початку поточної години)
cutoff = now.replace(minute=0, second=0, microsecond=0)


# ------------------------------------------------------------
# Запит до Open-Meteo
# ------------------------------------------------------------

params = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "timezone": TIMEZONE,
    "forecast_days": 2,
    "wind_speed_unit": "ms",   # без цього Open-Meteo віддає км/год
    "hourly": ",".join([
        "temperature_2m",
        "apparent_temperature",
        "precipitation_probability",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
    ]),
}

url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)

print("Отримуємо прогноз Open-Meteo...")

try:
    with urllib.request.urlopen(url, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
except Exception as e:
    print("Помилка отримання прогнозу:", e)
    raise SystemExit(1)

hourly = data["hourly"]

times = hourly["time"]
temperatures = hourly["temperature_2m"]
feels = hourly["apparent_temperature"]
precip_probability = hourly["precipitation_probability"]
precipitation = hourly["precipitation"]
weather_codes = hourly["weather_code"]
wind_speeds = hourly["wind_speed_10m"]
wind_directions = hourly["wind_direction_10m"]
wind_gusts = hourly["wind_gusts_10m"]

parsed_times = [datetime.fromisoformat(t) for t in times]


# ------------------------------------------------------------
# Допоміжні функції
# ------------------------------------------------------------

def clean(values):
    """Прибирає None (Open-Meteo іноді віддає порожні значення)."""
    return [v for v in values if v is not None]


def select_indices(day_offset, start_hour, end_hour):
    target_date = (now + timedelta(days=day_offset)).date()
    result = []
    for i, dt in enumerate(parsed_times):
        if dt.date() != target_date:
            continue
        if not (start_hour <= dt.hour < end_hour):
            continue
        if dt < cutoff:
            continue
        result.append(i)
    return result


def make_period(indices, icon, name, start_hour, end_hour):
    if not indices:
        return None

    temps = clean(temperatures[i] for i in indices)
    feels_period = clean(feels[i] for i in indices)
    rain_prob = clean(precip_probability[i] for i in indices)
    rain_amount = clean(precipitation[i] for i in indices)
    codes = clean(weather_codes[i] for i in indices)
    wind = clean(wind_speeds[i] for i in indices)
    gusts = clean(wind_gusts[i] for i in indices)
    wind_dirs = clean(wind_directions[i] for i in indices)

    if not (temps and feels_period and codes and wind and wind_dirs):
        return None

    # Якщо блок почався вже після своєї номінальної години — показуємо реальний початок
    first_hour = parsed_times[indices[0]].hour
    shown_start = max(start_hour, first_hour)

    temp_min = round(min(temps))
    temp_max = round(max(temps))
    feels_min = round(min(feels_period))
    feels_max = round(max(feels_period))

    rain_probability = max(rain_prob) if rain_prob else 0
    rain_total = sum(rain_amount) if rain_amount else 0

    most_common_code = Counter(codes).most_common(1)[0][0]
    weather = WEATHER_CODES.get(most_common_code, "Змінна погода")
    weather_icon = WEATHER_ICONS.get(weather, "🌦")

    wind_min = round(min(wind))
    wind_max = round(max(wind))
    gust_max = round(max(gusts)) if gusts else wind_max

    common_direction = Counter(
        wind_direction(d) for d in wind_dirs
    ).most_common(1)[0][0]

    if temp_min == temp_max:
        temp_text = f"{temp_min:+d}°C"
    else:
        temp_text = f"{temp_min:+d}…{temp_max:+d}°C"

    if feels_min == feels_max:
        feels_text = f"{feels_min:+d}°C"
    else:
        feels_text = f"{feels_min:+d}…{feels_max:+d}°C"

    if rain_probability == 0:
        precipitation_text = "Опади малоймовірні"
    else:
        precipitation_text = f"Ймовірність опадів до {rain_probability}%"
        if rain_total >= 0.1:
            precipitation_text += f" · {rain_total:.1f} мм"

    if wind_min == wind_max:
        wind_text = f"{common_direction}, {wind_min} м/с"
    else:
        wind_text = f"{common_direction}, {wind_min}–{wind_max} м/с"

    if gust_max > wind_max:
        wind_text += f" · пориви до {gust_max} м/с"

    return (
        f"{icon} <b>{name}</b> · "
        f"{shown_start:02d}:00–{end_hour:02d}:00\n"
        f"🌡 {temp_text} · відчувається {feels_text}\n"
        f"{weather_icon} {weather}\n"
        f"🌧 {precipitation_text}\n"
        f"💨 {wind_text}\n"
    )


# ------------------------------------------------------------
# Формуємо повідомлення
# ------------------------------------------------------------

today_text = now.strftime("%d.%m.%Y")
tomorrow_text = (now + timedelta(days=1)).strftime("%d.%m.%Y")

if mode == "evening":
    d0 = f"{now:%H}:00, {today_text}"
else:
    d0 = today_text

message = (
    "🇺🇦 <b>СУМСЬКИЙ СИНОПТИК</b>\n"
    f"{config['header']}\n"
    f"🌦 <b>{config['title'].format(d0=d0)}</b>\n"
    "📍 Суми\n\n"
)

blocks_added = 0
current_section = None

for day_offset, icon, name, start_hour, end_hour, section in config["blocks"]:
    indices = select_indices(day_offset, start_hour, end_hour)
    block = make_period(indices, icon, name, start_hour, end_hour)

    if not block:
        continue

    if section != current_section:
        current_section = section
        if section:
            message += f"━━━ <b>📅 {section}, {tomorrow_text}</b> ━━━\n\n"

    message += block + "\n"
    blocks_added += 1

if blocks_added == 0:
    print("Не вдалося знайти майбутні години прогнозу.")
    raise SystemExit(1)

message += (
    "━━━━━━━━━━━━━━━━━━\n"
    "📍 Суми\n"
    "🕒 Дані Open-Meteo\n"
    "🔄 Прогноз оновлюється тричі на добу: 07:00, 13:00, 19:00"
)


# ------------------------------------------------------------
# Надсилання в Telegram
# ------------------------------------------------------------

telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

payload = {
    "chat_id": CHANNEL,
    "text": message,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
}

encoded = urllib.parse.urlencode(payload).encode("utf-8")

print("Формуємо прогноз...")
print(f"Довжина повідомлення: {len(message)} символів")
print("Надсилаємо прогноз у Telegram...")

try:
    request = urllib.request.Request(
        telegram_url,
        data=encoded,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
except Exception as e:
    print("ПОМИЛКА TELEGRAM:", e)
    raise SystemExit(1)

if result.get("ok"):
    print()
    print("=" * 40)
    print("  ПРОГНОЗ УСПІШНО ОПУБЛІКОВАНО!")
    print("=" * 40)
    print()
    print(f"Режим: {mode}")
    print(f"Канал: {CHANNEL}")
else:
    print()
    print("Telegram повернув помилку:")
    print(result)
    raise SystemExit(1)
