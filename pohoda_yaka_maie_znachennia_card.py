#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки «Погода, яка має значення» (канал «Сумський синоптик»).
PNG 1600x1200 (4:3 — Telegram показує на всю ширину поста).

Статуси практичних порад показані значками БЕЗ зелених/жовтих/червоних кружків, щоб
їх не плутали зі статусами повітряної тривоги: ✓ спокійно, ! зверніть увагу, !! обережно.

Локальний перегляд:  python pohoda_yaka_maie_znachennia_card.py -> card_preview.png
"""
from __future__ import annotations

import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200
BG_TOP, BG_BOTTOM = (10, 20, 44), (26, 44, 80)
PANEL = (255, 255, 255, 20)
ACCENT = (126, 204, 255)
TEXT = (244, 247, 252)
MUTED = (150, 168, 196)
LINE = (54, 72, 106)
CLOUD = (226, 235, 248)
SUN = (255, 207, 84)
CHIP = {0: (96, 196, 182), 1: (240, 190, 96), 2: (240, 122, 112)}
VERDICT = {"ok": ((110, 210, 178), "є наукове пояснення"),
           "partly": ((236, 200, 120), "частково збігається"),
           "no": ((160, 176, 204), "скоріше традиція, ніж наука")}

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


def fmt_temp(x: float) -> str:
    v = round(x)
    if v == 0:
        return "0°"
    return f"{'+' if v > 0 else '−'}{abs(v)}°"


def _gradient() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    rnd = random.Random(21)
    for _ in range(90):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        c = rnd.randint(90, 170)
        d.ellipse([x, y, x + 2, y + 2], fill=(c, c, min(255, c + 40)))
    return img


def _panel(img: Image.Image, box, radius: int = 28) -> None:
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, radius=radius, fill=PANEL)
    img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"))


def _right(d, x, y, text, font, fill) -> float:
    w = d.textlength(text, font=font)
    d.text((x - w, y), text, font=font, fill=fill)
    return w


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


# ── Значки погоди ──────────────────────────────────────────────────────────
def _cloud(d, cx, cy, s, color=CLOUD):
    d.ellipse([cx - s * 0.55, cy - s * 0.12, cx - s * 0.05, cy + s * 0.38], fill=color)
    d.ellipse([cx - s * 0.30, cy - s * 0.42, cx + s * 0.28, cy + s * 0.20], fill=color)
    d.ellipse([cx + s * 0.05, cy - s * 0.18, cx + s * 0.58, cy + s * 0.38], fill=color)
    d.rounded_rectangle([cx - s * 0.50, cy + s * 0.05, cx + s * 0.52, cy + s * 0.38], radius=int(s * 0.17), fill=color)


def _sun(d, cx, cy, s):
    r = s * 0.26
    for k in range(8):
        a = math.pi / 4 * k
        d.line([(cx + r * 1.4 * math.cos(a), cy + r * 1.4 * math.sin(a)),
                (cx + r * 1.95 * math.cos(a), cy + r * 1.95 * math.sin(a))], fill=SUN, width=max(3, int(s / 20)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=SUN)


def _moon(img, cx, cy, s):
    size = int(s * 1.2)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    r = s * 0.40
    c = size / 2
    ld.ellipse([c - r, c - r, c + r, c + r], fill=(246, 240, 214, 255))
    ld.ellipse([c - r * 0.45, c - r * 1.15, c + r * 1.45, c + r * 0.85], fill=(0, 0, 0, 0))
    base = img.convert("RGBA")
    base.alpha_composite(layer, (int(cx - size / 2), int(cy - size / 2)))
    img.paste(base.convert("RGB"))


def draw_icon(img, kind: str, cx: int, cy: int, s: int, night: bool = False) -> None:
    d = ImageDraw.Draw(img)
    if kind == "clear":
        if night:
            _moon(img, cx, cy, s)
        else:
            _sun(d, cx, cy, s)
    elif kind == "partly":
        if night:
            _moon(img, cx - s * 0.18, cy - s * 0.18, s * 0.9)
        else:
            _sun(d, cx - s * 0.18, cy - s * 0.2, s * 0.85)
        d = ImageDraw.Draw(img)
        _cloud(d, cx + s * 0.1, cy + s * 0.12, s * 0.85)
    elif kind == "cloudy":
        _cloud(d, cx, cy, s)
    elif kind == "fog":
        _cloud(d, cx, cy - s * 0.12, s * 0.8, (190, 204, 224))
        for i in range(3):
            y = cy + s * (0.28 + 0.14 * i)
            d.line([(cx - s * 0.5, y), (cx + s * 0.5, y)], fill=(170, 188, 214), width=max(4, int(s / 16)))
    elif kind in ("drizzle", "rain"):
        _cloud(d, cx, cy - s * 0.12, s * 0.9, (196, 210, 232))
        n = 3 if kind == "drizzle" else 4
        for i in range(n):
            x = cx - s * 0.36 + i * s * 0.24
            d.line([(x, cy + s * 0.34), (x - s * 0.08, cy + s * 0.58)], fill=(110, 178, 250), width=max(4, int(s / 18)))
    elif kind == "snow":
        _cloud(d, cx, cy - s * 0.12, s * 0.9, (206, 218, 238))
        for i in range(3):
            x = cx - s * 0.3 + i * s * 0.3
            for a in range(3):
                ang = math.pi / 3 * a
                d.line([(x - s * 0.09 * math.cos(ang), cy + s * 0.46 - s * 0.09 * math.sin(ang)),
                        (x + s * 0.09 * math.cos(ang), cy + s * 0.46 + s * 0.09 * math.sin(ang))],
                       fill=(255, 255, 255), width=3)
    elif kind == "thunder":
        _cloud(d, cx, cy - s * 0.14, s * 0.9, (160, 176, 204))
        d.polygon([(cx + s * 0.02, cy + s * 0.18), (cx - s * 0.16, cy + s * 0.5), (cx - s * 0.02, cy + s * 0.5),
                   (cx - s * 0.12, cy + s * 0.78), (cx + s * 0.2, cy + s * 0.38), (cx + s * 0.04, cy + s * 0.38)], fill=SUN)
    else:
        _cloud(d, cx, cy, s)


def _chip(d, x, y, size, level: int):
    col = CHIP[level]
    d.rounded_rectangle([x, y, x + size, y + size], radius=16, fill=col)
    k, dark = size, (18, 30, 56)
    if level == 0:                                        # галочка
        d.line([(x + k * 0.24, y + k * 0.54), (x + k * 0.44, y + k * 0.72), (x + k * 0.78, y + k * 0.3)],
               fill=dark, width=8, joint="curve")
    else:                                                 # знак оклику (один чи два)
        xs = [0.5] if level == 1 else [0.36, 0.64]
        for fx in xs:
            cx = x + k * fx
            d.line([(cx, y + k * 0.2), (cx, y + k * 0.58)], fill=dark, width=8)
            d.ellipse([cx - 5, y + k * 0.7 - 5, cx + 5, y + k * 0.7 + 5], fill=dark)


# ── Основна функція ────────────────────────────────────────────────────────
def render_card(data: dict, out_path: str = "card.png") -> str:
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad, bottom = 64, H - 104

    d.text((pad, 44), "СУМСЬКИЙ СИНОПТИК", font=_font(28, True), fill=ACCENT)
    d.text((pad, 88), "Погода, яка має значення", font=_font(58, True), fill=TEXT)
    _right(d, W - pad, 46, f"Завтра · {data['weekday']}", _font(38, True), TEXT)
    _right(d, W - pad, 98, data["date_long"], _font(26), MUTED)
    d.line([(pad, 170), (W - pad, 170)], fill=ACCENT, width=3)
    top = 198

    # ── Ліва панель: ранок / день / вечір + народний синоптик ─────────────
    lx1, lx2 = pad, pad + 726
    _panel(img, (lx1, top, lx2, bottom))
    d = ImageDraw.Draw(img)
    d.text((lx1 + 36, top + 22), "Завтра в Сумах", font=_font(34, True), fill=ACCENT)
    d.text((lx1 + 36, top + 68), "температура · як відчувається", font=_font(22), fill=MUTED)
    ry = top + 112
    row_h = 176
    for i, p in enumerate(data["periods"]):
        y0 = ry + i * row_h
        if i:
            d.line([(lx1 + 36, y0), (lx2 - 36, y0)], fill=LINE, width=1)
        draw_icon(img, p["icon"], lx1 + 36 + 62, y0 + row_h // 2, 112, night=p.get("night", False))
        d = ImageDraw.Draw(img)
        d.text((lx1 + 190, y0 + 28), p["label"], font=_font(38, True), fill=TEXT)
        d.text((lx1 + 190, y0 + 80), p["hours"], font=_font(22), fill=MUTED)
        pop = p["pop"]
        d.text((lx1 + 190, y0 + 112), "без опадів" if pop < 20 else f"опади: {pop} %", font=_font(22),
               fill=MUTED if pop < 20 else ACCENT)
        _right(d, lx2 - 36, y0 + 20, fmt_temp(p["temp"]), _font(76, True), TEXT)
        _right(d, lx2 - 36, y0 + 112, f"відчувається {fmt_temp(p['feels'])}", _font(22), MUTED)

    fy = ry + 3 * row_h + 6
    d.line([(lx1 + 36, fy), (lx2 - 36, fy)], fill=LINE, width=1)
    folk = data["folk"]
    d.text((lx1 + 36, fy + 14), "Народний синоптик", font=_font(24, True), fill=ACCENT)
    col, vtxt = VERDICT[folk["verdict"]]
    f = _font(21, True)
    vw = d.textlength(vtxt, font=f)
    d.ellipse([lx2 - 36 - vw - 28, fy + 20, lx2 - 36 - vw - 10, fy + 38], fill=col)
    d.text((lx2 - 36 - vw, fy + 17), vtxt, font=f, fill=col)
    fs = _font(24)
    for j, ln in enumerate(_wrap(d, "«" + folk["sign"] + "»", fs, lx2 - lx1 - 72)[:3]):
        d.text((lx1 + 36, fy + 54 + j * 32), ln, font=fs, fill=TEXT)

    # ── Права панель: практично ───────────────────────────────────────────
    rx1, rx2 = lx2 + 28, W - pad
    a_bot = top + 600
    _panel(img, (rx1, top, rx2, a_bot))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 36, top + 22), "Практично", font=_font(34, True), fill=ACCENT)
    y = top + 76
    for it in data["practical"]:
        _chip(d, rx1 + 36, y + 8, 68, it["level"])
        d.text((rx1 + 128, y + 6), it["title"], font=_font(32, True), fill=TEXT)
        f = _font(26, True)
        txt = it["answer"]
        while d.textlength(txt, font=f) > rx2 - rx1 - 128 - 36 - 190 and len(txt) > 6:
            f = _font(f.size - 1, True)
        _right(d, rx2 - 36, y + 14, txt, f, CHIP[it["level"]] if it["level"] else TEXT)
        if it.get("hint"):
            _right(d, rx2 - 36, y + 50, it["hint"], _font(20), MUTED)
        y += 100

    # ── Права нижня панель: найкращий час ─────────────────────────────────
    b_top = a_bot + 22
    _panel(img, (rx1, b_top, rx2, bottom))
    d = ImageDraw.Draw(img)
    walk = data["walk"]
    d.text((rx1 + 36, b_top + 18), "Найкраще вийти", font=_font(30, True), fill=ACCENT)
    d.text((rx1 + 36, b_top + 56), walk["window"], font=_font(58, True), fill=TEXT)
    d.text((rx1 + 36, b_top + 128), walk["reason"], font=_font(23), fill=MUTED)
    bx1, bx2, by = rx1 + 36, rx2 - 36, b_top + 172
    hours = walk["hours"]
    n = len(hours)
    cw = (bx2 - bx1) / n
    for k, (h, sc) in enumerate(hours):
        c = tuple(int(a + (b - a) * sc) for a, b in zip((72, 88, 128), (110, 218, 190)))
        d.rectangle([bx1 + k * cw, by, bx1 + (k + 1) * cw - 2, by + 34], fill=c)
        if h % 3 == 0:
            d.text((bx1 + k * cw, by + 40), f"{h:02d}", font=_font(19), fill=MUTED)
    ws, we = walk["start"], walk["end"]
    hs = [h for h, _ in hours]
    if ws in hs:
        i0 = hs.index(ws)
        i1 = hs.index(we - 1) + 1 if (we - 1) in hs else n
        d.rounded_rectangle([bx1 + i0 * cw - 3, by - 5, bx1 + i1 * cw + 1, by + 39], radius=8, outline=TEXT, width=4)

    d.text((pad, H - 72), "t.me/sumskoy_sinoptik", font=_font(30, True), fill=ACCENT)
    _right(d, W - pad, H - 78, "Прогнозна модель Open-Meteo · не офіційне попередження", _font(23), MUTED)
    _right(d, W - pad, H - 46, "Приказки — традиція, а не прогноз", _font(20), MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    demo = {
        "date_long": "18 жовтня 2026", "weekday": "неділя",
        "periods": [
            {"label": "Ранок", "hours": "06–11", "temp": 4, "feels": 2, "icon": "fog", "pop": 5},
            {"label": "День", "hours": "11–18", "temp": 12, "feels": 11, "icon": "partly", "pop": 10},
            {"label": "Вечір", "hours": "18–23", "temp": 7, "feels": 5, "icon": "clear", "pop": 0, "night": True}],
        "practical": [
            {"title": "Шапка?", "answer": "до 10:00 — за бажанням", "level": 0},
            {"title": "Парасолька?", "answer": "не потрібна", "level": 0},
            {"title": "Слизько?", "answer": "можливий іній", "level": 1},
            {"title": "Туман?", "answer": "між 06:00 і 08:00", "level": 1},
            {"title": "Вітер?", "answer": "слабкий", "level": 0, "hint": "пориви до 7 м/с"}],
        "walk": {"window": "12:00–15:00", "reason": "найтепліше, сухо й безвітряно",
                 "hours": [(h, max(0, min(1, 1 - abs(h - 13.5) / 8))) for h in range(6, 24)], "start": 12, "end": 15},
        "folk": {"sign": "Якщо листя летить у двір — осінь поспішає. Якщо летить рахунок за опалення — зима вже не жартує!",
                 "verdict": "ok"},
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "card_preview.png"
    print("Збережено:", render_card(demo, out))
