"""N agents can take turns on the same thread.

PraisonAI had no N-agent conversation loop -- no round-robin, no speaker
selection -- so having agents debate meant writing the loop by hand.
repeat([a, b]) was the obvious workaround and silently misbehaved until it was
fixed, which is what made this worth building rather than documenting around.
"""
import pytest

from praisonaiagents.workflows.workflows import AgentFlow, Discussion


def _speaker(name, log, says=None):
    def handler(ctx):
        log.append(name)
        return says or f"{name} spoke"
    handler.__name__ = name
    return handler


class TestTakingTurns:
    def test_speakers_alternate_round_robin(self):
        log = []
        AgentFlow(steps=[Discussion([_speaker("a", log), _speaker("b", log)], rounds=2)]).run(
            "topic", verbose=False
        )
        assert log == ["a", "b", "a", "b"]

    def test_rounds_bounds_the_conversation(self):
        log = []
        AgentFlow(steps=[Discussion([_speaker("a", log)], rounds=3)]).run("t", verbose=False)
        assert log == ["a", "a", "a"]

    def test_each_speaker_sees_what_came_before(self):
        """The difference between a discussion and N independent answers."""
        seen = []

        def first(ctx):
            return "OPENING"

        def second(ctx):
            seen.append(ctx.previous_result)
            return "reply"

        first.__name__, second.__name__ = "first", "second"
        AgentFlow(steps=[Discussion([first, second], rounds=1)]).run("t", verbose=False)
        assert seen == ["OPENING"]

    def test_a_transcript_is_available_to_later_steps(self):
        log = []
        flow = AgentFlow(steps=[Discussion([_speaker("a", log), _speaker("b", log)], rounds=1)])
        result = flow.run("t", verbose=False)
        # run() returns the run's variables; flow.variables stays the DECLARED
        # initial state, which is what a second run would start from.
        transcript = (result.get("variables") or {}).get("discussion_transcript", "")
        assert "a:" in transcript and "b:" in transcript


class TestStopping:
    def test_until_stops_the_discussion_early(self):
        log = []
        flow = AgentFlow(steps=[
            Discussion([_speaker("a", log), _speaker("b", log, says="AGREED")], rounds=9,
                       until=lambda ctx: "AGREED" in (ctx.previous_result or ""))
        ])
        flow.run("t", verbose=False)
        assert log == ["a", "b"]

    def test_control_without_until_the_full_budget_runs(self):
        log = []
        AgentFlow(steps=[Discussion([_speaker("a", log)], rounds=4)]).run("t", verbose=False)
        assert log == ["a"] * 4

    def test_a_broken_until_is_reported_not_ignored(self):
        """Swallowing it would turn a bounded discussion into rounds of spend."""
        log = []
        def boom(ctx):
            raise KeyError("missing")
        flow = AgentFlow(steps=[Discussion([_speaker("a", log)], rounds=5, until=boom)])
        with pytest.raises(ValueError, match="until"):
            flow.run("t", verbose=False)


class TestSpeakerSelection:
    def test_a_custom_selector_chooses_who_speaks(self):
        log = []
        a, b = _speaker("a", log), _speaker("b", log)
        # Always pick the first speaker: proves selection is consulted rather
        # than round-robin being hardcoded.
        AgentFlow(steps=[Discussion([a, b], rounds=2, select=lambda turn, ctx: a)]).run(
            "t", verbose=False
        )
        assert log == ["a", "a", "a", "a"]


class TestRefusals:
    def test_an_empty_discussion_is_refused(self):
        """Zero speakers would run zero turns and report success."""
        with pytest.raises(ValueError, match="at least one speaker"):
            Discussion([], rounds=2)

    def test_zero_rounds_is_refused(self):
        with pytest.raises(ValueError, match="rounds must be"):
            Discussion([lambda ctx: "x"], rounds=0)
