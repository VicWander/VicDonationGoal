# VicDonationGoal v1.4.6 — полное руководство

VicDonationGoal — локальная система для управления донат-голом, историей донатов, событиями Streamer.bot и озвучкой сообщений через TTS Hub.

Версия **1.4.5.1** сохраняет перенос данных v1.4.5, завершает навигацию TTS и исправляет модель состояния DonationAlerts: OAuth/API, live-канал, автоматическое переподключение и догон пропущенных событий теперь различаются явно.

---

## 1. Что умеет проект

Основные возможности:

- подключать DonationAlerts, Donatty, StreamElements и Streamlabs через единый Integrations Hub;
- включать, выключать, проверять и переподключать каждый донат-сервис отдельно;
- добавлять переводы вручную;
- учитывать или не учитывать каждый донат в текущей цели;
- хранить полную историю событий;
- строить TopDonation за всё время и объединять профили одного человека;
- показывать кастомный донат-гол в OBS Browser Source;
- отправлять обычные оповещения в Streamer.bot;
- запускать дополнительные Streamer.bot actions по сумме доната;
- озвучивать сообщения через Speaker.bot, Microsoft Edge, Yandex SpeechKit, XTTS Local или Custom HTTP;
- выбирать разные голоса для донатов, модераторов, VIP, наград, Вашингтона и конкретных зрителей;
- принимать внешние TTS-события от Streamer.bot, Washington Service и других программ;
- экспортировать историю донатов в CSV;
- хранить данные локально без обязательного внешнего сервера.

Краткая схема:

```text
DonationAlerts Adapter ─┐
Donatty Adapter ─────────┤
StreamElements Adapter ──┼──> Integration Manager ──> VicDonationGoal Core
Streamlabs Adapter ──────┘                              │
                                                       ├──> JSON storage
                                                       ├──> Admin / Goal Widget
                                                       ├──> TopDonation
                                                       ├──> Streamer.bot Bridge
                                                       └──> TTS Hub
```

---

## 2. Архитектура

### 2.1. Core Server

Главный файл:

```text
core/server.py
```

Core запускает локальный HTTP-сервер на `http://127.0.0.1:3333`, хранит донаты, пересчитывает цель и предоставляет API. Начиная с v1.4.0 Core **не содержит реализацию конкретного донат-сервиса**.

### 2.2. Integration Manager

```text
core/integration_manager.py
```

Integration Manager:

- сканирует `integrations/*/manifest.json`;
- понимает, какие поля настройки нужны сервису;
- запускает только включённые интеграции;
- останавливает и переподключает модули;
- отдаёт в админку статусы, инструкции и логи;
- не передаёт секреты обратно в браузер.

### 2.3. DonationAlerts Adapter

```text
integrations/donationalerts/donationalerts_integration.py
```

Адаптер полностью отвечает за OAuth, refresh token, Centrifugo WebSocket и преобразование события DonationAlerts в единый формат доната.

### 2.4. Donatty Adapter

```text
integrations/donatty/donatty_listener.py
```

Donatty остаётся отдельным процессом, потому что использует Playwright и длительное SSE-соединение. Процесс запускается и останавливается Integration Manager автоматически.

### 2.5. StreamElements Adapter

```text
integrations/streamelements/streamelements_listener.py
```

Отдельный процесс подключается к официальному Astro WebSocket, подписывается на `channel.tips` и отправляет успешно завершённые tips в Core.

### 2.6. Streamlabs Adapter

```text
integrations/streamlabs/streamlabs_integration.py
```

In-process адаптер управляет OAuth, получает Socket Token и принимает Streamlabs Donation events через Socket.IO.

### 2.7. Единый формат события

Любая интеграция в конце передаёт Core объект:

```json
{
  "source": "service_name",
  "externalId": "event-id",
  "username": "ViewerName",
  "amount": 100,
  "currency": "RUB",
  "message": "Сообщение",
  "createdAt": "2026-07-30T20:00:00Z"
}
```

После этого источник больше не важен: Core одинаково обновляет историю, TopDonation, виджет, TTS и Streamer.bot.

---

## 3. Первый запуск

### 3.1. Требования

- Windows 10/11;
- Python 3.11 или новее;
- OBS Studio — для виджетов;
- Streamer.bot — если нужны оповещения и донат-ивенты;
- Speaker.bot — только если выбран соответствующий TTS-провайдер.

### 3.2. Установка зависимостей

Запусти:

```text
00_INSTALL_ALL.bat
```

Устанавливаются `requests`, `websocket-client`, `playwright`, `edge-tts` и Chromium Playwright.

### 3.3. Мастер интеграций

После первого запуска открой:

```text
http://127.0.0.1:3333/admin.html
```

Перейди в раздел **Интеграции**. На чистой установке появится мастер:

1. выбрать DonationAlerts, Donatty или оба сервиса;
2. заполнить настройки выбранных сервисов;
3. сохранить конфигурацию;
4. авторизовать DonationAlerts, если он выбран;
5. нажать **Проверить**.

Выключенные модули не запускаются и не показывают ошибки.

### 3.4. Проверка

```text
09_STABILITY_CHECK.bat
```

Проверка валидирует Python, JSON, manifests интеграций, конфиги, TTS, TopDonation и основные файлы.

---

## 4. Ежедневный запуск

```text
01_START_ALL.bat
```

Открываются Core Server, Streamer.bot Bridge и TTS Hub. Core самостоятельно запускает только включённые донат-интеграции.

```text
Админка:   http://127.0.0.1:3333/admin.html
Виджет:    http://127.0.0.1:3333/widget.html
TTS Player:http://127.0.0.1:3333/tts.html
```

`03_START_DONATTY_ONLY.bat` оставлен только для ручной отладки. В обычной работе Donatty управляется из Integration Hub.

---

## 5. Админка: раздел «Донаты»

### 5.1. Текущая цель

Можно изменить:

- название;
- стартовую сумму;
- целевую сумму;
- валюту цели.

`baseAmount` — деньги, которые уже были собраны, но не представлены отдельными донатами.

### 5.2. Ручной донат

Поля:

```text
Имя
Сумма
Валюта
Сообщение
```

Независимые флаги:

```text
Добавлять в текущий сбор
Отправить обычное оповещение в Streamer.bot
Запустить донат-ивенты
Озвучить сообщение через TTS Hub
```

Для ручного доната галочка **«Озвучить»** является окончательным решением. Если она включена, ручной донат обходит общий минимальный порог TTS. Это удобно для переводов на карту, разных валют и тестов.

### 5.3. История донатов

Основная строка показывает краткие данные. Нажми **«Развернуть»**, чтобы увидеть:

- полное сообщение;
- даты;
- сумму после конвертации;
- external ID;
- unique key;
- заметку.

Так таблица не растягивается горизонтально.

### 5.4. Редактирование и удаление

- `Изм.` — изменить имя, сумму, валюту и сообщение;
- `Удал.` — удалить донат;
- `Повт.` — повторить обычное оповещение Streamer.bot;
- чекбоксы в истории меняют отдельные флаги события.

---

## 6. Данные и валюты

### 6.1. state.json

```text
core/data/state.json
```

Хранит состояние цели.

### 6.2. donations.json

```text
core/data/donations.json
```

Основные поля доната:

```json
{
  "uniqueKey": "donatty:external-id",
  "source": "donatty",
  "username": "Viewer",
  "amount": 100,
  "currency": "RUB",
  "amountForGoal": 100,
  "includeInGoal": true,
  "notifyStreamerBot": true,
  "triggerDonationEvents": true,
  "speakTTS": true,
  "message": "Текст сообщения"
}
```

### 6.3. Курсы валют

```text
core/data/rates.json
```

Курс означает, сколько рублей стоит одна единица валюты. Например:

```json
{
  "baseCurrency": "RUB",
  "ratesToRUB": {
    "RUB": 1,
    "USD": 90,
    "EUR": 100,
    "KZT": 0.18
  }
}
```

---

## 7. DonationAlerts

В v1.4.0 DonationAlerts настраивается в **Админка → Интеграции → DonationAlerts**.

### 7.1. Настройка

1. Создай API Application в DonationAlerts.
2. Redirect URL должен точно совпадать:

```text
http://127.0.0.1:3333/auth/donationalerts/callback
```

3. Введи Client ID и Client Secret в Integration Hub.
4. Нажми **Сохранить настройки**.
5. Нажми **Авторизовать**.
6. После возврата нажми **Проверить**.

Рабочий конфиг и токены:

```text
integrations/donationalerts/donationalerts_config.json
integrations/donationalerts/donationalerts_tokens.json
```

Client Secret и токены не показываются обратно в браузере и не должны попадать в GitHub.

### 7.2. Управление

В карточке доступны:

```text
Включить / выключить
Запустить / остановить
Переподключить
Проверить
Авторизовать
Сбросить авторизацию
Инструкция / Логи / Техническое состояние
```

Совместимые адреса `/api/da/status`, `/api/da/start` и `/api/da/stop` сохранены.

---

## 8. Donatty

Donatty настраивается в **Админка → Интеграции → Donatty**.

1. Скопируй обычную OBS-ссылку виджета Donatty.
2. Вставь её в поле `Ссылка OBS-виджета Donatty`.
3. Оставь автоматическое получение SSE и скрытый браузер включёнными.
4. Сохрани и нажми **Проверить**.

Integration Manager запускает `donatty_listener.py` как отдельный процесс. Listener через Playwright получает временный `sse?jwt=...`, слушает поток и при истечении JWT переподключается.

Логи Donatty доступны прямо в Integration Hub. Для визуальной отладки можно временно выключить `Скрытый браузер`.

Не публикуй `widget_url`, `sse_url` и JWT.

---

## 9. Streamer.bot Bridge и Donation Event Rules

Bridge:

```text
integrations/streamerbot/streamerbot_bridge.py
```

Конфиг:

```text
integrations/streamerbot/streamerbot_config.json
```

### 9.1. Обычное оповещение

Bridge запускает основной Streamer.bot action и передаёт:

```text
%user%
%amount%
%currency%
%message%
%source%
%donationId%
```

### 9.2. Донат-ивенты

Правила:

```text
integrations/streamerbot/donation_event_rules.json
```

Пример:

```json
{
  "id": "pet-hand-20",
  "enabled": true,
  "sources": ["donationalerts", "donatty", "manual"],
  "match": "equals",
  "amount": 20,
  "currency": "RUB",
  "action_id": "STREAMERBOT-ACTION-ID"
}
```

Каждый донат может независимо:

- запустить обычное оповещение;
- запустить донат-ивент;
- попасть в сбор;
- быть озвучен.

---

# 10. TTS Hub

TTS Hub — единая система озвучки. Она принимает события, очищает текст, выбирает голосовой профиль, применяет правила и передаёт текст выбранному провайдеру.

Файлы:

```text
integrations/tts/tts_hub.py
integrations/tts/tts_config.json
integrations/tts/tts_profiles.json
integrations/tts/tts_rules.json
integrations/tts/tts_queue.json
integrations/tts/tts_history.json
integrations/tts/tts_log.json
integrations/tts/providers/
```

## 10.1. Общая последовательность

```text
Событие
  ↓
Проверка TTS-флага и суммы
  ↓
Очистка текста
  ↓
Выбор профиля
  ↓
Выбор основного провайдера
  ↓
Синтез / отправка Speaker.bot
  ↓
При подтверждённой ошибке — fallback
  ↓
История и лог
```

## 10.2. Общие настройки

- основной провайдер;
- резервный провайдер;
- профиль по умолчанию;
- минимальная сумма автоматического доната;
- максимальная длина;
- удаление ссылок и HTML;
- пропуск пустого текста;
- автоматическая озвучка донатов сервисов.

Важно: провайдер, жёстко заданный в профиле, имеет приоритет. Значение **«Автоматически»** заставляет профиль использовать основной провайдер.

---

## 11. Провайдер Speaker.bot

Speaker.bot удобен как общий голосовой центр для донатов, команд, наград и Вашингтона.

### 11.1. Настройка Speaker.bot

1. Открой `Settings -> Speech Engines`.
2. Добавь и настрой движок.
3. Открой `Settings -> Voice Aliases`.
4. Создай alias, например:

```text
Donations
moderator
Rewards
Washington
```

5. Проверь `Test Speak`.
6. Открой `Settings -> Websocket Server`.
7. Включи Auto Start.

Пример текущей конфигурации:

```text
Address: 127.0.0.1
Port: 7580
Endpoint: /
```

В VicDonationGoal:

```text
ws://127.0.0.1:7580/
```

Название Voice Alias в профиле должно совпадать символ в символ.

### 11.2. Очередь Speaker.bot

VicDonationGoal умеет отправлять команды:

```text
Pause
Resume
Stop
Clear
```

Fallback запускается только при подтверждённой ошибке отправки. Медленная речь Speaker.bot сама по себе не запускает второй голос.

### 11.3. Типичные ошибки

```text
speakerbot: выключен
```

Проверь флаг провайдера, профиль и WebSocket.

```text
Voice Alias не указан
```

Создай alias и впиши его в профиль.

---

## 12. Провайдер Microsoft Edge

Edge TTS не требует API-ключа, но использует онлайн-службу Microsoft.

Настройки:

```text
voice
rate
volume
pitch
```

Пример голоса:

```text
ru-RU-SvetlanaNeural
```

Edge создаёт MP3. Для вывода звука добавь в OBS Browser Source:

```text
http://127.0.0.1:3333/tts.html
```

TTS Hub показывает heartbeat этого плеера. Если аудио создано, но Browser Source не открыт, звук не будет воспроизведён.

---

## 13. Провайдер Yandex SpeechKit

Yandex является необязательным облачным провайдером.

Поля:

```text
Endpoint
API key или IAM token
Folder ID
Voice
Emotion
Speed
Format
```

Сервисному аккаунту нужны права SpeechKit TTS на выбранный каталог. При ошибке `401/403 PermissionDenied` проверь роль, Folder ID и владельца ключа.

Ключи хранятся в приватном:

```text
integrations/tts/tts_config.json
```

Никогда не публикуй его без очистки.

---

## 14. Провайдер XTTS Local

VicDonationGoal не включает модель XTTS и её веса. Провайдер подключается к отдельно запущенному локальному HTTP-серверу.

Ожидаемая схема по умолчанию:

```text
POST endpoint
multipart/form-data:
  text
  language
  speaker_wav (необязательно)
```

Поля настройки:

```text
Endpoint
Language
Reference WAV
Format
Response type
```

Поддерживаются ответы:

- готовое аудио;
- JSON с URL аудио;
- JSON с base64.

Если конкретный XTTS-сервер имеет другой API, используй Custom HTTP.

---

## 15. Провайдер Custom HTTP

Универсальный адаптер для внешнего или локального API.

Настройки:

```text
URL
HTTP method
Headers JSON
Body JSON / Form
Voice
Language
Response type
```

Шаблоны:

```text
{text}
{voice}
{language}
```

Пример тела:

```json
{
  "text": "{text}",
  "voice": "{voice}",
  "language": "{language}"
}
```

Типы ответа:

```text
audio       — бинарный аудиофайл в теле ответа
json_url    — JSON содержит ссылку на аудиофайл
json_base64 — JSON содержит base64-аудио
```

Для вложенного JSON можно указать путь через точку, например:

```text
data.audio.url
```

Не выводи приватные заголовки в публичные скриншоты и логи.

---

## 16. Голосовые профили

Профиль — набор настроек голоса для назначения или группы пользователей.

Стандартные профили:

```text
Default
Donations
Rewards
Washington
Moderator
VIP
```

### 16.1. Поля профиля

- ID — постоянный технический идентификатор;
- название;
- провайдер;
- Voice Alias Speaker.bot;
- Edge voice;
- Yandex voice/emotion;
- XTTS reference WAV/language;
- Custom HTTP voice/language;
- rate, pitch, volume;
- Bad Word Filter;
- включён/выключен.

### 16.2. Провайдер «Автоматически»

```text
Автоматически -> основной провайдер из общих настроек
```

Это лучший вариант для обычных профилей, если пользователь часто переключает движки.

### 16.3. Персональный голос

Создай профиль:

```text
ID: nick-special
Name: Голос Nick
Provider: Speaker.bot
Alias: NickVoice
```

После этого создай правило по нику или userId.

---

## 17. Правила маршрутизации

Правила выбирают профиль. Они **не задают порядок проигрывания очереди**.

Главное правило:

```text
меньше число приоритета = правило проверяется раньше
```

Срабатывает первое подходящее правило.

### 17.1. Типы событий

Стандартные значения:

```text
donation
channel_reward
washington
moderator_command
manual_test
custom
```

Это внутренние значения TTS Hub. Они не появляются автоматически из Twitch или YouTube — их передаёт создатель события.

### 17.2. Источники

Стандартные значения:

```text
donationalerts
donatty
manual
streamerbot
twitch
youtube
washington-service
custom
```

Пример:

```text
eventType = channel_reward
source = streamerbot
```

означает, что Streamer.bot получил награду и отправил её в TTS Hub.

### 17.3. User ID

Постоянный ID пользователя Twitch, YouTube или другой платформы. Он надёжнее ника, но доступен только если внешняя система его передала.

### 17.4. Ники

Сравнение выполняется без учёта регистра. У донатов DA/Donatty ник обычно доступен, а platform userId — не всегда.

### 17.5. Роли

Примеры:

```text
moderator
vip
subscriber
broadcaster
```

Роль сработает только если Streamer.bot или другая интеграция передала поле `roles`.

### 17.6. Reward ID

ID конкретной награды Twitch. Его можно получить из события Streamer.bot или из настроек награды.

### 17.7. Сумма

Правила могут ограничить минимальную и максимальную сумму. Сначала используется `amountForGoal`, затем обычный `amount`.

### 17.8. Как объединяются условия

Разные заполненные поля работают через **И**. Значения внутри одного поля, перечисленные через запятую, работают через **ИЛИ**.

Пример:

```text
Тип: donation
Источник: donatty, donationalerts
Ник: Nick
Минимальная сумма: 1000
```

означает: донат из Donatty или DA, от Nick, не меньше 1000.

### 17.9. Тестер маршрутизации

В разделе правил можно ввести тестовое событие и увидеть:

- совпавшее правило;
- выбранный профиль;
- фактический провайдер;
- голос;
- fallback.

Озвучка при этом не запускается.

---

## 18. Очередь, история и логи

### 18.1. Очередь

Показывает ожидающие, обрабатываемые и готовые задачи. Длинный текст раскрывается вниз.

### 18.2. История

Фильтры:

- поиск по нику, тексту и ID;
- статус;
- провайдер.

Развёрнутая запись показывает:

- оригинальный текст;
- текст после очистки;
- удалённые ссылки и фрагменты;
- профиль;
- совпавшее правило;
- провайдер и голос;
- fallback;
- ошибку;
- идентификаторы события.

Статус `Пропущено` не является аварией. Например, сообщение могло состоять только из ссылки и стать пустым после очистки.

### 18.3. Логи

Логи хранят технические события TTS. Секретные ключи нельзя добавлять в текст ошибок вручную.

---

## 19. Внешний TTS API

Главный endpoint:

```text
POST http://127.0.0.1:3333/api/tts/enqueue
```

Минимальный пример:

```json
{
  "eventType": "channel_reward",
  "source": "streamerbot",
  "username": "Viewer",
  "text": "Сообщение зрителя"
}
```

Расширенный пример:

```json
{
  "eventType": "channel_reward",
  "source": "streamerbot",
  "eventId": "reward-event-id",
  "username": "Viewer",
  "userId": "123456789",
  "roles": ["moderator"],
  "rewardId": "twitch-reward-id",
  "text": "Сообщение зрителя",
  "profileId": "moderator",
  "priority": 50
}
```

Если указан существующий `profileId`, правила пропускаются и профиль выбирается напрямую.

Проверка правил без озвучки:

```text
POST /api/tts/rules/test
```

---

## 20. Команда !ттс в Streamer.bot

Можно напрямую использовать встроенный sub-action Speaker.bot, но тогда сообщение не попадёт в историю VicDonationGoal. Для единой истории лучше отправлять POST в TTS Hub.

Пример C# sub-action Streamer.bot:

```csharp
using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;

public class CPHInline
{
    public bool Execute()
    {
        CPH.TryGetArg("rawInput", out string text);
        CPH.TryGetArg("user", out string username);
        CPH.TryGetArg("userId", out string userId);

        if (string.IsNullOrWhiteSpace(text))
            return false;

        var payload = new
        {
            eventType = "moderator_command",
            source = "streamerbot",
            username = username ?? "Moderator",
            userId = userId ?? "",
            roles = new[] { "moderator" },
            text,
            profileId = "moderator"
        };

        using var client = new HttpClient();
        var json = JsonSerializer.Serialize(payload);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var response = client.PostAsync(
            "http://127.0.0.1:3333/api/tts/enqueue",
            content
        ).GetAwaiter().GetResult();

        return response.IsSuccessStatusCode;
    }
}
```

Команда должна быть доступна только модераторам.

---

## 21. Награды за баллы канала

Схема:

```text
Twitch Reward
  ↓
Streamer.bot trigger
  ↓
POST /api/tts/enqueue
  ↓
eventType: channel_reward
source: streamerbot
rewardId: ID награды
  ↓
Профиль Rewards или правило конкретной награды
```

Для разных наград можно создавать разные правила по `rewardId`.

---

## 22. Washington Service

Washington Service генерирует текст, а TTS Hub отвечает за голос.

Пример:

```json
{
  "eventType": "washington",
  "source": "washington-service",
  "username": "Вашингтон",
  "text": "Реплика виртуального кота",
  "profileId": "washington"
}
```

Так Вашингтон может использовать отдельный Speaker.bot alias, Edge-голос или локальный XTTS-профиль.

---

## 23. Основные API endpoints

| Метод | Endpoint | Назначение |
|---|---|---|
| GET | `/api/state` | состояние цели |
| GET | `/api/donations` | история донатов |
| POST | `/api/donation` | добавить донат |
| GET | `/api/donors/top` | TopDonation |
| GET | `/api/integrations` | список и статусы интеграций |
| GET | `/api/integrations/detail?id=...` | manifest, настройки и инструкция сервиса |
| GET | `/api/integrations/logs?id=...` | логи интеграции |
| POST | `/api/integrations/config` | сохранить настройки сервиса |
| POST | `/api/integrations/enable` | включить или выключить модуль |
| POST | `/api/integrations/start` | запустить модуль |
| POST | `/api/integrations/stop` | остановить модуль |
| POST | `/api/integrations/restart` | переподключить модуль |
| POST | `/api/integrations/test` | проверить подключение |
| POST | `/api/integrations/clear-auth` | удалить OAuth-токены |
| POST | `/api/integrations/onboarding` | завершить мастер первого запуска |
| GET | `/api/status` | общий статус системы |
| GET | `/api/tts/bootstrap` | TTS-конфиг, профили, правила и очередь |
| POST | `/api/tts/enqueue` | внешнее TTS-событие |

---

## 24. BAT-файлы

```text
00_INSTALL_ALL.bat              установка зависимостей
01_START_ALL.bat                Core + включённые интеграции + Bridge + TTS
02_START_SERVER_ONLY.bat        Core и Integration Manager
03_START_DONATTY_ONLY.bat       ручная отладка Donatty
04_START_STREAMERBOT_ONLY.bat   только Streamer.bot Bridge
05_TEST_STREAMERBOT.bat         тест action Streamer.bot
06_RESET_STREAMERBOT_SENT.bat   сброс отправленных событий
07_CREATE_LOCAL_CONFIGS.bat     создание конфигов из примеров
08_START_TTS_ONLY.bat           только TTS Hub
09_STABILITY_CHECK.bat          проверка проекта
```

---

## 25. Структура проекта

```text
VicDonationGoal/
├─ core/
│  ├─ server.py
│  ├─ integration_manager.py
│  ├─ donor_store.py
│  ├─ tts_hub_store.py
│  ├─ data/
│  └─ public/
│     ├─ admin.html/js/css
│     ├─ integrations-admin.js
│     ├─ tts-admin.js
│     ├─ widget.html/js
│     └─ tts.html/js
├─ integrations/
│  ├─ donationalerts/
│  │  ├─ manifest.json
│  │  ├─ donationalerts_integration.py
│  │  ├─ donationalerts_config.json
│  │  ├─ donationalerts_tokens.json
│  │  └─ GUIDE.md
│  ├─ donatty/
│  │  ├─ manifest.json
│  │  ├─ donatty_listener.py
│  │  ├─ donatty_config.json
│  │  └─ GUIDE.md
│  ├─ streamerbot/
│  └─ tts/
├─ runtime/integrations/
├─ docs/
├─ backups/
└─ *.bat
```

Manifest описывает имя, тип запуска, обязательные поля, секреты, capabilities и встроенный гайд. Благодаря этому следующие сервисы можно добавлять без возврата их логики в Core.

---

## 26. Типичные проблемы TTS

### Профиль продолжает использовать не тот движок

Проверь поле `Провайдер` в профиле. Поставь `Автоматически`, если профиль должен следовать общим настройкам.

### Speaker.bot выключен

- запусти Speaker.bot;
- включи WebSocket Server;
- проверь порт;
- проверь флаг провайдера;
- проверь Voice Alias.

### Edge создал файл, но звука нет

Добавь `/tts.html` в OBS Browser Source и проверь heartbeat Edge Player в обзоре TTS Hub.

### После очистки сообщение пустое

Сообщение могло состоять только из ссылки или HTML. Это нормальный статус `Пропущено`.

### Сообщение озвучилось дважды

Не запускай одновременно прямой Speaker.bot sub-action и тот же текст через `/api/tts/enqueue`. Выбери одну цепочку.

### Старые сообщения проигрались после сброса sent

Не удаляй `tts_sent.json`, если не хочешь повторно обрабатывать старую историю донатов.

### Yandex 401/403

Проверь API key/IAM token, Folder ID и роль `ai.speechkit-tts.user`.

### XTTS timeout

Модель может долго загружаться. Проверь локальный сервер, GPU/CPU, endpoint и увеличь timeout.

---

## 27. Бэкапы и безопасность

Перед обновлением копируй всю папку проекта.

Особенно важны:

```text
core/data/state.json
core/data/donations.json
core/data/rates.json
integrations/donationalerts/donationalerts_config.json
integrations/donationalerts/donationalerts_tokens.json
integrations/donatty/donatty_config.json
integrations/streamerbot/streamerbot_config.json
integrations/tts/tts_config.json
integrations/tts/tts_profiles.json
integrations/tts/tts_rules.json
```

Приватную рабочую сборку нельзя публиковать целиком. Перед GitHub-релизом нужно собрать отдельный sanitized-архив.


---

## 28. TopDonation

Версия v1.3 добавляет отдельный рейтинг донатеров. В разделе `Донаты` доступны вкладки:

```text
История | Топ
```

### 28.1. Как считается рейтинг

TopDonation считает сумму за всё время и не зависит от текущего донат-гола. Для каждого доната при первом учёте сохраняется отдельная сумма `amountForTop` в RUB. Позднее изменение курса валют не меняет уже сохранённый результат.

Донат участвует в рейтинге, если у него включён флаг:

```text
Учитывать в TopDonation
```

Для ручного доната эта галочка находится прямо в форме добавления.

### 28.2. Почему одинаковые ники из разных сервисов разделены

Автоматическое объединение выполняется только внутри одного источника. Например:

```text
DonationAlerts: Nick
DonationAlerts: nick
```

считаются одним профилем, потому что отличается только регистр.

Но:

```text
DonationAlerts: Nick
Donatty: Nick
```

по умолчанию считаются разными донатерами. Это защищает от случайного объединения двух людей с одинаковыми никами. Если это один человек, используй меню `••• → Объединить с другим`.

### 28.3. Профиль донатера

Профиль содержит:

- отображаемое имя;
- алиасы с указанием источника;
- общую сумму донатов;
- сумму ручных корректировок;
- количество донатов;
- дату первого и последнего доната;
- личную заметку;
- признаки `Закреплён` и `Исключён из топа`.

Данные хранятся в:

```text
core/data/donor_profiles.json
core/data/donor_adjustments.json
```

### 28.4. Закреплённые донатеры

Команда `Закрепить` переносит профиль в отдельный блок над обычным рейтингом. Закреплённый пользователь не занимает номер в общем списке.

### 28.5. Корректировка суммы

Меню `Добавить сумму` создаёт техническую корректировку. Она полезна для старых переводов или денег, полученных вне донат-сервиса.

Корректировка:

- влияет только на TopDonation;
- не создаёт обычный донат;
- не меняет текущую цель;
- отображается в раскрытой истории профиля;
- может быть отрицательной;
- может быть удалена отдельно.

### 28.6. Объединение профилей

Чтобы объединить одного человека из разных сервисов:

1. открой вкладку `Топ`;
2. нажми `•••` у профиля, который нужно присоединить;
3. выбери `Объединить с другим`;
4. введи точное имя или ID целевого профиля;
5. подтверди действие.

Исходные донаты не переписываются и не удаляются. В целевой профиль добавляются алиасы, а записи связываются с одним `donorId`.

### 28.7. Исключение и удаление

`Исключить из топа` скрывает пользователя из рейтинга, но сохраняет историю и донат-гол.

`Удалить все донаты` — опасное действие. Оно удаляет все связанные донаты, корректировки и профиль, а затем пересчитывает текущую цель. Для подтверждения требуется повторно ввести имя донатера.

### 28.8. Поиск

Поиск во вкладке `Топ` работает по:

- отображаемому имени;
- алиасам;
- заметке;
- текстам всех донатов пользователя.

### 28.9. Экспорт одного донатера

Меню `Экспорт CSV` создаёт отдельный файл с:

- общей суммой;
- суммой корректировок;
- всеми донатами;
- исходными валютами;
- суммой для рейтинга;
- сообщениями;
- техническими корректировками.

### 28.10. Массовые флаги истории

Над историей есть общие переключатели:

```text
Сбор | Опов. | Ивент | TTS | Топ
```

Они применяются ко всей истории. Смешанное состояние отображается чертой. Это позволяет одним действием убрать все старые донаты из текущего сбора.

### 28.11. TopDonation API

Основные endpoints:

```text
GET  /api/donors/top
GET  /api/donors/detail?id=<donorId>
GET  /api/donors/export.csv?id=<donorId>
POST /api/donors/update
POST /api/donors/adjustment/add
POST /api/donors/adjustment/delete
POST /api/donors/merge
POST /api/donors/delete-all
POST /api/donations/bulk-update
```


---

## 29. Integrations Hub

### 29.1. Состояния

```text
Не настроено
Выключено
Остановлено
Запуск / подключение
Подключено
Ошибка
```

Карточка показывает фактическое состояние процесса и соединения. Кнопка **Переподключить** выполняет stop/start без перезапуска всей программы.

### 29.2. Секретные поля

Client Secret, widget URL и другие поля, помеченные в manifest как секретные, не отправляются обратно в браузер. Если секрет уже сохранён, поле показывает подсказку «Сохранено»; пустое значение при повторном сохранении не стирает его.

### 29.3. Первый запуск

Файл:

```text
integrations/integrations_onboarding.json
```

хранит завершение мастера и выбранные сервисы. На существующей рабочей установке мастер автоматически считается завершённым, если интеграции уже настроены.

### 29.4. Добавление будущего сервиса

Новая интеграция должна иметь собственную папку, `manifest.json`, конфиг, гайд и adapter/listener. Она приводит событие к единому формату и отправляет его в `/api/donation` или вызывает Core callback.

---



---

## 30. StreamElements

### 30.1. Как работает

```text
JWT / Overlay Token
→ wss://astro.streamelements.com/
→ subscribe channel.tips
→ completed tip
→ VicDonationGoal Core
```

Тема `channel.tips` предназначена для real-time tip/donation events. В событии доступны ID, пользователь, сообщение, сумма, валюта, статус и время.

### 30.2. Подключение

1. Откройте StreamElements Dashboard и переключитесь на нужный канал.
2. Скопируйте JWT Token или Overlay Token.
3. Скопируйте StreamElements Channel ID.
4. Откройте **Админка → Интеграции → StreamElements**.
5. Заполните Channel ID, тип токена и сам токен.
6. Включите интеграцию, сохраните и нажмите **Проверить**.
7. Убедитесь, что в логах появилась подписка `channel.tips`.
8. Выполните тестовый или маленький настоящий tip.

### 30.3. Статусы и фильтрация

По умолчанию интеграция принимает `status=success` и разрешённые moderation states. Значения меняются в настройках через запятую.

### 30.4. Безопасность

JWT и Overlay Token являются секретами канала. Они хранятся только локально в `streamelements_config.json` и исключены из Git.

---

## 31. Streamlabs — Beta

### 31.1. Создание приложения

1. Войдите в Streamlabs Developer Console.
2. Создайте OAuth Application.
3. Укажите Redirect URI:

```text
http://127.0.0.1:3333/auth/streamlabs/callback
```

4. Пока приложение не одобрено, добавьте свой аккаунт в whitelist.
5. Скопируйте Client ID и Client Secret.

### 31.2. Подключение

1. Откройте **Интеграции → Streamlabs**.
2. Введите Client ID и Client Secret.
3. Оставьте scope `socket.token`.
4. Включите интеграцию и сохраните.
5. Нажмите **Авторизовать** и подтвердите доступ.
6. После возврата нажмите **Проверить**.
7. Сделайте тестовый или маленький настоящий донат.

### 31.3. Техническая схема

```text
OAuth access token
→ GET /api/v2.0/socket/token
→ Socket.IO event
→ type=donation
→ VicDonationGoal Core
```

Интеграция автоматически пробует Engine.IO v4 и v3. В v1.4.1 Streamlabs помечен Beta до живого теста на пользовательском приложении.

### 31.4. Whitelist

Неодобренное Streamlabs-приложение разрешает авторизацию только whitelist-пользователям. Это подходит для личной сборки и небольшой закрытой беты.

### 31.5. Безопасность

Не публикуйте Client Secret и `streamlabs_tokens.json`.


## 32. Roadmap

```text
v1.4.0 — Integrations Hub — выполнено
v1.4.1 — StreamElements + Streamlabs — выполнено
v1.4.1 — StreamElements + Streamlabs
v1.4.2 — исследование DonatePay, DonateX, Donate.Stream и Tribute
v1.5   — Core & Storage Refactor
v1.6   — Donation Goal Customisation
v2.0   — Desktop EXE Application
Latest — optional account/cloud backup
```

Полный план находится в `ROADMAP.md`.


## 26. v1.4.2 — Russian Services

### DonatePay

DonatePay подключается по официальному API-ключу. Core получает пользователя через `/user`, последние операции через `/transactions`, затем временные токены для Centrifugo и подписывается на личный канал `$public:USER_ID`. Старые операции при первом запуске по умолчанию не импортируются.

### Donate.Stream

Beta-адаптер открывает официальный alert-виджет в Playwright и анализирует WebSocket, EventSource, fetch и сообщения страницы. Если тестовый донат не распознан, используйте `11_INTEGRATION_INSPECTOR.bat` и сохраните диагностический JSONL.

### DonateX

Beta-адаптер поддерживает личный API-токен. Endpoint и схема авторизации оставлены редактируемыми до подтверждения текущей документации живым аккаунтом. Также предусмотрен widget-режим.

### Tribute

Актуальное подключение Tribute использует персональную OBS-ссылку и прямой поток SSE. В мини-приложении Tribute скопируйте «Ссылку для OBS», вставьте в карточку интеграции, сохраните и включите модуль. Cloudflare и API-ключ не требуются. Подробности: `integrations/tribute/GUIDE.md`.

### Integration Inspector

`11_INTEGRATION_INSPECTOR.bat` открывает виджет в обычном Chromium и записывает URL запросов, WebSocket-фреймы и консоль. Значения параметров `token`, `jwt`, `key`, `secret` и `access_token` маскируются автоматически.


## 33. v1.4.3 — Integration Stability

### 33.1. Полная цепочка новых сервисов

Все автоматические источники (`donationalerts`, `donatty`, `streamelements`, `streamlabs`, `donatepay`, `donatestream`, `donatex`, `tribute`) теперь по умолчанию разрешены в Streamer.bot Bridge, Donation Event Rules и TTS Hub. Пустой список `send_sources` означает «все автоматические сервисы».

Существующие события, которые старая версия уже ошибочно отметила отправленными, автоматически повторно не воспроизводятся. Для проверки старой записи используйте кнопку `Повт.` в истории либо создайте новый тестовый донат.

### 33.2. DonatePay

DonatePay использует сохранённый `User ID` и не запрашивает `/user` при каждом переподключении. Восстановление истории через `/transactions` необязательно и по умолчанию выключено из-за строгих лимитов API. Новые события приходят через Centrifugo независимо от catch-up истории. API-ключи маскируются в статусах и логах интерфейса.

### 33.3. DonateX

DonateX работает опросом API. Успешный опрос считается подключением; временная ошибка после успешного ответа отображается как предупреждение `polling_degraded`, а не как полное отключение. Рекомендуемый интервал — 15–30 секунд.

### 33.4. Tribute и Cloudflare Quick Tunnel

Исторически Tribute использовал Quick Tunnel. Теперь карточка работает через OBS-ссылку без туннеля; старый код оставлен только для восстановления прежней настройки.

### 33.5. Остановка и блокировки файлов

`13_STOP_ALL.bat` завершает Core, Streamer.bot Bridge, TTS Hub, cloudflared и все скрытые listener-процессы. `01_START_ALL.bat` запускает эту очистку автоматически. Интеграции, запущенные Core, помещаются в Windows Job Object и завершаются вместе с Core даже при закрытии окна крестиком.

JSON теперь читается и записывается с повторными попытками при кратких Windows sharing violations. Core больше не переписывает `donations.json` на каждом обновлении админки.


## 34. v1.4.4 — Beta Readiness

### 34.1. Статусы на главной

Главная страница разделяет **системные модули** и **донат-сервисы**. Core Server, Integration Manager, Streamer.bot Bridge и TTS Hub имеют собственные лампочки. Донат-сервисы показываются компактной сеткой; красные и жёлтые состояния поднимаются выше работающих. Кнопка «Показать подробности» раскрывает heartbeat, последнее событие и переход в Integration Hub.

Цвета: зелёный — работает, голубой — подключается, жёлтый — degraded, красный — ошибка, серый — выключен или не настроен.

### 34.2. Центральный реестр источников

Файл `source_registry.py` содержит официальные ID всех источников. Streamer.bot Bridge, TTS Hub, фильтры и проверки используют этот реестр. При добавлении нового сервиса его ID больше не нужно вручную дублировать в нескольких модулях.

### 34.3. Диагностический отчёт

Кнопка «Диагностический отчёт» либо `14_CREATE_DIAGNOSTIC_REPORT.bat` создаёт ZIP в папке `diagnostics`. API-ключи, OAuth-токены, JWT, widget URL и webhook secrets маскируются. Тексты донатов не включаются; сохраняются только количество и распределение по источникам.

### 34.4. Beta Readiness Check

`15_BETA_READINESS_CHECK.bat` запускает Stability Check, импортирует исполняемые модули, проверяет manifests и source registry, пропуск источников через Streamer.bot/TTS, конкурентную JSON-запись и построение dashboard API.

### 34.5. Tribute и cloudflared

Tribute остаётся Experimental и выключен по умолчанию в чистой установке. Текущий модуль получает донаты напрямую по OBS-ссылке; установка cloudflared не требуется.

### 34.6. Уровни готовности

- Stable: DonationAlerts, Donatty, StreamElements, Donate.Stream, DonateX.
- Beta: DonatePay, Streamlabs.
- Experimental: Tribute.


## 35. v1.4.5 — перенос данных и резервные копии

Откройте **Админка → Донаты → Настройки → Переносимость данных**.

### 35.1. Полный резервный ZIP

Кнопка **«Создать и скачать полный бэкап»** в разделе настроек создаёт версионированный ZIP. В него входят:

- история донатов, состояние цели и курсы валют;
- профили, алиасы и корректировки TopDonation;
- выбранные интеграции, их настройки, токены и служебные отметки уже обработанных событий;
- настройки и правила Streamer.bot;
- конфигурация, профили, правила, очередь и история TTS Hub.

Временный каталог `integrations/tts/audio_cache` не переносится: готовые аудиофайлы являются кэшем и при необходимости будут созданы заново.

Полный бэкап содержит секреты подключений. Храните его как пароль и не отправляйте вместо диагностического отчёта.

### 35.2. Восстановление

После выбора ZIP программа проверяет:

- формат и версию схемы;
- допустимость всех путей внутри архива;
- типы JSON;
- размеры файлов;
- SHA-256 каждого файла.

До нажатия кнопки применения текущие данные не меняются. Непосредственно перед восстановлением создаётся автоматическая копия текущего состояния в `backups/automatic`. Если применение завершается ошибкой, программа автоматически возвращает исходные данные из этой копии.

После полного восстановления перезапустите VicDonationGoal, чтобы интеграции, Streamer.bot Bridge и TTS Hub перечитали перенесённые настройки.

### 35.3. Перенос папки старой версии

Выберите корневую папку старого VicDonationGoal. Браузер передаст только поддерживаемые пользовательские данные; файлы программы, логи, диагностика, кэш и BAT-файлы не копируются.

Папка из более новой major-версии блокируется. Если файл `VERSION` отсутствует, импорт возможен только после успешной проверки известных JSON-структур и сопровождается предупреждением.

### 35.4. Импорт donations.json

Импорт добавляет только записи с отсутствующим `uniqueKey`. Повторяющиеся записи пропускаются. Новые записи:

- по умолчанию не входят в текущую цель;
- учитываются в TopDonation, если это не запрещено самой записью;
- не запускают TTS, Streamer.bot и донат-ивенты.

В предпросмотре можно отдельно включить добавление новых записей в текущий сбор.

### 35.5. Импорт DonationAlerts donations.xls

DonationAlerts экспортирует HTML-таблицу с расширением `.xls`. В ней находится итоговая сумма по каждому имени, а не список отдельных донатов. Поэтому импорт изменяет только TopDonation и не создаёт вымышленные события в истории.

Для каждого имени программа вычисляет:

```text
снимок = итог из DonationAlerts − уже записанные отдельные события DonationAlerts
```

Снимок хранится как специальная корректировка источника. Повторный импорт обновляет её, поэтому одна таблица не накапливается несколько раз. Перед применением отображаются выгрузка, записанные события, предлагаемый снимок и точное изменение TopDonation.

Если профиль уже содержит ручные корректировки, программа покажет предупреждение: историческая сумма могла быть учтена вручную раньше. Такие спорные строки по умолчанию не выбраны; включайте их вручную только после сверки расчёта.

### 35.6. Локальные автоматические копии

Перед восстановлением бэкапа, переносом старой папки, импортом `donations.json` и импортом DonationAlerts всегда создаётся полный автоматический ZIP. Его можно снова выбрать в списке **«Локальные резервные копии»**, проверить и восстановить тем же способом.

## 36. v1.4.5.1 — устойчивость DonationAlerts и навигация TTS

### 36.1. Что означает состояние DonationAlerts

Карточка DonationAlerts различает четыре уровня:

- **OAuth и API** — токен сохранён, а официальный REST API отвечает;
- **Подключено** — live WebSocket/Centrifugo принимает новые донаты;
- **Переподключение** — краткий сетевой обрыв, после которого модуль повторяет попытку автоматически;
- **Требуется действие** — неправильная конфигурация, истёкшая авторизация, отсутствующая зависимость либо длительный обрыв.

Кнопка **«Проверить»** сообщает результат API и live-канала раздельно. Успешная API-проверка не выдаётся за подтверждение WebSocket.

### 36.2. Догон пропущенных донатов

После восстановления WebSocket модуль читает несколько последних страниц официальной истории DonationAlerts. События после сохранённой точки добавляются от старых к новым. Повторные записи блокируются по ключу `donationalerts:<externalId>`.

Состояние хранится в `integrations/donationalerts/donationalerts_catch_up_state.json` и входит в полный резервный ZIP. На первом запуске v1.4.5.1 программа ищет последнюю локальную запись среди свежих событий. Если безопасно продолжить от неё нельзя, создаётся новая стартовая точка без массового импорта старой истории.

### 36.3. Разделы TTS

Пункты **«Очередь»**, **«Голосовые профили»**, **«Правила»**, **«Настройки»**, **«История»** и **«Логи»** находятся в левой панели. Они прокручивают единую страницу TTS к выбранному блоку; текущий пункт меняется автоматически при обычной прокрутке. На узких экранах пункты превращаются в горизонтально прокручиваемую полосу.


## Tribute OBS — прямое подключение, 20 октября 2026

В карточке Tribute укажите персональную ссылку из кнопки «Копировать ссылку для OBS». Сохраните, включите модуль и дождитесь подключения. Кнопка «Проверить донат из Tribute» открывает двухминутный режим для теста из мини-приложения. Переключатель «Учитывать донаты во время проверки» по умолчанию выключен: все события этого периода показываются отдельно, без записи в историю и цель. Кнопка «Завершить проверку» сразу возвращает обычный учёт.

Tribute не помечает тестовые события. Вне проверки учитываются все донаты, включая Anonymous на 999 ₽ и тесты, отправленные без режима проверки. Полученные события сохраняются в очередь при недоступности Core, повторные платежи отсекаются по ID. Восстановление событий за время полного отключения программы пока не подтверждено. Подробная инструкция: `integrations/tribute/GUIDE.md`.


## 37. Обновление до 1.4.6

Основной способ обновления из 1.4.4 и 1.4.5.1 — отдельная новая папка и команда `16_UPDATE_FROM_OLD_VERSION.bat` до запуска Core, TTS и Streamer.bot. Остановите обе версии через `13_STOP_ALL.bat`, выберите старую папку и дождитесь переноса. Полная инструкция в `UPDATE_GUIDE.md` в корне сборки.

Старая папка не изменяется. Сохраняются история, профили, корректировки, настройки и авторизации. Все уже импортированные донаты помечаются обработанными для TTS и Streamer.bot. Незавершённая очередь озвучки остаётся в старой папке/резервной копии, но не запускается в новой. Полный импорт в админке блокируется при работающих внешних модулях. Публичный архив не содержит личной истории и секретов; личный архив отмечен `_my_` и `PRIVATE_BUILD.txt`.
