#!/usr/bin/env python3
"""
anons_tayemnytsi_neba — афіша-анонс проєкту «Таємниці неба» для «Київського не гідрометцентру».

Публікує картинку-анонс двічі на день (ранок і вечір, час щоразу трохи різний), без звуку,
а попередню афішу видаляє — тож у стрічці завжди лише одна свіжа.
Картинки: файли anons_tayemnytsi_neba_poster_01.jpg, _02.jpg, … (jpg/jpeg/png/webp) поруч зі скриптом.
Кількість не обмежена: скрипт показує їх по черзі. Немає жодної картинки — просто нічого не робить.

Потрібні змінні середовища: TELEGRAM_BOT_TOKEN (або BOT_TOKEN), CHAT_ID.
Тестування:  TEST_POST=true (надіслати зараз, без збереження стану й без видалення попередньої афіші),
             TEST_CHAT_ID=<id> (у тесті надсилати сюди, а не в канал),
             DRY_RUN=true (нічого не надсилати: зберегти кадр у anons_tayemnytsi_neba_test.jpg і вивести підпис).
"""
import glob
import html
import json
import os
import random
import sys
from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageColor, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
KYIV = ZoneInfo("Europe/Kyiv")
STATE_FILE = os.path.join(HERE, "anons_tayemnytsi_neba_state.json")
OVERLAY_FILE = os.path.join(HERE, "anons_tayemnytsi_neba_overlay.json")
IMAGE_MASKS = ["anons_tayemnytsi_neba_poster_*.jpg", "anons_tayemnytsi_neba_poster_*.jpeg",
               "anons_tayemnytsi_neba_poster_*.png", "anons_tayemnytsi_neba_poster_*.webp"]
FONT_CANDIDATES = [os.path.join(HERE, "yak_pratsyuye_pohoda_font.ttf"),
                   os.path.join(HERE, "anons_tayemnytsi_neba_font.ttf"),
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"]

# ── Розклад: (назва, година, хвилина, розкид у хвилинах); час публікації = початок + випадкові 0…розкид хв (Київ)
SLOTS = [("morning", 8, 0, 30), ("evening", 20, 30, 30)]
LATE_MIN = 90            # якщо запуск запізнився, ще публікуємо протягом цих хвилин
PIN_LATEST = False       # True — ще й закріплювати афішу вгорі каналу (без звуку)
MAX_SIDE = 1600          # довша сторона картинки (Telegram не любить занадто великі)

# ── Тексти (правте тут, коли змінюється розклад або з'являються нові підпроєкти)
SCHEDULE_TEXT = (
    "📅 <b>Коли що виходить</b>\n"
    "• Вівторок і п'ятниця ввечері — «Таємниці неба»\n"
    "• Середа і субота — «Словник синоптика»\n"
    "• Четвер ввечері — «Погода, що змінила історію»\n"
    "• Неділя вранці — «Як працює погода», ввечері — вікторина тижня\n"
    "• Понеділок ввечері — опитування тижня\n"
    "⏳ Скоро: «Запитай синоптика»"
)
TAGS = "#ТаємниціНеба #КиївськийНеГідрометцентр #Київ"
CAPTIONS = {
    "morning": [
        "🌅 <b>Доброго ранку, Києве!</b>\nЗнайомтесь із проєктом «Таємниці неба»: історії про небо й людей, що його вивчали, а ще зрозуміло про те, як усе працює. ☁️",
        "☀️ <b>Таємниці неба: від давніх прикмет до штучного інтелекту</b>\nНа афіші — з чого складається наш проєкт. Заглядайте: щось уже працює, а щось скоро з'явиться!",
        "🌤 <b>Новий день — нові таємниці неба</b>\nПрикмети, історія, наука та трішки штучного інтелекту — усе в одному проєкті.",
    ],
    "evening": [
        "🌙 <b>Добрий вечір!</b>\nНагадуємо про наш проєкт «Таємниці неба»: прикмети, історія, наука й зрозумілі пояснення погоди. ✨",
        "🌆 <b>Вечірня афіша «Таємниць неба»</b>\nЩо вже є в проєкті та що з'явиться найближчим часом — на картинці.",
        "✨ <b>Перед сном — трохи неба</b>\nЗагляньте в «Таємниці неба»: приєднуйтесь і пересилайте тим, кому цікаво, чому небо таке, яким ми його бачимо.",
    ],
}


def esc(s):
    return html.escape(s, quote=False)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def find_images():
    files = []
    for m in IMAGE_MASKS:
        files += glob.glob(os.path.join(HERE, m))
    return sorted(set(files))


def font(size):
    for p in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def apply_overlay(img, labels):
    """Підписи поверх афіші. Поля: text (можна з \n), x, y, size — частки розміру кадру; color, stroke/stroke_width;
    plate — колір «плашки» під текстом; sub — другий, дрібніший рядок (наприклад, «Вже працює» / «Скоро») з кольором sub_color."""
    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    for lb in labels:
        size = max(10, int(lb.get("size", 0.03) * h))
        f = font(size)
        lines = lb["text"].split("\n")
        lh = int(size * 1.2)
        sub = lb.get("sub")
        sf = font(max(9, int(size * 0.78)))
        slh = int(size * 0.78 * 1.25)
        tw = max(d.textlength(ln, font=f) for ln in lines)
        if sub:
            tw = max(tw, d.textlength(sub, font=sf))
        th = lh * len(lines) + (slh if sub else 0)
        x, y = lb["x"] * w, lb["y"] * h
        if lb.get("plate"):
            px, py = size * 0.6, size * 0.38
            d.rounded_rectangle([x - tw / 2 - px, y - th / 2 - py, x + tw / 2 + px, y + th / 2 + py],
                                radius=int(size * 0.55), fill=ImageColor.getrgb(lb["plate"]))
        sw = int(lb.get("stroke_width", 0) * h)
        top = y - th / 2
        for i, ln in enumerate(lines):
            d.text((x, top + lh * (i + 0.5)), ln, font=f, fill=ImageColor.getrgb(lb.get("color", "#FFFFFF")),
                   anchor="mm", stroke_width=sw, stroke_fill=ImageColor.getrgb(lb.get("stroke", "#1C3C78")))
        if sub:
            d.text((x, top + lh * len(lines) + slh / 2), sub, font=sf,
                   fill=ImageColor.getrgb(lb.get("sub_color", "#1E8E4E")), anchor="mm")
    return img


def prepare_image(path):
    img = Image.open(path).convert("RGB")
    if max(img.size) > MAX_SIDE:
        k = MAX_SIDE / max(img.size)
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
    cfg = load_json(OVERLAY_FILE, {}).get("files", {}).get(os.path.basename(path))
    if cfg and cfg.get("enabled"):
        img = apply_overlay(img, cfg.get("labels", []))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def due_slot(now, done):
    today = now.date().isoformat()
    for name, hh, mm, spread in SLOTS:
        key = f"{today}-{name}"
        if key in done:
            continue
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        target = start + timedelta(minutes=random.Random(key).randint(0, spread))
        if target <= now <= target + timedelta(minutes=LATE_MIN):
            return name, key
    return None, None


def build_caption(slot, key, test=False):
    text = random.Random(key).choice(CAPTIONS[slot])
    head = "🧪 <i>тестовий пост</i>\n\n" if test else ""
    return f"{head}{text}\n\n{SCHEDULE_TEXT}\n\n{TAGS}"


def api(token, method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    if not r.ok:
        raise RuntimeError(f"Telegram {method}: {r.status_code} {r.text}")
    return r.json()


def main():
    token, channel = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    dry = os.environ.get("DRY_RUN", "").lower() == "true"
    if not dry and (not token or not channel):
        print("[error] TELEGRAM_BOT_TOKEN / CHAT_ID не задані")
        return 1

    images = find_images()
    if not images:
        print("[info] немає жодної картинки anons_tayemnytsi_neba_poster_*.jpg — нічого публікувати")
        return 0

    test = os.environ.get("TEST_POST", "").lower() == "true" or dry
    state = load_json(STATE_FILE, {})
    now = datetime.now(KYIV)

    if test:
        slot, key = ("morning" if now.hour < 15 else "evening"), f"test-{now:%Y%m%d%H%M}"
    else:
        slot, key = due_slot(now, state.get("done", []))
        if not slot:
            print("[skip] зараз не час для афіші")
            return 0

    idx = state.get("next_image", 0) % len(images)
    path = images[idx]
    image = prepare_image(path)
    caption = build_caption(slot, key, test)
    if len(caption) > 1024:
        print(f"[error] підпис задовгий: {len(caption)} символів (ліміт 1024)")
        return 1

    if dry:
        with open("anons_tayemnytsi_neba_test.jpg", "wb") as f:
            f.write(image)
        print(f"[dry] картинка: {os.path.basename(path)} → anons_tayemnytsi_neba_test.jpg\n\n{caption}")
        return 0

    chat = (os.environ.get("TEST_CHAT_ID") or channel) if test else channel
    res = api(token, "sendPhoto", data={"chat_id": chat, "caption": caption, "parse_mode": "HTML",
                                        "disable_notification": "true"},
              files={"photo": ("anons_tayemnytsi_neba.jpg", image, "image/jpeg")})
    new_id = res["result"]["message_id"]
    print(f"[ok] афіша ({slot}): {os.path.basename(path)}, повідомлення {new_id}")
    if test:
        return 0

    old_id = state.get("last_message_id")
    if old_id:
        try:
            api(token, "deleteMessage", data={"chat_id": chat, "message_id": old_id})
            print(f"[ok] видалено попередню афішу {old_id}")
        except Exception as e:  # не критично: зазвичай бракує права «видаляти повідомлення» або минуло 48 год
            print(f"[warn] не вдалося видалити попередню афішу: {e}")
    if PIN_LATEST:
        try:
            api(token, "pinChatMessage", data={"chat_id": chat, "message_id": new_id, "disable_notification": "true"})
        except Exception as e:
            print(f"[warn] не вдалося закріпити афішу: {e}")

    done = (state.get("done", []) + [key])[-10:]
    state.update(done=done, last_message_id=new_id, next_image=idx + 1)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
