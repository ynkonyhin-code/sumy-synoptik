"""Генератор картинок для rukh_troleybusiv: радісний та сумний тролейбус (Pillow)."""
import os
import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
SS = 2  # supersampling для гладких ліній

HAPPY_VARIANTS = ["sunny", "sunset", "rainbow", "spring"]
SAD_VARIANTS = ["rain", "night", "storm", "fog"]

SKY = {
    "sunny": ((92, 178, 255), (200, 235, 255)),
    "sunset": ((120, 90, 180), (255, 175, 105)),
    "rainbow": ((110, 190, 255), (215, 240, 255)),
    "spring": ((130, 205, 255), (225, 245, 230)),
    "rain": ((105, 115, 135), (170, 178, 190)),
    "night": ((15, 20, 50), (45, 55, 100)),
    "storm": ((45, 50, 72), (110, 115, 135)),
    "fog": ((170, 178, 185), (215, 218, 222)),
}
# (колір будинків, колір вікон)
CITY = {
    "sunny": ((150, 185, 225), (235, 245, 255)),
    "sunset": ((150, 100, 150), (255, 220, 150)),
    "rainbow": ((160, 190, 225), (240, 248, 255)),
    "spring": ((160, 200, 205), (240, 250, 245)),
    "rain": ((105, 115, 130), (140, 150, 165)),
    "night": ((24, 30, 58), (255, 214, 100)),
    "storm": ((70, 76, 95), (110, 118, 135)),
    "fog": ((160, 168, 176), (190, 196, 202)),
}


def b(box):
    return tuple(int(round(v * SS)) for v in box)


def px(v):
    return int(round(v * SS))


def gradient(top, bottom):
    img = Image.new("RGB", (W * SS, H * SS))
    d = ImageDraw.Draw(img)
    for y in range(H * SS):
        t = y / (H * SS - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (W * SS, y)], fill=c)
    return img


def cloud(d, x, y, s=1.0, color=(255, 255, 255, 235)):
    for dx, dy, r in [(0, 0, 38), (40, -18, 48), (88, 0, 40), (44, 12, 40)]:
        d.ellipse(b([x + (dx - r) * s, y + (dy - r) * s, x + (dx + r) * s, y + (dy + r) * s]), fill=color)


def sun(d, x, y, r, color=(255, 214, 60)):
    for k in range(6, 0, -1):
        rr = r + k * 14
        d.ellipse(b([x - rr, y - rr, x + rr, y + rr]), fill=(255, 240, 150, 20))
    d.ellipse(b([x - r, y - r, x + r, y + r]), fill=color + (255,))


def heart(d, x, y, s, color):
    r = 10 * s
    d.ellipse(b([x - 2 * r, y - r, x, y + r]), fill=color)
    d.ellipse(b([x, y - r, x + 2 * r, y + r]), fill=color)
    d.polygon([b([x - 2 * r + 1, y + r * 0.35, x + 2 * r - 1, y + r * 0.35, x, y + r * 2.6])[i:i + 2]
               for i in (0, 2, 4)], fill=color)


def sparkle(d, x, y, r, color):
    pts = [(x, y - r), (x + r * .25, y - r * .25), (x + r, y), (x + r * .25, y + r * .25),
           (x, y + r), (x - r * .25, y + r * .25), (x - r, y), (x - r * .25, y - r * .25)]
    d.polygon([(px(a), px(c)) for a, c in pts], fill=color)


def skyline(d, rng, color, win_color, lit=False):
    x, base = -20, 600
    while x < W:
        w, h = rng.randint(70, 140), rng.randint(120, 300)
        d.rectangle(b([x, base - h, x + w, base]), fill=color + (255,))
        for wx in range(x + 12, x + w - 18, 26):
            for wy in range(base - h + 16, base - 30, 34):
                if rng.random() < (0.5 if lit else 0.6):
                    d.rectangle(b([wx, wy, wx + 12, wy + 18]), fill=win_color + (255,))
        x += w + rng.randint(0, 14)


def rainbow(d, cx, cy):
    cols = [(255, 70, 70), (255, 150, 50), (255, 230, 60), (90, 200, 90),
            (70, 150, 255), (110, 90, 220), (170, 90, 200)]
    for i, c in enumerate(cols):
        r = 430 - i * 16
        d.arc(b([cx - r, cy - r, cx + r, cy + r]), 180, 360, fill=c + (220,), width=px(16))


def bolt(d, cx, cy, s, fill, outline=None):
    rel = [(0, -40), (-22, 6), (-4, 6), (-12, 40), (24, -8), (5, -8), (18, -40)]
    pts = [(px(cx + a * s), px(cy + c * s)) for a, c in rel]
    d.polygon(pts, fill=fill, outline=outline)


def draw_bus(d, happy):
    body = (30, 120, 220) if happy else (108, 122, 148)
    roof = (245, 248, 255) if happy else (190, 196, 208)
    stripe = (255, 214, 10) if happy else (168, 160, 112)
    glass = (190, 232, 255) if happy else (52, 60, 80)
    dark = (30, 34, 44)

    # тінь
    d.ellipse(b([300, 598, 990, 630]), fill=(0, 0, 0, 70))
    # колісні арки
    for wx in (430, 850):
        d.ellipse(b([wx - 58, 507, wx + 58, 623]), fill=dark + (255,))
    # корпус
    d.rounded_rectangle(b([300, 330, 980, 565]), radius=px(30), fill=body + (255,))
    d.rounded_rectangle(b([300, 330, 980, 356]), radius=px(14), fill=roof + (255,))
    d.rectangle(b([300, 500, 980, 520]), fill=stripe + (255,))
    # вікна
    for x0 in (330, 435, 540, 645):
        d.rounded_rectangle(b([x0, 368, x0 + 90, 448]), radius=px(10), fill=glass + (255,))
        if happy:
            d.line(b([x0 + 12, 440, x0 + 40, 376]), fill=(255, 255, 255, 150), width=px(5))
    d.rounded_rectangle(b([765, 355, 955, 482]), radius=px(18), fill=glass + (255,))
    # колеса
    for wx in (430, 850):
        d.ellipse(b([wx - 48, 517, wx + 48, 613]), fill=(20, 22, 28, 255))
        d.ellipse(b([wx - 26, 539, wx + 26, 591]), fill=(170, 175, 185, 255))
        d.ellipse(b([wx - 8, 557, wx + 8, 573]), fill=(90, 95, 105, 255))
    # фари
    if happy:
        d.polygon([(px(975), px(520)), (px(1150), px(470)), (px(1150), px(575))], fill=(255, 240, 130, 70))
        d.ellipse(b([951, 506, 979, 534]), fill=(255, 244, 140, 255))
    else:
        d.ellipse(b([951, 506, 979, 534]), fill=(95, 100, 112, 255))
    d.ellipse(b([308, 508, 326, 526]), fill=(235, 60, 60, 255) if happy else (120, 80, 85, 255))

    # обличчя
    ex = (820, 900)
    for x in ex:
        d.ellipse(b([x - 21, 389, x + 21, 431]), fill=(255, 255, 255, 255), outline=dark + (255,), width=px(3))
    if happy:
        for x in ex:
            d.ellipse(b([x - 5, 399, x + 13, 417]), fill=dark + (255,))
            d.ellipse(b([x + 3, 401, x + 8, 406]), fill=(255, 255, 255, 255))
        d.arc(b([835, 425, 885, 468]), 10, 170, fill=dark + (255,), width=px(5))
        for cx in (788, 932):
            d.ellipse(b([cx - 14, 442, cx + 14, 460]), fill=(255, 120, 150, 140))
    else:
        for x in ex:
            d.ellipse(b([x - 8, 408, x + 8, 424]), fill=dark + (255,))
        d.line(b([794, 384, 842, 366]), fill=dark + (255,), width=px(5))
        d.line(b([878, 366, 926, 384]), fill=dark + (255,), width=px(5))
        d.arc(b([835, 456, 885, 498]), 195, 345, fill=dark + (255,), width=px(5))
        for ty, tw in ((440, 7), (466, 6)):
            d.ellipse(b([806 - tw, ty - 10, 806 + tw, ty + 10]), fill=(110, 190, 255, 235))

    # штанги та дроти
    if happy:
        for (bx, tx, ty) in ((505, 350, 150), (530, 375, 164)):
            d.line(b([bx, 332, tx, ty]), fill=(40, 44, 54, 255), width=px(6))
        for (tx, ty) in ((350, 150), (375, 164)):
            sparkle(d, tx, ty - 2, 18, (255, 235, 90, 255))
    else:
        for (bx, tx, ty) in ((505, 390, 245), (530, 418, 258)):
            d.line(b([bx, 332, tx, ty]), fill=(50, 54, 64, 255), width=px(6))
        # знак «немає струму»
        cx, cy = 700, 235
        d.ellipse(b([cx - 60, cy - 60, cx + 60, cy + 60]), fill=(255, 255, 255, 215))
        bolt(d, cx, cy, 1.2, (245, 200, 50, 255), (60, 50, 20, 255))
        d.ellipse(b([cx - 56, cy - 56, cx + 56, cy + 56]), outline=(220, 40, 40, 255), width=px(8))
        d.line(b([cx - 40, cy - 40, cx + 40, cy + 40]), fill=(220, 40, 40, 255), width=px(8))


def draw_caption(d):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "DejaVuSans-Bold.ttf", "arialbd.ttf"):
        try:
            font = ImageFont.truetype(path, px(26))
            break
        except OSError:
            font = None
    if not font:
        return
    text = "Сумський синоптик"
    tw = d.textlength(text, font=font)
    d.rounded_rectangle([px(24), px(660), px(24) + tw + px(36), px(700)], radius=px(18), fill=(0, 0, 0, 120))
    d.text((px(42), px(664)), text, font=font, fill=(255, 255, 255, 235))


def render(variant, happy):
    top, bottom = SKY[variant]
    img = gradient(top, bottom)  # RGB: тоді Draw("RGBA") коректно змішує прозорість
    d = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(variant)

    # небо
    if variant == "sunny":
        sun(d, 1080, 130, 70)
        cloud(d, 160, 120, 1.2)
        cloud(d, 620, 80, 0.9)
    elif variant == "sunset":
        sun(d, 900, 440, 95, (255, 205, 90))
        cloud(d, 150, 130, 1.2, (255, 205, 205, 210))
        cloud(d, 560, 90, 0.9, (255, 220, 200, 200))
    elif variant == "rainbow":
        rainbow(d, 700, 610)
        cloud(d, 140, 110, 1.2)
        cloud(d, 1010, 90, 1.0)
    elif variant == "spring":
        sun(d, 200, 110, 60)
        cloud(d, 700, 100, 1.1)
        cloud(d, 1050, 170, 0.8)
    elif variant == "rain":
        for x, y, s in ((100, 110, 1.4), (420, 70, 1.2), (760, 120, 1.5), (1080, 80, 1.3)):
            cloud(d, x, y, s, (118, 126, 142, 255))
    elif variant == "night":
        for _ in range(70):
            sparkle(d, rng.randint(10, W - 10), rng.randint(10, 300), rng.choice((3, 4, 6)), (255, 255, 225, 230))
        d.ellipse(b([1012, 72, 1108, 168]), fill=(245, 245, 220, 255))
        d.ellipse(b([1036, 58, 1126, 148]), fill=(22, 28, 62, 255))
    elif variant == "storm":
        for x, y, s in ((90, 100, 1.6), (460, 60, 1.5), (820, 110, 1.7), (1130, 70, 1.4)):
            cloud(d, x, y, s, (62, 66, 86, 255))
        bolt(d, 330, 190, 2.2, (255, 240, 120, 255))
    elif variant == "fog":
        cloud(d, 200, 140, 1.5, (235, 238, 240, 200))
        cloud(d, 800, 110, 1.6, (235, 238, 240, 200))

    city, win = CITY[variant]
    skyline(d, rng, city, win, lit=(variant == "night"))

    # дорога
    road = (75, 80, 90) if happy else (58, 62, 70)
    walk = (195, 195, 195) if happy else (125, 130, 138)
    d.rectangle(b([0, 590, W, 606]), fill=walk + (255,))
    d.rectangle(b([0, 606, W, H]), fill=road + (255,))
    for x in range(0, W, 120):
        d.rounded_rectangle(b([x, 668, x + 60, 678]), radius=px(4), fill=(235, 235, 235, 230))
    if not happy and variant in ("rain", "storm", "fog"):
        for x, y, w in ((180, 650, 150), (980, 690, 190)):
            d.ellipse(b([x, y, x + w, y + 24]), fill=(150, 175, 205, 130))
    if variant == "spring":
        for x in range(30, W, 55):
            c = rng.choice([(255, 120, 160), (255, 220, 80), (255, 255, 255)])
            d.ellipse(b([x - 6, 580, x + 6, 592]), fill=c + (255,))
            d.line(b([x, 592, x, 598]), fill=(60, 160, 70, 255), width=px(2))

    # стовпи та дроти
    pole = (60, 64, 74, 255)
    for x in (110, 1170):
        d.rectangle(b([x - 6, 140, x + 6, 592]), fill=pole)
        d.line(b([x, 150, x + (60 if x < 600 else -60), 150]), fill=pole, width=px(6))
    for y in (150, 164):
        d.line(b([0, y, W, y]), fill=(30, 32, 38, 255), width=px(3))

    draw_bus(d, happy)

    # ефекти поверх
    if happy:
        for y in (410, 455, 500):
            d.line(b([130 + (y % 40), y, 270 + (y % 30), y]), fill=(255, 255, 255, 190), width=px(7))
        heart(d, 560, 270, 1.3, (255, 90, 130, 235))
        heart(d, 640, 215, 1.0, (255, 130, 160, 220))
        heart(d, 730, 265, 1.1, (255, 100, 140, 230))
        for x, y, r in ((300, 250, 14), (1020, 300, 12), (880, 240, 16), (200, 330, 10)):
            sparkle(d, x, y, r, (255, 255, 255, 235))
    if variant in ("rain", "storm"):
        for _ in range(170):
            x, y = rng.randint(0, W), rng.randint(0, H)
            d.line(b([x, y, x - 8, y + 24]), fill=(205, 220, 240, 190), width=px(2))
    if variant == "fog":
        for y in (360, 470, 570):
            d.ellipse(b([-100, y, W + 100, y + 90]), fill=(240, 242, 244, 70))

    draw_caption(d)
    return img.convert("RGB").resize((W, H), Image.LANCZOS)


def generate_image(mood, avoid=None):
    """mood: 'happy' | 'sad'. Повертає (jpeg_bytes, variant). avoid — варіант, який не повторювати."""
    pool = HAPPY_VARIANTS if mood == "happy" else SAD_VARIANTS
    choices = [v for v in pool if v != avoid] or pool
    variant = random.choice(choices)
    buf = BytesIO()
    render(variant, mood == "happy").save(buf, "JPEG", quality=92)
    return buf.getvalue(), variant


if __name__ == "__main__":
    for m, vs in (("happy", HAPPY_VARIANTS), ("sad", SAD_VARIANTS)):
        for v in vs:
            render(v, m == "happy").save(f"rukh_troleybusiv_preview_{v}.jpg", quality=90)
