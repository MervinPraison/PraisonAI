"""
TDD tests for praisonai.security.protected module.

Tests cover:
- PROTECTED_PATHS list
- is_protected() function
- Custom overrides
"""
class TestIsProtected:
    def _check(self, path, extra=None):
        from praisonai.security.protected import is_protected
        return is_protected(path, extra_protected=extra)

    def test_env_file_protected(self):
        assert self._check(".env") is True

    def test_env_local_protected(self):
        assert self._check(".env.local") is True

    def test_git_dir_protected(self):
        assert self._check(".git/config") is True

    def test_pyc_protected(self):
        assert self._check("app/__pycache__/foo.pyc") is True

    def test_praisonaiagents_package_protected(self):
        assert self._check("praisonaiagents/agent/agent.py") is True

    def test_normal_python_file_not_protected(self):
        assert self._check("src/myapp/main.py") is False

    def test_normal_text_file_not_protected(self):
        assert self._check("README.md") is False

    def test_extra_protected(self):
        assert self._check("my_secret.key", extra=["my_secret.key"]) is True

    def test_absolute_path_env(self):
        assert self._check("/home/user/project/.env") is True

    def test_node_modules_protected(self):
        assert self._check("node_modules/lodash/index.js") is True


class TestProtectedList:
    def test_protected_paths_is_frozenset(self):
        from praisonai.security.protected import PROTECTED_PATHS
        assert isinstance(PROTECTED_PATHS, frozenset)

    def test_protected_patterns_nonempty(self):
        from praisonai.security.protected import PROTECTED_PATTERNS
        assert len(PROTECTED_PATTERNS) > 0

    def test_protected_reason(self):
        from praisonai.security.protected import get_protection_reason
        reason = get_protection_reason(".env")
        assert reason is not None
        assert isinstance(reason, str)

    def test_normal_file_reason_is_none(self):
        from praisonai.security.protected import get_protection_reason
        assert get_protection_reason("src/app.py") is None
