"""One builder turns any MCP server config entry into an ``MCP`` client.

``parse_mcp_servers`` reads the config shapes other tools write (Claude Code,
Cursor, VS Code, Gemini CLI, Codex, PraisonAI YAML) into one entry shape, and
``MCP.from_config`` builds a client from one entry.
"""

from unittest.mock import patch

import pytest

from praisonaiagents.mcp import MCP, parse_mcp_servers


# --- parse_mcp_servers: container keys ---------------------------------------

@pytest.mark.parametrize("key", ["mcpServers", "servers", "mcp_servers"])
def test_container_keys(key):
    out = parse_mcp_servers({key: {"fs": {"command": "npx", "args": ["-y", "fs"]}}})
    assert out == {"fs": {"command": "npx", "args": ["-y", "fs"], "type": "stdio"}}


def test_nested_mcp_servers_key():
    out = parse_mcp_servers({"mcp": {"servers": {"gh": {"url": "https://x.dev/mcp"}}}})
    assert out == {"gh": {"url": "https://x.dev/mcp", "type": "http"}}


def test_bare_mapping_and_string_entry():
    out = parse_mcp_servers({"fs": "npx -y fs"})
    assert out == {"fs": {"command": "npx -y fs", "type": "stdio"}}


def test_none_and_empty():
    assert parse_mcp_servers(None) == {}
    assert parse_mcp_servers({}) == {}


# --- parse_mcp_servers: field aliases ----------------------------------------

def test_gemini_http_url_and_tool_lists():
    out = parse_mcp_servers({"mcpServers": {"g": {
        "httpUrl": "https://x.dev/mcp", "includeTools": ["a"], "excludeTools": ["b"],
    }}})
    assert out["g"] == {"url": "https://x.dev/mcp", "type": "http",
                        "allowed_tools": ["a"], "disabled_tools": ["b"]}


@pytest.mark.parametrize("alias", ["enabled_tools", "include_tools", "tool_filter"])
def test_allowed_tools_aliases(alias):
    out = parse_mcp_servers({"s": {"command": "x", alias: ["t"]}})
    assert out["s"]["allowed_tools"] == ["t"]


def test_codex_bearer_and_http_headers():
    out = parse_mcp_servers({"mcp_servers": {"c": {
        "url": "https://x.dev/mcp", "bearer_token_env_var": "TOK",
        "http_headers": {"X-A": "1"},
    }}})
    assert out["c"]["headers"] == {"X-A": "1", "Authorization": "Bearer ${TOK}"}


def test_server_url_alias_and_ws_type():
    out = parse_mcp_servers({"s": {"server_url": "wss://x.dev/mcp"}})
    assert out["s"] == {"url": "wss://x.dev/mcp", "type": "ws"}


def test_oauth_shapes():
    claude = parse_mcp_servers({"a": {"url": "https://x.dev/mcp",
                                      "oauth": {"clientId": "id1", "scopes": ["r"]}}})
    cursor = parse_mcp_servers({"a": {"url": "https://x.dev/mcp",
                                      "auth": {"CLIENT_ID": "id1", "scopes": ["r"]}}})
    assert claude["a"]["oauth"] == cursor["a"]["oauth"] == {"client_id": "id1", "scopes": ["r"]}
    scopes_only = parse_mcp_servers({"a": {"url": "https://x.dev/mcp", "oauth": {"scopes": ["r"]}}})
    assert scopes_only["a"]["oauth"] == {"scopes": ["r"]}
    flag = parse_mcp_servers({"a": {"url": "https://x.dev/mcp", "oauth": True}})
    assert flag["a"]["oauth"] is True


def test_explicit_type_kept_and_aliases():
    assert parse_mcp_servers({"s": {"type": "sse", "url": "https://x/m"}})["s"]["type"] == "sse"
    assert parse_mcp_servers({"s": {"type": "local", "command": "x"}})["s"]["type"] == "stdio"
    assert parse_mcp_servers({"s": {"type": "remote", "url": "https://x/m"}})["s"]["type"] == "http"


def test_unknown_field_warns_and_is_dropped(caplog):
    with caplog.at_level("WARNING"):
        out = parse_mcp_servers({"s": {"command": "x", "colour": "red"}})
    assert "colour" not in out["s"]
    assert "colour" in caplog.text


def test_entry_without_command_or_url_is_rejected():
    with pytest.raises(ValueError, match="command.*url"):
        parse_mcp_servers({"s": {"args": ["a"]}})


def test_does_not_mutate_input():
    data = {"mcpServers": {"s": {"httpUrl": "https://x/m"}}}
    parse_mcp_servers(data)
    assert data == {"mcpServers": {"s": {"httpUrl": "https://x/m"}}}


# --- MCP.from_config ----------------------------------------------------------

class _Recorder:
    """Records what ``MCP.__init__`` was called with (no server is started)."""


def _build(entry, **opts):
    rec = _Recorder()

    def fake_init(self, target=None, args=None, **kw):
        rec.target, rec.args, rec.kw = target, args, kw

    with patch.object(MCP, "__init__", fake_init):
        MCP.from_config(entry, **opts)
    return rec


def test_from_config_stdio(monkeypatch):
    monkeypatch.setenv("FS_ROOT", "/data")
    rec = _build({"command": "npx", "args": ["-y", "fs", "${FS_ROOT}"],
                  "env": {"K": "${env:FS_ROOT}"}, "timeout": 30,
                  "allowed_tools": ["read"], "enabled": True}, expand_env=True)
    assert rec.target == "npx"
    assert rec.args == ["-y", "fs", "/data"]
    assert rec.kw == {"env": {"K": "/data"}, "timeout": 30, "allowed_tools": ["read"]}


def test_from_config_http_headers_expanded(monkeypatch):
    monkeypatch.setenv("TOK", "s3cret")
    rec = _build({"url": "https://x.dev/mcp", "headers": {"Authorization": "Bearer ${TOK}"}},
                 expand_env=True)
    assert rec.target == "https://x.dev/mcp"
    assert rec.kw == {"headers": {"Authorization": "Bearer s3cret"}}


def test_from_config_accepts_raw_aliases():
    rec = _build({"httpUrl": "https://x.dev/mcp", "excludeTools": ["rm"]})
    assert rec.target == "https://x.dev/mcp"
    assert rec.kw == {"disabled_tools": ["rm"]}


def test_from_config_timeout_ms():
    assert _build({"command": "x", "timeout": 30000}).kw["timeout"] == 30


def test_from_config_default_value(monkeypatch):
    monkeypatch.delenv("NOPE_VAR", raising=False)
    assert _build({"command": "x", "args": ["${NOPE_VAR:-fallback}"]}, expand_env=True).args == ["fallback"]


def test_from_config_missing_var_fails_fast(monkeypatch):
    monkeypatch.delenv("NOPE_VAR", raising=False)
    with pytest.raises(ValueError, match="NOPE_VAR"):
        _build({"command": "x", "args": ["${NOPE_VAR}"]}, expand_env=True)


def test_from_config_bad_url_never_runs_as_command():
    with pytest.raises(ValueError, match="url"):
        _build({"url": "rm -rf /"})


def test_from_config_does_not_write_env_back(monkeypatch):
    monkeypatch.setenv("TOK", "s3cret")
    entry = {"url": "https://x.dev/mcp", "headers": {"Authorization": "Bearer ${TOK}"}}
    _build(entry, expand_env=True)
    assert entry["headers"]["Authorization"] == "Bearer ${TOK}"


def test_default_passes_variables_through_literally(monkeypatch):
    """Expansion is opt-in: callers whose loader already interpolated must not
    expand a second time."""
    monkeypatch.setenv("TOK", "s3cret")
    rec = _build({"url": "https://x.dev/mcp", "headers": {"X": "${TOK}", "Y": "${env:TOK}"}})
    assert rec.kw["headers"] == {"X": "${TOK}", "Y": "${env:TOK}"}
    rec = _build({"command": "x", "args": ["${TOK}"], "env": {"K": "${TOK}"}})
    assert rec.args == ["${TOK}"] and rec.kw["env"] == {"K": "${TOK}"}


def test_default_missing_variable_does_not_raise(monkeypatch):
    monkeypatch.delenv("NOPE_VAR", raising=False)
    assert _build({"command": "x", "args": ["${NOPE_VAR}"]}).args == ["${NOPE_VAR}"]


def test_parse_mcp_servers_not_a_root_export():
    import praisonaiagents

    assert "parse_mcp_servers" not in getattr(praisonaiagents, "__all__", [])


# --- review fixes: disabled servers, SSE headers, quiet editor fields ---------

def test_disabled_true_means_enabled_false():
    out = parse_mcp_servers({"mcpServers": {"s": {"command": "x", "disabled": True}}})
    assert out["s"]["enabled"] is False and "disabled" not in out["s"]
    assert "enabled" not in parse_mcp_servers({"s": {"command": "x", "disabled": False}})["s"]


@pytest.mark.parametrize("entry", [{"command": "x", "enabled": False},
                                   {"command": "x", "disabled": True}])
def test_from_config_refuses_disabled_server(entry):
    with pytest.raises(ValueError, match="'s' is disabled"):
        MCP.from_config(entry, name="s")


def test_sse_authorization_header_is_refused():
    with pytest.raises(ValueError, match="SSE"):
        _build({"url": "https://x.dev/sse/", "headers": {"Authorization": "Bearer t"}})


def test_sse_other_headers_warn_and_are_dropped(caplog):
    with caplog.at_level("WARNING"):
        rec = _build({"url": "https://x.dev/sse", "headers": {"X-A": "1"}})
    assert "headers" not in rec.kw
    assert "SSE" in caplog.text


@pytest.mark.parametrize("field", ["name", "description", "trust", "alwaysAllow",
                                   "autoApprove", "startup_timeout_sec"])
def test_known_editor_fields_are_quiet(field, caplog):
    with caplog.at_level("WARNING"):
        out = parse_mcp_servers({"s": {"command": "x", field: 1}})
    assert field not in out["s"]
    assert caplog.text == ""


@pytest.mark.parametrize("transport,kind", [("stdio", "stdio"), ("sse", "sse"),
                                            ("streamable_http", "http"), ("streamable-http", "http"),
                                            ("http", "http"), ("websocket", "ws")])
def test_transport_maps_to_type(transport, kind):
    assert parse_mcp_servers({"s": {"url": "https://x/m", "transport": transport}})["s"]["type"] == kind


def test_codex_tool_timeout_sec():
    assert _build({"command": "x", "tool_timeout_sec": 45}).kw["timeout"] == 45


def test_bearer_with_null_headers():
    out = parse_mcp_servers({"s": {"url": "https://x/m", "headers": None, "bearer_token_env_var": "T"}})
    assert out["s"]["headers"] == {"Authorization": "Bearer ${T}"}


def test_timeout_1000_is_milliseconds():
    assert _build({"command": "x", "timeout": 1000}).kw["timeout"] == 1


def test_from_config_command_as_list():
    rec = _build({"command": ["npx", "-y", "pkg"], "args": ["/tmp"]})
    assert rec.target == "npx"
    assert rec.args == ["-y", "pkg", "/tmp"]
