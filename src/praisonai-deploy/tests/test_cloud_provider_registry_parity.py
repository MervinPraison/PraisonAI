"""A provider the registry can run must also validate.

``CloudProvider`` is an ``Enum`` and cannot be extended at runtime, so using it
as the validation gate made the ``praisonai.deploy.providers`` entry-point
group — which *is* declared in pyproject.toml — impossible to use.
"""

import json

import pytest

from praisonai_deploy.models import CloudConfig, CloudProvider, coerce_cloud_provider
from praisonai_deploy.providers import _registry as registry_mod
from praisonai_deploy.providers.base import get_provider
from praisonai_deploy.schema import validate_agents_yaml

BUILTINS = ["aws", "azure", "gcp", "fly", "railway", "render"]

YAML = """\
name: Sample Agent
framework: praisonai
deploy:
  type: cloud
  cloud:
    provider: hetzner
    region: fsn1
    service_name: praisonai-service
"""


class HetznerProvider:
    """Stand-in for a third-party provider registered via entry points."""

    def __init__(self, config):
        self.config = config

    def deploy(self):
        return {"ok": True, "provider": "hetzner", "region": self.config.region}

    def doctor(self):
        return {"ok": True}

    def plan(self):
        return {"ok": True}

    def status(self):
        return {"ok": True}

    def destroy(self, force: bool = False):
        return {"ok": True}


@pytest.fixture
def plugin_provider(monkeypatch):
    """Register 'hetzner' in a throwaway registry and make it the default."""
    reg = registry_mod.CloudProviderRegistry()
    reg.register("hetzner", HetznerProvider)
    monkeypatch.setattr(
        registry_mod.CloudProviderRegistry, "_default_instance", reg, raising=False
    )
    return reg


def test_registry_and_validation_agree(plugin_provider):
    assert registry_mod.list_cloud_providers() == BUILTINS + ["hetzner"]
    for name in registry_mod.list_cloud_providers():
        assert coerce_cloud_provider(name) == name


def test_unknown_provider_is_still_rejected(plugin_provider):
    with pytest.raises(ValueError) as exc:
        CloudConfig(provider="nope", region="x", service_name="svc")
    assert "Invalid cloud provider: nope" in str(exc.value)
    assert "hetzner" in str(exc.value)  # the list comes from the registry


def test_builtin_stays_an_enum_member_and_plugin_is_a_str(plugin_provider):
    assert CloudConfig(provider="AWS", region="r", service_name="s").provider is CloudProvider.AWS
    assert CloudConfig(provider=" HETZNER ", region="r", service_name="s").provider == "hetzner"


@pytest.mark.parametrize("name", BUILTINS + ["hetzner"])
def test_serialisation_round_trip(plugin_provider, name):
    cfg = CloudConfig(provider=name, region="r", service_name="svc")
    for source in (cfg.model_dump(), json.loads(cfg.model_dump_json())):
        again = CloudConfig(**source)
        assert again.provider == cfg.provider
        assert type(again.provider) is type(cfg.provider)
    assert json.loads(cfg.model_dump_json())["provider"] == name


def test_builtin_serialisation_is_unchanged(plugin_provider):
    cfg = CloudConfig(provider=CloudProvider.AWS, region="r", service_name="svc")
    assert cfg.model_dump()["provider"] is CloudProvider.AWS
    assert json.loads(cfg.model_dump_json())["provider"] == "aws"


def test_yaml_with_plugin_provider_validates_and_runs(plugin_provider, tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text(YAML)
    config = validate_agents_yaml(str(path))
    assert config.cloud.provider == "hetzner"
    assert get_provider(config.cloud).deploy() == {
        "ok": True, "provider": "hetzner", "region": "fsn1",
    }


def test_validate_command_prints_plugin_provider(plugin_provider, tmp_path, capsys):
    """The validate command must not crash on a plugin provider (plain str)."""
    import argparse

    from praisonai_deploy.cli.features.deploy import DeployHandler

    path = tmp_path / "agents.yaml"
    path.write_text(YAML)
    args = argparse.Namespace(file=str(path), json=False)
    DeployHandler().handle_validate(args)
    out = capsys.readouterr().out
    assert "hetzner" in out
    assert "Configuration is valid" in out


def test_sample_generation_preserves_plugin_provider(plugin_provider):
    """generate_sample_yaml must emit the requested plugin, not fall back to aws."""
    from praisonai_deploy.models import DeployType
    from praisonai_deploy.schema import generate_sample_yaml

    text = generate_sample_yaml(DeployType.CLOUD, coerce_cloud_provider("hetzner"))
    assert "provider: hetzner" in text
    assert "provider: aws" not in text
