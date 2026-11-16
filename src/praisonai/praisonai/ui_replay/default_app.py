"""PraisonAI Replay — aiui app that opens straight to the replay page.

Loaded by ``praisonai replay view`` -> ``aiui run default_app.py``. The replay
page reads traces from ``PRAISONAI_TRACES_DIR`` (set by the CLI), else
``$PRAISON_HOME/traces``, else ``~/.praison/traces``.

Requires: pip install "praisonai[ui]"

Run:
    praisonai replay view            # recent runs
    praisonai replay view RUN_ID     # one run
    praisonai replay view agents.yaml --live
"""

from praisonai.integration.host_app import UIPreset, build_ui_app

app = build_ui_app(UIPreset(
    title="PraisonAI Replay",
    pages=["replay"],
    sidebar=False,
    theme={"preset": "blue", "dark_mode": False, "radius": "lg"},
    welcome="PraisonAI Replay: pick a run to see what happened.",
))
