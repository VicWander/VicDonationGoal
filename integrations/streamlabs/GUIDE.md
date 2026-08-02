# Streamlabs — Beta

Интеграция использует официальный **OAuth 2.0**, получает `socket token` через API и подключается к real-time Socket.IO событиям Streamlabs.

## Почему пока Beta

Код и формат событий реализованы по официальной документации, но конкретное OAuth-приложение и живой донат должны быть проверены на вашем аккаунте. До одобрения приложения Streamlabs разрешает авторизацию только пользователям из whitelist.

## 1. Создание OAuth-приложения

1. Войдите в Streamlabs.
2. Откройте Streamlabs Developer Console и создайте OAuth Application.
3. Укажите Redirect URI **точно**:

```text
http://127.0.0.1:3333/auth/streamlabs/callback
```

4. Добавьте свой Streamlabs-аккаунт в whitelist, если приложение ещё не одобрено.
5. Скопируйте Client ID и Client Secret.

## 2. Настройка VicDonationGoal

1. Откройте **Интеграции → Streamlabs**.
2. Вставьте Client ID и Client Secret.
3. Не меняйте Redirect URL, если порт Core остаётся 3333.
4. Оставьте scope:

```text
socket.token
```

5. Включите интеграцию и сохраните настройки.
6. Нажмите **Авторизовать**.
7. Разрешите приложению доступ в окне Streamlabs.
8. После возврата в VicDonationGoal нажмите **Проверить**.

## 3. Проверка доната

После успешной проверки сделайте тестовый или маленький настоящий донат. Событие должно появиться в истории с источником `Streamlabs`.

## Что происходит внутри

```text
OAuth access token
→ GET /api/v2.0/socket/token
→ Socket.IO connection
→ event type=donation
→ единый объект VicDonationGoal
```

## Совместимость Socket.IO

Интеграция автоматически пробует Engine.IO v4 и v3. Поле `Engine.IO версии` обычно менять не требуется.

## Типичные проблемы

### Авторизация возвращает ошибку

- Redirect URI не совпадает посимвольно;
- аккаунт не добавлен в whitelist;
- неверный Client ID/Secret;
- приложение Streamlabs удалено или отключено.

### Socket token получен, но handshake не работает

Откройте логи. Интеграция автоматически пробует две версии Engine.IO. Если обе отклонены, пришлите лог без Client Secret и access token.

### Событие не появляется

Проверьте, что это именно Streamlabs Donation event. Twitch subscriptions, bits и YouTube Superchat в v1.4.1 не добавляются в историю донатов автоматически.

## Безопасность

Не публикуйте Client Secret и `streamlabs_tokens.json`. До публичного релиза каждый пользователь создаёт своё OAuth-приложение.
