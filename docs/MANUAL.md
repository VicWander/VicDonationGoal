# VicWander Donation Goal Widget

Полная документация по локальной системе донат-гола, учёта донатов и интеграции с DonationAlerts, Donatty, OBS и Streamer.bot.

---

## 1. Что это такое

**VicWander Donation Goal Widget** — это локальная система для стрима, которая:

- собирает донаты из разных источников;
- ведёт историю всех донатов;
- показывает кастомную полоску сбора в OBS;
- позволяет вручную добавлять донаты;
- позволяет решать, учитывать донат в текущей цели или нет;
- позволяет решать, отправлять ли ручной донат в Streamer.bot как оповещение;
- отправляет события донатов в Streamer.bot;
- работает локально на компьютере.

Основная идея:

```text
DonationAlerts ─┐
                 ├─> Donation Goal Server ──> OBS Widget
Donatty ─────────┘            │
                              ├─> Admin Panel
                              ├─> donations.json
                              └─> Streamer.bot Bridge ──> Streamer.bot Action ──> OBS Alerts
Manual donation ──────────────┘
```

---

## 2. Короткий запуск перед стримом

Если проект уже настроен и зависимости установлены:

1. Открой папку проекта.
2. Запусти:

```text
01_START_ALL.bat
```

3. Должны открыться окна:

```text
Donation Goal Server
Donatty Listener
Streamer.bot Bridge
```

4. Открой админку:

```text
http://127.0.0.1:3333/admin.html
```

5. Виджет для OBS:

```text
http://127.0.0.1:3333/widget.html
```

---

## 3. Первый запуск на новом ПК

### 3.1. Установить зависимости

Запусти:

```text
00_INSTALL_ALL.bat
```

Он должен установить:

```text
requests
websocket-client
playwright
Playwright Chromium
```

Если установка Chromium занимает несколько минут — это нормально.

### 3.2. Проверить Python

Если батник не запускается, проверь, установлен ли Python.

В консоли:

```text
python --version
```

или:

```text
py -3 --version
```

Если Python не найден, установи Python 3.11+ с официального сайта и при установке включи галочку:

```text
Add Python to PATH
```

---

## 4. Структура проекта

После реорганизации проект должен выглядеть примерно так:

```text
donation_goal_widget/
├─ 00_INSTALL_ALL.bat
├─ 01_START_ALL.bat
├─ 02_START_SERVER_ONLY.bat
├─ 03_START_DONATTY_ONLY.bat
├─ 04_START_STREAMERBOT_ONLY.bat
├─ 05_TEST_STREAMERBOT.bat
├─ 06_RESET_STREAMERBOT_SENT.bat
├─ PROJECT_STRUCTURE.txt
│
├─ core/
│  ├─ server.py
│  ├─ public/
│  │  ├─ widget.html
│  │  ├─ widget.js
│  │  ├─ style.css
│  │  ├─ admin.html
│  │  ├─ admin.js
│  │  ├─ admin.css
│  │  ├─ admin-theme.css
│  │  └─ admin-theme.js
│  │
│  ├─ data/
│  │  ├─ state.json
│  │  └─ donations.json
│  │
│  └─ integrations/
│     └─ donationalerts/
│        ├─ da_config.json
│        ├─ da_tokens.json
│        └─ da_oauth_state.txt
│
├─ integrations/
│  ├─ donatty/
│  │  ├─ donatty_listener.py
│  │  └─ donatty_config.json
│  │
│  └─ streamerbot/
│     ├─ streamerbot_bridge.py
│     ├─ streamerbot_config.json
│     └─ streamerbot_sent.json
│
├─ legacy/
└─ README/
```

### Что где лежит

| Путь | Назначение |
|---|---|
| `core/server.py` | Основной локальный сервер |
| `core/public/widget.html` | HTML виджета для OBS |
| `core/public/style.css` | Оформление OBS-виджета |
| `core/public/widget.js` | Логика обновления OBS-виджета |
| `core/public/admin.html` | Админка |
| `core/public/admin.css` | Основное оформление админки |
| `core/public/admin-theme.css` | Светлая/тёмная тема админки |
| `core/public/admin.js` | Логика админки |
| `core/public/admin-theme.js` | Переключатель темы |
| `core/data/state.json` | Текущая цель |
| `core/data/donations.json` | История донатов |
| `core/integrations/donationalerts/da_config.json` | Настройки DonationAlerts |
| `core/integrations/donationalerts/da_tokens.json` | Токены DonationAlerts |
| `integrations/donatty/donatty_listener.py` | Listener Donatty |
| `integrations/donatty/donatty_config.json` | Настройки Donatty |
| `integrations/streamerbot/streamerbot_bridge.py` | Bridge в Streamer.bot |
| `integrations/streamerbot/streamerbot_config.json` | Настройки Streamer.bot |
| `integrations/streamerbot/streamerbot_sent.json` | Список уже отправленных в Streamer.bot событий |

---

## 5. Основной сервер

Основной сервер запускается через:

```text
02_START_SERVER_ONLY.bat
```

или вместе со всем проектом через:

```text
01_START_ALL.bat
```

После запуска доступны адреса:

```text
Админка: http://127.0.0.1:3333/admin.html
Виджет:  http://127.0.0.1:3333/widget.html
API:     http://127.0.0.1:3333/api/state
```

---

## 6. OBS-виджет

### 6.1. Как добавить в OBS

1. Открой OBS.
2. В источниках нажми `+`.
3. Выбери `Браузер` / `Browser Source`.
4. URL:

```text
http://127.0.0.1:3333/widget.html
```

5. Рекомендуемый стартовый размер:

```text
Ширина: 800
Высота: 220
```

6. Включи прозрачный фон, если OBS предлагает такую настройку.

### 6.2. Где менять внешний вид

Оформление полоски лежит в:

```text
core/public/style.css
```

Основные блоки:

```css
.goal-card
.goal-title
.goal-bar
.goal-fill
.goal-bottom
```

### 6.3. Частые настройки

#### Длина полоски

```css
.goal-card {
  width: 700px;
}
```

#### Высота полоски

```css
.goal-bar {
  height: 55px;
}
```

#### Фон незаполненной части

```css
.goal-bar {
  background: rgba(83, 83, 83, 0.747);
}
```

#### Заполненная часть

```css
.goal-fill {
  background: linear-gradient(45deg, #23489e, #3bc7da, #35a9d4);
}
```

#### Текст внутри полоски

```css
.goal-bottom {
  font-size: 26px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.95);
}
```

---

## 7. Админка

Админка открывается по адресу:

```text
http://127.0.0.1:3333/admin.html
```

В ней можно:

- смотреть текущий прогресс цели;
- менять название цели;
- менять стартовую сумму;
- менять итоговую сумму цели;
- вручную добавлять донаты;
- выбирать, добавлять ли ручной донат в текущий сбор;
- выбирать, отправлять ли ручной донат в Streamer.bot;
- смотреть историю всех донатов;
- фильтровать историю;
- редактировать донаты;
- удалять донаты;
- включать/выключать донат из текущего сбора;
- включать/выключать оповещение в Streamer.bot для ручного доната;
- переключать светлую/тёмную тему.

### 7.1. Стартовая сумма

Стартовая сумма — это деньги, которые уже есть, но не связаны с отдельным донатом.

Пример:

```text
До запуска системы уже было собрано 500 RUB.
```

Тогда ставишь:

```text
Стартовая сумма: 500
```

### 7.2. В сбор / не в сбор

У каждого доната есть флаг:

```text
В сбор
```

Если включено — донат прибавляется к текущей цели.

Если выключено — донат остаётся в истории, но не влияет на текущую полоску.

### 7.3. Оповещение в Streamer.bot

У ручных донатов есть флаг:

```text
Отправить оповещение в Streamer.bot
```

Если включено — bridge отправит событие в Streamer.bot.

Если выключено — донат останется только в истории и/или сборе.

---

## 8. DonationAlerts

### 8.1. Что делает интеграция

DonationAlerts подключается к real-time событиям через WebSocket/Centrifugo.

Когда приходит донат:

```text
DonationAlerts -> core/server.py -> donations.json -> widget/admin -> Streamer.bot bridge
```

### 8.2. Создание приложения DonationAlerts

Нужно создать OAuth-приложение в DonationAlerts:

```text
https://www.donationalerts.com/application/clients
```

Redirect URL должен быть **точно**:

```text
http://127.0.0.1:3333/auth/donationalerts/callback
```

Важно: `127.0.0.1` и `localhost` считаются разными адресами. Если в конфиге стоит `127.0.0.1`, в DonationAlerts тоже должен быть `127.0.0.1`.

### 8.3. Настройка da_config.json

Файл:

```text
core/integrations/donationalerts/da_config.json
```

Пример:

```json
{
  "enabled": true,
  "client_id": "ТВОЙ_CLIENT_ID",
  "client_secret": "ТВОЙ_CLIENT_SECRET",
  "redirect_uri": "http://127.0.0.1:3333/auth/donationalerts/callback",
  "scopes": "oauth-user-show oauth-donation-subscribe oauth-donation-index"
}
```

Нужные права:

```text
oauth-user-show
oauth-donation-subscribe
oauth-donation-index
```

### 8.4. Авторизация DonationAlerts

1. Запусти основной сервер:

```text
02_START_SERVER_ONLY.bat
```

или:

```text
01_START_ALL.bat
```

2. Открой:

```text
http://127.0.0.1:3333/auth/donationalerts/start
```

3. Разреши доступ.
4. После успеха токены сохранятся в:

```text
core/integrations/donationalerts/da_tokens.json
```

### 8.5. Проверка статуса

Открой:

```text
http://127.0.0.1:3333/api/da/status
```

Нормальное состояние:

```json
{
  "configured": true,
  "authorized": true,
  "connected": true,
  "running": true
}
```

### 8.6. Безопасность

Не показывай на стриме и не отправляй другим:

```text
da_config.json
da_tokens.json
client_secret
access_token
refresh_token
```

---

## 9. Donatty

### 9.1. Что делает интеграция

Donatty listener получает донаты из Donatty и отправляет их в основной сервер:

```text
Donatty -> donatty_listener.py -> http://127.0.0.1:3333/api/donation
```

### 9.2. Почему нужен Auto Listener

В Donatty внутренняя SSE-ссылка вида:

```text
https://api-009.donatty.com/widgets/.../sse?jwt=...
```

может меняться. Поэтому новый listener не хранит старую SSE-ссылку, а:

1. открывает обычную ссылку виджета Donatty;
2. ловит свежий `/sse?jwt=...` из Network;
3. подключается к нему;
4. при отвале пытается повторить процесс.

### 9.3. Настройка Donatty

Файл:

```text
integrations/donatty/donatty_config.json
```

Пример:

```json
{
  "enabled": true,

  "widget_url": "https://widgets.donatty.com/ТВОЯ_ССЫЛКА_ДЛЯ_OBS",

  "sse_url": "",

  "widget_api_url": "http://127.0.0.1:3333/api/donation",

  "headless_browser": true,
  "sse_capture_timeout_seconds": 35,

  "prefer_auto_sse": true,
  "use_old_sse_if_auto_failed": true,

  "reconnect_delay_seconds": 5,
  "max_reconnect_delay_seconds": 60
}
```

В `widget_url` вставляется обычная ссылка Donatty для OBS/встраивания, не внутренняя `sse?jwt`.

### 9.4. Запуск Donatty listener

Отдельно:

```text
03_START_DONATTY_ONLY.bat
```

Или вместе со всем:

```text
01_START_ALL.bat
```

В норме в окне будет:

```text
[DONATTY] Открываю Donatty-виджет в скрытом браузере...
[DONATTY] Свежий SSE URL пойман из Network.
[DONATTY] Подключаюсь к SSE...
[DONATTY] Подключено. Слушаю донаты Donatty.
```

### 9.5. Если Donatty не подключается

Открой `donatty_config.json` и поставь:

```json
"headless_browser": false
```

Тогда браузер откроется видимо. Можно будет увидеть, грузится ли виджет.

Потом снова запусти:

```text
03_START_DONATTY_ONLY.bat
```

### 9.6. Безопасность

Не показывай публично:

```text
widget_url
sse_url
jwt
```

---

## 10. Streamer.bot

### 10.1. Что делает bridge

Streamer.bot bridge следит за историей донатов и отправляет новые донаты в Streamer.bot.

```text
donations.json -> streamerbot_bridge.py -> Streamer.bot HTTP Server -> action
```

Он запускает action и передаёт переменные:

```text
%user%
%amount%
%currency%
%message%
```

Дополнительные переменные:

```text
%username%
%donationUser%
%donor%
%currencyCode%
%currencySymbol%
%amountWithCurrency%
%source%
%donationId%
```

### 10.2. Настройка Streamer.bot

В Streamer.bot включи HTTP Server:

```text
Servers/Clients -> HTTP Server
```

Рекомендуемые настройки:

```text
Host: 127.0.0.1
Port: 7474
Auto Start: включить
```

### 10.3. Настройка streamerbot_config.json

Файл:

```text
integrations/streamerbot/streamerbot_config.json
```

Пример:

```json
{
  "enabled": true,
  "streamerbot_http_url": "http://127.0.0.1:7474/DoAction",

  "action_name": "оповещение о донате",
  "action_id": "",

  "poll_interval_seconds": 0.5,

  "send_existing_on_first_start": false,
  "send_manual_donations": false,

  "send_sources": [
    "donationalerts",
    "donatty"
  ],

  "currency_mode_for_currency_arg": "symbol",

  "currency_symbols": {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "KZT": "₸"
  },

  "extra_args": {
    "integration": "VicWanderDonationGoal"
  }
}
```

### 10.4. Action ID

Если bridge пишет:

```text
action not found
```

лучше запускать action по ID.

Открой:

```text
http://127.0.0.1:7474/GetActions
```

Найди нужное действие и скопируй `id`.

Вставь в:

```json
"action_id": "ТУТ_ID_ACTION"
```

`action_name` можно оставить для удобства.

### 10.5. Настройка текста в Streamer.bot

В твоём action используется:

```text
%user% — %amount%%currency%
```

и сообщение:

```text
%message%
```

Bridge передаёт именно эти переменные.

Пример:

```text
TestUser — 133₽
Тестовое сообщение доната
```

### 10.6. Тест Streamer.bot

Запусти:

```text
05_TEST_STREAMERBOT.bat
```

Должен запуститься action с тестовыми переменными.

### 10.7. Дубли с MiniChat

Если MiniChat тоже запускает тот же action, может быть двойное оповещение:

```text
MiniChat -> Streamer.bot
наш Bridge -> Streamer.bot
```

Для проверки лучше:

1. сделать копию action;
2. назвать её `оповещение о донате ТЕСТ`;
3. прописать её ID в `streamerbot_config.json`;
4. убедиться, что bridge работает;
5. потом отключить MiniChat trigger или перевести bridge на основной action.

---

## 11. Данные и хранение

### 11.1. state.json

Файл:

```text
core/data/state.json
```

Хранит:

```json
{
  "title": "Сбор на цель",
  "current": 0,
  "baseAmount": 0,
  "goal": 10000,
  "currency": "RUB",
  "lastDonation": null
}
```

`current` пересчитывается автоматически.

### 11.2. donations.json

Файл:

```text
core/data/donations.json
```

Пример записи:

```json
{
  "uniqueKey": "donatty:3376e992-7ac9-43b7-b685-334a176ccbb6",
  "source": "donatty",
  "externalId": "3376e992-7ac9-43b7-b685-334a176ccbb6",
  "username": "3223",
  "amount": 133,
  "currency": "RUB",
  "amountForGoal": 133,
  "includeInGoal": true,
  "notifyStreamerBot": true,
  "message": "12313",
  "createdAt": "2026-05-31T11:24:59.418570589Z",
  "receivedAt": "2026-06-01T23:00:00+07:00",
  "note": ""
}
```

### 11.3. Защита от дублей

Донаты не должны учитываться дважды, потому что используется ключ:

```text
source:externalId
```

Примеры:

```text
donationalerts:123456
donatty:3376e992-7ac9-43b7-b685-334a176ccbb6
manual:random-uuid
```

---

## 12. Валюты

Текущая базовая логика:

- если валюта совпадает с валютой цели — сумма добавляется как есть;
- если цель в RUB, для некоторых валют может использоваться ручная таблица курсов;
- полноценная система курсов пока требует отдельной доработки.

Рекомендуемая будущая логика:

```text
originalAmount: 10
originalCurrency: USD
goalAmount: 900
goalCurrency: RUB
rate: 90
rateSource: manual
```

То есть история должна хранить оригинал, а в сбор добавлять пересчитанную сумму.

---

## 13. Светлая и тёмная тема админки

Файлы:

```text
core/public/admin-theme.css
core/public/admin-theme.js
```

Тема переключается кнопкой в админке.

Выбор сохраняется в браузере через `localStorage`.

Акцентные цвета:

```text
#23489e
#35a9d4
#3bc7da
```

Если тема выглядит старой после правок:

```text
Ctrl + F5
```

---

## 14. Настройка оформления админки

Основной CSS:

```text
core/public/admin.css
```

Тема:

```text
core/public/admin-theme.css
```

Если надо менять общую палитру — лучше править переменные в `admin-theme.css`:

```css
body[data-theme="light"] {
  --bg: #edf3f8;
  --card: #ffffff;
  --text: #172033;
  --accent: #35a9d4;
}
```

```css
body[data-theme="dark"] {
  --bg: #0b0f17;
  --card: #111827;
  --text: #e5e7eb;
  --accent: #35a9d4;
}
```

---

## 15. API

Основные адреса:

| Метод | Адрес | Что делает |
|---|---|---|
| GET | `/api/state` | Текущее состояние цели |
| GET | `/api/donations` | История донатов |
| POST | `/api/donation` | Добавить донат |
| POST | `/api/donation/update` | Обновить донат |
| POST | `/api/donation/delete` | Удалить донат |
| POST | `/api/set-goal` | Обновить цель |
| POST | `/api/reset` | Сбросить текущий сбор, оставив историю |
| GET | `/api/da/status` | Статус DonationAlerts |

Пример ручного добавления через API:

```json
{
  "source": "manual",
  "externalId": "manual-test-1",
  "username": "TestUser",
  "amount": 100,
  "currency": "RUB",
  "message": "Тест",
  "includeInGoal": true,
  "notifyStreamerBot": false
}
```

---

## 16. Батники

| Батник | Что делает |
|---|---|
| `00_INSTALL_ALL.bat` | Установка зависимостей |
| `01_START_ALL.bat` | Запуск всего перед стримом |
| `02_START_SERVER_ONLY.bat` | Только основной сервер |
| `03_START_DONATTY_ONLY.bat` | Только Donatty listener |
| `04_START_STREAMERBOT_ONLY.bat` | Только Streamer.bot bridge |
| `05_TEST_STREAMERBOT.bat` | Тестовый запуск Streamer.bot action |
| `06_RESET_STREAMERBOT_SENT.bat` | Сброс списка отправленных в Streamer.bot событий |

---

## 17. Типичные проблемы

### 17.1. Виджет не открывается

Проверь, запущен ли основной сервер.

Должно быть открыто окно:

```text
Donation Goal Widget запущен
```

Адрес:

```text
http://127.0.0.1:3333/widget.html
```

### 17.2. Админка не обновляется

Попробуй:

```text
Ctrl + F5
```

Проверь:

```text
http://127.0.0.1:3333/api/state
```

Если API не открывается — сервер не запущен.

### 17.3. DonationAlerts не подключается

Проверь:

```text
http://127.0.0.1:3333/api/da/status
```

Частые причины:

- неверный `client_id`;
- неверный `client_secret`;
- redirect URL не совпадает символ в символ;
- не пройдена авторизация;
- токен протух.

### 17.4. Donatty не подключается

Проверь:

```text
integrations/donatty/donatty_config.json
```

Убедись, что вставлена обычная ссылка виджета, а не старая `sse?jwt`.

Если не помогает:

```json
"headless_browser": false
```

и перезапусти Donatty listener.

### 17.5. Streamer.bot пишет `action not found`

Открой:

```text
http://127.0.0.1:7474/GetActions
```

Найди action и вставь его ID в `streamerbot_config.json`.

### 17.6. Двойные оповещения

Скорее всего, одновременно работают:

```text
MiniChat trigger
Streamer.bot Bridge
```

Отключи MiniChat trigger или используй отдельный test action.

### 17.7. При запуске проигрались старые донаты

Bridge хранит список отправленных событий в:

```text
integrations/streamerbot/streamerbot_sent.json
```

Если его удалить или сбросить, старые донаты могут считаться новыми.

### 17.8. Светлая тема выглядит криво

Обнови страницу:

```text
Ctrl + F5
```

Проверь, что подключены:

```html
<link rel="stylesheet" href="admin-theme.css" />
<script src="admin-theme.js"></script>
```

---

## 18. Безопасность

Не публиковать:

```text
da_config.json
da_tokens.json
donatty_config.json
streamerbot_config.json
streamerbot_sent.json
```

Особенно опасны:

```text
client_secret
access_token
refresh_token
widget_url Donatty
sse_url Donatty
jwt
```

Если ссылка Donatty засветилась — лучше пересоздать ссылку виджета, если Donatty позволяет.

---

## 19. Бэкапы

Перед крупными изменениями делай копию папки:

```text
donation_goal_widget_BACKUP_дата
```

Особенно важно сохранить:

```text
core/data/state.json
core/data/donations.json
core/integrations/donationalerts/da_config.json
core/integrations/donationalerts/da_tokens.json
integrations/donatty/donatty_config.json
integrations/streamerbot/streamerbot_config.json
```

---

## 20. Что можно добавить потом

Идеи на будущее:

- нормальный пересчёт валют;
- ручная таблица курсов в админке;
- экспорт истории донатов в CSV/Excel;
- несколько целей;
- отдельные цели для разных источников;
- кнопка “повторить оповещение”;
- очередь оповещений;
- статусы Donatty/Streamer.bot прямо в админке;
- встроенная страница настроек;
- автообновление конфигов из админки;
- лог ошибок на отдельной странице;
- упаковка в `.exe`.

---

## 21. Быстрый чеклист перед стримом

```text
[ ] Запустить 01_START_ALL.bat
[ ] Открыть админку
[ ] Проверить, что сбор правильный
[ ] Проверить, что OBS видит widget.html
[ ] Проверить Streamer.bot HTTP Server
[ ] Проверить тест Streamer.bot, если были изменения
[ ] Проверить Donatty listener
[ ] Проверить DonationAlerts status
[ ] Не светить приватные ссылки на стриме
```


---

## 22. Stage 3: полезные функции

### Экспорт CSV

В админке есть кнопка **Экспорт CSV**. Она скачивает историю донатов в файл `donations_export.csv`.

Прямой адрес:

```text
http://127.0.0.1:3333/api/donations/export.csv
```

### Повторить оповещение

В истории донатов есть кнопка **Повт.**. Она ставит выбранный донат обратно в очередь Streamer.bot.

Если `streamerbot_sent.json` ещё не создан, сервер помечает остальные старые донаты как уже обработанные, чтобы при следующем запуске bridge не проиграл всю историю.

### Блок статусов

Админка показывает статусы:

```text
Локальный сервер
DonationAlerts
Donatty
Streamer.bot
```

Donatty и Streamer.bot пишут heartbeat-файлы в папку `runtime/`. Если процесс закрыт, статус станет устаревшим.

### Ручные курсы валют

Курсы хранятся в:

```text
core/data/rates.json
```

Пример:

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

Курс означает, сколько рублей стоит 1 единица валюты.
