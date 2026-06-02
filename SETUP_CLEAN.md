# Clean setup notes

This public build intentionally does **not** include local secrets, tokens, private widget URLs, real donation history, or personal state.

On first launch the app can create placeholder runtime files automatically:

- `core/data/state.json`
- `core/data/donations.json`
- `core/integrations/donationalerts/da_config.json`
- `integrations/donatty/donatty_config.json`
- `integrations/streamerbot/streamerbot_config.json`
- `integrations/streamerbot/streamerbot_sent.json`

You can also copy the example files manually:

```text
core/data/state.example.json -> core/data/state.json
core/data/donations.example.json -> core/data/donations.json
core/integrations/donationalerts/da_config.example.json -> core/integrations/donationalerts/da_config.json
integrations/donatty/donatty_config.example.json -> integrations/donatty/donatty_config.json
integrations/streamerbot/streamerbot_config.example.json -> integrations/streamerbot/streamerbot_config.json
```

Never commit real config files with tokens or private links.
