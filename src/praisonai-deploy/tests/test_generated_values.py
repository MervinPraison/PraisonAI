"""Config values must not add Dockerfile lines or CLI options.

One helper, ``models.check_value``, checks every value that is written into a
generated Dockerfile or passed to a cloud CLI. The guard tests list every
field and every provider so a new one has to be checked too.
"""
import ast
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError

from praisonai_deploy import models
from praisonai_deploy.docker import generate_dockerfile
from praisonai_deploy.models import CloudConfig, DockerConfig

INJECTED_LINE = "python:3.11-slim\nRUN echo INJECTED"


# --- Dockerfile ----------------------------------------------------------------

@pytest.mark.parametrize("field", ["base_image", "image_name", "tag", "registry"])
@pytest.mark.parametrize("bad", [INJECTED_LINE, "img RUN x", "img\r", "-img", ""])
def test_docker_config_rejects_values_that_break_a_line(field, bad):
    with pytest.raises(ValidationError):
        DockerConfig(**{field: bad})


def test_docker_config_rejects_unsafe_value_on_assignment():
    cfg = DockerConfig()
    with pytest.raises(ValidationError):
        cfg.base_image = INJECTED_LINE


def test_generate_dockerfile_has_no_injected_directive():
    cfg = DockerConfig()
    object.__setattr__(cfg, "base_image", INJECTED_LINE)  # skip the model validation
    with pytest.raises(ValueError):
        generate_dockerfile("agents.yaml", cfg)


@pytest.mark.parametrize("name", ["agents.yaml\nRUN echo x", "my agents.yaml", "a.yaml;x"])
def test_generate_dockerfile_rejects_agents_file_names_that_break_copy(name):
    with pytest.raises(ValueError):
        generate_dockerfile(f"/tmp/{name}")


@pytest.mark.parametrize("image", [
    "python:3.11-slim", "ghcr.io/org/app:1.2.3", "localhost:5000/app",
    "python@sha256:" + "a" * 64,
])
def test_real_image_references_still_work(image):
    text = generate_dockerfile("/abs/path/agents.yaml", DockerConfig(base_image=image))
    assert text.startswith(f"FROM {image}\n")
    assert "COPY agents.yaml /app/agents.yaml" in text


# --- cloud CLI arguments -------------------------------------------------------

def _cloud(**kw):
    base = dict(provider="azure", region="eastus", service_name="svc", resource_group="rg")
    base.update(kw)
    return CloudConfig(**base)


@pytest.mark.parametrize("key", ["--image", "--image=rogue", "-a", "A B", "A=B", "1ABC", ""])
def test_env_var_keys_must_be_names(key):
    with pytest.raises(ValidationError):
        _cloud(env_vars={key: "x"})


def test_env_var_values_are_free_text():
    cfg = _cloud(env_vars={"PEM": "-----BEGIN-----\nabc", "FLAGS": "--x"})
    assert cfg.env_vars["FLAGS"] == "--x"


CLI_FIELDS = ["region", "service_name", "image", "cpu", "memory", "cluster_name",
              "task_definition", "resource_group", "subscription_id", "project_id"]


@pytest.mark.parametrize("field", CLI_FIELDS)
@pytest.mark.parametrize("bad", ["--yes", "-x", "a\nb"])
def test_cli_values_cannot_become_options(field, bad):
    with pytest.raises(ValidationError):
        _cloud(**{field: bad})


def test_azure_argv_keeps_env_pairs_as_values():
    from praisonai_deploy.providers.azure import AzureProvider
    cfg = _cloud(env_vars={"OPENAI_API_KEY": "--image=x"}, subscription_id="sub")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return mock.Mock(returncode=0, stdout="{}", stderr="")

    with mock.patch("subprocess.run", side_effect=fake_run):
        AzureProvider(cfg).deploy()
    create = next(c for c in calls if c[:3] == ["az", "containerapp", "create"])
    pairs = create[create.index("--env-vars") + 1:]
    assert all(not p.startswith("-") for p in pairs)


# --- guards --------------------------------------------------------------------

def test_guard_every_str_cloud_field_is_checked():
    """Every optional/required str field of CloudConfig reaches some CLI argv."""
    str_fields = {
        name for name, f in CloudConfig.model_fields.items()
        if f.annotation in (str, models.Optional[str])
    }
    assert str_fields == set(CLI_FIELDS)
    validators = CloudConfig.__pydantic_decorators__.field_validators
    checked = set(validators["_validate_cli_value"].info.fields)
    assert checked == set(CLI_FIELDS)
    assert set(validators["_validate_env_keys"].info.fields) == {"env_vars"}


def test_guard_every_dockerfile_interpolation_is_checked():
    """Every value ``generate_dockerfile`` writes is checked or an int/constant."""
    import praisonai_deploy.docker as docker_mod
    tree = ast.parse(Path(docker_mod.__file__).read_text())
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate_dockerfile")
    written = set()
    for node in ast.walk(func):
        if isinstance(node, ast.FormattedValue):
            written.add(ast.unparse(node.value))
    # base_image: model validator + render check; agents_basename: render check;
    # expose / expose[0]: List[int]; DEFAULT_GUNICORN_TIMEOUT: constant.
    assert written == {"config.base_image", "agents_basename", "port", "expose_lines",
                       "config.expose[0]", "DEFAULT_GUNICORN_TIMEOUT"}
    src = ast.unparse(func)
    assert "check_value(config.base_image" in src
    assert "agents_basename = check_value(" in src


PROVIDERS_DIR = Path(models.__file__).parent / "providers"


def test_guard_providers_take_argv_values_only_from_cloud_config():
    """Providers build argv from ``self.config`` (validated) and literals only."""
    for path in sorted(PROVIDERS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "subprocess.run":
                assert node.args, f"{path.name}:{node.lineno}"
                arg = node.args[0]
                # A list literal, a local list, or a self._*_command() helper; never a shell string.
                is_helper = isinstance(arg, ast.Call) and ast.unparse(arg.func).startswith("self._")
                assert is_helper or isinstance(arg, (ast.List, ast.Name, ast.BinOp)), f"{path.name}:{node.lineno}"
                assert not any(k.arg == "shell" for k in node.keywords), f"{path.name}:{node.lineno}"


# --- GCP --set-env-vars: a comma in a value must not add a variable -----------

def _gcloud_env(arg):
    """Parse a --set-env-vars value the way gcloud does (incl. ^DELIM^)."""
    delim = ","
    if arg.startswith("^"):
        delim, arg = arg[1:].split("^", 1)
    return dict(p.split("=", 1) for p in arg.split(delim))


def _gcp_env_arg(env_vars):
    from praisonai_deploy.providers.gcp import GCPProvider
    cfg = CloudConfig(provider="gcp", region="us-central1", service_name="svc",
                      project_id="proj", env_vars=env_vars)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return mock.Mock(returncode=0, stdout="[]", stderr="")

    with mock.patch("subprocess.run", side_effect=fake_run):
        GCPProvider(cfg).deploy()
    deploy = next(c for c in calls if c[:3] == ["gcloud", "run", "deploy"])
    return deploy[deploy.index("--set-env-vars") + 1]


def test_gcp_comma_in_value_does_not_add_a_variable():
    env = {"ALLOWED": "a,DEBUG=true", "KEY": "k@x"}
    assert _gcloud_env(_gcp_env_arg(env)) == env


def test_gcp_plain_values_keep_comma_form():
    assert _gcp_env_arg({"A": "1", "B": "2"}) == "A=1,B=2"
