# Desktop Channels & Gateway

## What's new

- **Channels** sidebar tab: add Telegram/Slack bots, start/stop individually
- **Gateway** sidebar tab: run multi-bot gateway on `127.0.0.1:8765`

Tokens use `env:TELEGRAM_BOT_TOKEN`, `env:SLACK_BOT_TOKEN`, `env:SLACK_APP_TOKEN` resolved from:

1. Process environment
2. `~/.praisonai/.env` (loaded automatically)

## Engine API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/bots/channels` | List channels |
| POST | `/bots/channels` | Add channel |
| PUT | `/bots/channels/{id}` | Update channel |
| DELETE | `/bots/channels/{id}` | Remove channel |
| POST | `/bots/channels/{id}/start` | Start bot |
| POST | `/bots/channels/{id}/stop` | Stop bot |
| GET | `/bots/gateway` | Gateway status |
| POST | `/bots/gateway/start` | Start gateway |
| POST | `/bots/gateway/stop` | Stop gateway |
| GET | `/bots/logs?target={id\|gateway}` | Log tail |

## Dev run

```powershell
cd src/praisonai-desktop/src-tauri
cargo tauri dev
```

Or test engine only:

```powershell
cd src/praisonai-desktop/engine
$env:PRAISONAI_DESKTOP_HOME = "$env:TEMP\praison-desktop-dev"
py -3.13 server.py
```

## Tests

```powershell
cd src/praisonai-desktop/engine
py -3.13 test_bots.py -v
py -3.13 test_bots_routes.py -v
```

## Notes

- Only one poller per Telegram token: stop gateway before starting individual Telegram bot (and vice versa)
- `unknown_user_policy: allow` is set on generated bot YAML
- Gateway config is written to `%APPDATA%\PraisonAI\bots\gateway.yaml`
