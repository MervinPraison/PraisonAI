"""X-03: RAG and eval context windows come from the same data as the budgeter.

rag.get_model_context_window used only its static table, which had drifted
from litellm's model data (G-08 found 49 OpenAI models off). eval's
get_context_length read the same data but imported litellm to do it (~3 s).
Both now ask context.budgeter.litellm_model_info first (litellm's bundled JSON,
no import) and keep their static tables as the fallback.
"""

import subprocess
import sys

import pytest

from praisonaiagents.context.budgeter import litellm_model_info
from praisonaiagents.rag import budget as rag_budget


def _window(info):
    return info.get("max_input_tokens") or info.get("max_tokens")


def test_rag_window_follows_litellm_data_where_the_static_table_drifted():
    drifted = {}
    for name, static in rag_budget.MODEL_CONTEXT_WINDOWS.items():
        info = litellm_model_info(name)
        if info and _window(info) and _window(info) != static:
            drifted[name] = int(_window(info))
    if not drifted:
        pytest.skip("litellm data not installed, or no drift to check")
    got = {name: rag_budget.get_model_context_window(name) for name in drifted}
    assert got == drifted


def test_eval_context_length_does_not_import_litellm():
    code = (
        "import sys\n"
        "from praisonaiagents.eval.tokens import get_context_length\n"
        "n = get_context_length('gpt-4o')\n"
        "print(n, 'litellm' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert int(out[0]) > 0
    assert out[1] == "False"
