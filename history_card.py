"""Картинка-карточка для рубрики «Цього дня в історії Сум».

    from history_card import make_card
    make_card(14, 12, 1995, "Текст події ...", "card.png")

Нічого, крім matplotlib, не потрібно (шрифт DejaVu із кирилицею йде в комплекті).
Своя картинка = жодних проблем з авторськими правами на фото.
"""
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def make_card(day: int, month: int, year: int, text: str, out_path: str,
              source: str = "Сумський синоптик · За матеріалами Календаря знаменних і пам'ятних дат Сумщини (Сумська ОУНБ)"):
    W = H = 1080
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")

    # небо: вертикальний градієнт
    top, bottom = np.array([0x14, 0x2B, 0x4F]) / 255, np.array([0x3E, 0x7C, 0x9E]) / 255
    grad = np.linspace(0, 1, 256)[:, None, None]
    ax.imshow(top * (1 - grad) + bottom * grad, extent=[0, W, 0, H], aspect="auto", zorder=0)

    # сонце і пагорби
    ax.add_patch(plt.Circle((880, 330), 70, color="#F6D67A", alpha=0.9, zorder=1))
    x = np.linspace(0, W, 400)
    ax.fill_between(x, 0, 150 + 38 * np.sin(x / 140) + 20 * np.sin(x / 57), color="#1E4A5C", zorder=2)
    ax.fill_between(x, 0, 80 + 30 * np.sin(x / 190 + 1.5), color="#12303D", zorder=3)

    # дата
    ax.text(90, 960, f"{day} {MONTHS[month - 1].upper()}", color="white", fontsize=58, fontweight="bold", va="top", zorder=5)
    ax.text(90, 868, f"{year} рік", color="#F6D67A", fontsize=40, va="top", zorder=5)
    ax.text(90, 792, "ЦЬОГО ДНЯ В ІСТОРІЇ СУМЩИНИ", color="#BFD9E6", fontsize=18, va="top", zorder=5)
    ax.plot([90, 990], [760, 760], color="#BFD9E6", lw=1.5, alpha=0.6, zorder=5)

    # основний текст
    body = textwrap.fill(text, width=38)
    ax.text(90, 725, body, color="white", fontsize=27, va="top", linespacing=1.45, zorder=5)

    # підпис джерела
    ax.text(90, 52, textwrap.fill(source, width=70), color="#DCEAF1", fontsize=13, va="center", linespacing=1.4, zorder=6)
    fig.savefig(out_path, dpi=100)
    plt.close(fig)


if __name__ == "__main__":
    make_card(14, 12, 1995,
              "Створено регіональний ландшафтний парк «Сеймський» — найбільшу природно-заповідну територію Сумської області.",
              "sample_card_14-12.png")
