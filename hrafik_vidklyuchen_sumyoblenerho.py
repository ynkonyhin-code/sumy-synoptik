"""Сумський синоптик: репост графіків відключень з офіційного ТГ-каналу Сумиобленерго.

Що робить:
  1. Читає публічну стрічку https://t.me/s/SumyEnergo (без авторизації, без Cloudflare).
  2. Шукає пости за ключовими фразами: ГПВ, ГАВ / СГАВ, «Оновлено дані по відключенням на».
  3. Публікує їх у вашому каналі разом з оригінальною картинкою (або кількома, якщо це альбом),
     зберігаючи форматування та посилання, і додає підпис-джерело.
  4. Запам'ятовує вже опубліковане у файлі стану, щоб не було дублів.

Запуск:
  python hrafik_vidklyuchen_sumyoblenerho.py --dry-run     # показати, що було б опубліковано
  python hrafik_vidklyuchen_sumyoblenerho.py               # бойовий режим (BOT_TOKEN, CHAT_ID)

Змінні середовища (необов'язкові):
  MAX_AGE_HOURS=24       не публікувати пости старші за N годин
  FIRST_RUN_PUBLISH=1    на першому запуску опублікувати найновіший пост (0 = лише запам'ятати)
  DRY_RUN=1              те саме, що --dry-run
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

CHANNEL = "SumyEnergo"
TG_URL = f"https://t.me/s/{CHANNEL}"
STATE = Path("hrafik_vidklyuchen_sumyoblenerho_state.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

MAX_AGE_HOURS = float(os.getenv("MAX_AGE_HOURS", "24"))
FIRST_RUN_PUBLISH = os.getenv("FIRST_RUN_PUBLISH", "1") == "1"
SETTLE_SECONDS = 45      # не чіпаємо пост, поки він «свіжіший» за це (щоб альбом дозавантажився)
KEEP_SEEN = 100          # скільки ключів публікацій пам'ятати

FOOTER = '📡 Джерело: <a href="https://t.me/SumyEnergo">АТ «Сумиобленерго»</a>'

# Ключові слова та фрази (регістр не важливий, закінчення слів не важливі)
KEYWORDS = re.compile(
    "|".join([
        r"графік\w*\s+погодинн\w*\s+відключ\w*",       # Графіки погодинних відключень
        r"\bГПВ\b",                                      # (ГПВ)
        r"аварійн\w*\s+відключ\w*\s+світл\w*",          # АВАРІЙНЕ ВІДКЛЮЧЕННЯ СВІТЛА
        r"\bС?ГАВ\b",                                    # ГАВ / СГАВ
        r"оновлено\s+дані\s+по\s+відключ\w*",           # Оновлено дані по відключенням на:
    ]),
    re.IGNORECASE,
)


# ---------------------------------------------------------------- розбір сторінки
def fetch_page() -> str:
    r = requests.get(TG_URL, timeout=30,
                     headers={"User-Agent": UA, "Accept-Language": "uk,ru;q=0.8,en;q=0.5"})
    r.raise_for_status()
    return r.text


def node_to_html(node) -> str:
    """Переводить вміст поста в HTML, який розуміє Telegram (b, i, u, s, a, code, pre)."""
    if isinstance(node, NavigableString):
        return html.escape(str(node))
    if not isinstance(node, Tag):
        return ""
    if node.name == "br":
        return "\n"
    if node.name == "i" and "emoji" in (node.get("class") or []):
        return html.escape(node.get_text())                # емодзі лишаємо звичайним символом
    inner = "".join(node_to_html(c) for c in node.children)
    name = node.name
    if name == "a":
        href = (node.get("href") or "").strip()
        if href.startswith(("http://", "https://", "tg://")):
            return f'<a href="{html.escape(href, quote=True)}">{inner}</a>'
        return inner                                       # внутрішні посилання (#хештеги) — просто текст
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


def parse_messages(page: str) -> list[dict]:
    soup = BeautifulSoup(page, "html.parser")
    out = []
    for msg in soup.select(".tgme_widget_message"):
        post = msg.get("data-post", "")
        m = re.search(r"/(\d+)$", post)
        if not m:
            continue
        text_el = next((t for t in msg.select(".tgme_widget_message_text")
                        if not t.find_parent(class_="tgme_widget_message_reply")), None)
        dt = None
        t_el = msg.select_one(".tgme_widget_message_date time")
        if t_el and t_el.get("datetime"):
            try:
                dt = datetime.fromisoformat(t_el["datetime"])
            except ValueError:
                pass
        photos = []
        for ph in msg.select(".tgme_widget_message_photo_wrap"):
            u = re.search(r"url\(['\"]?(.*?)['\"]?\)", ph.get("style", ""))
            if u and u.group(1) not in photos:
                photos.append(u.group(1))
        out.append({
            "id": int(m.group(1)),
            "dt": dt,
            "html": "".join(node_to_html(c) for c in text_el.children).strip() if text_el else "",
            "plain": text_el.get_text("\n").strip() if text_el else "",
            "photos": photos,
        })
    return out


def build_clusters(msgs: list[dict]) -> list[dict]:
    """Склеює альбом (кілька постів підряд з картинками) в одну публікацію."""
    clusters: list[list[dict]] = []
    for m in sorted(msgs, key=lambda x: x["id"]):
        if clusters:
            prev = clusters[-1]
            last = prev[-1]
            close = (m["dt"] and last["dt"] and abs((m["dt"] - last["dt"]).total_seconds()) <= 90)
            consecutive = m["id"] == last["id"] + 1
            cluster_has_text = any(x["plain"] for x in prev)
            # приєднуємо, якщо підпис ще не з'явився або це «хвіст» альбому без тексту
            if consecutive and close and (not m["plain"] or not cluster_has_text):
                prev.append(m)
                continue
        clusters.append([m])
    result = []
    for c in clusters:
        photos = []
        for m in c:
            for p in m["photos"]:
                if p not in photos:
                    photos.append(p)
        result.append({
            "key": str(c[0]["id"]),
            "dt": c[-1]["dt"],
            "html": "\n\n".join(m["html"] for m in c if m["html"]),
            "plain": "\n\n".join(m["plain"] for m in c if m["plain"]),
            "photos": photos,
        })
    return result


# ---------------------------------------------------------------- Telegram Bot API
def need_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        sys.exit(f"❌ Змінна {name} порожня. Перевірте GitHub → Settings → Secrets and variables → "
                 f"Actions → вкладка Secrets: має існувати секрет {name} (точно таке ім'я).")
    return v


def tg_api(method: str, data: dict, files: dict | None = None):
    token = need_env("BOT_TOKEN")
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}",
                      data=data, files=files, timeout=90)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def plain_len(h: str) -> int:
    return len(html.unescape(re.sub(r"<[^>]+>", "", h)))


def send_text(chat: str, body: str, plain: str):
    if len(body) > 4000:
        body = html.escape(plain)[:3800] + "…\n\n" + FOOTER
    tg_api("sendMessage", {"chat_id": chat, "text": body, "parse_mode": "HTML",
                           "disable_web_page_preview": "true"})


def send_photos(chat: str, photos: list[bytes], caption: str | None):
    if len(photos) == 1:
        data = {"chat_id": chat}
        if caption:
            data.update(caption=caption, parse_mode="HTML")
        tg_api("sendPhoto", data, files={"photo": ("photo.jpg", photos[0])})
        return
    media, files = [], {}
    for i, b in enumerate(photos[:10]):
        item = {"type": "photo", "media": f"attach://p{i}"}
        if i == 0 and caption:
            item.update(caption=caption, parse_mode="HTML")
        media.append(item)
        files[f"p{i}"] = (f"p{i}.jpg", b)
    tg_api("sendMediaGroup", {"chat_id": chat, "media": json.dumps(media)}, files=files)


def publish(c: dict, chat: str):
    body = (c["html"] + "\n\n" if c["html"] else "") + FOOTER
    images = []
    for url in c["photos"][:10]:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": UA})
            r.raise_for_status()
            images.append(r.content)
        except Exception as e:
            print(f"  ⚠ не вдалося завантажити картинку: {e}")
    if images:
        fits = plain_len(body) <= 1024          # ліміт підпису до фото в Telegram
        send_photos(chat, images, body if fits else None)
        if not fits:
            send_text(chat, body, c["plain"])
    else:
        send_text(chat, body, c["plain"])


# ---------------------------------------------------------------- головна логіка
def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args or os.getenv("DRY_RUN") == "1"
    local = args[args.index("--html") + 1] if "--html" in args else None   # для тестів

    chat = None if dry else need_env("CHAT_ID")
    if not dry:
        need_env("BOT_TOKEN")

    page = Path(local).read_text(encoding="utf-8") if local else fetch_page()
    clusters = [c for c in build_clusters(parse_messages(page)) if KEYWORDS.search(c["plain"])]
    print(f"Знайдено постів із ключовими словами: {len(clusters)}")

    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    seen = state.get("seen")
    first_run = seen is None
    seen = list(seen or [])

    now = datetime.now(timezone.utc)

    def settled(c):
        return local or not c["dt"] or (now - c["dt"]).total_seconds() >= SETTLE_SECONDS

    def fresh(c):
        return local or not c["dt"] or (now - c["dt"]) <= timedelta(hours=MAX_AGE_HOURS)

    ready = [c for c in clusters if settled(c)]
    todo = [c for c in ready if c["key"] not in seen and fresh(c)]

    if first_run:
        print("Перший запуск: усі наявні пости запам'ятовуємо як опубліковані.")
        todo = todo[-1:] if FIRST_RUN_PUBLISH else []
        seen += [c["key"] for c in ready if c["key"] not in seen]

    failed = 0
    for c in todo:
        print(f"→ пост {c['key']}: {len(c['photos'])} фото, {len(c['plain'])} символів")
        if dry:
            print("-" * 60)
            print((c["html"] or "(без тексту)") + "\n\n" + FOOTER)
            print("Фото:", *c["photos"], sep="\n  ")
            print("-" * 60)
            continue
        try:
            publish(c, chat)
            seen.append(c["key"])
        except Exception as e:
            failed += 1
            print(f"  ❌ помилка публікації: {e}")

    if not todo and not first_run:
        print("Нових постів немає.")

    if not dry:
        state["seen"] = seen[-KEEP_SEEN:]
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
