"""Shipped examples must never contain raw credentials (issue #5783).

Operators copy example configs verbatim into durable stores, so every channel
credential in ``examples/`` must be an environment (``${VAR}``) or SecretRef
(``{source, id}``) reference, and no high-confidence secret literal may appear.
Intentionally fake demo values must say so (contain ``FAKE``).
"""

import re
from pathlib import Path

import pytest
import yaml

# repo_root/src/praisonai/tests/unit/this_file -> up 4 to repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXAMPLES_DIR = _REPO_ROOT / "examples"

_SECRET_PATTERNS = re.compile(
    r"\bxox[abprs]-[0-9A-Za-z-]{10,}"  # Slack bot/user tokens
    r"|\bxapp-\d-[0-9A-Za-z-]{10,}"  # Slack app tokens
    r"|\bsk-(?:proj-|live-|ant-)?[A-Za-z0-9_-]{20,}"  # OpenAI/Anthropic keys
    r"|\bgh[pousr]_[A-Za-z0-9]{36}"  # GitHub tokens
    r"|\bAKIA[0-9A-Z]{16}"  # AWS access key ids
    r"|\bAIza[0-9A-Za-z_-]{35}"  # Google API keys
    r"|\b\d{8,10}:AA[0-9A-Za-z_-]{33}\b"  # Telegram bot tokens
)
_TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".sh", ".env", ".toml", ".ts", ".js", ".ipynb"}
_CREDENTIAL_KEYS = {
    "token", "bot_token", "app_token", "verify_token", "access_token",
    "signing_secret", "api_key", "password", "secret", "auth_token",
}
_ENV_REF = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")


def _example_files(suffixes):
    if not _EXAMPLES_DIR.exists():
        return []
    return sorted(
        p for p in _EXAMPLES_DIR.rglob("*")
        if p.is_file() and p.suffix in suffixes and "node_modules" not in p.parts
    )


@pytest.mark.skipif(not _EXAMPLES_DIR.exists(), reason="examples not present")
def test_examples_contain_no_secret_literals():
    hits = []
    for path in _example_files(_TEXT_SUFFIXES):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in _SECRET_PATTERNS.finditer(text):
            if "FAKE" not in match.group(0).upper():
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{path.relative_to(_REPO_ROOT)}:{line}")
    assert not hits, "Raw secret literals in examples (use ${VAR}): " + ", ".join(hits)


def _channel_yaml_files():
    files = []
    for path in _example_files({".yaml", ".yml"}):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        if isinstance(data, dict) and isinstance(data.get("channels"), dict):
            files.append((path, data["channels"]))
    return files


@pytest.mark.skipif(not _channel_yaml_files(), reason="no channel examples present")
@pytest.mark.parametrize(
    "path,channels", _channel_yaml_files(), ids=lambda v: v.name if isinstance(v, Path) else ""
)
def test_channel_credentials_are_references(path, channels):
    for name, cfg in channels.items():
        if not isinstance(cfg, dict):
            continue
        for key, value in cfg.items():
            if key not in _CREDENTIAL_KEYS or value in (None, ""):
                continue
            is_secret_ref = isinstance(value, dict) and {"source", "id"} <= value.keys()
            is_env_ref = isinstance(value, str) and bool(_ENV_REF.match(value))
            assert is_secret_ref or is_env_ref, (
                f"{path.name}: channels.{name}.{key} must be a ${{VAR}} or "
                f"SecretRef reference, not a literal"
            )
