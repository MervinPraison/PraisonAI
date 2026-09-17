"""Root conftest: environment that must be set before third-party imports.

pytest loads plugins registered through entry points before it loads
``tests/conftest.py``, and something in that chain imports litellm. litellm
reads LITELLM_LOCAL_MODEL_COST_MAP at *its* import and, without it, fetches
model_prices_and_context_window.json from raw.githubusercontent.com -- so the
suite made an outbound request before a single test ran, and stalled or failed
when offline. A rootdir conftest is loaded early enough to win that race.

Anything that merely needs to be set before the tests themselves belongs in
tests/conftest.py instead.
"""

import os

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
