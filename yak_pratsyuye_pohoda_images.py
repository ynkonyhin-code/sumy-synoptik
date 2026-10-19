"""Генератор схем для підциклу «Як працює погода» (yak_pratsyuye_pohoda).
Кожен випуск — одна пояснювальна схема 1280×720: заголовок, малюнок явища та 3 кроки справа.
Запуск для перегляду всіх схем:  python yak_pratsyuye_pohoda_images.py [папка]
"""
import math
import os
import random
import sys
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
SS = 2                      # supersampling
SW, SH = 830, 520           # розмір «картки» зі сценою
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_CANDIDATES = [
    os.path.join(HERE, "yak_pratsyuye_pohoda_font.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "arialbd.ttf",
]
WHITE = (255, 255, 255, 255)
INK = (30, 45, 70, 255)
NAVY = (28, 60, 120, 255)
_fonts = {}


def F(size):
    if size not in _fonts:
        for p in FONT_CANDIDATES:
            try:
                _fonts[size] = ImageFont.truetype(p, int(size * SS))
                break
            except OSError:
                continue
        else:
            _fonts[size] = ImageFont.load_default()
    return _fonts[size]


def px(v):
    return int(round(v * SS))


def B(box):
    return tuple(int(round(v * SS)) for v in box)


def P(pt):
    return (int(round(pt[0] * SS)), int(round(pt[1] * SS)))


def vgrad(w, h, top, bottom):
    img = Image.new("RGB", (w * SS, h * SS))
    d = ImageDraw.Draw(img)
    n = h * SS
    for y in range(n):
        t = y / (n - 1)
        d.line([(0, y), (w * SS, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def canvas(top, bottom):
    img = vgrad(SW, SH, top, bottom)
    return img, ImageDraw.Draw(img, "RGBA")


# ───────────── примітиви ─────────────
def tag(d, cx, cy, text, size=21, bg=(255, 255, 255, 238), fg=INK, pad=10):
    font = F(size)
    lines = text.split("\n")
    ws = [d.textlength(ln, font=font) for ln in lines]
    lh = int(size * SS * 1.28)
    w = int(max(ws)) + 2 * px(pad)
    h = lh * len(lines) + 2 * px(pad) - int(size * SS * 0.15)
    x0, y0 = px(cx) - w // 2, px(cy) - h // 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=px(12), fill=bg)
    for i, ln in enumerate(lines):
        d.text((px(cx), y0 + px(pad) + i * lh), ln, font=font, fill=fg, anchor="ma")


def arrow(d, p0, p1, color=WHITE, w=6, head=18):
    poly_arrow(d, [p0, p1], color, w, head)


def poly_arrow(d, pts, color=WHITE, w=6, head=18):
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    bx, by = x1 - head * 0.8 * math.cos(a), y1 - head * 0.8 * math.sin(a)
    line = [P(p) for p in pts[:-1]] + [P((bx, by))]
    d.line(line, fill=color, width=px(w), joint="curve")
    for p in (line[0], line[-1]):
        d.ellipse([p[0] - px(w) // 2, p[1] - px(w) // 2, p[0] + px(w) // 2, p[1] + px(w) // 2], fill=color)
    s, c = math.sin(a), math.cos(a)
    tip = (x1, y1)
    l = (x1 - head * c + head * 0.55 * s, y1 - head * s - head * 0.55 * c)
    r = (x1 - head * c - head * 0.55 * s, y1 - head * s + head * 0.55 * c)
    d.polygon([P(tip), P(l), P(r)], fill=color)


def cloud(d, x, y, s=1.0, color=(255, 255, 255, 255)):
    for dx, dy, r in [(0, 0, 38), (40, -18, 48), (88, 0, 40), (44, 12, 40)]:
        d.ellipse(B([x + (dx - r) * s, y + (dy - r) * s, x + (dx + r) * s, y + (dy + r) * s]), fill=color)


def drop(d, x, y, r, color=(90, 150, 255, 255)):
    d.ellipse(B([x - r, y - r, x + r, y + r]), fill=color)
    d.polygon([P((x, y - r * 2.3)), P((x - r * 0.92, y - r * 0.35)), P((x + r * 0.92, y - r * 0.35))], fill=color)


def sun(d, x, y, r, color=(255, 214, 60, 255), rays=True):
    for k in range(5, 0, -1):
        rr = r + k * 12
        d.ellipse(B([x - rr, y - rr, x + rr, y + rr]), fill=(255, 240, 150, 22))
    if rays:
        for k in range(12):
            a = math.radians(k * 30)
            d.line([P((x + (r + 8) * math.cos(a), y + (r + 8) * math.sin(a))),
                    P((x + (r + 24) * math.cos(a), y + (r + 24) * math.sin(a)))], fill=color, width=px(5))
    d.ellipse(B([x - r, y - r, x + r, y + r]), fill=color)


def pine(d, x, yb, h, color):
    for k in range(3):
        top = yb - h + k * h * 0.24
        wid = h * 0.2 * (0.8 + 0.3 * k)
        d.polygon([P((x, top)), P((x - wid, top + h * 0.42)), P((x + wid, top + h * 0.42))], fill=color)
    d.rectangle(B([x - 4, yb - h * 0.12, x + 4, yb]), fill=(70, 50, 35, 255))


def snowflake(d, cx, cy, R, color=WHITE, w=6, branches=1):
    for k in range(6):
        a = math.radians(k * 60 + 30)
        ex, ey = cx + R * math.cos(a), cy + R * math.sin(a)
        d.line([P((cx, cy)), P((ex, ey))], fill=color, width=px(w))
        if branches:
            for t, l in ((0.5, 0.34), (0.76, 0.22)):
                bx, by = cx + t * R * math.cos(a), cy + t * R * math.sin(a)
                for sg in (-1, 1):
                    ba = a + sg * math.radians(60)
                    d.line([P((bx, by)), P((bx + l * R * math.cos(ba), by + l * R * math.sin(ba)))],
                           fill=color, width=px(max(2, w * 0.65)))
    d.ellipse(B([cx - w, cy - w, cx + w, cy + w]), fill=color)


def person(d, x, yb, s=1.0, coat=(200, 60, 70), scarf=True):
    leg = (40, 55, 95, 255)
    d.rounded_rectangle(B([x - 24 * s, yb - 90 * s, x - 3 * s, yb]), radius=px(6 * s), fill=leg)
    d.rounded_rectangle(B([x + 3 * s, yb - 90 * s, x + 24 * s, yb]), radius=px(6 * s), fill=leg)
    d.rounded_rectangle(B([x - 40 * s, yb - 200 * s, x + 40 * s, yb - 80 * s]), radius=px(18 * s), fill=coat + (255,))
    d.ellipse(B([x - 26 * s, yb - 262 * s, x + 26 * s, yb - 210 * s]), fill=(250, 214, 180, 255))
    d.pieslice(B([x - 30 * s, yb - 280 * s, x + 30 * s, yb - 226 * s]), 180, 360, fill=(40, 60, 130, 255))
    if scarf:
        d.rounded_rectangle(B([x - 34 * s, yb - 218 * s, x + 34 * s, yb - 198 * s]), radius=px(8 * s), fill=(255, 200, 60, 255))


def thermo(d, x, ytop, ybot, level, color):
    edge = (60, 70, 90, 255)
    d.rounded_rectangle(B([x - 16, ytop, x + 16, ybot]), radius=px(16), fill=WHITE, outline=edge, width=px(3))
    d.ellipse(B([x - 30, ybot - 8, x + 30, ybot + 52]), fill=WHITE, outline=edge, width=px(3))
    top_fill = ybot - (ybot - ytop) * level
    d.rounded_rectangle(B([x - 8, top_fill, x + 8, ybot + 10]), radius=px(8), fill=color + (255,))
    d.ellipse(B([x - 25, ybot - 3, x + 25, ybot + 47]), fill=color + (255,))


def front_line(d, pts, kind, color, side=1, step=42):
    d.line([P(p) for p in pts], fill=color, width=px(6), joint="curve")
    seg = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    carry = step / 2
    for (x0, y0), (x1, y1) in seg:
        L = math.hypot(x1 - x0, y1 - y0)
        a = math.atan2(y1 - y0, x1 - x0)
        pos = carry
        while pos < L:
            px_, py_ = x0 + pos * math.cos(a), y0 + pos * math.sin(a)
            nx, ny = -math.sin(a) * side, math.cos(a) * side
            if kind == "cold":
                tri = [(px_ - 11 * math.cos(a), py_ - 11 * math.sin(a)),
                       (px_ + 11 * math.cos(a), py_ + 11 * math.sin(a)),
                       (px_ + 20 * nx, py_ + 20 * ny)]
                d.polygon([P(p) for p in tri], fill=color)
            else:
                d.pieslice(B([px_ - 12, py_ - 12, px_ + 12, py_ + 12]),
                           math.degrees(math.atan2(ny, nx)) - 90, math.degrees(math.atan2(ny, nx)) + 90, fill=color)
            pos += step
        carry = pos - L


def spiral_arrow(d, cx, cy, r0, r1, a0, sweep, ccw, color, w=7, head=18):
    pts = []
    n = 40
    for i in range(n + 1):
        t = i / n
        r = r0 + (r1 - r0) * t
        a = math.radians(a0 + sweep * t)
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a) if ccw else cy + r * math.sin(a)))
    poly_arrow(d, pts, color, w, head)


# ───────────── сцени ─────────────
def sc_fog():
    img, d = canvas((35, 50, 95), (160, 175, 210))
    rng = random.Random(1)
    d.ellipse(B([700, 40, 760, 100]), fill=(250, 250, 230, 255))
    d.ellipse(B([722, 32, 782, 92]), fill=(49, 64, 108, 255))
    d.rectangle(B([0, 390, 830, 520]), fill=(46, 78, 82, 255))
    d.ellipse(B([-100, 360, 500, 540]), fill=(56, 92, 92, 255))
    d.ellipse(B([350, 370, 950, 540]), fill=(50, 86, 88, 255))
    for x, h in ((70, 120), (160, 90), (610, 110), (730, 140)):
        pine(d, x, 410, h, (30, 60, 62, 255))
    for _ in range(40):
        d.ellipse(B([(x := rng.randint(60, 760)) - 4, (y := rng.randint(150, 320)) - 4, x + 4, y + 4]), fill=(255, 255, 255, 150))
    d.rectangle(B([0, 365, 830, 440]), fill=(245, 248, 255, 70))
    for _ in range(110):
        r = rng.randint(22, 48)
        x, y = rng.randint(-20, 850), rng.randint(360, 425)
        d.ellipse(B([x - r, y - r, x + r, y + r]), fill=(245, 248, 255, 55))
    tag(d, 415, 120, "тепле вологе повітря\nз невидимою водяною парою")
    tag(d, 415, 320, "туман = мільйони крихітних краплинок води")
    for x in (180, 415, 650):
        arrow(d, (x, 438), (x, 490), (120, 190, 255, 255), 7, 20)
    tag(d, 415, 498, "земля віддає тепло й остигає", size=19)
    return img


def sc_dew():
    img, d = canvas((255, 226, 200), (180, 210, 250))
    d.rectangle(B([415, 0, 830, 520]), fill=(150, 185, 255, 70))
    d.line([P((415, 20)), P((415, 500))], fill=(255, 255, 255, 200), width=px(4))
    d.rectangle(B([0, 470, 830, 520]), fill=(70, 130, 80, 255))
    for cx, mode in ((207, "dew"), (623, "frost")):
        for poly in ([(cx - 30, 480), (cx - 14, 300), (cx + 10, 190), (cx + 70, 130), (cx + 20, 260), (cx + 32, 480)],
                     [(cx - 90, 480), (cx - 80, 330), (cx - 110, 250), (cx - 62, 320), (cx - 50, 480)],
                     [(cx + 60, 480), (cx + 80, 350), (cx + 120, 290), (cx + 110, 360), (cx + 95, 480)]):
            d.polygon([P(p) for p in poly], fill=(70, 150, 80, 255))
            if mode == "frost":
                d.polygon([P(p) for p in poly], fill=(255, 255, 255, 110))
        spots = [(cx - 8, 340), (cx + 2, 280), (cx + 24, 225), (cx + 52, 170), (cx - 78, 330), (cx - 92, 270), (cx + 92, 350), (cx + 110, 330)]
        for x, y in spots:
            if mode == "dew":
                d.ellipse(B([x - 10, y - 10, x + 10, y + 10]), fill=(205, 232, 255, 240), outline=WHITE, width=px(2))
                d.ellipse(B([x - 5, y - 6, x - 1, y - 2]), fill=WHITE)
            else:
                snowflake(d, x, y, 15, (235, 248, 255, 255), 3, 0)
    tag(d, 207, 55, "РОСА\nвище 0°C", size=24)
    tag(d, 623, 55, "ІНІЙ\nнижче 0°C", size=24)
    tag(d, 207, 497, "краплинки води", size=19)
    tag(d, 623, 497, "кристалики льоду", size=19)
    return img


def sc_cloud():
    img, d = canvas((110, 185, 255), (215, 240, 255))
    sun(d, 90, 90, 40)
    d.rectangle(B([0, 450, 830, 520]), fill=(96, 160, 90, 255))
    cloud(d, 150, 175, 2.4)
    rng = random.Random(2)
    for _ in range(46):
        x, y = rng.randint(80, 440), rng.randint(70, 250)
        d.ellipse(B([x - 4, y - 4, x + 4, y + 4]), fill=(190, 218, 252, 255))
    for x in (160, 260, 360):
        poly_arrow(d, [(x, 440), (x + 14, 400), (x - 10, 365), (x + 10, 335), (x, 305)], (255, 120, 60, 255), 8, 22)
    for i in range(330):
        t = i / 329
        d.line([P((745, 60 + i)), P((775, 60 + i))], fill=(int(70 + 185 * t), int(130 - 20 * t), int(255 - 195 * t), 255), width=px(1.2))
    tag(d, 760, 38, "холодніше", size=18)
    tag(d, 760, 425, "тепліше", size=18)
    tag(d, 585, 150, "угорі холодніше:\nпара стає краплинками", size=20)
    tag(d, 585, 360, "тепле вологе повітря\nпіднімається вгору", size=20)
    return img


def sc_rain():
    img, d = canvas((150, 170, 195), (210, 220, 235))
    rng = random.Random(3)
    cloud(d, 295, 140, 1.9, (118, 130, 150, 255))
    for _ in range(26):
        x, y = rng.randint(250, 520), rng.randint(40, 200)
        d.ellipse(B([x - 3, y - 3, x + 3, y + 3]), fill=(170, 195, 230, 255))
    for _ in range(16):
        x, y = 150 + rng.randint(-45, 45), 340 + rng.randint(-35, 35)
        d.ellipse(B([x - 5, y - 5, x + 5, y + 5]), fill=(110, 165, 235, 255))
    for x, y in ((385, 325), (445, 325), (415, 372)):
        drop(d, x, y, 10)
    for sx, sy in ((385, 345), (445, 345), (415, 355)):
        pass
    arrow(d, (392, 340), (410, 350), (60, 90, 150, 255), 3, 8)
    arrow(d, (438, 340), (420, 350), (60, 90, 150, 255), 3, 8)
    drop(d, 680, 345, 22)
    for dx in (-26, 0, 26):
        d.line([P((680 + dx, 250)), P((680 + dx, 292))], fill=(255, 255, 255, 190), width=px(4))
    arrow(d, (215, 340), (330, 340), WHITE, 7, 20)
    arrow(d, (490, 340), (605, 340), WHITE, 7, 20)
    tag(d, 150, 445, "1. дрібні краплинки\nзависли в хмарі", size=19)
    tag(d, 415, 445, "2. стикаються\nй зливаються", size=19)
    tag(d, 680, 445, "3. стали важкими —\nпадають дощем", size=19)
    return img


def sc_snow():
    img, d = canvas((110, 140, 195), (215, 230, 250))
    hexa = [P((130 + 26 * math.cos(math.radians(60 * k)), 270 + 26 * math.sin(math.radians(60 * k)))) for k in range(6)]
    d.polygon(hexa, fill=WHITE)
    snowflake(d, 385, 270, 72, WHITE, 6, 1)
    snowflake(d, 670, 270, 130, WHITE, 8, 1)
    arrow(d, (185, 270), (290, 270), (255, 255, 255, 255), 6, 18)
    arrow(d, (468, 270), (528, 270), (255, 255, 255, 255), 6, 18)
    tag(d, 130, 440, "1. крихітний\nкристал льоду", size=19)
    tag(d, 385, 440, "2. росте: на нього\nнамерзає пара", size=19)
    tag(d, 670, 440, "3. сніжинка:\nшість променів", size=19)
    tag(d, 415, 40, "у всіх сніжинок шість променів, а візерунок свій", size=19)
    return img


def sc_glaze():
    img, d = canvas((95, 110, 140), (95, 110, 140))
    d.rectangle(B([0, 0, 830, 150]), fill=(112, 128, 155, 255))
    d.rectangle(B([0, 150, 830, 280]), fill=(255, 196, 130, 255))
    d.rectangle(B([0, 280, 830, 430]), fill=(175, 213, 247, 255))
    d.rectangle(B([0, 430, 830, 520]), fill=(70, 76, 88, 255))
    d.ellipse(B([360, 438, 560, 478]), fill=(215, 240, 255, 255))
    d.ellipse(B([380, 444, 470, 458]), fill=(255, 255, 255, 230))
    snowflake(d, 450, 70, 28, WHITE, 5, 1)
    arrow(d, (450, 108), (450, 175), (255, 255, 255, 255), 6, 18)
    drop(d, 450, 225, 11)
    arrow(d, (450, 255), (450, 320), (60, 90, 170, 255), 6, 18)
    drop(d, 450, 372, 11, (60, 120, 235, 255))
    d.ellipse(B([436, 354, 464, 388]), outline=(255, 255, 255, 255), width=px(3))
    arrow(d, (450, 396), (450, 430), (60, 90, 170, 255), 6, 16)
    tag(d, 135, 75, "сніг у хмарі", size=19)
    tag(d, 135, 215, "тепле повітря\n(вище 0°C)", size=19)
    tag(d, 135, 355, "шар морозу\n(нижче 0°C)", size=19)
    tag(d, 135, 478, "дорога", size=19)
    tag(d, 660, 215, "сніжинка тане\nі стає краплею", size=19)
    tag(d, 660, 355, "крапля переохолоджується:\nще рідка, хоча мороз", size=19)
    tag(d, 665, 478, "торкнулась поверхні —\nмиттєво замерзла", size=19)
    return img


def sc_windchill():
    img, d = canvas((160, 195, 235), (230, 242, 252))
    d.rectangle(B([0, 480, 830, 520]), fill=(225, 235, 245, 255))
    person(d, 200, 480, 1.25)
    for y, dy in ((190, 12), (290, -12), (390, 12)):
        poly_arrow(d, [(560, y), (480, y + dy), (400, y - dy), (320, y + dy)], (255, 255, 255, 235), 7, 22)
    thermo(d, 590, 110, 330, 0.55, (230, 70, 70))
    thermo(d, 740, 110, 330, 0.34, (70, 120, 230))
    tag(d, 590, 425, "термометр:\n−5°C", size=19)
    tag(d, 740, 425, "відчувається:\n≈ −13°C", size=19)
    tag(d, 415, 45, "приклад: вітер 30 км/год", size=20)
    tag(d, 330, 495, "вітер здуває шар тепла біля шкіри", size=18)
    return img


def sc_wind():
    img, d = canvas((130, 195, 255), (220, 240, 255))
    sun(d, 730, 80, 36)
    d.rectangle(B([0, 380, 360, 520]), fill=(70, 140, 210, 255))
    d.rectangle(B([360, 380, 830, 520]), fill=(205, 175, 115, 255))
    for x in range(20, 340, 60):
        d.arc(B([x, 400, x + 40, 420]), 200, 340, fill=(255, 255, 255, 220), width=px(3))
    poly_arrow(d, [(60, 355), (240, 350), (420, 355), (600, 350)], WHITE, 9, 26)
    poly_arrow(d, [(660, 340), (665, 280), (660, 220), (662, 170)], (255, 110, 60, 255), 9, 26)
    poly_arrow(d, [(640, 140), (450, 125), (250, 140), (150, 150)], (255, 255, 255, 235), 7, 22)
    poly_arrow(d, [(130, 175), (135, 230), (130, 290), (132, 335)], (60, 110, 230, 255), 8, 22)
    tag(d, 180, 440, "холодніша ділянка\n(вода)", size=20)
    tag(d, 590, 440, "тепліша ділянка\n(суша)", size=20)
    tag(d, 360, 300, "вітер: повітря тече туди, де тепліше", size=19)
    tag(d, 400, 80, "угорі повітря повертається", size=19)
    return img


def sc_pressure():
    img, d = canvas((150, 200, 250), (225, 240, 255))
    d.rectangle(B([0, 470, 830, 520]), fill=(96, 160, 90, 255))
    d.polygon([P((430, 470)), P((640, 250)), P((830, 470))], fill=(135, 122, 112, 255))
    d.polygon([P((600, 292)), P((640, 250)), P((680, 292)), P((660, 280)), P((640, 296)), P((620, 280))], fill=WHITE)
    for i in range(9):
        a = 70 + i * 16
        d.rounded_rectangle(B([110, 36 + i * 48, 330, 80 + i * 48]), radius=px(10), fill=(255, 255, 255, a))
    for i in range(5):
        a = 70 + i * 16
        d.rounded_rectangle(B([535, 36 + i * 42, 745, 76 + i * 42]), radius=px(10), fill=(255, 255, 255, a))
    for x in (160, 220, 280):
        arrow(d, (x, 60), (x, 150), (60, 100, 200, 255), 6, 18)
    for x in (580, 640, 700):
        arrow(d, (x, 60), (x, 130), (60, 100, 200, 255), 6, 18)
    tag(d, 220, 270, "повітря зверху багато —\nтиск більший", size=19)
    tag(d, 640, 160, "повітря менше —\nтиск нижчий", size=19)
    tag(d, 220, 495, "рівень моря: ≈ 1013 гПа", size=19)
    tag(d, 640, 495, "висота ≈ 1 км: ≈ 900 гПа", size=19)
    return img


def sc_cyclone():
    img, d = canvas((205, 225, 245), (235, 245, 255))
    d.line([P((415, 20)), P((415, 500))], fill=(120, 150, 200, 200), width=px(4))
    lc, rc = (207, 235), (623, 235)
    for a0 in (0, 90, 180, 270):
        spiral_arrow(d, lc[0], lc[1], 150, 42, a0, 140, True, (60, 100, 210, 255))
        spiral_arrow(d, rc[0], rc[1], 42, 150, a0, 140, False, (230, 110, 60, 255))
    d.ellipse(B([lc[0] - 32, lc[1] - 32, lc[0] + 32, lc[1] + 32]), fill=(50, 90, 200, 255))
    d.text(P(lc), "Н", font=F(36), fill=WHITE, anchor="mm")
    d.ellipse(B([rc[0] - 32, rc[1] - 32, rc[0] + 32, rc[1] + 32]), fill=(220, 80, 50, 255))
    d.text(P(rc), "В", font=F(36), fill=WHITE, anchor="mm")
    for x, y, s in ((60, 60, 0.6), (330, 70, 0.55), (60, 400, 0.55)):
        cloud(d, x, y, s, (150, 160, 180, 255))
    sun(d, 780, 70, 24, rays=True)
    tag(d, 207, 447, "ЦИКЛОН (низький тиск)\nповітря піднімається:\nхмари, вітер, опади", size=18)
    tag(d, 623, 447, "АНТИЦИКЛОН (високий тиск)\nповітря опускається:\nясно й спокійно", size=18)
    return img


def sc_fronts():
    img, d = canvas((200, 225, 250), (235, 244, 255))
    d.rectangle(B([0, 150, 415, 440]), fill=(255, 215, 170, 110))
    d.rectangle(B([415, 150, 830, 440]), fill=(255, 215, 170, 110))
    d.polygon([P((10, 440)), P((340, 440)), P((265, 250)), P((10, 250))], fill=(110, 155, 235, 215))
    d.rectangle(B([0, 440, 830, 520]), fill=(120, 150, 100, 255))
    cloud(d, 200, 175, 1.5, (110, 120, 140, 255))
    for x in (270, 300, 330, 360):
        d.line([P((x, 215)), P((x - 12, 260))], fill=(70, 100, 190, 255), width=px(4))
    arrow(d, (60, 345), (190, 345), WHITE, 8, 22)
    d.line([P((415, 20)), P((415, 500))], fill=(120, 150, 200, 200), width=px(4))
    d.polygon([P((470, 440)), P((830, 440)), P((830, 330))], fill=(110, 155, 235, 215))
    sl = lambda x: 440 - (x - 470) * (110 / 360)
    for k in range(3):
        off = 18 + k * 44
        d.polygon([P((470, sl(470) - off)), P((830, sl(830) - off)), P((830, sl(830) - off - 30)), P((470, sl(470) - off - 30))],
                  fill=(140, 150, 168, 170))
    for x in (560, 610, 660):
        d.line([P((x, sl(x) - 18)), P((x - 8, sl(x) + 5))], fill=(70, 100, 190, 255), width=px(3))
    arrow(d, (500, 330), (700, 265), (255, 120, 60, 255), 8, 22)
    tag(d, 207, 45, "ХОЛОДНИЙ ФРОНТ", size=22, bg=(55, 105, 220, 255), fg=WHITE)
    tag(d, 622, 45, "ТЕПЛИЙ ФРОНТ", size=22, bg=(220, 85, 65, 255), fg=WHITE)
    tag(d, 207, 485, "різкий підйом: злива,\nгроза, потім похолодання", size=18)
    tag(d, 622, 485, "повільний підйом: тривалі\nслабкі опади, потім потепління", size=18)
    return img


def sc_map():
    img, d = canvas((232, 242, 252), (232, 242, 252))
    d.rounded_rectangle(B([6, 6, 824, 514]), radius=px(20), outline=(150, 175, 215, 255), width=px(4))
    for rx, ry, n in ((55, 42, "1000"), (105, 80, "1005"), (155, 115, "1010"), (200, 148, "1015")):
        d.ellipse(B([215 - rx, 240 - ry, 215 + rx, 240 + ry]), outline=(95, 115, 160, 220), width=px(3))
    for rx, ry in ((50, 42), (100, 80), (150, 118), (200, 155)):
        d.ellipse(B([610 - rx, 320 - ry, 610 + rx, 320 + ry]), outline=(95, 115, 160, 220), width=px(3))
    front_line(d, [(255, 270), (300, 335), (370, 395), (470, 445)], "cold", (45, 95, 215, 255), side=-1)
    front_line(d, [(255, 245), (340, 225), (430, 195), (520, 160)], "warm", (215, 70, 55, 255), side=-1)
    d.ellipse(B([185, 210, 245, 270]), fill=(50, 90, 200, 255))
    d.text(P((215, 240)), "Н", font=F(34), fill=WHITE, anchor="mm")
    d.ellipse(B([580, 290, 640, 350]), fill=(220, 80, 50, 255))
    d.text(P((610, 320)), "В", font=F(34), fill=WHITE, anchor="mm")
    d.rounded_rectangle(B([488, 20, 818, 146]), radius=px(14), fill=(255, 255, 255, 245))
    d.line([P((506, 50)), P((570, 50))], fill=(95, 115, 160, 255), width=px(4))
    d.text(P((582, 50)), "ізобари (рівний тиск)", font=F(17), fill=INK, anchor="lm")
    front_line(d, [(506, 84), (570, 84)], "cold", (45, 95, 215, 255), side=1, step=30)
    d.text(P((582, 84)), "холодний фронт", font=F(17), fill=INK, anchor="lm")
    front_line(d, [(506, 128), (570, 128)], "warm", (215, 70, 55, 255), side=-1, step=30)
    d.text(P((582, 124)), "теплий фронт", font=F(17), fill=INK, anchor="lm")
    return img


def sc_bluesky():
    img, d = canvas((120, 190, 255), (215, 238, 255))
    rng = random.Random(5)
    d.rectangle(B([415, 0, 830, 520]), fill=(70, 80, 150, 255))
    for i in range(520):
        t = i / 519
        d.line([P((415, i)), P((830, i))], fill=(int(70 + 185 * t), int(80 + 110 * t), int(150 - 20 * t), 255), width=px(1.2))
    d.rectangle(B([0, 450, 415, 520]), fill=(96, 160, 90, 255))
    d.rectangle(B([415, 450, 830, 520]), fill=(45, 55, 80, 255))
    d.line([P((415, 20)), P((415, 500))], fill=WHITE, width=px(4))
    sun(d, 110, 85, 34)
    arrow(d, (135, 110), (300, 395), WHITE, 9, 24)
    for t in (0.35, 0.55, 0.75):
        x, y = 135 + 165 * t, 110 + 285 * t
        for k in range(6):
            a = math.radians(k * 60 + 20)
            arrow(d, (x, y), (x + 38 * math.cos(a), y + 38 * math.sin(a)), (50, 110, 255, 255), 4, 12)
    person(d, 320, 480, 0.42, scarf=False)
    sun(d, 470, 392, 44, (255, 150, 60, 255), rays=False)
    d.rectangle(B([415, 392, 830, 450]), fill=(0, 0, 0, 0))
    arrow(d, (520, 385), (735, 408), (255, 110, 60, 255), 9, 24)
    for x, y in ((560, 392), (620, 398), (680, 403)):
        arrow(d, (x, y), (x + 8, y - 48), (110, 160, 255, 200), 4, 12)
    person(d, 770, 480, 0.42, coat=(200, 60, 70), scarf=False)
    tag(d, 207, 42, "вдень: світло йде коротким шляхом", size=17)
    tag(d, 207, 495, "синє розсіюється всюди — небо блакитне", size=16)
    tag(d, 622, 42, "увечері: шлях через атмосферу довший", size=17)
    tag(d, 622, 495, "синє розсіялось — доходить червоне", size=16)
    return img


def sc_chance():
    img, d = canvas((200, 225, 250), (240, 248, 255))
    rainy = {1, 4, 6, 9}
    for i in range(10):
        c, r = i % 5, i // 5
        x0, y0 = 45 + c * 150, 100 + r * 140
        d.rounded_rectangle(B([x0, y0, x0 + 130, y0 + 120]), radius=px(18), fill=(255, 255, 255, 240))
        cx, cy = x0 + 65, y0 + 60
        if i in rainy:
            cloud(d, cx - 40, cy - 15, 0.62, (125, 140, 165, 255))
            for dx in (-22, 4, 30):
                drop(d, cx + dx, cy + 38, 6)
        else:
            sun(d, cx, cy, 20)
    tag(d, 415, 42, "ймовірність опадів 40%", size=26, bg=(28, 60, 120, 255), fg=WHITE)
    tag(d, 415, 410, "з 10 схожих днів у 4 були опади, у 6 — ні", size=21)
    tag(d, 415, 465, "це шанси, а не тривалість чи площа дощу", size=19)
    return img


SCENES = {
    "fog": sc_fog, "dew": sc_dew, "cloud": sc_cloud, "rain": sc_rain, "snow": sc_snow, "glaze": sc_glaze,
    "windchill": sc_windchill, "wind": sc_wind, "pressure": sc_pressure, "cyclone": sc_cyclone,
    "fronts": sc_fronts, "map": sc_map, "bluesky": sc_bluesky, "chance": sc_chance,
}


# ───────────── складання кадру ─────────────
def wrap(d, text, font, maxw):
    lines, cur = [], ""
    for w_ in text.split():
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def compose(key, img_title, steps, idx, total):
    img = vgrad(W, H, (226, 240, 255), (247, 250, 255))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle(B([30, 20, W - 30, 100]), radius=px(28), fill=NAVY)
    for size in range(44, 26, -2):
        if d.textlength(img_title, font=F(size)) <= px(W - 120):
            break
    d.text(P((W / 2, 60)), img_title, font=F(size), fill=WHITE, anchor="mm")

    scene = SCENES[key]()
    mask = Image.new("L", scene.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, scene.size[0] - 1, scene.size[1] - 1], radius=px(26), fill=255)
    img.paste(scene, P((30, 120)), mask)
    d.rounded_rectangle(B([30, 120, 30 + SW, 120 + SH]), radius=px(26), outline=(255, 255, 255, 255), width=px(4))

    x0, y0, x1, y1 = 880, 120, 1250, 640
    d.rounded_rectangle(B([x0, y0, x1, y1]), radius=px(26), fill=WHITE, outline=(200, 215, 240, 255), width=px(3))
    d.text(P(((x0 + x1) / 2, y0 + 36)), "Як це відбувається", font=F(26), fill=NAVY, anchor="mm")
    avail = (y1 - y0) - 100
    for size in range(24, 15, -1):
        font = F(size)
        blocks = [wrap(d, s, font, px(x1 - x0 - 115)) for s in steps]
        lh = size * 1.3
        total_h = sum(len(b) * lh for b in blocks) + 26 * (len(blocks) - 1)
        if total_h <= avail:
            break
    y = y0 + 80
    colors = [(255, 140, 60), (60, 150, 240), (70, 180, 110)]
    for i, b in enumerate(blocks):
        cy = y + 16
        d.ellipse(B([x0 + 22, cy - 22, x0 + 66, cy + 22]), fill=colors[i % 3] + (255,))
        d.text(P((x0 + 44, cy)), str(i + 1), font=F(26), fill=WHITE, anchor="mm")
        for j, ln in enumerate(b):
            d.text(P((x0 + 84, y + j * lh)), ln, font=font, fill=INK, anchor="la")
        y += len(b) * lh + 26
    d.text(P((30, 678)), f"Як працює погода · підцикл «Таємниць неба» · випуск {idx} з {total} · Сумський синоптик",
           font=F(19), fill=(70, 95, 140, 255), anchor="lm")
    return img.resize((W, H), Image.LANCZOS)


def render_issue(issue, idx, total):
    """Повертає JPEG-байти схеми для випуску idx (з 1)."""
    img = compose(issue["img"], issue["img_title"], issue["img_steps"], idx, total)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


if __name__ == "__main__":
    from yak_pratsyuye_pohoda_data import ISSUES
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    for i, it in enumerate(ISSUES, 1):
        with open(os.path.join(out, f"yak_pratsyuye_pohoda_preview_{i:02d}_{it['img']}.jpg"), "wb") as f:
            f.write(render_issue(it, i, len(ISSUES)))
    print(f"готово: {len(ISSUES)} схем у «{out}»")
