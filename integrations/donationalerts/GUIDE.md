# Подключение DonationAlerts

1. В кабинете DonationAlerts откройте раздел API Applications и создайте приложение.
2. Укажите Redirect URL точно: `http://127.0.0.1:3333/auth/donationalerts/callback`.
3. Скопируйте `Client ID` и `Client Secret` в настройки Integration Hub.
4. Сохраните конфигурацию.
5. Нажмите **Авторизовать** и разрешите доступ в DonationAlerts.
6. Вернитесь в Integration Hub и нажмите **Проверить**.

Используемые scopes:

- `oauth-user-show` — профиль пользователя;
- `oauth-donation-subscribe` — новые донаты в real time;
- `oauth-donation-index` — чтение донатов.

Client Secret и полученные токены являются приватными. Не публикуйте личную папку программы.
