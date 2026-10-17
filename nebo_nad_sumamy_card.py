#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки «Небо над Сумами» (канал «Сумський синоптик»).

Приймає словник `data` (його формує nebo_nad_sumamy.py) і зберігає PNG 1600x1200
(4:3 — Telegram показує на всю ширину поста). Диск Місяця малюється за реальною фазою.

Локальний перегляд:  python nebo_nad_sumamy_card.py  ->  card_preview.png
"""
from __future__ import annotations

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200
BG_TOP, BG_BOTTOM = (6, 10, 28), (24, 30, 62)
PANEL = (255, 255, 255, 18)
GOLD = (222, 184, 82)
TEXT = (244, 246, 250)
MUTED = (150, 162, 184)
LINE = (58, 68, 92)
GREEN, RED, BLUE = (92, 200, 140), (240, 110, 110), (110, 170, 240)
KIND_COLOR = {"cloud": BLUE, "iss": (240, 200, 90), "event": GOLD, "retro": (190, 160, 230),
              "shower": (255, 150, 90)}

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
    # кілька «зірок» для настрою (детерміновано)
    import random
    rnd = random.Random(7)
    for _ in range(140):
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.choice([1, 1, 1, 2])
        c = rnd.randint(110, 200)
        d.ellipse([x, y, x + r, y + r], fill=(c, c, min(255, c + 30)))
    return img


def _panel(img: Image.Image, box) -> None:
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, radius=28, fill=PANEL)
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
    """Диск Місяця за фазою. elong — елонгація, 0=новий, 90=1-ша чверть, 180=повня."""
    S = 3                                              # суперсемплінг для гладких країв
    size = (2 * r + 8) * S
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    c = size // 2
    R = r * S
    ld.ellipse([c - R, c - R, c + R, c + R], fill=(36, 42, 70, 255))          # темна частина
    psi = math.radians(elong_deg % 360)
    cos_p = math.cos(psi)
    lit = (238, 234, 214, 255)
    for y in range(-R, R + 1):
        w = math.sqrt(max(R * R - y * y, 0))
        if psi <= math.pi:                              # зростаючий: освітлено праворуч
            x0, x1 = w * cos_p, w
        else:                                           # спадаючий: освітлено ліворуч
            x0, x1 = -w, -w * cos_p
        if x1 > x0:
            ld.line([(c + x0, c + y), (c + x1, c + y)], fill=lit, width=1)
    # кілька «морів» для виразності (лише на освітленій частині)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([c - R, c - R, c + R, c + R], fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", (size, size), 0), mask))
    layer = layer.resize((size // S, size // S), Image.LANCZOS)
    # м'яке сяйво
    glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([0, 0, layer.size[0] - 1, layer.size[1] - 1], outline=(200, 205, 240, 60), width=3)
    layer = Image.alpha_composite(layer, glow)
    base = img.convert("RGBA")
    base.alpha_composite(layer, (cx - layer.size[0] // 2, cy - layer.size[1] // 2))
    img.paste(base.convert("RGB"))


def render_card(data: dict, out_path: str = "card.png") -> str:
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad, bottom = 64, H - 104

    # Шапка
    d.text((pad, 44), "СУМСЬКИЙ СИНОПТИК", font=_font(28, True), fill=GOLD)
    d.text((pad, 88), "Небо над Сумами", font=_font(58, True), fill=TEXT)
    _right(d, W - pad, 46, data["date_long"], _font(40, True), TEXT)
    _right(d, W - pad, 98, data["weekday"], _font(26), MUTED)
    d.line([(pad, 170), (W - pad, 170)], fill=GOLD, width=3)
    top = 198

    # ── Ліва колонка: Місяць і Сонце ──────────────────────────────────────
    lx1, lx2 = pad, pad + 640
    _panel(img, (lx1, top, lx2, bottom))
    m, s = data["moon"], data["sun"]
    draw_moon(img, lx1 + 320, top + 190, 130, m["elong"])
    d = ImageDraw.Draw(img)
    cx = lx1 + 320
    f = _font(42, True)
    d.text((cx - d.textlength(m["name"], font=f) / 2, top + 350), m["name"], font=f, fill=TEXT)
    sub = f"освітлено {m['illum']} % · вік {m['age']} доби"
    f2 = _font(26)
    d.text((cx - d.textlength(sub, font=f2) / 2, top + 408), sub, font=f2, fill=MUTED)

    y = top + 470
    rows = [("Місяць", f"схід {m['rise']}  ·  захід {m['set']}"),
            ("Сонце", f"схід {s['rise']}  ·  захід {s['set']}"),
            ("День", f"{s['length']} ({s['delta']})")]
    for label, val in rows:
        d.text((lx1 + 40, y), label, font=_font(28, True), fill=GOLD)
        _right(d, lx2 - 40, y, val, _font(28), TEXT)
        d.line([(lx1 + 40, y + 46), (lx2 - 40, y + 46)], fill=LINE, width=1)
        y += 62
    d.text((lx1 + 40, y + 6), "Найближчі фази Місяця", font=_font(24, True), fill=MUTED)
    y += 46
    for ph in data.get("phases", [])[:2]:
        d.text((lx1 + 40, y), ph, font=_font(26), fill=TEXT)
        y += 38

    # ── Права колонка ─────────────────────────────────────────────────────
    rx1, rx2 = lx2 + 32, W - pad
    a_bottom = top + 470
    _panel(img, (rx1, top, rx2, a_bottom))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 36, top + 24), "Що видно без телескопа", font=_font(34, True), fill=GOLD)
    yy = top + 84
    windows = data.get("windows", [])
    if not any(w["planets"] for w in windows):
        d.text((rx1 + 36, yy + 20), "Яскравих планет над горизонтом немає", font=_font(32, True), fill=TEXT)
    for wnd in windows:
        if not wnd["planets"]:
            continue
        d.text((rx1 + 36, yy), wnd["label"], font=_font(24, True), fill=MUTED)
        yy += 36
        for p in wnd["planets"][:4]:
            if yy > a_bottom - 56:
                break
            d.ellipse([rx1 + 38, yy + 8, rx1 + 38 + 26, yy + 8 + 26], fill=tuple(p["color"]))
            d.text((rx1 + 84, yy), p["name"], font=_font(32, True), fill=TEXT)
            d.text((rx1 + 84 + d.textlength(p["name"], font=_font(32, True)) + 14, yy + 8),
                   f"{p['mag']} зв. вел.", font=_font(21), fill=MUTED)
            _right(d, rx2 - 36, yy, f"{p['dir']}, {p['alt']}°", _font(30, True), TEXT)
            yy += 50
        yy += 10

    b_top = a_bottom + 24
    _panel(img, (rx1, b_top, rx2, bottom))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 36, b_top + 22), "Умови та події", font=_font(34, True), fill=GOLD)
    yy = b_top + 80
    for ex in data.get("extras", []):
        ft = _font(26)
        lines = _wrap(d, ex["text"], ft, rx2 - rx1 - 36 - 36 - 36)
        need = 36 * len(lines) + 12
        if yy + need > bottom - 14:
            break
        d.ellipse([rx1 + 36, yy + 9, rx1 + 36 + 16, yy + 9 + 16], fill=KIND_COLOR.get(ex["kind"], GOLD))
        for ln in lines:
            d.text((rx1 + 72, yy), ln, font=ft, fill=TEXT)
            yy += 36
        yy += 12

    d.text((pad, H - 72), "t.me/sumskoy_sinoptik", font=_font(30, True), fill=GOLD)
    _right(d, W - pad, H - 78, "Розрахунок для Сум: 50,91° пн. ш., 34,80° сх. д.", _font(23), MUTED)
    _right(d, W - pad, H - 46, "Час — київський · напрямки й висота — для спостерігача в Сумах", _font(20), MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    demo = {
        "date_long": "17 жовтня 2026", "weekday": "субота",
        "moon": {"name": "Зростаючий Місяць", "illum": 40, "age": "7,6", "elong": 79,
                 "rise": "13:21", "set": "22:08"},
        "sun": {"rise": "07:07", "set": "17:44", "length": "10 г 37 хв", "delta": "−3 хв до вчора"},
        "phases": ["Перша чверть · 18 жовтня о 06:12", "Повня · 26 жовтня о 07:11"],
        "windows": [
            {"label": "Сьогодні ввечері, о 19:15", "planets": [
                {"name": "Сатурн", "mag": "+0,8", "dir": "південь", "alt": 38, "color": [215, 195, 120]},
                {"name": "Юпітер", "mag": "−2,0", "dir": "схід", "alt": 22, "color": [225, 190, 140]}]},
            {"label": "Завтра вранці, о 05:37", "planets": [
                {"name": "Венера", "mag": "−4,0", "dir": "схід", "alt": 18, "color": [240, 225, 170]}]},
        ],
        "extras": [
            {"kind": "cloud", "text": "Хмарність увечері: близько 20 % — ясно, добрі умови для спостережень"},
            {"kind": "shower", "text": "Оріоніди: пік близько 22 жовтня, до 20 метеорів на годину"},
            {"kind": "iss", "text": "МКС: 19:12, максимум 64° на південному заході, видно ≈ 4 хв"},
        ],
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "card_preview.png"
    print("Збережено:", render_card(demo, out))
