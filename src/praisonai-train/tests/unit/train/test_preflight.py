"""The version floors were pip metadata only, and the CUDA pin ignored hardware.

**Floors.** `pyproject.toml` declares `torch>=2.6.0`, `transformers>=4.51.3`
and so on, but nothing checked them at runtime — and pip is routinely bypassed:
`--no-deps`, a hand-built conda env, `setup_conda_env.sh` pinning its own
torch. The failure then arrives as whatever traceback the mismatched package
happens to raise, several imports deep, long after the CLI accepted the run.

**The pin.** Every Linux host got `pytorch-cuda=12.4` regardless of what was in
it. On an AMD box or a Blackwell card that produces a working-*looking*
environment that fails at the first kernel; on a CPU-only host it installs a
CUDA build that can never run.
"""

import re
try:
    import tomllib                      # 3.11+
except ModuleNotFoundError:             # 3.10, which pyproject still supports
    import tomli as tomllib
from pathlib import Path

import pytest

from praisonai_train import preflight as pf

ROOT = Path(__file__).resolve().parents[3]
SETUP_SH = ROOT / "praisonai_train" / "setup" / "setup_conda_env.sh"


def _code():
    """The script with comments stripped.

    The comment explaining the old behaviour quotes `pytorch-cuda=12.4`, so a
    structural assertion over the raw text matches the explanation rather than
    the code — and passes whatever the code does.
    """
    lines = []
    for line in SETUP_SH.read_text().splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line.split(" #", 1)[0])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The floors match the packaging metadata
# --------------------------------------------------------------------------- #
def test_the_floors_match_pyproject():
    """Otherwise the runtime check and pip disagree about what is required.

    A floor that is lower here than in pyproject lets a broken environment
    through; higher, and it refuses one pip would have built.
    """
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    declared = {}
    for group in data["project"].get("optional-dependencies", {}).values():
        for spec in group:
            m = re.match(r"^([A-Za-z0-9_.-]+)\s*>=\s*([0-9][0-9A-Za-z.]*)", spec)
            if m:
                declared[m.group(1).lower()] = m.group(2)
    for package, floor in pf.FLOORS.items():
        assert package in declared, f"{package} is checked but not declared"
        assert declared[package] == floor, (
            f"{package}: preflight wants {floor}, pyproject declares "
            f"{declared[package]}")


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("installed,floor,ok", [
    ("2.6.0", "2.6.0", True),
    ("2.7.1", "2.6.0", True),
    ("2.5.1", "2.6.0", False),
    ("2.10.0", "2.9.0", True),      # not a string comparison
    ("2.9.0", "2.10.0", False),
    ("2025.9.1", "2025.9.1", True),
    ("2025.8.9", "2025.9.1", False),
])
def test_versions_compare_numerically(installed, floor, ok):
    assert pf.satisfies(installed, floor) is ok


def test_a_prerelease_of_the_required_version_counts():
    # Refusing 2.6.0rc1 against a 2.6.0 floor blocks people testing upstream,
    # and unsloth's own checks are release-level too.
    assert pf.satisfies("2.6.0rc1", "2.6.0") is True
    assert pf.satisfies("2.6.0.dev20250101", "2.6.0") is True


def test_a_missing_version_never_satisfies():
    assert pf.satisfies(None, "2.6.0") is False
    assert pf.satisfies("", "2.6.0") is False


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #
def test_absent_and_stale_are_reported_differently(monkeypatch):
    # They need different remedies: install versus upgrade.
    monkeypatch.setattr(pf, "installed_version",
                        lambda p: None if p == "torch" else "0.0.1")
    problems = pf.check({"torch": "2.6.0", "trl": "0.18.2"})
    assert ("torch", None, "2.6.0") in problems
    assert ("trl", "0.0.1", "0.18.2") in problems
    text = pf.describe(problems)
    assert "Missing: torch" in text
    assert "trl 0.0.1 is older than the required 0.18.2" in text


def test_the_report_names_a_command_that_installs_everything(monkeypatch):
    monkeypatch.setattr(pf, "installed_version", lambda p: None)
    text = pf.describe(pf.check({"torch": "2.6.0", "trl": "0.18.2"}))
    assert 'pip install -U "torch>=2.6.0" "trl>=0.18.2"' in text


def test_a_healthy_environment_reports_nothing(monkeypatch):
    monkeypatch.setattr(pf, "installed_version", lambda p: "9999.0.0")
    assert pf.check() == []


def test_the_lazy_import_checks_before_importing(monkeypatch):
    import inspect

    from praisonai_train.train.llm import trainer

    src = inspect.getsource(trainer._lazy_import_training_deps)
    check = src.index("from praisonai_train.preflight import")
    imports = src.index("import torch")
    assert check < imports, (
        "the floors are checked after the imports that would fail on them")


# --------------------------------------------------------------------------- #
# The installer probes before it pins
# --------------------------------------------------------------------------- #
def test_the_installer_detects_before_pinning():
    body = _code()
    probe = body.index("detect_accelerator()")
    pin = body.index("pytorch-cuda=12.4")
    assert probe < pin, "the CUDA pin is chosen before the hardware is looked at"


def test_the_cuda_pin_is_conditional():
    body = _code()
    # Exactly one occurrence, inside the cuda branch of the case statement.
    assert body.count("pytorch-cuda=12.4") == 1, (
        "the pin appears more than once; a branch will diverge")
    case_start = body.index("case \"$ACCELERATOR\"")
    assert body.index("pytorch-cuda=12.4") > case_start


def test_the_probe_covers_the_three_real_outcomes():
    body = _code()
    for signal in ("nvidia-smi", "/proc/driver/nvidia/gpus", "rocminfo"):
        assert signal in body, f"the probe does not look for {signal}"


def test_a_cpu_host_is_warned_that_training_will_refuse():
    # trainer.py raises on a missing CUDA GPU, so an installer that silently
    # builds a CPU env hands the user a working-looking dead end.
    body = _code()
    cpu_branch = body[body.index("    cpu)"):]
    assert "no GPU detected" in cpu_branch


def test_the_script_still_parses():
    import subprocess

    assert subprocess.run(["bash", "-n", str(SETUP_SH)]).returncode == 0
