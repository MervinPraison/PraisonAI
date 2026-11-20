"""Full-window context usage: one percent, known models only."""

import io
import json

from praisonaiagents.context.budgeter import (
    compaction_context_payload,
    context_window_usage,
    get_model_limit,
    occupancy_tokens,
    resolved_model_limit,
)


class TestResolvedModelLimit:
    def test_known_window_that_equals_the_default_still_resolves(self):
        assert resolved_model_limit("gpt-4o") == 128000
        assert resolved_model_limit("gpt-4o-2024-05-13") == 128000
        assert resolved_model_limit("GPT-4o") == 128000

    def test_unknown_model_is_not_given_the_default(self):
        assert resolved_model_limit("totally-unknown-model-xyz") is None
        assert resolved_model_limit("") is None
        assert resolved_model_limit(None) is None
        # Compaction and budgeting still have a number to fall back on.
        assert get_model_limit("totally-unknown-model-xyz") == 128000

    def test_claude_and_gemini_use_the_budgeter_table(self):
        assert resolved_model_limit("claude-3-5-sonnet") == 200000
        assert resolved_model_limit("gemini-1.5-pro") == 2097152


class TestContextWindowUsage:
    def test_percent_is_of_the_full_window(self):
        usage = context_window_usage(15234, "gpt-4o")
        assert usage == {"used": 15234, "limit": 128000, "percent": 11}

    def test_output_tokens_are_not_an_argument(self):
        # The signature has no completion-token field. A large completion
        # cannot change the percent; only the prompt count can.
        assert context_window_usage(12800, "gpt-4o")["percent"] == 10

    def test_anthropic_cache_tokens_are_added(self):
        usage = context_window_usage(
            1000,
            "claude-3-5-sonnet",
            cache_read_tokens=5000,
            cache_creation_tokens=2000,
        )
        assert usage["used"] == 8000
        assert usage["limit"] == 200000
        assert usage["percent"] == 4

    def test_openai_cached_subset_is_not_added_again(self):
        # Caller passes the prompt total only. Adding a cached subset here
        # would double-count, so the helper has no such argument.
        usage = context_window_usage(8000, "gpt-4o")
        assert usage["used"] == 8000

    def test_over_the_window_reports_past_100(self):
        usage = context_window_usage(10000, "gpt-4")
        assert usage["limit"] == 8192
        assert usage["percent"] == 122

    def test_nothing_to_report(self):
        assert context_window_usage(0, "gpt-4o") is None
        assert context_window_usage(-5, "gpt-4o") is None
        assert context_window_usage("nope", "gpt-4o") is None
        assert context_window_usage(100, "totally-unknown-model-xyz") is None

    def test_negative_cache_fields_are_ignored(self):
        usage = context_window_usage(100, "gpt-4", cache_read_tokens=-50)
        assert usage["used"] == 100


class TestOccupancyTokens:
    def test_openai_cached_subset_stays_inside_prompt_tokens(self):
        usage = {
            "prompt_tokens": 8000,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 2000},
        }
        assert occupancy_tokens(usage) == 8000

    def test_raw_anthropic_adds_the_cache_tail(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 20,
            "cache_read_input_tokens": 5000,
            "cache_creation_input_tokens": 2000,
        }
        assert occupancy_tokens(usage) == 8000

    def test_litellm_anthropic_prompt_already_includes_cache(self):
        # prompt_tokens = input tail + cache read + cache creation.
        usage = {
            "prompt_tokens": 8000,
            "input_tokens": 1000,
            "cache_read_input_tokens": 5000,
            "cache_creation_input_tokens": 2000,
        }
        assert occupancy_tokens(usage) == 8000

    def test_openai_full_count_is_not_inflated_when_cache_field_is_a_subset(self):
        usage = {
            "prompt_tokens": 8000,
            "input_tokens": 8000,
            "cache_read_input_tokens": 2000,
        }
        assert occupancy_tokens(usage) == 8000


class TestCompactionPayload:
    def test_known_model_carries_the_three_fields(self):
        payload = compaction_context_payload(15234, "gpt-4o", message_count=6)
        assert payload["context_tokens"] == 15234
        assert payload["message_count"] == 6
        assert payload["context_window_size"] == 128000
        assert payload["context_usage_percent"] == 11

    def test_unknown_model_omits_the_window(self):
        payload = compaction_context_payload(500, "totally-unknown-model-xyz", 2)
        assert payload == {"context_tokens": 500, "message_count": 2}


class TestStatusLine:
    def test_anthropic_usage_fills_the_window_without_changing_the_bill(self):
        from praisonaiagents.output.status import StatusOutput

        buf = io.StringIO()
        out = StatusOutput(file=buf, use_color=False, show_metrics=True, show_timestamps=False)
        out.llm_end(
            model="claude-3-5-sonnet",
            tokens_in=1000,
            tokens_out=20,
            usage={
                "input_tokens": 1000,
                "cache_read_input_tokens": 5000,
                "cache_creation_input_tokens": 2000,
            },
        )
        text = buf.getvalue()
        assert "1000→20" in text
        assert "context 4% (8000/200000)" in text

    def test_quiet_text_does_not_resolve_a_window(self, monkeypatch):
        import praisonaiagents.context.budgeter as budgeter
        from praisonaiagents.output.status import StatusOutput

        def explode(model):
            raise AssertionError("window lookup on the quiet path")

        monkeypatch.setattr(budgeter, "resolved_model_limit", explode)
        buf = io.StringIO()
        out = StatusOutput(file=buf, use_color=False, show_metrics=False)
        out.llm_end(model="gpt-4o", tokens_in=15234, tokens_out=20)
        assert buf.getvalue() == ""

    def test_metrics_line_appends_the_window_percent(self):
        from praisonaiagents.output.status import StatusOutput

        buf = io.StringIO()
        out = StatusOutput(file=buf, use_color=False, show_metrics=True, show_timestamps=False)
        out.llm_end(model="openai/gpt-4o", tokens_in=15234, tokens_out=20, cost=0.01)
        text = buf.getvalue()
        assert "gpt-4o: 15234→20 tokens" in text
        assert "context 11% (15234/128000)" in text

    def test_unknown_model_keeps_the_token_counts_only(self):
        from praisonaiagents.output.status import StatusOutput

        buf = io.StringIO()
        out = StatusOutput(file=buf, use_color=False, show_metrics=True)
        out.llm_end(model="totally-unknown-model-xyz", tokens_in=1000, tokens_out=10)
        text = buf.getvalue()
        assert "1000→10" in text
        assert "context " not in text
        assert "128000" not in text

    def test_quiet_agents_print_nothing(self):
        from praisonaiagents.output.status import StatusOutput

        buf = io.StringIO()
        out = StatusOutput(file=buf, use_color=False, show_metrics=False)
        out.llm_end(model="gpt-4o", tokens_in=15234, tokens_out=20)
        assert buf.getvalue() == ""

    def test_jsonl_carries_the_window_fields(self):
        from praisonaiagents.output.status import StatusOutput

        buf = io.StringIO()
        out = StatusOutput(file=buf, format="jsonl", show_metrics=False)
        out.llm_end(model="gpt-4o", tokens_in=12800, tokens_out=4)
        data = json.loads(buf.getvalue())
        assert data["context_tokens"] == 12800
        assert data["context_window_size"] == 128000
        assert data["context_usage_percent"] == 10
        assert data["tokens_out"] == 4


class TestCompactionHookReceivesPayload:
    def test_before_compaction_is_not_empty(self):
        from praisonaiagents.agent.chat_mixin import ChatMixin
        from praisonaiagents.hooks.types import HookEvent

        agent = ChatMixin.__new__(ChatMixin)
        agent.name = "tester"
        agent.llm = "gpt-4o"
        agent._strict_hooks = False
        captured = {}

        class Runner:
            def execute_sync(self, event, data):
                captured.setdefault(event, data)

        class Result:
            original_tokens = 20
            compacted_tokens = 10
            messages_removed = 1
            summary = ""

        class Compactor:
            strategy = None

            def compact(self, messages):
                return messages, Result()

        class Strategy:
            value = "truncate"

        class Policy:
            strategy = Strategy()

        agent._hook_runner = Runner()
        messages = [{"role": "user", "content": "hello world " * 50}]
        agent._apply_compaction(messages, Compactor(), Policy())

        hook_input = captured[HookEvent.BEFORE_COMPACTION]
        # Plugin hooks read to_dict(); a bare dict becomes {} in that bridge.
        assert hasattr(hook_input, "to_dict")
        assert hook_input.cwd
        payload = hook_input.to_dict()
        assert payload["context_window_size"] == 128000
        assert payload["context_tokens"] > 0
        assert payload["message_count"] == 1
        assert payload["context_usage_percent"] == payload["context_tokens"] * 100 // 128000

    def test_payload_from_the_agent_matches_the_helper(self):
        from praisonaiagents.agent.chat_mixin import ChatMixin

        agent = ChatMixin.__new__(ChatMixin)
        agent.llm = "claude-3-5-sonnet"
        messages = [{"role": "user", "content": "alpha " * 80}]
        payload = agent._compaction_hook_payload(messages).to_dict()
        assert payload["context_window_size"] == 200000
        assert payload["message_count"] == 1
        assert "context_usage_percent" in payload

        agent.llm = "totally-unknown-model-xyz"
        unknown = agent._compaction_hook_payload(messages).to_dict()
        assert "context_window_size" not in unknown
        assert unknown["context_tokens"] > 0
