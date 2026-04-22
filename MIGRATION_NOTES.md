# Migration Notes for auto_approve_tools Behavioral Change

## Breaking Change: auto_approve_tools Default Changed to True

As of this release, the default value for `auto_approve_tools` in `BotConfig` has been changed from `False` to `True`.

### Impact

This affects all bot adapters that use the fallback pattern `config or BotConfig(...)`:
- **TelegramBot**
- **SlackBot** 
- **DiscordBot**
- **WhatsAppBot**
- **EmailBot**
- **AgentMailBot**

### Behavior Change

**Before:**
```python
# Tool calls required manual confirmation by default
bot = TelegramBot(token="...", agent=agent)  # auto_approve_tools=False
```

**After:**
```python
# Tool calls are now auto-approved by default
bot = TelegramBot(token="...", agent=agent)  # auto_approve_tools=True
```

### Rationale

Chat bots cannot show CLI approval prompts to users, making manual approval impractical in messaging environments. This change enables bots to work seamlessly out-of-the-box while maintaining safety through:

1. **Safe tool defaults**: Only non-destructive tools (web search, memory, scheduling) are auto-injected
2. **Destructive tool filtering**: Tools like `execute_command` are excluded from auto-injection
3. **Explicit opt-in for risky tools**: Destructive tools require explicit configuration

### Migration

If your bot adapter previously relied on manual tool approval, explicitly set `auto_approve_tools=False`:

```python
# Maintain old behavior (manual approval required)
config = BotConfig(auto_approve_tools=False)
bot = TelegramBot(token="...", agent=agent, config=config)
```

### Affected Packages

- `praisonaiagents.bots.config.BotConfig` (default changed)
- All bot adapters in `praisonai.bots.*` (when using default config)