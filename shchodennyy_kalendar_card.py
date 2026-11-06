# -*- coding: utf-8 -*-
"""
Генератор картки «Щоденний календар» (1080×1350, 4:5) для каналу «Сумський синоптик».

На картці: велика дата, ГОЛОВНА подія дня (заголовок), Місяць, схід/захід Сонця,
список свят та подій, народна прикмета.

Використання як модуль:
    from shchodennyy_kalendar import build_day
    from shchodennyy_kalendar_card import generate_card
    generate_card(build_day(date.today()), "output/card.png")

Самостійний запуск:
    python shchodennyy_kalendar_card.py                      # картка на сьогодні
    python shchodennyy_kalendar_card.py --date 2026-12-25 --out xmas.png
    python shchodennyy_kalendar_card.py --demo               # тестові дані, без shchodennyy_kalendar

Шрифт (кирилиця) шукається в такому порядку: тека зі скриптом → fonts/ поруч → fonts/ у поточній теці →
системні теки → шрифт із matplotlib. Найпростіше: покласти DejaVuSans.ttf і DejaVuSans-Bold.ttf
у корінь репозиторію поруч зі скриптами (папка fonts/ не потрібна).
"""
from __future__ import annotations

import argparse
import math
import os
import re
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
S = 2                      # малюємо у 2× та зменшуємо: гладкі краї
SS = 3                     # додатковий супер-семплінг для Місяця
HERE = os.path.dirname(os.path.abspath(__file__))

# Градієнти за місяцями: (верх, низ) — пори року
PALETTES = {
    1: ((18, 32, 66), (52, 90, 140)), 2: ((26, 40, 80), (84, 120, 170)),
    3: ((38, 78, 98), (120, 170, 160)), 4: ((34, 94, 98), (140, 198, 150)),
    5: ((30, 100, 80), (170, 214, 130)), 6: ((20, 110, 120), (240, 200, 110)),
    7: ((16, 100, 130), (250, 190, 90)), 8: ((24, 90, 120), (245, 170, 85)),
    9: ((90, 70, 40), (230, 160, 70)), 10: ((84, 44, 34), (206, 120, 60)),
    11: ((44, 52, 98), (122, 132, 190)), 12: ((14, 26, 58), (60, 100, 150)),
}
MONTHS_NOM_GEN = ["СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ",
                  "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ"]

NAVY, MUTED, GOLD = (27, 42, 65), (107, 122, 144), (255, 201, 74)
WHITE, SOFT = (255, 255, 255, 255), (255, 255, 255, 200)
PAD = 70


# ───────────────────────── шрифти ─────────────────────────
def _font_dirs() -> list[str]:
    dirs = [HERE, os.path.join(HERE, "fonts"), "fonts",
            "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
            "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/noto",
            "/Library/Fonts", "/System/Library/Fonts/Supplemental", "C:/Windows/Fonts"]
    try:                                   # DejaVu, що йде всередині matplotlib (як у киівському скрипті)
        import matplotlib
        dirs.append(os.path.join(matplotlib.get_data_path(), "fonts", "ttf"))
    except Exception:
        pass
    return dirs


REGULAR = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "Arial.ttf", "arial.ttf"]
BOLD = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]
_font_cache: dict = {}
_font_path_cache: dict = {}


def px(v: float) -> int:
    return int(round(v * S))


def _font_path(bold: bool) -> str:
    if bold in _font_path_cache:
        return _font_path_cache[bold]
    for folder in _font_dirs():
        for name in (BOLD if bold else REGULAR):
            p = os.path.join(folder, name)
            if os.path.exists(p):
                _font_path_cache[bold] = p
                return p
    raise RuntimeError("Не знайдено шрифт із кирилицею. Покладіть DejaVuSans.ttf та DejaVuSans-Bold.ttf "
                       "у корінь репозиторію поруч зі скриптом (або встановіть fonts-dejavu-core / matplotlib).")


def font(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(_font_path(bold), px(size))
    return _font_cache[key]


# ───────────────────────── допоміжне ─────────────────────────
_EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200d]+")


def _clean(text: str) -> str:
    """Шрифт не має емодзі — прибираємо їх лише з картки."""
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", text)).strip()


def _wrap(d, text: str, f, max_w: float) -> list[str]:
    words, lines, cur = _clean(text).split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=f) <= px(max_w):
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(d, text: str, sizes, bold: bool, max_w: float, max_lines: int):
    """Підбирає найбільший шрифт зі списку sizes, щоб текст вліз у max_lines; інакше обрізає «…»."""
    for size in sizes:
        f = font(size, bold)
        lines = _wrap(d, text, f, max_w)
        if len(lines) <= max_lines:
            return f, size, lines
    f, size = font(sizes[-1], bold), sizes[-1]
    lines = _wrap(d, text, f, max_w)[:max_lines]
    if lines:
        last = lines[-1]
        while last and d.textlength(last + "…", font=f) > px(max_w):
            last = last[:-1]
        lines[-1] = last.rstrip(" ,.;:") + "…"
    return f, size, lines


def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (px(W), px(H)), top)
    g = ImageDraw.Draw(img)
    for y in range(px(H)):
        t = y / (px(H) - 1)
        g.line([(0, y), (px(W), y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _text(d, xy, s, f, fill, anchor="la"):
    d.text((px(xy[0]), px(xy[1])), s, font=f, fill=fill, anchor=anchor)


def _panel(base, x, y, w, h, fill, radius=34, shadow=True):
    """Закруглена панель (з м'якою тінню для світлих)."""
    if shadow:
        pad = px(30)
        sh = Image.new("RGBA", (px(w) + 2 * pad, px(h) + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([pad, pad + px(6), pad + px(w), pad + px(h) + px(6)],
                                              radius=px(radius), fill=(10, 20, 50, 80))
        sh = sh.filter(ImageFilter.GaussianBlur(px(10)))
        base.paste(sh, (px(x) - pad, px(y) - pad), sh)
    ImageDraw.Draw(base, "RGBA").rounded_rectangle([px(x), px(y), px(x + w), px(y + h)],
                                                    radius=px(radius), fill=fill)



def _clip(d, lines, max_lines, f, max_w):
    """Обрізає список рядків до max_lines; в останньому ставить «…», якщо щось відкинули."""
    if len(lines) <= max_lines:
        return lines
    out = lines[:max_lines]
    last = out[-1]
    while last and d.textlength(last + "…", font=f) > px(max_w):
        last = last[:-1]
    out[-1] = last.rstrip(" ,.;:") + "…"
    return out


def _layout_items(d, rest, f, max_w, y0, limit, line_h=38, note_h=30):
    """Розкладає пункти: пробує до 2 рядків на пункт і до 1 рядка, обирає варіант, де влізає більше пунктів."""
    best = None
    for max_lines, gap in ((2, 12), (1, 8)):
        y, placed = y0, []
        for idx, (kind, text) in enumerate(rest):
            lines = _clip(d, _wrap(d, text, f, max_w), max_lines, f, max_w)
            need = len(lines) * line_h + gap
            reserve = note_h if idx + 1 < len(rest) else 0
            if y + need + reserve > limit:
                break
            placed.append((kind, lines, y))
            y += need
        if best is None or len(placed) > len(best[0]):
            best = (placed, y)
    return best


# ───────────────────────── значки ─────────────────────────
def _moon_icon(frac: float, size: int) -> Image.Image:
    """Місяць за часткою циклу (0=новий, 0.5=повня). Північна пів­куля: молодий — справа."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = s / 2 - 4 * SS
    cx = cy = s / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(38, 46, 70, 255), outline=(255, 255, 255, 90), width=2 * SS)
    k = math.cos(2 * math.pi * frac)
    lit = (250, 244, 220, 255)
    for yi in range(int(cy - r), int(cy + r) + 1):
        dy = yi - cy
        if abs(dy) > r:
            continue
        w = math.sqrt(max(r * r - dy * dy, 0))
        if frac <= 0.5:
            x0, x1 = cx + w * k, cx + w
        else:
            x0, x1 = cx - w, cx - w * k
        if x1 - x0 > 0.5:
            d.line([(x0, yi), (x1, yi)], fill=lit, width=1)
    return img.resize((size, size), Image.LANCZOS)


def _sun_icon(size: int) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, r = s / 2, s * 0.22
    for k in range(8):
        a = math.radians(k * 45)
        d.line([(c + math.cos(a) * s * 0.32, c + math.sin(a) * s * 0.32),
                (c + math.cos(a) * s * 0.46, c + math.sin(a) * s * 0.46)], fill=(255, 183, 3, 255), width=int(s * 0.055))
    d.ellipse([c - r, c - r, c + r, c + r], fill=(255, 196, 20, 255))
    d.ellipse([c - r + s * 0.04, c - r + s * 0.04, c + r - s * 0.04, c + r - s * 0.04], fill=(255, 214, 64, 255))
    return img.resize((size, size), Image.LANCZOS)


def _marker(d, kind, x, y):
    """Маркер у списку подій (x,y — лівий верх рядка, логічні px)."""
    if kind == "state":      # ● золотий
        d.ellipse([px(x), px(y + 9), px(x + 18), px(y + 27)], fill=(255, 183, 3, 255))
    elif kind == "church":   # ✚ синій
        c = (62, 100, 200, 255)
        d.rectangle([px(x + 7), px(y + 6), px(x + 11), px(y + 30)], fill=c)
        d.rectangle([px(x), px(y + 13), px(x + 18), px(y + 17)], fill=c)
    elif kind == "names":    # ★ рожева
        pts = [(9, 4), (13, 14), (24, 14), (15, 21), (19, 32), (9, 25), (-1, 32), (3, 21), (-6, 14), (5, 14)]
        d.polygon([(px(x + a), px(y + b)) for a, b in pts], fill=(230, 90, 140, 255))
    else:                    # ◆ бірюзовий (легенда)
        d.polygon([(px(x + 9), px(y + 5)), (px(x + 19), px(y + 18)), (px(x + 9), px(y + 31)), (px(x - 1), px(y + 18))],
                  fill=(32, 160, 160, 255))


# ───────────────────────── картка ─────────────────────────
def generate_card(info: dict, out_path: str = "output/card.png") -> str:
    d0: date = info["date"]
    top, bottom = PALETTES[d0.month]
    base = _gradient(top, bottom)

    # м'які декоративні кола
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([px(W - 520), px(-220), px(W + 160), px(460)], fill=(255, 255, 255, 30))
    gd.ellipse([px(-260), px(H - 520), px(360), px(H + 120)], fill=(255, 255, 255, 22))
    glow = glow.filter(ImageFilter.GaussianBlur(px(30)))
    base.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(base, "RGBA")

    # ── шапка ──
    _text(d, (PAD, 56), "СУМСЬКИЙ СИНОПТИК", font(34, True), WHITE)
    _text(d, (PAD, 104), "ЩОДЕННИЙ КАЛЕНДАР", font(26), SOFT)
    d.line([(px(PAD), px(158)), (px(W - PAD), px(158))], fill=(255, 255, 255, 90), width=px(2))

    # ── велика дата ──
    day_s = str(d0.day)
    day_font = font(300, True)
    _text(d, (PAD - 8, 400), day_s, day_font, WHITE, anchor="ls")
    mx = PAD + d.textlength(day_s, font=day_font) / S + 28
    _text(d, (mx, 214), MONTHS_NOM_GEN[d0.month - 1], font(54, True), WHITE)
    _text(d, (mx, 286), info["weekday"].upper(), font(40), SOFT)
    _text(d, (mx, 340), str(d0.year), font(34), SOFT)

    # ── головна подія дня (заголовок-стрічка) ──
    items = [("state", t) for t, _ in info["state"]] + [("church", t) for t, _ in info["church"]]
    if items:
        head_kind, head = items[0]
        rest = items[1:]
    else:
        head_kind, head, rest = "state", "Звичайний день для добрих справ", []
    if info["names"]:
        rest.append(("names", "Іменини: " + info["names"]))
    rib_y, rib_h = 432, 160
    _panel(base, PAD, rib_y, W - 2 * PAD, rib_h, (255, 255, 255, 242))
    d = ImageDraw.Draw(base, "RGBA")
    stripe = (255, 183, 3, 255) if head_kind == "state" else (62, 100, 200, 255)
    d.rounded_rectangle([px(PAD + 22), px(rib_y + 26), px(PAD + 30), px(rib_y + rib_h - 26)], radius=px(4), fill=stripe)
    _text(d, (PAD + 54, rib_y + 16), "СЬОГОДНІ" if head_kind == "state" else "ЦЕРКОВНИЙ КАЛЕНДАР",
          font(22, True), MUTED + (255,))
    f, size, lines = _fit(d, head, (42, 38, 34, 30), True, W - 2 * PAD - 100, 2)
    for i, ln in enumerate(lines):
        _text(d, (PAD + 54, rib_y + 48 + i * (size + 10)), ln, f, NAVY + (255,))

    # ── плитки: Місяць і Сонце ──
    ty, th = 612, 180
    tw = (W - 2 * PAD - 24) / 2
    for i in range(2):
        _panel(base, PAD + i * (tw + 24), ty, tw, th, (0, 0, 0, 96), radius=32, shadow=False)
    d = ImageDraw.Draw(base, "RGBA")
    moon = info["moon"]
    moon_ic = _moon_icon(moon["frac"], px(118))
    base.paste(moon_ic, (px(PAD + 26), px(ty + 34)), moon_ic)
    tx = PAD + 26 + 118 + 22
    f, size, lines = _fit(d, moon["name"], (30, 27, 24), True, tw - (tx - PAD) - 14, 2)
    yy = ty + 26
    for ln in lines:
        _text(d, (tx, yy), ln, f, WHITE)
        yy += size + 8
    ev = moon["event"]
    sub = f"о {ev['time']} · " if ev else ""
    _text(d, (tx, ty + th - 62), f"{sub}≈ {round(moon['illum'] * 100)}%", font(26), SOFT)
    _text(d, (tx, ty + th - 32), f"{moon['age']:.0f}-й день циклу", font(24), SOFT)

    sx = PAD + tw + 24
    sun = info["sun"]
    sun_ic = _sun_icon(px(116))
    base.paste(sun_ic, (px(sx + 22), px(ty + 36)), sun_ic)
    sx2 = sx + 22 + 116 + 18
    _text(d, (sx2, ty + 26), f"Схід  {sun['sunrise']}", font(31, True), WHITE)
    _text(d, (sx2, ty + 72), f"Захід {sun['sunset']}", font(31, True), WHITE)
    _text(d, (sx2, ty + 126), f"день {sun['day_len']}", font(24), SOFT)

    # ── список свят та подій ──
    ey, eh = 812, 292
    _panel(base, PAD, ey, W - 2 * PAD, eh, (255, 255, 255, 242))
    d = ImageDraw.Draw(base, "RGBA")
    legend = info.get("legend")
    legend_only = (not rest) and bool(legend)
    if legend and rest and len(rest) <= 2:          # мало подій — додаємо заголовок легенди, щоб панель не була порожня
        ltitle = legend[0]
        rest = rest + [("legend", ltitle if ltitle.lower().startswith("легенд") else f"Легенда дня: {ltitle}")]
    _text(d, (PAD + 38, ey + 22), "ЛЕГЕНДА ДНЯ" if legend_only else "СВЯТА Й ПОДІЇ", font(22, True), MUTED + (255,))
    tf = font(30)
    full_w = W - 2 * PAD - 76
    y0, limit = ey + 58, ey + eh - 18
    if legend_only:
        title, text = legend
        _marker(d, "legend", PAD + 38, y0)
        tfb = font(31, True)
        y = y0
        for ln in _clip(d, _wrap(d, title, tfb, full_w - 34), 2, tfb, full_w - 34):
            _text(d, (PAD + 38 + 34, y), ln, tfb, NAVY + (255,))
            y += 40
        ex = font(27)
        all_lines = _wrap(d, text, ex, full_w)
        lines = _clip(d, all_lines, 3, ex, full_w)
        for ln in lines:
            _text(d, (PAD + 38, y + 8), ln, ex, (58, 72, 98, 255))
            y += 36
        _text(d, (PAD + 38, ey + eh - 46), "Повна версія — у тексті поста ↓", font(25), MUTED + (255,))
    else:
        max_w = full_w - 34
        placed, y_end = _layout_items(d, rest, tf, max_w, y0, limit)
        for kind, lines, y in placed:
            _marker(d, kind, PAD + 38, y)
            for i, ln in enumerate(lines):
                _text(d, (PAD + 38 + 34, y + i * 38), ln, tf, NAVY + (255,))
        if len(placed) < len(rest):
            _text(d, (PAD + 38, y_end - 2), f"…і ще {len(rest) - len(placed)} — у тексті поста ↓",
                  font(26), MUTED + (255,))

    # ── народна прикмета ──
    py, ph = 1118, 160
    _panel(base, PAD, py, W - 2 * PAD, ph, (0, 0, 0, 100), radius=32, shadow=False)
    d = ImageDraw.Draw(base, "RGBA")
    _text(d, (PAD + 38, py + 18), "НАРОДНА ПРИКМЕТА", font(22, True), GOLD + (255,))
    f, size, lines = _fit(d, info["prykmeta"], (28, 26, 24), False, W - 2 * PAD - 76, 3)
    for i, ln in enumerate(lines):
        _text(d, (PAD + 38, py + 50 + i * (size + 7)), ln, f, WHITE)

    # ── підвал ──
    _text(d, (PAD, 1298), "t.me/sumskoy_sinoptik", font(32, True), WHITE)
    _text(d, (W - PAD, 1305), "Погода · календар · легенди", font(24), SOFT, anchor="ra")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    base.convert("RGB").resize((W, H), Image.LANCZOS).save(out_path, "PNG", optimize=True)
    return out_path


# ───────────────────────── запуск ─────────────────────────
def _demo_info() -> dict:
    return {"date": date(2026, 11, 7), "weekday": "Субота", "month_gen": "листопада",
            "state": [("День працівників соціальної сфери", None), ("Міжнародний день радіо", None)],
            "church": [("Собор архістратига Михаїла та інших безплотних сил", None)],
            "names": "Дмитро, Михайло, Ярослав, Олена, Тетяна",
            "legend": ("Легенда про сумську ярмарку", "…"),
            "prykmeta": "Якщо на Михайла випав перший сніг, зима буде снігова; якщо листя ще не облетіло, морози прийдуть пізно.",
            "moon": {"emoji": "🌘", "name": "Спадаючий серп (старий місяць)", "tag": "СтарийМісяць", "event": None,
                     "frac": 0.88, "age": 26.0, "illum": 0.14},
            "sun": {"sunrise": "07:12", "sunset": "16:34", "day_len": "9 год 22 хв"}, "tags": []}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Генератор картки «Щоденний календар»")
    ap.add_argument("--date", help="РРРР-ММ-ДД (за замовчуванням — сьогодні)")
    ap.add_argument("--out", default="output/card.png")
    ap.add_argument("--demo", action="store_true", help="тестові дані (не потребує shchodennyy_kalendar)")
    a = ap.parse_args()
    if a.demo:
        print("Збережено:", generate_card(_demo_info(), a.out))
    else:
        from shchodennyy_kalendar import build_day, TZ
        dd = date.fromisoformat(a.date) if a.date else datetime.now(TZ).date()
        print("Збережено:", generate_card(build_day(dd), a.out))
