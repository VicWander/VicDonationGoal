# Sanitization report

Removed from the public/GitHub-ready build:

- real DonationAlerts OAuth config and client secret;
- DonationAlerts access/refresh tokens;
- DonationAlerts OAuth state file;
- real Donatty widget URL/token;
- real Streamer.bot action ID and processed-event list;
- real donation history;
- personal current goal state.

Added:

- `.gitignore` for local secrets, runtime data, caches and logs;
- `requirements.txt`;
- `*.example.json` templates for all runtime configs/data;
- `SETUP_CLEAN.md` with clean setup notes.

Basic clean-start check performed:

- Python files compile successfully;
- core server can create fresh placeholder runtime files;
- `/api/state` and `/api/donations` respond on a clean data directory.
