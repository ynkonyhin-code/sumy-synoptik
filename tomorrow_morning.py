"""Утренний прогноз по Сумской области (Tomorrow.io) -> Telegram.

Сначала отправляется картинка-график (с короткой подписью),
следом - подробный текстовый пост.

Переменные окружения (GitHub Secrets):
  TOMORROW_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Необязательно:
  FORCE=1  - отправить независимо от текущего часа (для ручного запуска)
"""
import io
import os
import sys
import time
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import requests  # noqa: E402

TZ = ZoneInfo("Europe/Kyiv")
SEND_HOUR = 4  # локальный час отправки
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

# код погоды Tomorrow.io -> (эмодзи, описание)
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
DIRS = ["Пн", "ПнСх", "Сх", "ПдСх", "Пд", "ПдЗх", "Зх", "ПнЗх"]


def code_label(code, emoji=True):
    e, t = CODES.get(code, ("", "—"))
    return f"{e} {t}".strip() if emoji else t


# ---------------------------------------------------------------- данные
def fetch_hourly(lat, lon, key):
    url = "https://api.tomorrow.io/v4/weather/forecast"
    params = {"location": f"{lat},{lon}", "timesteps": "1h", "units": "metric", "apikey": key}
    for attempt in range(4):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:  # лимит: ждём и повторяем
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["timelines"]["hourly"]
    raise RuntimeError("Tomorrow.io: превышен лимит запросов (429)")


def today_hours(hourly):
    today = datetime.now(TZ).date()
    out = []
    for h in hourly:
        t = datetime.fromisoformat(h["time"].replace("Z", "+00:00")).astimezone(TZ)
        if t.date() == today:
            out.append((t, h["values"]))
    return out


def g(v, k, default=0):
    x = v.get(k)
    return default if x is None else x


def wind_dir(deg):
    return DIRS[round(deg / 45) % 8]


def summary(hours):
    vals = [v for _, v in hours]
    temps = [g(v, "temperature") for v in vals]
    codes = [v["weatherCode"] for t, v in hours if 6 <= t.hour <= 21 and v.get("weatherCode")]
    codes = codes or [v["weatherCode"] for _, v in hours if v.get("weatherCode")]
    vis = [(v["visibility"], t) for t, v in hours if v.get("visibility") is not None]
    return {
        "tmin": min(temps), "tmax": max(temps),
        "pop": max(g(v, "precipitationProbability") for v in vals),
        "rain": sum(g(v, "rainIntensity") + g(v, "snowIntensity") for v in vals),
        "gust": max(max(g(v, "windGust"), g(v, "windSpeed")) for v in vals),
        "code": Counter(codes).most_common(1)[0][0] if codes else None,
        "vmin": min(vis, key=lambda x: x[0]) if vis else None,   # (км, время)
        "vmax": max(x[0] for x in vis) if vis else None,
    }


# ---------------------------------------------------------------- график
def make_chart(main_name, hours, others, now):
    BG, FG, GRID = "#0f1b2d", "#e8eef7", "#2a3b55"
    C_T, C_A, C_RAIN, C_WIND, C_VIS = "#ffb347", "#8fb8ff", "#4aa3ff", "#7ee0a8", "#c9a7ff"

    xs = [t.hour for t, _ in hours]

    def ser(k):
        return [g(v, k, NAN) for _, v in hours]

    s = summary(hours)
    fig = plt.figure(figsize=(6, 7.5), dpi=180, facecolor=BG)
    gs = fig.add_gridspec(6, 1, height_ratios=[1.3, 3.0, 1.7, 1.9, 1.4, 3.0],
                          hspace=0.55, left=0.09, right=0.95, top=0.985, bottom=0.015)

    # --- заголовок
    ax = fig.add_subplot(gs[0])
    ax.axis("off")
    ax.text(0, 0.78, "Сумська область · прогноз", color=FG, fontsize=15, weight="bold", va="center")
    ax.text(1, 0.78, f"{now:%d.%m.%Y}", color=C_T, fontsize=12, weight="bold", va="center", ha="right")
    ax.text(0, 0.18, f"{main_name}: {s['tmin']:.0f}…{s['tmax']:.0f}°C · "
                     f"{code_label(s['code'], emoji=False)}", color=FG, fontsize=9.5, va="center")

    def style(ax, title):
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.set_xlim(min(xs) - 0.6, 23.6)
        ticks = [h for h in range(0, 24, 3) if h >= min(xs) - 1] or [min(xs)]
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{h:02d}" for h in ticks])
        ax.tick_params(colors=FG, labelsize=7, length=0)
        ax.set_title(title, loc="left", color=FG, fontsize=8, pad=4)

    # --- температура
    ax = fig.add_subplot(gs[1])
    temp, app = ser("temperature"), ser("temperatureApparent")
    style(ax, "Температура, °C (пунктир — відчувається як)")
    ax.plot(xs, temp, color=C_T, lw=2.4)
    ax.plot(xs, app, color=C_A, lw=1.4, ls="--")
    ax.fill_between(xs, temp, min(temp + app) - 1, color=C_T, alpha=0.08)
    for fn, off, ha in ((max, (0, 6), "center"), (min, (6, -13), "left")):
        val = fn(temp)
        x = xs[temp.index(val)]
        ax.annotate(f"{val:.0f}°", (x, val), textcoords="offset points", xytext=off,
                    ha=ha, color=C_T, fontsize=9, weight="bold")
    ax.margins(y=0.18)

    # --- осадки
    ax = fig.add_subplot(gs[2])
    pop = ser("precipitationProbability")
    style(ax, f"Імовірність опадів, % (сума ≈ {s['rain']:.1f} мм)")
    ax.bar(xs, pop, color=C_RAIN, alpha=0.85, width=0.7)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 50, 100])

    # --- ветер
    ax = fig.add_subplot(gs[3])
    spd, gust = ser("windSpeed"), ser("windGust")
    style(ax, "Вітер, м/с (пунктир — пориви)")
    ax.plot(xs, spd, color=C_WIND, lw=2)
    if not all(v != v for v in gust):
        ax.plot(xs, gust, color=C_WIND, lw=1.2, ls="--", alpha=0.8)
    for (t, v) in hours:
        if t.hour % 3 == 0:
            ax.annotate(wind_dir(g(v, "windDirection")), (t.hour, g(v, "windSpeed")),
                        textcoords="offset points", xytext=(0, 5), ha="center",
                        color=FG, fontsize=6.5)
    ax.set_ylim(0, None)
    ax.margins(y=0.3)

    # --- видимость
    ax = fig.add_subplot(gs[4])
    vis = ser("visibility")
    style(ax, "Видимість, км")
    if all(v != v for v in vis):
        ax.text(0.5, 0.5, "немає даних", transform=ax.transAxes, color=FG, ha="center", fontsize=8)
    else:
        ax.plot(xs, vis, color=C_VIS, lw=2)
        ax.fill_between(xs, vis, 0, color=C_VIS, alpha=0.15)
        ax.axhline(1, color="#ff6b6b", lw=0.8, ls=":")  # ниже 1 км - густой туман
        ax.set_ylim(0, max(10, max(v for v in vis if v == v) * 1.1))

    # --- города области
    ax = fig.add_subplot(gs[5])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    n = len(others) + 1
    step = 1 / n
    cols = (0.0, 0.30, 0.55, 0.80)
    for x, title in zip(cols, ("Область", "t, °C", "опади", "пориви")):
        ax.text(x, 1 - step * 0.5, title, color=C_T, fontsize=8, weight="bold", va="center")
    for i, (name, sm) in enumerate(others, start=1):
        y = 1 - step * (i + 0.5)
        ax.text(cols[0], y, name, color=FG, fontsize=9, va="center")
        ax.text(cols[1], y, f"{sm['tmin']:.0f}…{sm['tmax']:.0f}", color=FG, fontsize=9, va="center")
        ax.text(cols[2], y, f"{sm['pop']:.0f}%", color=FG, fontsize=9, va="center")
        ax.text(cols[3], y, f"{sm['gust']:.0f} м/с", color=FG, fontsize=9, va="center")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()


# ---------------------------------------------------------------- тексты
def vis_line(s):
    if not s["vmin"]:
        return None
    vmin, t = s["vmin"]
    line = f"👁 Видимість: від {vmin:.1f} км (близько {t:%H}:00) до {s['vmax']:.0f} км"
    if vmin < 1:
        line += "\n⚠️ Можливий густий туман — на дорогах будьте обережні!"
    elif vmin < 4:
        line += "\n⚠️ Подекуди серпанок/туман"
    return line


def block_main(name, hours):
    s = summary(hours)
    lines = [
        f"<b>📍 {name}</b> — {code_label(s['code'])}",
        f"🌡 {s['tmin']:.0f}…{s['tmax']:.0f}°C | 💧 опади до {s['pop']:.0f}%, "
        f"≈ {s['rain']:.1f} мм | 💨 пориви до {s['gust']:.0f} м/с",
    ]
    vl = vis_line(s)
    if vl:
        lines.append(vl)

    rows = [f"{'Год':<3} {'t°':>3} {'відч':>4} {'ос%':>3} {'вітер':<6} {'хм%':>3} {'вид':>3}"]
    for t, v in hours:
        if (t.hour % 3 == 0 and t.hour >= 6) or t.hour == 23:
            vis = f"{v['visibility']:.0f}" if v.get("visibility") is not None else "—"
            rows.append(
                f"{t:%H}  {g(v, 'temperature'):>3.0f} {g(v, 'temperatureApparent'):>4.0f} "
                f"{g(v, 'precipitationProbability'):>3.0f} "
                f"{g(v, 'windSpeed'):>2.0f}{wind_dir(g(v, 'windDirection')):<4} "
                f"{g(v, 'cloudCover'):>3.0f} {vis:>3}"
            )
    if len(rows) > 1:
        lines += ["", "<pre>" + "\n".join(rows) + "</pre>",
                  "<i>t° — темп., відч — відчувається, ос% — імовірність опадів, "
                  "вітер — м/с, хм% — хмарність, вид — видимість, км</i>"]

    mid = next((v for t, v in hours if t.hour == 12), hours[0][1])
    extra = []
    if "pressureSurfaceLevel" in mid:
        extra.append(f"тиск {mid['pressureSurfaceLevel'] * 0.750062:.0f} мм рт. ст.")
    if "humidity" in mid:
        extra.append(f"вологість {mid['humidity']:.0f}%")
    if "uvIndex" in mid:
        extra.append(f"UV {mid['uvIndex']:.0f}")
    if extra:
        lines.append("ℹ️ Опівдні: " + ", ".join(extra))
    return "\n".join(lines)


def line_other(name, s):
    txt = (f"• <b>{name}</b>: {s['tmin']:.0f}…{s['tmax']:.0f}°C, {code_label(s['code'])}, "
           f"опади до {s['pop']:.0f}%, пориви до {s['gust']:.0f} м/с")
    if s["vmin"] and s["vmin"][0] < 4:
        txt += f", 👁 до {s['vmin'][0]:.1f} км"
    return txt


# ---------------------------------------------------------------- Telegram
def tg(method, token, **kw):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    r.raise_for_status()


def send_photo(png, caption, token, chat_id):
    tg("sendPhoto", token,
       data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
       files={"photo": ("forecast.png", png, "image/png")})


def send_text(text, token, chat_id):
    tg("sendMessage", token,
       json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
             "disable_web_page_preview": True})


# ---------------------------------------------------------------- main
def main():
    now = datetime.now(TZ)
    # Страховка от перехода на летнее/зимнее время: workflow срабатывает в два UTC-слота
    if os.getenv("FORCE") != "1" and now.hour != SEND_HOUR:
        print(f"Зараз {now:%H:%M} за Києвом, не {SEND_HOUR}:00 — пропуск.")
        return 0

    key = os.environ["TOMORROW_API_KEY"]
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]

    main_hours = today_hours(fetch_hourly(MAIN[1], MAIN[2], key))
    ms = summary(main_hours)

    others = []  # [(name, summary)]
    for name, lat, lon in OTHERS:
        try:
            others.append((name, summary(today_hours(fetch_hourly(lat, lon, key)))))
        except Exception as e:  # один город не должен ронять весь пост
            print(f"{name}: {e}", file=sys.stderr)
        time.sleep(1)  # лимит free-плана: ~3 запроса/сек

    header = f"🌅 <b>Ранковий прогноз на {now:%d.%m.%Y}</b> · Сумська область"

    # 1) картинка с короткой подписью
    caption = (f"{header}\n{MAIN[0]}: {ms['tmin']:.0f}…{ms['tmax']:.0f}°C, "
               f"{code_label(ms['code'])}, опади до {ms['pop']:.0f}%, "
               f"пориви до {ms['gust']:.0f} м/с")
    try:
        send_photo(make_chart(MAIN[0], main_hours, others, now), caption, token, chat)
    except Exception as e:  # без картинки пост всё равно уйдёт текстом
        print(f"Не вдалося надіслати картинку: {e}", file=sys.stderr)

    # 2) подробный текст (со своим заголовком, чтобы был понятен и при пересылке)
    parts = [header + "\n", block_main(MAIN[0], main_hours)]
    if others:
        parts.append("\n<b>По області:</b>\n" + "\n".join(line_other(n, s) for n, s in others))
    parts.append("\n<i>Дані: Tomorrow.io</i>")
    send_text("\n".join(parts), token, chat)
    print("Надіслано.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
