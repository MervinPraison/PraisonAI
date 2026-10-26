# PraisonAI Replay: watch runs live

| Example | What it shows |
|---|---|
| `watch_flow.py` | Click **Run** and watch each step light up on the map; **Play** goes through it again. No API key. |
| `watch_team.py` | The same for two real agents (needs `OPENAI_API_KEY`). |
| `embed_fastapi.py` | Your own app starts a run and shows its progress in an `<iframe>` (`app.mount("/replay", replay_app())`). |

The same from the command line, for a YAML file:

```bash
praisonai replay watch agents.yaml
```

Install: `pip install "praisonai[ui]"`. Keep the page on localhost or behind your app's
login: anyone who can reach it can read the runs, and with a Run button, start one.
