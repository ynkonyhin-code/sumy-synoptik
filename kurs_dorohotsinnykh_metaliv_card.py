#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки для посту «Курс дорогоцінних металів» (канал «Сумський синоптик»).

Модуль самодостатній: приймає словник `data` (його формує kurs_dorohotsinnykh_metaliv.py)
і зберігає PNG 1080x1350 (формат, який добре виглядає в стрічці Telegram).

Локальний перегляд без інтернету:
    python kurs_dorohotsinnykh_metaliv_card.py        -> card_preview.png
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350

# ── Палітра ────────────────────────────────────────────────────────────────
BG_TOP = (9, 16, 32)
BG_BOTTOM = (27, 38, 62)
PANEL = (255, 255, 255, 18)          # напівпрозора панель
GOLD = (222, 184, 82)
TEXT = (244, 246, 250)
MUTED = (150, 162, 184)
GREEN = (74, 205, 128)
RED = (240, 98, 98)
METAL_COLORS = {
    "XAU": (232, 190, 70),
    "XAG": (200, 208, 220),
    "XPT": (150, 190, 215),
    "XPD": (190, 160, 205),
}

_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/Library/Fonts",
    "C:\\Windows\\Fonts",
]
_REGULAR = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "arial.ttf"]
_BOLD = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = _BOLD if bold else _REGULAR
    env = os.getenv("CARD_FONT_BOLD" if bold else "CARD_FONT")
    candidates = [env] if env else []
    for d in _FONT_DIRS:
        candidates += [os.path.join(d, n) for n in names]
    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise RuntimeError(
        "Не знайдено шрифт з кирилицею. Встановіть fonts-dejavu-core "
        "або задайте CARD_FONT / CARD_FONT_BOLD."
    )


def fmt_money(x: Optional[float], decimals: int = 2) -> str:
    """6123.4 -> '6 123,40' (нерозривний пробіл, кома)."""
    if x is None:
        return "—"
    return f"{x:,.{decimals}f}".replace(",", "\u00a0").replace(".", ",")


# ── Допоміжне малювання ────────────────────────────────────────────────────
def _gradient() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    px = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        px.line([(0, y), (W, y)], fill=c)
    return img


def _panel(img: Image.Image, box: tuple[int, int, int, int]) -> None:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle(box, radius=28, fill=PANEL)
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _right(d: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill) -> None:
    w = d.textlength(text, font=font)
    d.text((x - w, y), text, font=font, fill=fill)


def _triangle(d: ImageDraw.ImageDraw, x: int, y: int, up: bool, color, s: int = 11) -> None:
    pts = [(x, y + s), (x + 2 * s, y + s), (x + s, y)] if up else [(x, y), (x + 2 * s, y), (x + s, y + s)]
    d.polygon(pts, fill=color)


def _section_title(d, x, y, text) -> None:
    d.text((x, y), text, font=_font(30, True), fill=GOLD)


# ── Основна функція ────────────────────────────────────────────────────────
def render_card(data: dict, out_path: str = "card.png") -> str:
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad = 56
    right_edge = W - pad - 24

    # Шапка
    d.text((pad, 52), "СУМСЬКИЙ СИНОПТИК", font=_font(26, True), fill=GOLD)
    d.text((pad, 92), "Курс дорогоцінних", font=_font(58, True), fill=TEXT)
    d.text((pad, 160), "металів в Україні", font=_font(58, True), fill=TEXT)
    _right(d, W - pad, 60, data["date"], _font(34, True), TEXT)
    _right(d, W - pad, 104, "станом на 11:00", _font(24), MUTED)
    d.line([(pad, 238), (W - pad, 238)], fill=GOLD, width=3)

    y = 262

    # ── Блок 1: НБУ ───────────────────────────────────────────────────────
    nbu = data.get("nbu", {})
    row_h = 68
    box_h = 66 + row_h * max(len(nbu), 1) + 8
    _panel(img, (pad - 16, y, W - pad + 16, y + box_h))
    d = ImageDraw.Draw(img)
    _section_title(d, pad + 8, y + 18, "Офіційний курс НБУ · грн за 1 г")
    ry = y + 62
    for cc, m in nbu.items():
        col = METAL_COLORS.get(cc, GOLD)
        d.ellipse([pad + 8, ry + 14, pad + 8 + 34, ry + 14 + 34], fill=col)
        d.text((pad + 58, ry + 8), m["name"], font=_font(34, True), fill=TEXT)
        _right(d, right_edge, ry + 2, fmt_money(m["per_gram"]), _font(36, True), TEXT)
        delta = m.get("delta")
        if delta is None:
            _right(d, right_edge, ry + 40, "динаміка недоступна", _font(21), MUTED)
        else:
            if abs(delta) < 0.005:
                color, txt = MUTED, "без змін"
            else:
                color = GREEN if delta > 0 else RED
                sign = "+" if delta > 0 else "−"
                txt = f"{sign}{fmt_money(abs(delta))} ({sign}{fmt_money(abs(m['pct']), 1)}%)"
            f = _font(22, True)
            tw = d.textlength(txt, font=f)
            _right(d, right_edge, ry + 40, txt, f, color)
            if abs(delta) >= 0.005:
                _triangle(d, int(right_edge - tw - 34), ry + 44, delta > 0, color, 9)
        ry += row_h
    y += box_h + 18

    # ── Блок 2: Банки ─────────────────────────────────────────────────────
    banks = data.get("banks", [])
    row_h = 52
    n = max(len(banks), 1)
    box_h = 100 + row_h * n + 6
    _panel(img, (pad - 16, y, W - pad + 16, y + box_h))
    d = ImageDraw.Draw(img)
    _section_title(d, pad + 8, y + 18, "Банки · злитки золота, грн за 1 г")
    hy = y + 60
    d.text((pad + 8, hy), "Банк", font=_font(21), fill=MUTED)
    _right(d, 640, hy, "Купівля", _font(21), MUTED)
    _right(d, right_edge, hy, "Продаж", _font(21), MUTED)
    ry = hy + 34
    if not banks:
        d.text((pad + 8, ry + 6), "Дані банків тимчасово недоступні", font=_font(26), fill=MUTED)
    for b in banks:
        d.text((pad + 8, ry), b["name"], font=_font(29, True), fill=TEXT)
        d.text((pad + 8 + d.textlength(b["name"], font=_font(29, True)) + 12, ry + 8),
               f"{b['bar']}", font=_font(19), fill=MUTED)
        _right(d, 640, ry, fmt_money(b["buy"], 0), _font(29, True), GREEN)
        _right(d, right_edge, ry, fmt_money(b["sell"], 0), _font(29, True), TEXT)
        ry += row_h
    y += box_h + 18

    # ── Блок 3: Ломбарди ──────────────────────────────────────────────────
    lom = data.get("lombard", [])
    row_h = 48
    box_h = 98 + row_h * max(len(lom), 1) + 4
    _panel(img, (pad - 16, y, W - pad + 16, y + box_h))
    d = ImageDraw.Draw(img)
    _section_title(d, pad + 8, y + 18, "Ломбарди · прийом лому, грн за 1 г")
    d.text((pad + 8, y + 58), "орієнтовний розрахунок", font=_font(21), fill=MUTED)
    ry = y + 92
    for it in lom:
        d.text((pad + 8, ry), it["label"], font=_font(29, True), fill=TEXT)
        rng = f"{fmt_money(it['low'], 0)} – {fmt_money(it['high'], 0)}"
        _right(d, right_edge, ry, rng, _font(29, True), GOLD)
        ry += row_h
    y += box_h

    # Футер
    d.text((pad, H - 78), "t.me/sumskoy_sinoptik", font=_font(26, True), fill=GOLD)
    _right(d, W - pad, H - 74, "Джерела: НБУ, Finance.ua", _font(21), MUTED)
    _right(d, W - pad, H - 46, "Не є публічною офертою", _font(18), MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


# ── Демо ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    demo = {
        "date": "16.10.2026",
        "nbu": {
            "XAU": {"name": "Золото", "per_gram": 6123.45, "delta": 41.2, "pct": 0.68},
            "XAG": {"name": "Срібло", "per_gram": 82.31, "delta": -1.15, "pct": 1.38},
            "XPT": {"name": "Платина", "per_gram": 2310.9, "delta": 0.0, "pct": 0.0},
            "XPD": {"name": "Паладій", "per_gram": 1750.12, "delta": None, "pct": None},
        },
        "banks": [
            {"name": "ПриватБанк", "bar": "10 г", "buy": 6150, "sell": 6900},
            {"name": "Комінбанк", "bar": "10 г", "buy": 6140, "sell": 6890},
            {"name": "Індустріалбанк", "bar": "10 г", "buy": 6190, "sell": 6900},
            {"name": "МТБ Банк", "bar": "10 г", "buy": 6120, "sell": 6950},
        ],
        "lombard": [
            {"label": "Золото 375 проби", "low": 1600, "high": 1950},
            {"label": "Золото 585 проби", "low": 2500, "high": 3050},
            {"label": "Золото 750 проби", "low": 3200, "high": 3900},
            {"label": "Срібло 925 проби", "low": 40, "high": 56},
        ],
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "card_preview.png"
    print("Збережено:", render_card(demo, out))
