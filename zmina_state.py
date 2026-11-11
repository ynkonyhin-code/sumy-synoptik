# -*- coding: utf-8 -*-
"""Сховище стану «Нічної зміни» — без гонок між workflow.

Раніше стан лежав у файлі `nichna_zmina_state.json` і зберігався окремим кроком
workflow через `git commit && git pull --rebase && git push`. Крок падав через
non-fast-forward (30 workflow'ів пишуть у `main` одночасно), стан не оновлювався,
і той самий слот виходив повторно або губився.

Тепер стан лежить у GitHub Actions cache (як антидубль у «Щоденному календарі»):
  • ключ `zmina-<коміт>-<ночка>-<номер спроби>` — кожен запуск пише свій,
  • `restore-keys: zmina-<коміт>-<ночка>` — наступний запуск відновлює найновіший,
  • коли кешів стає забагато, GitHub витісняє найстаріші — для нас це нешкідливо.

Модуль також пише «людську» копію в `state/nichna_zmina.json` (її зберігає workflow),
щоб стан було видно в репозиторії й можна було перевірити очима.
"""
from __future__ import annotations

import json
import os
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")
BASE = Path(__file__).resolve().parent
STATE_DIR = BASE / "state"
STATE_FILE = STATE_DIR / "nichna_zmina.json"
CACHE_DIR = Path(os.getenv("NICHNA_CACHE_DIR") or (BASE / ".zmina_cache"))
CACHE_FILE = CACHE_DIR / "state.json"

# ──────────────────────────────────────────────────────────────────────────────
# Розклад ночі (за Києвом)
# ──────────────────────────────────────────────────────────────────────────────
# «Ніч» починається о 20:00 і триває до 12:00 наступного дня — так пост, що
# вийшов о 09:40, ще належить цій ночі, а не наступній.
NIGHT_START_HOUR = 20

# Передача варти: Кіт здає Сові ввечері, Сова здає Котові вранці.
# (ім'я, тип, години, хвилини, розкид хв, вікно «догону» хв)
SHIFT_SLOTS = [
    ("evening", "evening", 23, 15, 5, 240),   # 23:15 → наздоганяє до 03:15
    ("morning", "morning", 6, 0, 5, 300),     # 06:00 → наздоганяє до 11:00
]

# Вікна для матеріалів Сови (2 на ніч, іноді 3).
# Перше — «раннє»: одразу після вечірньої передачі варти.
# Друге — «глибоке»: для тих, хто справді не спить.
MATERIAL_SLOTS = [
    ("m1", 0, 30, 15, 120),     # 00:30 → 02:30
    ("m2", 2, 15, 15, 135),     # 02:15 → 04:30
    ("m3", 3, 45, 15, 120),     # 03:45 → 05:45 (третій матеріал, не кожну ніч)
]
MATERIAL_SLOTS_3 = 2          # скільки матеріалів гарантовано щоночі

MIN_GAP_MIN = 25              # мінімум між постами (пачка запусків не дає дублів)
DEEP_NIGHT_START = 0          # година, з якої вважається «глибока ніч»

# Які рубрики в яку частину ночі доречніші (для вибору матеріалу)
EARLY_KINDS = ("tale", "legend")            # до півночі й одразу після
DEEP_KINDS = ("legend", "phenomenon", "people", "tale")   # глибока ніч


def night_of(now: datetime) -> date:
    """Дата ночі, до якої належить момент `now` (Київ)."""
    local = now.astimezone(KYIV) if now.tzinfo else now.replace(tzinfo=KYIV)
    if local.hour < 12:                       # 00:00–11:59 — це ще вчорашня ніч
        return (local - timedelta(days=1)).date()
    return local.date()


def night_start(night: date) -> datetime:
    return datetime(night.year, night.month, night.day, NIGHT_START_HOUR, tzinfo=KYIV)


def _blank(night: date) -> dict:
    return {"night": night.isoformat(), "done": [], "last_post_at": None,
            "skip": {}, "recent": [], "morning": None}


# ──────────────────────────────────────────────────────────────────────────────
# Завантаження / збереження
# ──────────────────────────────────────────────────────────────────────────────
def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load(night: date | None = None) -> dict:
    """Стан ночі. Джерела за пріоритетом: кеш Actions → state/ у репо → порожній."""
    night = night or night_of(datetime.now(KYIV))
    state = {}
    for path in (CACHE_FILE, STATE_FILE):
        data = _read(path)
        if data.get("night") == night.isoformat():
            state = data
            break
    base = _blank(night)
    # беремо всі збережені поля (у тому числі «spoken» — про що Сова говорила вночі),
    # але гарантуємо наявність ключів, на які спирається логіка
    base.update(state)
    base["night"] = night.isoformat()
    base["done"] = list(state.get("done") or [])
    return base


def save(state: dict) -> None:
    """Зберегти стан у кеш-теку (його підхопить наступний запуск) і в репо."""
    payload = json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True)
    for path in (CACHE_FILE, STATE_FILE):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        except Exception as e:                       # noqa: BLE001
            print(f"state: не вдалося записати {path.name}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Вибір слоту
# ──────────────────────────────────────────────────────────────────────────────
def _shift_target(night: date, slot) -> datetime:
    name, _kind, hh, mm, jitter, _win = slot
    shift = random.Random(f"zmina-{night.isoformat()}-{name}").randint(0, jitter)
    return night_start(night) + timedelta(hours=(hh - NIGHT_START_HOUR) % 24, minutes=mm + shift)


def _material_target(night: date, slot) -> datetime:
    name, hh, mm, jitter, _win = slot
    shift = random.Random(f"zmina-{night.isoformat()}-{name}").randint(0, jitter)
    # m1/m2/m3 задані як години «після півночі» — рахуємо від початку доби
    day = night + timedelta(days=1)
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=KYIV) + timedelta(minutes=shift)


def material_count(night: date) -> int:
    """2 матеріали щоночі, третій — через одну ніч (детерміновано за датою)."""
    return 3 if night.toordinal() % 2 == 0 else 2


def next_action(state: dict, now: datetime) -> dict | None:
    """Що публікувати зараз. Повертає dict або None.

    {'kind': 'evening'|'morning'|'material', 'slot': ..., 'reason': ...}
    """
    night = night_of(now)
    local = now.astimezone(KYIV) if now.tzinfo else now.replace(tzinfo=KYIV)
    done = set(state.get("done", []))

    # 1) передача варти (вечір — до 03:15, ранок — до 11:00)
    for slot in SHIFT_SLOTS:
        name = slot[0]
        if name in done:
            continue
        target = _shift_target(night, slot)
        window = timedelta(minutes=slot[5])
        if target <= local <= target + window:
            if _too_soon(state, local):
                return None
            return {"kind": slot[1], "slot": name, "night": night}

    # 2) матеріали Сови
    limit = material_count(night)
    used = [n for n in done if n.startswith("m")]
    if len(used) >= limit:
        return None
    # m1/m2 — обов'язкові матеріали ночі; m3 — «бонусний», іде останнім у черзі.
    # Для нього окреме вікно, що закінчується раніше за ранкову передачу варти,
    # тож він виходить лише тоді, коли ніч справді дозволяє.
    order = MATERIAL_SLOTS[:limit]
    if limit >= 3:
        order = [s for s in MATERIAL_SLOTS if s[0] != "m3"] + [s for s in MATERIAL_SLOTS if s[0] == "m3"]
    for slot in order:
        name = slot[0]
        if name in done:
            continue
        target = _material_target(night, slot)
        window = timedelta(minutes=slot[4])
        if name == "m3":
            # Бонусний матеріал. Вікно: 01:45–04:00, і обидва обов'язкові матеріали
            # вже мають вийти — тобто третій пост буває лише в «спокійні» ночі.
            if not (target <= local <= target + window):
                continue
            if not ({"m1", "m2"} <= done):
                continue                     # ще не все обов'язкове — m3 зачекає
            if _too_soon(state, local):
                return None
            return {"kind": "material", "slot": name, "night": night}
        if target <= local <= target + window:
            if _too_soon(state, local):
                return None
            return {"kind": "material", "slot": name, "night": night}
        if local < target:
            return None
    return None


def _too_soon(state: dict, now: datetime) -> bool:
    last = state.get("last_post_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return False
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=KYIV)
    now = now.astimezone(KYIV) if now.tzinfo else now.replace(tzinfo=KYIV)
    gap = (now - last_dt).total_seconds() / 60
    if gap < 0:                          # мітки часу з майбутнього не блокують публікацію
        return False
    if gap < MIN_GAP_MIN:
        print(f"[wait] попередній пост був {last_dt:%H:%M}, пауза {MIN_GAP_MIN} хв")
        return True
    return False


def mark_done(state: dict, slot: str, now: datetime) -> None:
    done = state.setdefault("done", [])
    if slot not in done:
        done.append(slot)
    state["last_post_at"] = now.isoformat()


def note_skip(state: dict, reason: str, now: datetime) -> None:
    """Записати, чому нічого не вийшло — щоб уранці було видно причину."""
    state.setdefault("skip", {})[now.strftime("%H:%M")] = reason[:120]


# ──────────────────────────────────────────────────────────────────────────────
# Ротація матеріалів: без повторів, «по колу» після проходження всього списку
# ──────────────────────────────────────────────────────────────────────────────
def pick_material(state: dict, night: date, now: datetime, pool: dict) -> tuple[str, tuple]:
    """Вибрати (рубрика, матеріал) без повторів, доки не скінчиться пул.

    `pool` = {'tale': [...], 'legend': [...], ...}. Вибір залежить від часу:
    рано вночі — байки й легенди, глибоко вночі — ще й явища та синоптики.
    """
    local = now.astimezone(KYIV) if now.tzinfo else now.replace(tzinfo=KYIV)
    kinds = EARLY_KINDS if (local.hour >= 22 or local.hour < 1) else DEEP_KINDS
    recent = set(state.get("recent", []))          # ключі виду "legend:Чумацький Шлях"

    def collect(only_kinds):
        out = []
        for kind in only_kinds:
            for idx, item in enumerate(pool.get(kind) or []):
                if f"{kind}:{item[0]}" in recent:
                    continue
                # місячний фільтр: третій елемент запису — список місяців
                months = item[2] if len(item) > 2 and isinstance(item[2], (list, tuple)) else None
                if months and local.month not in months:
                    continue
                out.append((kind, idx, item))
        return out

    candidates = collect(kinds)
    if not candidates:                       # для цієї пори ночі все показано — беремо ширший пул
        candidates = collect(tuple(pool))
    if not candidates:                       # усе переглянуто — починаємо коло заново
        state["recent"] = []
        return pick_material(state, night, now, pool)

    rnd = random.Random(f"material-{night.isoformat()}-{len(recent)}-{now:%H%M}")
    kind, idx, item = rnd.choice(candidates)
    return kind, item


def remember(state: dict, kind: str, item: tuple, pool_size: int, max_recent: int) -> None:
    """Запам'ятати матеріал як використаний (щоб не повторювався)."""
    items = [i for i in range(pool_size)]
    title = item[0]
    # ключ будуємо за індексом у пулі — знайдемо його за заголовком
    recent = state.setdefault("recent", [])
    key = f"{kind}:{title}"
    if key not in recent:
        recent.append(key)
    state["recent"] = recent[-max_recent:]


def remember_key(state: dict, kind: str, title: str, max_recent: int = 400) -> None:
    recent = state.setdefault("recent", [])
    key = f"{kind}:{title}"
    if key in recent:
        recent.remove(key)
    recent.append(key)
    state["recent"] = recent[-max_recent:]
