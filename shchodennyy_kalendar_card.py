# -*- coding: utf-8 -*-
"""
Генератор картки «Щоденний календар» (1080×1350, формат 4:5) для каналу «Сумський синоптик».

Використання як модуль:
    from shchodennyy_kalendar import build_day
    from shchodennyy_kalendar_card import generate_card
    generate_card(build_day(date.today()), "output/card.png")

Самостійний запуск:
    python shchodennyy_kalendar_card.py                    # картка на сьогодні
    python shchodennyy_kalendar_card.py --date 2026-12-25 --out xmas.png

Шрифт: шукається у ./fonts/ (покладіть туди DejaVuSans.ttf та DejaVuSans-Bold.ttf,
якщо хочете незалежності від системи), далі — у стандартних системних теках.
"""
from __future__ import annotations

import argparse
import math
import os
import re
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
SS = 3                                  # супер-семплінг для гладкого Місяця

# Градієнти за місяцями: (верх, низ) — пори року
PALETTES = {
    1: ((18, 32, 66), (52, 90, 140)),   2: ((26, 40, 80), (84, 120, 170)),
    3: ((38, 78, 98), (120, 170, 160)), 4: ((34, 94, 98), (140, 198, 150)),
    5: ((30, 100, 80), (170, 214, 130)), 6: ((20, 110, 120), (240, 200, 110)),
    7: ((16, 100, 130), (250, 190, 90)), 8: ((24, 90, 120), (245, 170, 85)),
    9: ((90, 70, 40), (230, 160, 70)),  10: ((84, 44, 34), (206, 120, 60)),
    11: ((50, 52, 70), (130, 130, 150)), 12: ((14, 26, 58), (60, 100, 150)),
}
MONTHS_NOM_GEN = ["СІЧНЯ", "ЛЮТОГО", "БЕРЕЗНЯ", "КВІТНЯ", "ТРАВНЯ", "ЧЕРВНЯ",
                  "ЛИПНЯ", "СЕРПНЯ", "ВЕРЕСНЯ", "ЖОВТНЯ", "ЛИСТОПАДА", "ГРУДНЯ"]

FONT_DIRS = ["fonts",
             "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
             "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype/noto",
             "/Library/Fonts", "/System/Library/Fonts/Supplemental",
             "C:/Windows/Fonts"]
REGULAR = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "Arial.ttf", "arial.ttf"]
BOLD = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    for folder in FONT_DIRS:
        for name in (BOLD if bold else REGULAR):
            p = os.path.join(folder, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    raise RuntimeError("Не знайдено шрифт із кирилицею. Покладіть DejaVuSans.ttf у теку fonts/.")


def _gradient(top, bottom) -> Image.Image:
    img = Image.new("RGB", (W, H), top)
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        px.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


_EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\uFE0F\u200d]+")


def _clean(text: str) -> str:
    """Шрифт не має емодзі — прибираємо їх лише з картки."""
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", text)).strip()


def _wrap(draw, text, font, max_w) -> list[str]:
    text = _clean(text)
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _moon_icon(frac: float, size: int) -> Image.Image:
    """Малює Місяць за часткою циклу (0=новий, 0.5=повня). Північна півкуля: молодий — справа."""
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = S / 2 - 4 * SS
    cx = cy = S / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(38, 46, 70, 255), outline=(255, 255, 255, 70), width=2 * SS)
    k = math.cos(2 * math.pi * frac)
    lit = (250, 244, 220, 255)
    for yi in range(int(cy - r), int(cy + r) + 1):
        dy = yi - cy
        if abs(dy) > r:
            continue
        w = math.sqrt(max(r * r - dy * dy, 0))
        if frac <= 0.5:                      # зростає: світла частина справа
            x0, x1 = cx + w * k, cx + w
        else:                                # спадає: світла частина зліва
            x0, x1 = cx - w, cx - w * k
        if x1 - x0 > 0.5:
            d.line([(x0, yi), (x1, yi)], fill=lit, width=1)
    return img.resize((size, size), Image.LANCZOS)


def generate_card(info: dict, out_path: str = "output/card.png") -> str:
    d: date = info["date"]
    top, bottom = PALETTES[d.month]
    img = _gradient(top, bottom).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # м'які декоративні кола
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([W - 520, -220, W + 160, 460], fill=(255, 255, 255, 26))
    g.ellipse([-260, H - 520, 360, H + 120], fill=(255, 255, 255, 20))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    white, soft = (255, 255, 255, 255), (255, 255, 255, 190)
    PAD = 70

    # Шапка
    draw.text((PAD, 62), "СУМСЬКИЙ СИНОПТИК", font=_font(True, 34), fill=white)
    draw.text((PAD, 108), "ЩОДЕННИЙ КАЛЕНДАР", font=_font(False, 26), fill=soft)
    draw.line([(PAD, 160), (W - PAD, 160)], fill=(255, 255, 255, 90), width=2)

    # Велике число + місяць
    day_font = _font(True, 330)
    draw.text((PAD - 10, 150), str(d.day), font=day_font, fill=white)
    num_w = draw.textlength(str(d.day), font=day_font)
    mx = PAD + num_w + 24
    draw.text((mx, 300), MONTHS_NOM_GEN[d.month - 1], font=_font(True, 54), fill=white)
    draw.text((mx, 372), info["weekday"].upper(), font=_font(False, 40), fill=soft)
    draw.text((mx, 424), str(d.year), font=_font(False, 34), fill=soft)

    # Панель з Місяцем і Сонцем
    panel_y = 520
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([PAD, panel_y, W - PAD, panel_y + 210], 36, fill=(0, 0, 0, 70))
    img = Image.alpha_composite(img, panel)
    draw = ImageDraw.Draw(img)

    moon = info["moon"]
    icon = _moon_icon(moon["frac"], 150)
    img.alpha_composite(icon, (PAD + 36, panel_y + 30))
    tx = PAD + 36 + 150 + 34
    moon_name = moon["name"]
    mf = _font(True, 34)
    for i, line in enumerate(_wrap(draw, moon_name, mf, W - PAD - tx - 30)[:2]):
        draw.text((tx, panel_y + 28 + i * 42), line, font=mf, fill=white)
    ev = moon["event"]
    sub = f"о {ev['time']} · " if ev else ""
    draw.text((tx, panel_y + 118), f"{sub}освітлено ≈ {round(moon['illum'] * 100)}%", font=_font(False, 28), fill=soft)
    sun = info["sun"]
    draw.text((tx, panel_y + 160), f"Схід {sun['sunrise']}  ·  Захід {sun['sunset']}", font=_font(False, 28), fill=soft)

    # Список подій
    y = panel_y + 210 + 50
    items = [("●", t) for t, _ in info["state"]] + [("✚", t) for t, _ in info["church"]]
    if info["names"]:
        items.append(("★", "Іменини: " + info["names"]))
    tf = _font(False, 36)
    max_w = W - 2 * PAD - 60
    bottom_limit = H - 230
    shown = 0
    for mark, text in items:
        lines = _wrap(draw, text, tf, max_w)
        need = len(lines) * 46 + 18
        if y + need > bottom_limit:
            break
        if mark == "●":
            draw.ellipse([PAD + 4, y + 14, PAD + 22, y + 32], fill=(255, 214, 102, 255))
        elif mark == "✚":
            draw.rectangle([PAD + 11, y + 10, PAD + 15, y + 36], fill=(255, 255, 255, 235))
            draw.rectangle([PAD + 1, y + 18, PAD + 25, y + 22], fill=(255, 255, 255, 235))
        else:
            draw.polygon([(PAD + 13, y + 8), (PAD + 18, y + 20), (PAD + 31, y + 20), (PAD + 21, y + 28),
                          (PAD + 25, y + 40), (PAD + 13, y + 32), (PAD + 1, y + 40), (PAD + 5, y + 28),
                          (PAD - 5, y + 20), (PAD + 8, y + 20)], fill=(255, 190, 220, 255))
        for ln in lines:
            draw.text((PAD + 60, y), ln, font=tf, fill=white)
            y += 46
        y += 18
        shown += 1
    if shown < len(items):
        draw.text((PAD + 60, y), f"…і ще {len(items) - shown} — у тексті поста ↓", font=_font(False, 30), fill=soft)
    if not items:
        draw.text((PAD, y), "Звичайний день для добрих справ 🌿".replace(" 🌿", ""), font=tf, fill=soft)

    # Підвал
    draw.line([(PAD, H - 150), (W - PAD, H - 150)], fill=(255, 255, 255, 90), width=2)
    draw.text((PAD, H - 120), "t.me/sumskoy_sinoptik", font=_font(True, 36), fill=white)
    draw.text((PAD, H - 72), "Погода · календар · легенди", font=_font(False, 28), fill=soft)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    from shchodennyy_kalendar import build_day, TZ

    ap = argparse.ArgumentParser(description="Генератор картки «Щоденний календар»")
    ap.add_argument("--date", help="РРРР-ММ-ДД (за замовчуванням — сьогодні)")
    ap.add_argument("--out", default="output/card.png")
    a = ap.parse_args()
    dd = date.fromisoformat(a.date) if a.date else datetime.now(TZ).date()
    print("Збережено:", generate_card(build_day(dd), a.out))
