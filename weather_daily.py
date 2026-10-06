import urllib.request
import urllib.parse
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter

# ============================================================
# СУМСКОЙ СИНОПТИК — СУТОЧНЫЙ ПРОГНОЗ
# ============================================================

LATITUDE = 50.9077
LONGITUDE = 34.7981
TIMEZONE = "Europe/Kyiv"

BOT_TOKEN = __import__("os").environ.get("SUMY_BOT_TOKEN")
CHANNEL = __import__("os").environ.get("SUMY_CHANNEL")

if not BOT_TOKEN or not CHANNEL:
    print("ОШИБКА: не найдены переменные SUMY_BOT_TOKEN или SUMY_CHANNEL")
    raise SystemExit(1)


# ------------------------------------------------------------
# Описание погодных кодов Open-Meteo
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


# ------------------------------------------------------------
# Значки погоди
# ------------------------------------------------------------

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
    "Крижаний дощ": "🌧",
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
        "Північно-західний"
    ]

    index = int((degrees + 22.5) / 45) % 8
    return directions[index]

# ------------------------------------------------------------
# Запит до Open-Meteo
# ------------------------------------------------------------

params = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "timezone": TIMEZONE,
    "forecast_days": 2,

    "hourly": ",".join([
        "temperature_2m",
        "apparent_temperature",
        "precipitation_probability",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
    ])
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


# ------------------------------------------------------------
# Беремо поточну дату та наступні 24 години
# ------------------------------------------------------------

now = datetime.now(ZoneInfo("Europe/Kyiv")).replace(tzinfo=None)

current_date = now.strftime("%Y-%m-%d")
current_hour = now.hour

selected_indices = []

for i, t in enumerate(times):
    dt = datetime.fromisoformat(t)

    if dt >= now:
        selected_indices.append(i)

    if len(selected_indices) >= 24:
        break


if not selected_indices:
    print("Не вдалося знайти майбутні години прогнозу.")
    raise SystemExit(1)


# ------------------------------------------------------------
# Визначаємо блоки доби
# ------------------------------------------------------------

periods = [
    ("🌅", "РАНОК", 6, 12),
    ("☀️", "ДЕНЬ", 12, 18),
    ("🌆", "ВЕЧІР", 18, 24),
    ("🌙", "НІЧ", 0, 6),
]


def get_period(hour):
    if 6 <= hour < 12:
        return 0
    elif 12 <= hour < 18:
        return 1
    elif 18 <= hour < 24:
        return 2
    else:
        return 3


# ------------------------------------------------------------
# Формування блока прогнозу
# ------------------------------------------------------------

def make_period(indices, icon, name, start_hour, end_hour):

    if not indices:
        return None

    temps = [temperatures[i] for i in indices]
    feels_period = [feels[i] for i in indices]
    rain_prob = [precip_probability[i] for i in indices]
    rain_amount = [precipitation[i] for i in indices]
    codes = [weather_codes[i] for i in indices]
    wind = [wind_speeds[i] for i in indices]
    gusts = [wind_gusts[i] for i in indices]
    wind_dirs = [wind_directions[i] for i in indices]

    # Температура
    temp_min = round(min(temps))
    temp_max = round(max(temps))

    feels_min = round(min(feels_period))
    feels_max = round(max(feels_period))

    # Опади
    rain_probability = max(rain_prob)
    rain_total = sum(rain_amount)

    # Найбільш характерна погода
    most_common_code = Counter(codes).most_common(1)[0][0]
    weather = WEATHER_CODES.get(
        most_common_code,
        "Змінна погода"
    )

    weather_icon = WEATHER_ICONS.get(weather, "🌦")

    # Вітер
    wind_min = round(min(wind))
    wind_max = round(max(wind))
    gust_max = round(max(gusts))

    # Найчастіший напрямок
    direction_names = [
        wind_direction(d) for d in wind_dirs
    ]

    common_direction = Counter(
        direction_names
    ).most_common(1)[0][0]

    # Формат температури
    if temp_min == temp_max:
        temp_text = f"{temp_min:+d}°C"
    else:
        temp_text = f"{temp_min:+d}…{temp_max:+d}°C"

    if feels_min == feels_max:
        feels_text = f"{feels_min:+d}°C"
    else:
        feels_text = f"{feels_min:+d}…{feels_max:+d}°C"

    # Формат опадів
    if rain_probability == 0:
        precipitation_text = "Опади малоймовірні"
    else:
        precipitation_text = f"Ймовірність опадів до {rain_probability}%"

        if rain_total >= 0.1:
            precipitation_text += f" · {rain_total:.1f} мм"

    # Формат вітру
    if wind_min == wind_max:
        wind_text = f"{common_direction}, {wind_min} м/с"
    else:
        wind_text = (
            f"{common_direction}, "
            f"{wind_min}–{wind_max} м/с"
        )

    if gust_max > wind_max:
        wind_text += f" · пориви до {gust_max} м/с"

    text = (
        f"{icon} <b>{name}</b> · "
        f"{start_hour:02d}:00–{end_hour:02d}:00\n"
        f"🌡 {temp_text} · відчувається {feels_text}\n"
        f"{weather_icon} {weather}\n"
        f"🌧 {precipitation_text}\n"
        f"💨 {wind_text}\n"
    )

    return text


# ------------------------------------------------------------
# Розподіляємо години по чотирьох періодах
# ------------------------------------------------------------

period_indices = {
    0: [],
    1: [],
    2: [],
    3: [],
}

for i in selected_indices:
    dt = datetime.fromisoformat(times[i])
    period_number = get_period(dt.hour)
    period_indices[period_number].append(i)


# ------------------------------------------------------------
# Формуємо повідомлення
# ------------------------------------------------------------

forecast_dates = []

for i in selected_indices:
    dt = datetime.fromisoformat(times[i])
    date_text = dt.strftime("%d.%m.%Y")

    if date_text not in forecast_dates:
        forecast_dates.append(date_text)

if len(forecast_dates) == 1:
    date_header = forecast_dates[0]
else:
    date_header = f"{forecast_dates[0]} – {forecast_dates[-1]}"


message = (
    "🇺🇦 <b>СУМСЬКИЙ СИНОПТИК</b>\n"
    f"🌦 <b>Прогноз на {date_header}</b>\n"
    "📍 Суми\n\n"
)
for number, period in enumerate(periods):

    icon, name, start_hour, end_hour = period

    block = make_period(
        period_indices[number],
        icon,
        name,
        start_hour,
        end_hour
    )

    if block:
        message += block + "\n"


message += (
    "━━━━━━━━━━━━━━━━━━\n"
    "📍 Суми\n"
    "🕒 Дані Open-Meteo\n"
    "🔄 Прогноз оновлюється регулярно"
)


# ------------------------------------------------------------
# Надсилання в Telegram
# ------------------------------------------------------------

telegram_url = (
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
)

payload = {
    "chat_id": CHANNEL,
    "text": message,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
}

encoded = urllib.parse.urlencode(payload).encode("utf-8")

print("Формуємо добовий прогноз...")
print(f"Довжина повідомлення: {len(message)} символів")
print("Надсилаємо прогноз у Telegram...")

try:
    request = urllib.request.Request(
        telegram_url,
        data=encoded,
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

except Exception as e:
    print("ПОМИЛКА TELEGRAM:", e)
    raise SystemExit(1)


if result.get("ok"):
    print()
    print("=" * 40)
    print("  ДОБОВИЙ ПРОГНОЗ УСПІШНО ОПУБЛІКОВАНО!")
    print("=" * 40)
    print()
    print(f"Канал: {CHANNEL}")
else:
    print()
    print("Telegram повернув помилку:")
    print(result)
