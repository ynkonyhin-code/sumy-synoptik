#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
«Котик-черговий» — чотири щоденні публікації для «Київського не гідрометцентру».
https://t.me/kyyivskyy_ne_hidromettsentr

  morning   05:00  котик заступає на чергування: жартівливий вступ + що буде сьогодні + що, можливо, колись буде
  ad_day    14:05  картинка «Реклама каналу» (без тексту)
  ad_night  22:35  картинка «Реклама каналу» (без тексту)
  evening   23:05  котик здає зміну: що сьогодні було / дізналися читачі + «Спокійної та тихої ночі»

Картинка кота складається з аватара (kotyk_avatar.png, прозорий фон) і фону: вранці — «світанок», ввечері — «нічне небо».
Реклама: покладіть у корінь репо файл reklama_kanalu.jpg (або .png/.webp). Якщо файлів кілька (reklama_kanalu_1.jpg,
reklama_kanalu_2.jpg …), вони чергуються по днях і слотах. Немає файлу — слот просто пропускається.

«Що дізналися» ввечері береться лише з того, що можна ПЕРЕВІРИТИ без мережі: файли стану рубрик (опубліковано
сьогодні), детермінований вибір «Хвилинки тепла» та журнал подій (events_db: тривоги, магнітні бурі, відключення).
Якщо журнал порожній, про тривоги кіт мовчить — він не стверджує «тривог не було», бо міг їх не помітити.

Точний час: workflow стартує за ~20 хв до цілі, скрипт готує пост і ЧЕКАЄ до потрібної хвилини (GitHub затримує запуски).
Повторна публікація того ж слота за добу блокується файлом kotyk_dezhurnyi_state.json.

Змінні середовища: TELEGRAM_BOT_TOKEN (або BOT_TOKEN), CHAT_ID. Необов'язково: FORCE_RUN=1 (публікувати зараз).
Запуск без відправки:  python kotyk_dezhurnyi.py --slot morning --dry-run
"""
from __future__ import annotations

import argparse
import glob
import html
import io
import json
import logging
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFilter

TZ = ZoneInfo("Europe/Kyiv")
HERE = os.path.dirname(os.path.abspath(__file__))
AVATAR = os.path.join(HERE, "kotyk_avatar.png")
STATE_FILE = os.path.join(HERE, "kotyk_dezhurnyi_state.json")
AD_GLOBS = ["reklama_kanalu*.jpg", "reklama_kanalu*.jpeg", "reklama_kanalu*.png", "reklama_kanalu*.webp"]
log = logging.getLogger("kotyk")

# Слоти: час публікації за Києвом, тип, скільки хвилин можна чекати/запізнюватись.
SLOTS = {
    "morning":  {"at": "05:00", "kind": "cat", "late": 120},
    "ad_day":   {"at": "14:05", "kind": "ad",  "late": 120},
    "ad_night": {"at": "22:35", "kind": "ad",  "late": 45},
    "evening":  {"at": "23:05", "kind": "cat", "late": 50},
}
EARLY_MIN = 60            # раніше ніж за 60 хв до цілі — не наш запуск (відсікає зайвий сезонний cron)
SILENT = True             # без звуку: котик не будить і не відволікає (False — зі звуком)
SHOW_ALERT_SUMMARY = True  # вечірній підсумок: рядок про тривоги (лише якщо вони є в журналі)
HASHTAGS = {"morning": "#КотикЧерговий #ДоброгоРанку #КиївськийНеГідрометцентр",
            "evening": "#КотикЧерговий #СпокійноїНочі #КиївськийНеГідрометцентр"}


def kyiv_now() -> datetime:
    return datetime.now(TZ)


# ═══════════════════════ Дані для тексту (правте тут) ═══════════════════════
# (час, емодзі, назва, дні тижня [0=пн … 6=нд] або None = щодня). Час — орієнтовний.
def program(today: date) -> list[tuple[str, str, str]]:
    utc10 = datetime(today.year, today.month, today.day, 7, 0, tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    years = today.year - 1991
    items = [
        ("06:00", "🇺🇦", "Київщина: прогноз по області", None),
        ("07:05", "☀️", "Погода в Києві (далі ще о 13:05 і 19:05)", None),
        ("07:10", "🔮", "Гороскоп дня", None),
        ("07:30", "💱", "Курси валют і ціни на пальне", None),
        ("08:10", "🚆", "Поїзди до Європи без пересадок", None),
        ("09:05", "🧲", "Космічна погода: магнітне поле й Сонце", None),
        ("09:30", "🧩", "Як працює погода — простими словами", {6}),
        (utc10.strftime("%H:%M"), "📊", f"Цей день у погоді: рекорди за {years} років", None),
        ("10:10", "📅", "Підсумок тижня", {0}),
        ("11:05", "🥇", "Курс дорогоцінних металів", None),
        ("12:05", "₿", "Курс криптовалют", None),
        ("12:30", "🍀", "Найцікавіші забобони світу (час щодня різний)", None),
        ("15:30", "📖", "Словник синоптика — слово дня (час трохи гуляє)", {2, 5}),
        ("16:05", "🔭", "Небо над Києвом", None),
        ("17:50", "🌪", "Погода, що змінила історію (час трохи гуляє)", {3}),
        ("18:15", "🧠", "Вікторина тижня — перевірте себе (час трохи гуляє)", {6}),
        ("18:15", "🗳", "Опитування тижня — вирішуєте ви (час трохи гуляє)", {0}),
        ("18:30", "🌌", "Таємниці неба (час трохи гуляє)", {1, 4}),
        ("19:05", "🧡", "Хвилинка тепла", None),
        ("21:10", "🌙", "Погода, яка має значення — на завтра", None),
    ]
    return [(t, e, n) for t, e, n, days in items if days is None or today.weekday() in days]


ALWAYS_ON = [
    "🚨 Тривога й відбій у Києві — цілодобово, без вихідних",
    "🪖 Загальні бойові втрати ворога — одразу після зведення Генштабу",
    "🧲 Сповіщення про магнітні бурі — за потреби",
]
# Ідеї «може колись» — котик щодня називає три випадкові (це жарт-анонс, а не обіцянка!)
IDEAS = [
    "«Запитай синоптика» — відповіді на ваші питання про погоду",
    "відключення та ремонти: світло, вода, газ — усе в одному місці",
    "погода на вихідні — для тих, хто планує, і для тих, хто просто надіється",
    "прогноз настрою котика (точність — 50%, як у всіх)",
    "календар городника: коли сіяти, а коли просто дивитися на грядки",
    "прогноз для тих, хто вигулює собак (і для собак теж)",
    "щотижневий мур-рапорт: головне за тиждень",
    "карта «де зараз найкраща погода у країні»",
    "прикмети й народні спостереження: перевіряємо, що працює",
]
MORNING_OPENERS = [
    "Мур-р! Я знову заступаю на чергування: окуляри протерті, шарф поправлений, лапи на клавіатурі.",
    "Доброго ранку! Офіційно я «не гідрометцентр», тож хмари слухаються мене лише тоді, коли самі захочуть.",
    "Прокинувся раніше за будильник, бо хтось має першим сказати вам «доброго ранку». Це я. Зазвичай.",
    "Зміну прийняв, лоток перевірив, прогноз приготував. Кава — вам, молоко — мені.",
    "Сонце на небі? Хмари на місці? Тоді працюємо. Я — на чергуванні, ви — на добрі справи.",
    "Мур-мур-рапорт: нічна зміна без пригод, ранкова зміна розпочата. Дякую, що ви зі мною.",
    "Я, звісно, кіт, а не метеостанція, але вуса відчувають зміни тиску. Тож попереду буде цікаво.",
    "Мій девіз: «Прогноз — справа серйозна, а вуха — ще серйозніша». Поїхали!",
    "Усім привіт! Я на місці, окуляри на носі, а настрій — вищий за атмосферний тиск.",
    "Хвіст — трубою, зміна — розпочата! Сьогодні розповім вам багато цікавого.",
]
EVENING_OPENERS = [
    "Мур-р… Зміну здаю. Окуляри — у футляр, шарф — на спинку стільця, лапи — на подушку.",
    "День був насичений: встигли стільки всього, що я навіть подумав про відпустку (лише подумав).",
    "Підбиваю підсумки: прогнози — подані, цифри — пораховані, хмари — зафіксовані (вони не здалися).",
    "Офіційно я не гідрометцентр, але зміну здаю за всіма правилами: з журналом, печаткою і лапкою.",
    "Ваш котик-черговий звітує: день прожито недарма. Я ловив не мишей, а новини.",
    "Дякую, що були зі мною цілий день. Це приємніше, ніж тепла батарея в жовтні.",
    "Поки ви збираєтесь спати, я з суворим виглядом перевіряю: чи всі рубрики на місці. Усі! (Сам здивований.)",
    "Хвіст — до купи, зміна — здана. Мур-р, ось що ми сьогодні встигли.",
]
EVENING_GENERIC = [
    "☁️ Погода, гороскоп, курси й космос — усе вийшло за розкладом (майже без запізнень)",
    "🐾 А ще — кілька десятків мур-рів, які я не публікував, бо вони не за темою",
]
GOODNIGHT = "Спокійної та тихої ночі всім жителям України, Києва та Київщини! 🇺🇦💙💛"
GOODNIGHT_TAILS = [
    "Бережіть себе й одне одного. Я чергую — ви відпочивайте.",
    "Нехай ніч буде тихою, а ранок — добрим. Побачимось о 05:00.",
    "Я не сплю (я ж кіт, сплю лише вдень), тож усе під наглядом. До ранку! 🐾",
    "Нехай вам сниться тепла погода без тривог. До зустрічі вранці!",
]


# ═══════════════════════ Дані дня (без мережі) ═══════════════════════
def _read_json(name: str) -> dict:
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _published_index(state_name: str, today: date, size: int) -> int | None:
    """Індекс випуску, опублікованого СЬОГОДНІ (за файлом стану рубрики), або None."""
    st = _read_json(state_name)
    if st.get("last_date") != today.isoformat() or "next_index" not in st or not size:
        return None
    return (int(st["next_index"]) - 1) % size


def _list_of(mod) -> list:
    return getattr(mod, "ISSUES", None) or getattr(mod, "POSTS", None) or getattr(mod, "TERMS", None) or getattr(mod, "IST", None) or []


def today_facts(today: date) -> list[str]:
    e = lambda s: html.escape(str(s), quote=False)
    out: list[str] = []
    try:                                                   # Забобони
        import zabobony_svitu_data as m
        i = _published_index("zabobony_svitu_state.json", today, len(_list_of(m)))
        if i is not None:
            p = _list_of(m)[i]
            out.append(f"🍀 Найцікавіші забобони {e(p.get('from') or p['name'])}")
    except Exception as ex:
        log.debug("забобони: %s", ex)
    rubrics = (("tayemnytsi_neba_state.json", "tayemnytsi_neba_data", "Таємниці неба", "🌌", lambda x: f"«{x['title']}»"),
               ("yak_pratsyuye_pohoda_state.json", "yak_pratsyuye_pohoda_data", "Як працює погода", "🧩", lambda x: f"«{x['title']}»"),
               ("slovnyk_synoptyka_state.json", "slovnyk_synoptyka_data", "Словник синоптика", "📖", lambda x: f"«{x['term']}»"),
               ("istoria_pohody_state.json", "istoria_pohody_data", "Погода, що змінила історію", "🌪", lambda x: f"{x['year']} · {x['title']}"))
    for state, mod, label, icon, fmt in rubrics:
        try:
            m = __import__(mod)
            i = _published_index(state, today, len(_list_of(m)))
            if i is not None:
                out.append(f"{icon} {label}: {e(fmt(_list_of(m)[i]))}")
        except Exception as ex:
            log.debug("%s: %s", label, ex)
    try:                                                   # Хвилинка тепла — вибір детермінований за датою
        import khvylynka_tepla as kt
        cfg = _read_json("khvylynka_tepla_posts.json")
        post, cat, _key = kt.pick_post(today, cfg)
        if post.get("title"):
            out.append(f"🧡 Хвилинка тепла ({e(cat['label'])}): «{e(post['title'])}»")
    except Exception as ex:
        log.debug("хвилинка: %s", ex)
    try:                                                   # Вікторина / опитування (за файлом стану)
        st = _read_json("viktoryna_opytuvannia_state.json")
        for kind, icon, label in (("quiz", "🧠", "Вікторина тижня"), ("poll", "🗳", "Опитування")):
            k = st.get(kind, {})
            if k.get("last_date") == today.isoformat() and (k.get("last") or {}).get("q"):
                out.append(f"{icon} {label}: «{e(k['last']['q'])}»")
    except Exception as ex:
        log.debug("вікторина: %s", ex)
    try:                                                   # Журнал подій
        import events_db as ev
        t0 = datetime.combine(today, dtime(0, 0))
        t1 = t0 + timedelta(days=1)
        if SHOW_ALERT_SUMMARY:
            spans = ev.alert_durations(t0, t1)
            if spans:
                out.append(f"🚨 Повітряних тривог у Києві: {len(spans)} (разом {ev._fmt_dur(sum(spans))}). "
                           "Дякуємо, що ви обережні")
        n = ev._count_events("space", t0, t1)
        if n:
            out.append(f"🧲 Магнітних бур: {n}")
        for etype in ("water", "power", "gas", "dsns"):
            n = ev._count_events(etype, t0, t1)
            if n:
                out.append(f"{ev.TYPE_TITLES[etype]}: {n}")
    except Exception as ex:
        log.debug("журнал: %s", ex)
    return out


# ═══════════════════════ Тексти ═══════════════════════
def build_morning(today: date) -> tuple[str, str]:
    rnd = random.Random(f"kotyk-morning-{today}")
    e = lambda s: html.escape(s, quote=False)
    header = "🐾 <b>Котик-черговий заступає на зміну</b>\n\n" + e(rnd.choice(MORNING_OPENERS))
    L = ["📋 <b>Що буде сьогодні</b> <i>(час приблизний)</i>"]
    L += [f"{t} · {ic} {e(n)}" for t, ic, n in program(today)]
    L.append("")
    L += ALWAYS_ON
    if 1 <= today.day <= 8:
        L.append("🏙 Ціни на нерухомість і оренду — раз на місяць (саме цими днями)")
    ideas = rnd.sample(IDEAS, 3)
    L += ["", "🔮 <b>А що, якщо колись…</b> <i>(це я просто мрію вголос)</i>"]
    L += [f"▫️ {e(x)}" for x in ideas]
    L += ["", "Усе це — я, ваш котик. І так, окуляри справжні. 😎", "", HASHTAGS["morning"]]
    return header, "\n".join(L)


def build_evening(today: date) -> tuple[str, str]:
    rnd = random.Random(f"kotyk-evening-{today}")
    e = lambda s: html.escape(s, quote=False)
    header = "🌙 <b>Котик-черговий здає зміну</b>\n\n" + e(rnd.choice(EVENING_OPENERS))
    facts = today_facts(today)
    L = ["📌 <b>Що ми сьогодні дізналися</b>"]
    L += [f"▫️ {x}" for x in facts] if facts else []
    L += [f"▫️ {e(rnd.choice(EVENING_GENERIC))}"]
    L += ["", f"<b>{e(GOODNIGHT)}</b>", e(rnd.choice(GOODNIGHT_TAILS)), "", HASHTAGS["evening"]]
    return header, "\n".join(L)


# ═══════════════════════ Картинки ═══════════════════════
def _gradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img.convert("RGBA")


def compose_cat(slot: str, today: date, out: str, size: int = 1280) -> str:
    if slot == "morning":
        bg = _gradient(size, (96, 176, 255), (255, 214, 150))
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((size * 0.55, size * 0.62, size * 1.25, size * 1.32), fill=(255, 236, 170, 140))
        bg = Image.alpha_composite(bg, glow.filter(ImageFilter.GaussianBlur(90)))
    else:
        bg = _gradient(size, (5, 10, 28), (24, 42, 92))
        rnd = random.Random(f"stars-{today}")
        d = ImageDraw.Draw(bg)
        for _ in range(170):
            x, y, r = rnd.randrange(size), rnd.randrange(size), rnd.choice((1, 1, 2, 2, 3))
            a = rnd.randrange(110, 255)
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, a))
        moon = Image.new("RGBA", (size, size), (0, 0, 0, 0))                      # півмісяць на окремому шарі:
        md = ImageDraw.Draw(moon)
        md.ellipse((90, 70, 230, 210), fill=(246, 244, 226, 255))
        md.ellipse((128, 56, 262, 190), fill=(0, 0, 0, 0))                        # «відкушуємо» прозорістю, а не кольором
        bg = Image.alpha_composite(bg, moon)
    av = Image.open(AVATAR).convert("RGBA")
    side = int(size * 0.93)
    av = av.resize((side, side), Image.LANCZOS)
    x = y = (size - side) // 2
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((x + 6, y + 18, x + side - 6, y + side + 8), fill=(0, 0, 0, 120))
    bg = Image.alpha_composite(bg, shadow.filter(ImageFilter.GaussianBlur(22)))
    bg.alpha_composite(av, (x, y))
    bg.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out


def pick_ad(today: date, slot: str) -> str | None:
    files = sorted({p for g in AD_GLOBS for p in glob.glob(os.path.join(HERE, g))})
    if not files:
        return None
    # номер дня + зсув для нічного слота: удень і вночі — різні картинки, а з дня на день вони міняються місцями
    return files[(today.toordinal() + (1 if slot == "ad_night" else 0)) % len(files)]


def prepare_ad(path: str, out: str) -> str:
    """Telegram: фото ≤ 10 МБ, сума сторін ≤ 10000. Підходящий файл відправляємо як є."""
    ok_ext = path.lower().endswith((".jpg", ".jpeg", ".png"))
    with Image.open(path) as im:
        w, h = im.size
        if ok_ext and os.path.getsize(path) <= 9_500_000 and w + h <= 9_500 and im.mode != "RGBA":
            return path
        im = im.convert("RGB")
        im.thumbnail((2560, 2560))
        im.save(out, "JPEG", quality=90, optimize=True)
    return out


# ═══════════════════════ Telegram, стан ═══════════════════════
def tg(method: str, token: str, **kw) -> dict:
    for attempt in (1, 2, 3):
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=90, **kw)
        if r.status_code == 429 and attempt < 3:
            time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
            continue
        if not r.ok:
            raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text[:200]}")
        return r.json()
    raise RuntimeError("Telegram: вичерпано спроби")


def send_photo(token: str, chat: str, path: str, caption: str | None) -> None:
    data = {"chat_id": chat, "disable_notification": "true" if SILENT else "false"}
    if caption:
        data.update(caption=caption, parse_mode="HTML")
    with open(path, "rb") as f:
        tg("sendPhoto", token, data=data, files={"photo": f})


def send_text(token: str, chat: str, text: str) -> None:
    tg("sendMessage", token, data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true",
                                   "disable_notification": "true" if SILENT else "false"})


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mark_done(slot: str, today: str) -> None:
    st = load_state()
    days = st.get("days", {})
    days.setdefault(today, [])
    if slot not in days[today]:
        days[today].append(slot)
    st["days"] = dict(sorted(days.items())[-4:])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def target_of(now: datetime, slot: str) -> datetime:
    hh, mm = map(int, SLOTS[slot]["at"].split(":"))
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


# ═══════════════════════ main ═══════════════════════
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=list(SLOTS), default=os.getenv("SLOT"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.slot not in SLOTS:
        log.error("Вкажіть слот: --slot %s", "|".join(SLOTS))
        return 1
    slot, cfg = args.slot, SLOTS[args.slot]
    force = args.force or os.getenv("FORCE_RUN") == "1"
    now = kyiv_now()
    today = now.date()

    if not args.dry_run and not force:
        if slot in load_state().get("days", {}).get(today.isoformat(), []):
            log.info("Слот «%s» за %s уже опубліковано — вихід.", slot, today)
            return 0
        t = target_of(now, slot)
        if not t - timedelta(minutes=EARLY_MIN) <= now <= t + timedelta(minutes=cfg["late"]):
            log.info("Зараз %s за Києвом — поза вікном слота «%s» (ціль %s), вихід.", now.strftime("%H:%M"), slot, cfg["at"])
            return 0

    caption = body = None
    if cfg["kind"] == "cat":
        header, body = (build_morning if slot == "morning" else build_evening)(today)
        image = compose_cat(slot, today, os.path.join(HERE, f"kotyk_preview_{slot}.jpg"))
        caption = header
        if len(header) + 2 + len(body) <= 1024:           # усе вміщається під фото
            caption, body = header + "\n\n" + body, None
        elif len(body) > 4096:
            log.error("Текст задовгий (%d).", len(body))
            return 1
    else:
        src = pick_ad(today, slot)
        if not src:
            log.warning("Немає файлу reklama_kanalu.jpg (або .png/.webp) у корені репозиторію — слот пропущено.")
            return 0
        image = prepare_ad(src, os.path.join(HERE, f"kotyk_preview_{slot}.jpg"))
        log.info("Реклама: %s", os.path.basename(src))

    if args.dry_run:
        print(f"[dry-run] слот {slot} · {SLOTS[slot]['at']} · {today}")
        print("— підпис під фото:\n" + (caption or "(без підпису)"))
        if body:
            print("\n— окреме повідомлення:\n" + body)
        log.info("Dry-run: картинка %s; підпис %d симв.%s", image, len(caption or ""),
                 f", текст {len(body)} симв." if body else "")
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    chat = os.getenv("CHAT_ID")
    if not token or not chat:
        log.error("Не задано TELEGRAM_BOT_TOKEN / CHAT_ID")
        return 1
    if not force:                                           # дочекатися точної хвилини
        wait = (target_of(kyiv_now(), slot) - kyiv_now()).total_seconds()
        if 0 < wait <= EARLY_MIN * 60:
            log.info("Усе готово. Чекаємо %d хв %d с до %s за Києвом…", wait // 60, wait % 60, cfg["at"])
            time.sleep(wait)
    send_photo(token, chat, image, caption)
    mark_done(slot, today.isoformat())                      # фото вже в каналі — ставимо відмітку одразу
    if body:
        for attempt in (1, 2, 3):
            try:
                send_text(token, chat, body)
                break
            except RuntimeError as ex:
                log.warning("Текстова частина (спроба %d): %s", attempt, ex)
                if attempt == 3:
                    return 1
                time.sleep(5)
    log.info("Слот «%s» опубліковано.", slot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
