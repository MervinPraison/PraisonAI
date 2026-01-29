# PraisonAI Bot Docker Deployment

Deploy Slack, Discord, or Telegram bots using Docker.

## Quick Start

```bash
# 1. Copy environment template
cp .env.template .env

# 2. Edit .env with your tokens
nano .env

# 3. Run specific bot
docker compose up slack-bot -d

# Or run all bots
docker compose up -d
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | LLM API key |
| `SLACK_BOT_TOKEN` | For Slack | Bot token (xoxb-...) |
| `SLACK_APP_TOKEN` | For Slack | App token (xapp-...) |
| `DISCORD_BOT_TOKEN` | For Discord | Bot token |
| `TELEGRAM_BOT_TOKEN` | For Telegram | Bot token |

## Slack Setup

1. Create app at https://api.slack.com/apps
2. Enable **Socket Mode** → Generate App-Level Token with `connections:write`
3. Add **OAuth Scopes**: `chat:write`, `app_mentions:read`, `im:history`
4. Enable **Event Subscriptions** → Subscribe to `app_mention`, `message.im`
5. **Install to Workspace**
6. Copy Bot Token and App Token to `.env`

## Commands

```bash
# Start Slack bot
docker compose up slack-bot -d

# View logs
docker compose logs -f slack-bot

# Stop bot
docker compose down slack-bot

# Rebuild after updates
docker compose build --no-cache slack-bot
```

## Custom Agent Configuration

Mount your agent config:

```yaml
services:
  slack-bot:
    volumes:
      - ./agent.yaml:/app/agent.yaml
    command: ["praisonai", "bot", "slack", "--agent", "/app/agent.yaml"]
```
