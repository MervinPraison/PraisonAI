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

from praisonaiagents.context import budgeter
from praisonaiagents.context.budgeter import litellm_model_info
from praisonaiagents.eval import tokens as eval_tokens
from praisonaiagents.rag import budget as rag_budget


def _window(info):
    return info.get("max_input_tokens") or info.get("max_tokens")


def test_rag_window_prefers_litellm_data_over_static_table(monkeypatch):
    monkeypatch.setattr(
        rag_budget,
        "_litellm_model_info",
        lambda name: {"max_input_tokens": 999999} if name == "gpt-4o" else None,
    )
    assert rag_budget.get_model_context_window("gpt-4o") == 999999


def test_static_fallback_tables_match_litellm_bundled_data():
    if not budgeter._bundled_model_cost():
        pytest.skip("litellm bundled model data not installed")
    tables = {
        "context.budgeter.MODEL_LIMITS": {
            k: v for k, v in budgeter.MODEL_LIMITS.items() if k != "default"
        },
        "rag.budget.MODEL_CONTEXT_WINDOWS": rag_budget.MODEL_CONTEXT_WINDOWS,
        "eval.tokens.DEFAULT_CONTEXT_LENGTHS": eval_tokens.DEFAULT_CONTEXT_LENGTHS,
    }
    drifted = {}
    for table_name, table in tables.items():
        for model, static_val in table.items():
            info = litellm_model_info(model)
            win = _window(info) if info else None
            if win and int(win) != static_val:
                drifted[f"{table_name}[{model!r}]"] = (static_val, int(win))
    assert not drifted, f"Static fallback table entries drifted from litellm data: {drifted}"


def test_fallback_tables_return_synced_values_when_litellm_is_absent(monkeypatch):
    monkeypatch.setattr(budgeter, "_litellm_model_info", lambda _name: None)
    monkeypatch.setattr(rag_budget, "_litellm_model_info", lambda _name: None)
    monkeypatch.setattr(eval_tokens, "_litellm_model_info", lambda _name: None)

    assert budgeter.resolved_model_limit("gpt-5") == 272000
    assert budgeter.resolved_model_limit("gpt-5-mini") == 272000
    assert budgeter.resolved_model_limit("gpt-5-nano") == 272000
    assert rag_budget.get_model_context_window("gpt-5") == 272000
    assert rag_budget.get_model_context_window("gemini-2.5-pro") == 1048576
    assert rag_budget.get_model_context_window("gemini-2.5-flash") == 1048576
    assert rag_budget.get_model_context_window("deepseek-chat") == 131072
    assert eval_tokens.get_context_length("gpt-5") == 272000
    assert eval_tokens.get_context_length("deepseek-chat") == 131072


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
