#!/usr/bin/env python3
"""
pogoda_vykhidni — «Погода на вихідні» для Сумського синоптика.

У п'ятницю ввечері малює картинку-картку з прогнозом на суботу й неділю та публікує її в Telegram
з коротким підписом і порадою.

Джерело даних — Open-Meteo (безкоштовно, без ключа). Якщо у weather_daily.py інше джерело, замініть
лише fetch_forecast(): вона має повернути словник з ключами, як у demo_forecast().

Змінні середовища: BOT_TOKEN, CHAT_ID.
Запуск:
  python pogoda_vykhidni.py --demo --out card.png   # намалювати картку на тестових даних (без інтернету)
  python pogoda_vykhidni.py --dry-run --out card.png # реальний прогноз, лише зберегти картку та показати підпис
  python pogoda_vykhidni.py --force                  # опублікувати зараз (ручний запуск)
Автоматично: пʼятниця від 17:00 за Києвом, один раз на вікенд (стан у pogoda_vykhidni_state.json).
"""
import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont
from digest_tracker import track, commit_posted

KYIV = ZoneInfo("Europe/Kyiv")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "pogoda_vykhidni_state.json")
LAT, LON = 50.9077, 34.7981   # Суми
POST_HOUR = 17                 # не раніше цієї години за Києвом (п'ятниця)

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
DAYS = {5: "Субота", 6: "Неділя"}
COMPASS = ["Пн", "Пн-Сх", "Сх", "Пд-Сх", "Пд", "Пд-Зх", "Зх", "Пн-Зх"]

# код WMO -> (опис, тип іконки)
WMO = {0: ("ясно", "sun"), 1: ("переважно ясно", "sun"), 2: ("мінлива хмарність", "partly"),
       3: ("хмарно", "cloud"), 45: ("туман", "fog"), 48: ("паморозний туман", "fog"),
       51: ("легка мряка", "rain"), 53: ("мряка", "rain"), 55: ("густа мряка", "rain"),
       56: ("паморозна мряка", "rain"), 57: ("паморозна мряка", "rain"),
       61: ("невеликий дощ", "rain"), 63: ("дощ", "rain"), 65: ("сильний дощ", "rain"),
       66: ("дощ, що замерзає", "rain"), 67: ("дощ, що замерзає", "rain"),
       71: ("невеликий сніг", "snow"), 73: ("сніг", "snow"), 75: ("сильний сніг", "snow"),
       77: ("снігова крупа", "snow"), 80: ("короткочасні дощі", "rain"), 81: ("зливи", "rain"),
       82: ("сильні зливи", "rain"), 85: ("снігопад", "snow"), 86: ("сильний снігопад", "snow"),
       95: ("гроза", "storm"), 96: ("гроза з градом", "storm"), 99: ("гроза з градом", "storm")}
EMOJI = {"sun": "☀️", "partly": "🌤", "cloud": "☁️", "fog": "🌫", "rain": "🌧", "snow": "❄️", "storm": "⛈"}


# ───────────────────────── дані ─────────────────────────
def fetch_forecast(sat, timeout=20):
    """Прогноз на субботу й неділю: {дата: {...}}."""
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": LAT, "longitude": LON, "timezone": "Europe/Kyiv", "forecast_days": 10,
        "wind_speed_unit": "ms",
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                  "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,"
                  "wind_direction_10m_dominant,sunrise,sunset"),
        "hourly": "temperature_2m",
    }, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    d, h = j["daily"], j["hourly"]
    htemp = dict(zip(h["time"], h["temperature_2m"]))
    out = {}
    for i, ds in enumerate(d["time"]):
        day = date.fromisoformat(ds)
        if day not in (sat, sat + timedelta(days=1)):
            continue
        def at(hh):
            v = htemp.get(f"{ds}T{hh:02d}:00")
            return v
        out[day] = {
            "code": int(d["weather_code"][i]), "tmax": d["temperature_2m_max"][i],
            "tmin": d["temperature_2m_min"][i], "precip": d["precipitation_sum"][i] or 0,
            "pprob": d["precipitation_probability_max"][i] or 0,
            "wind": d["wind_speed_10m_max"][i], "gust": d["wind_gusts_10m_max"][i],
            "wdir": d["wind_direction_10m_dominant"][i],
            "sunrise": d["sunrise"][i][11:16], "sunset": d["sunset"][i][11:16],
            "morning": at(9), "noon": at(15), "evening": at(21),
        }
    if len(out) < 2:
        raise RuntimeError("у відповіді немає обох днів вихідних")
    return out


def demo_forecast(sat):
    return {
        sat: {"code": 63, "tmax": 7.4, "tmin": 2.1, "precip": 3.2, "pprob": 80, "wind": 6.0, "gust": 13.0,
              "wdir": 250, "sunrise": "07:12", "sunset": "16:34",
              "morning": 3.5, "noon": 7.0, "evening": 4.2},
        sat + timedelta(days=1): {"code": 2, "tmax": 5.1, "tmin": -1.3, "precip": 0.0, "pprob": 10,
                                  "wind": 4.0, "gust": 8.0, "wdir": 320, "sunrise": "07:14", "sunset": "16:32",
                                  "morning": -0.5, "noon": 4.8, "evening": 1.0},
    }


# ───────────────────────── текст ─────────────────────────
def fmt_t(t):
    if t is None:
        return "—"
    v = round(t)
    return "0°" if v == 0 else (f"+{v}°" if v > 0 else f"−{abs(v)}°")


def fmt_date(d):
    return f"{d.day} {MONTHS[d.month - 1]}"


def desc(code):
    return WMO.get(code, ("мінлива погода", "cloud"))


def wind_dir(deg):
    return COMPASS[int(((deg or 0) + 22.5) % 360 // 45)]


def advice(days):
    """Список порад (до двох) на основі прогнозу."""
    sat, sun = sorted(days)
    a, b = days[sat], days[sun]
    tips = []
    names = {sat: "суботу", sun: "неділю"}
    for d in (sat, sun):
        x = days[d]
        kind = desc(x["code"])[1]
        if kind == "storm":
            tips.append(f"⛈ У {names[d]} можлива гроза: плануйте справи на відкритому повітрі обережно.")
        elif kind == "snow":
            tips.append(f"❄️ У {names[d]} очікується сніг: одягайтесь тепліше й будьте обережні на дорогах.")
        elif x["pprob"] >= 50 or x["precip"] >= 1:
            tips.append(f"☂️ Парасольку краще взяти в {names[d]}.")
    if min(a["tmin"], b["tmin"]) <= 0 and len(tips) < 2:
        tips.append("🧊 Вранці можливі приморозки, на тротуарах буде слизько.")
    if max(a["gust"], b["gust"]) >= 15 and len(tips) < 2:
        tips.append("🌬 Очікуються сильні пориви вітру: закріпіть усе, що може злетіти.")
    if not tips:
        if desc(a["code"])[1] in ("sun", "partly") and desc(b["code"])[1] in ("sun", "partly"):
            tips.append("🚶 Гарні вихідні для прогулянок.")
        else:
            tips.append("🙂 Вихідні без погодних сюрпризів.")
    diff = b["tmax"] - a["tmax"]
    if abs(diff) >= 5 and len(tips) < 2:
        tips.append(f"{'🔺 У неділю помітно тепліше' if diff > 0 else '🔻 У неділю помітно холодніше'} "
                    f"(на {abs(diff):.0f}°).")
    return tips[:2]


def caption(days):
    lines = ["🗓 <b>Погода на вихідні в Сумах</b>", ""]
    for d in sorted(days):
        x = days[d]
        text, kind = desc(x["code"])
        lines.append(f"{EMOJI[kind]} <b>{DAYS[d.weekday()]}, {fmt_date(d)}</b>: {text}, "
                     f"вдень {fmt_t(x['tmax'])}, вночі {fmt_t(x['tmin'])}, "
                     f"вітер до {x['wind']:.0f} м/с, опади {x['pprob']:.0f}%")
    lines += [""] + advice(days) + ["", "#ПогодаНаВихідні #СумськийСиноптик #Суми"]
    return "\n".join(lines)


# ───────────────────────── малювання ─────────────────────────
S = 2                      # супер-семплінг для гладких ліній
W, H = 1080, 1350
GOLD, WHITE, MUTED = (255, 201, 74), (245, 248, 255), (160, 175, 210)
FONT_DIRS = [os.path.join(BASE, "fonts"), "/usr/share/fonts/truetype/dejavu",
             "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF", "/Library/Fonts", "C:/Windows/Fonts"]


def font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"] if bold
             else ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, int(size * S))
    raise RuntimeError("Не знайдено шрифт з кирилицею: покладіть DejaVuSans.ttf і DejaVuSans-Bold.ttf у папку fonts/")


def gradient(top, bottom):
    img = Image.new("RGB", (W * S, H * S))
    px = ImageDraw.Draw(img)
    for y in range(H * S):
        t = y / (H * S - 1)
        px.line([(0, y), (W * S, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def T(d, xy, text, size, fill=WHITE, bold=False, anchor="la"):
    d.text((xy[0] * S, xy[1] * S), text, font=font(size, bold), fill=fill, anchor=anchor)


def wrap(d, text, size, max_w, bold=False):
    f, words, lines, cur = font(size, bold), text.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) <= max_w * S:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    return lines + ([cur] if cur else [])


def cloud(d, cx, cy, sz, fill):
    def c(dx, dy, r):
        d.ellipse([(cx + (dx - r) * sz), (cy + (dy - r) * sz), (cx + (dx + r) * sz), (cy + (dy + r) * sz)], fill=fill)
    c(-0.20, 0.04, 0.20); c(0.00, -0.08, 0.27); c(0.24, 0.04, 0.19)
    d.rounded_rectangle([cx - 0.20 * sz, cy + 0.02 * sz, cx + 0.24 * sz, cy + 0.23 * sz], radius=0.1 * sz, fill=fill)


def sun(d, cx, cy, sz, r=0.24):
    for k in range(8):
        a = k * math.pi / 4
        d.line([(cx + math.cos(a) * sz * (r + 0.09), cy + math.sin(a) * sz * (r + 0.09)),
                (cx + math.cos(a) * sz * (r + 0.20), cy + math.sin(a) * sz * (r + 0.20))],
               fill=GOLD, width=max(2, int(sz * 0.045)))
    d.ellipse([cx - r * sz, cy - r * sz, cx + r * sz, cy + r * sz], fill=GOLD)


def icon(d, kind, cx, cy, size):
    sz = size * S
    cx, cy = cx * S, cy * S
    light, dark = (232, 238, 250), (178, 190, 215)
    if kind == "sun":
        sun(d, cx, cy, sz, 0.26)
    elif kind == "partly":
        sun(d, cx - 0.12 * sz, cy - 0.14 * sz, sz * 0.8, 0.24)
        cloud(d, cx + 0.06 * sz, cy + 0.10 * sz, sz * 0.95, light)
    elif kind == "cloud":
        cloud(d, cx, cy, sz, light)
    elif kind == "fog":
        cloud(d, cx, cy - 0.10 * sz, sz, light)
        for i, w_ in enumerate((0.34, 0.26, 0.30)):
            y = cy + (0.22 + i * 0.1) * sz
            d.line([cx - w_ * sz, y, cx + w_ * sz, y], fill=(190, 205, 230), width=max(2, int(sz * 0.045)))
    elif kind == "rain":
        cloud(d, cx, cy - 0.10 * sz, sz, dark)
        for dx in (-0.2, 0.0, 0.2):
            x = cx + dx * sz
            d.line([x + 0.04 * sz, cy + 0.20 * sz, x - 0.04 * sz, cy + 0.38 * sz],
                   fill=(110, 175, 255), width=max(2, int(sz * 0.05)))
    elif kind == "snow":
        cloud(d, cx, cy - 0.10 * sz, sz, light)
        for dx, dy in ((-0.2, 0.26), (0.0, 0.36), (0.2, 0.26)):
            x, y, r = cx + dx * sz, cy + dy * sz, 0.055 * sz
            for k in range(3):
                a = k * math.pi / 3
                d.line([x - math.cos(a) * r, y - math.sin(a) * r, x + math.cos(a) * r, y + math.sin(a) * r],
                       fill=WHITE, width=max(2, int(sz * 0.03)))
    elif kind == "storm":
        cloud(d, cx, cy - 0.10 * sz, sz, (150, 160, 190))
        bolt = [(0.04, 0.16), (-0.08, 0.32), (0.0, 0.32), (-0.06, 0.48), (0.12, 0.28), (0.03, 0.28), (0.10, 0.16)]
        d.polygon([(cx + x * sz, cy + y * sz) for x, y in bolt], fill=GOLD)


def row(d, x1, x2, y, label, value):
    T(d, (x1, y), label, 28, MUTED)
    T(d, (x2, y), value, 30, WHITE, True, "ra")


def draw_day(d, x, y, w, h, day, x_):
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=36 * S, fill=(255, 255, 255, 26),
                        outline=(255, 255, 255, 60), width=2 * S)
    cx = x + w / 2
    T(d, (cx, y + 52), DAYS[day.weekday()].upper(), 44, GOLD, True, "mm")
    T(d, (cx, y + 100), fmt_date(day), 30, MUTED, False, "mm")
    text, kind = desc(x_["code"])
    icon(d, kind, cx, y + 214, 190)
    T(d, (cx, y + 372), fmt_t(x_["tmax"]), 104, WHITE, True, "mm")
    T(d, (cx, y + 445), f"вночі {fmt_t(x_['tmin'])}", 36, MUTED, False, "mm")
    yy = y + 505
    for line in wrap(d, text[0].upper() + text[1:], 36, w - 50, True)[:2]:
        T(d, (cx, yy), line, 36, WHITE, True, "ma")
        yy += 46
    # ранок / день / вечір
    top = y + 615
    colw = (w - 60) / 3
    for i, (lab, key) in enumerate((("ранок", "morning"), ("день", "noon"), ("вечір", "evening"))):
        mx = x + 30 + colw * i + colw / 2
        T(d, (mx, top), lab, 26, MUTED, False, "ma")
        T(d, (mx, top + 34), fmt_t(x_[key]), 38, WHITE, True, "ma")
    d.line([(x + 30) * S, (top + 100) * S, (x + w - 30) * S, (top + 100) * S], fill=(255, 255, 255, 50), width=S)
    ry = top + 122
    precip = f"{x_['pprob']:.0f}%" + (f" · {x_['precip']:.1f} мм" if x_["precip"] >= 0.1 else "")
    row(d, x + 30, x + w - 30, ry, "Опади", precip)
    row(d, x + 30, x + w - 30, ry + 46, "Вітер", f"{x_['wind']:.0f} м/с, {wind_dir(x_['wdir'])}")
    row(d, x + 30, x + w - 30, ry + 92, "Пориви", f"до {x_['gust']:.0f} м/с")


def render(days, path):
    img = gradient((13, 22, 56), (30, 52, 104))
    d = ImageDraw.Draw(img, "RGBA")
    sat, sun_ = sorted(days)
    T(d, (W / 2, 78), "ПОГОДА НА ВИХІДНІ", 62, GOLD, True, "mm")
    sub = f"Суми · {sat.day}–{fmt_date(sun_)}" if sat.month == sun_.month else f"Суми · {fmt_date(sat)} – {fmt_date(sun_)}"
    T(d, (W / 2, 138), sub, 34, WHITE, False, "mm")
    cw = 480
    draw_day(d, 50, 190, cw, 880, sat, days[sat])
    draw_day(d, 550, 190, cw, 880, sun_, days[sun_])
    # порада
    box_y, box_h = 1095, 185
    d.rounded_rectangle([50 * S, box_y * S, 1030 * S, (box_y + box_h) * S], radius=30 * S,
                        fill=(255, 201, 74, 30), outline=(255, 201, 74, 150), width=2 * S)
    blocks = []
    for t in advice(days):
        if not t[0].isalpha():                 # прибираємо емодзі на початку (у картці їх не малюємо)
            t = t.split(" ", 1)[1]
        blocks.append(wrap(d, t, 30, 920)[:2])
    total = sum(len(bl) for bl in blocks) * 38 + (len(blocks) - 1) * 8
    yy = box_y + (box_h - total) / 2
    for bl in blocks:
        for line in bl:
            T(d, (W / 2, yy), line, 30, WHITE, False, "ma")
            yy += 38
        yy += 8
    T(d, (W / 2, 1318), "Сумський синоптик  ·  на варті погоди", 28, MUTED, False, "mm")
    img = img.resize((W, H), Image.LANCZOS)
    img.save(path, "PNG", optimize=True)
    return path


# ───────────────────────── Telegram, стан, запуск ─────────────────────────
def weekend_for(today, force):
    wd = today.weekday()
    if wd == 5:
        return today
    if wd == 6:
        return today + timedelta(days=6)
    return today + timedelta(days=5 - wd)


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def send(token, chat_id, png, cap):
    with open(png, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                          data={"chat_id": chat_id, "caption": cap, "parse_mode": "HTML"},
                          files={"photo": f}, timeout=90)
    if not r.ok:
        print(f"[error] Telegram: {r.status_code} {r.text}")
    return r.ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="тестові дані, без інтернету")
    ap.add_argument("--dry-run", action="store_true", help="не публікувати, лише зберегти картку")
    ap.add_argument("--force", action="store_true", help="опублікувати зараз, ігноруючи розклад")
    ap.add_argument("--out", default=os.path.join(BASE, "weekend_card.png"))
    args = ap.parse_args()

    now = datetime.now(KYIV)
    sat = weekend_for(now.date(), args.force)
    local_only = args.demo or args.dry_run

    if not local_only and not args.force:
        if now.weekday() != 4 or now.hour < POST_HOUR:
            print("[skip] публікація лише в п'ятницю після 17:00 за Києвом")
            return 0
        if now.hour >= POST_HOUR + 7:      # запізнілий запуск у ніч уже не публікуємо
            print("[skip] занадто пізно — публікація лише ввечері п'ятниці")
            return 0
        if load_state().get("posted_for") == sat.isoformat():
            print("[skip] на ці вихідні вже опубліковано")
            return 0

    try:
        days = demo_forecast(sat) if args.demo else fetch_forecast(sat)
    except Exception as e:
        print(f"[error] прогноз недоступний: {e}")
        return 1

    png = render(days, args.out)
    cap = caption(days)
    if len(cap) > 1024:
        cap = cap[:1020] + "…"
    print(cap)
    if local_only:
        print(f"[ok] картку збережено: {png}")
        return 0

    token, chat_id = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    if not token or not chat_id:
        print("[error] BOT_TOKEN / CHAT_ID не задані")
        return 1
    if not send(token, chat_id, png, cap):
        return 1
    if not args.force:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"posted_for": sat.isoformat(), "at": now.isoformat()}, f, ensure_ascii=False, indent=2)
    track("weekend", detail=f"на {sat:%d.%m}")
    commit_posted()
    print("[ok] опубліковано")
    return 0


if __name__ == "__main__":
    sys.exit(main())
