# Multi-Channel Bot Deployment Guide

This guide explains how to set up multiple bots on the same platform (e.g., multiple Telegram bots) for different roles using PraisonAI, similar to Hermes-style AI workforces.

## Overview

PraisonAI supports running multiple bots on the same platform, each routing to different agents with specialized knowledge and capabilities. This is useful for:

- **Role-based bots**: `@company_cfo_bot`, `@company_ops_bot`, `@company_content_bot`
- **Department-specific agents**: Each with different knowledge brains and tool access
- **Workflow separation**: Different bots handle different types of requests

## Quick Start with Onboard Wizard

The easiest way to set up multiple channels is using the onboard wizard:

```bash
praisonai onboard
```

The wizard now supports:
1. **Multi-channel setup**: Add multiple bots for the same platform
2. **Role-based naming**: Automatically generates `TELEGRAM_<ROLE>_BOT_TOKEN` environment variables
3. **Agent routing**: Each channel routes to a different agent

### Onboard Wizard Flow

1. **Choose platform**: Start with your first platform (e.g., telegram)
2. **Add more channels**: Wizard asks "Add another bot channel?"
3. **Specify role**: Enter role name (e.g., "cfo", "ops", "content")
4. **Configure tokens**: Each channel gets its own environment variable
5. **Test connections**: Wizard tests each bot separately

## Environment Variable Convention

For multiple bots on the same platform, use this naming convention:

| Channel | Environment Variable | Bot Purpose |
|---------|---------------------|-------------|
| `telegram_cfo` | `TELEGRAM_CFO_BOT_TOKEN` | CFO-related tasks |
| `telegram_ops` | `TELEGRAM_OPS_BOT_TOKEN` | Operations tasks |
| `telegram_content` | `TELEGRAM_CONTENT_BOT_TOKEN` | Content creation |
| `telegram_support` | `TELEGRAM_SUPPORT_BOT_TOKEN` | Customer support |

### Setting Up Tokens

1. **Create bots in @BotFather**:
   ```text
   /newbot
   Bot name: Company CFO Bot
   Username: @company_cfo_bot
   -> Copy token
   
   /newbot
   Bot name: Company Ops Bot
   Username: @company_ops_bot
   -> Copy token
   ```

2. **Set environment variables**:
   ```bash
   export TELEGRAM_CFO_BOT_TOKEN="123456789:ABC..."
   export TELEGRAM_OPS_BOT_TOKEN="987654321:DEF..."
   export TELEGRAM_CONTENT_BOT_TOKEN="456789123:GHI..."
   ```

3. **Or use `~/.praisonai/.env`**:
   ```env
   TELEGRAM_CFO_BOT_TOKEN=123456789:ABC...
   TELEGRAM_OPS_BOT_TOKEN=987654321:DEF...
   TELEGRAM_CONTENT_BOT_TOKEN=456789123:GHI...
   TELEGRAM_ALLOWED_USERS=123456789,987654321
   ```

## Example Configuration

See `multi-telegram-hermes-workforce.yaml` for a complete example.

### Key Features

1. **Multiple Channels**:
   ```yaml
   channels:
     telegram_cfo:
       platform: telegram
       token: ${TELEGRAM_CFO_BOT_TOKEN}
       routes:
         default: cfo
     
     telegram_ops:
       platform: telegram
       token: ${TELEGRAM_OPS_BOT_TOKEN}
       routes:
         default: ops
   ```

2. **Specialized Agents**:
   ```yaml
   agents:
     cfo:
       instructions: "You are a CFO agent. Help with financial analysis..."
       model: gpt-4o-mini
     
     ops:
       instructions: "You are an ops agent. Help with system monitoring..."
       model: gpt-4o-mini
   ```

## Validation with Doctor

Use the doctor command to validate your multi-channel setup:

```bash
praisonai doctor
```

The doctor checks for:
- ✅ **Unique tokens**: Each channel uses a different bot token
- ✅ **Naming convention**: Follows `PLATFORM_ROLE_BOT_TOKEN` pattern  
- ✅ **Missing tokens**: All referenced environment variables are set
- ❌ **Duplicate tokens**: Same token used by multiple channels (fails)

## Deployment

### Start Gateway

```bash
# Start the multi-bot gateway
praisonai gateway start --config multi-telegram-hermes-workforce.yaml

# Or install as daemon
praisonai onboard  # Wizard installs daemon automatically
praisonai gateway status
```

### Verify Setup

1. **Check health**: `curl http://127.0.0.1:8765/health`
2. **View dashboard**: `praisonai claw` → http://127.0.0.1:8082
3. **Test bots**: Send messages to each bot to verify routing

## Common Patterns

### Basic Multi-Role Setup
```yaml
# Single platform, multiple roles
channels:
  telegram_support:
    token: ${TELEGRAM_SUPPORT_BOT_TOKEN}
    routes:
      default: support_agent
  
  telegram_sales:
    token: ${TELEGRAM_SALES_BOT_TOKEN}
    routes:
      default: sales_agent
```

### Cross-Platform Workforce
```yaml
# Multiple platforms, multiple roles
channels:
  telegram_cfo:
    platform: telegram
    token: ${TELEGRAM_CFO_BOT_TOKEN}
    routes:
      default: cfo
  
  discord_ops:
    platform: discord
    token: ${DISCORD_OPS_BOT_TOKEN}
    routes:
      default: ops
  
  slack_content:
    platform: slack
    token: ${SLACK_CONTENT_BOT_TOKEN}
    routes:
      default: content
```

## Troubleshooting

### Common Issues

1. **"Token is used by multiple channels"**
   - Each bot needs its own unique token from @BotFather
   - Check environment variables for duplicates

2. **"Channel skipped - no token"**
   - Set the environment variable: `export TELEGRAM_CFO_BOT_TOKEN="..."`
   - Or update `~/.praisonai/.env`

3. **"Bot not responding"**
   - Verify token is correct: `praisonai doctor`
   - Check bot is not already running elsewhere
   - Ensure allowlist includes your user ID

### Debugging Commands

```bash
# Check configuration
praisonai doctor

# View logs
praisonai gateway logs

# Test connection
curl -H "Authorization: Bearer $GATEWAY_AUTH_TOKEN" \
     http://127.0.0.1:8765/info
```

## Migration from Single-Bot Setup

If you currently have a single bot setup, you can add more channels:

1. **Run onboard wizard**: `praisonai onboard`
2. **Add new channels**: Wizard will preserve existing setup
3. **Update configuration**: New channels added to existing `bot.yaml`
4. **Restart gateway**: `praisonai gateway restart`

The wizard preserves backward compatibility with single-bot configurations.