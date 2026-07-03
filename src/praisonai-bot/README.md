# praisonai-bot

Bots, gateway, and channel CLI for PraisonAI.

```bash
pip install praisonai-bot[gateway,bot]
praisonai-bot gateway start --config gateway.yaml
praisonai-bot bot start --config bot.yaml
```

Protocols live in `praisonaiagents`; this package holds platform adapters and the WebSocket gateway server.
