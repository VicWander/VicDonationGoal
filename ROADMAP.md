# VicDonationGoal Roadmap

Roadmap describes the planned development direction of VicDonationGoal after the first public release.

The current version, **v1.0.0**, is a working local donation goal system with an OBS widget, admin panel, donation history, CSV export, manual currency rates, DonationAlerts integration, Donatty listener, and Streamer.bot bridge.

---

## v1.0.x — Maintenance releases

Small updates after the first public release.

Planned improvements:

- bug fixes discovered during real stream usage;
- README and documentation corrections;
- minor UI polish;
- safer default configuration;
- Excel-friendly CSV export improvements;
- better error messages for first-time setup;
- small stability fixes without changing the main architecture.

Goal: make the current release more stable, predictable, and easier to install.

---

## v1.1 — Stabilization

Focus: polishing the existing system and making it reliable for everyday use.

Planned features:

- improved startup diagnostics;
- better integration status reporting;
- clearer logs for DonationAlerts, Donatty, and Streamer.bot;
- improved handling of connection errors and reconnects;
- better validation for config files;
- cleaner admin panel UX;
- safer replay alert behavior;
- more detailed testing checklist.

Goal: turn the current working version into a stable and comfortable release.

---

## v1.2 — More donation services

Focus: adding more donation platforms while keeping the current modular architecture.

Possible integrations:

- DonatePay;
- Donate.Stream;
- StreamElements;
- Streamlabs;
- other services with public APIs, webhooks, WebSocket, or SSE support.

Each new service should be implemented as a separate adapter/listener that converts incoming donation events into the common VicDonationGoal format:

```json
{
  "source": "service_name",
  "externalId": "...",
  "username": "...",
  "amount": 100,
  "currency": "RUB",
  "message": "...",
  "createdAt": "..."
}
```

Goal: make VicDonationGoal useful for streamers who use different donation platforms.

---

## v1.5 — Settings page in the admin panel

Focus: removing the need to manually edit JSON config files.

Planned features:

- settings page inside the admin panel;
- DonationAlerts settings form;
- Donatty widget URL settings form;
- Streamer.bot settings form;
- manual currency rates editor;
- widget appearance settings;
- integration enable/disable switches;
- config validation from the UI;
- safe save/reload behavior.

Goal: make the project usable without opening code or editing JSON manually.

---

## v2.0 — Desktop application

Focus: turning VicDonationGoal into a user-friendly desktop application.

Possible direction:

- single `.exe` launcher;
- graphical control panel;
- start/stop buttons for server, listeners, and bridges;
- integration setup wizard;
- built-in logs viewer;
- status indicators;
- local web admin panel opened from the app;
- automatic dependency checks;
- easier installation for non-technical users.

The current backend, admin panel, and integration architecture should remain the foundation. The desktop app should act as a convenient launcher and control center rather than a full rewrite.

Goal: make VicDonationGoal feel like a normal desktop program instead of a developer-oriented tool.

---

## Long-term ideas

Possible future improvements:

- multiple donation goals;
- alert queue system;
- custom webhooks;
- automatic currency exchange rates;
- export to Excel;
- import/export settings;
- plugin system for integrations;
- packaged installer;
- multi-language UI;
- better mobile layout for the admin panel.

---

## Development philosophy

VicDonationGoal should stay:

- local-first;
- transparent;
- modular;
- streamer-friendly;
- easy to back up;
- safe with private tokens and user data;
- customizable without depending on one specific donation service.

The project started as a custom OBS donation goal widget, but the long-term goal is to become a flexible local donation dashboard for streamers.
