"""Монитор тревог для «Сумського синоптика». БЕЗ ЗВУКУ. Окремі пости — лише про Сумський район.

ДЖЕРЕЛО ТРИВОГ — API Ukraine Alarm (https://api.ukrainealarm.com, ключ у секреті UKRAINEALARM_API_KEY):
один запит /api/v3/alerts за опитування (ліміт API ~1 запит/хв, опитуємо раз на POLL_SECONDS=120 с).
Рахується лише тип AIR (повітряна тривога); ARTILLERY / URBAN_FIGHTS ігноруються.
Тривоги в Охтирському, Конотопському, Роменському, Шосткинському районах окремих постів не дають —
вони додаються рядком «Також тривога триває: ...» до поста по Сумському району.

РІВЕНЬ (червоний = ракетна загроза, жовтий = дронова): API його не розрізняє, тому підказку беремо з
каналу «Сирена Сумщини» (парсер нижче). Немає підказки — пост нейтральний («Повітряна тривога», без кольору
і без банера); коли з'явиться підказка «червоний» — окремий пост про підвищення. Якщо API недоступне
(429, збій, немає ключа), монітор працює по каналу, як раніше.

ПРОБНИЙ РЕЖИМ: DRY_RUN=1 — нічого не публікує, не пише стан і не робить коміти (лише друкує, що зробив би).

Нижче — опис парсера каналу-підказки.
Монитор тревог Сумской области: читает канал «Сирена Сумщини» и публикует в ваш канал.

Типы сообщений канала-источника (тип определяется по ТЕКСТУ, а не по цвету кружка):
  «<район> — повітряна тривога, червоний рівень: Ракетна загроза»  -> RED    (alert_start_banner_1.jpg)
  «<район> — повітряна тривога, жовтий рівень: Дронова загроза»    -> YELLOW (alert_start_banner_2.jpg)
  «<район> — відбій повітряної тривоги» (+ «досі триває у: ...»)   -> END    (alert_end_banner_1.jpg)

РЕЖИМ «ТІЛЬКИ СУМСЬКИЙ РАЙОН»: окремі пости виходять лише коли тривога починається / змінює рівень на
червоний / закінчується саме в Сумському районі, і завжди БЕЗ ЗВУКУ. Тривоги в інших районах окремих
постів не дають — вони лише додаються рядком «Також тривога триває: ...» до поста по Сумському району.

Переменные окружения:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  - обязательные (секреты GitHub)
  LOOP_MINUTES  - сколько минут работать в цикле (0 = одна проверка и выход)
  POLL_SECONDS  - пауза между проверками, по умолчанию 120 (2 минуты)
  COMMIT_STATE  - "1": сохранять состояние в git сразу после каждой отправки
  UKRAINEALARM_API_KEY - ключ API Ukraine Alarm (секрет GitHub)
  DRY_RUN       - "1": пробний режим, див. вище
  SIMULATE      - "1" (лише з DRY_RUN=1): імітація тривоги Охтирка → Суми → відбій, щоб побачити оформлення постів
"""
import base64
import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# Журнал подій для «Підсумку тижня». Необов'язковий: якщо events_db.py немає або щось
# пішло не так, скрипт працює точно так само, як раніше.
try:
    from events_db import commit_journal, safe_log
except Exception:
    def safe_log(*args, **kwargs):
        return False

    def commit_journal():
        return None

# --- НАСТРОЙКИ ----------------------------------------------------------------
CHANNEL_URL = "https://t.me/s/surenasumy"        # веб-превью канала-источника
CHANNEL_LINK = "https://t.me/surenasumy"
CHANNEL_NAME = "Сирена Сумщини"

BANNERS = {
    "RED": "alert_start_banner_1.jpg",           # 🔴 червоний рівень: ракетна загроза
    "YELLOW": "alert_start_banner_2.jpg",        # 🟡 жовтий рівень: дронова загроза
    "END": "alert_end_banner_1.jpg",             # 🟢 відбій
    # "AIR" (рівень невідомий) — без банера: нейтральний текстовий пост
}
HASHTAGS = {
    "RED": "#Суми #Сумщина #Тривога #Ракети",
    "YELLOW": "#Суми #Сумщина #Тривога #Дрони",
    "END": "#Суми #Сумщина #Відбій",
    "AIR": "#Суми #Сумщина #Тривога",
}
HEADLINES = {
    "RED": "🔴 <b>{who}</b> — повітряна тривога, червоний рівень: Ракетна загроза",
    "YELLOW": "🟡 <b>{who}</b> — повітряна тривога, жовтий рівень: Дронова загроза",
    "END": "🟢 <b>{who}</b> — відбій повітряної тривоги",
    "AIR": "⚠️ <b>{who}</b> — повітряна тривога",
}
BOARD_ICON = {"RED": "🔴", "YELLOW": "🟡", "?": "⚠️"}   # «?» - тревога идёт, а тип угрозы неизвестен

# районы Сумской области (порядок = порядок в строке-табло) и короткие подписи для неё
DISTRICTS = ["Сумський", "Охтирський", "Конотопський", "Роменський", "Шосткинський"]
SHORT = {"Сумський": "Суми", "Охтирський": "Охтирка", "Конотопський": "Конотоп",
         "Роменський": "Ромни", "Шосткинський": "Шостка"}
# канал пише «Роменський район», а API віддає «Роменський» — зводимо варіанти до одного ключа
DISTRICT_ALIASES = {"Роменський": "Роменський", "Роменский": "Роменський",
                    "Конотопський": "Конотопський", "Шосткинський": "Шосткинський",
                    "Охтирський": "Охтирський", "Сумський": "Сумський"}

HOME_DISTRICT = "Сумський"  # лише для цього району виходять окремі пости
SILENT_ALERTS = True        # True — пости тривог виходять без звуку (disable_notification)
FORWARD_OTHER = False       # пересылать нестандартные посты (ракетна небезпека, загроза...) как есть:
                            # False — не пересилати (менше шуму); True — як раніше
OTHER_KEYWORDS = ("ракетна небезпека", "загроза", "увага")
MAX_AGE_MIN = 60            # посты старше этого возраста не публикуем (только учитываем в состоянии)

API_BASE = "https://api.ukrainealarm.com/api/v3"
STATE_REGION_ID = "20"                                   # Сумська область
DISTRICT_IDS = {"114": "Сумський", "115": "Шосткинський", "116": "Роменський",
                "117": "Конотопський", "118": "Охтирський"}
REGIONS_FILE = "sumy_regions.json"                       # кеш: громада -> район (створюється сам із /regions)
HINT_TTL_MIN = 10                                        # підказка рівня з каналу живе, поки район неактивний не довше цього
DRY_RUN = os.getenv("DRY_RUN") == "1"
API_SOURCE_LINK = "https://www.ukrainealarm.com/"

if DRY_RUN:                                              # пробний режим: журнал подій теж не чіпаємо
    def safe_log(*args, **kwargs):
        return False

    def commit_journal():
        return None

STATE_FILE = "alarm_state.json"
MAX_STATE_COMMITS = int(os.getenv("MAX_STATE_COMMITS", "3"))   # обмеження на кількість комітів стану за один запуск
LEGACY_FILE = "last_alarm_post_id.txt"   # файл старой версии - используется один раз для миграции
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "120"))
LOOP_MINUTES = float(os.getenv("LOOP_MINUTES", "0"))
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


# --- СОСТОЯНИЕ ----------------------------------------------------------------

def load_state():
    state = {"last_id": None, "active": {}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state.update(json.load(f))
        except Exception as e:
            print(f"Не удалось прочитать {STATE_FILE}: {e}")
    if isinstance(state["active"], list):          # состояние предыдущей версии
        state["active"] = {d: "?" for d in state["active"]}
    return state


_commits_left = MAX_STATE_COMMITS
_dirty = False


def _push_files(paths, message):
    """Закоммитить и запушить файлы состояния. True — удалось.

    Пуш в общий main почти всегда упирается в чужие коммиты (в репозитории ~30 workflow'ов),
    поэтому: коммит, затем pull --rebase и до 3 попыток пуша. Если не вышло — файл всё равно
    лежит на диске, и его заберёт шаг «Save state» в конце запуска.
    """
    run = lambda *a: subprocess.run(a, check=False, capture_output=True, text=True)
    try:
        run("git", "config", "user.name", "github-actions[bot]")
        run("git", "config", "user.email", "github-actions[bot]@users.noreply.github.com")
        for f in paths:
            if os.path.exists(f):
                run("git", "add", f)
        if run("git", "diff", "--cached", "--quiet").returncode == 0:
            return True
        run("git", "commit", "-m", message)
        for _ in range(3):
            if run("git", "push").returncode == 0:
                return True
            run("git", "pull", "--rebase", "--autostash")
        print("⚠ git push не вдався — стан збереже фінальний крок workflow.")
    except Exception as e:
        print(f"Не удалось сохранить состояние в git: {e}")
    return False


def commit_state():
    """В GitHub Actions сразу коммитим состояние, чтобы не потерять его при остановке запуска."""
    global _commits_left, _dirty
    if os.getenv("COMMIT_STATE") != "1" or DRY_RUN:
        return
    if _commits_left <= 0:
        return                                    # ліміт вичерпано — зробить фінальний крок
    _commits_left -= 1
    if _push_files((STATE_FILE, REGIONS_FILE), "Update alarm state"):
        _dirty = False


def save_state(state):
    global _dirty
    if DRY_RUN:
        return
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    _dirty = True
    commit_state()


def flush_state():
    """Фінальне збереження: добирає те, що не встигло піти в git під час циклу."""
    global _dirty
    if DRY_RUN or os.getenv("COMMIT_STATE") != "1":
        return
    if _dirty and _push_files((STATE_FILE, REGIONS_FILE), "Update alarm state (final)"):
        _dirty = False


def read_legacy_id():
    if os.path.exists(LEGACY_FILE):
        m = re.search(r"(\d+)\s*$", open(LEGACY_FILE, encoding="utf-8").read())
        if m:
            return int(m.group(1))
    return None


# --- РАЗБОР КАНАЛА ------------------------------------------------------------

def fetch_posts():
    """[(номер поста, текст, время)] по возрастанию номера."""
    r = requests.get(CHANNEL_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for el in soup.find_all("div", class_="tgme_widget_message"):
        m = re.search(r"/(\d+)$", el.get("data-post", ""))
        text_el = el.find("div", class_="tgme_widget_message_text")
        if not m or not text_el:
            continue
        ts = None
        t = el.select_one("a.tgme_widget_message_date time")
        if t and t.get("datetime"):
            try:
                ts = datetime.fromisoformat(t["datetime"])
            except ValueError:
                pass
        posts.append((int(m.group(1)), text_el.get_text(" ", strip=True), ts))
    posts.sort(key=lambda p: p[0])
    return posts


_DIST_RE = re.compile(r"([А-ЯІЇЄҐа-яіїєґ]+ий)\s+район")


def find_districts(text):
    out = []
    for m in _DIST_RE.finditer(text):
        name = DISTRICT_ALIASES.get(m.group(1).capitalize())
        if name and name not in out:
            out.append(name)
    return out


def alarm_level(head):
    """Красный = ракетная угроза, жёлтый = угроза дронов. Если оба признака - красный."""
    low = head.lower()
    if "червоний рівень" in low or "ракетна загроза" in low:
        return "RED"
    if "жовтий рівень" in low or "дронова загроза" in low:
        return "YELLOW"
    if "🔴" in head:
        return "RED"
    if "🟡" in head:
        return "YELLOW"
    return "RED"


def parse_post(num, text, ts):
    """Определяет тип события по тексту поста. None - пост нас не интересует."""
    flat = re.sub(r"\s+", " ", text).strip()
    low = flat.lower()
    idx = low.find("досі")
    head, tail = (flat[:idx], flat[idx:]) if idx >= 0 else (flat, "")
    districts, still = find_districts(head), find_districts(tail)
    head_low = head.lower()

    level = None
    if districts and "відбій" in head_low:
        level = "END"
    elif districts and "тривога" in head_low:
        level = alarm_level(head)
    elif FORWARD_OTHER and any(k in low for k in OTHER_KEYWORDS):
        level = "OTHER"
    if level is None:
        return None
    return {"num": num, "level": level, "districts": districts, "still": still, "text": flat, "ts": ts}


def apply_event(active, ev):
    """Обновляет словарь {район: RED|YELLOW|?} - где сейчас тревога и какого типа."""
    active = dict(active)
    if ev["level"] in ("RED", "YELLOW"):
        for d in ev["districts"]:
            if active.get(d) != "RED":                 # красный не понижаем до жёлтого
                active[d] = ev["level"]
    elif ev["level"] == "END":
        # «досі триває у» — это только ДОПОЛНЕНИЕ к состоянию, а не полный список районов:
        # снимаем тревогу лишь там, где канал сказал «відбій», остальные районы не трогаем.
        for d in ev["districts"]:
            active.pop(d, None)
    return active


# --- СООБЩЕНИЯ ----------------------------------------------------------------

def board(active):
    return " · ".join(f"{BOARD_ICON.get(active[d], '⚠️')} {SHORT[d]}" for d in DISTRICTS if d in active)


def others_line(others):
    """{район: рівень} -> «🔴 Охтирка · 🟡 Конотоп» (у порядку DISTRICTS)."""
    return " · ".join(f"{BOARD_ICON.get(others[d], '⚠️')} {SHORT[d]}" for d in DISTRICTS if d in others)


def phrase(districts):
    return f"{districts[0]} район" if len(districts) == 1 else f"{', '.join(districts)} райони"


def build_caption(group):
    level = group["level"]
    if group.get("source") == "api":
        footer = f"🔗 Джерело: <a href='{API_SOURCE_LINK}'>Ukraine Alarm</a> · {HASHTAGS.get(level, '#Суми #Сумщина')}"
    else:
        footer = f"🔗 Джерело: <a href='{CHANNEL_LINK}'>{CHANNEL_NAME}</a> · {HASHTAGS.get(level, '#Суми #Сумщина')}"
    if level == "OTHER":
        text = html.escape(group["text"])
        if len(text) > 750:
            text = text[:750] + "…"
        return f"{text}\n{footer}"

    lines = [HEADLINES[level].format(who=phrase([HOME_DISTRICT]))]
    others = {d: lvl for d, lvl in group["active_after"].items() if d != HOME_DISTRICT}
    if others:                                 # інші райони — одним рядком, без окремих постів
        label = "Також тривога триває" if level != "END" else "Тривога ще триває"
        lines.append(f"📍 {label}: {others_line(others)}")
    lines.append(footer)
    return "\n".join(lines)


def send_alert(level, caption):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not DRY_RUN and (not token or not chat_id):
        print("Ошибка: секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return False

    banner = BANNERS.get(level)
    if DRY_RUN:
        print(f"[DRY_RUN] Було б надіслано без звуку ({level}, банер: {banner or '—'}):\n" + caption + "\n")
        return True
    for attempt in range(3):
        try:
            if banner and os.path.exists(banner):
                with open(banner, "rb") as photo:
                    r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                      data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
                                             "disable_notification": "true" if SILENT_ALERTS else "false"},
                                      files={"photo": photo}, timeout=30)
            else:
                if banner:
                    print(f"Баннер {banner} не найден, отправляю текстом.")
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  json={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                        "disable_web_page_preview": True,
                                        "disable_notification": SILENT_ALERTS}, timeout=20)
            if r.status_code == 200:
                return True
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)) + 1)
                continue
            print(f"Ошибка отправки: {r.status_code} {r.text}")
            return False
        except Exception as e:
            print(f"Ошибка отправки (попытка {attempt + 1}): {e}")
            time.sleep(3)
    return False


# --- ОДНА ПРОВЕРКА ------------------------------------------------------------

def make_groups(events, active):
    """Склеивает подряд идущие события одного типа в одно сообщение (по районам)."""
    groups = []
    for ev in events:
        before = dict(active)
        active = apply_event(active, ev)
        if ev["level"] != "OTHER" and groups and groups[-1]["level"] == ev["level"]:
            g = groups[-1]
            g["districts"] += [d for d in ev["districts"] if d not in g["districts"]]
            g["last_num"], g["ts"], g["active_after"] = ev["num"], ev["ts"], dict(active)
            g["events"].append(ev)
        else:
            groups.append({"level": ev["level"], "districts": list(ev["districts"]), "text": ev["text"],
                           "last_num": ev["num"], "ts": ev["ts"], "active_after": dict(active),
                           "active_before": before, "events": [ev]})
    return groups


def home_change(g):
    """Що сталося з HOME_DISTRICT у цій групі: RED/YELLOW (початок або підвищення до червоного), END (відбій) або None."""
    if g["level"] == "OTHER":
        return "OTHER" if FORWARD_OTHER else None
    b, a = g["active_before"].get(HOME_DISTRICT), g["active_after"].get(HOME_DISTRICT)
    if a in ("RED", "YELLOW") and not b:
        return a                                   # тривога почалася
    if a == "RED" and b == "YELLOW":
        return "RED"                               # дрони -> ракетна загроза: важливо повідомити
    if b and not a:
        return "END"                               # відбій у нашому районі
    return None


def is_stale(ts):
    return bool(ts) and datetime.now(timezone.utc) - ts > timedelta(minutes=MAX_AGE_MIN)


def _sumy_time(g, kind):
    """Точний час повідомлення про Сумський район (а не останнього в склеєній групі)."""
    for ev in g.get("events", []):
        if "Сумський" in ev["districts"]:
            if (kind == "start" and ev["level"] in ("RED", "YELLOW")) or (kind == "end" and ev["level"] == "END"):
                return ev["ts"] or g["ts"]
    return g["ts"]


def poll_channel(state):
    """Запасний режим: тривоги з каналу «Сирена Сумщини» (використовується, коли API недоступне)."""
    posts = fetch_posts()
    if not posts:
        print("Не удалось найти сообщения на странице канала.")
        return state

    # первый запуск: восстанавливаем состояние по видимым постам, ничего не публикуя
    if state.get("last_id") is None:
        last = read_legacy_id() or posts[-1][0]
        active = {}
        for num, text, ts in posts:
            ev = parse_post(num, text, ts)
            if ev and num <= last:
                active = apply_event(active, ev)
        state = {"last_id": last, "active": active}
        save_state(state)
        print(f"Инициализация: последний обработанный пост {last}, тревога сейчас: {active or 'нет'}")

    new_posts = [p for p in posts if p[0] > state["last_id"]]
    if not new_posts:
        return state

    events = [e for e in (parse_post(*p) for p in new_posts) if e]
    groups = make_groups(events, state["active"])

    for g in groups:
        change = home_change(g)
        # початок тривоги в Сумському районі (був «зелений», став червоний/жовтий) - для журналу
        sumy_start = (g["level"] in ("RED", "YELLOW") and "Сумський" in g["districts"]
                      and "Сумський" not in state["active"])
        # відбій для Сумського району (була тривога, а після цього повідомлення вже немає)
        sumy_end = "Сумський" in state["active"] and "Сумський" not in g["active_after"]
        if change is None:
            print(f"Пост {g['last_num']}: {g['level']} {g['districts']} — для {HOME_DISTRICT} району змін немає, окремого поста не буде.")
        elif is_stale(g["ts"]):
            print(f"Пост {g['last_num']} старше {MAX_AGE_MIN} мин — не публикуем, только учитываем.")
        elif send_alert(change, build_caption(dict(g, level=change))):
            print(f"Отправлено: {change} ({HOME_DISTRICT} район)")
            time.sleep(1)
        else:
            print("Не удалось отправить, повторим при следующей проверке.")
            return state                                   # состояние не двигаем
        if sumy_start and safe_log("alert", f"{g['level']}: {phrase(g['districts'])}",
                                   key=f"alert-{g['last_num']}", when=_sumy_time(g, "start")):
            commit_journal()
        if sumy_end and safe_log("alert_end", "Відбій: Сумський район",
                                 key=f"alert-end-{g['last_num']}", when=_sumy_time(g, "end")):
            commit_journal()
        state = {"last_id": g["last_num"], "active": g["active_after"]}
        save_state(state)

    # непрофильные посты тоже считаем обработанными
    if new_posts[-1][0] > state["last_id"]:
        state["last_id"] = new_posts[-1][0]
        save_state(state)
    return state


# --- API UKRAINE ALARM --------------------------------------------------------

_community_map = None


def load_community_map():
    """{id громади: назва району} для Сумської області. Береться з кешу sumy_regions.json; немає — один раз із /regions."""
    global _community_map
    if _community_map is not None:
        return _community_map
    if os.path.exists(REGIONS_FILE):
        try:
            with open(REGIONS_FILE, encoding="utf-8") as f:
                _community_map = json.load(f)
                return _community_map
        except Exception as e:
            print(f"Не вдалося прочитати {REGIONS_FILE}: {e}")
    key = os.getenv("UKRAINEALARM_API_KEY", "").strip()
    if not key:
        return {}
    try:
        r = requests.get(f"{API_BASE}/regions", headers={"Authorization": key, "Accept": "application/json"}, timeout=40)
        if r.status_code != 200:
            print(f"API /regions: HTTP {r.status_code} — карту громад спробуємо пізніше.")
            return {}
        mapping = {}

        def descend(node, district):
            if isinstance(node, list):
                for x in node:
                    descend(x, district)
            elif isinstance(node, dict):
                rid = str(node.get("regionId", ""))
                if rid in DISTRICT_IDS:
                    district = DISTRICT_IDS[rid]
                    # сам район у карту НЕ пишемо: його id розбирається окремою гілкою в fetch_api,
                    # інакше громада з тим самим id «перебивала» б район
                    descend(node.get("regionChildIds", []), district)
                elif district and rid:
                    mapping[rid] = district
                    descend(node.get("regionChildIds", []), district)
                else:
                    descend(node.get("regionChildIds", []), district)

        def find_state(node):
            if isinstance(node, list):
                for x in node:
                    res = find_state(x)
                    if res:
                        return res
            elif isinstance(node, dict):
                if str(node.get("regionId")) == STATE_REGION_ID:
                    return node
                for v in node.values():
                    if isinstance(v, (list, dict)):
                        res = find_state(v)
                        if res:
                            return res
            return None

        state_node = find_state(r.json())
        if not state_node:
            print("API /regions: Сумську область не знайдено.")
            return {}
        descend(state_node.get("regionChildIds", []), None)
        _community_map = mapping
        if not DRY_RUN:
            with open(REGIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(mapping, f, ensure_ascii=False, indent=1)
        print(f"Карта громад Сумщини збережена: {len(mapping)} громад.")
        return mapping
    except Exception as e:
        print(f"API /regions: {e}")
        return {}


_sim_cycle = 0


def fetch_api():
    """Множина районів Сумщини, де зараз повітряна тривога (AIR). None — API недоступне (тоді працює канал)."""
    global _sim_cycle
    if DRY_RUN and os.getenv("SIMULATE") == "1":          # лише в пробному режимі: вигадана тривога, щоб побачити оформлення постів
        _sim_cycle += 1
        script = [{"Охтирський"}, {"Охтирський", "Сумський"}, {"Сумський"}]
        return script[_sim_cycle - 1] if _sim_cycle <= len(script) else set()
    key = os.getenv("UKRAINEALARM_API_KEY", "").strip()
    if not key:
        return None
    # Ліміт API ~1 запит/хв: карту громад завантажуємо ОКРЕМИМ циклом (цей цикл — по каналу), а не разом з /alerts.
    had_map = _community_map is not None or os.path.exists(REGIONS_FILE)
    communities = load_community_map()
    if not had_map:
        return None
    try:
        r = requests.get(f"{API_BASE}/alerts", headers={"Authorization": key, "Accept": "application/json"}, timeout=20)
    except requests.RequestException as e:
        print(f"API недоступне: {e}")
        return None
    if r.status_code == 429:
        print(f"API: ліміт запитів (429), retry-after={r.headers.get('retry-after', '?')} — цей цикл по каналу.")
        return None
    if r.status_code != 200:
        print(f"API: HTTP {r.status_code} — цей цикл по каналу.")
        return None
    try:
        data = r.json()
    except ValueError:
        print("API: відповідь не JSON — цей цикл по каналу.")
        return None
    if not isinstance(data, list):
        print("API: неочікувана структура відповіді — цей цикл по каналу.")
        return None
    active = set()
    for item in data:
        rid = str(item.get("regionId", ""))
        if not any(a.get("type") == "AIR" for a in item.get("activeAlerts", []) or []):
            continue
        if rid == STATE_REGION_ID:                                   # тривога на всю область = у всіх районах
            active.update(DISTRICT_IDS.values())
        elif rid in DISTRICT_IDS:
            active.add(DISTRICT_IDS[rid])
        elif rid in communities:                                      # тривога на рівні громади -> її район
            active.add(communities[rid])
    return active


def update_hints(state):
    """Підказки рівня (RED/YELLOW) з каналу. Помилки каналу не критичні. Просуває last_id, щоб запасний режим не повторював старі пости."""
    hints = state.setdefault("hints", {})
    try:
        posts = fetch_posts()
    except Exception as e:
        print(f"Канал-підказка недоступний: {e}")
        return
    if not posts:
        return
    seeding = state.get("last_id") is None
    last = state.get("last_id") or 0
    now = datetime.now(timezone.utc)
    for num, text, ts in posts:
        if num <= last:
            continue
        ev = parse_post(num, text, ts)
        fresh = ts is None or now - ts < timedelta(minutes=HINT_TTL_MIN + 5)
        if not ev or (seeding and not fresh):
            continue
        stamp = (ts or now).isoformat()
        if ev["level"] in ("RED", "YELLOW"):
            for d in ev["districts"]:
                if hints.get(d, {}).get("level") != "RED":            # червоний не понижуємо
                    hints[d] = {"level": ev["level"], "ts": stamp}
                else:
                    hints[d]["ts"] = stamp
        elif ev["level"] == "END":
            for d in ev["districts"]:
                hints.pop(d, None)
    state["last_id"] = posts[-1][0]


def home_change_api(before, after):
    """Що сталося з HOME_DISTRICT: RED/YELLOW/AIR (початок), RED (підвищення), END (відбій) або None.

    `after` — рівень тривоги в Сумському районі (None, якщо тривоги немає).
    """
    if after and not before:
        return after if after in ("RED", "YELLOW") else "AIR"
    if after == "RED" and before in ("YELLOW", "?"):
        return "RED"
    if before and not after:
        return "END"
    return None


def poll_api(state, api_active):
    hints = state.setdefault("hints", {})
    now = datetime.now(timezone.utc)
    for d in list(hints):                                             # старі підказки неактивних районів — прибираємо
        try:
            age = now - datetime.fromisoformat(hints[d]["ts"])
        except Exception:
            age = timedelta(days=1)
        if d not in api_active and age > timedelta(minutes=HINT_TTL_MIN):
            del hints[d]
    old = state.get("active", {})
    new = {}
    for d in DISTRICTS:
        if d in api_active:
            lvl = hints.get(d, {}).get("level") or (old.get(d) if old.get(d) in ("RED", "YELLOW") else "?")
            new[d] = lvl
    change = home_change_api(old.get(HOME_DISTRICT), new.get(HOME_DISTRICT))
    # відбій завжди позначаємо «🟢», навіть якщо в інших районах тривога ще триває —
    # це відбій саме в Сумському районі, і пост має виглядати саме так
    level = "END" if change == "END" else change
    if change:
        group = {"level": level, "districts": [HOME_DISTRICT], "active_after": new, "source": "api"}
        if not send_alert(level, build_caption(group)):
            print("Не вдалося відправити, повторимо при наступній перевірці.")
            return state                                              # стан не рухаємо
        print(f"Надіслано: {level} ({HOME_DISTRICT} район, джерело API)")
        time.sleep(1)
        if change in ("RED", "YELLOW", "AIR") and not old.get(HOME_DISTRICT) and safe_log(
                "alert", f"{change}: {HOME_DISTRICT} район", key=f"alert-api-{int(time.time())}", when=now):
            commit_journal()
        if change == "END" and safe_log("alert_end", "Відбій: Сумський район",
                                        key=f"alert-end-api-{int(time.time())}", when=now):
            commit_journal()
    if new != old:
        print(f"Стан тривог: було {old or 'нема'} → стало {new or 'нема'}")
    state["active"] = new
    save_state(state)
    return state


# без каналу-підказки рівень невідомий: API каже лише «тривога / відбій»
NO_HINTS = os.getenv("NO_HINTS") == "1"


def poll(state):
    api_active = fetch_api()
    if api_active is None:
        return poll_channel(state)
    try:                                        # підказки рівня (канал «Сирена Сумщини»)
        update_hints(state)
    except Exception as e:
        print(f"Підказки рівня недоступні: {e}")
    if NO_HINTS:
        return poll_api_plain(state, api_active)
    return poll_api(state, api_active)


def poll_api_plain(state, api_active):
    """Режим без підказок: рівень не розрізняємо, лише «тривога» / «відбій» по Сумському району."""
    old = state.get("active", {})
    # стан за замовчуванням порожній, тому на першому запуску «Суми вже в тривозі» губилось:
    # якщо тривога в Сумах уже є, а ми цього не знали — беремо рівень із підказок (якщо є)
    if HOME_DISTRICT in api_active and HOME_DISTRICT not in old:
        lvl = (state.get("hints") or {}).get(HOME_DISTRICT, {}).get("level") or "?"
        old = dict(old, **{HOME_DISTRICT: lvl})
    new = {d: "?" for d in DISTRICTS if d in api_active}
    change = home_change_api(old.get(HOME_DISTRICT), new.get(HOME_DISTRICT))
    level = "END" if change == "END" else "AIR"
    if change:
        group = {"level": level, "districts": [HOME_DISTRICT], "active_after": new, "source": "api"}
        if not send_alert(level, build_caption(group)):
            print("Не вдалося відправити, повторимо при наступній перевірці.")
            return state
        print(f"Надіслано: {level} ({HOME_DISTRICT} район, джерело API, без підказок)")
        time.sleep(1)
    if new != old:
        print(f"Стан тривог: було {old or 'нема'} → стало {new or 'нема'}")
    state["active"] = new
    save_state(state)
    return state


def main():
    state = load_state()
    deadline = time.time() + LOOP_MINUTES * 60
    while True:
        try:
            state = poll(state)
        except Exception as e:
            print(f"Ошибка проверки: {e}")
        if LOOP_MINUTES <= 0 or time.time() + POLL_SECONDS > deadline:
            break
        time.sleep(POLL_SECONDS)
    flush_state()


if __name__ == "__main__":
    print("Монітор тривог: API Ukraine Alarm" + (" (ПРОБНИЙ РЕЖИМ, нічого не публікується)" if DRY_RUN else "")
          + ", запасний режим — канал Сирена Сумщини")
    main()
    sys.exit(0)
