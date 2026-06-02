# GitHub publishing guide

## 1. Перед публикацией

Проверь, что в проекте нет приватных файлов:

- `da_config.json`
- `da_tokens.json`
- `da_oauth_state.txt`
- `donatty_config.json`
- `streamerbot_config.json`
- `streamerbot_sent.json`
- `state.json`
- `donations.json`
- `rates.json`

В репозитории должны лежать только `.example.json` версии конфигов и данных.

## 2. Создание репозитория

Вариант через сайт GitHub:

1. Нажать `New repository`.
2. Назвать репозиторий, например `VicDonationGoal`.
3. Не добавлять README через сайт, потому что `README.md` уже есть в проекте.
4. Создать репозиторий.

## 3. Загрузка через Git

В папке проекта:

```bash
git init
git add .
git commit -m "Initial release v1.0.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/VicDonationGoal.git
git push -u origin main
```

## 4. Создание release v1.0.0

1. Открыть репозиторий на GitHub.
2. Перейти в `Releases`.
3. Нажать `Draft a new release`.
4. Создать тег `v1.0.0`.
5. Release title: `VicDonationGoal v1.0.0`.
6. В описание вставить содержимое `RELEASE_NOTES_v1.0.0.md`.
7. Прикрепить архив `VicDonationGoal-v1.0.0.zip`.
8. Нажать `Publish release`.

## 5. После публикации

Проверь страницу репозитория в режиме инкогнито или с другого браузера:

- открывается README;
- скачивается релизный архив;
- в архиве нет приватных конфигов;
- инструкции запуска понятны.
