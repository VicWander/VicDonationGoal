DONATTY AUTO SSE LISTENER

Что изменилось:
Старый listener требовал вручную вставлять внутреннюю ссылку:
https://api-009.donatty.com/widgets/.../sse?jwt=...

Новый listener сам:
1) открывает обычную Donatty-ссылку для OBS/виджета;
2) смотрит Network;
3) ловит свежий /sse?jwt=...;
4) подключается к нему;
5) если токен протух/отвалился, повторяет процесс.

ВАЖНО:
Теперь в donatty_config.json нужна НЕ внутренняя SSE-ссылка,
а обычная ссылка Donatty для OBS/встраивания.

КАК ПОСТАВИТЬ:

1) Закрой старое окно start_donatty.bat.

2) Сделай бэкап старого файла:
donatty_listener.py -> donatty_listener_old.py

3) Скопируй в папку donation_goal_widget файлы из архива:
- donatty_listener.py
- donatty_config.json
- install_donatty_auto.bat
- start_donatty.bat

Если не хочешь перетирать старый donatty_config.json:
можно просто открыть старый и привести его к новому формату.

4) Запусти:
install_donatty_auto.bat

Первый раз он поставит:
- requests
- playwright
- chromium для playwright

Это может занять несколько минут.

5) Открой donatty_config.json.

Вставь обычную ссылку для OBS/встраивания в widget_url:

{
  "enabled": true,
  "widget_url": "https://widgets.donatty.com/ТВОЯ_ССЫЛКА_ОТСЮДА",
  "sse_url": "",
  ...
}

Поле sse_url можно оставить пустым.

6) Запусти:
start_donatty.bat

Должно быть примерно:
[DONATTY] Открываю Donatty-виджет в скрытом браузере...
[DONATTY] Свежий SSE URL пойман из Network.
[DONATTY] Подключаюсь к SSE...
[DONATTY] Подключено. Слушаю донаты Donatty.

7) Проверь тестом в Donatty.

НАСТРОЙКИ:

"headless_browser": true
- true: браузер скрытый
- false: браузер будет открываться видимо, удобно для отладки

"use_old_sse_if_auto_failed": true
- если автополучение не получилось, listener попробует использовать старый sse_url как запасной вариант

"prefer_auto_sse": true
- лучше оставить true

ЕСЛИ НЕ РАБОТАЕТ:

1) Поставь:
"headless_browser": false

2) Запусти start_donatty.bat.

3) Посмотри, открывается ли страница Donatty.

4) Если страница требует авторизацию или не грузит виджет — значит нужна другая ссылка/доступ.

5) Если пишет, что Playwright не установлен — снова запусти install_donatty_auto.bat.

БЕЗОПАСНОСТЬ:
Обычную widget_url тоже лучше не светить на стриме.
Но она стабильнее, чем временная sse?jwt= ссылка.
