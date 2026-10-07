import datetime
import json
import os
import re
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from jinja2 import Template
from playwright.sync_api import sync_playwright

TZ = ZoneInfo("Europe/Kyiv")
CHANNEL_LINK = "t.me/your_channel"   # <- впишите сюда адрес своего канала (или оставьте "" чтобы скрыть)
FUEL_FILE = "fuel_prices.json"
FUEL_URL = "https://outsignal.com/energy/azs/sumy/"   # цены на АЗС Сумской области (обновляются ежедневно)
FUEL_MAX_AGE_DAYS = 3                # через сколько дней цены на топливо считаются устаревшими
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- 1. СБОР ДАННЫХ ---------------------------------------------------------


def delta(now, prev):
    """Изменение курса к предыдущему дню для отображения на картинке."""
    if now is None or prev is None:
        return None
    d = now - prev
    if abs(d) < 0.005:
        return {"dir": "flat", "arrow": "•", "text": "0.00"}
    return {"dir": "up" if d > 0 else "down", "arrow": "▲" if d > 0 else "▼", "text": f"{d:+.2f}"}


def nbu_rates(date=None):
    url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
    if date:
        url += f"&date={date:%Y%m%d}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    rates = {i["cc"]: i["rate"] for i in r.json()}
    return rates.get("USD"), rates.get("EUR")


def buy_sell(buy, sell):
    return f"{float(buy):.2f} / {float(sell):.2f}"


def get_currency_data():
    """Курсы НБУ (с динамикой), ПриватБанка (готівка) и Monobank.
    Если источник недоступен, показываем «—», а не выдуманные цифры."""
    rows, nbu = [], None

    try:
        usd, eur = nbu_rates()
        try:
            usd_p, eur_p = nbu_rates(datetime.date.today() - datetime.timedelta(days=1))
        except Exception:
            usd_p = eur_p = None
        nbu = {"usd": usd, "eur": eur, "usd_d": delta(usd, usd_p), "eur_d": delta(eur, eur_p)}
        rows.append({"name": "Нацбанк (НБУ)", "usd": f"{usd:.2f}", "eur": f"{eur:.2f}",
                     "usd_d": nbu["usd_d"], "eur_d": nbu["eur_d"]})
    except Exception as e:
        print(f"::warning::НБУ недоступен: {e}")
        rows.append({"name": "Нацбанк (НБУ)", "usd": "—", "eur": "—"})

    try:
        r = requests.get("https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5",
                         headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        u = next((i for i in data if i["ccy"] == "USD"), None)
        e = next((i for i in data if i["ccy"] == "EUR"), None)
        rows.append({"name": "ПриватБанк", "usd": buy_sell(u["buy"], u["sale"]) if u else "—",
                     "eur": buy_sell(e["buy"], e["sale"]) if e else "—"})
    except Exception as e:
        print(f"::warning::ПриватБанк недоступен: {e}")
        rows.append({"name": "ПриватБанк", "usd": "—", "eur": "—"})

    try:
        r = requests.get("https://api.monobank.ua/bank/currency", headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()

        def mono(code):
            i = next((x for x in data if x.get("currencyCodeA") == code and x.get("currencyCodeB") == 980), None)
            return buy_sell(i["rateBuy"], i["rateSell"]) if i and "rateBuy" in i and "rateSell" in i else "—"

        rows.append({"name": "Monobank", "usd": mono(840), "eur": mono(978)})
    except Exception as e:
        print(f"::warning::Monobank недоступен: {e}")
        rows.append({"name": "Monobank", "usd": "—", "eur": "—"})

    return rows, nbu


def price(text):
    m = re.search(r"\d{2,3}[.,]\d{2}", text or "")
    return float(m.group().replace(",", ".")) if m else None


def col_key(text):
    """Нормализация заголовка колонки: без стрелок/пробелов, латинская A -> кириллическая А."""
    return re.sub(r"[^\w+\-]", "", text or "").upper().replace("A", "А")


def fetch_fuel_html():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(user_agent=HEADERS["User-Agent"], locale="uk-UA")
                page.goto(FUEL_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector("table", timeout=20000)
                return page.content()
            finally:
                browser.close()
    except Exception as e:
        print(f"::warning::Браузер не открыл {FUEL_URL}: {e}. Пробуем обычный запрос.")
        r = requests.get(FUEL_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text


def parse_fuel_html(html):
    """Возвращает (список сетей, дата данных, средняя по области | None)."""
    soup = BeautifulSoup(html, "html.parser")
    m = re.search(r"Станом на\s+(\d{2})\.(\d{2})\.(\d{4})", soup.get_text(" ", strip=True))
    if not m:
        raise ValueError("не найдена дата 'Станом на ...'")
    updated = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    stations, avg = [], None
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if not rows:
            continue
        head = [col_key(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
        if not head or not all(k in head for k in ("А-95", "ДП", "ГАЗ")):
            continue
        ia, idp, ig = head.index("А-95"), head.index("ДП"), head.index("ГАЗ")
        need = max(ia, idp, ig)
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) <= need:
                continue
            name = cells[0].get_text(" ", strip=True)
            vals = {"a95": price(cells[ia].get_text(" ", strip=True)),
                    "dp": price(cells[idp].get_text(" ", strip=True)),
                    "gas": price(cells[ig].get_text(" ", strip=True))}
            if head[0].startswith("МЕРЕЖА"):
                if name and any(v is not None for v in vals.values()):
                    stations.append({"name": name, **vals})
            elif head[0].startswith("ОБЛАСТЬ") and "Сумськ" in name:
                avg = vals

    stations.sort(key=lambda x: (x["a95"] is None, x["a95"] or 0))
    return stations[:8], updated, avg


def get_fuel_data():
    """Цены на АЗС Сумской области: парсим сайт; при сбое берём fuel_prices.json."""
    source = "outsignal.com"
    try:
        stations, updated, avg = parse_fuel_html(fetch_fuel_html())
        if not stations:
            raise ValueError("таблица с сетями пуста")
    except Exception as e:
        print(f"::warning::Не удалось получить цены на топливо автоматически ({e}). Беру {FUEL_FILE}.")
        with open(FUEL_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        stations, avg = d["stations"], d.get("average")
        updated = datetime.date.fromisoformat(d["updated"])
        source = "відкриті дані мереж"

    best = {}
    for key in ("a95", "dp", "gas"):
        vals = [s[key] for s in stations if s.get(key) is not None]
        low = min(vals) if vals else None
        if low is not None:
            best[key] = (low, next(s["name"] for s in stations if s.get(key) == low))
        for s in stations:
            s[key + "_s"] = f"{s[key]:.2f}" if s.get(key) is not None else "—"
            s[key + "_best"] = low is not None and s.get(key) == low

    age = (datetime.datetime.now(TZ).date() - updated).days
    if age > FUEL_MAX_AGE_DAYS:
        print(f"::warning::Цены на топливо устарели: данные от {updated:%d.%m.%Y} ({age} дн.).")
    return stations, updated, best, avg, source


# --- 2. КАРТИНКА ------------------------------------------------------------

def generate_image(currency_data, fuel_data, fuel_date, date_str, fuel_avg, fuel_source):
    with open("template.html", "r", encoding="utf-8") as f:
        template = Template(f.read(), autoescape=True)

    avg_s = ({k: (f"{fuel_avg[k]:.2f}" if fuel_avg.get(k) is not None else "—") for k in ("a95", "dp", "gas")}
             if fuel_avg else None)
    html = template.render(date_str=date_str, currency_data=currency_data, fuel_data=fuel_data,
                           fuel_date=f"{fuel_date:%d.%m.%Y}", fuel_avg=avg_s, fuel_source=fuel_source,
                           channel=CHANNEL_LINK)
    file_path = os.path.abspath("rendered.html")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        # 1080x1350 (4:5) в 1.5x = 1620x2025 px: чёткий текст на телефоне
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1.5)
        page.goto(f"file://{file_path}", wait_until="load")
        page.evaluate("document.fonts.ready")
        page.screenshot(path="card.png", full_page=True)
        browser.close()


# --- 3. TELEGRAM ------------------------------------------------------------

def send_to_telegram(photo_path, caption_text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise ValueError("Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены в окружении!")

    with open(photo_path, "rb") as photo:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendPhoto",
            data={"chat_id": chat_id, "caption": caption_text, "parse_mode": "HTML"},
            files={"photo": photo}, timeout=60)
    if response.status_code == 200:
        print("Успешно отправлено в Telegram!")
    else:
        print(f"Ошибка отправки: {response.status_code}, {response.text}")
        response.raise_for_status()


# --- 4. ПОДПИСЬ (строится из реальных данных, без «выдуманных» выводов) ------

def build_caption(date_str, nbu, best, fuel_date, avg):
    lines = [f"<b>📊 Курси валют і ціни на пальне — {date_str}</b>", ""]

    if nbu:
        def line(code, val, d):
            tail = f" ({d['arrow']} {d['text']})" if d else ""
            return f"{code} — <b>{val:.2f} грн</b>{tail}"
        lines += ["<b>💵 Офіційний курс НБУ:</b>",
                  line("USD", nbu["usd"], nbu["usd_d"]),
                  line("EUR", nbu["eur"], nbu["eur_d"]), ""]

    if best:
        names = {"a95": "А-95", "dp": "ДП", "gas": "Газ"}
        lines.append(f"<b>⛽ Найнижчі ціни на АЗС Сумщини</b> (станом на {fuel_date:%d.%m}):")
        for k in ("a95", "dp", "gas"):
            if k in best:
                lowest, who = best[k]
                lines.append(f"{names[k]} — <b>{lowest:.2f} грн</b> ({who})")
        if avg and all(avg.get(k) is not None for k in ("a95", "dp", "gas")):
            lines.append(f"<i>У середньому по області: А-95 — {avg['a95']:.2f}, "
                         f"ДП — {avg['dp']:.2f}, газ — {avg['gas']:.2f}</i>")
        lines.append("")

    lines.append("#Суми #КурсВалют #ПальнеСуми #Економіка")
    return "\n".join(lines)


# --- 5. ЗАПУСК --------------------------------------------------------------

if __name__ == "__main__":
    date_str = datetime.datetime.now(TZ).strftime("%d.%m.%Y")

    print(f"[{date_str}] Собираем данные...")
    currencies, nbu = get_currency_data()
    fuels, fuel_date, best, fuel_avg, fuel_source = get_fuel_data()

    print("Генерируем картинку...")
    generate_image(currencies, fuels, fuel_date, date_str, fuel_avg, fuel_source)

    print("Отправляем в Telegram...")
    send_to_telegram("card.png", build_caption(date_str, nbu, best, fuel_date, fuel_avg))
