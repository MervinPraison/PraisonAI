"""Read, merge and remove the ``praisonai`` entry in a client's config file.

Every change is planned first (:func:`plan_write` / :func:`plan_remove`):
the plan carries the file before and after and a unified diff, so the CLI
can show a dry run. :func:`apply` keeps a ``.praisonai.bak`` copy of the old
file and replaces it atomically. Writing the same entry twice changes
nothing. Only our own entry is touched: other servers, keys and (for TOML)
comments stay as they were.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .catalog import Client, ServerSpec, config_path, container_key, entry, file_format

BACKUP_SUFFIX = ".praisonai.bak"


class ConfigError(Exception):
    """The file cannot be changed safely (unreadable, comments we would lose…)."""


@dataclass
class Plan:
    client: Client
    path: Path
    before: Optional[str]
    after: str

    @property
    def changed(self) -> bool:
        return self.before != self.after

    @property
    def diff(self) -> str:
        return "".join(
            difflib.unified_diff(
                (self.before or "").splitlines(keepends=True),
                self.after.splitlines(keepends=True),
                fromfile=f"{self.path} (before)",
                tofile=f"{self.path} (after)",
            )
        )


# --------------------------------------------------------------------------- TOML


def toml_block(name: str, body: Dict[str, Any]) -> str:
    """A ``[mcp_servers.<name>]`` table (strings, lists of strings, numbers)."""
    lines = [f"[mcp_servers.{name}]"]
    for key, value in body.items():
        lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines) + "\n"


def _toml_split(text: str, name: str) -> tuple[str, Optional[str]]:
    """``text`` without our table(s), and our table text (``None`` if absent)."""
    head = re.compile(rf'^\[mcp_servers\.(?:{re.escape(name)}|"{re.escape(name)}")(\.[^\]]+)?\]\s*$')
    keep: List[str] = []
    ours: List[str] = []
    inside = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("["):
            inside = bool(head.match(line.strip()))
        (ours if inside else keep).append(line)
    return "".join(keep), ("".join(ours) if ours else None)


# --------------------------------------------------------------------------- JSON


def _strip_comments(text: str) -> str:
    """JSONC → JSON: drop ``//`` and ``/* */`` comments outside strings."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _load_json(text: Optional[str], path: Path, jsonc: bool) -> Dict[str, Any]:
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        if not jsonc:
            raise ConfigError(f"{path} is not valid JSON; fix it or edit it by hand.") from None
        raise ConfigError(
            f"{path} has comments, which a rewrite would drop. Paste the snippet from "
            "`praisonai connect <client> --print` into it instead."
        ) from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not hold a JSON object.")
    return data


def _load_yaml(text: Optional[str], path: Path) -> Dict[str, Any]:
    import yaml

    try:
        data = yaml.safe_load(text or "") or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not hold a YAML mapping.")
    return data


def _dump(data: Dict[str, Any], fmt: str) -> str:
    if fmt == "yaml":
        import yaml

        return yaml.safe_dump(data, sort_keys=False)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _servers(data: Dict[str, Any], client: Client, create: bool) -> Any:
    node: Any = data
    for key in container_key(client):
        if not isinstance(node, dict):
            raise ConfigError(f"Unexpected value at {'.'.join(container_key(client))}.")
        if key not in node:
            if not create:
                return None
            node[key] = {}
        node = node[key]
    return node


# --------------------------------------------------------------------------- API


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from None


def _path(client: Client, home: Path) -> Path:
    path = config_path(client, home)
    if path is None:
        raise ConfigError(f"{client.label} has no config file; use --print and paste the snippet.")
    return path


def read_entry(client: Client, home: Path, name: str) -> Optional[Any]:
    """Our entry as stored, or ``None``. Never raises for a missing file."""
    path = config_path(client, home)
    text = _read(path) if path else None
    if not text:
        return None
    fmt = file_format(client)
    if fmt == "toml":
        return _toml_split(text, name)[1]
    try:
        data = _load_yaml(text, path) if fmt == "yaml" else _load_json(text, path, False)
    except ConfigError:
        if fmt != "jsonc":
            return None
        try:
            data = json.loads(_strip_comments(text))
        except json.JSONDecodeError:
            return None
    servers = _servers(data, client, create=False)
    return servers.get(name) if isinstance(servers, dict) else None


def plan_write(client: Client, spec: ServerSpec, home: Path) -> Plan:
    path = _path(client, home)
    before = _read(path)
    body = entry(client, spec)
    fmt = file_format(client)
    if fmt == "toml":
        rest, _ = _toml_split(before or "", spec.name)
        rest = rest.rstrip("\n")
        return Plan(client, path, before, (rest + "\n\n" if rest else "") + toml_block(spec.name, body))
    data = _load_yaml(before, path) if fmt == "yaml" else _load_json(before, path, fmt == "jsonc")
    servers = _servers(data, client, create=True)
    if not isinstance(servers, dict):
        raise ConfigError(f"Unexpected value at {'.'.join(container_key(client))} in {path}.")
    servers[spec.name] = body
    after = _dump(data, fmt)
    if before is not None and _same(before, after, fmt):
        after = before  # semantically equal: keep the user's formatting
    return Plan(client, path, before, after)


def plan_remove(client: Client, home: Path, name: str) -> Optional[Plan]:
    """The plan that drops our entry, or ``None`` when there is none."""
    path = _path(client, home)
    before = _read(path)
    if before is None or read_entry(client, home, name) is None:
        return None
    fmt = file_format(client)
    if fmt == "toml":
        rest, _ = _toml_split(before, name)
        return Plan(client, path, before, rest.rstrip("\n") + "\n" if rest.strip() else "")
    data = _load_yaml(before, path) if fmt == "yaml" else _load_json(before, path, fmt == "jsonc")
    _servers(data, client, create=False).pop(name, None)
    return Plan(client, path, before, _dump(data, fmt))


def _same(a: str, b: str, fmt: str) -> bool:
    try:
        if fmt == "yaml":
            import yaml

            return yaml.safe_load(a) == yaml.safe_load(b)
        return json.loads(a) == json.loads(b)
    except Exception:
        return False


def apply(plan: Plan) -> Optional[Path]:
    """Write the plan; returns the backup path (``None`` for a new file)."""
    if not plan.changed:
        return None
    path = plan.path
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    mode = 0o600
    if plan.before is not None:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        backup.write_text(plan.before, encoding="utf-8")
        mode = path.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(plan.after)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return backup


_SECRET = re.compile(r"^(sk-|sk_|ghp_|gho_|xox[bp]-|AIza|gsk_)[A-Za-z0-9_\-]{8,}|^[A-Za-z0-9_\-]{32,}$")


def plaintext_secrets(stored: Any) -> List[str]:
    """Keys of env/headers values in our entry that look like raw secrets."""
    found: List[str] = []
    if not isinstance(stored, dict):
        return found
    for block in ("env", "environment", "envs", "headers"):
        for key, value in (stored.get(block) or {}).items():
            if isinstance(value, str) and "{" not in value and _SECRET.match(value):
                found.append(key)
    return found
