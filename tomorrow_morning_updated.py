"""Трёхдневный утренний прогноз Сумской области (Tomorrow.io) -> Telegram.

Публикует PNG-инфографику и подробный текст на украинском языке.
Нужны GitHub Secrets: TOMORROW_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
FORCE=1 разрешает ручной запуск в любое время.
"""
import io
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests

TZ = ZoneInfo("Europe/Kyiv")
SEND_HOUR = 7
NAN = float("nan")

MAIN = ("Суми", 50.9077, 34.7981)
OTHERS = [
    ("Конотоп", 51.2405, 33.2025),
    ("Шостка", 51.8667, 33.4833),
    ("Ромни", 50.7497, 33.4744),
    ("Охтирка", 50.3100, 34.8986),
    ("Глухів", 51.6786, 33.9111),
    ("Лебедин", 50.5833, 34.4833),
]

CODES = {
    1000: ("ЯСНО", "ясно"), 1100: ("СОНЯЧНО", "невелика хмарність"),
    1101: ("МІНЛИВА ХМАРНІСТЬ", "мінлива хмарність"),
    1102: ("ХМАРНО З ПРОЯСНЕННЯМИ", "хмарно з проясненнями"),
    1001: ("ХМАРНО", "похмуро"),
    2000: ("ТУМАН", "туман"), 2100: ("ЛЕГКИЙ ТУМАН", "легкий туман"),
    4000: ("МРЯКА", "мряка"), 4200: ("НЕВЕЛИКИЙ ДОЩ", "невеликий дощ"),
    4001: ("ДОЩ", "дощ"), 4201: ("СИЛЬНИЙ ДОЩ", "сильний дощ"),
    5001: ("ДРІБНИЙ СНІГ", "дрібний сніг"), 5100: ("НЕВЕЛИКИЙ СНІГ", "невеликий сніг"),
    5000: ("СНІГ", "сніг"), 5101: ("СИЛЬНИЙ СНІГ", "сильний сніг"),
    6000: ("КРИЖАНА МРЯКА", "крижана мряка"),
    6200: ("КРИЖАНИЙ ДОЩ", "невеликий крижаний дощ"),
    6001: ("КРИЖАНИЙ ДОЩ", "крижаний дощ"),
    6201: ("СИЛЬНИЙ КРИЖАНИЙ ДОЩ", "сильний крижаний дощ"),
    7102: ("ЛЬОДЯНА КРУПА", "легка льодяна крупа"),
    7000: ("ЛЬОДЯНА КРУПА", "льодяна крупа"),
    7101: ("СИЛЬНА ЛЬОДЯНА КРУПА", "сильна льодяна крупа"),
    8000: ("ГРОЗА", "гроза"),
}
DIRS = ["Пн", "ПнСх", "Сх", "ПдСх", "Пд", "ПдЗх", "Зх", "ПнЗх"]
WEEKDAYS = ["понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя"]
MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def code_label(code, upper=False):
    return CODES.get(code, ("ХМАРНО", "умови уточнюються"))[0 if upper else 1]


def date_label(d):
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fetch_hourly(lat, lon, key):
    url = "https://api.tomorrow.io/v4/weather/forecast"
    params = {
        "location": f"{lat},{lon}",
        "timesteps": "1h",
        "units": "metric",
        "apikey": key,
    }
    last_error = None
    for attempt in range(4):
        r = requests.get(url, params=params, timeout=35)
        if r.status_code == 429:
            last_error = "Tomorrow.io повернув 429 (ліміт запитів)"
            time.sleep(6 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"Tomorrow.io HTTP {r.status_code}: {r.text[:300]}")
        payload = r.json()
        try:
            return payload["timelines"]["hourly"]
        except (KeyError, TypeError):
            raise RuntimeError("У відповіді Tomorrow.io немає timelines.hourly")
    raise RuntimeError(last_error or "Не вдалося отримати прогноз")


def local_hours(hourly):
    out = []
    for item in hourly:
        t = datetime.fromisoformat(item["time"].replace("Z", "+00:00")).astimezone(TZ)
        out.append((t, item.get("values", {})))
    return out


def g(values, key, default=0):
    value = values.get(key)
    return default if value is None else value


def wind_dir(degrees):
    if degrees is None:
        return "—"
    return DIRS[round(float(degrees) / 45) % 8]


def daily_summary(hours):
    if not hours:
        return None
    temps = [float(v["temperature"]) for _, v in hours if v.get("temperature") is not None]
    if not temps:
        return None
    daytime_codes = [
        v.get("weatherCode") for t, v in hours
        if 8 <= t.hour <= 19 and v.get("weatherCode") is not None
    ]
    all_codes = [v.get("weatherCode") for _, v in hours if v.get("weatherCode") is not None]
    codes = daytime_codes or all_codes
    vis = [(float(v["visibility"]), t) for t, v in hours if v.get("visibility") is not None]
    winds = [float(v["windSpeed"]) for _, v in hours if v.get("windSpeed") is not None]
    gusts = [float(v["windGust"]) for _, v in hours if v.get("windGust") is not None]
    pops = [float(v["precipitationProbability"]) for _, v in hours
            if v.get("precipitationProbability") is not None]
    rain = sum(float(v.get("rainIntensity") or 0) + float(v.get("snowIntensity") or 0)
               for _, v in hours)
    directions = [int(round(float(v["windDirection"]) / 45) % 8)
                  for _, v in hours if v.get("windDirection") is not None]
    return {
        "tmin": min(temps), "tmax": max(temps),
        "pop": max(pops) if pops else 0,
        "rain": rain,
        "wind": max(winds) if winds else 0,
        "gust": max(gusts + winds) if (gusts or winds) else 0,
        "code": Counter(codes).most_common(1)[0][0] if codes else None,
        "vmin": min(vis, key=lambda x: x[0]) if vis else None,
        "vmax": max((x[0] for x in vis), default=None),
        "winddir": DIRS[Counter(directions).most_common(1)[0][0]] if directions else "—",
        "hours": hours,
    }


def by_date(hours, dates):
    grouped = {d: [] for d in dates}
    for t, values in hours:
        if t.date() in grouped:
            grouped[t.date()].append((t, values))
    return {d: daily_summary(grouped[d]) for d in dates}


def collect_city(name, lat, lon, key, dates):
    hourly = local_hours(fetch_hourly(lat, lon, key))
    result = by_date(hourly, dates)
    missing = [d.isoformat() for d, summary in result.items() if summary is None]
    if missing:
        print(f"ПОПЕРЕДЖЕННЯ: {name}: немає даних за {', '.join(missing)}", file=sys.stderr)
    return result


def make_chart(now, dates, main_days, regional):
    # Висококонтрастна темна інфографіка для читання з телефона.
    BG = "#081426"
    PANEL = "#12233b"
    PANEL2 = "#172b46"
    FG = "#f4f7ff"
    MUTED = "#a9bad2"
    GOLD = "#ffc857"
    BLUE = "#64c7ff"
    GREEN = "#6ee7b7"
    LINE = "#2d4564"

    plt.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
    fig = plt.figure(figsize=(10, 13.5), dpi=160, facecolor=BG)
    fig.subplots_adjust(left=0.07, right=0.93, top=0.95, bottom=0.04)

    # Header
    fig.text(0.07, 0.965, "СУМСЬКИЙ СИНОПТИК", color=BLUE, fontsize=13,
             weight="bold", va="top")
    fig.text(0.07, 0.925, "ПРОГНОЗ НА 3 ДНІ", color=FG, fontsize=26,
             weight="bold", va="top")
    fig.text(0.07, 0.892,
             f"Сумська область  •  оновлено {now:%d.%m.%Y о %H:%M}",
             color=MUTED, fontsize=10, va="top")
    fig.text(0.93, 0.965, "ПРОГНОЗ", color=GOLD, fontsize=9,
             weight="bold", ha="right", va="top")

    # Three day cards
    card_y = [0.735, 0.565, 0.395]
    for i, d in enumerate(dates):
        s = main_days.get(d)
        y = card_y[i]
        rect = plt.Rectangle((0.06, y), 0.88, 0.145, transform=fig.transFigure,
                             facecolor=PANEL if i != 0 else PANEL2,
                             edgecolor=LINE, linewidth=1.1, zorder=0,
                             joinstyle="round")
        fig.add_artist(rect)
        fig.text(0.09, y + 0.112, ["СЬОГОДНІ", "ЗАВТРА", "ПІСЛЯЗАВТРА"][i],
                 color=GOLD if i == 0 else BLUE, fontsize=9, weight="bold")
        fig.text(0.09, y + 0.078, f"{d.day:02d}.{d.month:02d}",
                 color=FG, fontsize=17, weight="bold")
        fig.text(0.09, y + 0.035, WEEKDAYS[d.weekday()].capitalize(),
                 color=MUTED, fontsize=9)
        if not s:
            fig.text(0.44, y + 0.073, "Дані тимчасово недоступні",
                     color=MUTED, fontsize=12, va="center")
            continue
        fig.text(0.32, y + 0.087, code_label(s["code"], upper=True),
                 color=FG, fontsize=10, weight="bold")
        fig.text(0.32, y + 0.039,
                 f"{s['tmin']:+.0f}°  —  {s['tmax']:+.0f}°C",
                 color=GOLD, fontsize=20, weight="bold")
        fig.text(0.70, y + 0.088, f"ОПАДИ  {s['pop']:.0f}%",
                 color=BLUE, fontsize=10, weight="bold")
        fig.text(0.70, y + 0.055, f"ПОРИВИ  {s['gust']:.0f} м/с",
                 color=GREEN, fontsize=10, weight="bold")
        fig.text(0.70, y + 0.025, f"ВІТЕР  {s['winddir']}",
                 color=MUTED, fontsize=9)

    # Temperature range plot
    ax = fig.add_axes([0.10, 0.245, 0.80, 0.105], facecolor=BG)
    valid = [(d, main_days[d]) for d in dates if main_days.get(d)]
    if valid:
        x = list(range(len(valid)))
        lows = [s["tmin"] for _, s in valid]
        highs = [s["tmax"] for _, s in valid]
        mids = [(a + b) / 2 for a, b in zip(lows, highs)]
        ax.vlines(x, lows, highs, color=BLUE, linewidth=7, alpha=0.8, zorder=2)
        ax.scatter(x, lows, color=FG, s=35, zorder=3)
        ax.scatter(x, highs, color=GOLD, s=35, zorder=3)
        for xi, low, high in zip(x, lows, highs):
            ax.text(xi, high + 0.8, f"+{high:.0f}°" if high > 0 else f"{high:.0f}°",
                    color=GOLD, fontsize=9, ha="center", va="bottom", weight="bold")
            ax.text(xi, low - 0.8, f"+{low:.0f}°" if low > 0 else f"{low:.0f}°",
                    color=FG, fontsize=9, ha="center", va="top")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{d.day:02d}.{d.month:02d}" for d, _ in valid],
                           color=MUTED, fontsize=9)
        ax.set_xlim(-0.5, len(valid) - 0.5)
        ax.set_ylim(min(lows) - 4, max(highs) + 4)
        ax.grid(axis="y", color=LINE, linewidth=0.7)
        ax.tick_params(axis="y", left=False, labelleft=False)
        ax.tick_params(axis="x", length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
    fig.text(0.07, 0.365, "ТЕМПЕРАТУРА ПРОТЯГОМ ТРЬОХ ДНІВ",
             color=FG, fontsize=10, weight="bold")

    # Regional overview
    fig.text(0.07, 0.215, "ПО СУМСЬКІЙ ОБЛАСТІ", color=FG, fontsize=12, weight="bold")
    fig.text(0.07, 0.193, "Місто", color=MUTED, fontsize=8, weight="bold")
    for j, d in enumerate(dates):
        fig.text(0.34 + j * 0.205, 0.193, f"{d.day:02d}.{d.month:02d}",
                 color=MUTED, fontsize=8, weight="bold", ha="center")
    city_names = [MAIN[0]] + [name for name, _, _ in OTHERS]
    row_y_start = 0.172
    row_h = 0.019
    for idx, name in enumerate(city_names):
        y = row_y_start - idx * row_h
        if idx % 2 == 0:
            fig.add_artist(plt.Rectangle((0.06, y - 0.006), 0.88, 0.018,
                                         transform=fig.transFigure, facecolor=PANEL,
                                         edgecolor="none", zorder=0))
        fig.text(0.08, y, name, color=FG, fontsize=8.5, va="center")
        city_map = main_days if idx == 0 else regional.get(name, {})
        for j, d in enumerate(dates):
            s = city_map.get(d)
            txt = f"{s['tmin']:+.0f}…{s['tmax']:+.0f}°" if s else "—"
            fig.text(0.34 + j * 0.205, y, txt, color=GOLD if idx == 0 else FG,
                     fontsize=8.5, va="center", ha="center")

    fig.text(0.07, 0.025, "Джерело: Tomorrow.io  •  Прогноз може уточнюватися",
             color=MUTED, fontsize=8)
    fig.text(0.93, 0.025, "@sumskoy_sinoptik", color=BLUE, fontsize=8,
             ha="right", weight="bold")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, dpi=160)
    plt.close(fig)
    return buf.getvalue()


def daily_line(d, s):
    if not s:
        return f"• <b>{date_label(d).capitalize()}</b>: дані тимчасово недоступні."
    return (
        f"• <b>{date_label(d).capitalize()}</b>\n"
        f"  🌡 {s['tmin']:+.0f}…{s['tmax']:+.0f}°C · "
        f"{code_label(s['code'])}\n"
        f"  🌧 Імовірність опадів до {s['pop']:.0f}%"
        f" (орієнтовно {s['rain']:.1f} мм) · "
        f"💨 пориви до {s['gust']:.0f} м/с · вітер {s['winddir']}"
    )


def hourly_peek(s):
    if not s:
        return ""
    selected = []
    for target in (6, 9, 12, 15, 18, 21):
        pair = min(s["hours"], key=lambda pair: abs(pair[0].hour - target), default=None)
        if pair and pair[0].hour not in [t.hour for t, _ in selected]:
            selected.append(pair)
    if not selected:
        return ""
    lines = ["<pre>Час   °C  опади  вітер"]
    for t, v in selected:
        temp = v.get("temperature")
        temp_txt = f"{temp:+.0f}" if temp is not None else "—"
        pop = v.get("precipitationProbability")
        pop_txt = f"{pop:.0f}%" if pop is not None else "—"
        speed = v.get("windSpeed")
        speed_txt = f"{speed:.0f}" if speed is not None else "—"
        lines.append(f"{t:%H}:00  {temp_txt:>4}  {pop_txt:>5}  {speed_txt:>2} м/с {wind_dir(v.get('windDirection'))}")
    lines.append("</pre>")
    return "\n".join(lines)


def build_text(now, dates, main_days, regional):
    lines = [
        f"🌤 <b>ПРОГНОЗ ПОГОДИ НА 3 ДНІ</b>",
        f"📍 Сумська область · оновлено {now:%d.%m.%Y о %H:%M}",
        "",
        "<b>Суми — детально</b>",
    ]
    for d in dates:
        s = main_days.get(d)
        lines.append(daily_line(d, s))
        if d == dates[0] and s:
            lines.append(hourly_peek(s))
        lines.append("")
    lines.append("<b>🌍 По області — температура за днями</b>")
    for name, _, _ in OTHERS:
        day_values = regional.get(name, {})
        cells = []
        for d in dates:
            s = day_values.get(d)
            cells.append(f"{d.day:02d}.{d.month:02d}: {s['tmin']:+.0f}…{s['tmax']:+.0f}°" if s else f"{d.day:02d}.{d.month:02d}: —")
        lines.append(f"• <b>{name}</b> — " + " · ".join(cells))
    lines += [
        "",
        "ℹ️ Прогноз модельний і може змінюватися; перед поїздками враховуйте актуальні попередження.",
        "<i>Джерело: Tomorrow.io</i>",
        "",
        "#Погода #ПогодаСуми #Сумщина #ПрогнозПогоди #ПогодаУкраїна",
    ]
    message = "\n".join(lines)
    if len(message) > 3900:
        # Reserve space below Telegram's 4096-character limit.
        message = message[:3800].rsplit("\n", 1)[0] + "\n\n#Погода #ПогодаСуми #Сумщина #ПрогнозПогоди"
    return message


def tg(method, token, **kwargs):
    response = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        timeout=60,
        **kwargs,
    )
    if not response.ok:
        raise RuntimeError(f"Telegram {method}: HTTP {response.status_code}: {response.text[:400]}")
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method}: {payload}")
    return payload


def send_photo(png, caption, token, chat_id):
    tg(
        "sendPhoto", token,
        data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("sumy-3day-forecast.png", png, "image/png")},
    )


def send_text(text, token, chat_id):
    tg(
        "sendMessage", token,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True},
    )


def main():
    now = datetime.now(TZ)
    if os.getenv("FORCE") != "1" and now.hour != SEND_HOUR:
        print(f"Зараз {now:%H:%M} за Києвом, не 07:00 — пропуск.")
        return 0

    key = os.environ["TOMORROW_API_KEY"]
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    dates = [now.date() + timedelta(days=i) for i in range(3)]
    print("Дати прогнозу:", ", ".join(d.isoformat() for d in dates))

    main_days = collect_city(MAIN[0], MAIN[1], MAIN[2], key, dates)
    regional = {}
    for name, lat, lon in OTHERS:
        try:
            regional[name] = collect_city(name, lat, lon, key, dates)
        except Exception as exc:
            print(f"ПОПЕРЕДЖЕННЯ: не вдалося отримати дані для {name}: {exc}", file=sys.stderr)
        time.sleep(1)

    if not any(main_days.values()):
        raise RuntimeError("Tomorrow.io не повернув погодинні дані для Сум на найближчі три дні.")

    caption = (
        f"🌤 <bПрогноз на 3 дні · Сумщина</b>\n"
        f"📍 Суми · {dates[0]:%d.%m}–{dates[-1]:%d.%m}\n"
        f"🌡 " + " | ".join(
            f"{main_days[d]['tmin']:+.0f}…{main_days[d]['tmax']:+.0f}°C"
            if main_days.get(d) else "дані уточнюються"
            for d in dates
        )
    )
    try:
        png = make_chart(now, dates, main_days, regional)
        send_photo(png, caption, token, chat_id)
        print("Інфографіку надіслано.")
    except Exception as exc:
        print(f"Не вдалося надіслати інфографіку: {exc}", file=sys.stderr)

    message = build_text(now, dates, main_days, regional)
    send_text(message, token, chat_id)
    print(f"Текстовий прогноз надіслано. Довжина: {len(message)} символів.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
