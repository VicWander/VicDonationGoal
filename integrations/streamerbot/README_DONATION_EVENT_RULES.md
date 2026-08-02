# Donation Event Rules для Streamer.bot Bridge

Donation Event Rules позволяют запускать дополнительные действия Streamer.bot по сумме, валюте и источнику доната.

Теперь bridge делает две вещи:

1. как раньше отправляет обычное оповещение о донате в основной Streamer.bot action;
2. отдельно проверяет `donation_event_rules.json` и при совпадении суммы запускает дополнительный Streamer.bot action.

## Файлы

```text
integrations/streamerbot/streamerbot_bridge.py
integrations/streamerbot/donation_event_rules.json
integrations/streamerbot/donation_event_rules.example.json
integrations/streamerbot/streamerbot_event_rules_sent.json
```

`streamerbot_event_rules_sent.json` создаётся автоматически. Он хранит, какие пары `донат + правило` уже были отправлены, чтобы не было дублей.

## Примеры правил

```text
10 RUB exact -> PASTE_STREAMERBOT_ACTION_ID_HERE -> небольшая анимация
1000 RUB or more -> PASTE_STREAMERBOT_ACTION_ID_HERE -> особое оповещение
```

В публичном примере правила выключены. После добавления своего Action ID выберите нужные источники, например:

```text
donationalerts
donatty
streamelements
donatepay
```

Ручные донаты `manual` лучше добавлять только после проверки, чтобы тест из админки случайно не запустил реальную сцену или звук.

## Как устроено правило

```json
{
  "id": "example_20_rub_event",
  "enabled": false,
  "name": "Пример события на 20 RUB",
  "sources": ["donationalerts", "donatty"],
  "match": "equals",
  "amount": 20,
  "currency": "RUB",
  "amount_field": "amount",
  "epsilon": 0.001,
  "action_id": "PASTE_STREAMERBOT_ACTION_ID_HERE",
  "action_name": ""
}
```

Поля:

| Поле | Что значит |
|---|---|
| `id` | постоянный ID правила внутри VicDonationGoal |
| `enabled` | включено ли правило |
| `name` | понятное название для логов |
| `sources` | источники донатов |
| `match` | условие сравнения суммы |
| `amount` | сумма |
| `currency` | валюта доната |
| `amount_field` | какое поле сравнивать: `amount` или `amountForGoal` |
| `epsilon` | допуск для сравнения `20`, `20.0`, `20.00` |
| `action_id` | ID действия Streamer.bot |
| `action_name` | запасное имя действия, лучше использовать именно `action_id` |

## Поддерживаемые условия

```text
equals / eq / exact / ==
greater_or_equal / gte / >= / min / at_least
greater / gt / >
less_or_equal / lte / <= / max / at_most
less / lt / <
between / range
```

Для диапазона:

```json
{
  "match": "between",
  "min": 50,
  "max": 100
}
```

## Какие переменные уходят в Streamer.bot

В дополнительный action уходят те же переменные, что и в обычное оповещение:

```text
%user%
%amount%
%currency%
%message%
%username%
%amountRaw%
%amountForGoal%
%amountForGoalRaw%
%currencyCode%
%currencySymbol%
%source%
%donationId%
```

Плюс новые переменные для правил:

```text
%isDonationEvent%
%donationEventRuleId%
%donationEventRuleName%
%donationEventMatch%
%donationEventAmount%
%donationEventCurrency%
%donationEventAmountField%
```

Твои текущие actions с условием `if "%amount%" equals "10"` и `if "%amount%" equals "20"` должны работать, потому что bridge передаёт красивую сумму через `%amount%`: `10`, `20`, `133`.

## Как поставить

1. Закрой окно Streamer.bot Bridge.
2. Скопируй файлы из патча в проект с заменой.
3. Запусти `04_START_STREAMERBOT_ONLY.bat` или `01_START_ALL.bat`.
4. В консоли bridge должно быть примерно:

```text
Event rules: on (2 rules)
```

5. На донат 10 RUB должен отправиться action "рука тыкает".
6. На донат 20 RUB должен отправиться action "рука гладит".

## Если надо заново протестировать старый донат

Удали файл:

```text
integrations/streamerbot/streamerbot_event_rules_sent.json
```

Но осторожно: если в истории уже есть донаты на 10/20, bridge может пометить их как старые при первом запуске. Для реального теста лучше создать новый тестовый донат или временно поставить `process_existing_on_first_start: true`.
