# «Хвилинка тепла від Сумського синоптика»

Небольшой Python-проект для ежедневной публикации короткого доброго сообщения
на украинском языке в Telegram. Картинки не создаются. Тексты и примеры примет
хранятся локально в `khvylynka_tepla.json`; для фактической заметки о Сумах
в JSON сохранены ссылки на два независимых источника.

## Файлы

- `khvylynka_tepla.py` — выбор записи, формирование поста и отправка в Telegram.
- `khvylynka_tepla_sources.py` — проверка ссылок и независимых доменов.
- `khvylynka_tepla.json` — настройки и библиотека оригинальных текстов.
- `khvylynka_tepla_history.json` — даты публикаций и защита от повторов.
- `requirements_khvylynka_tepla.txt` — зависимости.
- `.github/workflows/khvylynka_tepla.yml` — ежедневный workflow.
- `README_khvylynka_tepla.md` — эта инструкция.

## Настройка Telegram

1. Создайте Telegram-бота через BotFather.
2. Добавьте бота в нужный канал и предоставьте ему право публиковать сообщения.
3. В GitHub откройте репозиторий: **Settings → Secrets and variables → Actions**.
4. Создайте репозиториальные secrets с именами `BOT_TOKEN` и `CHAT_ID`.
   Значения секретов в код не записывайте.
5. Для публичного канала в `CHAT_ID` можно использовать его username,
   например `@example_channel`; для закрытого канала нужен числовой chat ID.

Workflow должен иметь право записывать изменения в репозиторий. Проверьте
**Settings → Actions → General → Workflow permissions** и выберите разрешение
на чтение и запись содержимого репозитория.

## Локальная установка и тест

Нужен Python 3.12 или 3.13.

```bash
python -m venv .venv
