# Быстрый запуск VicWander Donation Goal Widget

## Первый запуск на новом ПК

1. Распакуй проект.
2. Запусти:

```text
00_INSTALL_ALL.bat
```

3. Настрой:
   - DonationAlerts: `core/integrations/donationalerts/da_config.json`
   - Donatty: `integrations/donatty/donatty_config.json`
   - Streamer.bot: `integrations/streamerbot/streamerbot_config.json`

4. Авторизуй DonationAlerts:

```text
http://127.0.0.1:3333/auth/donationalerts/start
```

5. В OBS добавь Browser Source:

```text
http://127.0.0.1:3333/widget.html
```

## Каждый раз перед стримом

Запусти:

```text
01_START_ALL.bat
```

Админка:

```text
http://127.0.0.1:3333/admin.html
```

Виджет:

```text
http://127.0.0.1:3333/widget.html
```
