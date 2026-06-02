STREAMER.BOT BRIDGE ДЛЯ DONATION GOAL WIDGET

Что делает:
- Следит за donations.json.
- Когда появляется новый донат из DonationAlerts или Donatty, отправляет его в Streamer.bot.
- Запускает action "оповещение о донате".
- Передаёт переменные:
  %user%
  %amount%
  %currency%
  %message%

Также передаёт дополнительные переменные:
  %username%
  %donationUser%
  %donor%
  %currencyCode%
  %currencySymbol%
  %amountWithCurrency%
  %source%
  %donationId%

ВАЖНО:
Этот bridge не заменяет server.py и не ломает админку.
Он запускается отдельным окном.

КАК ПОСТАВИТЬ:

1) Скопируй файлы в папку donation_goal_widget:

streamerbot_bridge.py
streamerbot_config.json
install_streamerbot_bridge.bat
start_streamerbot_bridge.bat
test_streamerbot_bridge.bat
reset_streamerbot_sent.bat
start_everything.bat

2) Запусти:
install_streamerbot_bridge.bat

3) В Streamer.bot включи HTTP Server:

Servers/Clients -> HTTP Server

Рекомендуемые настройки:
Host: 127.0.0.1
Port: 7474
Auto Start: включить

4) Проверь action в streamerbot_config.json:

"action_name": "оповещение о донате"

Если action называется иначе — поменяй название.

5) Запусти основной сервер виджета:
start.bat

6) Запусти bridge:
start_streamerbot_bridge.bat

7) Для проверки запусти:
test_streamerbot_bridge.bat

Если всё правильно, Streamer.bot запустит action "оповещение о донате"
с переменными:
%user% = TestUser
%amount% = 133
%currency% = ₽
%message% = Тестовое сообщение доната

ВАЖНО ПРО ДУБЛИ:
Если MiniChat тоже запускает тот же action, при настоящем донате может быть двойное оповещение:
1) от MiniChat
2) от нашего bridge

Для теста лучше:
- либо отключить MiniChat trigger на время проверки;
- либо сделать копию action "оповещение о донате ТЕСТ" и указать это имя в streamerbot_config.json.

Ручные донаты:
По умолчанию bridge НЕ отправляет manual-донаты в Streamer.bot.

Если хочешь отправлять ручные донаты тоже, в streamerbot_config.json поставь:
"send_manual_donations": true

Старые донаты:
При первом запуске bridge помечает все старые донаты как уже отправленные.
Это сделано, чтобы при запуске не проигрались все старые оповещения.

Если нужно сбросить список отправленных:
reset_streamerbot_sent.bat

После сброса старые донаты снова могут считаться новыми.
Аккуратно.
