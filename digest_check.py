# -*- coding: utf-8 -*-
"""Перевірка: чи все, що має виходити строго за розкладом, потрапило в «Підсумок тижня».

Джерело правди — .github/workflows/*.yml (усі cron-слоти). Кожен workflow зі schedule
отримує категорію:
  journal — подія журналу (journal/events/<тип>): підсумок рахує її автоматично;
  db      — пише в synoptic.db;
  none    — дані ніде не зберігаються, у підсумок не входить (саме це й шукаємо).

    python digest_check.py            # таблиця + підсумок
    python digest_check.py --md       # ще й markdown-таблицю для README
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WF_DIR = Path(".github/workflows")
PY = Path(".")

# Розклад за Києвом (літо/зима) -> опис. Тут те, що має виходити щодня у фіксований час.
FIXED = {
    "shchodennyy_kalendar.yml": "Щоденний календар 10:00",
    "weather.yml": "Погода 07:00 / 13:00 / 19:00",
    "tomorrow_morning.yml": "Tomorrow.io 07:00",
    "horoskop_dnia.yml": "Гороскоп дня 07:00",
    "poyizdy_do_yevropy.yml": "Поїзди до Європи 08:00",
    "daily_rates.yml": "Курси валют і пальне 08:00",
    "oblast_daily.yml": "Сумщина: прогноз 09:00",
    "space-daily.yml": "Магнітне поле 09:00",
    "weather-on-this-day.yml": "Цей день у погоді 10:00",
    "kurs_dorohotsinnykh_metaliv.yml": "Дорогоцінні метали 11:00",
    "kurs_kryptovalyut.yml": "Криптовалюти 12:00",
    "nebo_nad_sumamy.yml": "Небо над Сумами 16:00",
    "khvylynka_tepla.yml": "Хвилинка тепла 19:00",
    "pohoda_yaka_maie_znachennia.yml": "Погода, яка має значення 21:00",
    "pogoda_vykhidni.yml": "Погода на вихідні (пт 17:00)",
    "tayemnytsi_neba.yml": "Таємниці неба (вт, пт 18:00)",
    "zabobony_svitu.yml": "Забобони світу 12:00",
    "yak_pratsyuye_pohoda.yml": "Як працює погода (нд 09:00)",
    "zahalni_boyovi_vtraty.yml": "Бойові втрати 09:00",
    "nichna_zmina.yml": "Нічна зміна (22:00–08:00)",
    "anons_tayemnytsi_neba.yml": "Анонс «Таємниць неба»",
    "Sumska_filiya_hazmerezhi.yml": "Газмережі",
    "dsns_sumy.yml": "ДСНС",
    "hrafik_vidklyuchen_sumyoblenerho.yml": "Графіки відключень",
    "water_monitor.yml": "Водоканал",
    "rukh_troleybusiv.yml": "Тролейбуси",
    "alarm_monitor.yml": "Повітряні тривоги",
    "space-alert.yml": "Магнітні бурі (алерт)",
    "weekly-digest.yml": "Підсумок тижня (пн 09:00)",
}

# workflow -> тип журналу (звіряється з events_db.TYPE_TITLES)
JOURNAL = {
    "alarm_monitor.yml": "alert",
    "water_monitor.yml": "water",
    "hrafik_vidklyuchen_sumyoblenerho.yml": "power",
    "Sumska_filiya_hazmerezhi.yml": "gas",
    "dsns_sumy.yml": "dsns",
    "space-alert.yml": "space",
}
# workflow -> що робить із даними
DB = {"space-daily.yml", "oblast_daily.yml", "weather-on-this-day.yml"}
# workflow -> ключ у журналі публікацій journal/posted (digest_tracker.TITLES)
POSTED = {
    "weather.yml": "weather", "tomorrow_morning.yml": "tomorrow",
    "shchodennyy_kalendar.yml": "kalendar", "horoskop_dnia.yml": "horoskop",
    "daily_rates.yml": "rates", "kurs_dorohotsinnykh_metaliv.yml": "metals",
    "kurs_kryptovalyut.yml": "crypto", "poyizdy_do_yevropy.yml": "trains",
    "oblast_daily.yml": "oblast", "space-daily.yml": "space",
    "weather-on-this-day.yml": "weather_day", "nebo_nad_sumamy.yml": "sky",
    "khvylynka_tepla.yml": "warm", "pohoda_yaka_maie_znachennia.yml": "meaning",
    "pogoda_vykhidni.yml": "weekend", "zahalni_boyovi_vtraty.yml": "losses",
    "tayemnytsi_neba.yml": "legends", "zabobony_svitu.yml": "omens",
    "yak_pratsyuye_pohoda.yml": "how_weather", "rukh_troleybusiv.yml": "trolley",
}
# регулярні, але не «пости за розкладом»: без стану у підсумок не входять
NO_DATA = {"rukh_troleybusiv.yml", "zabobony_svitu.yml", "tayemnytsi_neba.yml",
           "yak_pratsyuye_pohoda.yml", "anons_tayemnytsi_neba.yml", "nichna_zmina.yml",
           "zahalni_boyovi_vtraty.yml", "pogoda_vykhidni.yml", "tomorrow_morning.yml",
           "weather.yml", "weekly-digest.yml", "shchodennyy_kalendar.yml",
           "horoskop_dnia.yml", "poyizdy_do_yevropy.yml", "daily_rates.yml",
           "kurs_dorohotsinnykh_metaliv.yml", "kurs_kryptovalyut.yml",
           "nebo_nad_sumamy.yml", "khvylynka_tepla.yml",
           "pohoda_yaka_maie_znachennia.yml", "Sumska_filiya_hazmerezhi.yml",
           "dsns_sumy.yml", "hrafik_vidklyuchen_sumyoblenerho.yml",
           "water_monitor.yml", "alarm_monitor.yml", "space-alert.yml"}


def crons(wf: Path) -> list[str]:
    text = wf.read_text(encoding="utf-8")
    return re.findall(r'cron:\s*["\']([^"\']+)["\']', text)


def main() -> int:
    rows = []
    for wf in sorted(WF_DIR.glob("*.yml")):
        cs = crons(wf)
        if not cs:
            continue
        name = wf.name
        if name in POSTED:
            cat, note = "posted", f"journal/posted · {POSTED[name]}"
        elif name in JOURNAL:
            cat, note = "journal", f"journal/events/{JOURNAL[name]}"
        elif name in DB:
            cat, note = "db", "synoptic.db"
        elif name in NO_DATA:
            cat, note = "none", "стан не зберігається"
        else:
            cat, note = "none", "—"
        rows.append((name, FIXED.get(name, ""), len(cs), cat, note))

    print(f"{'workflow':<44}{'за Києвом':<34}{'cron':<5}{'дані':<9}")
    for name, when, n, cat, note in rows:
        print(f"{name:<44}{when:<34}{n:<5}{cat:<9}{note}")

    miss = [r for r in rows if r[3] == "none" and r[1]]
    print(f"\nусього workflow зі schedule: {len(rows)}")
    print(f"у підсумку через журнал: {sum(1 for r in rows if r[3]=='journal')}")
    print(f"у підсумку через synoptic.db: {sum(1 for r in rows if r[3]=='db')}")
    print(f"у підсумку через журнал публікацій: {sum(1 for r in rows if r[3]=='posted')}")
    print(f"НЕ входять у підсумок (пости за розкладом): {len(miss)}")
    for r in miss:
        print("  •", r[0], "—", r[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
