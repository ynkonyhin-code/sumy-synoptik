"""Рубрика «Цей день у погоді»: рекорди та типова погода Сум для сьогоднішньої дати
за всі роки, починаючи з 7 грудня 1972 року, + картинка-графік.

Запуск:
    python weather_on_this_day.py                  # опублікувати в канал (BOT_TOKEN, CHAT_ID)
    python weather_on_this_day.py --dry            # лише показати текст і зберегти картинку
    python weather_on_this_day.py --dry --date 12-07   # перевірити будь-яку дату (ММ-ДД)

Дані: Open-Meteo Archive (реаналіз ERA5), без ключа.
Залежності: pip install requests matplotlib
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests

LAT, LON = 50.9077, 34.7981                      # Суми
START = date(1972, 12, 7)                        # точка відліку рубрики
TZ = ZoneInfo("Europe/Kyiv")
API = "https://archive-api.open-meteo.com/v1/archive"
TAGS = "#Суми #СумськийСиноптик #Погода #ЦейДеньУПогоді"
ANCHOR_NOTE = "📌 Саме з 7 грудня 1972 року ведемо відлік у цій рубриці."   # лише 7 грудня
MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


# ------------------------------------------------------------------ дані
def load_history(end: date) -> list:
    """[(дата, tmax, tmin, tmean, опади)] з 1972-12-07 до end."""
    r = requests.get(API, params={
        "latitude": LAT, "longitude": LON,
        "start_date": START.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum",
        "timezone": "Europe/Kyiv",
    }, timeout=180)
    r.raise_for_status()
    d = r.json()["daily"]
    rows = []
    for i, t in enumerate(d["time"]):
        tmax, tmin = d["temperature_2m_max"][i], d["temperature_2m_min"][i]
        if tmax is None or tmin is None:
            continue
        tmean = d["temperature_2m_mean"][i]
        rows.append((date.fromisoformat(t), tmax, tmin,
                     tmean if tmean is not None else (tmax + tmin) / 2,
                     d["precipitation_sum"][i] or 0.0))
    return rows


def pick(rows: list, month: int, day: int) -> list:
    return [r for r in rows if r[0].month == month and r[0].day == day and r[0] >= START]


# ------------------------------------------------------------------ текст
def t(v: float) -> str:
    return f"{v:+.1f}".replace("-", "−") + "°"


def years_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "рік"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "роки"
    return "років"


def build_caption(sel: list, month: int, day: int, this_year: int) -> str:
    warm = max(sel, key=lambda r: r[1])
    cold = min(sel, key=lambda r: r[2])
    avg = sum(r[3] for r in sel) / len(sel)
    wet_share = sum(1 for r in sel if r[4] >= 1.0) / len(sel) * 100
    rain = max(sel, key=lambda r: r[4])
    n = len(sel)
    lines = [
        f"🌡 <b>Цей день у погоді — {day} {MONTHS[month - 1]}</b>",
        f"<i>Спостереження з {sel[0][0].year} року · {n} {years_word(n)}</i>",
        "",
        f"🔥 Рекорд тепла: <b>{t(warm[1])}</b> вдень ({warm[0].year})",
        f"❄️ Рекорд холоду: <b>{t(cold[2])}</b> вночі ({cold[0].year})",
        f"🌡 Зазвичай (середня за {n} {years_word(n)}): <b>{t(avg)}</b>",
        f"🌧 Опади були у {wet_share:.0f}% років" + (f", рекорд — {rain[4]:.1f} мм ({rain[0].year})" if rain[4] >= 1 else ""),
    ]
    last = next((r for r in sel if r[0].year == this_year - 1), None)
    if last:
        lines.append(f"↩️ Торік: {t(last[2])} / {t(last[1])}, опади {last[4]:.1f} мм")
    if (month, day) == (START.month, START.day):
        lines += ["", ANCHOR_NOTE]
    lines += ["", "<i>Дані: Open-Meteo (реаналіз ERA5), не показання окремої станції</i>", TAGS]
    return "\n".join(lines)


# ------------------------------------------------------------------ картинка
def make_chart(sel: list, month: int, day: int, out_path: str, watermark: str | None = None):
    years = np.array([r[0].year for r in sel])
    tmax = np.array([r[1] for r in sel]); tmin = np.array([r[2] for r in sel])
    tmean = np.array([r[3] for r in sel])
    avg = tmean.mean()

    fig = plt.figure(figsize=(12, 8), dpi=100)
    bg = fig.add_axes([0, 0, 1, 1]); bg.axis("off")
    top, bot = np.array([0x14, 0x2B, 0x4F]) / 255, np.array([0x2E, 0x62, 0x82]) / 255
    g = np.linspace(0, 1, 256)[:, None, None]
    bg.imshow(top * (1 - g) + bot * g, aspect="auto", extent=[0, 1, 0, 1])

    ax = fig.add_axes([0.08, 0.13, 0.88, 0.66]); ax.set_facecolor("none")
    light = "#E8F1F6"
    for s in ax.spines.values():
        s.set_color("#8FB3C7")
    ax.tick_params(colors=light, labelsize=12)
    ax.grid(axis="y", color="white", alpha=0.15)

    cmap = plt.get_cmap("coolwarm")
    norm = plt.Normalize(tmean.min(), tmean.max())
    ax.vlines(years, tmin, tmax, colors=cmap(norm(tmean)), linewidth=6, zorder=2)
    ax.scatter(years, tmean, s=16, color="white", zorder=3)
    ax.axhline(avg, ls="--", color="white", alpha=0.65, lw=1.3, zorder=1)
    ax.text(years.max() + 0.9, avg, f"середня {t(avg)}", color=light, fontsize=12, va="bottom", ha="right")

    def mark(x, y, label, up):
        ax.scatter([x], [y], s=170, color="#F6D67A", edgecolors="white", zorder=5)
        ha = "left" if x < years.min() + 6 else "right" if x > years.max() - 6 else "center"
        ax.annotate(label, (x, y), xytext=(0, 14 if up else -22), textcoords="offset points",
                    ha=ha, color="#F6D67A", fontsize=14, fontweight="bold")

    iw, ic = int(np.argmax(tmax)), int(np.argmin(tmin))
    mark(years[iw], tmax[iw], f"{t(tmax[iw])} · {years[iw]}", True)
    mark(years[ic], tmin[ic], f"{t(tmin[ic])} · {years[ic]}", False)

    if (month, day) == (START.month, START.day):
        ax.annotate("1972 — початок відліку", (years.min(), tmin[0]), xytext=(8, -44),
                    textcoords="offset points", color=light, fontsize=12,
                    arrowprops=dict(arrowstyle="->", color=light, alpha=0.7))

    ax.set_xlim(years.min() - 1.5, years.max() + 1.5)
    ax.set_ylim(tmin.min() - 6, tmax.max() + 6)
    ax.set_xticks(sorted({y for y in range(years.min(), years.max() + 1) if y % 5 == 0} | {int(years.min()), int(years.max())}))
    ax.set_ylabel("°C", color=light, fontsize=13)

    fig.text(0.08, 0.93, f"{day} {MONTHS[month - 1]}", color="white", fontsize=36, fontweight="bold")
    fig.text(0.08, 0.875, f"Сумы цього дня, {years.min()}–{years.max()}: від нічного мінімуму до денного максимуму",
             color=light, fontsize=13)
    fig.text(0.08, 0.04, "Сумський синоптик · Дані: Open-Meteo (реаналіз ERA5)", color="#BFD9E6", fontsize=12)
    if watermark:
        fig.text(0.5, 0.45, watermark, color="white", alpha=0.28, fontsize=64, fontweight="bold",
                 rotation=18, ha="center", va="center")
    fig.savefig(out_path, dpi=100)
    plt.close(fig)


# ------------------------------------------------------------------ Telegram
def send_photo(path: str, caption: str):
    with open(path, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/sendPhoto",
            data={"chat_id": os.environ["CHAT_ID"], "caption": caption, "parse_mode": "HTML"},
            files={"photo": f}, timeout=60)
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="не публікувати, лише показати")
    ap.add_argument("--date", help="ММ-ДД, наприклад 12-07 (за замовчуванням сьогодні)")
    ap.add_argument("--out", default="weather_on_this_day.png")
    a = ap.parse_args()

    today = datetime.now(TZ).date()
    month, day = map(int, a.date.split("-")) if a.date else (today.month, today.day)
    rows = load_history(today - timedelta(days=7))      # архів відстає на кілька днів
    sel = pick(rows, month, day)
    if len(sel) < 5:
        sys.exit(f"Замало даних для {day:02d}.{month:02d}: {len(sel)} років")
    make_chart(sel, month, day, a.out)
    caption = build_caption(sel, month, day, today.year)
    if a.dry:
        print(caption)
        return
    send_photo(a.out, caption)


if __name__ == "__main__":
    main()
