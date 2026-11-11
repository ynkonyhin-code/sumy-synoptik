#!/usr/bin/env python3
"""
nichna_zmina — «Нічна зміна» для Сумського синоптика.

Кіт (денна зміна) увечері здає варту Сові й перелічує, що вийшло за день.
Сова вночі розповідає тим, хто не спить. Уранці Сова здає зміну Котові
й розповідає, про що говорила вночі.

Розклад (за Києвом, «ніч» рахується з 20:00):
  23:15  вечірня передача зміни (Кіт → Сова) + звіт про денні пости
  00:45  матеріал Сови №1
  03:30  матеріал Сови №2
  01:45  матеріал Сови №3 (через одну ніч)
  06:00  ранкова передача зміни (Сова → Кіт) + про що говорила вночі

До кожного часу додається випадковий зсув (5–15 хв). Вікна «догонові»: якщо GitHub
запустив розклад із запізненням, пост усе одно вийде (вечір до 03:15, ранок до 11:00,
матеріали — до 2 годин), але не раніше ніж через 25 хв після попереднього поста.

Матеріали Сови (125 штук: байки, легенди, погодні явища, великі синоптики) ротуються
без повторів — приблизно на два місяці, потім ідуть по колу.

Потрібні змінні середовища: BOT_TOKEN, CHAT_ID.
Необов'язково: TEST_KIND=evening|morning|material (надіслати зараз, без збереження стану).
Аргументи: --dry-run (лише показати текст), --kind ..., --weather (додати «Зведення тиші»).

Стан лежить у кеші GitHub Actions (zmina_state.py), тож гонок за `main` більше немає.
"""
import argparse
import html
import os
import random
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import nichna_weather
import nichna_zmina_data as D
import zmina_state as Z
from digest_tracker import track

KYIV = ZoneInfo("Europe/Kyiv")
BASE = os.path.dirname(os.path.abspath(__file__))
IMAGES = {"evening": "zmina_vechir.jpg", "morning": "zmina_ranok.jpg", "material": "bayka_sovy.jpg"}
TAGS = "#СумськийСиноптик #Суми"
MAX_LEN = 4096

KIND_HEAD = {
    "tale": ("🦉 <b>Нічна байка від Сови</b>", "<i>Для тих, хто не спить</i>", "#НічнаБайка #БайкиСови"),
    "legend": ("🦉 <b>Легенди старої Сови</b>", "<i>Те, що розповідали наші предки про небо й погоду</i>",
               "#Легенди #НародніПерекази"),
    "phenomenon": ("🦉 <b>Сова пояснює</b>", "<i>Погодні явища — як вони влаштовані насправді</i>",
                   "#ПогодніЯвища #Цікаве"),
    "people": ("🦉 <b>Великі синоптики</b>", "<i>Люди, які навчили нас розуміти погоду</i>",
               "#Синоптики #ІсторіяНауки"),
}


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ──────────────────────────────────────────────────────────────────────────────
# Тексти постів
# ──────────────────────────────────────────────────────────────────────────────
def build_material(kind: str, item: tuple, no: int, weather_block: str | None = None) -> str:
    title, text = item[0], item[1]
    head, sub, tags = KIND_HEAD.get(kind, KIND_HEAD["tale"])
    lines = [f"{head} №{no}", sub, "", f"📖 <b>{esc(title)}</b>", "", esc(text), ""]
    if weather_block:
        lines += [weather_block, ""]
    lines += ["🌙 Добраніч, а хто не спить — тримайтесь, я поруч.", "", f"{tags} {TAGS}"]
    return "\n".join(lines)


def _report_lines(night_start: datetime) -> list[str]:
    """Що вийшло за день (для кота) — з журналу публікацій journal/posted."""
    try:
        from digest_tracker import read_week
    except Exception:                                  # noqa: BLE001
        return []
    # вечірня передача о 23:15 — отже, звіт за день, у який вона відбувається
    days = [night_start.date(), (night_start - timedelta(days=1)).date()]
    week = read_week(min(days), max(days))
    today = night_start.date().isoformat()
    for day in sorted(week, key=lambda d: (d == today, d), reverse=True):
        entries = week[day]
        if not entries:
            continue
        # сам «Підсумок тижня» у вечірній звіт не входить: він виходить зранку в понеділок
        items = [(k, v) for k, v in entries.items() if k != "digest"]
        if not items:
            continue
        lines = ["📋 <b>Що вийшло за день</b>"]
        for _key, v in sorted(items, key=lambda kv: kv[1].get("ts", "")):
            detail = f" — {esc(v['detail'])}" if v.get("detail") else ""
            lines.append(f"• {esc(v.get('title', ''))}{detail}")
        return lines
    return []


def _morning_summary(night: date) -> list[str]:
    """Про що Сова говорила вночі — з того, що записав нічний запуск."""
    try:
        state = Z.load(night)
    except Exception:                                  # noqa: BLE001
        return []
    spoken = state.get("spoken") or []
    if not spoken:
        return []
    lines = ["🦉 <b>Про що я говорила вночі</b>"]
    for emoji, title in spoken:
        lines.append(f"• {emoji} <i>{esc(title)}</i>")
    return lines


def build_shift(kind: str, idx: int, night: date) -> str:
    texts = D.EVENING if kind == "evening" else D.MORNING
    parts = [texts[idx % len(texts)]]
    if kind == "evening":
        report = _report_lines(Z.night_start(night))
        if report:
            parts += ["", *report]
        parts += ["", f"🦉 #НічнаЗміна #ЗмінаВарти {TAGS}"]
    else:
        spoken = _morning_summary(night)
        if spoken:
            parts += ["", *spoken]
        parts += ["", f"🐱 #НічнаЗміна #ЗмінаВарти {TAGS}"]
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Надсилання
# ──────────────────────────────────────────────────────────────────────────────
def send(token: str, chat_id: str, kind: str, text: str) -> bool:
    """Надсилає картинку (якщо є) окремо, потім текст. Повертає True/False."""
    img = os.path.join(BASE, IMAGES.get(kind, IMAGES["material"]))
    if os.path.exists(img):
        with open(img, "rb") as f:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                              data={"chat_id": chat_id}, files={"photo": f}, timeout=60)
        if not r.ok:
            print(f"[warn] фото не надіслано: {r.status_code} {r.text[:200]}")
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        print(f"[error] Telegram: {r.status_code} {r.text[:300]}")
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Основна логіка
# ──────────────────────────────────────────────────────────────────────────────
def pool() -> dict:
    return {"tale": D.TALES, "legend": D.LEGENDS,
            "phenomenon": D.PHENOMENA, "people": D.PEOPLE}


def material_no(state: dict) -> int:
    return sum(1 for n in state.get("done", []) if n.startswith("m")) + 1


def weather_block(now: datetime, night: date, slot: str) -> str | None:
    rnd = random.Random(f"zvedennia-{night.isoformat()}-{slot}")
    return nichna_weather.get_block(now, rnd)      # «іноді»: ~50% ночей + завжди при помітній погоді


def _publish(state: dict, now: datetime, slot: str, kind: str, text: str) -> int:
    token, chat_id = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    if not token or not chat_id:
        print("[error] BOT_TOKEN / CHAT_ID не задані")
        return 1
    if not send(token, chat_id, kind, text):
        return 1
    Z.mark_done(state, slot, now)
    Z.save(state)
    labels = {"evening": "передача зміни Кіт→Сова", "morning": "передача зміни Сова→Кіт"}
    track("zmina", detail=labels.get(kind, f"матеріал Сови ({slot})"))
    print(f"[ok] опубліковано «{slot}»")
    return 0


def run_once(state: dict, now: datetime) -> int:
    action = Z.next_action(state, now)
    if not action:
        Z.note_skip(state, "нічого публікувати за розкладом", now)
        print("[skip] зараз нічого публікувати")
        return 0
    kind, slot, night = action["kind"], action["slot"], action["night"]

    if kind in ("evening", "morning"):
        idx = state.get(f"{kind}_index", 0)
        text = build_shift(kind, idx, night)
        pool_size = len(D.EVENING if kind == "evening" else D.MORNING)
        state[f"{kind}_index"] = (idx + 1) % pool_size
    else:
        kind_name, item = Z.pick_material(state, night, now, pool())
        wb = weather_block(now, night, slot)
        text = build_material(kind_name, item, material_no(state), wb)
        if len(text) > MAX_LEN and wb:
            print(f"[warn] пост {len(text)} символів, публікую без «Зведення тиші»")
            text = build_material(kind_name, item, material_no(state), None)
        if len(text) > MAX_LEN:
            print(f"[error] пост задовгий: {len(text)}")
            return 1
        Z.remember_key(state, kind_name, item[0])
        emoji = KIND_HEAD.get(kind_name, KIND_HEAD["tale"])[0].split(" ")[0]
        state.setdefault("spoken", []).append((emoji, item[0]))

    return _publish(state, now, slot, kind, text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--kind", choices=["evening", "morning", "material"])
    ap.add_argument("--weather", action="store_true", help="у dry-run додати «Зведення тиші» (потрібен інтернет)")
    args = ap.parse_args()

    now = datetime.now(KYIV)
    night = Z.night_of(now)
    state = Z.load(night)

    if args.dry_run:
        kinds = [args.kind] if args.kind else ["evening", "material", "morning"]
        for k in kinds:
            if k == "material":
                kind_name, item = Z.pick_material(dict(state), night, now, pool())
                wb = nichna_weather.get_block(now, force=True) if args.weather else None
                print(build_material(kind_name, item, 1, wb), "\n" + "-" * 40)
            else:
                print(build_shift(k, 0, night), "\n" + "-" * 40)
        return 0

    token, chat_id = os.environ.get("BOT_TOKEN"), os.environ.get("CHAT_ID")
    test_kind = os.environ.get("TEST_KIND", "").lower()
    if test_kind in ("evening", "morning", "material"):
        if not token or not chat_id:
            print("[error] BOT_TOKEN / CHAT_ID не задані")
            return 1
        if test_kind == "material":
            kind_name, item = Z.pick_material(dict(state), night, now, pool())
            text = build_material(kind_name, item, material_no(state), weather_block(now, night, "m1"))
        else:
            text = build_shift(test_kind, random.randrange(3), night)
        return 0 if send(token, chat_id, test_kind, text) else 1

    code = run_once(state, now)
    Z.save(state)
    return code


if __name__ == "__main__":
    sys.exit(main())
