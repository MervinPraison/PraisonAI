"""Tests for AgentTeam.stream_emitter fan-in.

Verifies that a team exposes an aggregate StreamEventEmitter that forwards each
member agent's per-step events, tagged with the emitting agent's id, so a single
consumer (e.g. the CLI stream-json bridge) gets multi-agent parity.
"""


class _FakeMemberEmitter:
    """Minimal stand-in for a member agent's StreamEventEmitter."""

    def __init__(self):
        self.callbacks = []

    def add_callback(self, cb):
        self.callbacks.append(cb)

    def remove_callback(self, cb):
        if cb in self.callbacks:
            self.callbacks.remove(cb)

    def emit(self, event):
        for cb in list(self.callbacks):
            cb(event)


class _FakeAgent:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.display_name = agent_id
        self.stream_emitter = _FakeMemberEmitter()


def _make_team(agents):
    """Build a bare AgentTeam-like object exercising only the fan-in mixin.

    We avoid a full AgentTeam construction (which requires tasks/LLM config) by
    binding the real methods onto a lightweight instance that provides the two
    attributes the fan-in touches: ``agents`` and the private slots.
    """
    from praisonaiagents.agents.agents import AgentTeam

    team = AgentTeam.__new__(AgentTeam)
    team.agents = agents
    team._AgentTeam__stream_emitter = None
    team._AgentTeam__stream_fanin_wired = False
    return team


def _make_event(agent_id=None):
    from praisonaiagents.streaming.events import StreamEvent, StreamEventType
    return StreamEvent(type=StreamEventType.DELTA_TEXT, content="hi", agent_id=agent_id)


def test_team_exposes_stream_emitter():
    team = _make_team([_FakeAgent("a")])
    assert team.stream_emitter is not None
    # Idempotent: same instance returned on repeated access.
    assert team.stream_emitter is team.stream_emitter


def test_member_events_forwarded_and_tagged():
    a = _FakeAgent("researcher")
    b = _FakeAgent("writer")
    team = _make_team([a, b])

    received = []
    team.stream_emitter.add_callback(received.append)

    a.stream_emitter.emit(_make_event())
    b.stream_emitter.emit(_make_event())

    assert len(received) == 2
    assert received[0].agent_id == "researcher"
    assert received[1].agent_id == "writer"


def test_existing_agent_id_preserved():
    a = _FakeAgent("researcher")
    team = _make_team([a])
    received = []
    team.stream_emitter.add_callback(received.append)

    a.stream_emitter.emit(_make_event(agent_id="explicit"))

    assert received[0].agent_id == "explicit"


def test_fanin_wired_once():
    a = _FakeAgent("a")
    team = _make_team([a])
    _ = team.stream_emitter
    _ = team.stream_emitter
    # Only a single forwarding callback should be registered on the member.
    assert len(a.stream_emitter.callbacks) == 1
