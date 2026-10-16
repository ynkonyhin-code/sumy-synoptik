"""Рубрика «Цей день у погоді»: найтепліше/найхолодніше та типова погода Сум для сьогоднішньої дати
за всі роки, починаючи з START (зараз 7 грудня 2022), + картинка-графік.

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
START = date(2022, 12, 7)                        # точка відліку рубрики (для тексту й графіка)
CHART_FROM = None                                # None = графік за весь період; напр. date(2012, 1, 1) = лише останні роки
TZ = ZoneInfo("Europe/Kyiv")
API = "https://archive-api.open-meteo.com/v1/archive"
TAGS = "#Суми #СумськийСиноптик #Погода #ЦейДеньУПогоді"
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


def years_gen(n: int) -> str:
    """«з 21 року», «з 4 років»."""
    return "року" if n % 10 == 1 and n % 100 != 11 else "років"


def build_caption(sel: list, month: int, day: int, this_year: int) -> str:
    warm = max(sel, key=lambda r: r[1])
    cold = min(sel, key=lambda r: r[2])
    avg = sum(r[3] for r in sel) / len(sel)
    rain = max(sel, key=lambda r: r[4])
    n = len(sel)
    wet_n = sum(1 for r in sel if r[4] >= 1.0)
    long_run = n >= 15                       # «рекорд» кажемо лише для довгого періоду
    first, last_y = sel[0][0].year, sel[-1][0].year
    lines = [
        f"🌡 <b>Цей день у погоді — {day} {MONTHS[month - 1]}</b>",
        f"<i>Дані за {n} {years_word(n)}: {first}–{last_y}</i>",
        "",
        f"🔥 {'Рекорд тепла' if long_run else 'Найтепліше'}: <b>{t(warm[1])}</b> вдень ({warm[0].year})",
        f"❄️ {'Рекорд холоду' if long_run else 'Найхолодніше'}: <b>{t(cold[2])}</b> вночі ({cold[0].year})",
        f"🌡 Зазвичай (середня за {n} {years_word(n)}): <b>{t(avg)}</b>",
        f"🌧 Опади були у {wet_n} з {n} {years_gen(n)}"
        + (f", {'рекорд' if long_run else 'найбільше'} — {rain[4]:.1f} мм ({rain[0].year})" if rain[4] >= 1 else ""),
    ]
    last = next((r for r in sel if r[0].year == this_year - 1), None)
    if last:
        lines.append(f"↩️ Торік: вночі {t(last[2])}, вдень {t(last[1])}, опади {last[4]:.1f} мм")
    if (month, day) == (START.month, START.day):
        lines += ["", f"📌 Саме з {START.day} {MONTHS[START.month - 1]} {START.year} року ведемо відлік у цій рубриці."]
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
    n = len(years)
    few = n <= 12
    ax.vlines(years, tmin, tmax, colors=cmap(norm(tmean)), linewidth=26 if n <= 8 else 14 if few else 6, zorder=2)
    ax.scatter(years, tmean, s=60 if few else 16, color="white", zorder=3)
    ax.axhline(avg, ls="--", color="white", alpha=0.65, lw=1.3, zorder=1)
    ax.text(0.012, 0.975, f"┄┄  середня за період: {t(avg)}", transform=ax.transAxes, color=light, fontsize=12,
            va="top", ha="left", bbox=dict(boxstyle="round,pad=0.35", facecolor="#142B4F", alpha=0.75, edgecolor="none"))

    def mark(x, y, label, up):
        ax.scatter([x], [y], s=170, color="#F6D67A", edgecolors="white", zorder=5)
        frac = (x - years.min()) / max(years.max() - years.min(), 1)
        ha = "left" if frac < 0.12 else "right" if frac > 0.88 else "center"
        ax.annotate(label, (x, y), xytext=(0, 14 if up else -22), textcoords="offset points",
                    ha=ha, color="#F6D67A", fontsize=14, fontweight="bold")

    iw, ic = int(np.argmax(tmax)), int(np.argmin(tmin))
    mark(years[iw], tmax[iw], f"{t(tmax[iw])} · {years[iw]}", True)
    mark(years[ic], tmin[ic], f"{t(tmin[ic])} · {years[ic]}", False)

    if (month, day) == (START.month, START.day) and years.min() == START.year:
        ax.annotate(f"{START.year} — початок відліку", (years.min(), tmin[0]),
                    xytext=(years.min() + (0.2 if few else 1.2), tmin.min() - 4.5), textcoords="data",
                    color=light, fontsize=12, ha="left", va="center",
                    arrowprops=dict(arrowstyle="->", color=light, alpha=0.7))

    pad = 0.8 if few else 1.5
    ax.set_xlim(years.min() - pad, years.max() + pad)
    ax.set_ylim(tmin.min() - 6, tmax.max() + 6)
    ax.set_xticks(list(range(int(years.min()), int(years.max()) + 1)) if few
                  else [y for y in range(int(years.min()), int(years.max()) + 1) if y % 5 == 0])
    ax.set_ylabel("°C", color=light, fontsize=13)

    fig.text(0.08, 0.91, f"{day} {MONTHS[month - 1]}", color="white", fontsize=36, fontweight="bold")
    fig.text(0.08, 0.855, f"Суми цього дня, {years.min()}–{years.max()}: від нічного мінімуму до денного максимуму",
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
    if len(sel) < 2:                                    # напр. 29 лютого: поста сьогодні не буде
        print(f"Замало даних для {day:02d}.{month:02d}: {len(sel)} рік — пропускаємо.")
        return
    chart_sel = [r for r in sel if CHART_FROM is None or r[0] >= CHART_FROM]
    make_chart(chart_sel if len(chart_sel) >= 2 else sel, month, day, a.out)
    caption = build_caption(sel, month, day, today.year)
    if a.dry:
        print(caption)
        return
    send_photo(a.out, caption)


if __name__ == "__main__":
    main()
