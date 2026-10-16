import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ============================================================
# СУМСЬКИЙ СИНОПТИК — ПРОГНОЗ ТРИЧІ НА ДОБУ (картка-картинка + короткий текст + теги)
#   07:00  morning — прогноз на поточну добу
#   13:00  noon    — оновлення прогнозу
#   19:00  evening — вечір + ніч + наступна доба
# Режим береться зі змінної середовища MODE; якщо її немає — за поточним часом.
#
# Режим перегляду без публікації:  DRY_RUN=1 python weather_daily.py
# (збереже forecast.png і надрукує підпис; BOT_TOKEN у цьому режимі не потрібен)
#
# Для картинки потрібні: pip install pillow matplotlib   (matplotlib — лише заради шрифту DejaVu з кирилицею)
# Якщо картинку створити не вдалося — скрипт надішле звичайний текстовий прогноз.
# ============================================================

LATITUDE = 50.9077
LONGITUDE = 34.7981
TIMEZONE = "Europe/Kyiv"
CHANNEL_HANDLE = "t.me/sumskoy_sinoptik"
OUT_PNG = "forecast.png"

BOT_TOKEN = os.environ.get("SUMY_BOT_TOKEN")
CHANNEL = os.environ.get("SUMY_CHANNEL")
DRY_RUN = os.environ.get("DRY_RUN", "").strip() == "1"

if not DRY_RUN and (not BOT_TOKEN or not CHANNEL):
    print("ПОМИЛКА: не знайдено змінні SUMY_BOT_TOKEN або SUMY_CHANNEL")
    raise SystemExit(1)


# ------------------------------------------------------------
# Налаштування режимів
# Блок: (зсув у днях, значок, назва, година початку, година кінця, секція)
# ------------------------------------------------------------

MODES = {
    "morning": {
        "header": "🌅 <b>ДОБРОГО РАНКУ, СУМИ!</b>",
        "title": "Прогноз на сьогодні, {d0}",
        "image_title": "Доброго ранку, Суми!",
        "label": "Сьогодні",
        "palette": ("#FF9A5B", "#D9488A"),
        "blocks": [
            (0, "🌅", "РАНОК", 6, 12, None),
            (0, "☀️", "ДЕНЬ", 12, 18, None),
            (0, "🌆", "ВЕЧІР", 18, 24, None),
        ],
    },
    "noon": {
        "header": "☀️ <b>ОНОВЛЕННЯ ПРОГНОЗУ</b>",
        "title": "Що чекає на Суми далі, {d0}",
        "image_title": "Оновлення прогнозу",
        "label": "Далі",
        "palette": ("#4FA8F5", "#2D5FD0"),
        "blocks": [
            (0, "☀️", "ДЕНЬ", 12, 18, None),
            (0, "🌆", "ВЕЧІР", 18, 24, None),
            (1, "🌙", "НІЧ", 0, 6, None),
        ],
    },
    "evening": {
        "header": "🌙 <b>ВЕЧІР, НІЧ ТА ЗАВТРА</b>",
        "title": "Прогноз від {d0}",
        "image_title": "Вечір, ніч та завтра",
        "label": "Завтра",
        "palette": ("#1E2A5E", "#6B3FA0"),
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
    0: "Ясно", 1: "Переважно ясно", 2: "Мінлива хмарність", 3: "Хмарно",
    45: "Туман", 48: "Туман",
    51: "Мряка", 53: "Мряка", 55: "Сильна мряка", 56: "Крижана мряка", 57: "Крижана мряка",
    61: "Невеликий дощ", 63: "Дощ", 65: "Сильний дощ", 66: "Крижаний дощ", 67: "Крижаний дощ",
    71: "Невеликий сніг", 73: "Сніг", 75: "Сильний сніг", 77: "Снігові зерна",
    80: "Короткочасний дощ", 81: "Злива", 82: "Сильна злива",
    85: "Невеликий сніг", 86: "Сильний сніг",
    95: "Гроза", 96: "Гроза з градом", 99: "Гроза з сильним градом",
}

WEATHER_ICONS = {
    "Ясно": "☀️", "Переважно ясно": "🌤", "Мінлива хмарність": "⛅", "Хмарно": "☁️",
    "Туман": "🌫", "Мряка": "🌦", "Сильна мряка": "🌧", "Крижана мряка": "🌧",
    "Невеликий дощ": "🌦", "Дощ": "🌧", "Сильний дощ": "🌧", "Крижаний дощ": "🌧",
    "Невеликий сніг": "🌨", "Сніг": "❄️", "Сильний сніг": "❄️", "Снігові зерна": "🌨",
    "Короткочасний дощ": "🌦", "Злива": "🌧", "Сильна злива": "⛈",
    "Гроза": "⛈", "Гроза з градом": "⛈", "Гроза з сильним градом": "⛈",
}

SNOW_CODES = {71, 73, 75, 77, 85, 86}
STORM_CODES = {95, 96, 99}
FOG_CODES = {45, 48}


def icon_kind(code):
    """Код погоди -> тип намальованого значка."""
    if code == 0:
        return "clear"
    if code == 1:
        return "mostly"
    if code == 2:
        return "partly"
    if code == 3:
        return "cloud"
    if code in FOG_CODES:
        return "fog"
    if code in (51, 53, 61, 80):
        return "drizzle"
    if code in (55, 56, 57, 63, 66, 67, 81):
        return "rain"
    if code in (65, 82):
        return "heavy"
    if code in SNOW_CODES:
        return "snow"
    if code in STORM_CODES:
        return "storm"
    return "cloud"


# ------------------------------------------------------------
# Вітер
# ------------------------------------------------------------

DIRECTIONS = ["Північний", "Північно-східний", "Східний", "Південно-східний",
              "Південний", "Південно-західний", "Західний", "Північно-західний"]
DIRECTIONS_SHORT = {
    "Північний": "Півн.", "Північно-східний": "ПнСх", "Східний": "Сх.", "Південно-східний": "ПдСх",
    "Південний": "Півд.", "Південно-західний": "ПдЗх", "Західний": "Зх.", "Північно-західний": "ПнЗх",
}


def wind_direction(degrees):
    return DIRECTIONS[int((degrees + 22.5) / 45) % 8]


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
print(f"Режим: {mode} | Київський час: {now:%d.%m.%Y %H:%M}" + (" | DRY RUN" if DRY_RUN else ""))

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
        "temperature_2m", "apparent_temperature", "precipitation_probability", "precipitation",
        "weather_code", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    ]),
}

url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)

print("Отримуємо прогноз Open-Meteo...")

data = None
for attempt in range(1, 4):          # до 3 спроб: на runner-ах GitHub мережа іноді «моргає»
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        break
    except Exception as e:
        print(f"Спроба {attempt}/3: помилка отримання прогнозу: {e}")
        if attempt < 3:
            time.sleep(5)

if data is None:
    print("Не вдалося отримати прогноз Open-Meteo.")
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
# Розрахунок періодів
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


def make_period(indices, icon, name, start_hour, end_hour, section):
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

    first_hour = parsed_times[indices[0]].hour
    code = Counter(codes).most_common(1)[0][0]
    weather = WEATHER_CODES.get(code, "Змінна погода")
    wind_max = round(max(wind))

    return {
        "icon": icon,
        "name": name,
        "section": section,
        "start": max(start_hour, first_hour),
        "end": end_hour,
        "night": end_hour <= 6 or start_hour >= 18,
        "temp_min": round(min(temps)),
        "temp_max": round(max(temps)),
        "feels_min": round(min(feels_period)),
        "feels_max": round(max(feels_period)),
        "rain_probability": max(rain_prob) if rain_prob else 0,
        "rain_total": sum(rain_amount) if rain_amount else 0,
        "code": code,
        "codes": codes,
        "weather": weather,
        "weather_icon": WEATHER_ICONS.get(weather, "🌦"),
        "wind_min": round(min(wind)),
        "wind_max": wind_max,
        "gust_max": round(max(gusts)) if gusts else wind_max,
        "direction": Counter(wind_direction(d) for d in wind_dirs).most_common(1)[0][0],
    }


def rng(lo, hi, unit="°C"):
    return f"{lo:+d}{unit}" if lo == hi else f"{lo:+d}…{hi:+d}{unit}"


def period_text(p):
    """Текстовий блок (запасний варіант, якщо картинку створити не вдалося)."""
    if p["rain_probability"] == 0:
        precip = "Опади малоймовірні"
    else:
        precip = f"Ймовірність опадів до {p['rain_probability']}%"
        if p["rain_total"] >= 0.1:
            precip += f" · {p['rain_total']:.1f} мм"

    if p["wind_min"] == p["wind_max"]:
        wind = f"{p['direction']}, {p['wind_min']} м/с"
    else:
        wind = f"{p['direction']}, {p['wind_min']}–{p['wind_max']} м/с"
    if p["gust_max"] > p["wind_max"]:
        wind += f" · пориви до {p['gust_max']} м/с"

    return (
        f"{p['icon']} <b>{p['name']}</b> · {p['start']:02d}:00–{p['end']:02d}:00\n"
        f"🌡 {rng(p['temp_min'], p['temp_max'])} · відчувається {rng(p['feels_min'], p['feels_max'])}\n"
        f"{p['weather_icon']} {p['weather']}\n"
        f"🌧 {precip}\n"
        f"💨 {wind}\n"
    )


today_text = now.strftime("%d.%m.%Y")
tomorrow_text = (now + timedelta(days=1)).strftime("%d.%m.%Y")
d0 = f"{now:%H}:00, {today_text}" if mode == "evening" else today_text

items = []                      # ("section", "ЗАВТРА, 15.10.2026") | ("period", dict)
current_section = None
for day_offset, icon, name, start_hour, end_hour, section in config["blocks"]:
    p = make_period(select_indices(day_offset, start_hour, end_hour), icon, name, start_hour, end_hour, section)
    if not p:
        continue
    if section != current_section:
        current_section = section
        if section:
            items.append(("section", f"{section}, {tomorrow_text}"))
    items.append(("period", p))

periods = [p for kind, p in items if kind == "period"]
if not periods:
    print("Не вдалося знайти майбутні години прогнозу.")
    raise SystemExit(1)


# ------------------------------------------------------------
# Короткий підпис і теги
# ------------------------------------------------------------

def build_summary():
    used = [p for p in periods if p["section"]] or periods
    label = config["label"] if used is not periods or mode != "evening" else "Далі"
    all_codes = {c for p in periods for c in p["codes"]}

    tmin = min(p["temp_min"] for p in used)
    tmax = max(p["temp_max"] for p in used)
    main_weather = Counter(p["weather"] for p in used).most_common(1)[0][0]
    w_icon = WEATHER_ICONS.get(main_weather, "🌦")
    prob = max(p["rain_probability"] for p in used)
    rain_sum = sum(p["rain_total"] for p in used)
    wind_top = max(p["wind_max"] for p in used)
    gust_top = max(p["gust_max"] for p in used)

    lines = [
        config["header"],
        config["title"].format(d0=d0),
        "",
        f"🌡 {label}: <b>{minus(rng(tmin, tmax))}</b> · {w_icon} {main_weather}",
    ]
    lines.append(f"🌧 Опади: до {prob}%" + (f" · {rain_sum:.1f} мм" if rain_sum >= 0.5 else "")
                 if prob >= 30 else "🌧 Опади малоймовірні")
    wind_line = f"💨 Вітер: до {wind_top} м/с"
    if gust_top > wind_top:
        wind_line += f", пориви до {gust_top} м/с"
    lines.append(wind_line)

    # Попередження (не більше трьох)
    alerts = []
    if all_codes & STORM_CODES:
        alerts.append("⛈ Можлива гроза")
    if gust_top >= 15:
        alerts.append(f"⚠️ Сильні пориви вітру — до {gust_top} м/с")
    if rain_sum >= 10:
        alerts.append(f"⚠️ Значні опади: близько {rain_sum:.0f} мм")
    if all_codes & SNOW_CODES:
        alerts.append("❄️ Можливий сніг")
    if tmin <= 0:
        alerts.append(f"🥶 Заморозки: до {str(tmin).replace('-', '−')}°C")
    if all_codes & FOG_CODES:
        alerts.append("🌫 Туман — обережно на дорогах")
    if tmax >= 30:
        alerts.append("🔥 Спека")
    if alerts:
        lines.append("")
        lines += alerts[:3]

    tags = ["#Суми", "#ПогодаСуми", "#Прогноз"]
    if prob >= 60 and rain_sum >= 0.5 and not (all_codes & SNOW_CODES):
        tags.append("#Дощ")
    if all_codes & SNOW_CODES:
        tags.append("#Сніг")
    if all_codes & STORM_CODES:
        tags.append("#Гроза")
    if all_codes & FOG_CODES:
        tags.append("#Туман")
    if gust_top >= 15:
        tags.append("#СильнийВітер")
    elif gust_top >= 12:
        tags.append("#Вітер")
    if tmin <= 0:
        tags.append("#Заморозки")
    if tmax >= 30:
        tags.append("#Спека")
    tags.append("#СумськийСиноптик")

    lines += ["", " ".join(tags)]
    return "\n".join(lines), " ".join(tags)


# ------------------------------------------------------------
# Малювання картки (Pillow)
# ------------------------------------------------------------

SC = 2            # малюємо у 2× та зменшуємо — гладкі краї
W = 1080
MARGIN = 36
ROW_H = 214
GAP = 22
SECTION_H = 84
HEADER_H = 262
FOOTER_H = 120

NAVY = (27, 42, 65)
MUTED = (107, 122, 144)
LINE = (227, 233, 242)


def px(v):
    return int(round(v * SC))


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def temp_color(t):
    for limit, color in ((-5, "#4C6EF5"), (0, "#228BE6"), (8, "#1098AD"),
                         (15, "#2F9E44"), (22, "#F08C00"), (30, "#E8590C")):
        if t <= limit:
            return hex_rgb(color)
    return hex_rgb("#C92A2A")


def find_font(bold):
    from PIL import ImageFont  # noqa: F401  (перевірка, що Pillow є)
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    alt = "arialbd.ttf" if bold else "arial.ttf"
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
              "/Library/Fonts", "C:/Windows/Fonts"):
        for n in (name, alt):
            path = os.path.join(d, n)
            if os.path.exists(path):
                return path
    try:
        import matplotlib
        path = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", name)
        if os.path.exists(path):
            return path
    except ImportError:
        pass
    raise RuntimeError("Не знайдено шрифт з кирилицею (встановіть matplotlib або fonts-dejavu)")


_font_cache = {}


def font(size, bold=False):
    from PIL import ImageFont
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(find_font(bold), px(size))
    return _font_cache[key]


def fit_font(text, size, bold, max_width, min_size=20):
    """Зменшує шрифт, поки текст не влізе у задану ширину."""
    while size > min_size and font(size, bold).getlength(text) > px(max_width):
        size -= 1
    return font(size, bold)


def minus(text):
    return text.replace("-", "−")


def icon_image(kind, night, size):
    """Малює значок погоди в квадраті size×size (прозорий фон)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def u(v):
        return v * size / 100.0

    def circle(cx, cy, r, fill):
        d.ellipse([u(cx - r), u(cy - r), u(cx + r), u(cy + r)], fill=fill)

    def cloud(ox, oy, sc, color):
        circle(ox + 22 * sc, oy + 30 * sc, 17 * sc, color)
        circle(ox + 42 * sc, oy + 22 * sc, 22 * sc, color)
        circle(ox + 62 * sc, oy + 32 * sc, 15 * sc, color)
        d.rounded_rectangle([u(ox + 8 * sc), u(oy + 30 * sc), u(ox + 75 * sc), u(oy + 47 * sc)],
                            radius=u(8 * sc), fill=color)

    def sun(cx, cy, r):
        ray = (255, 183, 3, 255)
        import math
        for k in range(8):
            a = math.radians(k * 45)
            d.line([u(cx + math.cos(a) * (r + 6)), u(cy + math.sin(a) * (r + 6)),
                    u(cx + math.cos(a) * (r + 15)), u(cy + math.sin(a) * (r + 15))],
                   fill=ray, width=max(2, int(u(5))))
        circle(cx, cy, r, (255, 196, 20, 255))
        circle(cx, cy, r - 5, (255, 214, 64, 255))

    def moon(cx, cy, r):
        circle(cx, cy, r, (246, 226, 127, 255))
        circle(cx + r * 0.42, cy - r * 0.32, r * 0.86, (0, 0, 0, 0))       # виріз місяця
        for sx, sy, sr in ((80, 24, 3), (88, 44, 2.2), (70, 12, 2)):
            circle(sx, sy, sr, (246, 226, 127, 255))

    def drops(n, heavy=False):
        import math
        xs = [28 + k * (46 / max(1, n - 1)) for k in range(n)] if n > 1 else [50]
        for k, x in enumerate(xs):
            y = 81 + (k % 2) * 6
            d.line([u(x), u(y), u(x - 5), u(y + (13 if heavy else 10))],
                   fill=(77, 171, 247, 255), width=max(2, int(u(4.2 if heavy else 3.4))))

    light, mid, dark = (205, 217, 233, 255), (150, 168, 192, 255), (92, 108, 130, 255)

    if kind == "clear":
        moon(48, 50, 29) if night else sun(50, 50, 21)
    elif kind == "mostly":
        moon(40, 44, 24) if night else sun(42, 44, 19)
        cloud(40, 52, 0.62, light)
    elif kind == "partly":
        moon(34, 36, 19) if night else sun(34, 36, 15)
        cloud(18, 36, 0.98, mid if night else light)
    elif kind == "cloud":
        cloud(6, 24, 1.12, mid)
    elif kind == "fog":
        cloud(8, 12, 1.0, light)
        for k, (x1, x2) in enumerate(((16, 80), (24, 88), (16, 72))):
            y = 66 + k * 11
            d.line([u(x1), u(y), u(x2), u(y)], fill=mid, width=max(2, int(u(5))))
    elif kind == "drizzle":
        cloud(8, 14, 1.05, mid)
        drops(3)
    elif kind == "rain":
        cloud(8, 12, 1.05, mid)
        drops(5)
    elif kind == "heavy":
        cloud(8, 10, 1.05, dark)
        drops(6, heavy=True)
    elif kind == "snow":
        import math
        cloud(8, 12, 1.05, light if not night else mid)
        for cx, cy in ((30, 84), (50, 90), (70, 84)):
            for k in range(3):
                a = math.radians(k * 60)
                d.line([u(cx - math.cos(a) * 6), u(cy - math.sin(a) * 6), u(cx + math.cos(a) * 6), u(cy + math.sin(a) * 6)],
                       fill=(116, 192, 252, 255), width=max(2, int(u(2.6))))
    elif kind == "storm":
        cloud(8, 8, 1.05, dark)
        d.polygon([(u(54), u(60)), (u(38), u(84)), (u(50), u(84)), (u(42), u(100)), (u(68), u(72)), (u(55), u(72)), (u(62), u(60))],
                  fill=(255, 212, 59, 255))
    return im


def draw_drop(img, x, y, s, color):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([(x + s * .5, y), (x + s * .12, y + s * .62), (x + s * .88, y + s * .62)], fill=color)
    d.ellipse([x + s * .08, y + s * .38, x + s * .92, y + s * 1.0], fill=color)


def draw_wind(img, x, y, s, color):
    from PIL import ImageDraw
    d = ImageDraw.Draw(img, "RGBA")
    w = max(2, int(s * .09))
    d.line([x, y + s * .30, x + s * .72, y + s * .30], fill=color, width=w)
    d.arc([x + s * .52, y + s * .08, x + s * .92, y + s * .48], 270, 100, fill=color, width=w)
    d.line([x, y + s * .55, x + s * .95, y + s * .55], fill=color, width=w)
    d.line([x, y + s * .80, x + s * .62, y + s * .80], fill=color, width=w)
    d.arc([x + s * .42, y + s * .60, x + s * .80, y + s * 1.0], 90, 270 + 180, fill=color, width=w)


def render_card():
    from PIL import Image, ImageDraw, ImageFilter

    n_periods = len(periods)
    n_sections = sum(1 for k, _ in items if k == "section")
    H = HEADER_H + n_periods * (ROW_H + GAP) + n_sections * SECTION_H + FOOTER_H

    top, bottom = (hex_rgb(c) for c in config["palette"])
    base = Image.new("RGB", (px(W), px(H)))
    gd = ImageDraw.Draw(base)
    for y in range(px(H)):
        t = y / max(1, px(H) - 1)
        gd.line([(0, y), (px(W), y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    # м'яке сяйво у верхньому куті (сонце/місяць)
    glow = Image.new("RGBA", (px(W), px(760)), (255, 255, 255, 0))
    ImageDraw.Draw(glow).ellipse([px(W - 340), px(-120), px(W + 60), px(280)], fill=(255, 255, 255, 54))
    glow = glow.filter(ImageFilter.GaussianBlur(px(70)))
    base.paste(glow, (0, 0), glow)

    d = ImageDraw.Draw(base, "RGBA")

    def text(xy, s, f, fill, shadow=False):
        if shadow:
            d.text((xy[0], xy[1] + px(2)), s, font=f, fill=(0, 0, 0, 70))
        d.text(xy, s, font=f, fill=fill)

    # --- шапка ---
    flag = Image.new("RGBA", (px(68), px(46)), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flag)
    fd.rectangle([0, 0, px(68), px(23)], fill=(0, 87, 183, 255))
    fd.rectangle([0, px(23), px(68), px(46)], fill=(255, 215, 0, 255))
    mask = Image.new("L", flag.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, px(68) - 1, px(46) - 1], radius=px(9), fill=255)
    base.paste(flag, (px(MARGIN + 4), px(58)), mask)

    text((px(MARGIN + 92), px(50)), "СУМСЬКИЙ СИНОПТИК", font(50, True), (255, 255, 255, 255), shadow=True)
    text((px(MARGIN + 4), px(138)), config["image_title"], fit_font(config["image_title"], 46, True, W - 2 * MARGIN - 8),
         (255, 255, 255, 255), shadow=True)
    sub = config["title"].format(d0=d0) + " · Суми"
    text((px(MARGIN + 4), px(204)), sub, fit_font(sub, 30, False, W - 2 * MARGIN - 8), (255, 255, 255, 225))

    # --- картки ---
    y = HEADER_H
    for kind, payload in items:
        if kind == "section":
            f = font(32, True)
            tw = f.getlength(payload) / SC
            d.rounded_rectangle([px(MARGIN), px(y + 8), px(MARGIN + tw + 56), px(y + 62)], radius=px(27),
                                fill=(255, 255, 255, 52))
            text((px(MARGIN + 28), px(y + 14)), payload, f, (255, 255, 255, 255), shadow=True)
            y += SECTION_H
            continue

        p = payload
        x0, w, h = px(MARGIN), px(W - 2 * MARGIN), px(ROW_H)
        y0 = px(y)

        pad = px(30)
        shadow = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([pad, pad + px(6), pad + w, pad + h + px(6)], radius=px(34),
                                                 fill=(10, 20, 50, 80))
        shadow = shadow.filter(ImageFilter.GaussianBlur(px(10)))
        base.paste(shadow, (x0 - pad, y0 - pad), shadow)
        d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=px(34), fill=(255, 255, 255, 240))

        tcol = temp_color(p["temp_max"])
        d.rounded_rectangle([x0 + px(22), y0 + px(30), x0 + px(30), y0 + h - px(30)], radius=px(4), fill=tcol)

        ic = icon_image(icon_kind(p["code"]), p["night"], px(150))
        base.paste(ic, (x0 + px(46), y0 + (h - px(150)) // 2), ic)

        mx = x0 + px(222)
        fn = font(32, True)
        text((mx, y0 + px(24)), p["name"], fn, NAVY)
        text((mx + fn.getlength(p["name"]) + px(14), y0 + px(30)), f"{p['start']:02d}:00–{p['end']:02d}:00",
             font(24), MUTED)

        t_txt = minus(rng(p["temp_min"], p["temp_max"]))
        text((mx, y0 + px(66)), t_txt, fit_font(t_txt, 66, True, 380, 40), tcol)
        f_txt = minus("відчувається " + rng(p["feels_min"], p["feels_max"]))
        text((mx, y0 + px(148)), f_txt, fit_font(f_txt, 26, False, 380, 18), MUTED)

        rx = x0 + px(640)
        d.line([x0 + px(614), y0 + px(32), x0 + px(614), y0 + h - px(32)], fill=LINE, width=px(2))
        text((rx, y0 + px(26)), p["weather"], fit_font(p["weather"], 30, True, 336, 20), NAVY)

        draw_drop(base, rx, y0 + px(84), px(26), (77, 171, 247, 255))
        if p["rain_probability"] == 0:
            precip = "без опадів"
        else:
            precip = f"до {p['rain_probability']}%" + (f" · {p['rain_total']:.1f} мм" if p["rain_total"] >= 0.1 else "")
        text((rx + px(40), y0 + px(80)), precip, fit_font(precip, 28, False, 296, 18), NAVY)

        draw_wind(base, rx, y0 + px(124), px(28), (120, 135, 158, 255))
        wspeed = f"{p['wind_min']} м/с" if p["wind_min"] == p["wind_max"] else f"{p['wind_min']}–{p['wind_max']} м/с"
        wtxt = f"{DIRECTIONS_SHORT[p['direction']]} {wspeed}"
        text((rx + px(40), y0 + px(122)), wtxt, fit_font(wtxt, 28, False, 296, 18), NAVY)
        if p["gust_max"] > p["wind_max"]:
            g = f"пориви до {p['gust_max']} м/с"
            text((rx + px(40), y0 + px(160)), g, fit_font(g, 24, False, 296, 16), MUTED)

        y += ROW_H + GAP

    # --- підвал ---
    fy = H - FOOTER_H + 22
    text((px(MARGIN + 4), px(fy)), "Дані: Open-Meteo · оновлення о 07:00, 13:00 та 19:00", font(24), (255, 255, 255, 215))
    text((px(MARGIN + 4), px(fy + 40)), CHANNEL_HANDLE, font(32, True), (255, 255, 255, 255), shadow=True)

    out = base.convert("RGB").resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------
# Telegram
# ------------------------------------------------------------

def tg_call(method, body, content_type):
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=body, method="POST", headers={"Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        details = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {details}")


def send_photo(png, caption):
    boundary = "----sumy" + os.urandom(8).hex()
    parts = []
    for key, value in (("chat_id", CHANNEL), ("caption", caption), ("parse_mode", "HTML")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="forecast.png"\r\n'
                 f'Content-Type: image/png\r\n\r\n'.encode("utf-8") + png + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return tg_call("sendPhoto", b"".join(parts), f"multipart/form-data; boundary={boundary}")


def send_text(text):
    payload = {"chat_id": CHANNEL, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    return tg_call("sendMessage", urllib.parse.urlencode(payload).encode("utf-8"), "application/x-www-form-urlencoded")


def text_fallback(tags):
    """Запасний повний текстовий прогноз (як було раніше) + теги."""
    message = (
        "🇺🇦 <b>СУМСЬКИЙ СИНОПТИК</b>\n"
        f"{config['header']}\n"
        f"🌦 <b>{config['title'].format(d0=d0)}</b>\n"
        "📍 Суми\n\n"
    )
    for kind, payload in items:
        if kind == "section":
            message += f"━━━ <b>📅 {payload}</b> ━━━\n\n"
        else:
            message += period_text(payload) + "\n"
    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "📍 Суми\n"
        "🕒 Дані Open-Meteo\n"
        "🔄 Прогноз оновлюється тричі на добу: 07:00, 13:00, 19:00\n\n"
        f"{tags}"
    )
    return message


# ------------------------------------------------------------
# Публікація
# ------------------------------------------------------------

caption, tags = build_summary()

png = None
try:
    png = render_card()
    with open(OUT_PNG, "wb") as f:
        f.write(png)
    print(f"Картинку створено: {OUT_PNG} ({len(png) // 1024} КБ)")
except Exception as e:
    print(f"⚠ Не вдалося створити картинку ({type(e).__name__}: {e}). Буде текстовий прогноз.")

if DRY_RUN:
    print("\n" + "=" * 40 + " ПІДПИС " + "=" * 40)
    print(caption)
    print("=" * 88)
    print(f"Довжина підпису: {len(caption)} символів. DRY RUN — у Telegram нічого не надіслано.")
    raise SystemExit(0)

result = None
if png:
    print("Надсилаємо картинку в Telegram...")
    try:
        result = send_photo(png, caption)
    except Exception as e:
        print(f"⚠ Не вдалося надіслати картинку: {e}. Пробуємо текстом.")

if not (result and result.get("ok")):
    try:
        result = send_text(text_fallback(tags))
    except Exception as e:
        print("ПОМИЛКА TELEGRAM:", e)
        raise SystemExit(1)

if result.get("ok"):
    print()
    print("=" * 40)
    print("  ПРОГНОЗ УСПІШНО ОПУБЛІКОВАНО!")
    print("=" * 40)
    print(f"\nРежим: {mode}\nКанал: {CHANNEL}")
else:
    print("\nTelegram повернув помилку:")
    print(result)
    raise SystemExit(1)
