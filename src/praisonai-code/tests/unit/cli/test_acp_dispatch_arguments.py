"""ACP must receive its arguments as typed when the verb comes first.

The legacy argparse pass runs over the same argv, and two of its flags collide
with ACP's: ``--model`` would consume the model value before the handler saw
it, and ``--resume`` (which requires a value there) rejects the legal
``--resume --last`` pair outright. The documented invocation is verb-first
(``praisonai acp ...``), so that shape is dispatched before the parse. These
gates pin the route, and pin that nothing else changes: a test runner's own
``-k acp`` must never dispatch, and other argument shapes keep the legacy
parse and its post-parse fallback.
"""

import sys

import pytest

from praisonai_code.cli.legacy import praison_ai

# The handler lives in the wrapper; without it these gates would error on the
# import in _stub_handler rather than skip, so stand down when it is absent.
pytest.importorskip("praisonai.cli.features.acp")


def _stub_handler(monkeypatch):
    import praisonai.cli.features.acp as acp_mod

    seen = []
    monkeypatch.setattr(
        acp_mod, "run_acp_command", lambda args: seen.append(list(args)) or 0
    )
    return seen


@pytest.mark.parametrize("argv, expected", [
    (["acp", "--model", "gpt-4o"], ["--model", "gpt-4o"]),
    (["acp", "--resume", "--last"], ["--resume", "--last"]),
    (["acp", "--help"], ["--help"]),
    (["acp"], []),
])
def test_verb_first_acp_reaches_the_handler_with_its_arguments(
    monkeypatch, argv, expected
):
    seen = _stub_handler(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["praisonai"] + argv)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        praison_ai.PraisonAI().parse_args()

    assert exit_info.value.code == 0
    assert seen == [expected]


def test_pytest_argv_does_not_dispatch_acp(monkeypatch):
    """The route reads the real argv, so a test runner's `-k acp` must not run it."""
    seen = _stub_handler(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["/venv/bin/pytest", "-k", "acp"])

    args, _unknown = praison_ai.PraisonAI().parse_args()

    assert seen == []
    assert args.command is None


def test_other_shapes_keep_the_legacy_parse_and_forward_its_unknown_args(monkeypatch):
    """`-v acp ...` parses first; ACP receives what the parser left unconsumed."""
    seen = _stub_handler(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["praisonai", "-v", "acp", "--workspace", "."])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        praison_ai.PraisonAI().parse_args()

    assert exit_info.value.code == 0
    assert seen == [["--workspace", "."]]


def test_non_acp_argv_is_untouched(monkeypatch):
    seen = _stub_handler(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["praisonai", "agents.yaml"])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    args, _unknown = praison_ai.PraisonAI().parse_args()

    assert seen == []
    assert args.command == "agents.yaml"
