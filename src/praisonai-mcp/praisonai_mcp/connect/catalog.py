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
from dataclasses import dataclass
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
    deeplink: Optional[str] = None  # cursor | vscode(-insiders) | kiro | lmstudio | trae | goose | raycast | claude-connector
    cli: Optional[str] = None  # claude | codex | gemini | copilot | code | opencode | cline | amp
    apps: Tuple[str, ...] = ()
    bins: Tuple[str, ...] = ()
    dirs: Tuple[str, ...] = ()
    download: str = ""
    docs: str = ""
    note: str = ""
    #: Most tools the client takes (TRAE 40 in all, VS Code 128 per request).
    max_tools: Optional[int] = None
    #: Connects from the vendor's cloud: needs a public https URL, never localhost.
    cloud: bool = False


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
        remote="http", deeplink="vscode", cli="code", max_tools=128,
        apps=("Visual Studio Code.app",), bins=("code",),
        download="https://code.visualstudio.com/download",
        docs="https://code.visualstudio.com/docs/copilot/reference/mcp-configuration",
    ),
    Client(
        "vscode-insiders", "VS Code Insiders", "editor", _COPILOT, shape="copilot",
        env_ref="${%s}", remote="http", deeplink="vscode-insiders", max_tools=128,
        apps=("Visual Studio Code - Insiders.app",), bins=("code-insiders",),
        download="https://code.visualstudio.com/insiders/",
        docs="https://code.visualstudio.com/docs/copilot/reference/mcp-configuration",
    ),
    Client(
        "windsurf", "Devin Desktop (Windsurf)", "editor",
        {"darwin": ".config/devin/mcp_config.json", "linux": ".config/devin/mcp_config.json",
         "win32": "AppData/Roaming/devin/mcp_config.json"},
        env_ref="${env:%s}", remote="devin",
        apps=("Devin.app", "Windsurf.app"), bins=("devin", "windsurf"), dirs=(".config/devin", ".codeium/windsurf"),
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
        remote=None, deeplink="claude-connector", cloud=True, apps=("Claude.app",),
        dirs=("Library/Application Support/Claude", ".config/Claude", "AppData/Roaming/Claude"),
        download="https://claude.ai/download",
        docs="https://modelcontextprotocol.io/docs/develop/connect-local-servers",
        note="Restart Claude Desktop to load the server. A remote server is added as a claude.ai "
             "connector instead; it reaches the server from Anthropic's cloud, so it needs a public https URL.",
    ),
    Client(
        "zed", "Zed", "editor",
        {"darwin": ".config/zed/settings.json", "linux": ".config/zed/settings.json",
         "win32": "AppData/Roaming/Zed/settings.json"},
        shape="zed",
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
        "antigravity", "Antigravity", "editor", ".gemini/config/mcp_config.json", remote="serverUrl",
        apps=("Antigravity IDE.app", "Antigravity.app"), bins=("agy",), dirs=(".gemini/config",),
        download="https://antigravity.google/download", docs="https://antigravity.google/docs/mcp",
    ),
    Client(
        "trae", "TRAE", "editor",
        {"darwin": "Library/Application Support/Trae/User/mcp.json",
         "linux": ".config/Trae/User/mcp.json", "win32": "AppData/Roaming/Trae/User/mcp.json"},
        deeplink="trae", max_tools=40, apps=("Trae.app",),
        dirs=("Library/Application Support/Trae", ".config/Trae", "AppData/Roaming/Trae"),
        download="https://www.trae.ai/download", docs="https://docs.trae.ai/ide/mcp-server-install-links",
        note="TRAE reads at most 40 tools across all servers: scope with --tools.",
    ),
    Client(
        "junie", "JetBrains Junie", "editor", ".junie/mcp/mcp.json", bins=("junie",), dirs=(".junie",),
        download="https://junie.jetbrains.com",
        docs="https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html",
    ),
    Client(
        "cline", "Cline", "editor", ".cline/data/settings/cline_mcp_settings.json", remote="cline",
        cli="cline", bins=("cline",), dirs=(".cline",),
        download="https://cline.bot", docs="https://docs.cline.bot/mcp/configuring-mcp-servers",
    ),
    Client(
        "continue", "Continue", "editor", ".continue/mcpServers/praisonai.json", remote="http",
        dirs=(".continue",), download="https://continue.dev",
        docs="https://github.com/continuedev/continue/blob/main/docs/reference.mdx",
    ),
    Client(
        "claude-code", "Claude Code", "terminal", ".claude.json", shape="typed", env_ref="${%s}",
        remote="http", cli="claude", bins=("claude",),
        download="https://claude.com/product/claude-code", docs="https://code.claude.com/docs/en/mcp",
    ),
    Client(
        "codex", "Codex", "terminal", ".codex/config.toml", shape="codex", cli="codex",
        apps=("Codex.app", "ChatGPT.app"), bins=("codex",), dirs=(".codex",), download="https://developers.openai.com/codex/cli",
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
        env_ref="{env:%s}", remote="remote", cli="opencode", bins=("opencode",), dirs=(".config/opencode",),
        download="https://opencode.ai", docs="https://opencode.ai/docs/mcp-servers/",
    ),
    Client(
        "goose", "Goose", "other",
        {"darwin": ".config/goose/config.yaml", "linux": ".config/goose/config.yaml",
         "win32": "AppData/Roaming/Block/goose/config/config.yaml"},
        shape="goose", remote="goose", deeplink="goose", apps=("Goose.app",), bins=("goose",),
        dirs=(".config/goose",),
        download="https://block.github.io/goose/docs/getting-started/installation",
        docs="https://goose-docs.ai/docs/guides/config-files",
    ),
    Client(
        "amp", "Amp", "terminal", ".config/amp/settings.json", shape="amp", env_ref="${%s}", cli="amp",
        bins=("amp",), dirs=(".config/amp",), download="https://ampcode.com",
        docs="https://ampcode.com/docs/customize/mcp",
    ),
    Client(
        "raycast", "Raycast", "other", deeplink="raycast", remote=None, apps=("Raycast.app",),
        download="https://www.raycast.com", docs="https://manual.raycast.com/v1/model-context-protocol",
        note="Raycast → Install Server also fills itself from this JSON on the clipboard.",
    ),
    Client(
        "chatgpt", "ChatGPT", "other", cloud=True,
        download="https://chatgpt.com", docs="https://platform.openai.com/docs/guides/developer-mode",
        note="Settings → Apps & Connectors → Create (developer mode). ChatGPT connects from OpenAI's "
             "cloud: the URL must be public https (a tunnel works), never localhost.",
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
    ("antigravity", "antigravity"), ("trae", "trae"), ("junie", "junie"), ("cline", "cline"), ("continue", "continue"),
    ("codex", "codex"), ("gemini", "gemini-cli"), ("copilot", "copilot-cli"),
    ("opencode", "opencode"), ("goose", "goose"), ("amp", "amp"), ("raycast", "raycast"),
    ("chatgpt", "chatgpt"), ("openai-mcp", "chatgpt"), ("lm studio", "lm-studio"),
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
        if client.id == "chatgpt":
            return {"name": spec.name, "url": spec.url}
        if not client.remote:
            raise ValueError(f"{client.label} only runs local servers; drop --url.")
        if shape == "opencode":
            return {"type": "remote", "url": spec.url, "enabled": True}
        if client.remote == "cline":  # no type means SSE in Cline
            return {"type": "streamableHttp", "url": spec.url}
        if client.remote == "goose":
            return {"type": "streamable_http", "name": spec.name, "enabled": True, "uri": spec.url,
                    "envs": {}, "env_keys": [], "headers": {}, "timeout": 300}
        if client.remote == "http":
            return {"type": "http", "url": spec.url}
        if client.remote == "devin":
            return {"url": spec.url, "transport": "http"}
        return {client.remote: spec.url}
    if client.cloud and client.path is None:
        raise ValueError(f"{client.label} reaches servers from its cloud: serve over HTTP at a public https URL.")
    args = list(spec.args)
    if shape == "codex":
        out: Dict[str, Any] = {"command": spec.command, "args": args}
        if spec.env:
            out["env_vars"] = list(spec.env)
        return out
    if shape == "opencode":  # the V1 shape, which V2 also reads
        out = {"type": "local", "command": spec.argv, "enabled": True}
        return {**out, "environment": env} if env else out
    if shape == "goose":
        return {"type": "stdio", "name": spec.name, "enabled": True, "cmd": spec.command,
                "args": args, "envs": {}, "env_keys": list(spec.env), "timeout": 300}
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
        "opencode": ("mcp",),
        "amp": ("amp.mcpServers",),
        "codex": ("mcp_servers",),
        "goose": ("extensions",),
    }.get(client.shape, ("mcpServers",))


def deeplink(client: Client, spec: ServerSpec) -> Optional[str]:
    """The one-click install link, or ``None``."""
    kind = client.deeplink
    if not kind:
        return None
    if kind == "claude-connector":  # remote only; syncs to Desktop, mobile and Claude Code
        if not spec.url:
            return None
        return "https://claude.ai/customize/connectors?" + urlencode(
            {"modal": "add-custom-connector", "connectorName": spec.name, "connectorUrl": spec.url}
        )
    if kind == "goose":
        if spec.url:
            return "goose://extension?" + urlencode(
                {"url": spec.url, "type": "streamable_http", "id": spec.name, "name": spec.name}
            )
        return None  # a stdio link may only run npx/uvx/docker/…: the config file is written instead
    if kind == "raycast":
        if spec.url:
            return None
        cfg = {"name": spec.name, "type": "stdio", "command": spec.command, "args": list(spec.args)}
        return "raycast://mcp/install?" + quote(json.dumps(cfg, separators=(",", ":")), safe="")
    body = entry(client, spec)
    compact = json.dumps(body, separators=(",", ":"))
    b64 = base64.b64encode(compact.encode()).decode()
    if kind == "cursor":
        # urlencode turns "+" into %2B: Cursor's URLSearchParams would read it as a space.
        link = "cursor://anysphere.cursor-deeplink/mcp/install?" + urlencode({"name": spec.name, "config": b64})
        return link if len(link) <= 10_000 else None  # Cursor's deep-link cap
    if kind in ("vscode", "vscode-insiders"):
        return f"{kind}:mcp/install?" + quote(json.dumps(_vscode_editor_entry(spec), separators=(",", ":")), safe="")
    if kind == "trae":
        return "trae://trae.ai-ide/mcp-import?" + urlencode(
            {"type": "http" if spec.url else "stdio", "name": spec.name, "config": b64}
        )
    if kind == "kiro":
        return "https://kiro.dev/launch/mcp/add?" + urlencode({"name": spec.name, "config": compact})
    if kind == "lmstudio":
        return "lmstudio://add_mcp?" + urlencode({"name": spec.name, "config": b64})
    return None


def _vscode_editor_entry(spec: ServerSpec) -> Dict[str, Any]:
    """VS Code's link and ``code --add-mcp`` write its editor-format config,
    which spells env references ``${env:NAME}`` (the Copilot file: ``${NAME}``)."""
    if spec.url:
        return {"name": spec.name, "type": "http", "url": spec.url}
    out: Dict[str, Any] = {"name": spec.name, "type": "stdio", "command": spec.command, "args": list(spec.args)}
    if spec.env:
        out["env"] = {k: "${env:%s}" % k for k in spec.env}
    return out


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
            return q(["code", "--add-mcp", json.dumps(_vscode_editor_entry(spec))])
        if kind == "gemini":
            return q(["gemini", "mcp", "add", "--scope", "user", "--transport", "http", spec.name, spec.url])
        if kind in ("codex", "opencode"):
            return q([kind, "mcp", "add", spec.name, "--url", spec.url])
        if kind == "cline":
            return q(["cline", "mcp", "add", spec.name, spec.url, "--transport", "http", "--yes"])
        if kind == "amp":
            return q(["amp", "mcp", "add", spec.name, spec.url])
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
    if kind in ("copilot", "amp"):
        return q([kind, "mcp", "add", spec.name, "--", *spec.argv])
    if kind == "cline":
        return q(["cline", "mcp", "add", spec.name, "--yes", "--", *spec.argv])
    if kind == "opencode":
        return q(["opencode", "mcp", "add", spec.name, "--global", "--", *spec.argv])
    if kind == "code":
        return q(["code", "--add-mcp", json.dumps(_vscode_editor_entry(spec))])
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

        return yaml.safe_dump({"extensions": {spec.name: body}}, sort_keys=False)
    if client.id == "chatgpt":
        return f"Name: {spec.name}\nMCP server URL: {spec.url}\nAuthentication: OAuth (or none)"
    doc: Dict[str, Any] = {spec.name: body}
    for key in reversed(container_key(client)):
        doc = {key: doc}
    return json.dumps(doc, indent=2)


def export_catalog(spec: ServerSpec, home: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every client as plain JSON: what PraisonAIUI's Connect page renders."""
    home = home or Path.home()
    rows = []
    def safe(fn, c):
        try:
            return fn(c, spec)
        except ValueError as exc:  # e.g. a local-only client asked for a URL server
            return exc

    for c in CLIENTS:
        link, cmd, text = (safe(fn, c) for fn in (deeplink, command, snippet))
        link = None if isinstance(link, ValueError) else link
        cmd = None if isinstance(cmd, ValueError) else cmd
        text = str(text)
        path = config_path(c, home)
        rows.append({
            "id": c.id, "label": c.label, "group": c.group,
            "deeplink": link, "command": cmd, "snippet": text,
            "config_path": str(path) if path else None,
            "env_reference": bool(c.env_ref) or c.shape == "codex",
            "download": c.download, "docs": c.docs, "note": c.note, "max_tools": c.max_tools,
            "cloud": c.cloud,
        })
    return rows
