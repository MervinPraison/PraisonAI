"""CloudConfig settings must reach the provider CLI, or be reported.

CloudConfig declares env_vars, cpu, memory, image, region, min_instances and
max_instances, validates them with extra="forbid", and echoes them from
`deploy validate --json`. fly, railway and render sent NONE of them: the
commands were

    flyctl deploy --app <name> --remote-only
    railway up --detach
    render ...

So a config naming env_vars={"OPENAI_API_KEY": ...} deployed an application
without its key, and reported success. AWS, GCP and Azure consume the same
fields, which is what makes this an inconsistency rather than an unbuilt
feature.

Fly now carries what flyctl actually accepts -- flags verified against
flyctl v0.4.14: -e/--env, --vm-cpus, --vm-memory and --image exist, --region
does not. Railway and render name what they cannot apply instead of guessing
at flags: their CLIs were not installed to verify against, and inventing flag
names would turn a silent omission into a broken deploy.
"""
import pytest

from praisonai_deploy.models import CloudConfig
from praisonai_deploy.providers.fly import FlyProvider
from praisonai_deploy.providers.railway import RailwayProvider
from praisonai_deploy.providers.render import RenderProvider


def _config(provider, **overrides):
    base = dict(
        provider=provider,
        region="lhr",
        service_name="demo",
        cpu="2",
        memory="2048",
        image="registry.example.com/demo:v1",
        env_vars={"OPENAI_API_KEY": "sk-secret", "LOG_LEVEL": "debug"},
    )
    base.update(overrides)
    return CloudConfig(**base)


class TestFlyCarriesWhatFlyctlAccepts:

    def test_secrets_do_not_reach_the_deploy_argv(self):
        """Env values can be credentials; the argv is process-visible.

        They travel through `fly secrets set` instead (see _set_secrets), so
        the deploy command must not carry --env pairs at all.
        """
        cmd = " ".join(FlyProvider(_config("fly"))._deploy_command("demo"))
        assert "--env" not in cmd
        assert "sk-secret" not in cmd

    def test_secrets_are_staged_out_of_the_argument_vector(self):
        """`fly secrets set --stage` receives the env values, not `flyctl deploy`."""
        recorded = []

        def fake_run(cmd, **kwargs):
            recorded.append(cmd)
            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()

        provider = FlyProvider(_config("fly"))
        import praisonai_deploy.providers.fly as fly_mod
        original = fly_mod.subprocess.run
        fly_mod.subprocess.run = fake_run
        try:
            provider.deploy()
        finally:
            fly_mod.subprocess.run = original

        secret_cmds = [c for c in recorded if c[:3] == ["flyctl", "secrets", "set"]]
        assert secret_cmds, "env_vars never reached `fly secrets set`"
        staged = " ".join(secret_cmds[0])
        assert "--stage" in staged
        assert "OPENAI_API_KEY=sk-secret" in staged
        deploy_cmds = [c for c in recorded if c[:2] == ["flyctl", "deploy"]]
        assert deploy_cmds and "--env" not in " ".join(deploy_cmds[0])

    def test_cpu_and_memory_reach_the_command(self):
        cmd = " ".join(FlyProvider(_config("fly"))._deploy_command("demo"))
        assert "--vm-cpus 2" in cmd
        assert "--vm-memory 2048" in cmd

    def test_the_ecs_cpu_default_is_not_forwarded_to_fly(self):
        """CloudConfig.cpu defaults to "256" (an ECS CPU unit), which is not a
        Fly VM core count -- `--vm-cpus 256` would fail. A config leaving the
        defaults must not forward them."""
        cfg = CloudConfig(provider="fly", region="", service_name="demo")
        cmd = " ".join(FlyProvider(cfg)._deploy_command("demo"))
        assert "--vm-cpus" not in cmd
        assert "--vm-memory" not in cmd

    def test_the_image_reaches_the_command(self):
        cmd = " ".join(FlyProvider(_config("fly"))._deploy_command("demo"))
        assert "--image registry.example.com/demo:v1" in cmd

    def test_no_invented_region_flag(self):
        """flyctl deploy has no --region; region belongs in fly.toml."""
        cmd = " ".join(FlyProvider(_config("fly"))._deploy_command("demo"))
        assert "--region" not in cmd

    def test_region_is_reported_as_unsupported(self):
        assert any("region" in s
                   for s in FlyProvider(_config("fly"))._unsupported_settings())

    def test_a_bare_config_produces_a_plain_command(self):
        cfg = CloudConfig(provider="fly", region="", service_name="demo",
                          cpu=None, memory=None)
        cmd = FlyProvider(cfg)._deploy_command("demo")
        assert cmd == ["flyctl", "deploy", "--app", "demo", "--remote-only"]

    def test_the_app_name_is_still_passed(self):
        cmd = FlyProvider(_config("fly"))._deploy_command("demo")
        assert cmd[:4] == ["flyctl", "deploy", "--app", "demo"]


@pytest.mark.parametrize("provider_cls,name", [
    (RailwayProvider, "railway"),
    (RenderProvider, "render"),
])
class TestProvidersThatCannotApplyThemSaySo:

    def test_env_vars_are_named(self, provider_cls, name):
        pending = provider_cls(_config(name))._unapplied_settings()
        assert any("env_vars" in p for p in pending)

    def test_the_secret_name_is_listed_but_not_its_value(self, provider_cls, name):
        pending = " ".join(provider_cls(_config(name))._unapplied_settings())
        assert "OPENAI_API_KEY" in pending
        assert "sk-secret" not in pending, "a secret value was put in a log line"

    def test_a_default_config_reports_nothing(self, provider_cls, name):
        cfg = CloudConfig(provider=name, region="", service_name="demo")
        assert provider_cls(cfg)._unapplied_settings() == []

    def test_unapplied_settings_reach_the_structured_result(self, provider_cls, name):
        """A `deploy --json` consumer must see that settings were dropped, not
        just a log line -- the DeployResult carries them in metadata."""
        provider = provider_cls(_config(name))
        import praisonai_deploy.providers.railway as railway_mod
        import praisonai_deploy.providers.render as render_mod

        def fake_run(cmd, **kwargs):
            class _R:
                returncode = 0
                stdout = ""
                stderr = ""
            return _R()

        originals = (railway_mod.subprocess.run, render_mod.subprocess.run)
        railway_mod.subprocess.run = fake_run
        render_mod.subprocess.run = fake_run
        try:
            result = provider.deploy()
        finally:
            railway_mod.subprocess.run, render_mod.subprocess.run = originals

        assert result.success is True
        assert result.metadata.get("unapplied"), "dropped settings absent from result"
        assert any("env_vars" in item for item in result.metadata["unapplied"])
        assert "sk-secret" not in " ".join(result.metadata["unapplied"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
