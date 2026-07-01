"""
Mixins for bot protocol implementations.

ChatCommandMixin — ``register_command`` / ``list_commands`` (DRY).
MessageHookMixin — fire MESSAGE_RECEIVED / MESSAGE_SENDING / MESSAGE_SENT hooks (DRY).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set

from praisonaiagents.bots import ChatCommandInfo

logger = logging.getLogger(__name__)


class ChatCommandMixin:
    """Mixin that satisfies the ChatCommandProtocol interface.

    Expects the host class to have ``_command_handlers: Dict[str, Callable]``.

    Channel-specific command filtering:
        Pass ``channels=["telegram", "discord"]`` to ``register_command``
        to restrict a command to specific platforms.  If *channels* is
        empty/None the command is available everywhere.
    """

    _command_info: Dict[str, ChatCommandInfo]
    _command_channels: Dict[str, Set[str]]

    def register_command(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        usage: Optional[str] = None,
        channels: Optional[List[str]] = None,
    ) -> None:
        """Register a chat command handler (ChatCommandProtocol).

        Args:
            name: Command name (without /).
            handler: Callable to invoke.
            description: Human-readable description.
            usage: Usage string shown in help.
            channels: Optional list of platform names this command is
                restricted to (e.g. ``["telegram", "slack"]``).
                ``None`` or ``[]`` means available on all platforms.
        """
        self._command_handlers[name] = handler  # type: ignore[attr-defined]
        if not hasattr(self, '_command_info'):
            self._command_info = {}
        if not hasattr(self, '_command_channels'):
            self._command_channels = {}
        self._command_info[name] = ChatCommandInfo(
            name=name, description=description, usage=usage
        )
        if channels:
            self._command_channels[name] = {c.lower() for c in channels}

    def list_commands(self, platform: Optional[str] = None) -> list:
        """List all registered chat commands (ChatCommandProtocol).

        Args:
            platform: If provided, only return commands available on
                this platform.  Builtins are always returned.
        """
        builtin_names = {"status", "new", "help", "stop"}
        builtins = [
            ChatCommandInfo(name="status", description="Show bot status and info"),
            ChatCommandInfo(name="new", description="Reset conversation session"),
            ChatCommandInfo(name="help", description="Show this help message"),
            ChatCommandInfo(name="stop", description="Cancel current agent task"),
        ]
        custom_all = getattr(self, '_command_info', {})
        channels_map = getattr(self, '_command_channels', {})
        if platform:
            plat = platform.lower()
            custom = [
                info for name, info in custom_all.items()
                if name not in builtin_names and (name not in channels_map or plat in channels_map[name])
            ]
        else:
            custom = [
                info for name, info in custom_all.items()
                if name not in builtin_names
            ]
        return builtins + custom

    def is_command_allowed(self, name: str, platform: Optional[str] = None) -> bool:
        """Check if a command is allowed on the given platform."""
        channels_map = getattr(self, '_command_channels', {})
        if name not in channels_map:
            return True  # No restriction
        if not platform:
            return True
        return platform.lower() in channels_map[name]


class MessageHookMixin:
    """Mixin that fires MESSAGE_RECEIVED / MESSAGE_SENDING / MESSAGE_SENT hooks.

    All bot adapters inherit this so hook wiring is DRY.
    Expects the host class to have:
      - ``platform`` (str property)
      - ``_agent`` (optional Agent with hook_runner)

    Zero overhead when no hooks are registered — all attribute access
    is guarded by ``getattr`` checks.
    """

    def _get_hook_runner(self) -> Any:
        """Resolve the HookRunner from the agent, if available."""
        agent = getattr(self, '_agent', None)
        if agent is None:
            return None
        return getattr(agent, '_hook_runner', None)

    def _note_inbound(self) -> None:
        """Record a passive inbound transport event.

        Called on every inbound update/frame/poll batch so channel health can
        be driven by whether messages are actually still flowing in, not only
        by whether an outbound probe succeeds. Refreshing this timestamp keeps
        a reachable-but-deaf channel from being reported HEALTHY forever.
        """
        self._last_inbound_activity = time.time()

    def _note_run_progress(self) -> None:
        """Record in-run progress (tool/stream/token/heartbeat) for liveness.

        Inbound activity (``_note_inbound``) only fires when a *new* message
        arrives, so it never advances during a single long agent turn. Channel
        health would therefore mistake an actively-streaming 30-minute run for a
        hung one once its wall-clock crosses ``stuck_after`` and restart it
        mid-run. Refreshing this timestamp on real run progress lets the health
        evaluator keep such a run BUSY (never restarted) while still flagging a
        genuinely-wedged run that emits nothing for ``stuck_after`` as STUCK.
        """
        self._last_run_progress = time.time()

    def _resolve_run_progress(self) -> Optional[float]:
        """Best-effort latest in-run progress timestamp for this adapter.

        Prefers an adapter-local ``_last_run_progress`` (set by
        ``_note_run_progress``) and falls back to the session's own
        ``last_run_progress`` so adapters that drive runs purely through
        ``BotSessionManager`` still report in-run liveness without extra wiring.
        Returns ``None`` when no progress has been recorded.
        """
        candidates = [getattr(self, '_last_run_progress', None)]
        session = getattr(self, '_session', None)
        if session is None:
            session = getattr(self, '_session_mgr', None)
        if session is not None:
            getter = getattr(session, 'last_run_progress', None)
            if callable(getter):
                try:
                    candidates.append(getter())
                except Exception:  # noqa: BLE001 — health must never raise
                    pass
        ts = [c for c in candidates if c is not None]
        return max(ts) if ts else None

    def _active_run_count(self) -> int:
        """Best-effort count of in-flight agent turns for this adapter.

        Resolves the session from ``_session`` or ``_session_mgr`` so adapters
        that name the attribute differently (e.g. WhatsApp/Linear use
        ``_session_mgr``) all report active runs DRY-ly.
        """
        session = getattr(self, '_session', None)
        if session is None:
            session = getattr(self, '_session_mgr', None)
        if session is None:
            return 0
        getter = getattr(session, 'get_active_runs', None)
        if callable(getter):
            try:
                return len(getter())
            except Exception:  # noqa: BLE001 — health must never raise
                return 0
        active = getattr(session, '_active_runs', None)
        if isinstance(active, dict):
            return len(active)
        return 0

    async def _default_health(self) -> Any:
        """Build a :class:`HealthResult` shared by all bot adapters (DRY).

        Combines ``self.probe()`` liveness with ``self._is_running``,
        ``self._started_at`` and ``self._session``. The only per-adapter
        difference is ``self.platform``, which each adapter already exposes.
        Adapters delegate via ``health()`` but may override for bespoke needs.
        """
        from praisonaiagents.bots import HealthResult

        probe_result = await self.probe()  # type: ignore[attr-defined]
        started_at = getattr(self, '_started_at', None)
        uptime = (time.time() - started_at) if started_at else None
        session = getattr(self, '_session', None)
        if session is not None and hasattr(session, '_histories'):
            session_count = len(session._histories)
        elif session is not None and hasattr(session, 'active_count'):
            session_count = session.active_count()
        else:
            session_count = 0
        is_running = getattr(self, '_is_running', False)
        # Seed inbound liveness from start time so a reachable-but-deaf channel
        # that never received an inbound message is still subject to the
        # stale-socket check (rather than reported HEALTHY forever). Subsequent
        # inbound traffic refreshes this via ``_note_inbound``.
        last_inbound = getattr(self, '_last_inbound_activity', None)
        if last_inbound is None:
            last_inbound = started_at
        return HealthResult(
            ok=is_running and probe_result.ok,
            platform=self.platform,  # type: ignore[attr-defined]
            is_running=is_running,
            uptime_seconds=uptime,
            probe=probe_result,
            sessions=session_count,
            error=probe_result.error if not probe_result.ok else None,
            last_activity=last_inbound,
            last_run_progress=self._resolve_run_progress(),
            active_runs=self._active_run_count(),
        )

    def fire_message_received(self, message: Any) -> None:
        """Fire MESSAGE_RECEIVED hook when an incoming message arrives.

        Args:
            message: A BotMessage instance.
        """
        # Passive inbound liveness: refresh on every inbound message so the
        # health monitor can detect a deaf-but-reachable channel even when the
        # outbound probe keeps passing.
        self._note_inbound()
        runner = self._get_hook_runner()
        if runner is None:
            return
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageReceivedInput

            platform = getattr(self, 'platform', 'unknown')
            sender = getattr(message, 'sender', None)
            channel = getattr(message, 'channel', None)
            content = getattr(message, 'content', '')
            if not isinstance(content, str):
                content = str(content)

            event_input = MessageReceivedInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_RECEIVED,
                timestamp=str(time.time()),
                agent_name=getattr(getattr(self, '_agent', None), 'agent_name', 'bot'),
                platform=platform,
                content=content,
                sender_id=getattr(sender, 'user_id', '') if sender else '',
                channel_id=getattr(channel, 'channel_id', '') if channel else '',
                channel_type=getattr(channel, 'channel_type', '') if channel else '',
                message_id=getattr(message, 'message_id', ''),
            )
            runner.execute_sync(HookEvent.MESSAGE_RECEIVED, event_input)
        except Exception as e:
            logger.debug(f"MESSAGE_RECEIVED hook error (non-fatal): {e}")

    def fire_message_sending(
        self, channel_id: str, content: str, reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fire MESSAGE_SENDING hook before sending a message.

        Hooks can modify content or cancel the send.

        Returns:
            dict with keys ``content`` (possibly modified) and ``cancel`` (bool).
        """
        # Check for intentional silence first (if enabled)
        if getattr(self, '_allow_silence', False):
            custom_token = getattr(self.config, 'silence_token', None) if hasattr(self, 'config') else None
            try:
                from praisonaiagents.bots.silence import is_intentional_silence_response, SILENT_REPLY_TOKEN
                # Check against custom token if configured, otherwise use default
                if custom_token:
                    # Exact match for custom token
                    if content and content.strip() == custom_token:
                        return {"content": "", "cancel": True, "silent": True}
                else:
                    # Use default silence detection
                    if is_intentional_silence_response(content):
                        return {"content": "", "cancel": True, "silent": True}
            except ImportError:
                # Fallback if core module not available
                if custom_token and content and content.strip() == custom_token:
                    return {"content": "", "cancel": True, "silent": True}
                if content and content.strip() == "NO_REPLY":
                    return {"content": "", "cancel": True, "silent": True}
        
        result: Dict[str, Any] = {"content": content, "cancel": False}
        runner = self._get_hook_runner()
        if runner is None:
            return result
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageSendingInput

            platform = getattr(self, 'platform', 'unknown')
            event_input = MessageSendingInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_SENDING,
                timestamp=str(time.time()),
                agent_name=getattr(getattr(self, '_agent', None), 'agent_name', 'bot'),
                platform=platform,
                content=content,
                channel_id=channel_id,
                reply_to=reply_to,
            )
            hook_results = runner.execute_sync(HookEvent.MESSAGE_SENDING, event_input)
            if runner.is_blocked(hook_results):
                result["cancel"] = True
                return result
            # Check for modified content in results
            if hook_results:
                for hr in hook_results:
                    output = getattr(hr, 'output', None)
                    if output is not None:
                        modified = getattr(output, 'modified_data', None)
                        if isinstance(modified, dict) and 'content' in modified:
                            result["content"] = modified["content"]
        except Exception as e:
            logger.debug(f"MESSAGE_SENDING hook error (non-fatal): {e}")
        return result

    def fire_message_sent(
        self, channel_id: str, content: str, message_id: str = ""
    ) -> None:
        """Fire MESSAGE_SENT hook after a message was successfully sent.

        Args:
            channel_id: The channel the message was sent to.
            content: The sent content.
            message_id: Platform message ID of the sent message.
        """
        runner = self._get_hook_runner()
        if runner is None:
            return
        try:
            from praisonaiagents.hooks.types import HookEvent
            from praisonaiagents.hooks.events import MessageSentInput

            platform = getattr(self, 'platform', 'unknown')
            event_input = MessageSentInput(
                session_id="",
                cwd=os.getcwd(),
                event_name=HookEvent.MESSAGE_SENT,
                timestamp=str(time.time()),
                agent_name=getattr(getattr(self, '_agent', None), 'agent_name', 'bot'),
                platform=platform,
                content=content,
                channel_id=channel_id,
                message_id=message_id,
            )
            runner.execute_sync(HookEvent.MESSAGE_SENT, event_input)
        except Exception as e:
            logger.debug(f"MESSAGE_SENT hook error (non-fatal): {e}")


def _resolve_runner_from_agent(agent: Any) -> Any:
    """Resolve the HookRunner from an agent instance, if available."""
    if agent is None:
        return None
    return getattr(agent, '_hook_runner', None)


# Strong references to in-flight fire-and-forget hook tasks. Without this the
# event loop only holds a weak reference and the task may be garbage-collected
# before it completes (see asyncio.create_task docs).
_PENDING_HOOK_TASKS: Set[Any] = set()


def _on_hook_task_done(task: Any) -> None:
    """Drop the finished task and log any swallowed coroutine exception."""
    _PENDING_HOOK_TASKS.discard(task)
    try:
        exc = task.exception()
    except Exception:  # noqa: BLE001 — cancelled or loop teardown; nothing to log
        return
    if exc is not None:
        logger.debug(f"hook task error (non-fatal): {exc}")


def _emit(runner: Any, event: Any, input_data: Any) -> None:
    """Dispatch a hook event, working in both sync and async contexts.

    ``HookRunner.execute_sync`` raises inside a running event loop, so when
    one is detected we schedule the async ``execute`` coroutine as a
    fire-and-forget task instead.  Outside a loop we use ``execute_sync``.
    Always best-effort — never raises to the caller.
    """
    if runner is None:
        return
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop is not None and loop.is_running():
            # Fire-and-forget inside a running loop, but keep a strong
            # reference until completion so the task is not GC'd mid-flight,
            # and surface any coroutine exception via a done callback.
            task = loop.create_task(runner.execute(event, input_data))
            _PENDING_HOOK_TASKS.add(task)
            task.add_done_callback(_on_hook_task_done)
        else:
            runner.execute_sync(event, input_data)
    except Exception as e:  # noqa: BLE001 — best-effort: hooks must never break the runtime
        logger.debug(f"hook emit error for {event} (non-fatal): {e}")


def fire_gateway_start(runner: Any, platforms: List[str], agent_name: str = "gateway") -> None:
    """Fire GATEWAY_START hook when a gateway/BotOS starts.

    Args:
        runner: The HookRunner (or None — no-op).
        platforms: Platform names the gateway is starting.
        agent_name: Name to attach to the event.
    """
    if runner is None:
        return
    try:
        from praisonaiagents.hooks.types import HookEvent
        from praisonaiagents.hooks.events import GatewayStartInput

        event_input = GatewayStartInput(
            session_id="",
            cwd=os.getcwd(),
            event_name=HookEvent.GATEWAY_START,
            timestamp=str(time.time()),
            agent_name=agent_name,
            platforms=list(platforms),
            bot_count=len(platforms),
        )
        _emit(runner, HookEvent.GATEWAY_START, event_input)
    except Exception as e:
        logger.debug(f"GATEWAY_START hook error (non-fatal): {e}")


def fire_gateway_stop(
    runner: Any, platforms: List[str], agent_name: str = "gateway", reason: str = "stop"
) -> None:
    """Fire GATEWAY_STOP hook when a gateway/BotOS stops."""
    if runner is None:
        return
    try:
        from praisonaiagents.hooks.types import HookEvent
        from praisonaiagents.hooks.events import GatewayStopInput

        event_input = GatewayStopInput(
            session_id="",
            cwd=os.getcwd(),
            event_name=HookEvent.GATEWAY_STOP,
            timestamp=str(time.time()),
            agent_name=agent_name,
            platforms=list(platforms),
            bot_count=len(platforms),
            reason=reason,
        )
        _emit(runner, HookEvent.GATEWAY_STOP, event_input)
    except Exception as e:
        logger.debug(f"GATEWAY_STOP hook error (non-fatal): {e}")


def fire_schedule_trigger(
    runner: Any,
    job_name: str,
    job_id: str = "",
    message: str = "",
    agent_name: str = "scheduler",
) -> None:
    """Fire SCHEDULE_TRIGGER hook when a scheduled job fires."""
    if runner is None:
        return
    try:
        from praisonaiagents.hooks.types import HookEvent
        from praisonaiagents.hooks.events import ScheduleTriggerInput

        event_input = ScheduleTriggerInput(
            session_id="",
            cwd=os.getcwd(),
            event_name=HookEvent.SCHEDULE_TRIGGER,
            timestamp=str(time.time()),
            agent_name=agent_name,
            job_name=job_name,
            job_id=job_id,
            message=message,
        )
        _emit(runner, HookEvent.SCHEDULE_TRIGGER, event_input)
    except Exception as e:
        logger.debug(f"SCHEDULE_TRIGGER hook error (non-fatal): {e}")


def fire_job_completed(
    runner: Any,
    job_id: str,
    status: str,
    *,
    result: Any = None,
    error: Optional[str] = None,
    deliver: str = "",
    platform: str = "",
    chat_id: str = "",
    thread_id: str = "",
    agent_name: str = "background",
) -> None:
    """Fire JOB_COMPLETED hook when a background job reaches a terminal state.

    Best-effort and non-fatal: an observability/delivery plugin may subscribe
    to this to react to background completion, but delivery itself is routed by
    the gateway's ``on_job_complete`` callback (see :class:`BotOS`).
    """
    if runner is None:
        return
    try:
        from praisonaiagents.hooks.types import HookEvent
        from praisonaiagents.hooks.events import JobCompletedInput

        event_input = JobCompletedInput(
            session_id="",
            cwd=os.getcwd(),
            event_name=HookEvent.JOB_COMPLETED,
            timestamp=str(time.time()),
            agent_name=agent_name,
            job_id=job_id,
            status=status,
            result=result,
            error=error,
            deliver=deliver,
            platform=platform,
            chat_id=chat_id,
            thread_id=thread_id,
        )
        _emit(runner, HookEvent.JOB_COMPLETED, event_input)
    except Exception as e:
        logger.debug(f"JOB_COMPLETED hook error (non-fatal): {e}")


def fire_session_start(
    runner: Any,
    session_id: str,
    platform: str = "",
    agent_name: str = "bot",
    source: str = "startup",
) -> None:
    """Fire SESSION_START hook when a per-user session is created."""
    if runner is None:
        return
    try:
        from praisonaiagents.hooks.types import HookEvent
        from praisonaiagents.hooks.events import SessionStartInput

        event_input = SessionStartInput(
            session_id=session_id,
            cwd=os.getcwd(),
            event_name=HookEvent.SESSION_START,
            timestamp=str(time.time()),
            agent_name=agent_name,
            source=source,
            session_name=platform,
        )
        _emit(runner, HookEvent.SESSION_START, event_input)
    except Exception as e:
        logger.debug(f"SESSION_START hook error (non-fatal): {e}")


def fire_session_end(
    runner: Any,
    session_id: str,
    agent_name: str = "bot",
    reason: str = "clear",
) -> None:
    """Fire SESSION_END hook when a per-user session is reset/ended."""
    if runner is None:
        return
    try:
        from praisonaiagents.hooks.types import HookEvent
        from praisonaiagents.hooks.events import SessionEndInput

        event_input = SessionEndInput(
            session_id=session_id,
            cwd=os.getcwd(),
            event_name=HookEvent.SESSION_END,
            timestamp=str(time.time()),
            agent_name=agent_name,
            reason=reason,
        )
        _emit(runner, HookEvent.SESSION_END, event_input)
    except Exception as e:
        logger.debug(f"SESSION_END hook error (non-fatal): {e}")
