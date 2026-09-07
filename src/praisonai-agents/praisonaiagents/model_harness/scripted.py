"""A scriptable model double for offline agent tests.

:class:`ScriptedModel` stands in for a real provider so a unit test can assert
what an agent *does* -- "given this user turn, it calls ``refund()`` and then
stops" -- in milliseconds, with no network, no API key and no ``unittest.mock``
patching of provider internals.

It is a real :class:`~praisonaiagents.llm.llm.LLM` subclass that replaces the
methods which talk to a provider and nothing else, so everything around the
call is the production code path: the system prompt is assembled normally,
tools are serialised to real schemas, scripted tool calls are dispatched
through the agent's own executor, and results are fed back as real tool
messages. Replies are built as genuine litellm response objects, so they are
parsed by the same code a live response would be.

Basic use::

    from praisonaiagents import Agent
    from praisonaiagents.model_harness import ScriptedModel

    model = ScriptedModel(["Paris."])
    agent = Agent(instructions="You are a geography bot.", llm=model)

    assert agent.start("What is the capital of France?") == "Paris."
    assert model.requests[0].last_user_message == "What is the capital of France?"

Scripting a tool call followed by a final answer::

    model = ScriptedModel([
        ScriptedModel.tool_call("refund", {"order_id": "A1"}),
        "Refunded order A1.",
    ])
    agent = Agent(instructions="Support bot.", llm=model, tools=[refund])

    assert agent.start("refund order A1") == "Refunded order A1."
    assert model.request_count == 2  # tool turn, then the follow-up

A script entry may also be a callable, which receives the
:class:`RecordedRequest` and returns a reply -- useful for replies that depend
on what the agent actually sent::

    model = ScriptedModel([lambda req: f"You said: {req.last_user_message}"])

When the agent asks for one more reply than the script holds, the double raises
:class:`ScriptExhausted` rather than hanging, looping or inventing an answer.
"""

from __future__ import annotations

import itertools
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from ..llm.llm import LLM

__all__ = [
    "ScriptedModelError",
    "ScriptExhausted",
    "ScriptedToolCall",
    "ScriptedReply",
    "RecordedRequest",
    "ScriptedModel",
]


class ScriptedModelError(BaseException):
    """Base class for failures of the double itself.

    Derives from ``BaseException`` deliberately. The agent's tool loop catches
    ``Exception`` broadly and converts failures into a ``None`` answer, so an
    ordinary exception raised from inside the double would reach the test as a
    mysterious ``None`` -- hiding the very thing the test needs to be told.
    """


class ScriptExhausted(ScriptedModelError):
    """Raised when an agent asks a :class:`ScriptedModel` for an unscripted reply.

    Usually means the script is one reply short: after a tool call the agent
    comes back for a follow-up answer.

    Attributes:
        model: The double's model id.
        request_index: 1-based index of the request that had no scripted reply.
        scripted: How many replies the script held.
    """

    def __init__(self, message: str, *, model: str, request_index: int, scripted: int):
        self.model = model
        self.request_index = request_index
        self.scripted = scripted
        super().__init__(message)


@dataclass(frozen=True)
class ScriptedToolCall:
    """One tool call the double should emit.

    Attributes:
        name: Tool function name, matching a tool given to the agent.
        arguments: Arguments dict; serialised to JSON exactly as a provider would.
        id: Optional tool-call id. Generated when omitted.
    """

    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


@dataclass(frozen=True)
class ScriptedReply:
    """One assistant turn the double should return.

    Attributes:
        text: Assistant message content, or ``None`` for a pure tool-call turn.
        tool_calls: Tool calls to emit alongside/instead of ``text``.
        finish_reason: Overrides the finish reason ("tool_calls" when the turn
            has tool calls, otherwise "stop").
        usage: Optional ``{"prompt_tokens": .., "completion_tokens": ..}`` to
            report, for tests that assert on token accounting.
    """

    text: Optional[str] = None
    tool_calls: Tuple[ScriptedToolCall, ...] = ()
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None

    @property
    def resolved_finish_reason(self) -> str:
        """The finish reason to report for this turn."""
        if self.finish_reason:
            return self.finish_reason
        return "tool_calls" if self.tool_calls else "stop"


@dataclass(frozen=True)
class RecordedRequest:
    """What the agent actually sent to the model on one turn.

    Attributes:
        model: Model id the request named.
        messages: The full message list, system prompt first.
        tools: Tool schemas offered on this turn, or ``None``.
        stream: Whether the agent asked for a streaming response.
        params: Every completion parameter the agent actually sent, for
            assertions on ``tool_choice``, ``response_format``, ``temperature``
            and the like. Parameters left unset never appear.
    """

    model: str
    messages: Tuple[Dict[str, Any], ...]
    tools: Optional[Tuple[Dict[str, Any], ...]]
    stream: bool
    params: Dict[str, Any]

    @property
    def system_prompt(self) -> Optional[str]:
        """Content of the first system message, or ``None`` if there was none."""
        for message in self.messages:
            if message.get("role") == "system":
                return message.get("content")
        return None

    @property
    def user_messages(self) -> Tuple[str, ...]:
        """Text content of every user message, in order."""
        return tuple(
            m.get("content")
            for m in self.messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        )

    @property
    def last_user_message(self) -> Optional[str]:
        """Text of the most recent user message, or ``None``."""
        users = self.user_messages
        return users[-1] if users else None

    @property
    def tool_names(self) -> Tuple[str, ...]:
        """Names of the tools offered to the model on this turn."""
        if not self.tools:
            return ()
        names = []
        for tool in self.tools:
            function = tool.get("function") if isinstance(tool, dict) else None
            if isinstance(function, dict) and function.get("name"):
                names.append(function["name"])
        return tuple(names)

    @property
    def tool_results(self) -> Tuple[Dict[str, Any], ...]:
        """Tool-result messages present in this request's history."""
        return tuple(m for m in self.messages if m.get("role") == "tool")


# A script entry: literal reply, or a callable computing one from the request.
ScriptEntry = Union[
    str,
    ScriptedReply,
    ScriptedToolCall,
    Sequence[ScriptedToolCall],
    Dict[str, Any],
    Callable[[RecordedRequest], Union[str, "ScriptedReply"]],
]


def _coerce_reply(entry: Any) -> ScriptedReply:
    """Normalise a script entry's literal value into a :class:`ScriptedReply`."""
    if isinstance(entry, ScriptedReply):
        return entry
    if isinstance(entry, str):
        return ScriptedReply(text=entry)
    if isinstance(entry, ScriptedToolCall):
        return ScriptedReply(tool_calls=(entry,))
    if isinstance(entry, dict):
        calls = entry.get("tool_calls") or ()
        return ScriptedReply(
            text=entry.get("text", entry.get("content")),
            tool_calls=tuple(_coerce_tool_call(c) for c in calls),
            finish_reason=entry.get("finish_reason"),
            usage=entry.get("usage"),
        )
    if isinstance(entry, (list, tuple)):
        return ScriptedReply(tool_calls=tuple(_coerce_tool_call(c) for c in entry))
    raise TypeError(
        f"ScriptedModel cannot use {entry!r} as a reply. Use a str, a ScriptedReply, "
        "a ScriptedModel.tool_call(...), a list of tool calls, or a callable "
        "taking the RecordedRequest."
    )


def _validated(script: Iterable[Any]) -> List[Any]:
    """Copy a script, failing now on any entry that cannot become a reply.

    Callables are only checkable when they run, so they pass through; every
    literal is coerced immediately so a typo raises at the ``ScriptedModel(...)``
    line rather than several agent turns later.
    """
    entries = list(script)
    for position, entry in enumerate(entries, start=1):
        if callable(entry) and not isinstance(entry, (ScriptedReply, ScriptedToolCall)):
            continue
        try:
            _coerce_reply(entry)
        except TypeError as exc:
            raise TypeError(f"Script entry #{position} is unusable. {exc}") from exc
    return entries


def _coerce_tool_call(value: Any) -> ScriptedToolCall:
    """Normalise a tool-call entry into a :class:`ScriptedToolCall`."""
    if isinstance(value, ScriptedToolCall):
        return value
    if isinstance(value, dict):
        if "function" in value:  # already OpenAI-shaped
            function = value["function"]
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments) if arguments else {}
            return ScriptedToolCall(
                name=function["name"], arguments=arguments, id=value.get("id")
            )
        return ScriptedToolCall(
            name=value["name"], arguments=value.get("arguments", {}), id=value.get("id")
        )
    raise TypeError(f"ScriptedModel cannot use {value!r} as a tool call.")


class ScriptedModel(LLM):
    """A model double that returns scripted replies in order and records requests.

    Pass one to an agent in place of a model name::

        model = ScriptedModel(["done"])
        agent = Agent(instructions="...", llm=model)

    Args:
        script: Replies to return, in order. Each entry may be a ``str`` (a
            final answer), a :class:`ScriptedReply`, a
            :meth:`ScriptedModel.tool_call` result, a list of tool calls, or a
            callable receiving the :class:`RecordedRequest`.
        model: Model id to report. Defaults to ``"scripted/model"``. Set a real
            id (e.g. ``"gpt-4o"``) to exercise model-specific behaviour while
            still answering from the script.
        **llm_kwargs: Forwarded to :class:`~praisonaiagents.llm.llm.LLM`.

    Attributes:
        requests: Every :class:`RecordedRequest` the agent has sent, in order.
    """

    def __init__(
        self,
        script: Iterable[ScriptEntry] = (),
        *,
        model: str = "scripted/model",
        **llm_kwargs: Any,
    ):
        super().__init__(model=model, **llm_kwargs)
        self._script: List[ScriptEntry] = _validated(script)
        self._requests: List[RecordedRequest] = []
        self._cursor = 0
        self._script_lock = threading.RLock()
        self._id_counter = itertools.count(1)

    # ---- scripting ------------------------------------------------------

    @staticmethod
    def tool_call(
        name: str, arguments: Optional[Dict[str, Any]] = None, *, id: Optional[str] = None
    ) -> ScriptedReply:
        """Script a turn in which the model calls one tool.

        Args:
            name: Tool function name.
            arguments: Arguments to call it with.
            id: Optional tool-call id; generated when omitted.

        Returns:
            A :class:`ScriptedReply` to put in the script.
        """
        return ScriptedReply(
            tool_calls=(ScriptedToolCall(name=name, arguments=dict(arguments or {}), id=id),)
        )

    @staticmethod
    def tool_calls(*calls: Union[ScriptedToolCall, Dict[str, Any]]) -> ScriptedReply:
        """Script a turn in which the model calls several tools at once.

        Args:
            *calls: :class:`ScriptedToolCall` values (or equivalent dicts).

        Returns:
            A :class:`ScriptedReply` carrying all of them.
        """
        return ScriptedReply(tool_calls=tuple(_coerce_tool_call(c) for c in calls))

    @staticmethod
    def text(content: str) -> ScriptedReply:
        """Script a plain assistant answer (the same as a bare ``str`` entry)."""
        return ScriptedReply(text=content)

    def extend(self, script: Iterable[ScriptEntry]) -> "ScriptedModel":
        """Append more replies to the script. Returns ``self`` for chaining.

        Raises:
            TypeError: If an entry cannot be used as a reply.
        """
        entries = _validated(script)
        with self._script_lock:
            self._script.extend(entries)
        return self

    def reset(self) -> None:
        """Rewind to the start of the script and forget recorded requests.

        Generated tool-call ids restart too, so a re-run is byte-identical.
        """
        with self._script_lock:
            self._cursor = 0
            self._requests.clear()
            self._id_counter = itertools.count(1)

    # ---- inspection -----------------------------------------------------

    @property
    def requests(self) -> Tuple[RecordedRequest, ...]:
        """Every request the agent has sent to this double, in order."""
        with self._script_lock:
            return tuple(self._requests)

    @property
    def request_count(self) -> int:
        """How many requests the agent has sent."""
        with self._script_lock:
            return len(self._requests)

    @property
    def remaining(self) -> int:
        """How many scripted replies are still unused."""
        with self._script_lock:
            return max(0, len(self._script) - self._cursor)

    @property
    def exhausted(self) -> bool:
        """Whether every scripted reply has been consumed."""
        return self.remaining == 0

    # ---- provider replacement -------------------------------------------

    def _record(self, params: Dict[str, Any]) -> RecordedRequest:
        """Record one outgoing request and return its :class:`RecordedRequest`.

        The message list is snapshotted, not referenced: the tool loop keeps
        appending to the same list, so a live reference would make every
        recorded turn look identical to the last one.
        """
        tools = params.get("tools")
        messages = tuple(params.get("messages") or ())
        snapshot = dict(params)
        snapshot["messages"] = list(messages)
        request = RecordedRequest(
            model=params.get("model", self.model),
            messages=messages,
            tools=tuple(tools) if tools else None,
            stream=bool(params.get("stream")),
            params=snapshot,
        )
        with self._script_lock:
            self._requests.append(request)
        return request

    def _next_reply(self, request: RecordedRequest) -> ScriptedReply:
        """Take the next scripted reply, or raise :class:`ScriptExhausted`."""
        with self._script_lock:
            index = self._cursor
            scripted = len(self._script)
            if index >= scripted:
                raise ScriptExhausted(
                    self._exhausted_message(index, scripted, request),
                    model=self.model,
                    request_index=index + 1,
                    scripted=scripted,
                )
            self._cursor = index + 1
            entry = self._script[index]
        if callable(entry) and not isinstance(entry, (ScriptedReply, ScriptedToolCall)):
            entry = entry(request)
        try:
            return _coerce_reply(entry)
        except TypeError as exc:
            # A callable's return value is only checkable here, and a plain
            # TypeError would be swallowed by the agent's tool loop.
            raise ScriptedModelError(
                f"Script entry #{index + 1} returned something unusable. {exc}"
            ) from exc

    def _exhausted_message(
        self, index: int, scripted: int, request: RecordedRequest
    ) -> str:
        """Explain what the agent asked for and how to extend the script."""
        last = request.messages[-1] if request.messages else {}
        role = last.get("role", "?")
        content = last.get("content")
        if isinstance(content, str) and len(content) > 120:
            content = content[:117] + "..."
        return (
            f"ScriptedModel(model={self.model!r}) ran out of scripted replies: the agent "
            f"asked for reply #{index + 1} but the script holds {scripted}.\n"
            f"The unanswered request ended with a {role!r} message: {content!r}.\n"
            "The agent is still mid-loop (a tool result usually needs a follow-up "
            "answer) -- add another entry to the script."
        )

    def _build_response(self, reply: ScriptedReply) -> Any:
        """Build a provider-shaped, non-streaming response for ``reply``.

        Uses litellm's own response types so the double exercises exactly the
        parsing code a real response would.
        """
        from litellm import Choices, Message, ModelResponse, Usage

        message_kwargs: Dict[str, Any] = {"content": reply.text, "role": "assistant"}
        if reply.tool_calls:
            message_kwargs["tool_calls"] = [
                self._tool_call_payload(call) for call in reply.tool_calls
            ]
        response_kwargs: Dict[str, Any] = {
            "id": f"scripted-{len(self._requests)}",
            "model": self.model,
            "choices": [
                Choices(
                    finish_reason=reply.resolved_finish_reason,
                    index=0,
                    message=Message(**message_kwargs),
                )
            ],
        }
        if reply.usage:
            usage = dict(reply.usage)
            usage.setdefault(
                "total_tokens",
                usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            )
            response_kwargs["usage"] = Usage(**usage)
        return ModelResponse(**response_kwargs)

    def _tool_call_payload(self, call: ScriptedToolCall) -> Dict[str, Any]:
        """Serialise one scripted tool call the way a provider would."""
        return {
            "id": call.id or f"scripted_tool_{next(self._id_counter)}",
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": json.dumps(call.arguments or {}),
            },
        }

    def _stream_chunks(self, reply: ScriptedReply) -> List[Any]:
        """Split ``reply`` into streaming chunks shaped like provider deltas."""
        from litellm import ModelResponseStream, StreamingChoices
        from litellm.types.utils import ChatCompletionDeltaToolCall, Delta, Function

        chunks: List[Any] = []
        chunk_id = f"scripted-{len(self._requests)}"

        def emit(delta: Any, finish_reason: Optional[str] = None) -> None:
            chunks.append(
                ModelResponseStream(
                    id=chunk_id,
                    model=self.model,
                    choices=[
                        StreamingChoices(index=0, delta=delta, finish_reason=finish_reason)
                    ],
                )
            )

        if reply.text:
            emit(Delta(role="assistant", content=reply.text))
        for index, call in enumerate(reply.tool_calls):
            payload = self._tool_call_payload(call)
            emit(
                Delta(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ChatCompletionDeltaToolCall(
                            id=payload["id"],
                            index=index,
                            type="function",
                            function=Function(
                                name=call.name,
                                arguments=payload["function"]["arguments"],
                            ),
                        )
                    ],
                )
            )
        if not chunks:  # an empty reply still terminates the stream
            emit(Delta(role="assistant", content=""))
        chunks[-1].choices[0].finish_reason = reply.resolved_finish_reason
        return chunks

    def _completion_with_retry(self, **completion_params: Any) -> Any:
        """Answer from the script instead of calling a provider (sync)."""
        request = self._record(completion_params)
        reply = self._next_reply(request)
        if completion_params.get("stream"):
            return iter(self._stream_chunks(reply))
        response = self._build_response(reply)
        if reply.usage:
            try:
                self._track_token_usage(response, self.model)
            except Exception:  # pragma: no cover - accounting must never fail a test
                pass
        return response

    async def _acompletion_with_retry(self, **completion_params: Any) -> Any:
        """Answer from the script instead of calling a provider (async)."""
        request = self._record(completion_params)
        reply = self._next_reply(request)
        if completion_params.get("stream"):
            return self._astream_chunks(reply)
        response = self._build_response(reply)
        if reply.usage:
            try:
                self._track_token_usage(response, self.model)
            except Exception:  # pragma: no cover - accounting must never fail a test
                pass
        return response

    async def _astream_chunks(self, reply: ScriptedReply) -> Any:
        """Async counterpart of :meth:`_stream_chunks`."""
        for chunk in self._stream_chunks(reply):
            yield chunk

    def _supports_streaming_tools(self) -> bool:
        """Scripted tool calls arrive in stream deltas, so always accept them."""
        return True

    def _supports_responses_api(self) -> bool:
        """Always answer through the Chat Completions path.

        ``LLM`` routes OpenAI models to litellm's Responses API instead of
        Chat Completions. Since a script is written in Chat Completions terms,
        pinning this to ``False`` keeps ``ScriptedModel(model="gpt-4o")``
        answering from the script rather than reaching for a provider.
        """
        return False

    def __repr__(self) -> str:
        return (
            f"ScriptedModel(model={self.model!r}, scripted={len(self._script)}, "
            f"used={self._cursor}, requests={len(self._requests)})"
        )
