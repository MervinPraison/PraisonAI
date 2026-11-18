"""The MCP client catalog: one list of editors and agents, used by
``praisonai connect``, the docs and PraisonAIUI's Connect page.

Each :class:`Client` says where its user-level MCP config lives, the shape of
one server entry, how it references an environment variable, and whether it
has a one-click deep link or an ``add`` command. Nothing here touches the
disk; :mod:`.config_io` reads and writes.

Formats were checked against each vendor's docs (Nov 2026); the URL in
``docs`` is the source for that client's row.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlencode

#: The key every client's entry is written under.
SERVER_NAME = "praisonai"

#: Provider keys referenced (never copied) when they are set in the shell.
PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
)


@dataclass(frozen=True)
class ServerSpec:
    """The server a client is pointed at: a local command or a URL.

    ``env`` holds variable *names*. Each client gets a reference in its own
    syntax (``${env:NAME}``, ``${NAME}``, Codex ``env_vars``); a value is
    never written.
    """

    name: str = SERVER_NAME
    command: Optional[str] = None
    args: Tuple[str, ...] = ()
    env: Tuple[str, ...] = ()
    url: Optional[str] = None

    @property
    def argv(self) -> List[str]:
        return [self.command or "", *self.args]

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"name": self.name}
        if self.url:
            out["url"] = self.url
        else:
            out.update(command=self.command, args=list(self.args))
        if self.env:
            out["env"] = list(self.env)
        return out


def local_spec(
    tools: Sequence[str] = (),
    agents: Optional[str] = None,
    env: Optional[Sequence[str]] = None,
    name: str = SERVER_NAME,
) -> ServerSpec:
    """The stdio spec for this machine's ``praisonai-mcp``.

    The command is an absolute path, so GUI editors that do not read the
    shell's ``PATH`` still start it. ``tools`` (names or globs) and
    ``agents`` (an agents.yaml) are server args, so the scope holds in every
    client, deep links included.
    """
    # The praisonai-mcp of the environment running this code first: another
    # one on PATH may be an older install without --tools/--agents.
    sibling = Path(sys.executable).with_name("praisonai-mcp" + (".exe" if os.name == "nt" else ""))
    exe = str(sibling) if sibling.is_file() else shutil.which("praisonai-mcp")
    if exe:
        command, args = exe, ["serve", "--transport", "stdio"]
    else:
        command, args = sys.executable, ["-m", "praisonai_mcp", "serve", "--transport", "stdio"]
    if tools:
        args += ["--tools", ",".join(tools)]
    if agents:
        args += ["--agents", str(Path(agents).expanduser().resolve())]
    if env is None:
        env = [k for k in PROVIDER_ENV if os.environ.get(k)]
    return ServerSpec(name=name, command=command, args=tuple(args), env=tuple(env))


@dataclass(frozen=True)
class Client:
    """One MCP client.

    ``path``: the user config file, relative to the home folder; a dict when
    it differs per platform (``darwin`` / ``linux`` / ``win32``), ``None``
    for a client with no file we write (the generic entry).
    ``shape``: how one entry looks (see :func:`entry`).
    ``env_ref``: ``%s`` template for an env reference, ``None`` when the
    client has none (variables then come from the server's own environment).
    ``remote``: the entry for a URL server, ``None`` when unsupported.
    """

    id: str
    label: str
    group: str  # editor | terminal | other
    path: Any = None
    shape: str = "mcpServers"
    env_ref: Optional[str] = None
    remote: Optional[str] = "url"
    deeplink: Optional[str] = None  # cursor | vscode | vscode-insiders | kiro | lmstudio
    cli: Optional[str] = None  # claude | codex | gemini | copilot | code
    apps: Tuple[str, ...] = ()
    bins: Tuple[str, ...] = ()
    dirs: Tuple[str, ...] = ()
    download: str = ""
    docs: str = ""
    note: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


_COPILOT = ".copilot/mcp-config.json"
_JSON_FMT = {"toml": "toml", "yaml": "yaml"}

CLIENTS: Tuple[Client, ...] = (
    Client(
        "cursor", "Cursor", "editor", ".cursor/mcp.json", env_ref="${env:%s}",
        deeplink="cursor", apps=("Cursor.app",), bins=("cursor",), dirs=(".cursor",),
        download="https://cursor.com/download",
        docs="https://cursor.com/docs/context/mcp/install-links",
    ),
    Client(
        "vscode", "VS Code", "editor", _COPILOT, shape="copilot", env_ref="${%s}",
        remote="http", deeplink="vscode", cli="code",
        apps=("Visual Studio Code.app",), bins=("code",),
        download="https://code.visualstudio.com/download",
        docs="https://code.visualstudio.com/docs/copilot/reference/mcp-configuration",
    ),
    Client(
        "vscode-insiders", "VS Code Insiders", "editor", _COPILOT, shape="copilot",
        env_ref="${%s}", remote="http", deeplink="vscode-insiders",
        apps=("Visual Studio Code - Insiders.app",), bins=("code-insiders",),
        download="https://code.visualstudio.com/insiders/",
        docs="https://code.visualstudio.com/docs/copilot/reference/mcp-configuration",
    ),
    Client(
        "windsurf", "Windsurf (Devin Desktop)", "editor", ".codeium/windsurf/mcp_config.json",
        env_ref="${env:%s}", remote="serverUrl",
        apps=("Devin.app", "Windsurf.app"), bins=("windsurf",), dirs=(".codeium/windsurf",),
        download="https://windsurf.com/download",
        docs="https://docs.devin.ai/windsurf/plugins/cascade/mcp.md",
    ),
    Client(
        "claude-desktop", "Claude Desktop", "editor",
        {
            "darwin": "Library/Application Support/Claude/claude_desktop_config.json",
            "linux": ".config/Claude/claude_desktop_config.json",
            "win32": "AppData/Roaming/Claude/claude_desktop_config.json",
        },
        remote=None, apps=("Claude.app",),
        dirs=("Library/Application Support/Claude", ".config/Claude", "AppData/Roaming/Claude"),
        download="https://claude.ai/download",
        docs="https://modelcontextprotocol.io/docs/develop/connect-local-servers",
        note="Restart Claude Desktop to load the server.",
    ),
    Client(
        "zed", "Zed", "editor", ".config/zed/settings.json", shape="zed", remote=None,
        apps=("Zed.app",), bins=("zed",), dirs=(".config/zed",),
        download="https://zed.dev/download", docs="https://zed.dev/docs/ai/mcp",
    ),
    Client(
        "kiro", "Kiro", "editor", ".kiro/settings/mcp.json", env_ref="${%s}", deeplink="kiro",
        apps=("Kiro.app",), bins=("kiro", "kiro-cli"), dirs=(".kiro",),
        download="https://kiro.dev/downloads/", docs="https://kiro.dev/docs/mcp/share/",
        note="Kiro expands ${VAR} only for variables approved in its MCP settings.",
    ),
    Client(
        "antigravity", "Antigravity", "editor", ".gemini/config/mcp_config.json", remote=None,
        apps=("Antigravity.app",), bins=("agy",), dirs=(".gemini/config",),
        download="https://antigravity.google/download", docs="https://antigravity.google/docs/mcp",
    ),
    Client(
        "cline", "Cline", "editor", ".cline/data/settings/cline_mcp_settings.json", remote=None,
        bins=("cline",), dirs=(".cline",),
        download="https://cline.bot", docs="https://docs.cline.bot/mcp/configuring-mcp-servers",
    ),
    Client(
        "continue", "Continue", "editor", ".continue/config.yaml", shape="continue", remote=None,
        dirs=(".continue",), download="https://continue.dev",
        docs="https://github.com/continuedev/continue/blob/main/docs/reference.mdx",
    ),
    Client(
        "claude-code", "Claude Code", "terminal", ".claude.json", shape="typed", env_ref="${%s}",
        remote="http", cli="claude", bins=("claude",),
        download="https://claude.com/product/claude-code", docs="https://code.claude.com/docs/en/mcp",
    ),
    Client(
        "codex", "Codex CLI", "terminal", ".codex/config.toml", shape="codex", cli="codex",
        bins=("codex",), dirs=(".codex",), download="https://developers.openai.com/codex/cli",
        docs="https://learn.chatgpt.com/docs/extend/mcp?surface=cli",
    ),
    Client(
        "gemini-cli", "Gemini CLI", "terminal", ".gemini/settings.json", env_ref="${%s}",
        remote="httpUrl", cli="gemini", bins=("gemini",), dirs=(".gemini",),
        download="https://geminicli.com", docs="https://geminicli.com/docs/tools/mcp-server/",
    ),
    Client(
        "copilot-cli", "Copilot CLI", "terminal", _COPILOT, shape="copilot", env_ref="${%s}",
        remote="http", cli="copilot", bins=("copilot",), dirs=(".copilot",),
        download="https://github.com/features/copilot/cli",
        docs="https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers",
    ),
    Client(
        "opencode", "OpenCode", "terminal", ".config/opencode/opencode.json", shape="opencode",
        env_ref="{env:%s}", remote="remote", bins=("opencode",), dirs=(".config/opencode",),
        download="https://opencode.ai", docs="https://opencode.ai/docs/mcp-servers/",
    ),
    Client(
        "goose", "Goose", "other",
        {"darwin": ".config/goose/config.yaml", "linux": ".config/goose/config.yaml",
         "win32": "AppData/Roaming/Block/goose/config/config.yaml"},
        shape="goose", remote=None, apps=("Goose.app",), bins=("goose",), dirs=(".config/goose",),
        download="https://block.github.io/goose/docs/getting-started/installation",
        docs="https://goose-docs.ai/docs/guides/config-files",
    ),
    Client(
        "lm-studio", "LM Studio", "other", ".lmstudio/mcp.json", deeplink="lmstudio",
        apps=("LM Studio.app",), bins=("lms",), dirs=(".lmstudio",),
        download="https://lmstudio.ai/download", docs="https://lmstudio.ai/docs/app/mcp/deeplink",
    ),
    Client(
        "any", "Any MCP client", "other",
        docs="https://modelcontextprotocol.io/docs/develop/connect-local-servers",
        note="Paste this JSON into the client's MCP settings.",
    ),
)

BY_ID: Dict[str, Client] = {c.id: c for c in CLIENTS}


#: Substrings of the ``clientInfo.name`` each client sends on ``initialize``,
#: to match a ledger row to a catalog entry (first match wins).
SEEN_AS: Tuple[Tuple[str, str], ...] = (
    ("claude-code", "claude-code"), ("claude", "claude-desktop"), ("cursor", "cursor"),
    ("insiders", "vscode-insiders"), ("visual studio code", "vscode"), ("vscode", "vscode"),
    ("windsurf", "windsurf"), ("devin", "windsurf"), ("zed", "zed"), ("kiro", "kiro"),
    ("antigravity", "antigravity"), ("cline", "cline"), ("continue", "continue"),
    ("codex", "codex"), ("gemini", "gemini-cli"), ("copilot", "copilot-cli"),
    ("opencode", "opencode"), ("goose", "goose"), ("lm studio", "lm-studio"),
    ("lmstudio", "lm-studio"),
)


def client_for(client_name: str) -> Optional[str]:
    """The catalog id for a ``clientInfo.name`` (``None`` when unknown)."""
    low = client_name.lower()
    return next((cid for needle, cid in SEEN_AS if needle in low), None)


def get_client(client_id: str) -> Client:
    try:
        return BY_ID[client_id]
    except KeyError:
        raise KeyError(f"Unknown client {client_id!r}. Known: {', '.join(BY_ID)}") from None


def config_path(client: Client, home: Path, platform: str = sys.platform) -> Optional[Path]:
    """The client's user config file under ``home`` (``None``: nothing to write)."""
    rel = client.path
    if isinstance(rel, dict):
        rel = rel.get("win32" if platform.startswith("win") else platform, rel.get("linux"))
    return home / rel if rel else None


def file_format(client: Client) -> str:
    """``json``, ``jsonc`` (Zed allows comments), ``toml`` or ``yaml``."""
    if client.shape == "zed":
        return "jsonc"
    return _JSON_FMT.get(Path(str(client.path or "x.json")).suffix.lstrip("."), "json")


def env_values(client: Client, spec: ServerSpec) -> Dict[str, str]:
    """The env block: one reference per name, in the client's syntax."""
    if not client.env_ref:
        return {}
    return {k: client.env_ref % k for k in spec.env}


def entry(client: Client, spec: ServerSpec) -> Any:
    """One server entry in the client's own shape (a TOML/YAML-ready dict)."""
    env = env_values(client, spec)
    shape = client.shape
    if spec.url:
        if not client.remote:
            raise ValueError(f"{client.label} only runs local servers; drop --url.")
        if shape == "opencode":
            return {"type": "remote", "url": spec.url}
        if client.remote == "http":
            return {"type": "http", "url": spec.url}
        return {client.remote: spec.url}
    args = list(spec.args)
    if shape == "codex":
        out: Dict[str, Any] = {"command": spec.command, "args": args}
        if spec.env:
            out["env_vars"] = list(spec.env)
        return out
    if shape == "opencode":
        out = {"type": "local", "command": spec.argv}
        return {**out, "environment": env} if env else out
    if shape == "goose":
        return {"type": "stdio", "name": spec.name, "enabled": True, "cmd": spec.command,
                "args": args, "envs": {}, "env_keys": list(spec.env), "timeout": 300}
    if shape == "continue":
        return {"name": spec.name, "type": "stdio", "command": spec.command, "args": args}
    out = {"command": spec.command, "args": args}
    if shape == "copilot":
        out = {"type": "stdio", **out, "tools": ["*"]}
    elif shape == "typed":
        out = {"type": "stdio", **out}
    if env:
        out["env"] = env
    return out


def container_key(client: Client) -> Tuple[str, ...]:
    """Where the servers map (or list) sits in the file."""
    return {
        "zed": ("context_servers",),
        "opencode": ("mcp", "servers"),
        "codex": ("mcp_servers",),
        "goose": ("extensions",),
    }.get(client.shape, ("mcpServers",))


def deeplink(client: Client, spec: ServerSpec) -> Optional[str]:
    """The one-click install link, or ``None``."""
    kind = client.deeplink
    if not kind:
        return None
    body = entry(client, spec)
    if kind == "cursor":
        b64 = base64.b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
        return "cursor://anysphere.cursor-deeplink/mcp/install?" + urlencode(
            {"name": spec.name, "config": b64}
        )
    if kind in ("vscode", "vscode-insiders"):
        body = {"name": spec.name, **{k: v for k, v in body.items() if k != "tools"}}
        return f"{kind}:mcp/install?" + quote(json.dumps(body, separators=(",", ":")), safe="")
    if kind == "kiro":
        return "https://kiro.dev/launch/mcp/add?" + urlencode(
            {"name": spec.name, "config": json.dumps(body, separators=(",", ":"))}
        )
    if kind == "lmstudio":
        b64 = base64.b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
        return "lmstudio://add_mcp?" + urlencode({"name": spec.name, "config": b64})
    return None


def command(client: Client, spec: ServerSpec) -> Optional[str]:
    """The client's own ``add`` command, for people who prefer to run it."""
    kind = client.cli
    if not kind:
        return None
    q = shlex.join
    if spec.url:
        if kind == "claude":
            return q(["claude", "mcp", "add", "--transport", "http", "--scope", "user", spec.name, spec.url])
        if kind == "code":
            return q(["code", "--add-mcp", json.dumps({"name": spec.name, "type": "http", "url": spec.url})])
        if kind == "gemini":
            return q(["gemini", "mcp", "add", "--scope", "user", "--transport", "http", spec.name, spec.url])
        return None
    envs: List[str] = []
    if kind == "claude":
        for k in spec.env:
            envs += ["--env", f"{k}=${{{k}}}"]
        # --env goes before the other options: right before the name it would
        # read the name as one more KEY=value pair.
        return q(["claude", "mcp", "add", *envs, "--transport", "stdio", "--scope", "user", spec.name, "--", *spec.argv])
    if kind == "codex":
        return q(["codex", "mcp", "add", spec.name, "--", *spec.argv])
    if kind == "gemini":
        return q(["gemini", "mcp", "add", "--scope", "user", spec.name, *spec.argv])
    if kind == "copilot":
        return q(["copilot", "mcp", "add", spec.name, "--", *spec.argv])
    if kind == "code":
        return q(["code", "--add-mcp", json.dumps({"name": spec.name, **entry(client, spec)})])
    return None


def snippet(client: Client, spec: ServerSpec) -> str:
    """The text to paste by hand: the entry inside its container key."""
    body = entry(client, spec)
    fmt = file_format(client)
    if fmt == "toml":
        from .config_io import toml_block

        return toml_block(spec.name, body)
    if fmt == "yaml":
        import yaml

        doc = {"mcpServers": [body]} if client.shape == "continue" else {"extensions": {spec.name: body}}
        return yaml.safe_dump(doc, sort_keys=False)
    doc: Dict[str, Any] = {spec.name: body}
    for key in reversed(container_key(client)):
        doc = {key: doc}
    return json.dumps(doc, indent=2)


def export_catalog(spec: ServerSpec, home: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every client as plain JSON: what PraisonAIUI's Connect page renders."""
    home = home or Path.home()
    rows = []
    for c in CLIENTS:
        try:
            link, cmd, text = deeplink(c, spec), command(c, spec), snippet(c, spec)
        except ValueError as exc:  # a local-only client asked for a URL server
            link, cmd, text = None, None, str(exc)
        path = config_path(c, home)
        rows.append({
            "id": c.id, "label": c.label, "group": c.group,
            "deeplink": link, "command": cmd, "snippet": text,
            "config_path": str(path) if path else None,
            "env_reference": bool(c.env_ref) or c.shape == "codex",
            "download": c.download, "docs": c.docs, "note": c.note,
        })
    return rows
