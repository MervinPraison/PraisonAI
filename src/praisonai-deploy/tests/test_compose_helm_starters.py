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

