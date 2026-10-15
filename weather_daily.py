"""Вечерняя запись погоды Сум в журнал (Open-Meteo, без ключа).

Запуск: python weather_daily.py
Записывает вчера и сегодня: если какой-то запуск пропущен, данные сами дозаполнятся.
Зависимость: pip install requests
"""
import requests

from events_db import commit_journal, save_daily_weather

# Сумы
LAT, LON = 50.9077, 34.7981
URL = "https://api.open-meteo.com/v1/forecast"


def main():
    r = requests.get(URL, params={
        "latitude": LAT,
        "longitude": LON,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "wind_speed_unit": "ms",
        "timezone": "Europe/Kyiv",
        "past_days": 1,
        "forecast_days": 1,
    }, timeout=30)
    r.raise_for_status()
    d = r.json()["daily"]
    for i, day in enumerate(d["time"]):
        tmax, tmin = d["temperature_2m_max"][i], d["temperature_2m_min"][i]
        if tmax is None or tmin is None:
            continue
        save_daily_weather(day, tmax, tmin,
                           d["precipitation_sum"][i], d["wind_speed_10m_max"][i])
        print(f"{day}: {tmin:+.1f}..{tmax:+.1f}°, опади {d['precipitation_sum'][i]} мм")
    commit_journal()


if __name__ == "__main__":
    main()
