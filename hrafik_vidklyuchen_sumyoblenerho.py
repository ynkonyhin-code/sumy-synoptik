"""Сумський синоптик: графік погодинних відключень -> картинка + текст з ТГ Сумиобленерго.

Запуск:
  python hrafik_vidklyuchen_sumyoblenerho.py --sample --dry-run   # тест на sample.json, без публікації (створить out.png)
  python hrafik_vidklyuchen_sumyoblenerho.py --dry-run            # реальні дані, без публікації
  python hrafik_vidklyuchen_sumyoblenerho.py                      # бойовий режим (потрібні BOT_TOKEN, CHAT_ID)
"""
import hashlib, json, os, re, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from bs4 import BeautifulSoup

API_URL = os.getenv("SOE_API_URL", "https://www.soe.com.ua/api/vidkluchenya/get_all_data_disconnections_api")
TG_URL = "https://t.me/s/SumyEnergo"
STATE = Path("hrafik_vidklyuchen_sumyoblenerho_state.json")
OUT = Path("hrafik_vidklyuchen_sumyoblenerho_out.png")
TZ = ZoneInfo("Europe/Kyiv")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
# погодинн* + відключ*, ГАВ/СГАВ, «Оновлено дані по відключенням»
KEYWORDS = re.compile(r"погодинн\w*\s+відключ|\bС?ГАВ\b|аварійн\w*\s+відключ|Оновлено\s+дані\s+по\s+відключ", re.I)
SOURCE = "Джерело: АТ «Сумиобленерго»"


# ---------- дані ----------
def fetch_schedule(sample=False):
    if sample:
        return json.loads(Path("hrafik_vidklyuchen_sumyoblenerho_sample.json").read_text(encoding="utf-8"))["data"]
    r = requests.get(API_URL, timeout=30, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.soe.com.ua/", "x-source": "soe-website"})
    r.raise_for_status()
    return r.json()["data"]


def schedule_hash(rows):
    core = [(r["cherga_n"], [(i["start_time"], i["end_time"]) for i in r["lst_time_disc"]]) for r in rows]
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


def latest_tg_post():
    r = requests.get(TG_URL, timeout=30, headers={"User-Agent": UA})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for msg in reversed(soup.select(".tgme_widget_message")):
        t = msg.select_one(".tgme_widget_message_text")
        if not t:
            continue
        text = t.get_text("\n").strip()
        if KEYWORDS.search(text):
            return {"id": msg.get("data-post", ""), "text": text}
    return None


# ---------- картинка ----------
def _t(s):
    h, m = s.split(":")
    return int(h) + int(m) / 60


def intervals(row):
    out = []
    for i in row["lst_time_disc"]:
        s, e = _t(i["start_time"]), _t(i["end_time"])
        if e == 0 or e == s:
            out.append((s, 24.0, i))
        elif e < s:                      # перехід через північ
            out += [(s, 24.0, i), (0.0, e, i)]
        else:
            out.append((s, e, i))
    return out


def render(rows, path=OUT):
    upd = rows[0]["last_update"] if rows else ""
    today = datetime.now(TZ).strftime("%d.%m.%Y")
    n = len(rows)
    fig, ax = plt.subplots(figsize=(11, 1.6 + 0.62 * n), dpi=150)
    fig.patch.set_facecolor("#f5f8fd")
    ax.set_facecolor("white")
    for y, row in enumerate(rows):
        if y % 2 == 0:
            ax.axhspan(y - .5, y + .5, color="#f1f5fb", zorder=0)
        if not row["lst_time_disc"]:
            ax.text(0.3, y, "відключень не заплановано", va="center", fontsize=9, color="#9aa7b8", style="italic")
        for s, e, i in intervals(row):
            ax.barh(y, e - s, left=s, height=.62, color="#dce9fb", edgecolor="#5b8fd9", linewidth=1.2, zorder=3)
            label = f'{i["start_time"]}–{i["end_time"]}'
            if e - s >= 3:
                ax.text((s + e) / 2, y, label, ha="center", va="center", fontsize=9, fontweight="bold", color="#1d3557", zorder=4)
            else:
                ax.text((s + e) / 2, y - .42, label, ha="center", va="bottom", fontsize=7, color="#1d3557", zorder=4)
    ax.set_xlim(0, 24)
    ax.set_ylim(n - .5, -.5)
    ax.set_xticks(range(0, 25, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 25, 2)], fontsize=9)
    ax.xaxis.tick_top()
    ax.grid(axis="x", color="#d5deea", linewidth=.8, zorder=1)
    ax.set_yticks(range(n))
    ax.set_yticklabels([f'Черга {r["cherga_n"]}' for r in rows], fontsize=10, fontweight="bold", color="#1d3557")
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    fig.suptitle(f"Графік погодинних відключень · Сумщина · {today}", x=.02, y=.985, ha="left", fontsize=15, fontweight="bold", color="#1d3557")
    fig.text(.02, .02, f"{upd}  ·  Джерело: АТ «Сумиобленерго»  ·  Сумський синоптик", fontsize=8.5, color="#6b7b90")
    fig.subplots_adjust(left=.11, right=.985, top=1 - (0.75 / (1.6 + .62 * n)) - .035, bottom=.075 + .2 / n)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


# ---------- Telegram ----------
def tg_api(method, **kw):
    token = os.environ["BOT_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=60, **kw)
    r.raise_for_status()
    return r.json()


def publish_photo(path, caption):
    chat = os.environ["CHAT_ID"]
    long_text = len(caption) > 1024
    short = caption[:1000].rsplit("\n", 1)[0] if long_text else caption
    with open(path, "rb") as f:
        tg_api("sendPhoto", data={"chat_id": chat, "caption": short if not long_text else "⚡ Графік погодинних відключень"}, files={"photo": f})
    if long_text:
        tg_api("sendMessage", data={"chat_id": chat, "text": caption, "disable_web_page_preview": True})


def publish_text(text):
    tg_api("sendMessage", data={"chat_id": os.environ["CHAT_ID"], "text": text, "disable_web_page_preview": True})


# ---------- головна логіка ----------
def main():
    sample, dry = "--sample" in sys.argv, "--dry-run" in sys.argv
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    rows = fetch_schedule(sample)
    try:
        post = latest_tg_post()
    except Exception as e:
        print("TG scrape failed:", e)
        post = None

    h = schedule_hash(rows)
    body = (post["text"] + "\n\n" if post else f'{rows[0]["last_update"]}\n\n') + SOURCE

    if h != state.get("hash"):
        print("Новий графік -> картинка + текст")
        render(rows)
        if dry:
            print(body)
            return
        publish_photo(OUT, body)
        state["hash"] = h
        if post:
            state["tg_id"] = post["id"]
    elif post and post["id"] != state.get("tg_id"):
        print("Новий пост з ключовими словами -> лише текст")
        if dry:
            print(body)
            return
        publish_text(body)
        state["tg_id"] = post["id"]
    else:
        print("Без змін")
        return
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
