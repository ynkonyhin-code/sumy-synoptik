#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор картки «Поїзди до Європи без пересадок» (канал «Сумський синоптик»).

Приймає словник `data` (його формує poyizdy_do_yevropy.py) і зберігає PNG 1600x1200
(4:3, горизонтальний — Telegram показує на всю ширину поста).

Локальний перегляд:  python poyizdy_do_yevropy_card.py  ->  card_preview.png
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200

BG_TOP, BG_BOTTOM = (9, 16, 32), (27, 38, 62)
PANEL = (255, 255, 255, 18)
GOLD = (222, 184, 82)
TEXT = (244, 246, 250)
MUTED = (150, 162, 184)
LINE = (58, 68, 92)
PILL = {  # колір «значка» країни
    "PL": (226, 92, 108), "HU": (92, 184, 128), "SK": (88, 146, 232),
    "AT": (232, 110, 110), "MD": (232, 196, 80), "RO": (232, 200, 90),
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
    return img


def _panel(img: Image.Image, box) -> None:
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, radius=28, fill=PANEL)
    img.paste(Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB"))


def _right(d, x, y, text, font, fill) -> float:
    w = d.textlength(text, font=font)
    d.text((x - w, y), text, font=font, fill=fill)
    return w


def _fit(d, text: str, font_size: int, max_w: int, bold: bool = False, min_size: int = 17):
    """Зменшує шрифт, поки текст не влізе в max_w; якщо не влазить — обрізає."""
    size = font_size
    while size > min_size:
        f = _font(size, bold)
        if d.textlength(text, font=f) <= max_w:
            return f, text
        size -= 1
    f = _font(min_size, bold)
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return f, text + "…"


def render_card(data: dict, out_path: str = "card.png") -> str:
    img = _gradient()
    d = ImageDraw.Draw(img)
    pad = 64
    bottom = H - 104

    # Шапка
    d.text((pad, 44), "СУМСЬКИЙ СИНОПТИК", font=_font(28, True), fill=GOLD)
    d.text((pad, 88), "Поїзди до Європи без пересадок", font=_font(54, True), fill=TEXT)
    _right(d, W - pad, 46, data["date_short"], _font(40, True), TEXT)
    _right(d, W - pad, 98, f"{data['weekday']} · {data['parity']} число", _font(26), MUTED)
    d.line([(pad, 170), (W - pad, 170)], fill=GOLD, width=3)

    top = 198
    _panel(img, (pad, top, W - pad, bottom))
    d = ImageDraw.Draw(img)
    d.text((pad + 36, top + 24), "Сьогодні відправляються з України", font=_font(34, True), fill=GOLD)
    d.text((pad + 36, top + 70), "час — місцевий на станції · «від» — мінімальна ціна, грн", font=_font(23), fill=MUTED)

    trains = data.get("trains", [])
    y0 = top + 120
    if not trains:
        d.text((pad + 36, y0 + 60), "Сьогодні за довідником прямих рейсів немає", font=_font(40, True), fill=TEXT)
        d.text((pad + 36, y0 + 124), "Розклад на інші дні — у застосунку «Укрзалізниці»", font=_font(28), fill=MUTED)
    else:
        n = len(trains)
        row_h = min(124, (bottom - y0 - 16) // n)
        x_l, x_r = pad + 36, W - pad - 36
        for i, t in enumerate(trains):
            y = y0 + i * row_h
            if i:
                d.line([(x_l, y), (x_r, y)], fill=LINE, width=2)
            # значок країни
            col = PILL.get(t["code"], GOLD)
            d.rounded_rectangle([x_l, y + 14, x_l + 84, y + 14 + 44], radius=12, fill=col)
            f = _font(26, True)
            tw = d.textlength(t["code"], font=f)
            d.text((x_l + 42 - tw / 2, y + 22), t["code"], font=f, fill=(18, 24, 38))
            # номер + маршрут
            fn = _font(36, True)
            d.text((x_l + 108, y + 12), t["train"], font=fn, fill=TEXT)
            rx = x_l + 108 + d.textlength(t["train"], font=fn) + 24
            route = f"{t['from']} → {t['to']}"
            fr, route = _fit(d, route, 36, int(x_r - 330 - rx), True)
            d.text((rx, y + 12), route, font=fr, fill=TEXT)
            # час
            times = f"{t['dep']} → {t['arr']}"
            ft = _font(40, True)
            tw = d.textlength(times, font=ft)
            d.text((x_r - tw - (52 if t["arr_day"] else 0), y + 8), times, font=ft, fill=TEXT)
            if t["arr_day"]:
                _right(d, x_r, y + 10, f"+{t['arr_day']}", _font(26, True), GOLD)
            # другий рядок: тип / тривалість / ціни
            second = f"{t['kind']} · в дорозі {t['duration']}"
            d.text((x_l + 108, y + 62), second, font=_font(24), fill=MUTED)
            if t.get("prices"):
                fp, ptxt = _fit(d, t["prices"], 24, 820, True)
                _right(d, x_r, y + 62, ptxt, fp, GOLD)
            if t.get("note") and row_h >= 112:
                fnote, ntxt = _fit(d, "ℹ " + t["note"], 22, x_r - x_l - 108)
                d.text((x_l + 108, y + 92), ntxt, font=fnote, fill=MUTED)

    # Футер
    d.text((pad, H - 72), "t.me/sumskoy_sinoptik", font=_font(30, True), fill=GOLD)
    _right(d, W - pad, H - 78, "Джерело: Укрзалізниця (uz-vezemo.uz.gov.ua)", _font(23), MUTED)
    _right(d, W - pad, H - 46, "Квитки та наявність місць — у застосунку УЗ", _font(20), MUTED)

    img.save(out_path, "PNG", optimize=True)
    return out_path


if __name__ == "__main__":
    demo = {
        "date_short": "17.10.2026", "weekday": "субота", "parity": "непарне",
        "trains": [
            {"code": "PL", "train": "№715 Інтерсіті+", "kind": "денний", "from": "Київ", "to": "Перемишль",
             "dep": "11:06", "arr": "19:55", "arr_day": 0, "duration": "9 г 49 хв",
             "prices": "2 клас від 1 400 · 1 клас від 2 100 грн", "note": "Зупинки: Вінниця, Хмельницький, Тернопіль"},
            {"code": "PL", "train": "№705 Інтерсіті+", "kind": "вечірній", "from": "Київ", "to": "Перемишль",
             "dep": "18:35", "arr": "03:30", "arr_day": 1, "duration": "9 г 55 хв", "prices": "", "note": None},
            {"code": "PL", "train": "№51", "kind": "нічний", "from": "Київ", "to": "Перемишль",
             "dep": "20:05", "arr": "05:00", "arr_day": 1, "duration": "9 г 55 хв",
             "prices": "Плацкарт від 1 100 · Купе від 1 700 · СВ від 3 000 грн", "note": "Через Львів"},
            {"code": "PL", "train": "№19", "kind": "вечірній", "from": "Київ", "to": "Холм",
             "dep": "19:06", "arr": "05:00", "arr_day": 1, "duration": "10 г 54 хв", "prices": "",
             "note": "У Холмі — пересадка на IC до Варшави (06:22 → 09:43)"},
            {"code": "PL", "train": "№23", "kind": "нічний", "from": "Київ", "to": "Холм",
             "dep": "21:30", "arr": "08:08", "arr_day": 1, "duration": "11 г 38 хв", "prices": "",
             "note": "У Холмі — пересадка на IC до Варшави (08:32 → 11:19)"},
            {"code": "MD", "train": "№351", "kind": "нічний", "from": "Київ", "to": "Кишинів",
             "dep": "18:06", "arr": "11:53", "arr_day": 1, "duration": "17 г 47 хв", "prices": "",
             "note": "Курсує по непарних числах"},
        ],
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "card_preview.png"
    print("Збережено:", render_card(demo, out))
