# Tribute — v1.4.3

Tribute отправляет webhook на публичный HTTPS URL. Локальный адрес `127.0.0.1` из интернета недоступен, поэтому для тестовой версии используется Cloudflare Quick Tunnel.

## Шаг 1. Установить cloudflared

Запустите:

```text
12_INSTALL_CLOUDFLARED.bat
```

Исправленный установщик скачивает официальный Windows-бинарник и сохраняет его как:

```text
tools/cloudflared.exe
```

## Шаг 2. Настроить Tribute

В Integration Hub заполните:

- **API-ключ Tribute** — ключ из мини-приложения Tribute;
- **Секрет в адресе webhook** — придуманная вами длинная случайная строка, это не API-ключ;
- путь `tools/cloudflared.exe`;
- **Автоматически запускать Quick Tunnel** — включено;
- публичный URL — оставить пустым.

Сохраните настройки, включите интеграцию и нажмите **Запустить**.

## Шаг 3. Получить URL

Через несколько секунд в **Техническом состоянии** появится поле:

```text
publicWebhookUrl
```

Скопируйте его полностью. Адрес выглядит примерно так:

```text
https://random-words.trycloudflare.com/api/integrations/tribute/webhook/ВАШ_СЕКРЕТ
```

## Шаг 4. Вставить URL в Tribute

В мини-приложении Tribute вставьте полный адрес в поле **WEBHOOK URL**, сохраните и нажмите **Отправить тестовый запрос**.

Tribute подписывает запрос заголовком `trbt-signature`. VicDonationGoal проверяет HMAC-SHA256 по вашему API-ключу.

Quick Tunnel временный: после перезапуска адрес `trycloudflare.com` может измениться. Новый `publicWebhookUrl` нужно снова вставить в Tribute.
