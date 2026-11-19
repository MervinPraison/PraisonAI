"""A subprocess sandbox config's default policy must be one that backend can keep.

The default SecurityPolicy says allow_network=False. A plain host subprocess
cannot block the network, and praisonai-sandbox's SubprocessSandbox now refuses
a policy that claims it can. So SandboxConfig.subprocess() -- what
Agent(sandbox=True) and SandboxManager() use -- defaults to allow_network=True,
while an isolating backend keeps the closed default and an explicit policy is
never rewritten.
"""
import dataclasses

import pytest

from praisonaiagents.sandbox.config import SandboxConfig, SecurityPolicy


@pytest.mark.parametrize("config", [
    SandboxConfig(),
    SandboxConfig.subprocess(),
    SandboxConfig(sandbox_type="subprocess"),
    SandboxConfig(sandbox_type="local"),
], ids=["bare", "subprocess()", "type=subprocess", "type=local"])
def test_a_plain_subprocess_defaults_to_an_honest_network_setting(config):
    assert config.security_policy.allow_network is True


@pytest.mark.parametrize("config", [
    SandboxConfig.docker(),
    SandboxConfig(sandbox_type="sandlock"),
    SandboxConfig.e2b(),
], ids=["docker", "sandlock", "e2b"])
def test_an_isolating_backend_keeps_the_closed_default(config):
    assert config.security_policy.allow_network is False


def test_only_the_network_field_differs_from_the_standard_policy():
    honest = dataclasses.asdict(SandboxConfig.subprocess().security_policy)
    standard = dataclasses.asdict(SecurityPolicy())
    assert {k for k in standard if honest[k] != standard[k]} == {"allow_network"}


def test_an_explicit_policy_is_never_rewritten():
    policy = SecurityPolicy()
    assert SandboxConfig(security_policy=policy).security_policy is policy
    assert policy.allow_network is False


def test_each_config_gets_its_own_policy():
    assert SandboxConfig().security_policy is not SandboxConfig().security_policy
