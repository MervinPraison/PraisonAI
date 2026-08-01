"""Tests for compose, helm, starters, and infra path resolution."""
from pathlib import Path

import pytest

import praisonai_deploy
from praisonai_deploy._infra import (
    AGENTS_API_CHART,
    GATEWAY_CHART,
    bot_infra_root,
    deploy_infra_root,
    iter_helm_chart_dirs,
    resolve_compose_stack_dir,
    resolve_helm_chart_dir,
    resolve_starters_root,
)

PKG_ROOT = Path(praisonai_deploy.__file__).resolve().parent
DEPLOY_INFRA = deploy_infra_root()
BOT_INFRA = bot_infra_root()


def test_deploy_infra_root_exists():
    assert DEPLOY_INFRA.is_dir()
    assert (DEPLOY_INFRA / "compose" / "agents-stack" / "docker-compose.yml").is_file()


def test_bot_infra_gateway_chart_exists():
    assert (BOT_INFRA / "helm" / GATEWAY_CHART / "Chart.yaml").is_file()


def test_resolve_stack_dir_from_package():
    stack = resolve_compose_stack_dir()
    assert stack.name == "agents-stack"


def test_prepare_compose_project_writes_api_server(tmp_path):
    from praisonai_deploy.compose import prepare_compose_project

    agents = tmp_path / "agents.yaml"
    agents.write_text(
        "agents:\n  - name: a\n    role: r\n    goal: g\n    backstory: b\n"
        "deploy:\n  type: api\n  api:\n    port: 8005\n",
        encoding="utf-8",
    )
    project = prepare_compose_project(str(agents), project_dir=tmp_path)
    assert (project / "api_server.py").is_file()
    assert (project / "agents.yaml").is_file()


def test_resolve_gateway_chart_dir():
    path = resolve_helm_chart_dir(GATEWAY_CHART)
    assert path.name == GATEWAY_CHART
    assert path.parent.name == "helm"


def test_resolve_agents_api_chart_dir():
    path = resolve_helm_chart_dir(AGENTS_API_CHART)
    assert path.name == AGENTS_API_CHART


def test_iter_helm_chart_dirs_includes_both():
    names = {p.name for p in iter_helm_chart_dirs()}
    assert GATEWAY_CHART in names
    assert AGENTS_API_CHART in names


def test_list_starter_templates():
    from praisonai_deploy.starters import list_templates

    templates = list_templates()
    names = {t["name"] for t in templates}
    assert "docker-api" in names
    assert "fly" in names


def test_create_from_template(tmp_path):
    from praisonai_deploy.starters import create_from_template

    result = create_from_template("docker-api", str(tmp_path / "proj"))
    assert result.success
    assert (tmp_path / "proj" / "agents.yaml").is_file()


def test_legacy_deploy_root_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    stack = legacy / "deploy" / "compose" / "agents-stack"
    stack.mkdir(parents=True)
    (stack / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")

    missing = tmp_path / "no-infra"
    monkeypatch.setattr(
        "praisonai_deploy._infra.deploy_infra_root",
        lambda: missing / "infra",
    )

    resolved = resolve_compose_stack_dir(cwd=legacy)
    assert resolved == stack.resolve()


@pytest.mark.parametrize("provider_name,cls_name", [
    ("fly", "FlyProvider"),
    ("railway", "RailwayProvider"),
    ("render", "RenderProvider"),
])
def test_optional_providers_registered(provider_name, cls_name):
    from praisonai_deploy.providers._registry import CloudProviderRegistry

    registry = CloudProviderRegistry.default()
    cls = registry.resolve(provider_name)
    assert cls.__name__ == cls_name


def test_resolve_starters_root():
    root = resolve_starters_root()
    assert (root / "templates.yaml").is_file()


def test_resolve_chart_dir_gateway_alias():
    from praisonai_deploy.helm import resolve_chart_dir

    path = resolve_chart_dir("gateway")
    assert path.name == GATEWAY_CHART
    assert "praisonai-bot" in str(path)


def test_resolve_chart_dir_agents_api_alias():
    from praisonai_deploy.helm import resolve_chart_dir

    path = resolve_chart_dir("agents-api")
    assert path.name == AGENTS_API_CHART
    assert "praisonai-deploy" in str(path)


def test_legacy_helm_chart_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    chart = legacy / "deploy" / "helm" / GATEWAY_CHART
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: praisonai-gateway\nversion: 0.0.1\n", encoding="utf-8")

    missing = tmp_path / "no-infra"
    monkeypatch.setattr("praisonai_deploy._infra.deploy_infra_root", lambda: missing / "infra")
    monkeypatch.setattr("praisonai_deploy._infra.bot_infra_root", lambda: missing / "bot-infra")

    resolved = resolve_helm_chart_dir(GATEWAY_CHART, cwd=legacy)
    assert resolved == chart.resolve()


def test_legacy_starters_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    starters = legacy / "deploy" / "starters"
    starters.mkdir(parents=True)
    (starters / "templates.yaml").write_text("templates: []\n", encoding="utf-8")

    missing = tmp_path / "no-infra"
    monkeypatch.setattr("praisonai_deploy._infra.deploy_infra_root", lambda: missing / "infra")
    monkeypatch.delenv("PRAISONAI_INFRA_ROOT", raising=False)
    monkeypatch.delenv("PRAISONAI_STARTERS_ROOT", raising=False)

    resolved = resolve_starters_root(cwd=legacy)
    assert resolved == starters.resolve()


def test_invalid_praisonai_helm_root_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PRAISONAI_HELM_ROOT", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError, match="PRAISONAI_HELM_ROOT"):
        resolve_helm_chart_dir(GATEWAY_CHART)


def test_compose_stack_from_praisonai_compose_stack_env(monkeypatch, tmp_path):
    stack = tmp_path / "custom-stack"
    stack.mkdir()
    (stack / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setenv("PRAISONAI_COMPOSE_STACK", str(stack))
    assert resolve_compose_stack_dir() == stack.resolve()


def test_helm_upgrade_install_builds_cmd(monkeypatch):
    from praisonai_deploy.helm import helm_upgrade_install

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("praisonai_deploy.helm.subprocess.run", fake_run)
    result = helm_upgrade_install("gateway", release="gw", install=True)
    assert result.success
    assert "helm" in captured["cmd"]
    assert "auth.existingSecret=praisonai-gateway-auth" in captured["cmd"]


def test_prepare_compose_project_uses_stack_dir_env_example(tmp_path):
    from praisonai_deploy.compose import prepare_compose_project

    custom_stack = tmp_path / "custom-stack"
    custom_stack.mkdir()
    (custom_stack / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (custom_stack / ".env.example").write_text("API_PORT=9001\n", encoding="utf-8")

    agents = tmp_path / "agents.yaml"
    agents.write_text(
        "agents:\n  - name: a\n    role: r\n    goal: g\n    backstory: b\n"
        "deploy:\n  type: api\n",
        encoding="utf-8",
    )
    project = prepare_compose_project(str(agents), project_dir=tmp_path / "work", stack_dir=str(custom_stack))
    env_file = project / ".env"
    assert env_file.is_file()
    assert "9001" in env_file.read_text(encoding="utf-8")


def test_create_from_template_unknown_template():
    from praisonai_deploy.starters import create_from_template

    result = create_from_template("does-not-exist", "/tmp/x")
    assert not result.success
    assert "Unknown template" in result.message


def test_compose_env_example_has_no_default_postgres_password():
    """Security: shipped .env.example must not carry a repo-known DB password."""
    stack = resolve_compose_stack_dir()
    env_example = (stack / ".env.example").read_text(encoding="utf-8")
    for line in env_example.splitlines():
        stripped = line.strip()
        if stripped.startswith("POSTGRES_PASSWORD="):
            value = stripped.split("=", 1)[1].strip()
            assert value == "", f"POSTGRES_PASSWORD must be empty, got {value!r}"


def test_compose_postgres_binds_loopback_by_default():
    """Security: Postgres must not be published on all interfaces by default."""
    stack = resolve_compose_stack_dir()
    compose = (stack / "docker-compose.yml").read_text(encoding="utf-8")
    assert "POSTGRES_BIND:-127.0.0.1" in compose


def test_compose_requires_explicit_postgres_password():
    """Security: no default password baked into the compose file."""
    stack = resolve_compose_stack_dir()
    compose = (stack / "docker-compose.yml").read_text(encoding="utf-8")
    default_pattern = "POSTGRES_PASSWORD:-" + "praisonai"
    assert default_pattern not in compose
    assert "POSTGRES_PASSWORD:?" in compose


def test_prepare_compose_project_generates_postgres_password(tmp_path):
    from praisonai_deploy.compose import prepare_compose_project

    agents = tmp_path / "agents.yaml"
    agents.write_text(
        "agents:\n  - name: a\n    role: r\n    goal: g\n    backstory: b\n"
        "deploy:\n  type: api\n",
        encoding="utf-8",
    )
    project = prepare_compose_project(str(agents), project_dir=tmp_path / "work")
    env_text = (project / ".env").read_text(encoding="utf-8")
    pw_lines = [
        line for line in env_text.splitlines()
        if line.strip().startswith("POSTGRES_PASSWORD=")
    ]
    assert len(pw_lines) == 1
    value = pw_lines[0].split("=", 1)[1].strip()
    assert value and value != ("change" + "-me")
    assert len(value) >= 16


def test_ensure_postgres_password_keeps_effective_nonempty_value(tmp_path):
    """When the last assignment is non-empty, it is preserved as-is (no rewrite)."""
    from praisonai_deploy.compose import _ensure_postgres_password, _env_password_value

    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD= # placeholder\nPOSTGRES_PASSWORD=real-secret-value\n",
        encoding="utf-8",
    )
    _ensure_postgres_password(env_file)
    lines = [
        line for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("POSTGRES_PASSWORD=")
    ]
    # Effective (last) value is non-empty → left untouched.
    assert any(_env_password_value(l.split("=", 1)[1]) == "real-secret-value" for l in lines)


def test_ensure_postgres_password_regenerates_when_effective_empty(tmp_path):
    """A trailing empty override makes the effective value empty → regenerate a strong one."""
    from praisonai_deploy.compose import _ensure_postgres_password, _env_password_value

    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD=present\nPOSTGRES_PASSWORD= # comment\n",
        encoding="utf-8",
    )
    _ensure_postgres_password(env_file)
    lines = [
        line for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("POSTGRES_PASSWORD=")
    ]
    # Exactly one assignment, with a non-empty, strong effective value.
    assert len(lines) == 1
    value = _env_password_value(lines[0].split("=", 1)[1])
    assert value and value != "present"
    assert len(value) >= 16


def test_ensure_postgres_password_treats_quoted_empty_as_empty(tmp_path):
    from praisonai_deploy.compose import _ensure_postgres_password, _env_password_value

    env_file = tmp_path / ".env"
    env_file.write_text('POSTGRES_PASSWORD=""\n', encoding="utf-8")
    _ensure_postgres_password(env_file)
    lines = [
        line for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("POSTGRES_PASSWORD=")
    ]
    assert len(lines) == 1
    value = _env_password_value(lines[0].split("=", 1)[1])
    assert value and len(value) >= 16


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX file mode only")
def test_prepare_compose_project_env_is_owner_only(tmp_path):
    import stat

    from praisonai_deploy.compose import prepare_compose_project

    agents = tmp_path / "agents.yaml"
    agents.write_text(
        "agents:\n  - name: a\n    role: r\n    goal: g\n    backstory: b\n"
        "deploy:\n  type: api\n",
        encoding="utf-8",
    )
    project = prepare_compose_project(str(agents), project_dir=tmp_path / "work")
    mode = stat.S_IMODE((project / ".env").stat().st_mode)
    assert mode == 0o600


def test_resolve_api_port_precedence(tmp_path):
    from praisonai_deploy.compose import _resolve_api_port

    # runtime env wins
    assert _resolve_api_port({"API_PORT": "9100"}, tmp_path) == "9100"
    # falls back to project .env
    (tmp_path / ".env").write_text("API_PORT=9200\n", encoding="utf-8")
    assert _resolve_api_port({}, tmp_path) == "9200"
    # final default
    assert _resolve_api_port({}, tmp_path / "missing") == "8005"


def test_create_from_template_refuses_overwrite(tmp_path):
    """Scaffolding must not silently clobber existing project files."""
    from praisonai_deploy.starters import create_from_template, list_templates

    templates = list_templates()
    assert templates, "expected at least one starter template"
    name = templates[0]["name"]

    # First creation succeeds.
    first = create_from_template(name, str(tmp_path))
    assert first.success, first.error

    # Second creation into the same dir must fail (conflict guard).
    second = create_from_template(name, str(tmp_path))
    assert not second.success
    assert "already contains" in second.message

    # force=True permits overwrite.
    forced = create_from_template(name, str(tmp_path), force=True)
    assert forced.success, forced.error


def test_deployment_template_passes_helm_values_via_env():
    """Helm init container must not interpolate values into Python source."""
    chart = resolve_helm_chart_dir(AGENTS_API_CHART)
    deployment = (chart / "templates" / "deployment.yaml").read_text(encoding="utf-8")
    # Values are surfaced as env vars and read via os.environ, not inlined.
    assert 'os.environ["PRAISONAI_AGENTS_FILE"]' in deployment
    assert 'os.environ["PRAISONAI_SERVER_FILE"]' in deployment
    assert "{{ .Values.agents.fileName }}" not in deployment
    # DATABASE_URL carries the password via k8s env interpolation.
    assert "$(POSTGRES_PASSWORD)" in deployment

