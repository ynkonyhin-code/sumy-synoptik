#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки «Курс криптовалют» (канал «Сумський синоптик»).
PNG 1600x1200 (4:3): ліворуч — таблиця монет із міні-графіками за 7 днів,
праворуч — індекс настрою ринку, курс обміну на гривню та короткий огляд.

Локальний перегляд:  python kurs_kryptovalyut_card.py  ->  card_preview.png
"""
from __future__ import annotations

import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200
BG_TOP, BG_BOTTOM = (8, 14, 28), (20, 32, 58)
PANEL = (255, 255, 255, 18)
ACCENT = (247, 170, 40)
TEXT = (244, 246, 250)
MUTED = (150, 165, 190)
LINE = (52, 66, 94)
GREEN, RED = (84, 208, 140), (240, 105, 105)

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


def fmt_num(x: float, decimals: int = 2) -> str:
    return f"{x:,.{decimals}f}".replace(",", "\u00a0").replace(".", ",")


def fmt_usd(x: float) -> str:
    if x >= 1000:
        return "$" + fmt_num(x, 0)
    if x >= 1:
        return "$" + fmt_num(x, 2)
    return "$" + fmt_num(x, 4)


def fmt_pct(x: float | None, nd: int = 1) -> str:
    if x is None:
        return "—"
    sign = "+" if x > 0 else "−" if x < 0 else ""
    return f"{sign}{fmt_num(abs(x), nd)}%"


def _gradient() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    rnd = random.Random(5)
    for _ in range(60):                                  # ледь помітні «вузли мережі»
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        d.ellipse([x, y, x + 3, y + 3], fill=(60, 80, 120))
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


def _sparkline(d, x: int, y: int, w: int, h: int, series: list[float], color) -> None:
    if not series or len(series) < 2:
        return
    step = max(1, len(series) // 48)
    pts = series[::step]
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    xy = [(x + i * w / (len(pts) - 1), y + h - (v - lo) / span * h) for i, v in enumerate(pts)]
    d.line(xy, fill=color, width=3, joint="curve")
    d.ellipse([xy[-1][0] - 5, xy[-1][1] - 5, xy[-1][0] + 5, xy[-1][1] + 5], fill=color)


def _gauge(d, cx: int, cy: int, R: int, value: int | None) -> None:
    zones = [(0, 25, (230, 90, 90)), (25, 45, (240, 150, 90)), (45, 55, (200, 200, 120)),
             (55, 75, (140, 210, 120)), (75, 100, (70, 200, 130))]
    box = [cx - R, cy - R, cx + R, cy + R]
    for a, b, col in zones:
        d.arc(box, 180 + a * 1.8 + 0.6, 180 + b * 1.8 - 0.6, fill=col, width=30)
    if value is None:
        return
    th = math.radians(180 + max(0, min(100, value)) * 1.8)
    nx, ny = cx + (R - 40) * math.cos(th), cy + (R - 40) * math.sin(th)
    d.line([(cx, cy), (nx, ny)], fill=TEXT, width=6)
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=TEXT)


def render_card(data: dict, out_path: str = "card.png") -> str:
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad, bottom = 64, H - 104

    d.text((pad, 44), "СУМСЬКИЙ СИНОПТИК", font=_font(28, True), fill=ACCENT)
    d.text((pad, 88), "Курс криптовалют", font=_font(58, True), fill=TEXT)
    _right(d, W - pad, 46, data["date_long"], _font(40, True), TEXT)
    _right(d, W - pad, 98, "станом на 12:00", _font(26), MUTED)
    d.line([(pad, 170), (W - pad, 170)], fill=ACCENT, width=3)
    top = 198

    # ── Ліва колонка: таблиця монет ───────────────────────────────────────
    lx1, lx2 = pad, pad + 940
    _panel(img, (lx1, top, lx2, bottom))
    d = ImageDraw.Draw(img)
    d.text((lx1 + 32, top + 22), "Топ монет", font=_font(34, True), fill=ACCENT)
    d.text((lx1 + 32, top + 68), "ціна в USD · зміна за 24 год і 7 днів", font=_font(22), fill=MUTED)
    coins = data["coins"]
    y0 = top + 112
    row_h = (bottom - y0 - 12) // max(len(coins), 1)
    for i, c in enumerate(coins):
        y = y0 + i * row_h
        if i:
            d.line([(lx1 + 32, y), (lx2 - 32, y)], fill=LINE, width=1)
        cy = y + row_h // 2
        col = tuple(c["color"])
        d.ellipse([lx1 + 34, cy - 24, lx1 + 34 + 48, cy + 24], fill=col)
        sym_font = _font(34 if len(c["symbol"]) < 5 else 28, True)
        d.text((lx1 + 106, cy - 32), c["symbol"], font=sym_font, fill=TEXT)
        d.text((lx1 + 106, cy + 8), c["name"], font=_font(20), fill=MUTED)
        ch = c.get("change_24h")
        up = (ch or 0) >= 0
        _sparkline(d, lx1 + 290, cy - 24, 190, 48, c.get("spark") or [], GREEN if up else RED)
        _right(d, lx1 + 700, cy - 28, fmt_usd(c["price_usd"]), _font(36, True), TEXT)
        _right(d, lx1 + 700, cy + 12, f"₴ {fmt_num(c['price_uah'], 0 if c['price_uah'] >= 1000 else 2)}",
               _font(22), MUTED)
        if ch is not None:
            _right(d, lx2 - 34, cy - 28, fmt_pct(ch), _font(32, True), GREEN if ch >= 0 else RED)
        ch7 = c.get("change_7d")
        _right(d, lx2 - 34, cy + 12, f"7 д: {fmt_pct(ch7)}", _font(22),
               MUTED if ch7 is None else (GREEN if ch7 >= 0 else RED))

    # ── Права колонка ─────────────────────────────────────────────────────
    rx1, rx2 = lx2 + 28, W - pad
    # A. Настрій ринку
    a_bot = top + 330
    _panel(img, (rx1, top, rx2, a_bot))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 30, top + 20), "Настрій ринку", font=_font(32, True), fill=ACCENT)
    fg = data.get("fear_greed")
    gcx, gcy = (rx1 + rx2) // 2, top + 206
    _gauge(d, gcx, gcy, 128, fg["value"] if fg else None)
    if fg:
        v = str(fg["value"])
        f = _font(54, True)
        d.text((gcx - d.textlength(v, font=f) / 2, gcy + 14), v, font=f, fill=TEXT)
        f2 = _font(28, True)
        lab = fg["label"]
        d.text((gcx - d.textlength(lab, font=f2) / 2, gcy + 76), lab, font=f2, fill=ACCENT)
        if fg.get("delta") is not None:
            t = f"вчора: {fg['yesterday']} ({'+' if fg['delta'] > 0 else '−' if fg['delta'] < 0 else ''}{abs(fg['delta'])})"
            f3 = _font(20)
            d.text((gcx - d.textlength(t, font=f3) / 2, gcy + 112), t, font=f3, fill=MUTED)
    else:
        d.text((gcx - 130, gcy - 40), "дані недоступні", font=_font(28), fill=MUTED)

    # B. Обмін на гривню
    b_top = a_bot + 22
    b_bot = b_top + 330
    _panel(img, (rx1, b_top, rx2, b_bot))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 30, b_top + 20), "Обмін на гривню", font=_font(32, True), fill=ACCENT)
    yy = b_top + 80
    for label, val in data.get("exchange", []):
        d.text((rx1 + 30, yy), label, font=_font(26), fill=MUTED)
        _right(d, rx2 - 30, yy - 2, val, _font(28, True), TEXT)
        d.line([(rx1 + 30, yy + 38), (rx2 - 30, yy + 38)], fill=LINE, width=1)
        yy += 50

    # C. Огляд
    c_top = b_bot + 22
    _panel(img, (rx1, c_top, rx2, bottom))
    d = ImageDraw.Draw(img)
    d.text((rx1 + 30, c_top + 16), "Технічний огляд BTC", font=_font(26, True), fill=ACCENT)
    f = _font(22)
    for j, ln in enumerate(_wrap(d, data.get("summary", ""), f, rx2 - rx1 - 60)[:6]):
        d.text((rx1 + 30, c_top + 56 + j * 28), ln, font=f, fill=TEXT)

    d.text((pad, H - 72), "t.me/sumskoy_sinoptik", font=_font(30, True), fill=ACCENT)
    _right(d, W - pad, H - 78, "Джерела: CoinGecko, НБУ, Alternative.me", _font(23), MUTED)
    _right(d, W - pad, H - 46, "Інформаційний огляд, не інвестиційна порада · ризики на вас", _font(20), MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    rnd = random.Random(3)

    def fake(base, drift):
        v, out = base, []
        for _ in range(168):
            v *= 1 + rnd.uniform(-0.006, 0.006) + drift
            out.append(v)
        return out
    spec = [("BTC", "Bitcoin", 67450, 41.2, 1.2, 4.5, (247, 147, 26), 0.0003),
            ("ETH", "Ethereum", 3380, 41.2, -0.8, 2.1, (130, 150, 230), 0.0001),
            ("USDT", "Tether", 1.0, 41.2, 0.0, 0.0, (80, 190, 150), 0.0),
            ("BNB", "BNB", 598, 41.2, 0.4, -1.2, (240, 200, 70), -0.0001),
            ("SOL", "Solana", 168.4, 41.2, 3.1, 8.4, (150, 100, 240), 0.0006),
            ("XRP", "XRP", 0.5234, 41.2, -1.9, -3.3, (200, 205, 215), -0.0003),
            ("TON", "Toncoin", 5.82, 41.2, 0.9, 1.0, (70, 160, 240), 0.0),
            ("DOGE", "Dogecoin", 0.1534, 41.2, -2.4, -6.1, (225, 190, 90), -0.0004)]
    coins = [{"symbol": s, "name": n, "price_usd": p, "price_uah": p * u, "change_24h": c24, "change_7d": c7,
              "color": col, "spark": fake(p, dr)} for s, n, p, u, c24, c7, col, dr in spec]
    demo = {
        "date_long": "17 жовтня 2026", "coins": coins,
        "fear_greed": {"value": 34, "label": "Страх", "yesterday": 31, "delta": 3},
        "exchange": [("USD · курс НБУ", "41,20 ₴"), ("USDT ≈", "41,35 ₴"), ("1 BTC ≈", "2 779 000 ₴"),
                     ("1 ETH ≈", "139 300 ₴"), ("10 000 ₴ ≈", "241,8 USDT")],
        "summary": "За тиждень BTC +4,5 %: помірний висхідний рух. Ціна в середній третині тижневого "
                   "діапазону $64 100–$68 300, волатильність помірна.",
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "card_preview.png"
    print("Збережено:", render_card(demo, out))
