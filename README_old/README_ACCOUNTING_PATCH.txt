ПАТЧ: УЧЁТ ВСЕХ ДОНАТОВ + НОВАЯ АДМИНКА

Что добавляется:
1) У каждого доната теперь есть receivedAt — дата и время добавления автоматически.
2) У каждого доната есть includeInGoal — добавлять ли его в текущий сбор.
3) Донаты из DonationAlerts и Donatty автоматически попадают в историю и по умолчанию идут в сбор.
4) Ручной донат можно добавить из админки: имя, сумма, валюта, сообщение, добавлять/не добавлять в сбор.
5) В админке есть таблица истории: дата, источник, имя, сумма, сообщение, включение в сбор, редактирование, удаление.
6) Сброс сбора теперь НЕ удаляет историю. Он только убирает все старые донаты из текущего сбора.

Какие файлы заменить:
- server.py
- public/admin.html
- public/admin.css
- public/admin.js

Важно:
- public/widget.html, public/widget.js, public/style.css не трогай — твой виджет и оформление останутся как были.
- da_config.json и da_tokens.json не удаляй.
- donatty_listener.py не трогай. Он продолжит отправлять донаты в /api/donation.

Как поставить:
1) Закрой start.bat и start_donatty.bat.
2) Сделай копию всей папки donation_goal_widget на всякий случай.
3) Замени файлы из этого патча.
4) Запусти start.bat.
5) Запусти start_donatty.bat.
6) Открой http://127.0.0.1:3333/admin.html

Новые API:
GET  /api/donations
POST /api/donation
POST /api/donation/update
POST /api/donation/delete
POST /api/set-goal
POST /api/reset
