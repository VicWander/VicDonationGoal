ПАТЧ ДЛЯ ПОДКЛЮЧЕНИЯ DONATIONALERTS REAL-TIME

Файлы из этого архива нужно скопировать в твою папку donation_goal_widget.

ВАЖНО:
- public/style.css, public/widget.js и твой внешний вид этот патч не трогает.
- Заменяется только server.py.
- Добавляются requirements.txt, install.bat, da_config.json.

ШАГИ:

1) Закрой сервер виджета, если он сейчас запущен.

2) На всякий случай сделай копию старого server.py.
Например переименуй:
server.py -> server_old.py

3) Скопируй файлы из этого архива в папку donation_goal_widget:
- server.py
- requirements.txt
- install.bat
- start.bat
- da_config.json

4) Запусти install.bat.
Он установит библиотеки:
- requests
- websocket-client

5) Создай OAuth-приложение в DonationAlerts:
https://www.donationalerts.com/application/clients

Redirect URL должен быть ТОЧНО:
http://127.0.0.1:3333/auth/donationalerts/callback

6) Открой da_config.json и вставь:
- client_id
- client_secret

Пример:
{
  "enabled": true,
  "client_id": "123456",
  "client_secret": "abcdefg...",
  "redirect_uri": "http://127.0.0.1:3333/auth/donationalerts/callback",
  "scopes": "oauth-user-show oauth-donation-subscribe oauth-donation-index"
}

7) Запусти start.bat.

8) Открой в браузере:
http://127.0.0.1:3333/auth/donationalerts/start

9) Разреши доступ DonationAlerts.

10) После успешной авторизации открой:
http://127.0.0.1:3333/api/da/status

Если всё хорошо, там будет:
"connected": true

11) Сделай тестовый донат / попроси кого-то задонатить.
Полоска должна обновиться почти сразу.

Если не работает:
- Проверь, что Redirect URL в DonationAlerts и da_config.json совпадают символ в символ.
- Проверь, что install.bat выполнился без ошибок.
- Посмотри чёрное окно сервера: там будут строки с [DA].
- Открой /api/da/status и посмотри last_error.
