# Approval Examples

Minimal examples showing how to route tool-execution approvals through
different backends.

## Quick Start

```bash
pip install praisonaiagents praisonai[bot]
export OPENAI_API_KEY=sk-...
```

| Backend  | Script               | Extra env vars                                   |
|----------|-----------------------|--------------------------------------------------|
| Slack    | `slack_approval.py`   | `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`               |
| Telegram | `telegram_approval.py`| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`         |
| Discord  | `discord_approval.py` | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`        |
| HTTP     | `http_approval.py`    | *(none — opens a local web dashboard)*           |
| Agent    | `agent_approval.py`   | *(none — AI reviewer agent decides)*             |

## SSL Verification

For corporate proxy / CA issues, Discord and Telegram backends support
optional SSL bypass:

```bash
export PRAISONAI_DISCORD_SSL_VERIFY=false
export PRAISONAI_TELEGRAM_SSL_VERIFY=false
```

Default is `true` (secure).
