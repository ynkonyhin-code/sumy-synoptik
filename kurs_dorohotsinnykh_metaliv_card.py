#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки для посту «Курс дорогоцінних металів» (канал «Сумський синоптик»).

Модуль самодостатній: приймає словник `data` (його формує kurs_dorohotsinnykh_metaliv.py)
і зберігає PNG 1600x1200 (4:3, горизонтальний — Telegram показує на всю ширину поста).

Локальний перегляд без інтернету:
    python kurs_dorohotsinnykh_metaliv_card.py        -> card_preview.png
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200

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
    """Горизонтальна картка 4:3 — Telegram показує її на всю ширину поста."""
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad = 64
    bottom = H - 104

    # Шапка
    d.text((pad, 44), "СУМСЬКИЙ СИНОПТИК", font=_font(28, True), fill=GOLD)
    d.text((pad, 88), "Курс дорогоцінних металів в Україні", font=_font(54, True), fill=TEXT)
    _right(d, W - pad, 46, data["date"], _font(40, True), TEXT)
    _right(d, W - pad, 98, "станом на 11:00", _font(26), MUTED)
    d.line([(pad, 170), (W - pad, 170)], fill=GOLD, width=3)
    top = 198

    lx1, lx2 = pad, pad + 690                 # ліва колонка
    rx1, rx2 = lx2 + 32, W - pad              # права колонка

    # ── Ліва колонка: НБУ ─────────────────────────────────────────────────
    nbu = data.get("nbu", {})
    _panel(img, (lx1, top, lx2, bottom))
    d = ImageDraw.Draw(img)
    d.text((lx1 + 32, top + 28), "Офіційний курс НБУ", font=_font(36, True), fill=GOLD)
    d.text((lx1 + 32, top + 76), "грн за 1 грам", font=_font(24), fill=MUTED)
    n = max(len(nbu), 1)
    ry = top + 130
    row_h = (bottom - ry - 16) // n
    re_ = lx2 - 32
    for i, (cc, m) in enumerate(nbu.items()):
        col = METAL_COLORS.get(cc, GOLD)
        cy = ry + row_h // 2
        d.ellipse([lx1 + 32, cy - 26, lx1 + 32 + 52, cy + 26], fill=col)
        d.text((lx1 + 106, cy - 28), m["name"], font=_font(42, True), fill=TEXT)
        _right(d, re_, cy - 48, fmt_money(m["per_gram"]), _font(58, True), TEXT)
        delta = m.get("delta")
        f = _font(28, True)
        if delta is None:
            _right(d, re_, cy + 26, "динаміка недоступна", _font(24), MUTED)
        elif abs(delta) < 0.005:
            _right(d, re_, cy + 26, "без змін", f, MUTED)
        else:
            color = GREEN if delta > 0 else RED
            sign = "+" if delta > 0 else "−"
            txt = f"{sign}{fmt_money(abs(delta))}  ({sign}{fmt_money(abs(m['pct']), 1)}%)"
            tw = d.textlength(txt, font=f)
            _right(d, re_, cy + 26, txt, f, color)
            _triangle(d, int(re_ - tw - 38), cy + 32, delta > 0, color, 11)
        if i < n - 1:
            d.line([(lx1 + 32, ry + row_h), (lx2 - 32, ry + row_h)], fill=(58, 68, 92), width=2)
        ry += row_h

    # ── Права колонка: банки ──────────────────────────────────────────────
    banks = data.get("banks", [])
    b_bottom = top + 440
    _panel(img, (rx1, top, rx2, b_bottom))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 32, top + 28), "Банки · злитки золота", font=_font(36, True), fill=GOLD)
    d.text((rx1 + 32, top + 76), "грн за 1 грам", font=_font(24), fill=MUTED)
    hy = top + 122
    d.text((rx1 + 32, hy), "Банк", font=_font(23), fill=MUTED)
    buy_x, sell_x = rx1 + 530, rx2 - 32
    _right(d, buy_x, hy, "Купівля", _font(23), MUTED)
    _right(d, sell_x, hy, "Продаж", _font(23), MUTED)
    ry = hy + 44
    if not banks:
        d.text((rx1 + 32, ry + 8), "Дані банків тимчасово недоступні", font=_font(28), fill=MUTED)
    for bk in banks:
        fb = _font(32, True)
        d.text((rx1 + 32, ry), bk["name"], font=fb, fill=TEXT)
        d.text((rx1 + 32 + d.textlength(bk["name"], font=fb) + 12, ry + 10),
               bk["bar"], font=_font(21), fill=MUTED)
        _right(d, buy_x, ry, fmt_money(bk["buy"], 0), fb, GREEN)
        _right(d, sell_x, ry, fmt_money(bk["sell"], 0), fb, TEXT)
        ry += 62

    # ── Права колонка: ломбарди ───────────────────────────────────────────
    lom = data.get("lombard", [])
    l_top = b_bottom + 24
    _panel(img, (rx1, l_top, rx2, bottom))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 32, l_top + 28), "Ломбарди · прийом лому", font=_font(36, True), fill=GOLD)
    d.text((rx1 + 32, l_top + 76), "грн за 1 грам · орієнтовний розрахунок", font=_font(24), fill=MUTED)
    ry = l_top + 126
    for it in lom:
        fl = _font(32, True)
        d.text((rx1 + 32, ry), it["label"], font=fl, fill=TEXT)
        rng = f"{fmt_money(it['low'], 0)} – {fmt_money(it['high'], 0)}"
        _right(d, rx2 - 32, ry, rng, fl, GOLD)
        ry += 56

    # Футер
    d.text((pad, H - 72), "t.me/sumskoy_sinoptik", font=_font(30, True), fill=GOLD)
    _right(d, W - pad, H - 78, "Джерела: НБУ, Finance.ua", _font(23), MUTED)
    _right(d, W - pad, H - 46, "Не є публічною офертою", _font(20), MUTED)

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
