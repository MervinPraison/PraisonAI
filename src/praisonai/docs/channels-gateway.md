# Channels gateway integration

Channel bots (Telegram, Discord, Slack, WhatsApp) require the **`praisonai[bot]`** optional extra:

```bash
pip install "praisonai[bot]"
```

## Architecture

- **Pattern B/C host**: `configure_host()` + `AIUIGateway` serve chat UI and REST APIs.
- **Channels feature** (`praisonaiui.features.channels`): starts platform bots via `praisonai.bots`.
- **Gateway WebSocket**: `/ws` on the same process when using Pattern C.

## Environment variables

| Platform | Variables |
|----------|-------------|
| Telegram | `TELEGRAM_BOT_TOKEN` |
| Discord | `DISCORD_BOT_TOKEN` |
| Slack | `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` |
| WhatsApp | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` |

## CLI

```bash
praisonai dashboard --aiui          # Pattern B in-process host
PRAISONAI_HOST_LEGACY=1 praisonai ui  # Legacy @aiui.reply callbacks only
```

See `praisonai.bots.BotOS` for multi-platform orchestration.
