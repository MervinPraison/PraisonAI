"""Tests for the published gateway.yaml / bot.yaml JSON Schema (issue #5414).

Brings the gateway/bot config surface to parity with ``agents.yaml``:
- ``gateway_config_json_schema()`` emits a draft-07 schema from the canonical
  Pydantic ``GatewayConfigSchema``.
- The committed ``gateway.schema.json`` artefact matches the model.
- ``praisonai gateway schema`` prints the schema / writes it to a file.
- Scaffolded ``gateway.yaml``/``bot.yaml`` start with the
  ``# yaml-language-server`` header (and still parse with ``yaml.safe_load``).
"""

import json
from pathlib import Path

import pytest
import yaml

from praisonai_bot.bots._config_schema import (
    GATEWAY_SCHEMA_HEADER,
    GATEWAY_SCHEMA_URL,
    gateway_config_json_schema,
)


def test_gateway_schema_derived_from_pydantic_model():
    schema = gateway_config_json_schema()
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["$id"] == GATEWAY_SCHEMA_URL
    props = schema["properties"]
    for key in ("gateway", "agents", "channels", "routing", "schedules"):
        assert key in props, f"expected '{key}' in gateway schema properties"


def test_committed_artefact_matches_model():
    artefact = (
        Path(__file__).resolve().parents[3]
        / "praisonai_bot"
        / "bots"
        / "gateway.schema.json"
    )
    assert artefact.exists(), "gateway.schema.json artefact must be committed"
    committed = json.loads(artefact.read_text(encoding="utf-8"))
    assert committed == gateway_config_json_schema(), (
        "gateway.schema.json is stale; regenerate via "
        "`praisonai gateway schema -o "
        "src/praisonai-bot/praisonai_bot/bots/gateway.schema.json`"
    )


def test_schema_header_points_at_published_url():
    assert GATEWAY_SCHEMA_HEADER.startswith("# yaml-language-server: $schema=")
    assert GATEWAY_SCHEMA_URL in GATEWAY_SCHEMA_HEADER
    assert GATEWAY_SCHEMA_HEADER.endswith("\n")


def test_shipped_sample_gateway_yaml_has_header():
    sample = (
        Path(__file__).resolve().parents[3] / "gateway.yaml"
    )
    if not sample.exists():
        pytest.skip("sample gateway.yaml not present")
    first_line = sample.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("# yaml-language-server: $schema=")
    # Leading comment is ignored by safe_load -> execution unaffected.
    loaded = yaml.safe_load(sample.read_text(encoding="utf-8"))
    assert "gateway" in loaded


def test_generated_configs_scaffold_header():
    from praisonai_bot.cli.features.onboard import (
        _generate_bot_yaml,
        _generate_bot_yaml_multi_channel,
    )

    single = _generate_bot_yaml(["telegram"])
    assert single.startswith("# yaml-language-server: $schema=")
    assert yaml.safe_load(single)["gateway"]["port"] == 8765

    multi = _generate_bot_yaml_multi_channel(
        {
            "telegram": {
                "platform": "telegram",
                "role": "assistant",
                "env_var": "TELEGRAM_BOT_TOKEN",
                "token": "",
                "info": {"allowed_users_env": "TELEGRAM_ALLOWED_USERS"},
                "config": {},
            }
        }
    )
    assert multi.startswith("# yaml-language-server: $schema=")
    assert "gateway" in yaml.safe_load(multi)


def test_gateway_schema_cli_prints_and_writes(tmp_path):
    from typer.testing import CliRunner

    from praisonai_bot.cli.commands.gateway import app

    runner = CliRunner()
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert '"$schema"' in result.output

    out = tmp_path / "gateway.schema.json"
    result2 = runner.invoke(app, ["schema", "-o", str(out)])
    assert result2.exit_code == 0, result2.output
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8")) == gateway_config_json_schema()
