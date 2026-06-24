"""
Stream event bridge for `praisonai run`.

Maps the core agent's ``StreamEventEmitter`` events (and equivalent hook
payloads) onto the CLI ``OutputController.emit_event(...)`` sink so that
``--output stream-json`` produces a stable, versioned NDJSON event stream
(one JSON object per line) describing per-step agent activity:

    {"type":"run.start", ...}
    {"type":"agent.message", ...}
    {"type":"tool.start", "tool":"edit_file", "args":{...}}
    {"type":"tool.result", "tool":"edit_file", "ok":true}
    {"type":"text.delta", "text":"..."}
    {"type":"run.result", "ok":true, "result":"..."}

Design goals:
- Zero overhead when not in a JSON/stream mode (the bridge is a no-op).
- No hard dependency on the core package at import time (lazy import).
- A small, stable canonical schema with a ``schema_version`` so external
  scripts/CI/observability tooling can depend on it.
"""

from typing import Any, Dict, Optional

# Canonical schema version for the NDJSON event stream emitted during `run`.
# Bump this when the event shape changes in a backward-incompatible way.
SCHEMA_VERSION = 1

# Canonical event type names (stable surface scripts can depend on).
EVENT_RUN_START = "run.start"
EVENT_AGENT_MESSAGE = "agent.message"
EVENT_TOOL_START = "tool.start"
EVENT_TOOL_RESULT = "tool.result"
EVENT_TOOL_ERROR = "tool.error"
EVENT_TEXT_DELTA = "text.delta"
EVENT_REASONING_DELTA = "reasoning.delta"
EVENT_RUN_RESULT = "run.result"
EVENT_RUN_ERROR = "run.error"


class StreamEventBridge:
    """Bridge core ``StreamEvent`` objects into ``OutputController`` events.

    The bridge is intentionally tolerant: it accepts the core ``StreamEvent``
    dataclass but never imports it eagerly, so it can be used even if the core
    package layout changes. Any unmapped event types are ignored.
    """

    def __init__(self, output: Any) -> None:
        self._output = output

    @property
    def active(self) -> bool:
        """Whether bridging should produce structured events at all.

        Only JSON / stream-json consumers need per-step events. In human/TTY
        modes the bridge is a no-op so existing output is unchanged.
        """
        return bool(getattr(self._output, "is_json_mode", False))

    def _emit(self, event_type: str, data: Optional[Dict[str, Any]] = None,
              agent_id: Optional[str] = None) -> None:
        if not self.active:
            return
        payload: Dict[str, Any] = {"schema_version": SCHEMA_VERSION}
        if data:
            payload.update(data)
        self._output.emit_event(event_type, data=payload, agent_id=agent_id)

    def on_stream_event(self, event: Any) -> None:
        """Callback compatible with ``StreamEventEmitter.add_callback``.

        Maps a core ``StreamEvent`` to a canonical CLI event. Exceptions are
        swallowed by the emitter, but we also guard defensively here so a
        malformed event can never break a run.
        """
        if not self.active:
            return
        try:
            type_value = self._event_type_value(event)
            agent_id = getattr(event, "agent_id", None)

            if type_value == "tool_call_start":
                tool = self._tool_info(event)
                self._emit(EVENT_TOOL_START, tool, agent_id=agent_id)
            elif type_value == "tool_call_result":
                tool = self._tool_info(event)
                tool.setdefault("ok", event.error is None if hasattr(event, "error") else True)
                self._emit(EVENT_TOOL_RESULT, tool, agent_id=agent_id)
            elif type_value == "delta_text":
                content = getattr(event, "content", None)
                if content:
                    if getattr(event, "is_reasoning", False):
                        self._emit(EVENT_REASONING_DELTA, {"text": content}, agent_id=agent_id)
                    else:
                        self._emit(EVENT_TEXT_DELTA, {"text": content}, agent_id=agent_id)
            elif type_value == "error":
                self._emit(
                    EVENT_TOOL_ERROR,
                    {"error": getattr(event, "error", None) or "unknown error"},
                    agent_id=agent_id,
                )
        except Exception:
            # Never allow observability to break the run.
            pass

    @staticmethod
    def _event_type_value(event: Any) -> Optional[str]:
        """Extract the lowercase string value of a core StreamEventType."""
        etype = getattr(event, "type", None)
        if etype is None:
            return None
        # StreamEventType is an Enum with .value, but tolerate plain strings.
        return getattr(etype, "value", etype)

    @staticmethod
    def _tool_info(event: Any) -> Dict[str, Any]:
        """Build a tool payload from a core StreamEvent's tool_call dict."""
        info: Dict[str, Any] = {}
        tool_call = getattr(event, "tool_call", None)
        if isinstance(tool_call, dict):
            name = tool_call.get("name")
            if name:
                info["tool"] = name
            args = tool_call.get("arguments", tool_call.get("args"))
            if args is not None:
                info["args"] = args
            result = tool_call.get("result")
            if result is not None:
                info["result"] = result
        return info

    # -- Run-level lifecycle helpers (driven directly by run.py) -------------

    def emit_run_start(self, data: Optional[Dict[str, Any]] = None) -> None:
        self._emit(EVENT_RUN_START, data)

    def emit_agent_message(self, agent: Optional[str] = None) -> None:
        self._emit(EVENT_AGENT_MESSAGE, {"agent": agent} if agent else None)

    def emit_run_result(self, result: Any = None, ok: bool = True) -> None:
        data: Dict[str, Any] = {"ok": ok}
        if result is not None:
            data["result"] = str(result)
        self._emit(EVENT_RUN_RESULT, data)

    def emit_run_error(self, error: str) -> None:
        self._emit(EVENT_RUN_ERROR, {"ok": False, "error": error})


def attach_bridge(agent: Any, output: Any) -> Optional[StreamEventBridge]:
    """Attach a ``StreamEventBridge`` to an agent's stream emitter.

    Returns the bridge if attached (so callers can drive run-level events and
    detach later), or ``None`` if bridging is not applicable (non-JSON mode or
    the agent has no stream emitter).
    """
    bridge = StreamEventBridge(output)
    if not bridge.active:
        return None
    emitter = getattr(agent, "stream_emitter", None)
    if emitter is None or not hasattr(emitter, "add_callback"):
        return bridge  # still usable for run-level lifecycle events
    try:
        emitter.add_callback(bridge.on_stream_event)
    except Exception:
        pass
    return bridge


def detach_bridge(agent: Any, bridge: Optional[StreamEventBridge]) -> None:
    """Remove a previously attached bridge callback from the agent."""
    if bridge is None:
        return
    emitter = getattr(agent, "stream_emitter", None)
    if emitter is not None and hasattr(emitter, "remove_callback"):
        try:
            emitter.remove_callback(bridge.on_stream_event)
        except Exception:
            pass
