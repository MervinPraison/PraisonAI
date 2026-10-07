"""CLI tests for praisonai decisions (mocked HTTP)."""

from __future__ import annotations

import json
from unittest import mock

from typer.testing import CliRunner


def test_decisions_run_json():
    from praisonai_code.cli.commands.decisions import app

    fake = mock.Mock()
    fake.model = "nimble"
    fake.answers = {"team": {"type": "choice", "choice": "billing"}}
    fake.raw = {"model": "nimble", "answers": fake.answers}

    runner = CliRunner()
    with mock.patch("praisonaiagents.decisions.system_one", return_value=fake):
        result = runner.invoke(app, ["run", "refund please", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["answers"]["team"]["choice"] == "billing"


def test_decisions_triage_rejects_non_choice_route_question():
    from praisonai_code.cli.commands.decisions import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["triage", "charged twice", "--route-question", "refund", "--skip-chat"]
    )
    assert result.exit_code != 0
    assert "choice question" in result.output
