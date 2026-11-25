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
    # Outside a test environment, which is where the scan is allowed to run.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        praison_ai.PraisonAI().parse_args()

    assert exit_info.value.code == 0
    assert seen == [["--resume", "--last"]]


def test_pytest_argv_does_not_dispatch_acp(monkeypatch):
    """The scan reads the real argv, so a test runner's `-k acp` must not run it."""
    import praisonai.cli.features.acp as acp_mod

    calls = []
    monkeypatch.setattr(
        acp_mod, "run_acp_command", lambda args: calls.append(list(args)) or 0
    )
    monkeypatch.setattr(sys, "argv", ["/venv/bin/pytest", "-k", "acp"])

    args, _unknown = praison_ai.PraisonAI().parse_args()

    assert calls == []
    assert args.command is None


def _legacy_wrapper(monkeypatch, builder):
    """Make the bridge return a wrapper that predates the build_parser split."""
    import praisonai_code._wrapper_bridge as bridge

    real = bridge.import_wrapper_module

    def fake(name):
        if name.endswith("argparse_builder"):
            return builder
        return real(name)

    monkeypatch.setattr(bridge, "import_wrapper_module", fake)


def _old_wrapper_builder():
    """A wrapper module with only the pre-split API, backed by the real builder."""
    import types

    from praisonai.cli.legacy.dispatch import argparse_builder as real

    return types.SimpleNamespace(build_argument_parser=real.build_argument_parser)


def test_an_older_wrapper_still_runs_non_acp_commands(monkeypatch):
    """Only `acp` needs the pre-parse look; every other command must not break."""
    _legacy_wrapper(monkeypatch, _old_wrapper_builder())
    monkeypatch.setattr(sys, "argv", ["praisonai", "agents.yaml"])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    args, _unknown = praison_ai.PraisonAI().parse_args()

    assert args.command == "agents.yaml"


def test_an_older_wrapper_still_routes_acp(monkeypatch):
    """The post-parse route survives for a wrapper without build_parser."""
    import praisonai.cli.features.acp as acp_mod

    seen = []
    monkeypatch.setattr(
        acp_mod, "run_acp_command", lambda args: seen.append(list(args)) or 0
    )
    _legacy_wrapper(monkeypatch, _old_wrapper_builder())
    monkeypatch.setattr(sys, "argv", ["praisonai", "acp", "--workspace", "."])
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        praison_ai.PraisonAI().parse_args()

    assert exit_info.value.code == 0
    assert seen == [["--workspace", "."]]
