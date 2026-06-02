# Stage 3 Report — Mini features

Implemented on top of Stage 2.

## Added

- CSV export for donation history: `/api/donations/export.csv`.
- Replay notification endpoint: `/api/donation/replay`.
- Admin button **Повт.** for resending selected donation alerts to Streamer.bot.
- Combined status endpoint: `/api/status`.
- Status block in admin panel for server, DonationAlerts, Donatty and Streamer.bot.
- Runtime heartbeat files in `runtime/` for Donatty and Streamer.bot bridge.
- Manual currency rates in `core/data/rates.json`.
- `core/data/rates.example.json`.
- Admin UI for USD/EUR/KZT and extra JSON rates.

## Safety notes

`runtime/`, `state.json`, `donations.json`, `rates.json`, service configs and token files are ignored by Git.

When replaying an alert before `streamerbot_sent.json` exists, the server seeds the sent file with all old donations except the selected one. This prevents accidental replay of the full history.

## Tested

- Python syntax compilation for server, Donatty listener and Streamer.bot bridge.
- JavaScript syntax check for admin.js.
- Clean server startup.
- `/api/state`, `/api/donations`, `/api/rates`, `/api/status`.
- Manual USD donation conversion using rates.
- CSV export endpoint.
- Replay endpoint and safe creation of `streamerbot_sent.json`.
