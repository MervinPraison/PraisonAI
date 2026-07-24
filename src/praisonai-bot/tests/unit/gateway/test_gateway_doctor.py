"""Tests for gateway pre-flight channel credential validation (#2426).

Covers:
- ``BotOS.probe_all()`` aggregate
- CLI helpers ``_probe_channels`` / ``_render_probe_results`` / ``_resolve_env_token``
- ``gateway doctor`` and ``gateway channels --probe`` exit codes
"""

import asyncio

import pytest

from praisonai_bot.bots import Bot, BotOS
from praisonaiagents.bots import ProbeResult


def _patch_probe(monkeypatch):
    async def fake_probe(self):
        if self._platform == "slack":
            return ProbeResult(ok=False, platform="slack", error="invalid_auth")
        return ProbeResult(ok=True, platform=self._platform, bot_username="support_bot")

    monkeypatch.setattr(Bot, "probe", fake_probe)


def test_probe_all_aggregates_results(monkeypatch):
    _patch_probe(monkeypatch)
    botos = BotOS(
        bots=[Bot("telegram", token="x"), Bot("slack", token="y")],
        enable_supervision=False,
    )
    res = asyncio.run(botos.probe_all())
    assert set(res) == {"telegram", "slack"}
    assert res["telegram"].ok is True
    assert res["telegram"].bot_username == "support_bot"
    assert res["slack"].ok is False
    assert "invalid_auth" in res["slack"].error


def test_probe_all_empty():
    botos = BotOS(bots=[], enable_supervision=False)
    assert asyncio.run(botos.probe_all()) == {}


def test_resolve_env_token(monkeypatch):
    from praisonai_bot.cli.commands.gateway import _resolve_env_token

    monkeypatch.setenv("MY_TOKEN", "abc123")
    assert _resolve_env_token("${MY_TOKEN}") == "abc123"
    assert _resolve_env_token("literal") == "literal"
    assert _resolve_env_token("${MISSING_TOKEN}") == ""


def test_probe_channels_and_render(monkeypatch, capsys):
    _patch_probe(monkeypatch)
    from praisonai_bot.cli.commands.gateway import _probe_channels, _render_probe_results

    channels = {
        "telegram": {"platform": "telegram", "token": "t"},
        "slack": {"platform": "slack", "token": "s"},
    }
    results = asyncio.run(_probe_channels(channels))
    all_ok = _render_probe_results(results)
    out = capsys.readouterr().out
    assert all_ok is False
    assert "telegram" in out and "✓" in out
    assert "@support_bot" in out
    assert "slack" in out and "✗" in out and "invalid_auth" in out


def test_probe_channels_loads_env_file(monkeypatch):
    """_probe_channels must load ~/.praisonai/.env before resolving ${VAR}
    tokens so doctor / channels --probe match runtime token resolution (#2426)."""
    import praisonai.cli.features.gateway as gw_feature

    loaded = {"called": False}

    def _fake_load_env():
        loaded["called"] = True
        import os
        os.environ.setdefault("ENVFILE_TOKEN", "from-env-file")
        return {}

    monkeypatch.setattr(gw_feature, "_load_praisonai_env_file", _fake_load_env)

    captured = {}

    async def capture_probe(self):
        captured["token"] = self._explicit_token
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", capture_probe)

    from praisonai_bot.cli.commands.gateway import _probe_channels

    channels = {"telegram": {"platform": "telegram", "token": "${ENVFILE_TOKEN}"}}
    asyncio.run(_probe_channels(channels))

    assert loaded["called"] is True
    assert captured["token"] == "from-env-file"


def test_doctor_command_exits_nonzero_on_failure(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")
    _patch_probe(monkeypatch)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  telegram:\n    platform: telegram\n    token: t\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["doctor", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "telegram" in result.stdout
    assert "slack" in result.stdout


def test_channels_probe_flag_passes_when_all_ok(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    async def all_ok_probe(self):
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", all_ok_probe)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  telegram:\n    platform: telegram\n    token: t\n")

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["channels", "--probe", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "telegram" in result.stdout


def test_start_preflight_fails_fast_on_bad_token(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")
    _patch_probe(monkeypatch)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    import praisonai.cli.features.gateway as gw_feature

    def _fail_if_called(self, *a, **k):  # pragma: no cover - must not run
        raise AssertionError("handler.start() must not run on preflight failure")

    monkeypatch.setattr(gw_feature.GatewayHandler, "start", _fail_if_called)

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["start", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "slack" in result.stdout


def test_is_ssl_error_classification():
    """SSL certificate-verify failures must be distinguished from bad tokens (#2845)."""
    from praisonai_bot.cli.commands.gateway import _is_ssl_error

    ssl_err = ProbeResult(
        ok=False,
        platform="telegram",
        error=(
            "Cannot connect to host api.telegram.org:443 ssl:True "
            "[SSLCertVerificationError: (1, '[SSL: CERTIFICATE_VERIFY_FAILED] "
            "certificate verify failed: self-signed certificate in certificate chain')]"
        ),
    )
    assert _is_ssl_error(ssl_err) is True

    token_err = ProbeResult(ok=False, platform="slack", error="invalid_auth")
    assert _is_ssl_error(token_err) is False

    ok_result = ProbeResult(ok=True, platform="discord", bot_username="bot")
    assert _is_ssl_error(ok_result) is False


def test_is_ssl_error_ignores_handshake_failures():
    """Non cert-verify TLS handshake errors must NOT soft-fail — runtime fails too (#2845)."""
    from praisonai_bot.cli.commands.gateway import _is_ssl_error

    for err in (
        "[SSL: WRONG_VERSION_NUMBER] wrong version number",
        "[SSL: NO_SHARED_CIPHER] no shared cipher",
        "[SSL: HANDSHAKE_FAILURE] handshake failure",
    ):
        result = ProbeResult(ok=False, platform="telegram", error=err)
        assert _is_ssl_error(result) is False, err


def test_render_ssl_error_mentions_ssl_not_credentials(capsys):
    """Render output for an SSL failure must point at SSL/proxy, not bad token (#2845)."""
    from praisonai_bot.cli.commands.gateway import _render_probe_results

    results = {
        "telegram": ProbeResult(
            ok=False,
            platform="telegram",
            error="[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        ),
    }
    all_ok = _render_probe_results(results)
    out = capsys.readouterr().out
    assert all_ok is False
    assert "SSL certificate verify failed" in out
    assert "--no-preflight" in out


def test_apply_probe_ca_bundle_honors_env(monkeypatch, tmp_path):
    """Custom CA bundle env vars must be propagated to the probe SSL stack (#2845)."""
    import os
    from praisonai_bot.cli.commands.gateway import _apply_probe_ca_bundle

    ca = tmp_path / "corp-ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("PRAISONAI_SSL_CA_BUNDLE", str(ca))

    _apply_probe_ca_bundle()

    assert os.environ["SSL_CERT_FILE"] == str(ca)
    assert os.environ["REQUESTS_CA_BUNDLE"] == str(ca)


def test_apply_probe_ca_bundle_prefers_praisonai_override(monkeypatch, tmp_path):
    """PRAISONAI_SSL_CA_BUNDLE must win even when SSL_CERT_FILE is already set (#2845)."""
    import os
    from praisonai_bot.cli.commands.gateway import _apply_probe_ca_bundle

    corp_ca = tmp_path / "corp-ca.pem"
    corp_ca.write_text("-----BEGIN CERTIFICATE-----\n")
    system_ca = tmp_path / "system-ca.pem"
    system_ca.write_text("-----BEGIN CERTIFICATE-----\n")

    monkeypatch.setenv("SSL_CERT_FILE", str(system_ca))
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("PRAISONAI_SSL_CA_BUNDLE", str(corp_ca))

    _apply_probe_ca_bundle()

    assert os.environ["SSL_CERT_FILE"] == str(corp_ca)
    assert os.environ["REQUESTS_CA_BUNDLE"] == str(corp_ca)


def test_apply_probe_ca_bundle_warns_on_missing_path(monkeypatch, tmp_path, capsys):
    """A configured-but-missing CA bundle must warn, not silently no-op (#2845)."""
    import os
    from praisonai_bot.cli.commands.gateway import _apply_probe_ca_bundle

    missing = tmp_path / "does-not-exist.pem"

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("PRAISONAI_SSL_CA_BUNDLE", str(missing))

    _apply_probe_ca_bundle()

    out = capsys.readouterr().out
    assert "does not exist" in out
    assert "SSL_CERT_FILE" not in os.environ


def test_start_preflight_soft_fails_on_ssl_only(monkeypatch, tmp_path):
    """SSL-only preflight failures must warn but still start (#2845)."""
    typer_testing = pytest.importorskip("typer.testing")

    async def ssl_probe(self):
        return ProbeResult(
            ok=False,
            platform=self._platform,
            error="[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        )

    monkeypatch.setattr(Bot, "probe", ssl_probe)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  telegram:\n    platform: telegram\n    token: t\n")

    import praisonai.cli.features.gateway as gw_feature

    started = {}

    def _record_start(self, *a, **k):
        started["called"] = True

    monkeypatch.setattr(gw_feature.GatewayHandler, "start", _record_start)

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["start", "--config", str(cfg)])
    assert result.exit_code == 0
    assert started.get("called") is True
    assert "SSL" in result.stdout


def test_start_preflight_still_aborts_when_token_and_ssl_fail(monkeypatch, tmp_path):
    """A real bad-token failure must still abort even if another channel is SSL-only (#2845)."""
    typer_testing = pytest.importorskip("typer.testing")

    async def mixed_probe(self):
        if self._platform == "slack":
            return ProbeResult(ok=False, platform="slack", error="invalid_auth")
        return ProbeResult(
            ok=False,
            platform=self._platform,
            error="[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        )

    monkeypatch.setattr(Bot, "probe", mixed_probe)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  telegram:\n    platform: telegram\n    token: t\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    import praisonai.cli.features.gateway as gw_feature

    def _fail_if_called(self, *a, **k):  # pragma: no cover - must not run
        raise AssertionError("handler.start() must not run when a token fails")

    monkeypatch.setattr(gw_feature.GatewayHandler, "start", _fail_if_called)

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["start", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "slack" in result.stdout


def test_start_no_preflight_skips_probe(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    async def _must_not_probe(self):  # pragma: no cover - must not run
        raise AssertionError("probe must not run with --no-preflight")

    monkeypatch.setattr(Bot, "probe", _must_not_probe)

    import praisonai.cli.features.gateway as gw_feature

    started = {}

    def _record_start(self, *a, **k):
        started["called"] = True

    monkeypatch.setattr(gw_feature.GatewayHandler, "start", _record_start)

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["start", "--config", str(cfg), "--no-preflight"])
    assert result.exit_code == 0
    assert started.get("called") is True


def test_doctor_json_single_document_with_turn(monkeypatch, tmp_path):
    """--json with --turn must emit one parseable document (#gateway-readiness)."""
    typer_testing = pytest.importorskip("typer.testing")
    import json

    async def all_ok_probe(self):
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", all_ok_probe)
    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._check_gateway_secret_strength",
        lambda _cfg: None,
    )

    async def fake_turn(config_path, channel_name, prompt):
        return True, "turn-ok"

    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._run_gateway_turn_test",
        fake_turn,
    )

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n    token: s\n")

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(
        app,
        ["doctor", "--config", str(cfg), "--json", "--channel", "slack", "--turn", "hi"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip())
    assert "probes" in payload
    assert payload["turn"]["ok"] is True
    assert payload["turn"]["response"] == "turn-ok"


def test_doctor_turn_runs_when_other_channel_fails(monkeypatch, tmp_path):
    """--channel slack --turn runs when slack ok even if telegram fails."""
    typer_testing = pytest.importorskip("typer.testing")

    async def mixed_probe(self):
        if self._platform == "slack":
            return ProbeResult(ok=True, platform="slack", bot_username="slackbot")
        return ProbeResult(ok=False, platform=self._platform, error="bad")

    monkeypatch.setattr(Bot, "probe", mixed_probe)

    async def fake_turn(config_path, channel_name, prompt):
        return True, "slack-turn"

    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._run_gateway_turn_test",
        fake_turn,
    )

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(
        "channels:\n"
        "  telegram:\n    platform: telegram\n    token: t\n"
        "  slack:\n    platform: slack\n    token: s\n"
    )

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(
        app,
        ["doctor", "--config", str(cfg), "--channel", "slack", "--turn", "hi"],
    )
    assert result.exit_code == 1  # telegram still failed overall
    assert "Turn test (slack): OK" in result.stdout
    assert "slack-turn" in result.stdout


def test_gateway_test_command(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    async def all_ok_probe(self):
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", all_ok_probe)

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n    token: s\n")

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["test", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "shell wiring" in result.stdout
    assert "slack" in result.stdout


def test_gateway_test_check_runtime_json(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    async def all_ok_probe(self):
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", all_ok_probe)
    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._check_gateway_secret_strength",
        lambda _cfg: None,
    )
    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._check_runtime",
        lambda _cfg: type(
            "R",
            (),
            {
                "ok": True,
                "to_dict": lambda self: {"ok": True, "health": {"ok": True}},
            },
        )(),
    )

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n    token: s\n")

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(
        app, ["test", "--config", str(cfg), "--check-runtime", "--json"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.stdout)
    assert payload["runtime"]["ok"] is True


def test_gateway_test_check_inbound_fails(monkeypatch, tmp_path):
    typer_testing = pytest.importorskip("typer.testing")

    async def all_ok_probe(self):
        return ProbeResult(ok=True, platform=self._platform, bot_username="bot")

    monkeypatch.setattr(Bot, "probe", all_ok_probe)
    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._check_gateway_secret_strength",
        lambda _cfg: None,
    )
    monkeypatch.setattr(
        "praisonai_bot.cli.commands.gateway._check_inbound",
        lambda *a, **k: type(
            "I",
            (),
            {
                "ok": False,
                "proves": "inbound_delivery",
                "mentions_in_window": 0,
                "hint": "No inbound",
                "to_dict": lambda self: {
                    "ok": False,
                    "proves": "inbound_delivery",
                    "mentions_in_window": 0,
                },
            },
        )(),
    )

    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("channels:\n  slack:\n    platform: slack\n    token: s\n")

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(
        app, ["test", "--config", str(cfg), "--check-inbound", "--since", "5m"]
    )
    assert result.exit_code == 1
    assert "inbound" in result.stdout


def test_gateway_sessions_list_cli(tmp_path, monkeypatch):
    typer_testing = pytest.importorskip("typer.testing")
    import json

    monkeypatch.setattr(
        "praisonai_bot.gateway.preflight.list_gateway_sessions",
        lambda **kwargs: [
            {"session_id": "bot_slack_U1", "message_count": 2, "user_id": "U1"}
        ],
    )

    from praisonai_bot.cli.commands.gateway import app

    runner = typer_testing.CliRunner()
    result = runner.invoke(app, ["sessions", "list", "--platform", "slack"])
    assert result.exit_code == 0
    assert "bot_slack_U1" in result.stdout
    assert "--check-inbound" in result.stdout

