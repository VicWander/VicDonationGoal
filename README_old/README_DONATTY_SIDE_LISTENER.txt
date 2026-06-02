DONATTY LISTENER ДЛЯ DONATION GOAL WIDGET

Этот патч НЕ заменяет server.py.
Он запускается отдельным окном и отправляет донаты Donatty в уже работающий локальный сервер виджета.

Файлы:
- donatty_listener.py
- donatty_config.json
- install_donatty.bat
- start_donatty.bat
- start_all.bat

Как поставить:

1) Скопируй все файлы из архива в папку donation_goal_widget.

2) Запусти install_donatty.bat.
Если requests уже установлен, ничего страшного.

3) Открой donatty_config.json.

4) Поставь enabled: true.

5) В sse_url вставь ПОЛНУЮ ссылку из DevTools Network.
Нужна именно строка, у которой:
Type: eventsource
Content-Type: text/event-stream
URL примерно содержит /sse?jwt=...

Пример:
{
  "enabled": true,
  "sse_url": "https://api-009.donatty.com/widgets/.../sse?jwt=...",
  "widget_api_url": "http://127.0.0.1:3333/api/donation"
}

6) Сначала запусти основной сервер виджета через start.bat.

7) Потом запусти start_donatty.bat.

8) Нажми тестовый донат в Donatty.
В окне должно появиться:
[DONATTY] Донат: ...

Полоска должна обновиться.

Можно запускать сразу оба окна через start_all.bat,
но только если start.bat лежит в этой же папке и уже нормально работает.

Важно:
SSE-ссылка Donatty содержит токен. Не показывай её на стриме.
