# VicDonationGoal

**VicDonationGoal** is a local donation goal widget and donation management tool for streamers.

It runs on your computer, collects donations from different services, keeps a local donation history, shows a customizable OBS browser widget, and can trigger Streamer.bot actions for custom alerts.

> The project was made as a practical local streaming utility and can also be used as an educational project demonstrating a small client-server application with external integrations.

## Features

- Local Python HTTP server.
- OBS browser widget for a donation goal bar.
- Web admin panel for managing goals and donation history.
- Manual donation entry.
- Donation history stored locally as JSON.
- Include/exclude each donation from the current goal.
- Optional Streamer.bot alert trigger for manual donations.
- DonationAlerts integration via OAuth and realtime events.
- Donatty integration through an automatic SSE listener.
- Streamer.bot bridge through the local HTTP API.
- Light/dark admin theme.
- CSV export for donation history.
- Manual currency rates for conversion to the goal currency.
- Integration status block in the admin panel.
- Replay button to resend a donation alert to Streamer.bot.
- Built-in local documentation page.
- GitHub-ready example configs with secrets excluded.

## Requirements

- Windows 10/11.
- Python 3.11 or newer.
- OBS Studio, if you want to use the widget on stream.
- Streamer.bot, if you want custom alert actions.
- DonationAlerts and/or Donatty accounts, if you want live donation integrations.

Python dependencies are listed in [`requirements.txt`](requirements.txt):

```txt
requests
websocket-client
playwright
```

The installer also downloads Playwright Chromium because Donatty Auto Listener uses a small hidden browser to capture a fresh SSE URL.

## Quick start

### 1. Install dependencies

Run:

```bat
00_INSTALL_ALL.bat
```

This installs Python packages, downloads Playwright Chromium, and creates local config/data files from examples if they do not exist yet.

### 2. Configure services

Edit local config files created from examples:

```text
core/integrations/donationalerts/da_config.json
integrations/donatty/donatty_config.json
integrations/streamerbot/streamerbot_config.json
```

Private config files are ignored by Git.

### 3. Start everything

Run:

```bat
01_START_ALL.bat
```

It opens three windows:

```text
Core server
Donatty listener
Streamer.bot bridge
```

Admin panel:

```text
http://127.0.0.1:3333/admin.html
```

OBS widget:

```text
http://127.0.0.1:3333/widget.html
```

Documentation page:

```text
http://127.0.0.1:3333/docs/index.html
```

## OBS setup

1. Open OBS.
2. Add a new **Browser Source**.
3. Set URL:

```text
http://127.0.0.1:3333/widget.html
```

Recommended starting size:

```text
Width: 800
Height: 220
```

The widget style is configured in:

```text
core/public/style.css
```

## DonationAlerts setup

1. Create an OAuth application in DonationAlerts.
2. Set redirect URL exactly:

```text
http://127.0.0.1:3333/auth/donationalerts/callback
```

3. Copy the example config:

```text
core/integrations/donationalerts/da_config.example.json
```

into:

```text
core/integrations/donationalerts/da_config.json
```

4. Fill in `client_id` and `client_secret`.
5. Start the core server.
6. Open:

```text
http://127.0.0.1:3333/auth/donationalerts/start
```

7. Authorize the app.

Status endpoint:

```text
http://127.0.0.1:3333/api/da/status
```

## Donatty setup

Donatty internal `sse?jwt=...` links may change. This project uses an Auto Listener:

1. Open:

```text
integrations/donatty/donatty_config.json
```

2. Put your normal Donatty OBS/widget URL into `widget_url`.
3. Keep `sse_url` empty unless you need a fallback.
4. Start:

```bat
03_START_DONATTY_ONLY.bat
```

The listener opens the widget in hidden Chromium, captures a fresh SSE URL from network requests, then listens for donation events.

## Streamer.bot setup

1. In Streamer.bot enable:

```text
Servers/Clients -> HTTP Server
```

Recommended settings:

```text
Host: 127.0.0.1
Port: 7474
Auto Start: enabled
```

2. Open:

```text
integrations/streamerbot/streamerbot_config.json
```

3. Set the action name or action ID.

The bridge sends these variables to Streamer.bot:

```text
%user%
%amount%
%currency%
%message%
```

Additional variables:

```text
%username%
%donationUser%
%donor%
%currencyCode%
%currencySymbol%
%amountWithCurrency%
%source%
%donationId%
```

Test:

```bat
05_TEST_STREAMERBOT.bat
```

If Streamer.bot says `action not found`, open:

```text
http://127.0.0.1:7474/GetActions
```

copy the action ID and paste it into `streamerbot_config.json`.

## Stage 3 utilities

The admin panel also includes several practical utilities:

- **Export CSV** — downloads the donation history as `donations_export.csv`.
- **Replay alert** — sends a selected donation back to Streamer.bot.
- **Integration statuses** — shows local server, DonationAlerts, Donatty and Streamer.bot bridge status.
- **Manual exchange rates** — stores simple currency rates to RUB in `core/data/rates.json`.

CSV export endpoint:

```text
http://127.0.0.1:3333/api/donations/export.csv
```

Status endpoint:

```text
http://127.0.0.1:3333/api/status
```

Rates endpoint:

```text
http://127.0.0.1:3333/api/rates
```

## Project structure

```text
VicDonationGoal/
├─ 00_INSTALL_ALL.bat
├─ 01_START_ALL.bat
├─ 02_START_SERVER_ONLY.bat
├─ 03_START_DONATTY_ONLY.bat
├─ 04_START_STREAMERBOT_ONLY.bat
├─ 05_TEST_STREAMERBOT.bat
├─ 06_RESET_STREAMERBOT_SENT.bat
├─ 07_CREATE_LOCAL_CONFIGS.bat
├─ README.md
├─ LICENSE
├─ requirements.txt
├─ docs/
│
├─ core/
│  ├─ server.py
│  ├─ public/
│  ├─ data/
│  └─ integrations/donationalerts/
│
└─ integrations/
   ├─ donatty/
   └─ streamerbot/
```

## Local files and secrets

The repository contains only example configs. Real local files are ignored:

```text
da_config.json
da_tokens.json
donatty_config.json
streamerbot_config.json
streamerbot_sent.json
state.json
donations.json
rates.json
runtime/
```

Do not publish real service tokens, widget URLs, JWT links, OAuth secrets, or donation history.

## Documentation

A full local manual is available in two places:

Repository docs:

```text
docs/index.html
```

Served by the local app:

```text
http://127.0.0.1:3333/docs/index.html
```

Markdown version:

```text
docs/MANUAL.md
```

## Development notes

This is a local-first project. It intentionally avoids an external database and stores state in JSON files:

```text
core/data/state.json
core/data/donations.json
core/data/rates.json
```

That makes it easy to inspect, backup, and move between machines.

## License

MIT License. See [LICENSE](LICENSE).
