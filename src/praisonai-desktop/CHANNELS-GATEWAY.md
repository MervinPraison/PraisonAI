# Desktop Channels & Gateway

## What's new

- **Onboarding** (3 steps): API key + test “Hi” → optional Knowledge folder → Channels env hints (Telegram / Slack / Discord)
- **Engine auto-start**: engine starts when the window opens (`engine_status` on load); **Settings → Restart engine** after code updates
- **Knowledge (RAG)**: index folders, **Test retrieval**, chat **Knowledge** toggle (tools auto-off)
- **Channels** sidebar tab: add Telegram, Slack, or Discord bots; start/stop individually; **View log**
- **Gateway** sidebar tab: run multi-bot gateway on `127.0.0.1:8765`
- **Images** tab: DALL·E image generation (OpenAI key)
- **Video** tab: Replicate video (optional `REPLICATE_API_TOKEN`)
- **Settings → Restart engine**: pick up new engine code without stale adoption

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

## Recommended workflow (Telegram + Slack together)

1. Put tokens in `~/.praisonai/.env` (do not paste raw tokens in the UI).
2. **Channels** → add Telegram and Slack (`env:TELEGRAM_BOT_TOKEN`, etc.).
3. Leave every channel **Stopped**.
4. **Gateway** → **Start gateway** once.
5. Test: Telegram DM the bot; Slack DM or `@mention` in a channel (invite the bot first).

Do **not** click **Channels → Start** while Gateway is running (one poller per token).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Bot never replies | Ensure `unknown_user_policy: allow` in `gateway.yaml`; restart gateway |
| `Unauthorized` on start | Refresh token in `~/.praisonai/.env`; restart Desktop so engine reloads env |
| Add/Delete does nothing | Engine needs CORS `Allow-Methods` fix (included in this branch) |
| Gateway start blocked | Stop all channel bots on the Channels tab first |

## Notes

- Only one poller per token: stop gateway before starting an individual channel bot (and vice versa)
- `unknown_user_policy: allow` is set on generated YAML; re-applied after gateway migrates config
- Gateway config: `%APPDATA%\PraisonAI\bots\gateway.yaml`
