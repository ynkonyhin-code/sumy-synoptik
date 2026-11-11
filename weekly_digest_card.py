#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Картка «Підсумок тижня» для каналу «Сумський синоптик» (1080×1350, 4:5).

Два блоки:
  1. «Виходило за розкладом» — скільки днів тижня вийшла кожна рубрика (N/7).
  2. «Події» — тривоги, вода, світло, газ, ДСНС, магнітні бурі.
Плюс погода за журналом, якщо вона є.

Використання як модуль:
    from weekly_digest_card import render_card
    render_card(data, "output/digest.png")

Самостійно (демо-дані, без інтернету):
    python weekly_digest_card.py --demo
"""
from __future__ import annotations

import argparse
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
S = 2

BG_TOP = (14, 26, 46)
BG_BOTTOM = (44, 62, 96)
PANEL = (255, 255, 255, 22)
GOLD = (232, 190, 90)
TEXT = (243, 246, 251)
MUTED = (168, 180, 200)
GREEN = (92, 205, 140)
AMBER = (238, 190, 80)
RED = (238, 108, 104)

HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_CANDIDATES = [
    os.path.join(HERE, "DejaVuSans.ttf"),
    os.path.join(HERE, "fonts", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_FONT_BOLD_CANDIDATES = [
    os.path.join(HERE, "DejaVuSans-Bold.ttf"),
    os.path.join(HERE, "fonts", "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in (_FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES):
        if os.path.exists(path):
            return ImageFont.truetype(path, size * S)
    raise RuntimeError("Не знайдено шрифт з кирилицею (DejaVuSans). "
                       "Поставте DejaVuSans.ttf і DejaVuSans-Bold.ttf у корінь репозиторію.")


def _gradient() -> Image.Image:
    img = Image.new("RGB", (W * S, H * S), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H * S):
        t = y / (H * S - 1)
        d.line([(0, y), (W * S, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    return img


def _panel(img: Image.Image, box) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle([v * S for v in box], radius=24 * S, fill=PANEL)
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _t(d, xy, text, font, fill=TEXT, max_w: float | None = None):
    if max_w:
        text = _ellipsize(d, text, font, max_w * S)
    d.text((xy[0] * S, xy[1] * S), text, font=font, fill=fill)


def _ellipsize(d, text: str, font, max_w: float) -> str:
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _right(d, x, y, text, font, fill=TEXT):
    w = d.textlength(text, font=font)
    d.text((x * S - w, y * S), text, font=font, fill=fill)


def _pill(d, x, y, text, font, fill, bg):
    w = d.textlength(text, font=font)
    h = font.size / S + 12
    d.rounded_rectangle([x * S, y * S, x * S + w + 26 * S, y * S + h * S],
                        radius=h * S / 2, fill=bg)
    d.text((x * S + 13 * S, y * S + 4 * S), text, font=font, fill=fill)
    return (w + 26 * S) / S


def render_card(data: dict, out_path: str = "digest.png") -> str:
    """data: {period, days, rows:[{title, days, total, pct}], events:[{title,value}], weather:[str]}"""
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad = 56

    # ── шапка ────────────────────────────────────────────────────────────
    _t(d, (pad, 44), "СУМСЬКИЙ СИНОПТИК", _font(24, True), GOLD)
    _t(d, (pad, 84), "ПІДСУМОК ТИЖНЯ", _font(58, True))
    _t(d, (pad, 158), data.get("period", ""), _font(30), MUTED)
    d.line([(pad * S, 214 * S), ((W - pad) * S, 214 * S)], fill=GOLD, width=3 * S)

    y = 246
    # ── виходило за розкладом ────────────────────────────────────────────
    rows = data.get("rows", [])
    total_days = data.get("days", 7)
    height = 92 + max(len(rows), 1) * 44
    _panel(img, (pad, y, W - pad, y + height))
    d = ImageDraw.Draw(img)
    _t(d, (pad + 28, y + 20), "ВИХОДИЛО ЗА РОЗКЛАДОМ", _font(22, True), GOLD)
    _right(d, W - pad - 28, y + 22, f"днів тижня: {total_days}", _font(20), MUTED)
    ry = y + 62
    if not rows:
        _t(d, (pad + 28, ry), "Журнал публікацій порожній", _font(24), MUTED)
    for r in rows:
        pct = r["days"] / max(total_days, 1)
        col = GREEN if pct >= 0.99 else (AMBER if pct >= 0.7 else RED)
        mark = "●" if pct >= 0.99 else ("◐" if pct >= 0.7 else "○")
        _t(d, (pad + 28, ry), mark, _font(24, True), col)
        _t(d, (pad + 66, ry + 2), r["title"], _font(24), max_w=W - pad - 190 - (pad + 66))
        _right(d, W - pad - 30, ry + 2, f"{r['days']}/{total_days}", _font(24, True), col)
        ry += 44
    y += height + 18

    # ── події ────────────────────────────────────────────────────────────
    events = data.get("events", [])
    if events:
        per_row = 2
        h_rows = (len(events) + per_row - 1) // per_row
        eh = 76 + h_rows * 62
        _panel(img, (pad, y, W - pad, y + eh))
        d = ImageDraw.Draw(img)
        _t(d, (pad + 28, y + 20), "ПОДІЇ ТИЖНЯ", _font(22, True), GOLD)
        col_w = (W - 2 * pad - 56) // per_row
        for i, e in enumerate(events):
            cx = pad + 28 + (i % per_row) * col_w
            cy = y + 62 + (i // per_row) * 62
            _t(d, (cx, cy), e["title"], _font(23), MUTED, max_w=col_w - 20)
            _t(d, (cx, cy + 26), e["value"], _font(30, True), max_w=col_w - 20)
        y += eh + 18

    # ── погода ───────────────────────────────────────────────────────────
    weather = data.get("weather", [])
    if weather:
        wh = 60 + len(weather) * 40
        if y + wh < H - 110:
            _panel(img, (pad, y, W - pad, y + wh))
            d = ImageDraw.Draw(img)
            _t(d, (pad + 28, y + 18), "ПОГОДА ЗА ЖУРНАЛОМ", _font(22, True), GOLD)
            wy = y + 58
            for line in weather:
                _t(d, (pad + 28, wy), line, _font(23), max_w=W - 2 * pad - 56)
                wy += 40

    # ── футер ────────────────────────────────────────────────────────────
    d = ImageDraw.Draw(img)
    _t(d, (pad, H - 72), "t.me/sumskoy_sinoptik", _font(24, True), GOLD)
    _right(d, W - pad, H - 68, "Дані: журнал каналу", _font(19), MUTED)

    img = img.resize((W, H), Image.LANCZOS)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


DEMO = {
    "period": "04.11–10.11.2026",
    "days": 7,
    "rows": [
        {"title": "Щоденний календар", "days": 7},
        {"title": "Курси валют і пальне", "days": 7},
        {"title": "Курс дорогоцінних металів", "days": 6},
        {"title": "Курс криптовалют", "days": 7},
        {"title": "Гороскоп дня", "days": 5},
        {"title": "Поїзди до Європи", "days": 7},
    ],
    "events": [
        {"title": "Повітряні тривоги", "value": "18 · 96 год"},
        {"title": "Відключення води", "value": "12"},
        {"title": "Оновлення світла", "value": "34"},
        {"title": "ДСНС", "value": "1"},
    ],
    "weather": ["Найтепліший день: 08.11 (+12°)", "Найхолодніша ніч: 05.11 (+1°)"],
}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", default="digest_card.png")
    a = ap.parse_args()
    print(render_card(DEMO, a.out))
