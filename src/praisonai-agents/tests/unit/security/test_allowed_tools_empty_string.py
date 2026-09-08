"""An empty ALLOWED_TOOLS must not silently switch the whitelist off.

The module's own docstring says:

    ALLOWED_TOOLS unset          : all tools visible
    ALLOWED_TOOLS empty string   : error - must specify tools or unset
    ALLOWED_TOOLS with values    : only whitelisted tools visible

The middle line was not what happened. Presence was tested by truthiness:

    self.env_value = os.environ.get(primary) or os.environ.get(legacy)

so ALLOWED_TOOLS="" was falsy, fell through to the legacy variable, and ended
as None -- which _parse_whitelist reads as "unset, allow everything". The
whitelist was therefore disabled by the exact value documented as an error,
while a whitespace-only value was correctly refused. Measured before the fix:

    ALLOWED_TOOLS=""     -> allows ['read_file', 'shell', 'write_file']
    ALLOWED_TOOLS="  "   -> RAISED ValueError

`export ALLOWED_TOOLS=` and `ALLOWED_TOOLS="$SOME_UNSET_VAR"` both produce
that empty string, so this is reachable from an ordinary shell script or CI
config that meant to restrict tools and instead removed the restriction.
"""
import logging

import pytest

from praisonaiagents.allowed_tools_filter import (
    AllowedToolsFilter,
    filter_tools_with_allowed_tools,
)

TOOLS = ["read_file", "write_file", "shell"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ALLOWED_TOOLS", raising=False)
    monkeypatch.delenv("HERMES_ONLY_TOOLS", raising=False)
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def _filter():
    return sorted(filter_tools_with_allowed_tools(list(TOOLS), log_diagnostics=False))


class TestEmptyIsAnError:

    def test_an_empty_string_is_refused(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_TOOLS", "")
        with pytest.raises(ValueError):
            _filter()

    def test_it_does_not_silently_allow_everything(self, monkeypatch):
        """The security-relevant half: failing open is worse than failing."""
        monkeypatch.setenv("ALLOWED_TOOLS", "")
        try:
            allowed = _filter()
        except ValueError:
            return  # refused, which is the point
        pytest.fail(f"empty ALLOWED_TOOLS allowed {allowed}")

    def test_whitespace_is_still_refused(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_TOOLS", "   ")
        with pytest.raises(ValueError):
            _filter()

    def test_the_legacy_variable_is_refused_when_empty_too(self, monkeypatch):
        monkeypatch.setenv("HERMES_ONLY_TOOLS", "")
        with pytest.raises(ValueError):
            _filter()


class TestDocumentedBehaviourIsUnchanged:

    def test_unset_allows_every_tool(self):
        assert _filter() == sorted(TOOLS)

    def test_a_named_tool_is_the_only_one_allowed(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_TOOLS", "read_file")
        assert _filter() == ["read_file"]

    def test_a_comma_separated_list_works(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_TOOLS", "read_file, shell")
        assert _filter() == ["read_file", "shell"]

    def test_the_legacy_variable_still_works(self, monkeypatch):
        monkeypatch.setenv("HERMES_ONLY_TOOLS", "shell")
        assert _filter() == ["shell"]

    def test_the_primary_variable_wins_over_the_legacy_one(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_TOOLS", "read_file")
        monkeypatch.setenv("HERMES_ONLY_TOOLS", "shell")
        assert _filter() == ["read_file"]

    def test_the_error_names_the_variable_that_was_set(self, monkeypatch):
        """A message naming the wrong variable sends the user to the wrong line."""
        monkeypatch.setenv("HERMES_ONLY_TOOLS", "")
        with pytest.raises(ValueError, match="HERMES_ONLY_TOOLS"):
            _filter()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
