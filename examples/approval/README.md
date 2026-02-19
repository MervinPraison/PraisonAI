# Praison AI – Approval (CLI, low code)

Route dangerous tool approvals to **Slack**, **Discord**, or **Telegram**.  
See [docs.praison.ai/docs/concepts/approval](https://docs.praison.ai/docs/concepts/approval).

---

## Quick start

1. **Install:** `pip install -r requirements.txt` (or `pip install praisonai`)
2. **Secrets:** Set environment variables (see below). PowerShell: `$env:VAR="value"`. Bash: `export VAR=value`.
3. **Run:**
   - **Slack:** `python slack_approval.py`
   - **Telegram:** `python telegram_approval.py`
   - **Discord:** `python discord_approval.py`
   - **CLI:** `praisonai "your task" --approval slack` (or `telegram` / `discord`).

---

## 1. Install

These examples use `SlackApproval`, `TelegramApproval`, and `DiscordApproval` from [praisonai.bots](https://docs.praison.ai/docs/concepts/approval). Install **praisonai from this repo** so those classes are available:

```bash
pip install -e path/to/PraisonAI/src/praisonai
```

Example (Windows, from repo root):

```bash
pip install -e "c:\Users\DELL\Downloads\testing\PraisonAI\src\praisonai"
```

Then install the rest:

```bash
pip install -r requirements.txt
```

## 2. Set environment variables

Set these in your shell before running. Pick the backend you want:

**Slack**

```bash
export SLACK_BOT_TOKEN=xoxb-your-token
export SLACK_CHANNEL=C0123456789
```

**Discord**

```bash
export DISCORD_BOT_TOKEN=your-bot-token
export DISCORD_CHANNEL_ID=123456789
```

If you get `SSLCertVerificationError` when calling the Discord API, set `PRAISONAI_DISCORD_SSL_VERIFY=false` (use only in trusted environments).

**Telegram**

```bash
export TELEGRAM_BOT_TOKEN=123456:ABC-DEF
export TELEGRAM_CHAT_ID=your-chat-id
```

If you get `SSLCertVerificationError` when calling the Telegram API (e.g. corporate proxy or strict CA), you can disable SSL verification for Telegram only: `PRAISONAI_TELEGRAM_SSL_VERIFY=false` (use only in trusted environments).

You also need an LLM key, e.g.:

```bash
export OPENAI_API_KEY=sk-your-key
```

To require approval (don’t auto-approve), leave unset or set:

```bash
export PRAISONAI_AUTO_APPROVE=false
```

**PowerShell (Windows):** Use `$env:VAR="value"` instead of `export VAR=value`.

## 3. Run with `--approval`

```bash
praisonai "delete old log files" --approval slack
```

```bash
praisonai "deploy to production" --approval slack
```

```bash
praisonai "delete old logs" --approval discord
```

```bash
praisonai "clean up temp files" --approval telegram
```

One command: task + approval backend. The agent will use dangerous tools (e.g. `delete_file`, `execute_command`); each use triggers an approval step (in terminal or in the chosen channel, depending on your setup).

## Other flags

| Flag | Description |
|------|-------------|
| `--approval slack` \| `telegram` \| `discord` | Route approvals to that platform |
| `--trust` | Auto-approve all tools (skip prompts) |
| `--approve-level <level>` | Auto-approve up to a risk level |
| `--approval-timeout <sec>` | Override backend timeout |

## Backends

| Value | Env vars |
|-------|----------|
| `slack` | `SLACK_BOT_TOKEN`, `SLACK_CHANNEL` |
| `discord` | `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID` |
| `telegram` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| `console` | (default terminal prompt) |
| `auto` | Auto-approve |

---

## What’s in this repo

| File | Purpose |
|------|--------|
| `slack_approval.py` | Simple example: approvals go to Slack. Run `python slack_approval.py`. |
| `telegram_approval.py` | Simple example: approvals go to Telegram. Run `python telegram_approval.py`. |
| `discord_approval.py` | Simple example: approvals go to Discord. Run `python discord_approval.py`. |
| `.env.example` | List of variable names to set in your environment (reference only). |
| `requirements.txt` | Python dependencies. |

Approval uses the framework’s built-in `SlackApproval`, `TelegramApproval`, and `DiscordApproval` from `praisonai.bots` (no custom backends).
