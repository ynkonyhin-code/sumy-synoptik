from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1080, 1350
BG = "#101B2D"
PANEL = "#1B2A40"
GOLD = "#E7BD69"
WHITE = "#F7F4EC"
MUTED = "#AAB7C7"

METAL_NAMES = {
    "XAU": "Золото",
    "XAG": "Срібло",
    "XPT": "Платина",
    "XPD": "Паладій",
}


def load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]

    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)

    return ImageFont.load_default()


def format_price(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def create_card(rates: dict, rate_date: str, output_path: str = "Koshtovnosti_card.png"):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    font_title = load_font(58, bold=True)
    font_subtitle = load_font(28)
    font_metal = load_font(34, bold=True)
    font_price = load_font(38, bold=True)
    font_small = load_font(22)

    draw.rounded_rectangle(
        (54, 54, WIDTH - 54, HEIGHT - 54),
        radius=34,
        fill=PANEL,
        outline="#34445A",
        width=2,
    )

    draw.text((100, 112), "КОШТОВНОСТІ", font=font_title, fill=GOLD)
    draw.text((104, 192), "Банківські метали • офіційні дані НБУ",
              font=font_subtitle, fill=WHITE)
    draw.text((104, 244), f"Дата курсу: {rate_date}",
              font=font_small, fill=MUTED)

    y = 330
    for code in ("XAU", "XAG", "XPT", "XPD"):
        if code not in rates:
            continue

        draw.rounded_rectangle(
            (92, y, WIDTH - 92, y + 150),
            radius=22,
            fill="#22344C",
        )
        draw.text((128, y + 28), METAL_NAMES[code],
                  font=font_metal, fill=WHITE)
        draw.text(
            (128, y + 83),
            f"{format_price(rates[code])} грн / г",
            font=font_price,
            fill=GOLD,
        )
        y += 174

    note_y = min(y + 16, HEIGHT - 250)
    draw.text((104, note_y), "Окремий курс ломбардів",
              font=font_metal, fill=WHITE)
    draw.text((104, note_y + 58), "Не підключено: тарифи залежать від",
              font=font_small, fill=MUTED)
    draw.text((104, note_y + 91), "ломбарду та проби виробу.",
              font=font_small, fill=MUTED)

    footer_y = HEIGHT - 132
    draw.line((104, footer_y - 24, WIDTH - 104, footer_y - 24),
              fill="#40516A", width=2)
    draw.text((104, footer_y), "Офіційний орієнтир НБУ — не ціна викупу виробів.",
              font=font_small, fill=MUTED)

    image.save(output_path, "PNG")
    return output_path


if __name__ == "__main__":
    sample = {"XAU": 2860.50, "XAG": 31.20, "XPT": 1050.00, "XPD": 980.00}
    today = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y")
    create_card(sample, today)
    print("Створено Koshtovnosti_card.png")
