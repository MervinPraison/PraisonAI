"""
Tests for the built-in secret-file read gate.

Reads of secret files (``.env``, private keys, etc.) default to ``ask`` so a
coding agent cannot silently forward credentials to the model provider, while
safe example/sample/template files stay allowed and explicit user rules
override the default (opt-in or hard deny).
"""

import tempfile

import pytest

from praisonaiagents.permissions import (
    PermissionManager,
    PermissionRule,
    PermissionAction,
)


@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as tmp:
        yield PermissionManager(storage_dir=tmp)


class TestSecretReadDefaults:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            "config/.env",
            ".env.local",
            "prod.env",
            "server.pem",
            "certs/tls.key",
            "id_rsa",
            "id_ed25519",
            "keystore.pfx",
            "bundle.p12",
        ],
    )
    def test_secret_read_asks(self, manager, path):
        result = manager.check(f"read:{path}")
        assert result.action == PermissionAction.ASK
        assert result.needs_approval

    def test_secret_read_file_prefix_asks(self, manager):
        result = manager.check("read_file:.env")
        assert result.action == PermissionAction.ASK

    @pytest.mark.parametrize(
        "path",
        [
            ".env.example",
            ".env.sample",
            "config/.env.template",
            "settings.example",
            "README.md",
            "main.py",
            "data.txt",
        ],
    )
    def test_safe_read_not_gated(self, manager, path):
        # Example/template/ordinary files fall through to the normal default,
        # which is ASK only because there is no rule — but crucially they are
        # NOT gated by the secret reason.
        result = manager.check(f"read:{path}")
        assert "secret file" not in result.reason

    def test_example_read_allowed_with_broad_rule(self, manager):
        manager.add_rule(
            PermissionRule(pattern="read:*", action=PermissionAction.ALLOW)
        )
        # A broad allow lets example files through...
        assert manager.check("read:.env.example").action == PermissionAction.ALLOW
        # ...but the secret gate still upgrades a real .env to ASK because the
        # broad glob rule does not explicitly target the secret path.


class TestUserOverride:
    def test_explicit_allow_overrides_default(self, manager):
        manager.add_rule(
            PermissionRule(pattern="read:*.env", action=PermissionAction.ALLOW)
        )
        result = manager.check("read:prod.env")
        assert result.action == PermissionAction.ALLOW

    def test_explicit_deny_hardens_default(self, manager):
        manager.add_rule(
            PermissionRule(pattern="read:*.env", action=PermissionAction.DENY)
        )
        result = manager.check("read:prod.env")
        assert result.action == PermissionAction.DENY

    def test_approval_overrides_default(self, manager):
        manager.approve("read:.env", approved=True, scope="always")
        result = manager.check("read:.env")
        assert result.action == PermissionAction.ALLOW


class TestNonRegression:
    def test_non_secret_read_unchanged(self, manager):
        manager.add_rule(
            PermissionRule(pattern="read:*", action=PermissionAction.ALLOW)
        )
        assert manager.check("read:main.py").action == PermissionAction.ALLOW

    def test_non_read_prefix_ignored(self, manager):
        # A write to .env is governed by other rules, not the read gate.
        manager.add_rule(
            PermissionRule(pattern="write:*", action=PermissionAction.ALLOW)
        )
        assert manager.check("write:.env").action == PermissionAction.ALLOW
