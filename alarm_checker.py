"""Монитор тревог Сумской области: читает канал «Сирена Сумщини» и публикует в ваш канал.

Типы сообщений канала-источника (тип определяется по ТЕКСТУ, а не по цвету кружка):
  «<район> — повітряна тривога, червоний рівень: Ракетна загроза»  -> RED    (alert_start_banner_1.jpg)
  «<район> — повітряна тривога, жовтий рівень: Дронова загроза»    -> YELLOW (alert_start_banner_2.jpg)
  «<район> — відбій повітряної тривоги» (+ «досі триває у: ...»)   -> END    (alert_end_banner_1.jpg)

Переменные окружения:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  - обязательные (секреты GitHub)
  LOOP_MINUTES  - сколько минут работать в цикле (0 = одна проверка и выход)
  POLL_SECONDS  - пауза между проверками, по умолчанию 120 (2 минуты)
  COMMIT_STATE  - "1": сохранять состояние в git сразу после каждой отправки
"""
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

# --- НАСТРОЙКИ ----------------------------------------------------------------
CHANNEL_URL = "https://t.me/s/surenasumy"        # веб-превью канала-источника
CHANNEL_LINK = "https://t.me/surenasumy"
CHANNEL_NAME = "Сирена Сумщини"

BANNERS = {
    "RED": "alert_start_banner_1.jpg",           # 🔴 червоний рівень: ракетна загроза
    "YELLOW": "alert_start_banner_2.jpg",        # 🟡 жовтий рівень: дронова загроза
    "END": "alert_end_banner_1.jpg",             # 🟢 відбій
}
HASHTAGS = {
    "RED": "#Суми #Сумщина #Тривога #Ракети",
    "YELLOW": "#Суми #Сумщина #Тривога #Дрони",
    "END": "#Суми #Сумщина #Відбій",
}
HEADLINES = {
    "RED": "🔴 <b>{who}</b> — повітряна тривога, червоний рівень: Ракетна загроза",
    "YELLOW": "🟡 <b>{who}</b> — повітряна тривога, жовтий рівень: Дронова загроза",
    "END": "🟢 <b>{who}</b> — відбій повітряної тривоги",
}
BOARD_ICON = {"RED": "🔴", "YELLOW": "🟡", "?": "⚠️"}   # «?» - тревога идёт, а тип угрозы неизвестен

# районы Сумской области (порядок = порядок в строке-табло) и короткие подписи для неё
DISTRICTS = ["Сумський", "Охтирський", "Конотопський", "Роменський", "Шосткинський"]
SHORT = {"Сумський": "Суми", "Охтирський": "Охтирка", "Конотопський": "Конотоп",
         "Роменський": "Ромни", "Шосткинський": "Шостка"}

FORWARD_OTHER = True        # пересылать нестандартные посты (ракетна небезпека, загроза...) как есть
OTHER_KEYWORDS = ("ракетна небезпека", "загроза", "увага")
MAX_AGE_MIN = 60            # посты старше этого возраста не публикуем (только учитываем в состоянии)

STATE_FILE = "alarm_state.json"
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


def commit_state():
    """В GitHub Actions сразу коммитим состояние, чтобы не потерять его при остановке запуска."""
    if os.getenv("COMMIT_STATE") != "1":
        return
    try:
        run = lambda *a: subprocess.run(a, check=False, capture_output=True, text=True)
        run("git", "config", "user.name", "github-actions[bot]")
        run("git", "config", "user.email", "github-actions[bot]@users.noreply.github.com")
        run("git", "add", STATE_FILE)
        if run("git", "diff", "--cached", "--quiet").returncode == 0:
            return
        run("git", "commit", "-m", "Update alarm state")
        if run("git", "push").returncode != 0:
            run("git", "pull", "--rebase")
            run("git", "push")
    except Exception as e:
        print(f"Не удалось сохранить состояние в git: {e}")


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    commit_state()


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
        name = m.group(1).capitalize()
        if name in DISTRICTS and name not in out:
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
        # «досі триває у» - полный актуальный список; нет списка - значит тревог больше нет
        active = {d: active.get(d, "?") for d in ev["still"]}
    return active


# --- СООБЩЕНИЯ ----------------------------------------------------------------

def board(active):
    return " · ".join(f"{BOARD_ICON.get(active[d], '⚠️') if d in active else '🟢'} {SHORT[d]}"
                      for d in DISTRICTS)


def phrase(districts):
    return f"{districts[0]} район" if len(districts) == 1 else f"{', '.join(districts)} райони"


def build_caption(group):
    level = group["level"]
    footer = f"🔗 Джерело: <a href='{CHANNEL_LINK}'>{CHANNEL_NAME}</a> · {HASHTAGS.get(level, '#Суми #Сумщина')}"
    if level == "OTHER":
        text = html.escape(group["text"])
        if len(text) > 750:
            text = text[:750] + "…"
        return f"{text}\n{footer}"

    lines = [HEADLINES[level].format(who=phrase(group["districts"]))]
    if group["active_after"]:                  # табло показываем, пока где-то ещё есть тревога
        lines.append(f"📍 {board(group['active_after'])}")
    lines.append(footer)
    return "\n".join(lines)


def send_alert(level, caption):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Ошибка: секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return False

    banner = BANNERS.get(level)
    for attempt in range(3):
        try:
            if banner and os.path.exists(banner):
                with open(banner, "rb") as photo:
                    r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                                      data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                                      files={"photo": photo}, timeout=30)
            else:
                if banner:
                    print(f"Баннер {banner} не найден, отправляю текстом.")
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  json={"chat_id": chat_id, "text": caption, "parse_mode": "HTML",
                                        "disable_web_page_preview": True}, timeout=20)
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
        active = apply_event(active, ev)
        if ev["level"] != "OTHER" and groups and groups[-1]["level"] == ev["level"]:
            g = groups[-1]
            g["districts"] += [d for d in ev["districts"] if d not in g["districts"]]
            g["last_num"], g["ts"], g["active_after"] = ev["num"], ev["ts"], dict(active)
        else:
            groups.append({"level": ev["level"], "districts": list(ev["districts"]), "text": ev["text"],
                           "last_num": ev["num"], "ts": ev["ts"], "active_after": dict(active)})
    return groups


def is_stale(ts):
    return bool(ts) and datetime.now(timezone.utc) - ts > timedelta(minutes=MAX_AGE_MIN)


def poll(state):
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
        if is_stale(g["ts"]):
            print(f"Пост {g['last_num']} старше {MAX_AGE_MIN} мин — не публикуем, только учитываем.")
        elif send_alert(g["level"], build_caption(g)):
            print(f"Отправлено: {g['level']} {g['districts']}")
            time.sleep(1)
        else:
            print("Не удалось отправить, повторим при следующей проверке.")
            return state                                   # состояние не двигаем
        state = {"last_id": g["last_num"], "active": g["active_after"]}
        save_state(state)

    # непрофильные посты тоже считаем обработанными
    if new_posts[-1][0] > state["last_id"]:
        state["last_id"] = new_posts[-1][0]
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


if __name__ == "__main__":
    print("Проверяем свежие посты в канале Сирена Сумщини...")
    main()
    sys.exit(0)
