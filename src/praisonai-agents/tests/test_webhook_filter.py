"""Unit tests for the declarative webhook filter (Issue #3580).

Covers the pure, import-light core matcher that a generic webhook channel uses
to decide, from configuration alone, whether an inbound HTTP event triggers an
agent. No I/O, no HTTP — just predicate-tree semantics and fail-safe behaviour.
"""

from praisonaiagents.bots import (
    WebhookFilter,
    evaluate_webhook_filter,
    resolve_field,
)


def _event():
    return {
        "payload": {
            "action": "opened",
            "issue": {"number": 42, "title": "Bug: crash on start"},
            "labels": ["bug", "urgent"],
        },
        "headers": {"X-GitHub-Event": "issues", "Content-Type": "application/json"},
        "query": {"debug": "1"},
    }


class TestResolveField:
    def test_dotted_path(self):
        assert resolve_field(_event(), "payload.issue.number") == 42
        assert resolve_field(_event(), "payload.issue.title") == "Bug: crash on start"

    def test_header_case_insensitive(self):
        assert resolve_field(_event(), "headers.x-github-event") == "issues"
        assert resolve_field(_event(), "headers.X-GitHub-Event") == "issues"

    def test_missing_path_returns_none(self):
        assert resolve_field(_event(), "payload.nope.deep") is None
        assert resolve_field(_event(), "") is None


class TestLeafOperators:
    def test_equals(self):
        assert evaluate_webhook_filter(
            _event(), {"field": "payload.action", "equals": "opened"}
        )
        assert not evaluate_webhook_filter(
            _event(), {"field": "payload.action", "equals": "closed"}
        )

    def test_in(self):
        assert evaluate_webhook_filter(
            _event(), {"field": "payload.action", "in": ["opened", "reopened"]}
        )
        assert not evaluate_webhook_filter(
            _event(), {"field": "payload.action", "in": ["closed"]}
        )

    def test_contains(self):
        assert evaluate_webhook_filter(
            _event(), {"field": "payload.labels", "contains": "urgent"}
        )
        assert evaluate_webhook_filter(
            _event(), {"field": "payload.issue.title", "contains": "crash"}
        )
        assert not evaluate_webhook_filter(
            _event(), {"field": "payload.labels", "contains": "nope"}
        )

    def test_exists(self):
        assert evaluate_webhook_filter(
            _event(), {"field": "payload.issue", "exists": True}
        )
        assert evaluate_webhook_filter(
            _event(), {"field": "payload.missing", "exists": False}
        )
        assert not evaluate_webhook_filter(
            _event(), {"field": "payload.missing", "exists": True}
        )

    def test_regex(self):
        assert evaluate_webhook_filter(
            _event(), {"field": "headers.X-GitHub-Event", "regex": "^iss"}
        )
        assert not evaluate_webhook_filter(
            _event(), {"field": "payload.action", "regex": "^clos"}
        )

    def test_bare_field_is_existence(self):
        assert evaluate_webhook_filter(_event(), {"field": "payload.action"})
        assert not evaluate_webhook_filter(_event(), {"field": "payload.nope"})


class TestCombinators:
    def test_all(self):
        node = {
            "all": [
                {"field": "headers.X-GitHub-Event", "equals": "issues"},
                {"field": "payload.action", "in": ["opened", "reopened"]},
            ]
        }
        assert evaluate_webhook_filter(_event(), node)
        # One clause fails → whole AND fails.
        node["all"][1]["in"] = ["closed"]
        assert not evaluate_webhook_filter(_event(), node)

    def test_any(self):
        node = {
            "any": [
                {"field": "payload.action", "equals": "closed"},
                {"field": "payload.action", "equals": "opened"},
            ]
        }
        assert evaluate_webhook_filter(_event(), node)

    def test_not(self):
        assert evaluate_webhook_filter(
            _event(), {"not": {"field": "payload.action", "equals": "closed"}}
        )
        assert not evaluate_webhook_filter(
            _event(), {"not": {"field": "payload.action", "equals": "opened"}}
        )

    def test_empty_all_is_true_empty_any_is_false(self):
        assert evaluate_webhook_filter(_event(), {"all": []})
        assert not evaluate_webhook_filter(_event(), {"any": []})


class TestCatchAllAndFailSafe:
    def test_none_and_empty_match_everything(self):
        assert evaluate_webhook_filter(_event(), None)
        assert evaluate_webhook_filter(_event(), {})

    def test_malformed_node_fails_closed(self):
        # Unrecognised structure → False, never raises.
        assert not evaluate_webhook_filter(_event(), {"bogus": 1})
        assert not evaluate_webhook_filter(_event(), 123)


class TestWebhookFilterClass:
    def test_matches(self):
        f = WebhookFilter(
            {
                "all": [
                    {"field": "headers.X-GitHub-Event", "equals": "issues"},
                    {"field": "payload.action", "in": ["opened", "reopened"]},
                ]
            }
        )
        assert f.matches(_event())

    def test_catch_all(self):
        assert WebhookFilter().matches(_event())
        assert WebhookFilter(None).matches(_event())
