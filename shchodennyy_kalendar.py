# -*- coding: utf-8 -*-
"""
Щоденний календар для Telegram-каналу «Сумський синоптик»
https://t.me/sumskoy_sinoptik

Що робить:
  • збирає дані на дату (свята, церковний календар, іменини, легенда/прикмета);
  • рахує фазу Місяця та схід/захід Сонця для Сум (без зовнішніх API);
  • генерує картку (shchodennyy_kalendar_card.py) і публікує пост у канал.

Змінні середовища: BOT_TOKEN, CHAT_ID (беруться з GitHub Secrets).

Приклади запуску:
  python shchodennyy_kalendar.py --dry-run               # лише показати пост
  python shchodennyy_kalendar.py --date 2026-12-25 --dry-run
  python shchodennyy_kalendar.py --force                 # опублікувати негайно
"""
from __future__ import annotations

import argparse
import html
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import shchodennyy_kalendar_data as D

# ── Налаштування ─────────────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Kyiv")
POST_HOUR = 10                      # о котрій годині (за Києвом) публікуємо
SUMY_LAT, SUMY_LON = 50.9077, 34.7981
CHANNEL_NAME = "Сумський синоптик"
CHANNEL_URL = "https://t.me/sumskoy_sinoptik"
BASE_TAGS = ["Календар", "ЩоденнийКалендар", "СумськийСиноптик", "Суми", "Сумщина"]

MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня",
              "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
MONTH_TAG = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
             "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]
WEEKDAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]


# ═════════════════════════════════════════════════════════════════════════════
#  РУХОМІ СВЯТА
# ═════════════════════════════════════════════════════════════════════════════
def orthodox_easter(year: int) -> date:
    """Великдень за юліанською пасхалією (дата у григоріанському календарі)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return date(year, month, day) + timedelta(days=13)      # 1900–2099


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-й заданий день тижня місяця (n=-1 — останній). weekday: 0=пн … 6=нд."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def moveable_events(d: date) -> tuple[list[str], list[str]]:
    """Повертає (державні/народні, церковні) рядки для рухомих свят."""
    state, church = [], []
    easter = orthodox_easter(d.year)
    off = (d - easter).days

    fixed_church = {
        -49: "Прощена неділя. Завершення Масляної, початок Великого посту|Масляна",
        -48: "Чистий понеділок — початок Великого посту|Великий_піст",
        -7: "Вербна неділя|Вербна_неділя",
        -3: "Чистий четвер|Великий_тиждень",
        -2: "Страсна п'ятниця|Великий_тиждень",
        -1: "Страсна субота|Великий_тиждень",
        0: "Великдень — Воскресіння Христове ✝️|Великдень",
        1: "Великодній понеділок (Поливаний)|Великдень",
        7: "Томина неділя (Антипасха)",
        9: "Радониця — день поминання предків|Радониця",
        39: "Вознесіння Господнє|Вознесіння",
        49: "Трійця — Зелені свята 🌿|Трійця",
        50: "Духів день|Трійця",
    }
    if off in fixed_church:
        church.append(fixed_church[off])
    elif -55 <= off <= -50:
        church.append("Масляний (сирний) тиждень|Масляна")
    elif -47 <= off <= -8:
        church.append("Триває Великий піст|Великий_піст")

    moves = {
        nth_weekday(d.year, 5, 6, 2): "День матері|День_матері",
        nth_weekday(d.year, 5, 3, 3): "День вишиванки 🇺🇦|День_вишиванки",
        nth_weekday(d.year, 5, 6, -1): "День Києва|День_Києва",
        nth_weekday(d.year, 6, 6, 3): "День батька / День медичного працівника|День_батька",
        nth_weekday(d.year, 7, 6, 1): "День Військово-Морських Сил ЗСУ|ВМС",
        nth_weekday(d.year, 8, 6, 1): "День Повітряних Сил ЗСУ|Повітряні_сили",
        nth_weekday(d.year, 11, 5, 4): "День пам'яті жертв голодоморів 🕯|Голодомор",
        nth_weekday(d.year, 10, 6, 1): "День працівників освіти (в Україні — перша неділя жовтня)",
    }
    if d in moves:
        state.append(moves[d])
    return state, church


# ═════════════════════════════════════════════════════════════════════════════
#  МІСЯЦЬ (фази за Меєром, точність ~кілька хвилин) — без зовнішніх залежностей
# ═════════════════════════════════════════════════════════════════════════════
JD_UNIX_EPOCH = 2440587.5
SYNODIC = 29.530588861


def _jd_to_dt(jd: float) -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(days=jd - JD_UNIX_EPOCH)


def _dt_to_jd(dt: datetime) -> float:
    return dt.timestamp() / 86400 + JD_UNIX_EPOCH


def _phase_jde(k: float) -> float:
    """JDE фази: k цілий — молодик, +0.25 — перша чверть, +0.5 — повня, +0.75 — остання чверть."""
    r = math.radians
    T = k / 1236.85
    jde = (2451550.09766 + SYNODIC * k + 0.00015437 * T**2
           - 0.000000150 * T**3 + 0.00000000073 * T**4)
    E = 1 - 0.002516 * T - 0.0000074 * T**2
    M = r(2.5534 + 29.10535670 * k - 0.0000014 * T**2)
    Mp = r(201.5643 + 385.81693528 * k + 0.0107582 * T**2)
    F = r(160.7108 + 390.67050284 * k - 0.0016118 * T**2)
    Om = r(124.7746 - 1.56375588 * k + 0.0020672 * T**2)
    s = math.sin
    frac = round(k % 1, 2)
    if frac in (0.0, 0.5):
        if frac == 0.0:
            c = (-0.40720, 0.17241, 0.01608, 0.01039, 0.00739, -0.00514, 0.00208)
        else:
            c = (-0.40614, 0.17302, 0.01614, 0.01043, 0.00734, -0.00515, 0.00209)
        corr = (c[0] * s(Mp) + c[1] * E * s(M) + c[2] * s(2 * Mp) + c[3] * s(2 * F)
                + c[4] * E * s(Mp - M) + c[5] * E * s(Mp + M) + c[6] * E**2 * s(2 * M)
                - 0.00111 * s(Mp - 2 * F) - 0.00057 * s(Mp + 2 * F)
                + 0.00056 * E * s(2 * Mp + M) - 0.00042 * s(3 * Mp)
                + 0.00042 * E * s(M + 2 * F) + 0.00038 * E * s(M - 2 * F)
                - 0.00024 * E * s(2 * Mp - M) - 0.00017 * s(Om))
    else:
        corr = (-0.62801 * s(Mp) + 0.17172 * E * s(M) - 0.01183 * E * s(Mp + M)
                + 0.00862 * s(2 * Mp) + 0.00804 * s(2 * F) + 0.00454 * E * s(Mp - M)
                + 0.00204 * E**2 * s(2 * M) - 0.00180 * s(Mp - 2 * F)
                - 0.00070 * s(Mp + 2 * F) - 0.00040 * s(3 * Mp)
                - 0.00034 * E * s(2 * Mp - M) + 0.00032 * E * s(M + 2 * F)
                + 0.00032 * E * s(M - 2 * F) - 0.00028 * E**2 * s(Mp + 2 * M)
                + 0.00027 * E * s(2 * Mp + M) - 0.00017 * s(Om))
        w = (0.00306 - 0.00038 * E * math.cos(M) + 0.00026 * math.cos(Mp)
             - 0.00002 * math.cos(Mp - M) + 0.00002 * math.cos(Mp + M)
             + 0.00002 * math.cos(2 * F))
        corr += w if frac == 0.25 else -w
    return jde + corr


PHASE_EVENTS = {0.0: ("🌑", "Новий місяць", "Новомісяччя"),
                0.25: ("🌓", "Перша чверть", "ПершаЧверть"),
                0.5: ("🌕", "Повня", "Повня"),
                0.75: ("🌗", "Остання чверть", "ОстанняЧверть")}


def moon_info(d: date) -> dict:
    noon = datetime(d.year, d.month, d.day, 12, tzinfo=TZ)
    jd = _dt_to_jd(noon)
    k0 = math.floor((jd - 2451550.09766) / SYNODIC)

    # 1) подія фази, що припадає на цю добу (за Києвом)
    event = None
    for k in range(k0 - 2, k0 + 3):
        for q in (0.0, 0.25, 0.5, 0.75):
            moment = _jd_to_dt(_phase_jde(k + q)).astimezone(TZ)
            if moment.date() == d:
                emoji, name, tag = PHASE_EVENTS[q]
                event = {"emoji": emoji, "name": name, "tag": tag, "time": moment.strftime("%H:%M")}

    # 2) частка циклу: від попереднього молодика до наступного
    prev_new = max(_phase_jde(k) for k in range(k0 - 2, k0 + 3) if _phase_jde(k) <= jd)
    next_new = min(_phase_jde(k) for k in range(k0 - 2, k0 + 3) if _phase_jde(k) > jd)
    frac = (jd - prev_new) / (next_new - prev_new)
    age = jd - prev_new
    illum = (1 - math.cos(2 * math.pi * frac)) / 2

    if event:
        emoji, name, tag = event["emoji"], event["name"], event["tag"]
    else:
        for limit, e, n, t in ((0.25, "🌒", "Зростаючий серп (молодий місяць)", "МолодийМісяць"),
                               (0.50, "🌔", "Зростаючий місяць", "ЗростаючийМісяць"),
                               (0.75, "🌖", "Спадаючий місяць", "СпадаючийМісяць"),
                               (1.01, "🌘", "Спадаючий серп (старий місяць)", "СтарийМісяць")):
            if frac < limit:
                emoji, name, tag = e, n, t
                break
    return {"emoji": emoji, "name": name, "tag": tag, "event": event,
            "frac": frac, "age": age, "illum": illum}


# ═════════════════════════════════════════════════════════════════════════════
#  СОНЦЕ (формули NOAA) для Сум
# ═════════════════════════════════════════════════════════════════════════════
def sun_info(d: date) -> dict:
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat = math.radians(SUMY_LAT)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl))
              - math.tan(lat) * math.tan(decl))
    cos_ha = max(-1.0, min(1.0, cos_ha))
    ha = math.degrees(math.acos(cos_ha))
    rise_utc = 720 - 4 * (SUMY_LON + ha) - eqt        # хвилини від 00:00 UTC
    set_utc = 720 - 4 * (SUMY_LON - ha) - eqt

    midnight = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)

    def local(minutes: float) -> datetime:
        return (midnight + timedelta(minutes=minutes)).astimezone(TZ)

    rise, sset = local(rise_utc), local(set_utc)
    length = int(round(set_utc - rise_utc))
    return {"sunrise": rise.strftime("%H:%M"), "sunset": sset.strftime("%H:%M"),
            "day_len": f"{length // 60} год {length % 60:02d} хв"}


# ═════════════════════════════════════════════════════════════════════════════
#  ЗБИРАННЯ ДАНИХ ДНЯ
# ═════════════════════════════════════════════════════════════════════════════
def _split(item: str) -> tuple[str, str | None]:
    text, _, tag = item.partition("|")
    return text.strip(), (tag.strip() or None)


def build_day(d: date) -> dict:
    key = d.strftime("%m-%d")
    state_raw = list(D.STATE.get(key, [])) + list(D.LOCAL.get(key, []))
    church_raw = list(D.CHURCH.get(key, []))
    m_state, m_church = moveable_events(d)
    state_raw = m_state + state_raw
    church_raw = m_church + church_raw

    state = [_split(x) for x in state_raw]
    church = [_split(x) for x in church_raw]

    # легенда: спочатку під дату, інакше — з загального пулу
    if key in D.LEGENDS:
        legend = D.LEGENDS[key]
    else:
        legend = D.GENERAL_LEGENDS[d.timetuple().tm_yday % len(D.GENERAL_LEGENDS)]
    prykmety = D.PRYKMETY[d.month]
    prykmeta = prykmety[d.day % len(prykmety)]

    moon = moon_info(d)
    sun = sun_info(d)

    tags = list(BASE_TAGS) + [MONTH_TAG[d.month - 1], moon["tag"]]
    if key in D.NAMES:
        tags.append("Іменини")
    for _, t in state + church:
        if t:
            tags.append(t)
    seen, uniq = set(), []
    for t in tags:                                   # без дублів, збереження порядку
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)

    return {"date": d, "key": key, "weekday": WEEKDAYS[d.weekday()],
            "month_gen": MONTHS_GEN[d.month - 1],
            "state": state, "church": church, "names": D.NAMES.get(key),
            "legend": legend, "prykmeta": prykmeta, "moon": moon, "sun": sun,
            "tags": uniq}


# ═════════════════════════════════════════════════════════════════════════════
#  ФОРМАТУВАННЯ ПОСТУ (HTML для Telegram)
# ═════════════════════════════════════════════════════════════════════════════
def _e(s: str) -> str:
    return html.escape(s, quote=False)


def format_post(info: dict) -> str:
    d = info["date"]
    moon, sun = info["moon"], info["sun"]
    L: list[str] = []
    L.append(f"📅 <b>{info['weekday']}, {d.day} {info['month_gen']} {d.year}</b>")
    L.append("")

    if info["state"]:
        L.append("🎉 <b>Свята та пам'ятні дні</b>")
        L += [f"• {_e(t)}" for t, _ in info["state"]]
        L.append("")
    if info["church"]:
        L.append("⛪️ <b>Церковний календар</b>")
        L += [f"• {_e(t)}" for t, _ in info["church"]]
        L.append("")
    if info["names"]:
        L.append("🎂 <b>Іменини святкують</b>")
        L.append(_e(info["names"]))
        L.append("")
    if not info["state"] and not info["church"]:
        L.append("🌿 <i>Сьогодні без великих свят — звичайний день для добрих справ.</i>")
        L.append("")

    ev = moon["event"]
    moon_line = f"{moon['emoji']} <b>Місяць:</b> {_e(moon['name'])}"
    if ev:
        moon_line += f" (о {ev['time']})"
    L.append(moon_line)
    L.append(f"Освітленість диска ≈ {round(moon['illum'] * 100)}% · вік ≈ {moon['age']:.0f}-й день")
    L.append(f"🌅 Схід {sun['sunrise']} · 🌇 Захід {sun['sunset']} · день {sun['day_len']}  <i>(Суми)</i>")
    L.append("")

    title, text = info["legend"]
    L.append(f"📜 <b>Легенда дня: {_e(title)}</b>")
    L.append(f"<i>{_e(text)}</i>")
    L.append("")
    L.append(f"🌦 <b>Народна прикмета:</b> {_e(info['prykmeta'])}")
    L.append("")
    L.append(" ".join("#" + t for t in info["tags"][:12]))
    return "\n".join(L)


def format_caption(info: dict) -> str:
    d = info["date"]
    return (f"📅 <b>Щоденний календар · {d.day} {info['month_gen']} {d.year}</b>\n"
            f"{info['weekday']} · {info['moon']['emoji']} {_e(info['moon']['name'])}")


# ═════════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ═════════════════════════════════════════════════════════════════════════════
def _api(method: str, token: str, **kw):
    import requests
    url = f"https://api.telegram.org/bot{token}/{method}"
    last = None
    for attempt in range(1, 4):
        try:
            r = requests.post(url, timeout=60, **kw)
            data = r.json()
            if data.get("ok"):
                return data
            last = data
            if r.status_code == 429:                       # flood control
                time.sleep(data.get("parameters", {}).get("retry_after", 5) + 1)
                continue
            break
        except Exception as exc:                           # мережа
            last = {"error": str(exc)}
            time.sleep(3 * attempt)
    raise RuntimeError(f"Telegram {method} не вдався: {last}")


def send_message(token: str, chat_id: str, text: str):
    return _api("sendMessage", token,
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": "true"})


def send_photo(token: str, chat_id: str, path: str, caption: str):
    with open(path, "rb") as fh:
        return _api("sendPhoto", token,
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": fh})


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser(description="Щоденний календар для Telegram-каналу")
    ap.add_argument("--date", help="РРРР-ММ-ДД (за замовчуванням — сьогодні за Києвом)")
    ap.add_argument("--dry-run", action="store_true", help="не публікувати, лише показати")
    ap.add_argument("--force", action="store_true", help="ігнорувати перевірку години 10:00")
    ap.add_argument("--no-card", action="store_true", help="не створювати картку")
    ap.add_argument("--card-out", default="output/card.png", help="куди зберегти картку")
    args = ap.parse_args()

    now = datetime.now(TZ)

    # GitHub Actions запускає два cron (на літній і зимовий час) — публікуємо лише о 10:00 за Києвом
    if (os.getenv("GITHUB_EVENT_NAME") == "schedule" and not args.force
            and now.hour != POST_HOUR):
        print(f"Зараз {now:%H:%M} за Києвом — не година публікації ({POST_HOUR}:00). Пропускаю.")
        return 0

    d = date.fromisoformat(args.date) if args.date else now.date()
    info = build_day(d)
    text = format_post(info)

    card_path = None
    if not args.no_card:
        try:
            from shchodennyy_kalendar_card import generate_card
            os.makedirs(os.path.dirname(args.card_out) or ".", exist_ok=True)
            card_path = generate_card(info, args.card_out)
        except Exception as exc:                            # картка — не критична
            print(f"⚠️  Картку не створено ({exc}). Публікую лише текст.", file=sys.stderr)

    if args.dry_run:
        print(text)
        print("\n— довжина тексту:", len(text), "символів")
        if card_path:
            print("— картка збережена:", card_path)
        return 0

    token, chat_id = os.getenv("BOT_TOKEN"), os.getenv("CHAT_ID")
    if not token or not chat_id:
        print("❌ Не задано BOT_TOKEN або CHAT_ID.", file=sys.stderr)
        return 1

    if card_path:
        send_photo(token, chat_id, card_path, format_caption(info))
    send_message(token, chat_id, text)
    print(f"✅ Опубліковано календар на {d.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
