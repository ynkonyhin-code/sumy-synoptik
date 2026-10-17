#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки «Хвилинка тепла від Сумського синоптика».
PNG 1600x1200 (4:3 — Telegram показує на всю ширину поста).
Палітра й прикраси залежать від сезону: осінь — листя, зима — сніжинки,
весна — квіти, літо — соняхи й сонце.

Локальний перегляд:  python khvylynka_tepla_card.py  ->  card_preview_<season>.png
"""
from __future__ import annotations

import math
import os
import random
import sys
import zlib

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200

SEASONS = {
    #            фон зверху         фон знизу          колір тексту     акцент
    "autumn": {"top": (255, 240, 214), "bot": (247, 196, 140), "text": (74, 40, 26), "accent": (196, 84, 36),
               "pal": [(214, 96, 40), (232, 140, 40), (190, 70, 40), (240, 180, 60), (160, 80, 30)]},
    "winter": {"top": (232, 242, 255), "bot": (176, 204, 240), "text": (30, 48, 86), "accent": (52, 100, 176),
               "pal": [(255, 255, 255), (214, 232, 255), (190, 214, 245)]},
    "spring": {"top": (238, 250, 228), "bot": (186, 226, 176), "text": (30, 70, 36), "accent": (60, 140, 70),
               "pal": [(255, 192, 214), (255, 255, 255), (255, 224, 120), (200, 170, 240)]},
    "summer": {"top": (255, 248, 210), "bot": (255, 212, 130), "text": (88, 52, 14), "accent": (214, 120, 20),
               "pal": [(255, 200, 40), (255, 170, 30), (250, 220, 80)]},
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


def season_of(month: int) -> str:
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(month, "autumn")


def _gradient(top, bot) -> Image.Image:
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return img


def _rot(pts, cx, cy, ang):
    c, s = math.cos(ang), math.sin(ang)
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in pts]


# ── Прикраси ───────────────────────────────────────────────────────────────
def _leaf(d, cx, cy, size, ang, color):
    n = 28
    left = [(-size * 0.55 * math.sin(math.pi * (i / n)) ** 0.85, -size + 2 * size * i / n) for i in range(n + 1)]
    right = [(-x, y) for x, y in reversed(left)]
    d.polygon(_rot(left + right, cx, cy, ang), fill=color)
    stem = _rot([(0, -size * 0.9), (0, size * 1.15)], cx, cy, ang)
    d.line(stem, fill=tuple(max(0, c - 40) for c in color), width=max(2, int(size / 14)))


def _snowflake(d, cx, cy, r, color):
    w = max(3, int(r / 14))
    for k in range(6):
        a = math.pi / 3 * k
        ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
        d.line([(cx, cy), (ex, ey)], fill=color, width=w)
        for f in (0.5, 0.75):
            bx, by = cx + r * f * math.cos(a), cy + r * f * math.sin(a)
            for sgn in (-1, 1):
                a2 = a + sgn * math.pi / 5
                d.line([(bx, by), (bx + r * 0.28 * math.cos(a2), by + r * 0.28 * math.sin(a2))], fill=color, width=w)


def _flower(d, cx, cy, r, color, center=(255, 214, 80)):
    for k in range(5):
        a = 2 * math.pi / 5 * k
        px, py = cx + r * 0.55 * math.cos(a), cy + r * 0.55 * math.sin(a)
        d.ellipse([px - r * 0.45, py - r * 0.45, px + r * 0.45, py + r * 0.45], fill=color)
    d.ellipse([cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3], fill=center)


def _sunflower(d, cx, cy, r, color):
    for k in range(14):
        a = 2 * math.pi / 14 * k
        pts = [(0, -r * 0.35), (r * 0.16, -r * 0.7), (0, -r), (-r * 0.16, -r * 0.7)]
        d.polygon(_rot(pts, cx, cy, a), fill=color)
    d.ellipse([cx - r * 0.38, cy - r * 0.38, cx + r * 0.38, cy + r * 0.38], fill=(112, 70, 30))


def _sun(img, cx, cy, r):
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for i in range(14, 0, -1):
        rr = r * (1 + i * 0.16)
        g.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 226, 120, 14))
    img.paste(Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB"))
    d = ImageDraw.Draw(img)
    for k in range(16):
        a = 2 * math.pi / 16 * k
        d.line([(cx + r * 1.25 * math.cos(a), cy + r * 1.25 * math.sin(a)),
                (cx + r * 1.7 * math.cos(a), cy + r * 1.7 * math.sin(a))], fill=(255, 196, 60), width=8)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 205, 70))
    d.ellipse([cx - r * 0.78, cy - r * 0.78, cx + r * 0.78, cy + r * 0.78], fill=(255, 224, 110))


def _decorate(img, season: str, seed: int) -> None:
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img)
    pal = SEASONS[season]["pal"]
    keep = [(90, 70, 860, 215), (100, 380, W - 100, 930), (90, H - 190, 760, H - 60)]   # зони тексту без прикрас
    placed = 0
    tries = 0
    while placed < 18 and tries < 400:
        tries += 1
        x, y = rnd.randint(30, W - 30), rnd.randint(30, H - 30)
        if any(k[0] - 40 < x < k[2] + 40 and k[1] - 40 < y < k[3] + 40 for k in keep):
            continue
        size = rnd.randint(34, 78)
        col = rnd.choice(pal)
        if season == "autumn":
            _leaf(d, x, y, size, rnd.uniform(0, 2 * math.pi), col)
        elif season == "winter":
            _snowflake(d, x, y, size, (255, 255, 255))
        elif season == "spring":
            _flower(d, x, y, size * 0.7, col)
        else:
            _sunflower(d, x, y, size * 0.8, col)
        placed += 1


def _wrap(d, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split(" "):
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


def render_card(data: dict, out_path: str = "card.png") -> str:
    """data: {"title", "label", "date_long", "season"(optional), "month"(optional)}"""
    season = data.get("season") or season_of(data.get("month", 10))
    st = SEASONS[season]
    img = _gradient(st["top"], st["bot"])
    if season == "summer":
        _sun(img, W - 190, 190, 80)
    _decorate(img, season, seed=zlib.crc32(data["title"].encode("utf-8")) % 100000)
    d = ImageDraw.Draw(img)
    pad = 120

    d.text((pad, 96), "ХВИЛИНКА ТЕПЛА", font=_font(40, True), fill=st["accent"])
    d.text((pad, 148), "від Сумського синоптика", font=_font(30), fill=st["text"])

    # Чип рубрики
    chip = data["label"]
    fc = _font(32, True)
    cw = d.textlength(chip, font=fc)
    d.rounded_rectangle([pad, 424, pad + cw + 56, 424 + 64], radius=32, fill=st["accent"])
    d.text((pad + 28, 424 + 13), chip, font=fc, fill=(255, 255, 255))

    # Заголовок: найбільший шрифт, що вміщається у 3 рядки
    max_w = W - 2 * pad
    for size in (96, 86, 76, 68, 60, 54):
        f = _font(size, True)
        lines = _wrap(d, data["title"], f, max_w)
        if len(lines) <= 3:
            break
    y = 534
    for ln in lines[:3]:
        d.text((pad, y), ln, font=f, fill=st["text"])
        y += int(size * 1.22)

    d.line([(pad, y + 22), (pad + 220, y + 22)], fill=st["accent"], width=8)

    d.text((pad, H - 150), data["date_long"], font=_font(30), fill=st["text"])
    d.text((pad, H - 100), "t.me/sumskoy_sinoptik", font=_font(34, True), fill=st["accent"])

    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    demo = {"title": "Суми народилися 1652 року", "label": "Факт про Суми та Сумщину",
            "date_long": "17 жовтня 2026"}
    for s, t in (("autumn", "Золоте світло осені"), ("winter", "Сніжинки й шість променів"),
                 ("spring", "Березень з водою"), ("summer", "Соняшник і сонце")):
        out = f"card_preview_{s}.png"
        render_card({**demo, "title": t, "season": s}, out)
        print("Збережено:", out)
