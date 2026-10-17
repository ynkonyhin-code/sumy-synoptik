#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки «Гороскоп дня» (канал «Сумський синоптик»).
PNG 1600x1200 (4:3): шапка з Місяцем + 12 плиток знаків + народна прикмета дня.

Локальний перегляд:  python horoskop_dnia_card.py  ->  card_preview.png
"""
from __future__ import annotations

import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200
BG_TOP, BG_BOTTOM = (14, 8, 34), (38, 24, 66)
PANEL = (255, 255, 255, 18)
GOLD = (222, 184, 82)
TEXT = (244, 246, 250)
MUTED = (160, 152, 190)
LABEL_COLOR = {
    "conjunction": (240, 200, 90), "sextile": (110, 175, 240), "square": (240, 150, 90),
    "trine": (100, 205, 140), "opposition": (190, 150, 235), "quiet": (170, 175, 195),
}

_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
         "/usr/share/fonts/truetype/liberation", "/Library/Fonts", "C:\\Windows\\Fonts"]
_REG = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "arial.ttf"]
_BLD = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    env = os.getenv("CARD_FONT_BOLD" if bold else "CARD_FONT")
    cands = [env] if env else []
    for d in _DIRS:
        cands += [os.path.join(d, n) for n in (_BLD if bold else _REG)]
    for p in cands:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise RuntimeError("Не знайдено шрифт з кирилицею (fonts-dejavu-core або CARD_FONT).")


def _gradient() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    rnd = random.Random(11)
    for _ in range(130):
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.choice([1, 1, 1, 2])
        c = rnd.randint(110, 200)
        d.ellipse([x, y, x + r, y + r], fill=(c, c, min(255, c + 30)))
    return img


def _panel(img: Image.Image, box, radius: int = 28, fill=PANEL) -> None:
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, radius=radius, fill=fill)
    img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"))


def _right(d, x, y, text, font, fill) -> float:
    w = d.textlength(text, font=font)
    d.text((x - w, y), text, font=font, fill=fill)
    return w


def _wrap(d, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_moon(img: Image.Image, cx: int, cy: int, r: int, elong_deg: float) -> None:
    S = 3
    size = (2 * r + 8) * S
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    c, R = size // 2, r * S
    ld.ellipse([c - R, c - R, c + R, c + R], fill=(40, 40, 76, 255))
    psi = math.radians(elong_deg % 360)
    cos_p = math.cos(psi)
    for y in range(-R, R + 1):
        w = math.sqrt(max(R * R - y * y, 0))
        x0, x1 = (w * cos_p, w) if psi <= math.pi else (-w, -w * cos_p)
        if x1 > x0:
            ld.line([(c + x0, c + y), (c + x1, c + y)], fill=(238, 234, 214, 255), width=1)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([c - R, c - R, c + R, c + R], fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", (size, size), 0), mask))
    layer = layer.resize((size // S, size // S), Image.LANCZOS)
    base = img.convert("RGBA")
    base.alpha_composite(layer, (cx - layer.size[0] // 2, cy - layer.size[1] // 2))
    img.paste(base.convert("RGB"))


def render_card(data: dict, out_path: str = "card.png") -> str:
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad, bottom = 64, H - 104

    d.text((pad, 44), "СУМСЬКИЙ СИНОПТИК", font=_font(28, True), fill=GOLD)
    d.text((pad, 88), "Гороскоп на сьогодні", font=_font(58, True), fill=TEXT)
    _right(d, W - pad, 46, data["date_long"], _font(40, True), TEXT)
    _right(d, W - pad, 98, f"{data['weekday']} · розважальний формат", _font(26), MUTED)
    d.line([(pad, 170), (W - pad, 170)], fill=GOLD, width=3)

    # ── Смуга Місяця ──────────────────────────────────────────────────────
    top = 194
    _panel(img, (pad, top, W - pad, top + 196))
    m = data["moon"]
    draw_moon(img, pad + 110, top + 98, 70, m["elong"])
    d = ImageDraw.Draw(img)
    tx = pad + 222
    d.text((tx, top + 24), f"Місяць {m['sign_loc']}", font=_font(46, True), fill=TEXT)
    d.text((tx, top + 84), f"{m['name']} · освітлено {m['illum']} %", font=_font(28), fill=GOLD)
    for i, ln in enumerate(_wrap(d, m["theme"], _font(26), 800)[:2]):
        d.text((tx, top + 126 + i * 34), ln, font=_font(26), fill=MUTED)
    rx = W - pad - 36
    _right(d, rx, top + 34, f"Сонце у знаку: {data['sun_sign']}", _font(28, True), TEXT)
    if data.get("retro"):
        txt = "Меркурій ↺ зворотний рух"
        f = _font(24, True)
        w = d.textlength(txt, font=f)
        d.rounded_rectangle([rx - w - 36, top + 92, rx, top + 140], radius=24, fill=(120, 90, 190))
        d.text((rx - w - 18, top + 102), txt, font=f, fill=TEXT)

    # ── Сітка знаків ──────────────────────────────────────────────────────
    gy = top + 196 + 18
    gap = 16
    tw = (W - 2 * pad - 3 * gap) // 4
    th = 176
    for i, s in enumerate(data["signs"]):
        r_, c_ = divmod(i, 4)
        x1, y1 = pad + c_ * (tw + gap), gy + r_ * (th + gap)
        _panel(img, (x1, y1, x1 + tw, y1 + th), radius=24)
        d = ImageDraw.Draw(img)
        col = LABEL_COLOR.get(s["aspect"], GOLD)
        if s.get("is_sun"):
            d.rounded_rectangle([x1, y1, x1 + tw, y1 + th], radius=24, outline=GOLD, width=3)
            _right(d, x1 + tw - 18, y1 + 142, "☀ сезон", _font(22, True), GOLD)
        d.text((x1 + 22, y1 + 10), s["symbol"], font=_font(54, True), fill=col)
        d.text((x1 + 92, y1 + 16), s["name"], font=_font(34, True), fill=TEXT)
        d.text((x1 + 92, y1 + 58), s["dates"], font=_font(20), fill=MUTED)
        d.text((x1 + 22, y1 + 98), s["label"], font=_font(26, True), fill=col)
        for k in range(5):                       # «настрій дня»
            cx = x1 + 30 + k * 30
            d.ellipse([cx - 9, y1 + 150, cx + 9, y1 + 168],
                      fill=col if k < s["score"] else (70, 64, 100))

    # ── Народна прикмета ──────────────────────────────────────────────────
    fy = gy + 3 * (th + gap) - gap + 18
    _panel(img, (pad, fy, W - pad, bottom))
    d = ImageDraw.Draw(img)
    d.text((pad + 32, fy + 14), "Народна прикмета дня", font=_font(24, True), fill=GOLD)
    f = _font(27)
    for i, ln in enumerate(_wrap(d, data["folk"], f, W - 2 * pad - 64)[:2]):
        d.text((pad + 32, fy + 48 + i * 34), ln, font=f, fill=TEXT)

    d.text((pad, H - 72), "t.me/sumskoy_sinoptik", font=_font(30, True), fill=GOLD)
    _right(d, W - pad, H - 78, "Гороскоп — жарт для настрою, а не прогноз долі", _font(23), MUTED)
    _right(d, W - pad, H - 46, "Знаки зодіаку ≠ сузір’я · Місяць — за астрономічними розрахунками", _font(20), MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    from itertools import cycle
    asp = cycle(["trine", "sextile", "quiet", "square", "conjunction", "opposition"])
    labels = {"conjunction": "у центрі уваги", "sextile": "нагоди поруч", "square": "потрібна гнучкість",
              "trine": "усе складається", "opposition": "дзеркальний день", "quiet": "спокійний день"}
    score = {"conjunction": 4, "sextile": 4, "square": 3, "trine": 5, "opposition": 3, "quiet": 3}
    names = [("♈", "Овен", "21.03–19.04"), ("♉", "Телець", "20.04–20.05"), ("♊", "Близнюки", "21.05–20.06"),
             ("♋", "Рак", "21.06–22.07"), ("♌", "Лев", "23.07–22.08"), ("♍", "Діва", "23.08–22.09"),
             ("♎", "Терези", "23.09–22.10"), ("♏", "Скорпіон", "23.10–21.11"), ("♐", "Стрілець", "22.11–21.12"),
             ("♑", "Козеріг", "22.12–19.01"), ("♒", "Водолій", "20.01–18.02"), ("♓", "Риби", "19.02–20.03")]
    signs = []
    for i, (sy, nm, dt) in enumerate(names):
        a = next(asp)
        signs.append({"symbol": sy, "name": nm, "dates": dt, "aspect": a, "label": labels[a],
                      "score": score[a], "is_sun": nm == "Терези"})
    demo = {
        "date_long": "17 жовтня 2026", "weekday": "субота", "sun_sign": "Терези", "retro": True,
        "moon": {"sign_loc": "у Козерозі", "name": "Зростаючий серп", "illum": 41, "elong": 79,
                 "theme": "Місяць у Козерозі: день дисципліни, відповідальності та практичних рішень."},
        "signs": signs,
        "folk": "Ореол навколо Місяця — до зміни погоди. І справді: коло дають крижані кристали у високих "
                "перистих хмарах, що часто йдуть перед теплим фронтом.",
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "card_preview.png"
    print("Збережено:", render_card(demo, out))
