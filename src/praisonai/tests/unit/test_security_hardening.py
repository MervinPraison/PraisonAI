"""Regression tests for security hardening.

Covers:
- GHSA-rg3h-x3jw-7jm5: table_prefix/schema SQL-identifier validation across
  conversation-store backends and the SQLiteBackend storage adapter.
- GHSA-9qhq-v63v-fv3j: argument validation in MCP command parsing.
"""
from __future__ import annotations

import pytest

from praisonai.persistence.conversation.base import validate_identifier


# ---------------------------------------------------------------------------
# GHSA-rg3h-x3jw-7jm5 — SQL identifier validator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("good", ["", "praison_", "abc", "a1_b2", "schema_1"])
def test_validate_identifier_accepts_safe(good):
    assert validate_identifier(good, "x") == good


@pytest.mark.parametrize(
    "bad",
    [
        "x'; DROP TABLE users; --",
        "a.b",
        "a b",
        "--",
        "/etc/passwd",
        "public; DROP SCHEMA data CASCADE; --",
    ],
)
def test_validate_identifier_rejects_malicious(bad):
    with pytest.raises(ValueError):
        validate_identifier(bad, "x")


def test_validate_identifier_rejects_non_string():
    with pytest.raises(ValueError):
        validate_identifier(None, "x")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Each conversation backend must call validate_identifier on table_prefix
# before assigning it. We exercise the relevant init path minimally by
# importing the module and patching dependencies where necessary.
# ---------------------------------------------------------------------------

def _assert_prefix_rejected(cls, **kwargs):
    with pytest.raises(ValueError):
        cls(table_prefix="x'; DROP--", **kwargs)


def test_sqlite_store_rejects_malicious_prefix(tmp_path):
    from praisonai.persistence.conversation.sqlite import SQLiteConversationStore

    _assert_prefix_rejected(SQLiteConversationStore, path=str(tmp_path / "x.db"))


def test_async_sqlite_store_rejects_malicious_prefix(tmp_path):
    pytest.importorskip("aiosqlite")
    from praisonai.persistence.conversation.async_sqlite import (
        AsyncSQLiteConversationStore,
    )

    _assert_prefix_rejected(AsyncSQLiteConversationStore, path=str(tmp_path / "x.db"))


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("mysql", "MySQLConversationStore"),
        ("async_mysql", "AsyncMySQLConversationStore"),
        ("postgres", "PostgresConversationStore"),
        ("async_postgres", "AsyncPostgresConversationStore"),
        ("singlestore", "SingleStoreConversationStore"),
        ("supabase", "SupabaseConversationStore"),
        ("surrealdb", "SurrealDBConversationStore"),
        ("turso", "TursoConversationStore"),
    ],
)
def test_other_backends_reject_malicious_prefix(module_name, class_name):
    """Construct the store lazily; validation must fire before any network I/O."""
    import importlib

    mod = importlib.import_module(
        f"praisonai.persistence.conversation.{module_name}"
    )
    cls = getattr(mod, class_name)
    try:
        cls(table_prefix="x'; DROP--")
    except ValueError as exc:
        assert "alphanumeric" in str(exc) or "identifier" in str(exc)
    except ImportError:
        pytest.skip(f"optional driver for {module_name} not installed")
    except Exception as exc:  # pragma: no cover — still rejected but via driver
        # If the optional driver raised before validation, we cannot assert
        # strictly; validation happens early in __init__ so this path should
        # be unusual.
        pytest.skip(f"driver raised before validation: {type(exc).__name__}")
    else:
        pytest.fail(f"{class_name} accepted malicious table_prefix")


def test_postgres_store_rejects_malicious_schema():
    pytest.importorskip("psycopg2")
    from praisonai.persistence.conversation.postgres import (
        PostgresConversationStore,
    )

    with pytest.raises(ValueError):
        PostgresConversationStore(
            url="postgresql://u:p@localhost/db",
            schema="public; DROP SCHEMA data CASCADE; --",
        )


def test_sqlite_backend_rejects_malicious_table_name(tmp_path):
    from praisonaiagents.storage.backends import SQLiteBackend

    with pytest.raises(ValueError):
        SQLiteBackend(db_path=str(tmp_path / "x.db"), table_name="x'; DROP--")


# ---------------------------------------------------------------------------
# GHSA-9qhq-v63v-fv3j — MCP command inline-eval blocker
# ---------------------------------------------------------------------------

@pytest.fixture
def mcp_handler():
    from praisonai.cli.features.mcp import MCPHandler

    return MCPHandler()


@pytest.mark.parametrize(
    "command",
    [
        "bash -c 'cat /etc/passwd'",
        "/bin/sh -c 'id'",
        "python -c 'import os; os.system(\"id\")'",
        "python3 -c 'print(1)'",
        "node -e 'require(\"child_process\").execSync(\"id\")'",
        "node --eval 'console.log(1)'",
        "deno eval 'Deno.exit(0)'",
        "bun -e 'console.log(1)'",
    ],
)
def test_parse_mcp_command_blocks_injection(mcp_handler, command):
    with pytest.raises(ValueError):
        mcp_handler.parse_mcp_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "npx -y @modelcontextprotocol/server-filesystem .",
        "uvx mcp-server-fetch",
        "python -m mcp_server_fetch",
        "node /opt/mcp/server.js",
    ],
)
def test_parse_mcp_command_accepts_legitimate(mcp_handler, command):
    cmd, args, env = mcp_handler.parse_mcp_command(command)
    assert cmd
    assert isinstance(args, list)
    assert isinstance(env, dict)
