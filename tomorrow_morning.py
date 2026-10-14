"""Сумський синоптик: ранковий прогноз на 3 дні по Сумщині (Tomorrow.io) -> Telegram, щодня о 07:00.

Що публікується:
  1) Альбом із двох картинок + короткий підпис з тегами:
       • «Погода на 3 дні» для Сум — три картки (сьогодні, завтра, післязавтра) з графіком по годинах;
       • «Сумська область» — таблиця міст на 3 дні.
  2) Якщо картинки створити/надіслати не вдалося — надсилається текстовий прогноз (запасний варіант).

Змінні середовища (GitHub Secrets):
  TOMORROW_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Необов'язково:
  FORCE=1    надіслати незалежно від години (ручний запуск)
  DRY_RUN=1  лише створити forecast_3days.png / forecast_oblast.png і показати підпис, у Telegram нічого не слати

Залежності: pip install requests pillow matplotlib   (matplotlib — лише заради шрифту DejaVu з кирилицею)
"""
import html
import io
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Europe/Kyiv")
SEND_HOUR = 7                       # локальна година відправки
DAYS = 3
CHANNEL_HANDLE = "t.me/sumskoy_sinoptik"
DRY_RUN = os.getenv("DRY_RUN", "").strip() == "1"
OUT_A = "forecast_3days.png"
OUT_B = "forecast_oblast.png"

MAIN = ("Суми", 50.9077, 34.7981)
OTHERS = [
    ("Конотоп", 51.2405, 33.2025),
    ("Шостка", 51.8667, 33.4833),
    ("Ромни", 50.7497, 33.4744),
    ("Охтирка", 50.3100, 34.8986),
    ("Глухів", 51.6786, 33.9111),
    ("Лебедин", 50.5833, 34.4833),
]

# код погоди Tomorrow.io -> (емодзі, опис)
CODES = {
    1000: ("☀️", "ясно"), 1100: ("🌤", "невелика хмарність"), 1101: ("⛅", "мінлива хмарність"),
    1102: ("🌥", "хмарно з проясненнями"), 1001: ("☁️", "похмуро"),
    2000: ("🌫", "туман"), 2100: ("🌫", "легкий туман"),
    4000: ("🌦", "мряка"), 4200: ("🌧", "невеликий дощ"), 4001: ("🌧", "дощ"),
    4201: ("🌧", "сильний дощ"),
    5001: ("🌨", "дрібний сніг"), 5100: ("🌨", "невеликий сніг"), 5000: ("❄️", "сніг"),
    5101: ("❄️", "сильний сніг"),
    6000: ("🧊", "крижана мряка"), 6200: ("🧊", "невеликий крижаний дощ"),
    6001: ("🧊", "крижаний дощ"), 6201: ("🧊", "сильний крижаний дощ"),
    7102: ("🧊", "легка льодяна крупа"), 7000: ("🧊", "льодяна крупа"),
    7101: ("🧊", "сильна льодяна крупа"),
    8000: ("⛈", "гроза"),
}
SNOW_CODES = {5000, 5001, 5100, 5101}
ICE_CODES = {6000, 6001, 6200, 6201, 7000, 7101, 7102}
STORM_CODES = {8000}
FOG_CODES = {2000, 2100}

DIRS = ["Пн", "ПнСх", "Сх", "ПдСх", "Пд", "ПдЗх", "Зх", "ПнЗх"]
DAY_LABELS = ["Сьогодні", "Завтра", "Післязавтра"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "пʼятниця", "субота", "неділя"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]
MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня",
              "вересня", "жовтня", "листопада", "грудня"]


def code_text(code):
    return CODES.get(code, ("", "—"))[1]


def code_emoji(code):
    return CODES.get(code, ("🌡", ""))[0] or "🌡"


def icon_kind(code):
    return {1000: "clear", 1100: "mostly", 1101: "partly", 1102: "mcloud", 1001: "cloud",
            2000: "fog", 2100: "fog", 4000: "drizzle", 4200: "drizzle", 4001: "rain", 4201: "heavy",
            5001: "snow", 5100: "snow", 5000: "snow", 5101: "snow",
            6000: "sleet", 6200: "sleet", 6001: "sleet", 6201: "sleet",
            7102: "sleet", 7000: "sleet", 7101: "sleet", 8000: "storm"}.get(code, "cloud")


PALETTES = {
    "clear": ("#4DA3FF", "#2B62D9"), "mostly": ("#4DA3FF", "#2B62D9"), "partly": ("#5AA9F0", "#3563C4"),
    "mcloud": ("#7E9BC0", "#445B82"), "cloud": ("#8CA0BB", "#4A5C78"), "fog": ("#A7B2C1", "#6B788A"),
    "drizzle": ("#6C8BAE", "#34496A"), "rain": ("#5E7FA6", "#2B3F60"), "heavy": ("#4F6B93", "#232F4E"),
    "snow": ("#A5CCF2", "#6283BE"), "sleet": ("#8FB0D4", "#566FA0"), "storm": ("#51458A", "#1F1B3F"),
}


# ---------------------------------------------------------------- дані
def fetch_hourly(lat, lon, key):
    url = "https://api.tomorrow.io/v4/weather/forecast"
    params = {"location": f"{lat},{lon}", "timesteps": "1h", "units": "metric", "apikey": key}
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:               # ліміт: чекаємо й повторюємо
                last = "429 (перевищено ліміт запитів)"
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()["timelines"]["hourly"]
        except requests.RequestException as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Tomorrow.io: {last}")


def day_hours(hourly, date):
    out = []
    for h in hourly:
        t = datetime.fromisoformat(h["time"].replace("Z", "+00:00")).astimezone(TZ)
        if t.date() == date:
            out.append((t, h["values"]))
    return out


def g(v, k, default=0):
    x = v.get(k)
    return default if x is None else x


def wind_dir(deg):
    return DIRS[round(deg / 45) % 8]


def summarize(hours):
    if not hours:
        return None
    vals = [v for _, v in hours]
    temps = [g(v, "temperature") for v in vals]
    feels = [g(v, "temperatureApparent", g(v, "temperature")) for v in vals]
    all_codes = [v["weatherCode"] for _, v in hours if v.get("weatherCode")]
    day_codes = [v["weatherCode"] for t, v in hours if 6 <= t.hour <= 21 and v.get("weatherCode")] or all_codes
    winds = [g(v, "windSpeed") for v in vals]
    gust = max(max(g(v, "windGust"), g(v, "windSpeed")) for v in vals)
    vis = [v["visibility"] for v in vals if v.get("visibility") is not None]
    press = [v["pressureSurfaceLevel"] * 0.750062 for v in vals if v.get("pressureSurfaceLevel") is not None]
    humid = [v["humidity"] for v in vals if v.get("humidity") is not None]
    return {
        "tmin": round(min(temps)), "tmax": round(max(temps)),
        "fmin": round(min(feels)), "fmax": round(max(feels)),
        "pop": round(max(g(v, "precipitationProbability") for v in vals)),
        "rain": sum(g(v, "rainIntensity") + g(v, "snowIntensity") for v in vals),
        "wmin": round(min(winds)), "wmax": round(max(winds)), "gust": round(gust),
        "dir": Counter(wind_dir(g(v, "windDirection")) for v in vals).most_common(1)[0][0],
        "code": Counter(day_codes).most_common(1)[0][0] if day_codes else None,
        "codes": set(all_codes),
        "vmin": min(vis) if vis else None,
        "press": round(sum(press) / len(press)) if press else None,
        "hum": round(sum(humid) / len(humid)) if humid else None,
    }


# ---------------------------------------------------------------- підпис, теги, попередження
def minus(text):
    return text.replace("-", "−")


def rng(lo, hi, unit="°C"):
    return minus(f"{lo:+d}{unit}" if lo == hi else f"{lo:+d}…{hi:+d}{unit}")


def date_label(date):
    return f"{WEEKDAYS_SHORT[date.weekday()]}, {date:%d.%m}"


def period_text(dates):
    a, b = dates[0], dates[-1]
    if a.month == b.month:
        return f"{a.day}–{b.day} {MONTHS_GEN[a.month - 1]} {a.year}"
    return f"{a.day} {MONTHS_GEN[a.month - 1]} – {b.day} {MONTHS_GEN[b.month - 1]} {b.year}"


def build_alerts(days):
    """Найважливіші попередження на 3 дні (кожного типу — лише найближче)."""
    found = {}

    def add(kind, severity, day_i, text):
        if kind not in found:
            found[kind] = (severity, day_i, f"{text}")

    for i, d in enumerate(days):
        s, lab = d["s"], DAY_LABELS[i].lower()
        if s["codes"] & STORM_CODES:
            add("storm", 5, i, f"⛈ {DAY_LABELS[i]}: можлива гроза")
        if s["codes"] & ICE_CODES:
            add("ice", 5, i, f"🧊 {DAY_LABELS[i]}: ожеледиця / крижаний дощ — обережно на дорогах")
        if s["gust"] >= 15:
            add("wind", 5 if s["gust"] >= 20 else 4, i, f"💨 {DAY_LABELS[i]}: сильні пориви вітру до {s['gust']} м/с")
        if s["rain"] >= 10:
            add("rain", 4, i, f"🌧 {DAY_LABELS[i]}: значні опади, близько {s['rain']:.0f} мм")
        if (s["codes"] & SNOW_CODES) and s["pop"] >= 40:
            add("snow", 3, i, f"❄️ {DAY_LABELS[i]}: можливий сніг")
        if (s["vmin"] is not None and s["vmin"] < 1) or (s["codes"] & {2000}):
            add("fog", 3, i, f"🌫 {DAY_LABELS[i]}: туман, видимість знижена")
        if s["tmax"] >= 30:
            add("heat", 3, i, f"🔥 {DAY_LABELS[i]}: спека до {s['tmax']}°C")
        if s["tmin"] <= 0:
            add("frost", 2, i, f"🥶 {DAY_LABELS[i]}: заморозки до {minus(str(s['tmin']))}°C")
    ordered = sorted(found.values(), key=lambda x: (-x[0], x[1]))[:3]
    return [t for _, _, t in ordered]


def build_tags(days):
    allc = set().union(*(d["s"]["codes"] for d in days))
    pop = max(d["s"]["pop"] for d in days)
    rain = sum(d["s"]["rain"] for d in days)
    gust = max(d["s"]["gust"] for d in days)
    tmin = min(d["s"]["tmin"] for d in days)
    tmax = max(d["s"]["tmax"] for d in days)
    tags = ["#Суми", "#ПогодаСуми", "#Сумщина", "#Прогноз", "#ПрогнозНа3Дні"]
    if pop >= 60 and rain >= 0.5 and not (allc & SNOW_CODES):
        tags.append("#Дощ")
    if allc & SNOW_CODES:
        tags.append("#Сніг")
    if allc & STORM_CODES:
        tags.append("#Гроза")
    if allc & ICE_CODES:
        tags.append("#Ожеледиця")
    if allc & FOG_CODES:
        tags.append("#Туман")
    if gust >= 15:
        tags.append("#СильнийВітер")
    elif gust >= 12:
        tags.append("#Вітер")
    if tmin <= 0:
        tags.append("#Заморозки")
    if tmax >= 30:
        tags.append("#Спека")
    trend = days[-1]["s"]["tmax"] - days[0]["s"]["tmax"]
    if trend >= 5:
        tags.append("#Потепління")
    elif trend <= -5:
        tags.append("#Похолодання")
    tags.append("#СумськийСиноптик")
    return " ".join(tags)


def plain_len(h):
    import re
    return len(html.unescape(re.sub(r"<[^>]+>", "", h)))


def build_caption(days, dates):
    lines = [f"🌤 <b>Погода на 3 дні · Сумщина</b>", f"📍 {MAIN[0]} · {period_text(dates)}", ""]
    for i, d in enumerate(days):
        s = d["s"]
        lines.append(f"<b>{DAY_LABELS[i]}</b> · {date_label(d['date'])}")
        lines.append(f"{code_emoji(s['code'])} {rng(s['tmin'], s['tmax'])} · {code_text(s['code'])}"
                     + (f" · опади до {s['pop']}%" if s["pop"] >= 30 else ""))
    alerts = build_alerts(days)
    tags = build_tags(days)
    tail = ["", "📊 На другій картинці — всі міста області", "", tags]
    caption = "\n".join(lines + ([""] + alerts if alerts else []) + tail)
    if plain_len(caption) > 1024:          # запобіжник: без попереджень
        caption = "\n".join(lines + tail)
    return caption, tags


def build_text_fallback(days, dates, cities, tags):
    msg = [f"🌤 <b>Погода на 3 дні · Сумщина</b>", f"📍 {MAIN[0]} · {period_text(dates)}", ""]
    for i, d in enumerate(days):
        s = d["s"]
        wind = f"{s['dir']} {s['wmin']}–{s['wmax']} м/с" if s["wmin"] != s["wmax"] else f"{s['dir']} {s['wmax']} м/с"
        if s["gust"] > s["wmax"]:
            wind += f", пориви до {s['gust']}"
        msg.append(f"<b>{DAY_LABELS[i]}</b> · {date_label(d['date'])}")
        msg.append(f"{code_emoji(s['code'])} {rng(s['tmin'], s['tmax'])}, {code_text(s['code'])}")
        msg.append(f"💧 опади до {s['pop']}% · 💨 {wind}")
        if s["vmin"] is not None and s["vmin"] < 4:
            msg.append(f"👁 видимість від {s['vmin']:.1f} км")
        msg.append("")
    alerts = build_alerts(days)
    if alerts:
        msg += alerts + [""]
    msg.append("<b>По області:</b>")
    for name, ds in cities:
        parts = [rng(s["tmin"], s["tmax"], "") if s else "—" for s in ds]
        msg.append(f"• <b>{name}</b>: " + " | ".join(parts) + " °C")
    msg += ["<i>(сьогодні | завтра | післязавтра)</i>", "", "<i>Дані: Tomorrow.io</i>", "", tags]
    return "\n".join(msg)


# ---------------------------------------------------------------- малювання (Pillow)
SC = 2
W = 1080
M = 36
CW = W - 2 * M
HEADER_H = 262
FOOTER_H = 124
GAP = 24
DAY_H = 430

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


_fonts = {}


def font(size, bold=False):
    from PIL import ImageFont
    if (size, bold) not in _fonts:
        _fonts[(size, bold)] = ImageFont.truetype(find_font(bold), px(size))
    return _fonts[(size, bold)]


def fit_font(text, size, bold, max_width, min_size=16):
    while size > min_size and font(size, bold).getlength(text) > px(max_width):
        size -= 1
    return font(size, bold)


def icon_image(kind, size):
    """Значок погоди size×size на прозорому тлі (денний варіант)."""
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
        for k in range(8):
            a = math.radians(k * 45)
            d.line([u(cx + math.cos(a) * (r + 6)), u(cy + math.sin(a) * (r + 6)),
                    u(cx + math.cos(a) * (r + 15)), u(cy + math.sin(a) * (r + 15))],
                   fill=(255, 183, 3, 255), width=max(2, int(u(5))))
        circle(cx, cy, r, (255, 196, 20, 255))
        circle(cx, cy, r - 5, (255, 214, 64, 255))

    def drops(n, heavy=False, xs=None, y0=81):
        xs = xs or ([28 + k * (46 / max(1, n - 1)) for k in range(n)] if n > 1 else [50])
        for k, x in enumerate(xs):
            y = y0 + (k % 2) * 6
            d.line([u(x), u(y), u(x - 5), u(y + (13 if heavy else 10))],
                   fill=(77, 171, 247, 255), width=max(2, int(u(4.2 if heavy else 3.4))))

    def flake(cx, cy, r=6):
        for k in range(3):
            a = math.radians(k * 60)
            d.line([u(cx - math.cos(a) * r), u(cy - math.sin(a) * r), u(cx + math.cos(a) * r), u(cy + math.sin(a) * r)],
                   fill=(116, 192, 252, 255), width=max(2, int(u(2.6))))

    light, mid, dark = (205, 217, 233, 255), (150, 168, 192, 255), (92, 108, 130, 255)

    if kind == "clear":
        sun(50, 50, 21)
    elif kind == "mostly":
        sun(42, 44, 19)
        cloud(40, 52, 0.62, light)
    elif kind == "partly":
        sun(34, 36, 15)
        cloud(18, 36, 0.98, light)
    elif kind == "mcloud":
        sun(30, 30, 11)
        cloud(10, 30, 1.0, mid)
    elif kind == "cloud":
        cloud(6, 24, 1.12, mid)
    elif kind == "fog":
        cloud(8, 12, 1.0, light)
        for k, (x1, x2) in enumerate(((16, 80), (24, 88), (16, 72))):
            d.line([u(x1), u(66 + k * 11), u(x2), u(66 + k * 11)], fill=mid, width=max(2, int(u(5))))
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
        cloud(8, 12, 1.05, light)
        for cx, cy in ((30, 84), (50, 90), (70, 84)):
            flake(cx, cy)
    elif kind == "sleet":
        cloud(8, 12, 1.05, mid)
        drops(2, xs=[30, 62], y0=80)
        flake(46, 88)
        flake(78, 86)
    elif kind == "storm":
        cloud(8, 8, 1.05, dark)
        d.polygon([(u(54), u(60)), (u(38), u(84)), (u(50), u(84)), (u(42), u(100)), (u(68), u(72)),
                   (u(55), u(72)), (u(62), u(60))], fill=(255, 212, 59, 255))
    return im


def draw_drop(base, x, y, s, color):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    d.polygon([(x + s * .5, y), (x + s * .12, y + s * .62), (x + s * .88, y + s * .62)], fill=color)
    d.ellipse([x + s * .08, y + s * .38, x + s * .92, y + s * 1.0], fill=color)


def draw_wind(base, x, y, s, color):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    w = max(2, int(s * .09))
    d.line([x, y + s * .30, x + s * .72, y + s * .30], fill=color, width=w)
    d.arc([x + s * .52, y + s * .08, x + s * .92, y + s * .48], 270, 100, fill=color, width=w)
    d.line([x, y + s * .55, x + s * .95, y + s * .55], fill=color, width=w)
    d.line([x, y + s * .80, x + s * .62, y + s * .80], fill=color, width=w)
    d.arc([x + s * .42, y + s * .60, x + s * .80, y + s * 1.0], 90, 450, fill=color, width=w)


def draw_eye(base, x, y, s, color):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    d.ellipse([x, y + s * .2, x + s, y + s * .8], outline=color, width=max(2, int(s * .08)))
    d.ellipse([x + s * .35, y + s * .35, x + s * .65, y + s * .65], fill=color)


def new_canvas(height, palette):
    from PIL import Image, ImageDraw, ImageFilter
    top, bottom = (hex_rgb(c) for c in palette)
    base = Image.new("RGB", (px(W), px(height)))
    gd = ImageDraw.Draw(base)
    for y in range(px(height)):
        t = y / max(1, px(height) - 1)
        gd.line([(0, y), (px(W), y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    glow = Image.new("RGBA", (px(W), px(760)), (255, 255, 255, 0))
    ImageDraw.Draw(glow).ellipse([px(W - 340), px(-120), px(W + 60), px(280)], fill=(255, 255, 255, 54))
    glow = glow.filter(ImageFilter.GaussianBlur(px(70)))
    base.paste(glow, (0, 0), glow)
    return base


def put_text(base, xy, s, f, fill, shadow=False):
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    if shadow:
        d.text((xy[0], xy[1] + px(2)), s, font=f, fill=(0, 0, 0, 70))
    d.text(xy, s, font=f, fill=fill)


def draw_header(base, subtitle, line3):
    from PIL import Image, ImageDraw
    flag = Image.new("RGBA", (px(68), px(46)), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flag)
    fd.rectangle([0, 0, px(68), px(23)], fill=(0, 87, 183, 255))
    fd.rectangle([0, px(23), px(68), px(46)], fill=(255, 215, 0, 255))
    mask = Image.new("L", flag.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, px(68) - 1, px(46) - 1], radius=px(9), fill=255)
    base.paste(flag, (px(M + 4), px(58)), mask)
    put_text(base, (px(M + 92), px(50)), "СУМСЬКИЙ СИНОПТИК", font(50, True), (255, 255, 255, 255), True)
    put_text(base, (px(M + 4), px(138)), subtitle, fit_font(subtitle, 48, True, CW - 8), (255, 255, 255, 255), True)
    put_text(base, (px(M + 4), px(208)), line3, fit_font(line3, 30, False, CW - 8), (255, 255, 255, 228))


def draw_footer(base, height, note):
    fy = height - FOOTER_H + 22
    put_text(base, (px(M + 4), px(fy)), note, fit_font(note, 24, False, CW - 8), (255, 255, 255, 215))
    put_text(base, (px(M + 4), px(fy + 40)), CHANNEL_HANDLE, font(32, True), (255, 255, 255, 255), True)


def card(base, x, y, w, h, fill=(255, 255, 255, 240)):
    from PIL import Image, ImageDraw, ImageFilter
    pad = px(30)
    shadow = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([pad, pad + px(6), pad + w, pad + h + px(6)], radius=px(34),
                                             fill=(10, 20, 50, 80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(px(10)))
    base.paste(shadow, (x - pad, y - pad), shadow)
    ImageDraw.Draw(base, "RGBA").rounded_rectangle([x, y, x + w, y + h], radius=px(34), fill=fill)


def draw_spark(base, bx, by, bw, bh, hours, tcol):
    """Міні-графік доби: температура (крива) + ймовірність опадів (стовпчики)."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(base, "RGBA")
    temps = [g(v, "temperature") for _, v in hours]
    tmin, tmax = min(temps), max(temps)
    span = max(tmax - tmin, 2.0)
    ytop, ybot = by + bh * 0.20, by + bh * 0.70

    def X(t):
        return px(bx) + (t.hour / 23.0) * px(bw)

    def Y(v):
        return px(ytop) + (1 - (v - tmin) / span) * (px(ybot) - px(ytop))

    for hh in (0, 6, 12, 18, 23):                       # сітка та підписи годин
        gx = px(bx) + hh / 23.0 * px(bw)
        d.line([gx, px(by + 6), gx, px(by + bh)], fill=(200, 210, 225, 120), width=px(1.5))
        label = f"{24 if hh == 23 else hh:02d}"
        f = font(20)
        put_text(base, (gx - f.getlength(label) / 2, px(by + bh + 6)), label, f, MUTED)

    for t, v in hours:                                  # ймовірність опадів
        p = g(v, "precipitationProbability")
        if p > 0:
            bar_h = p / 100.0 * px(bh * 0.30)
            x = X(t)
            d.rectangle([x - px(7), px(by + bh) - bar_h, x + px(7), px(by + bh)], fill=(77, 171, 247, 95))

    pts = [(X(t), Y(g(v, "temperature"))) for t, v in hours]
    if len(pts) >= 2:
        d.polygon(pts + [(pts[-1][0], px(by + bh)), (pts[0][0], px(by + bh))], fill=tcol + (38,))
        d.line(pts, fill=tcol + (255,), width=px(4), joint="curve")
    for fn in (max, min):                               # підписи екстремумів
        val = fn(temps)
        i = temps.index(val)
        x, y = pts[i]
        d.ellipse([x - px(6), y - px(6), x + px(6), y + px(6)], fill=(255, 255, 255, 255), outline=tcol + (255,), width=px(3))
        label = minus(f"{round(val):+d}°")
        f = font(22, True)
        ly = y - px(32) if fn is max else y + px(9)
        put_text(base, (x - f.getlength(label) / 2, ly), label, f, tcol)


def render_days(days, dates, palette):
    from PIL import Image
    n = len(days)
    height = HEADER_H + n * DAY_H + (n - 1) * GAP + GAP + FOOTER_H
    base = new_canvas(height, palette)
    draw_header(base, "Погода на 3 дні", f"{MAIN[0]} · {period_text(dates)}")

    y = HEADER_H
    for i, day in enumerate(days):
        s, date = day["s"], day["date"]
        x0, y0, w, h = px(M), px(y), px(CW), px(DAY_H)
        card(base, x0, y0, w, h)

        tcol = temp_color(s["tmax"])
        base_d = None  # noqa
        put_text(base, (x0 + px(40), y0 + px(26)), DAY_LABELS[i].upper(), font(34, True), NAVY)
        label_w = font(34, True).getlength(DAY_LABELS[i].upper())
        dtxt = f"{WEEKDAYS[date.weekday()]}, {date.day} {MONTHS_GEN[date.month - 1]}"
        put_text(base, (x0 + px(40) + label_w + px(18), y0 + px(33)), dtxt, font(26), MUTED)

        ic = icon_image(icon_kind(s["code"]), px(172))
        base.paste(ic, (x0 + px(34), y0 + px(86)), ic)

        mx = x0 + px(236)
        big = minus(f"{s['tmax']:+d}°")
        put_text(base, (mx, y0 + px(78)), big, fit_font(big, 92, True, 290, 50), tcol)
        mn = minus(f"мін {s['tmin']:+d}°")
        put_text(base, (mx, y0 + px(186)), mn, fit_font(mn, 34, True, 290, 20), MUTED)
        fe = minus(f"відчувається {s['fmin']:+d}…{s['fmax']:+d}°" if s["fmin"] != s["fmax"] else f"відчувається {s['fmin']:+d}°")
        put_text(base, (mx, y0 + px(232)), fe, fit_font(fe, 24, False, 290, 14), MUTED)

        from PIL import ImageDraw
        ImageDraw.Draw(base, "RGBA").line([x0 + px(548), y0 + px(92), x0 + px(548), y0 + px(262)], fill=LINE, width=px(2))
        rx = x0 + px(574)
        wt = code_text(s["code"]).capitalize()
        put_text(base, (rx, y0 + px(88)), wt, fit_font(wt, 32, True, 400, 20), NAVY)

        draw_drop(base, rx, y0 + px(142), px(26), (77, 171, 247, 255))
        precip = "без опадів" if s["pop"] == 0 else f"до {s['pop']}%" + (f" · {s['rain']:.1f} мм" if s["rain"] >= 0.1 else "")
        put_text(base, (rx + px(40), y0 + px(138)), precip, fit_font(precip, 28, False, 360, 18), NAVY)

        draw_wind(base, rx, y0 + px(186), px(28), (120, 135, 158, 255))
        ws = f"{s['wmin']} м/с" if s["wmin"] == s["wmax"] else f"{s['wmin']}–{s['wmax']} м/с"
        wtxt = f"{s['dir']} {ws}"
        put_text(base, (rx + px(40), y0 + px(184)), wtxt, fit_font(wtxt, 28, False, 360, 18), NAVY)
        if s["gust"] > s["wmax"]:
            gt = f"пориви до {s['gust']} м/с"
            put_text(base, (rx + px(40), y0 + px(220)), gt, fit_font(gt, 24, False, 360, 16), MUTED)

        if s["vmin"] is not None and s["vmin"] < 4:
            warn = (234, 120, 20, 255) if s["vmin"] < 1 else MUTED
            draw_eye(base, rx, y0 + px(252), px(26), warn)
            vt = f"видимість від {s['vmin']:.1f} км"
            put_text(base, (rx + px(40), y0 + px(250)), vt, fit_font(vt, 24, False, 360, 16), warn)
        elif s["press"] is not None and s["hum"] is not None:
            it = f"{s['press']} мм рт. ст. · вологість {s['hum']}%"
            put_text(base, (rx, y0 + px(256)), it, fit_font(it, 24, False, 410, 14), MUTED)

        draw_spark(base, M + 40, y + 300, CW - 80, 92, day["hours"], tcol)
        y += DAY_H + GAP

    draw_footer(base, height, "Дані: Tomorrow.io · оновлення щодня о 07:00")
    out = base.convert("RGB").resize((W, height), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_oblast(cities, dates, palette):
    """cities: [(name, [summary|None ×3])] — перше місто (Суми) виділяється."""
    from PIL import Image, ImageDraw
    ROW_H, HEAD_ROW = 122, 96
    n = len(cities)
    card_h = HEAD_ROW + n * ROW_H + 20
    height = HEADER_H + card_h + GAP + FOOTER_H
    base = new_canvas(height, palette)
    draw_header(base, "Сумська область", f"Погода на 3 дні по містах · {period_text(dates)}")

    x0, y0, w, h = px(M), px(HEADER_H), px(CW), px(card_h)
    card(base, x0, y0, w, h)
    d = ImageDraw.Draw(base, "RGBA")

    CELL_X0, CELL_W = M + 236, 250                     # три колонки по 250 px праворуч від назви міста
    cell_x = [px(CELL_X0 + CELL_W * i) for i in range(3)]
    for cx, lab, dt in zip(cell_x, DAY_LABELS, dates):
        f = font(22, True)
        mid = cx + px(CELL_W / 2)
        put_text(base, (mid - f.getlength(lab.upper()) / 2, y0 + px(22)), lab.upper(), f, NAVY)
        t = f"{dt:%d.%m}"
        f2 = font(22)
        put_text(base, (mid - f2.getlength(t) / 2, y0 + px(52)), t, f2, MUTED)
    d.line([x0 + px(30), y0 + px(HEAD_ROW - 4), x0 + w - px(30), y0 + px(HEAD_ROW - 4)], fill=LINE, width=px(2))

    for r, (name, ds) in enumerate(cities):
        ry = y0 + px(HEAD_ROW + r * ROW_H)
        if r == 0:
            d.rounded_rectangle([x0 + px(14), ry + px(4), x0 + w - px(14), ry + px(ROW_H - 4)], radius=px(26),
                                fill=(77, 171, 247, 38))
        put_text(base, (x0 + px(36), ry + px(42)), name, fit_font(name, 34, True, 190, 20), NAVY)
        for cx, s in zip(cell_x, ds):
            if not s:
                put_text(base, (cx + px(90), ry + px(36)), "—", font(36, True), MUTED)
                continue
            ic = icon_image(icon_kind(s["code"]), px(70))
            base.paste(ic, (cx + px(2), ry + px(26)), ic)
            tcol = temp_color(s["tmax"])
            put_text(base, (cx + px(82), ry + px(14)), minus(f"{s['tmax']:+d}°"), fit_font(minus(f"{s['tmax']:+d}°"), 36, True, 84, 24), tcol)
            put_text(base, (cx + px(82), ry + px(58)), minus(f"{s['tmin']:+d}°"), fit_font(minus(f"{s['tmin']:+d}°"), 28, True, 84, 20), MUTED)
            if s["pop"] >= 40:
                draw_drop(base, cx + px(170), ry + px(48), px(18), (77, 171, 247, 255))
                put_text(base, (cx + px(192), ry + px(44)), f"{s['pop']}%", font(22), NAVY)
        if r < n - 1:
            d.line([x0 + px(30), ry + px(ROW_H), x0 + w - px(30), ry + px(ROW_H)], fill=LINE, width=px(1.5))

    draw_footer(base, height, "Макс / мін, °C · краплина — ймовірність опадів від 40%")
    out = base.convert("RGB").resize((W, height), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- Telegram
def tg(method, token, **kw):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=90, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def send_album(png_a, png_b, caption, token, chat_id):
    media = [{"type": "photo", "media": "attach://p0", "caption": caption, "parse_mode": "HTML"},
             {"type": "photo", "media": "attach://p1"}]
    tg("sendMediaGroup", token, data={"chat_id": chat_id, "media": json.dumps(media)},
       files={"p0": ("forecast_3days.png", png_a, "image/png"),
              "p1": ("forecast_oblast.png", png_b, "image/png")})


def send_text(text, token, chat_id):
    tg("sendMessage", token, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": True})


# ---------------------------------------------------------------- main
def main():
    now = datetime.now(TZ)
    # Страховка від переходу на літній/зимовий час: workflow спрацьовує у два UTC-слоти
    if os.getenv("FORCE") != "1" and not DRY_RUN and now.hour != SEND_HOUR:
        print(f"Зараз {now:%H:%M} за Києвом, не {SEND_HOUR}:00 — пропуск.")
        return 0

    key = os.environ["TOMORROW_API_KEY"]
    token = chat = None
    if not DRY_RUN:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat = os.environ["TELEGRAM_CHAT_ID"]

    dates = [(now + timedelta(days=i)).date() for i in range(DAYS)]

    # --- Суми (детально)
    hourly = fetch_hourly(MAIN[1], MAIN[2], key)
    days = []
    for date in dates:
        hrs = day_hours(hourly, date)
        s = summarize(hrs)
        if s:
            days.append({"date": date, "hours": hrs, "s": s})
    if not days:
        print("Не вдалося отримати прогноз для Сум.", file=sys.stderr)
        return 1
    dates = [d["date"] for d in days]

    # --- інші міста області
    cities = [(MAIN[0], [summarize(day_hours(hourly, dt)) for dt in dates])]
    for name, lat, lon in OTHERS:
        try:
            hr = fetch_hourly(lat, lon, key)
            cities.append((name, [summarize(day_hours(hr, dt)) for dt in dates]))
        except Exception as e:                        # одне місто не повинно валити весь пост
            print(f"{name}: {e}", file=sys.stderr)
        time.sleep(1)                                 # ліміт free-плану: ~3 запити/сек

    caption, tags = build_caption(days, dates)
    palette = PALETTES.get(icon_kind(days[0]["s"]["code"]), PALETTES["cloud"])

    png_a = png_b = None
    try:
        png_a = render_days(days, dates, palette)
        png_b = render_oblast(cities, dates, palette)
        with open(OUT_A, "wb") as f:
            f.write(png_a)
        with open(OUT_B, "wb") as f:
            f.write(png_b)
        print(f"Картинки створено: {OUT_A} ({len(png_a) // 1024} КБ), {OUT_B} ({len(png_b) // 1024} КБ)")
    except Exception as e:
        print(f"⚠ Не вдалося створити картинки ({type(e).__name__}: {e}). Буде текстовий прогноз.", file=sys.stderr)
        png_a = png_b = None

    if DRY_RUN:
        print("\n" + "=" * 36 + " ПІДПИС " + "=" * 36)
        print(caption)
        print("=" * 80)
        print(f"Довжина підпису: {plain_len(caption)} символів. DRY RUN — у Telegram нічого не надіслано.")
        return 0

    if png_a and png_b:
        try:
            send_album(png_a, png_b, caption, token, chat)
            print("Надіслано (альбом).")
            return 0
        except Exception as e:
            print(f"⚠ Не вдалося надіслати картинки: {e}. Надсилаємо текстом.", file=sys.stderr)

    send_text(build_text_fallback(days, dates, cities, tags), token, chat)
    print("Надіслано (текст).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
