"""ACP must receive its arguments exactly as typed.

The legacy argparse pass runs over the same argv, and two of its flags collide
with ACP's: ``--model`` would consume the model value before the handler saw
it, and ``--resume`` (which requires a value there) rejects the legal
``--resume --last`` pair outright. These gates pin the pre-parse dispatch that
keeps both intact, and pin that an ``acp`` which is an option's *value* — or a
``--auto``/``--init`` payload — does not start a server.

The arity comes from the legacy parser itself, so the scan cannot drift from
the flag list the way a hand-kept copy would.
"""

import sys

import pytest

from praisonai.cli.legacy.dispatch.argparse_builder import build_parser, option_arity
from praisonai_code.cli.legacy import praison_ai


def _arity():
    parser, _ = build_parser(False)
    return option_arity(parser)


@pytest.mark.parametrize("argv, expected", [
    (["acp", "--model", "gpt-4o"], ["--model", "gpt-4o"]),
    (["acp", "--resume", "--last"], ["--resume", "--last"]),
    (["-v", "acp", "--workspace", "."], ["--workspace", "."]),
    # An option's value is not the verb.
    (["--model", "acp"], None),
    (["-p", "acp"], None),
    (["--prompt=acp"], None),
    # A value ahead of the verb is skipped, not read as the command.
    (["--model", "prefix", "acp", "--model", "target"], ["--model", "target"]),
    (["--model", "prefix", "acp", "--resume", "--last"], ["--resume", "--last"]),
    # REMAINDER options swallow the rest, so no verb can follow one.
    (["--auto", "acp"], None),
    (["agents.yaml"], None),
])
def test_acp_tail_uses_the_legacy_parser_arity(argv, expected):
    assert praison_ai._acp_tail(argv, _arity()) == expected


def test_resume_last_reaches_the_handler(monkeypatch):
    """`acp --resume --last` exited 2 in argparse before the pre-parse dispatch."""
    import praisonai.cli.features.acp as acp_mod

    seen = []
    monkeypatch.setattr(
        acp_mod, "run_acp_command", lambda args: seen.append(list(args)) or 0
    )
    monkeypatch.setattr(sys, "argv", ["praisonai", "acp", "--resume", "--last"])

    with pytest.raises(SystemExit) as exit_info:
        praison_ai.PraisonAI().parse_args()

    assert exit_info.value.code == 0
    assert seen == [["--resume", "--last"]]
