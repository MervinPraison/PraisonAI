"""ACP must receive its arguments exactly as typed.

The legacy argparse pass runs over the same argv, and two of its flags collide
with ACP's: ``--model`` would consume the model value before the handler saw
it, and ``--resume`` (which requires a value there) rejects the legal
``--resume --last`` pair outright. These gates pin the pre-parse dispatch that
keeps both intact, and pin the argv shapes the scan must leave to the legacy
parser: an ``acp`` that is an option's value or an ``--auto``/``--init``
payload, ``--``-terminated positionals, help, and arguments argparse would
reject.

Classification is delegated to the legacy parser (``_parse_optional``), so
exact spellings, ``--opt=value``, unambiguous long prefixes and clustered
short options resolve the way the legacy parse would.
"""

import sys

import pytest

from praisonai.cli.legacy.dispatch.argparse_builder import build_parser
from praisonai_code.cli.legacy import praison_ai


def _parser():
    parser, _ = build_parser(False)
    return parser


@pytest.mark.parametrize("argv, expected", [
    (["acp", "--model", "gpt-4o"], ["--model", "gpt-4o"]),
    (["acp", "--resume", "--last"], ["--resume", "--last"]),
    (["acp", "--help"], ["--help"]),
    (["acp"], []),
    (["-v", "acp", "--workspace", "."], ["--workspace", "."]),
    (["-vv", "acp", "--model", "m"], ["--model", "m"]),
    # An option's value is not the verb.
    (["--model", "acp"], None),
    (["-p", "acp"], None),
    (["--prompt=acp"], None),
    # A value ahead of the verb is skipped, not read as the command -- including
    # through an unambiguous abbreviation of the option's name.
    (["--model", "prefix", "acp", "--model", "target"], ["--model", "target"]),
    (["--model", "prefix", "acp", "--resume", "--last"], ["--resume", "--last"]),
    (["--mode", "prefix", "acp", "--resume", "--last"], ["--resume", "--last"]),
    (["--mode", "acp"], None),
    # REMAINDER options swallow the rest, so no verb can follow one.
    (["--auto", "acp"], None),
    (["--ini", "acp"], None),
    # `--` ends option parsing: only the token after it is the command.
    (["--", "acp", "--model", "x"], ["--model", "x"]),
    (["--", "-v", "acp"], None),
    # Help and invalid arguments stay with the legacy parser.
    (["--help", "acp"], None),
    (["--model", "--verbose", "acp"], None),
    (["agents.yaml"], None),
])
def test_acp_tail_follows_the_legacy_parser(argv, expected):
    assert praison_ai._acp_tail(argv, _parser()) == expected


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
