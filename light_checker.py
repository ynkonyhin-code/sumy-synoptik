import os
import requests

def send_telegram_message(text):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    print(f"Используем Chat ID: {chat_id}")

    if not bot_token or not chat_id:
        print("Ошибка: Секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не найдены!")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, json=payload, timeout=15)
    print(f"Ответ от Telegram API: {response.status_code} - {response.text}")

if __name__ == "__main__":
    test_message = "<b>⚡ Тест бота sumy_light_alert_bot</b>\n\nСвязь с каналом @sumskoy_sinoptik успешно установлена!"
    send_telegram_message(test_message)