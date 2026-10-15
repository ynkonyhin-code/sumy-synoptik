"""Сумський синоптик: репост оперативних повідомлень КП «Міськводоканал» (@vodokanalSMR).

Що робить:
  1. Читає публічну стрічку https://t.me/s/vodokanalSMR.
  2. Відбирає нові пости про воду (відключення, аварійні/ремонтні роботи, тиск, відновлення).
  3. Публікує у ваш канал: банер water_banner.jpg + акуратно оформлений текст
     (заголовок за типом події, час публікації, текст з емодзі «в рядок», джерело, теги).
  4. Запам'ятовує останній оброблений пост у last_water_post_id.txt.

Запуск:
  python water_checker.py --dry-run     # показати готовий пост, нічого не публікуючи
  python water_checker.py               # бойовий режим (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)

Необов'язкові змінні: MAX_AGE_HOURS=12 (не публікувати пости старші за N годин).
"""
import html
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# Журнал подій для «Підсумку тижня». Необов'язковий: якщо events_db.py немає або щось
# пішло не так, скрипт працює точно так само, як раніше.
try:
    from events_db import commit_journal, safe_log
except Exception:
    def safe_log(*args, **kwargs):
        return False

    def commit_journal():
        return None

# ОФІЦІЙНИЙ канал КП «Міськводоканал» Сумської міської ради
CHANNEL = "vodokanalSMR"
TELEGRAM_CHANNEL_URL = f"https://t.me/s/{CHANNEL}"

# Банер та файл для збереження ID останнього поста
IMAGE_FILENAME = "water_banner.jpg"
CACHE_FILE = Path("last_water_post_id.txt")

TZ = ZoneInfo("Europe/Kyiv")
MAX_AGE_HOURS = float(os.getenv("MAX_AGE_HOURS", "12"))
MAX_POSTS_PER_RUN = 5          # захист від «потопу» після тривалої перерви
CAPTION_LIMIT = 1024           # ліміт підпису до фото в Telegram
MESSAGE_BODY_LIMIT = 3700      # запас під джерело й теги (ліміт повідомлення 4096)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

# Ключові слова офіційних аварійних повідомлень (регістр і закінчення не важливі)
KEYWORDS = re.compile(
    "|".join([
        r"припинен\w*\s+водопостачання",
        r"обмежен\w*\s+водопостачання",
        r"відключенн\w*\s+води",
        r"аварійн\w*\s+робот\w*",
        r"ремонтн\w*\s+робот\w*",
        r"\bпорив\w*",
        r"витіканн\w*",
        r"знеструмленн\w*",
        r"тиск\w*\s+води",
        r"водопостачання",
    ]),
    re.IGNORECASE,
)

BASE_TAGS = ["#Суми", "#Водопостачання", "#Міськводоканал"]
BRAND_TAG = "#СумськийСиноптик"


# ---------------------------------------------------------------- тип події
def detect_category(text: str):
    """Повертає (емодзі, заголовок, тег) залежно від змісту поста."""
    t = text.lower()
    if re.search(r"(відновлен|поновлен)\w*\s+(водопостачання|подач)"
                 r"|(водопостачання|подач\w*\s+води)\s+(вже\s+|повністю\s+|поступово\s+)?(відновлен|поновлен)", t):
        return "✅", "Водопостачання відновлено", "#ВодопостачанняВідновлено"
    if re.search(r"припинен|без\s+води|відключенн\w*\s+води|відсутн\w+\s+(вод|водопостач)", t):
        return "🚱", "Припинено водопостачання", "#ВідключенняВоди"
    if re.search(r"обмежен\w*\s+водопостач", t):
        return "⚠️", "Обмежено водопостачання", "#ОбмеженняВоди"
    if "тиск" in t:
        return "⚠️", "Змінено тиск води", "#ТискВоди"
    if re.search(r"аварійн|ремонтн|\bпорив|витіканн", t):
        return "🚧", "Аварійні та ремонтні роботи", "#АварійніРоботи"
    return "💧", "Оперативна інформація", ""


# ---------------------------------------------------------------- розбір сторінки
def node_to_html(node) -> str:
    """Вміст поста -> HTML для Telegram. Емодзі лишаються В РЯДКУ з текстом."""
    if isinstance(node, NavigableString):
        return html.escape(str(node))
    if not isinstance(node, Tag):
        return ""
    if node.name == "br":
        return "\n"
    if node.name == "i" and "emoji" in (node.get("class") or []):
        return html.escape(node.get_text())
    inner = "".join(node_to_html(c) for c in node.children)
    name = node.name
    if name == "a":
        href = (node.get("href") or "").strip()
        if href.startswith(("http://", "https://", "tg://")):
            return f'<a href="{html.escape(href, quote=True)}">{inner}</a>'
        return inner
    if name in ("b", "strong"):
        return f"<b>{inner}</b>"
    if name in ("i", "em"):
        return f"<i>{inner}</i>"
    if name in ("u", "ins"):
        return f"<u>{inner}</u>"
    if name in ("s", "strike", "del"):
        return f"<s>{inner}</s>"
    if name == "code":
        return f"<code>{inner}</code>"
    if name == "pre":
        return f"<pre>{inner}</pre>"
    return inner


def strip_html(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", h))


def plain_len(h: str) -> int:
    return len(strip_html(h))


def fetch_page() -> str:
    r = requests.get(TELEGRAM_CHANNEL_URL, timeout=30,
                     headers={"User-Agent": UA, "Accept-Language": "uk,ru;q=0.8,en;q=0.5"})
    r.raise_for_status()
    return r.text


def parse_posts(page: str) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    posts = []
    for msg in soup.select(".tgme_widget_message"):
        m = re.search(r"/(\d+)$", msg.get("data-post", ""))
        text_el = next((t for t in msg.select(".tgme_widget_message_text")
                        if not t.find_parent(class_="tgme_widget_message_reply")), None)
        if not m or not text_el:
            continue
        dt = None
        t_el = msg.select_one(".tgme_widget_message_date time")
        if t_el and t_el.get("datetime"):
            try:
                dt = datetime.fromisoformat(t_el["datetime"])
            except ValueError:
                pass
        posts.append({
            "id": int(m.group(1)),
            "dt": dt,
            "html": "".join(node_to_html(c) for c in text_el.children),
            "plain": text_el.get_text(" ").strip(),
        })
    return sorted(posts, key=lambda p: p["id"])


# ---------------------------------------------------------------- оформлення поста
def clean_body(h: str) -> str:
    """Прибирає зайві порожні рядки, пробіли та власні хештеги джерела."""
    h = h.replace("\xa0", " ").replace("\r", "")
    h = re.sub(r"[ \t]+\n", "\n", h)
    lines = []
    for line in h.split("\n"):
        plain = strip_html(line).strip()
        if plain and re.fullmatch(r"(#\w+[\s,]*)+", plain):   # рядок лише з хештегів
            continue
        lines.append(line.strip())
    h = "\n".join(lines)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def fit_body(body: str, limit: int) -> str:
    """Скорочує по абзацах (теги не рвуться); якщо навіть перший абзац завеликий — різ по тексту."""
    if plain_len(body) <= limit:
        return body
    acc: list[str] = []
    for para in body.split("\n\n"):
        if plain_len("\n\n".join(acc + [para])) > limit:
            break
        acc.append(para)
    if not acc:
        return html.escape(strip_html(body)[:limit].rsplit(" ", 1)[0]) + "…"
    return "\n\n".join(acc) + "\n\n…"


def build_post(p: dict) -> tuple[str, str | None]:
    """Повертає (підпис до банера, додаткове повідомлення або None)."""
    icon, label, cat_tag = detect_category(p["plain"])
    when = p["dt"].astimezone(TZ).strftime("%d.%m.%Y, %H:%M") if p["dt"] else ""
    sub = f"КП «Міськводоканал»" + (f" · {when}" if when else "")
    header = f"{icon} <b>{label}</b>\n<i>{sub}</i>"

    body = clean_body(p["html"])
    if body.startswith(icon):                      # не дублюємо емодзі заголовка на початку тексту
        body = body[len(icon):].lstrip()
    source = f'🔗 <a href="https://t.me/{CHANNEL}/{p["id"]}">Джерело: КП «Міськводоканал» Суми</a>'
    tags = " ".join(BASE_TAGS + ([cat_tag] if cat_tag else []) + [BRAND_TAG])

    full = f"{header}\n\n{body}\n\n{source}\n\n{tags}"
    if plain_len(full) <= CAPTION_LIMIT:
        return full, None
    # довгий пост: банер із заголовком + окреме повідомлення з повним текстом
    details = f"{fit_body(body, MESSAGE_BODY_LIMIT)}\n\n{source}\n\n{tags}"
    return header, details


# ---------------------------------------------------------------- Telegram Bot API
def need_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        sys.exit(f"❌ Змінна {name} порожня. Перевірте GitHub → Settings → Secrets and variables → "
                 f"Actions → Secrets та файл workflow (env).")
    return v


class TgError(RuntimeError):
    pass


def tg_api(method: str, data: dict, files: dict | None = None):
    token = need_env("TELEGRAM_BOT_TOKEN")
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                      data=data, files=files, timeout=60)
    if not r.ok:
        raise TgError(f"Telegram {method}: HTTP {r.status_code}: {r.text[:300]}")


def deliver(kind: str, text: str, chat: str):
    """kind: 'photo' або 'message'. Якщо Telegram не прийняв HTML — повторюємо звичайним текстом."""
    for html_mode in (True, False):
        payload = text if html_mode else strip_html(text)
        data = {"chat_id": chat}
        if html_mode:
            data["parse_mode"] = "HTML"
        try:
            if kind == "photo":
                data["caption"] = payload
                with open(IMAGE_FILENAME, "rb") as f:
                    tg_api("sendPhoto", data, files={"photo": f})
            else:
                data.update(text=payload, disable_web_page_preview="true")
                tg_api("sendMessage", data)
            return
        except TgError as e:
            if html_mode and "parse entities" in str(e).lower():
                print("  ⚠ HTML не прийнято, повторюю простим текстом")
                continue
            raise


def publish(p: dict, chat: str):
    caption, details = build_post(p)
    deliver("photo" if os.path.exists(IMAGE_FILENAME) else "message", caption, chat)
    if details:
        deliver("message", details, chat)


# ---------------------------------------------------------------- стан
def read_last_id() -> int | None:
    if CACHE_FILE.exists():
        m = re.search(r"(\d+)\s*$", CACHE_FILE.read_text(encoding="utf-8").strip())
        if m:
            return int(m.group(1))
    return None


def save_last_id(post_id: int):
    CACHE_FILE.write_text(f"{CHANNEL}/{post_id}", encoding="utf-8")   # той самий формат, що й раніше


# ---------------------------------------------------------------- головна логіка
def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args or os.getenv("DRY_RUN") == "1"
    local = args[args.index("--html") + 1] if "--html" in args else None   # для тестів

    print("Перевіряємо свіжі повідомлення КП «Міськводоканал» (@%s)..." % CHANNEL)
    chat = None
    if not dry:
        need_env("TELEGRAM_BOT_TOKEN")
        chat = need_env("TELEGRAM_CHAT_ID")

    posts = parse_posts(Path(local).read_text(encoding="utf-8") if local else fetch_page())
    if not posts:
        print("Не вдалося знайти повідомлення на сторінці Водоканалу.")
        return

    last = read_last_id()
    newest = posts[-1]["id"]
    matching = [p for p in posts if KEYWORDS.search(p["plain"])]
    todo = matching[-1:] if last is None else [p for p in matching if p["id"] > last]

    if not local:
        now = datetime.now(timezone.utc)
        todo = [p for p in todo if not p["dt"] or now - p["dt"] <= timedelta(hours=MAX_AGE_HOURS)]
    todo = todo[-MAX_POSTS_PER_RUN:]

    if not todo:
        print("Нових цільових постів про воду не знайдено.")
        if not dry and last != newest:
            save_last_id(newest)
        return

    for p in todo:
        print(f"→ пост {CHANNEL}/{p['id']}")
        if dry:
            caption, details = build_post(p)
            print("-" * 60)
            print(("[ФОТО + підпис]\n" if os.path.exists(IMAGE_FILENAME) else "[ПОВІДОМЛЕННЯ]\n") + caption)
            if details:
                print("\n[ДОДАТКОВЕ ПОВІДОМЛЕННЯ]\n" + details)
            print("-" * 60)
            continue
        try:
            publish(p, chat)
            print("  ✅ опубліковано")
            _icon, _label, _tag = detect_category(p["plain"])
            if _label != "Водопостачання відновлено":      # «відновлено» - не аварія, не рахуємо
                safe_log("water", f"{_label}: {p['plain'][:120]}", key=f"water-{p['id']}", when=p["dt"])
        except Exception as e:
            print(f"  ❌ помилка публікації: {e}")
            sys.exit(1)       # ID не зберігаємо — наступний запуск спробує ще раз

    if not dry:
        commit_journal()
        save_last_id(newest)


if __name__ == "__main__":
    main()
