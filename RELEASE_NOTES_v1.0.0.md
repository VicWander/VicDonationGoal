# VicDonationGoal v1.0.0

Первый публичный релиз VicDonationGoal.

## Что это

VicDonationGoal — локальное приложение для стримеров: OBS-виджет донат-гола, админ-панель, история донатов и интеграции с DonationAlerts, Donatty и Streamer.bot.

## Основные возможности

- Локальный Python HTTP-сервер.
- OBS Browser Source виджет для полоски сбора.
- Админ-панель для управления целью и историей донатов.
- Ручное добавление донатов.
- Включение/исключение донатов из текущей цели.
- CSV-экспорт истории донатов.
- Ручные курсы валют к RUB.
- DonationAlerts integration через OAuth и real-time события.
- Donatty Auto SSE Listener.
- Streamer.bot Bridge для запуска кастомных оповещений.
- Кнопка повтора оповещения.
- Блок статусов интеграций.
- Светлая/тёмная тема админки.
- Локальная HTML-документация.

## Быстрый старт

1. Распаковать архив.
2. Запустить `00_INSTALL_ALL.bat`.
3. Заполнить локальные конфиги:
   - `core/integrations/donationalerts/da_config.json`
   - `integrations/donatty/donatty_config.json`
   - `integrations/streamerbot/streamerbot_config.json`
4. Запустить `01_START_ALL.bat`.
5. Открыть админку: `http://127.0.0.1:3333/admin.html`.

## Важно

В релизе нет приватных токенов, реальных ссылок виджетов и истории донатов. Все локальные конфиги создаются из `.example.json` файлов.
