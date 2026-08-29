"""
Execution and orchestration mixin for the Agent class.

Contains all methods for run/start/launch lifecycle, planning,
and server endpoints. Extracted from agent.py for maintainability.
"""

import time
import json
import logging
import inspect
import os

import asyncio
import threading


# Shared lazy display helpers (cached, thread-safe; avoid circular imports)
from ._lazy_display import _get_console, _get_live, _get_display_functions

logger = logging.getLogger(__name__)

from typing import List, Optional, Any, Dict, Union, Generator, TYPE_CHECKING

# Shared HTTP launch state (Agent.launch() multi-endpoint registration)
_server_lock = threading.Lock()
_server_started: Dict[int, bool] = {}
_registered_agents: Dict[int, Dict[str, str]] = {}
_shared_apps: Dict[int, Any] = {}


def cleanup_launch_registration(agent_id: str) -> None:
    """Remove launch() endpoints registered for ``agent_id`` from the shared
    HTTP state that ``Agent.launch()`` actually populates.

    ``Agent.launch()`` writes routes into the module-level ``_registered_agents``
    and ``_shared_apps`` dicts above. This tears those routes back down so a
    closed agent's endpoint stops accepting requests and the request handler
    closure no longer keeps the Agent object graph alive.
    """
    with _server_lock:
        for port, paths in list(_registered_agents.items()):
            stale_paths = [p for p, aid in paths.items() if aid == agent_id]
            for p in stale_paths:
                del paths[p]
                app = _shared_apps.get(port)
                if app is not None:
                    try:
                        # Only drop the agent-owned POST route. launch() always
                        # registers the handler via ``.post(path)``, so filtering
                        # on both path AND method preserves unrelated routes that
                        # share the path with a different verb (e.g. the built-in
                        # GET /health and GET /).
                        app.router.routes = [
                            r for r in app.router.routes
                            if not (
                                getattr(r, "path", None) == p
                                and "POST" in (getattr(r, "methods", None) or set())
                            )
                        ]
                        # Invalidate cached OpenAPI schema so removed routes
                        # disappear from /openapi.json and /docs.
                        app.openapi_schema = None
                    except Exception:
                        pass
            if not paths:
                _registered_agents.pop(port, None)

if TYPE_CHECKING:
    pass


class ExecutionMixin:
    """Mixin providing execution methods for the Agent class."""

    def _safe_sleep(self, duration: float) -> None:
        """Synchronous sleep - safe for sync contexts only."""
        time.sleep(duration)

    def generate_task(self) -> 'Task':
        """Generate a Task object from the agent's instructions"""
        from ..task.task import Task
        
        description = self.instructions if self.instructions else f"Execute task as {self.role} with goal: {self.goal}"
        expected_output = "Complete the assigned task successfully"
        
        return Task(
            name=self.name,
            description=description,
            expected_output=expected_output,
            agent=self,
            tools=self.tools
        )

    def as_tool(
        self,
        description: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> 'Handoff':
        """Convert this agent to a callable tool for use by other agents.
        
        Unlike handoffs which pass conversation context, as_tool() creates a tool
        where the child agent receives only the generated input (no history).
        The parent agent retains control and receives the result.
        
        This is useful for hierarchical agent composition where you want to
        invoke a specialist agent as a subordinate tool.
        
        Args:
            description: Tool description for the LLM (what this agent does)
            tool_name: Custom tool name (default: invoke_<agent_name>)
        
        Returns:
            Handoff configured as a tool with no context passed
        
        Example:
            researcher = Agent(name="Researcher", instructions="Research topics")
            coder = Agent(name="Coder", instructions="Write Python code")
            
            writer = Agent(
                name="Writer",
                tools=[
                    researcher.as_tool("Research a topic and return findings"),
                    coder.as_tool("Write Python code for a given task"),
                ]
            )
            
            result = writer.chat("Write an article about async Python")
        """
        from .handoff import Handoff, HandoffConfig, ContextPolicy
        
        # Generate default tool name
        agent_name_snake = self.name.lower().replace(' ', '_').replace('-', '_')
        default_tool_name = f"invoke_{agent_name_snake}"
        
        return Handoff(
            agent=self,
            tool_name_override=tool_name or default_tool_name,
            tool_description_override=description or f"Invoke {self.name} to complete a subtask and return the result",
            config=HandoffConfig(context_policy=ContextPolicy.NONE),
        )

    async def arun(self, prompt: str, **kwargs) -> Optional[str]:
        """Async version of run() - silent, non-streaming, returns structured result.
        
        Production-friendly async execution. Does not stream or display output.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments passed to achat()
            
        Returns:
            The agent's response as a string
        """
        # Remove stream from kwargs since achat() doesn't accept it
        kwargs.pop('stream', None)
        return await self.achat(prompt, **kwargs)

    async def astart(self, prompt: str, **kwargs):
        """Async version of start() - interactive, streaming-aware.
        
        Beginner-friendly async execution. Streams by default when in TTY.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments passed to achat():
                - return_outcome (bool): If True, return a canonical
                  ``RunOutcome`` (completed | hard_timeout | cancelled |
                  aborted | failed) instead of raising on error/timeout/
                  cancellation. Default: False.
                - timeout (float): When used with ``return_outcome=True``,
                  a hard timeout budget for the run.
            
        Returns:
            The agent's response as a string, or AutonomyResult if autonomy
            enabled, or a ``RunOutcome`` when ``return_outcome=True``.
            
        Note:
            If autonomy=True was set on the agent, astart() automatically uses
            the autonomous loop (run_autonomous_async) instead of single-turn chat.
        """
        import sys

        return_outcome = kwargs.pop('return_outcome', False)
        if return_outcome:
            outcome_timeout = kwargs.pop('timeout', None)
            return await self._astart_with_outcome(
                prompt, outcome_timeout, **kwargs
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # UNIFIED AUTONOMY API: If autonomy is enabled, route to run_autonomous_async
        # This allows: Agent(autonomy=True) + await agent.astart("Task") to just work!
        # ─────────────────────────────────────────────────────────────────────
        if self.autonomy_enabled:
            auto_config = self.autonomy_config or {}
            mode = auto_config.get('mode', 'caller')
            
            if mode == 'iterative':
                # Iterative mode: use run_autonomous_async (backward compat for full_auto)
                timeout = kwargs.pop('timeout', None)
                kwargs.pop('stream', None)  # Not used in autonomous mode
                max_iterations = auto_config.get('max_iterations', 20)
                completion_promise = auto_config.get('completion_promise')
                clear_context = auto_config.get('clear_context', False)
                
                return await self.run_autonomous_async(
                    prompt=prompt,
                    max_iterations=max_iterations,
                    timeout_seconds=timeout,
                    completion_promise=completion_promise,
                    clear_context=clear_context,
                )
            else:
                # Caller mode: single achat() call, wrapper-equivalent
                import time as time_module
                from datetime import datetime, timezone
                start_time = time_module.time()
                started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                
                response = await self.achat(prompt, **kwargs)
                response_str = str(response) if response else ""
                
                # Auto-save session after chat
                self._auto_save_session()
                
                # Wrap in AutonomyResult for consistent API
                from .autonomy import AutonomyResult
                return AutonomyResult(
                    success=True,
                    output=response_str,
                    completion_reason="caller_mode",
                    iterations=1,
                    stage="direct",
                    actions=[],
                    duration_seconds=time_module.time() - start_time,
                    started_at=started_at,
                )
        
        # Determine streaming behavior (same logic as start())
        stream_requested = kwargs.get('stream')
        if stream_requested is None:
            if getattr(self, 'stream', None) is not None:
                stream_requested = self.stream
            else:
                stream_requested = sys.stdout.isatty()
        
        kwargs['stream'] = stream_requested
        return await self.achat(prompt, **kwargs)

    async def _astart_with_outcome(self, prompt, timeout=None, **kwargs):
        """Run astart() and normalise its result/exception into a RunOutcome.

        Optionally enforces a hard run-level timeout budget. The budget is the
        *authoritative* source of ``hard_timeout``: when our own
        ``asyncio.wait_for`` fires we return ``hard_timeout`` directly, so a
        nested operation timeout (which surfaces as a generic
        ``asyncio.TimeoutError`` from inside the run) is never misreported as a
        run-budget timeout — it falls through to ``failed`` via
        ``RunOutcome.from_exception``.

        External ``asyncio.CancelledError`` (e.g. the enclosing task being
        cancelled during host shutdown) is re-raised, not swallowed, so
        cooperative cancellation semantics are honoured.
        """
        import asyncio
        from .run_outcome import RunOutcome

        enforce_budget = timeout is not None and timeout > 0

        # Enforce the run budget with an explicit deadline on a task we own, so
        # that only *our* budget expiry maps to hard_timeout. This deliberately
        # avoids ``asyncio.wait_for`` catching a bare inner ``TimeoutError``:
        # a nested operation timeout raised inside the run must fall through to
        # ``failed`` rather than be misreported as a run-budget ``hard_timeout``.
        try:
            if enforce_budget:
                task = asyncio.ensure_future(self.astart(prompt, **kwargs))
                try:
                    done, _ = await asyncio.wait({task}, timeout=timeout)
                except asyncio.CancelledError:
                    # Enclosing task cancelled (e.g. host shutdown): cancel the
                    # child and propagate so cooperative cancellation is honoured.
                    task.cancel()
                    raise
                if task not in done:
                    # Our budget expired first: authoritative, sticky hard_timeout.
                    task.cancel()
                    return RunOutcome(reason="hard_timeout")
                result = task.result()
            else:
                result = await self.astart(prompt, **kwargs)
        except asyncio.CancelledError:
            # External cancellation of the awaiting task: honour asyncio
            # cancellation / host shutdown by propagating instead of converting
            # it into a benign RunOutcome.
            raise
        except Exception as exc:  # noqa: BLE001 - normalised into outcome
            return RunOutcome.from_exception(exc)
        return self._outcome_for_result(result)

    def _outcome_for_result(self, result):
        """Map a normally-returned run result into a canonical RunOutcome.

        A run that returned without raising is ``completed`` *unless* the core
        recorded a provider block/refusal/truncation on ``last_stop_reason`` from
        the LLM ``finish_reason``/refusal signal — in which case the specific,
        actionable terminal reason (``content_filtered | refused |
        length_truncated``) is surfaced instead of a silent empty ``completed``.
        Any other stop reason (``completed``/``max_steps``/unknown) preserves the
        existing ``completed`` semantics, so behaviour is unchanged on success.
        """
        from .run_outcome import RunOutcome, PROVIDER_BLOCK_REASONS
        output = str(result) if result is not None else None
        # Read the recorded classification without letting a lookup problem mask a
        # provider block as a successful ``completed``. Only an expected
        # missing-state lookup (``AttributeError``) is treated as "no reason
        # recorded"; anything else propagates rather than silently succeeding.
        reason = None
        try:
            reason = getattr(self, "last_stop_reason", None)
        except AttributeError:
            reason = None
        if reason in PROVIDER_BLOCK_REASONS:
            return RunOutcome(reason=reason, output=output)
        return RunOutcome.completed(output=output)

    def run(self, prompt: str, **kwargs: Any) -> Optional[str]:
        """Execute agent silently and return structured result.
        
        Production-friendly execution. Always uses silent mode with no streaming
        or verbose display, regardless of TTY status. Use this for programmatic,
        scripted, or automated usage where you want just the result.
        
        Args:
            prompt: The input prompt to process
            **kwargs: Additional arguments:
                - stream (bool): Force streaming if True. Default: False
                - output (str): Output preset override (rarely needed)
                - return_outcome (bool): If True, return a canonical
                  ``RunOutcome`` describing how the run ended
                  (completed | hard_timeout | cancelled | aborted | failed)
                  instead of raising on error. Default: False.
                
        Returns:
            The agent's response as a string, or a ``RunOutcome`` when
            ``return_outcome=True``.
            
        Example:
            ```python
            agent = Agent(instructions="You are helpful")
            result = agent.run("What is 2+2?")  # Silent, returns "4"
            print(result)
            ```
            
        Note:
            Unlike .start() which enables verbose output in TTY for interactive
            use, .run() is always silent. This makes it suitable for:
            - Production pipelines
            - Automated scripts
            - Background processing
            - API endpoints
        """
        return_outcome = kwargs.pop('return_outcome', False)

        # Check if external managed backend is configured
        if hasattr(self, 'backend') and self.backend is not None:
            if return_outcome:
                return self._run_with_outcome(
                    lambda: self._delegate_to_backend(prompt, **kwargs)
                )
            return self._delegate_to_backend(prompt, **kwargs)
        
        # Production defaults: no streaming, no display
        if 'stream' not in kwargs:
            kwargs['stream'] = False
        
        # Substitute dynamic variables ({{today}}, {{now}}, {{uuid}}, etc.)
        if prompt and "{{" in prompt:
            from praisonaiagents.utils.variables import substitute_variables
            prompt = substitute_variables(prompt, {})
        
        # Load history context
        self._load_history_context()

        def _execute():
            if self.planning:
                _result = self._start_with_planning(prompt, **kwargs)
            else:
                _result = self.chat(prompt, **kwargs)
            # Auto-save session if enabled
            self._auto_save_session()
            return _result

        if return_outcome:
            return self._run_with_outcome(_execute)

        return _execute()

    def _run_with_outcome(self, executor):
        """Run ``executor`` and normalise its result/exception into a RunOutcome.

        Keeps the canonical terminal-outcome logic in one place so callers get
        a single, closed description of how the run ended instead of inferring
        it from exception identity.
        """
        from .run_outcome import RunOutcome
        try:
            result = executor()
        except BaseException as exc:  # noqa: BLE001 - normalised into outcome
            return RunOutcome.from_exception(exc)
        return self._outcome_for_result(result)

    def _delegate_to_backend(self, prompt: str, **kwargs) -> Optional[str]:
        """Delegate execution to external managed backend (e.g., ManagedAgentIntegration).
        
        Also records the prompt and response in the Agent's chat_history so that
        PraisonAI's session management (SessionStore, auto_save) stays consistent
        with managed-backend conversations.
        """
        import asyncio
        
        # Check if backend satisfies ManagedBackendProtocol
        from praisonaiagents.agent.protocols import ManagedBackendProtocol
        if not (isinstance(self.backend, ManagedBackendProtocol) or hasattr(self.backend, 'execute')):
            raise RuntimeError(f"Backend {type(self.backend).__name__} does not support execute() method")
        
        # Handle streaming vs non-streaming
        stream_requested = kwargs.get('stream', False)
        
        if stream_requested and hasattr(self.backend, '_execute_sync'):
            # Fast path: backend supports sync streaming (prints token-by-token)
            result = self.backend._execute_sync(prompt, stream_live=True)
        elif stream_requested:
            if hasattr(self.backend, 'stream'):
                result = self._delegate_streaming_to_backend(prompt, **kwargs)
            else:
                result = self._execute_backend_sync(prompt, **kwargs)
        else:
            result = self._execute_backend_sync(prompt, **kwargs)
        
        # ── Chat history & session linkage ──
        # Record prompt+response in chat_history so SessionStore/auto_save works
        if result is not None:
            self._append_to_chat_history({"role": "user", "content": prompt})
            self._append_to_chat_history({"role": "assistant", "content": str(result)})
            # Link managed session ID into SessionStore gateway_session_id
            if hasattr(self.backend, 'managed_session_id'):
                msid = self.backend.managed_session_id
                if msid and self._session_store is not None:
                    try:
                        sid = getattr(self, 'auto_save', None) or getattr(self, '_session_id', None)
                        if sid and hasattr(self._session_store, 'set_gateway_info'):
                            self._session_store.set_gateway_info(sid, gateway_session_id=msid)
                    except Exception as e:
                        # Log session linkage failures for debugging
                        logger.warning(
                            "Session gateway linkage failed: %s",
                            e,
                            extra={"session_id": sid, "managed_session_id": msid},
                            exc_info=True,
                        )
            self._auto_save_session()
        
        return result

    async def _adelegate_to_backend(self, prompt: str, **kwargs) -> Optional[str]:
        """Async delegation to an external managed backend (async parity with
        ``_delegate_to_backend``). Awaits the backend's async ``execute`` directly
        instead of bridging through a worker thread, then records prompt/response
        in chat_history so session management stays consistent.
        """
        from praisonaiagents.agent.protocols import ManagedBackendProtocol
        if not (isinstance(self.backend, ManagedBackendProtocol) or hasattr(self.backend, 'execute')):
            raise RuntimeError(f"Backend {type(self.backend).__name__} does not support execute() method")

        result = await self.backend.execute(prompt, **kwargs)

        if result is not None:
            self._append_to_chat_history({"role": "user", "content": prompt})
            self._append_to_chat_history({"role": "assistant", "content": str(result)})
            if hasattr(self.backend, 'managed_session_id'):
                msid = self.backend.managed_session_id
                if msid and self._session_store is not None:
                    try:
                        sid = getattr(self, 'auto_save', None) or getattr(self, '_session_id', None)
                        if sid and hasattr(self._session_store, 'set_gateway_info'):
                            self._session_store.set_gateway_info(sid, gateway_session_id=msid)
                    except Exception as e:
                        logger.warning(
                            "Session gateway linkage failed: %s",
                            e,
                            extra={"session_id": sid, "managed_session_id": msid},
                            exc_info=True,
                        )
            self._auto_save_session()

        return result

    def _execute_backend_sync(self, prompt: str, **kwargs) -> Optional[str]:
        """Execute backend in sync mode, handling async backends."""
        try:
            # Try to run in existing event loop
            loop = asyncio.get_running_loop()
            # If we're already in an async context, we can't use asyncio.run()
            # Create a new task instead
            import concurrent.futures
            import threading
            
            def run_async():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(self.backend.execute(prompt, **kwargs))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                return future.result()
                
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(self.backend.execute(prompt, **kwargs))
    
    def _delegate_streaming_to_backend(self, prompt: str, **kwargs):
        """Delegate to backend's streaming method."""
        try:
            # For streaming, we need to return an iterator/generator
            # The backend's stream method is async, so we need to handle that
            import asyncio
            
            async def stream_wrapper():
                async for chunk in self.backend.stream(prompt, **kwargs):
                    yield chunk
            
            # Convert async generator to sync generator
            def sync_stream():
                try:
                    loop = asyncio.get_running_loop()
                    # Already in async context - need to handle differently
                    import concurrent.futures
                    import threading
                    import queue
                    
                    result_queue = queue.Queue()
                    exception_holder = [None]
                    
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            async def collect():
                                try:
                                    async for item in self.backend.stream(prompt, **kwargs):
                                        result_queue.put(('item', item))
                                    result_queue.put(('done', None))
                                except Exception as e:
                                    exception_holder[0] = e
                                    result_queue.put(('error', e))
                            
                            new_loop.run_until_complete(collect())
                        finally:
                            new_loop.close()
                    
                    thread = threading.Thread(target=run_in_thread)
                    thread.start()
                    
                    while True:
                        msg_type, data = result_queue.get()
                        if msg_type == 'item':
                            # For managed backends, we might get event objects
                            # Convert to string format expected by Agent
                            if isinstance(data, dict):
                                if data.get('type') == 'agent.message':
                                    content = data.get('content', [])
                                    if isinstance(content, list):
                                        text_parts = []
                                        for block in content:
                                            if isinstance(block, dict) and block.get('type') == 'text':
                                                text_parts.append(block.get('text', ''))
                                            elif isinstance(block, str):
                                                text_parts.append(block)
                                        if text_parts:
                                            yield ''.join(text_parts)
                                    elif isinstance(content, str):
                                        yield content
                                # Skip other event types (session.status_idle, etc.)
                            elif isinstance(data, str):
                                yield data
                        elif msg_type == 'done':
                            break
                        elif msg_type == 'error':
                            raise data
                    
                    thread.join()
                    
                except RuntimeError:
                    # No event loop (the common script/CLI case). Drive the
                    # backend's async generator from a background thread and
                    # push each chunk through a queue as it arrives, so the
                    # caller receives chunks incrementally instead of only
                    # after the whole response has been buffered. Mirrors the
                    # running-loop branch above.
                    import threading
                    import queue
                    # Bounded queue so an abandoned consumer applies
                    # back-pressure instead of letting the producer fill memory
                    # unbounded. ``cancel_event`` lets the producer stop early
                    # when the caller closes the generator.
                    bridge_queue = queue.Queue(maxsize=64)
                    cancel_event = threading.Event()

                    def run_in_thread_noloop():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            async def pump():
                                try:
                                    async for item in self.backend.stream(prompt, **kwargs):
                                        if cancel_event.is_set():
                                            break
                                        # Block until space is available or the
                                        # consumer signals cancellation, so we
                                        # never spin nor grow the queue forever.
                                        while not cancel_event.is_set():
                                            try:
                                                bridge_queue.put(('item', item), timeout=0.1)
                                                break
                                            except queue.Full:
                                                continue
                                    if not cancel_event.is_set():
                                        bridge_queue.put(('done', None))
                                except Exception as e:
                                    if not cancel_event.is_set():
                                        bridge_queue.put(('error', e))

                            new_loop.run_until_complete(pump())
                        finally:
                            new_loop.close()

                    # Daemon thread so a stalled/abandoned producer can never
                    # block interpreter shutdown.
                    thread = threading.Thread(target=run_in_thread_noloop, daemon=True)
                    thread.start()

                    try:
                        while True:
                            msg_type, data = bridge_queue.get()
                            if msg_type == 'item':
                                item = data
                                # Same conversion logic as the running-loop branch.
                                if isinstance(item, dict):
                                    if item.get('type') == 'agent.message':
                                        content = item.get('content', [])
                                        if isinstance(content, list):
                                            text_parts = []
                                            for block in content:
                                                if isinstance(block, dict) and block.get('type') == 'text':
                                                    text_parts.append(block.get('text', ''))
                                                elif isinstance(block, str):
                                                    text_parts.append(block)
                                            if text_parts:
                                                yield ''.join(text_parts)
                                        elif isinstance(content, str):
                                            yield content
                                elif isinstance(item, str):
                                    yield item
                            elif msg_type == 'done':
                                break
                            elif msg_type == 'error':
                                raise data
                    finally:
                        # Runs on normal completion AND on early generator
                        # close/GC: signal the producer to stop, drain one slot
                        # so a blocked put() can observe the cancel, and join.
                        cancel_event.set()
                        try:
                            bridge_queue.get_nowait()
                        except queue.Empty:
                            pass
                        thread.join(timeout=5)
            
            return sync_stream()
            
        except Exception as e:
            # Fallback to non-streaming
            logger.warning(f"Backend streaming failed, falling back to non-streaming: {e}")
            return self._execute_backend_sync(prompt, **kwargs)

    def _get_planning_agent(self):
        """Lazy load PlanningAgent for planning mode."""
        if self._planning_agent is None and self.planning:
            from ..planning import PlanningAgent
            self._planning_agent = PlanningAgent(
                llm=self.llm if hasattr(self, 'llm') else (self.llm_instance.model if hasattr(self, 'llm_instance') else "gpt-4o-mini"),
                tools=self.planning_tools,
                reasoning=self.planning_reasoning,
                verbose=1 if self.verbose else 0
            )
        return self._planning_agent

    def _start_with_planning(self, prompt: str, **kwargs):
        """Execute with planning mode - creates plan then executes each step."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        console = _get_console()()
        
        # Step 1: Create the plan
        console.print("\n[bold blue]📋 PLANNING PHASE[/bold blue]")
        console.print("[dim]Creating implementation plan...[/dim]\n")
        
        planner = self._get_planning_agent()
        plan = planner.create_plan_sync(request=prompt, agents=[self])
        
        if not plan or not plan.steps:
            console.print("[yellow]⚠️ Planning failed, falling back to direct execution[/yellow]")
            return self.chat(prompt, **kwargs)
        
        # Display the plan
        console.print(Panel(
            Markdown(plan.to_markdown()),
            title="[bold green]Generated Plan[/bold green]",
            border_style="green"
        ))
        
        # Step 2: Execute each step
        console.print("\n[bold blue]🚀 EXECUTION PHASE[/bold blue]\n")
        
        results = []
        context = ""
        
        for i, step in enumerate(plan.steps):
            progress = (i + 1) / len(plan.steps)
            bar_length = 30
            filled = int(bar_length * progress)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            console.print(f"[dim]Progress: [{bar}] {progress * 100:.0f}%[/dim]")
            console.print(f"\n[bold]📌 Step {i + 1}/{len(plan.steps)}:[/bold] {step.description[:60]}...")
            
            # Build prompt with context from previous steps
            step_prompt = step.description
            if context:
                step_prompt = f"{step.description}\n\nContext from previous steps:\n{context}"
            
            # Execute the step
            result = self.chat(step_prompt, **kwargs)
            results.append({"step": i + 1, "description": step.description, "result": result})
            
            # Update context for next step (use full result, not truncated)
            context += f"\n\nStep {i + 1} result: {result if result else 'No result'}"
            
            console.print(f"   [green]✅ Completed[/green]")
        
        console.print(f"\n[bold green]🎉 EXECUTION COMPLETE[/bold green]")
        console.print(f"[dim]Progress: [{'█' * bar_length}] 100%[/dim]")
        console.print(f"Completed {len(plan.steps)}/{len(plan.steps)} steps!\n")
        
        # Compile all results into a comprehensive final output
        if len(results) > 1:
            # Create a compilation prompt
            all_results_text = "\n\n".join([
                f"## Step {r['step']}: {r['description']}\n\n{r['result']}" 
                for r in results
            ])
            
            compilation_prompt = f"""You are tasked with compiling a comprehensive, detailed report from the following research steps.

IMPORTANT: Write a DETAILED and COMPREHENSIVE report. Do NOT summarize or compress the information. 
Include ALL relevant details, data, statistics, and findings from each step.
Organize the information logically with clear sections and subsections.

## Research Results to Compile:

{all_results_text}

## Instructions:
1. Combine all the information into a single, well-organized document
2. Preserve ALL details, numbers, statistics, and specific findings
3. Use clear headings and subheadings
4. Do not omit any important information
5. Make it comprehensive and detailed

Write the complete compiled report:"""
            
            console.print("\n[bold blue]📝 COMPILING FINAL REPORT[/bold blue]")
            console.print("[dim]Creating comprehensive output from all steps...[/dim]\n")
            
            final_result = self.chat(compilation_prompt, **kwargs)
            return final_result
        
        # Return the single result if only one step
        return results[0]["result"] if results else None

    def switch_model(self, new_model: str) -> None:
        """
        Switch the agent's LLM model while preserving conversation history.
        
        Args:
            new_model: The new model name to switch to (e.g., "gpt-4o", "claude-3-sonnet")
        """
        # Store the new model name
        self.llm = new_model
        
        # Recreate the LLM instance with the new model
        try:
            from ..llm.llm import LLM
            self._llm_instance = LLM(
                model=new_model,
                base_url=self._openai_base_url,
                api_key=self._openai_api_key,
            )
            self._using_custom_llm = True
        except ImportError:
            # If LLM class not available, just update the model string
            pass

    def start(self, prompt: Optional[str] = None, **kwargs: Any) -> Union[str, Generator[str, None, None], None]:
        """Start the agent interactively with verbose output.
        
        Beginner-friendly execution. Defaults to verbose output with streaming
        when running in a TTY. Use this for interactive/terminal usage where 
        you want to see output in real-time with rich formatting.
        
        Args:
            prompt: The input prompt to process. If not provided, uses the 
                    agent's instructions as the task (useful when instructions
                    already describe what the agent should do).
            **kwargs: Additional arguments:
                - stream (bool | None): Override streaming. None = auto-detect TTY
                - output (str): Output preset override (e.g., "silent", "verbose")
                
        Returns:
            - If streaming: Generator yielding response chunks
            - If not streaming: The complete response as a string
            
        Example:
            ```python
            # Minimal usage - instructions IS the task
            agent = Agent(instructions="Research AI trends and summarize")
            result = agent.start()  # Uses instructions as task
            
            # With explicit prompt (overrides/adds to instructions)
            agent = Agent(instructions="You are a helpful assistant")
            result = agent.start("What is 2+2?")  # Uses prompt as task
            ```
            
        Note:
            Unlike .run() which is always silent (production use), .start()
            enables verbose output by default when in a TTY for beginner-friendly
            interactive use. Use .run() for programmatic/scripted usage.
            
            If autonomy=True was set on the agent, start() automatically uses
            the autonomous loop (run_autonomous) instead of single-turn chat.
        """
        import sys
        
        # If no prompt provided, use instructions as the task
        if prompt is None:
            prompt = self.instructions or "Hello"
        
        # Substitute dynamic variables ({{today}}, {{now}}, {{uuid}}, etc.)
        if prompt and "{{" in prompt:
            from praisonaiagents.utils.variables import substitute_variables
            prompt = substitute_variables(prompt, {})
        
        # Check if external managed backend is configured
        if hasattr(self, 'backend') and self.backend is not None:
            # Detect streaming preference BEFORE delegating (same logic as normal path)
            if 'stream' not in kwargs:
                if getattr(self, 'stream', None) is not None:
                    kwargs['stream'] = self.stream
                else:
                    kwargs['stream'] = sys.stdout.isatty()
            return self._delegate_to_backend(prompt, **kwargs)
        
        # ─────────────────────────────────────────────────────────────────────
        # UNIFIED AUTONOMY API: If autonomy is enabled, route to run_autonomous
        # This allows: Agent(autonomy=True) + agent.start("Task") to just work!
        # ─────────────────────────────────────────────────────────────────────
        if self.autonomy_enabled:
            auto_config = self.autonomy_config or {}
            mode = auto_config.get('mode', 'caller')
            
            if mode == 'iterative':
                # Iterative mode: use run_autonomous (backward compat for full_auto)
                timeout = kwargs.pop('timeout', None)
                max_iterations = auto_config.get('max_iterations', 20)
                completion_promise = auto_config.get('completion_promise')
                clear_context = auto_config.get('clear_context', False)
                
                return self.run_autonomous(
                    prompt=prompt,
                    max_iterations=max_iterations,
                    timeout_seconds=timeout,
                    completion_promise=completion_promise,
                    clear_context=clear_context,
                )
            else:
                # Caller mode: single chat() call, wrapper-equivalent
                # All init-time features (approval, doom-loop per-tool,
                # track_changes, sandbox, default_tools) are already wired.
                import time as time_module
                from datetime import datetime, timezone
                start_time = time_module.time()
                started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                
                # Load history from past sessions
                self._load_history_context()
                
                # Use chat() — all tools, approval, doom-loop per-tool work
                response = self.chat(prompt, **kwargs)
                response_str = str(response) if response else ""
                
                # Auto-save session after chat
                self._auto_save_session()
                
                # Wrap in AutonomyResult for consistent API
                from .autonomy import AutonomyResult
                return AutonomyResult(
                    success=True,
                    output=response_str,
                    completion_reason="caller_mode",
                    iterations=1,
                    stage="direct",
                    actions=[],
                    duration_seconds=time_module.time() - start_time,
                    started_at=started_at,
                )
        
        # Load history from past sessions
        self._load_history_context()
        
        # Determine if we're in an interactive TTY
        is_tty = sys.stdout.isatty()
        
        # Determine streaming behavior
        # Priority: explicit kwarg > agent's stream attribute > TTY detection
        stream_requested = kwargs.get('stream')
        if stream_requested is None:
            # Check agent's stream attribute first
            if getattr(self, 'stream', None) is not None:
                stream_requested = self.stream
            else:
                # Auto-detect: stream if stdout is a TTY (interactive terminal)
                stream_requested = is_tty
        
        # ─────────────────────────────────────────────────────────────────────
        # Enable verbose output in TTY for beginner-friendly interactive use
        # Priority: agent's explicit output config > start() override > TTY auto
        # ─────────────────────────────────────────────────────────────────────
        original_verbose = self.verbose
        original_markdown = self.markdown
        output_override = kwargs.pop('output', None)  # Pop to prevent passing to chat()
        
        # Check if agent was configured with explicit output mode (not default)
        # If so, respect it and don't auto-enable verbose for TTY
        has_explicit_output = getattr(self, '_has_explicit_output_config', False)
        
        try:
            # Apply output override from start() call if provided
            if output_override:
                # Apply explicit output preset for this call
                from ..config.presets import OUTPUT_PRESETS
                if output_override in OUTPUT_PRESETS:
                    preset = OUTPUT_PRESETS[output_override]
                    self.verbose = preset.get('verbose', False)
                    self.markdown = preset.get('markdown', False)
            # Only auto-enable verbose for TTY if NO explicit output was configured
            elif is_tty and not has_explicit_output:
                self.verbose = True
                self.markdown = True
            
            # Check if planning mode is enabled
            if self.planning:
                result = self._start_with_planning(prompt, **kwargs)
            elif stream_requested:
                # Return a generator for streaming response
                kwargs['stream'] = True
                result = self._start_stream(prompt, **kwargs)
            else:
                # Return regular chat response with animated working status
                kwargs['stream'] = False
                
                # Show animated status during LLM call if verbose
                if self.verbose and is_tty:
                    from ..main import PRAISON_COLORS, sync_display_callbacks, _callbacks_lock
                    import threading
                    import time as time_module
                    
                    console = _get_console()()
                    start_time = time_module.time()
                    
                    # ─────────────────────────────────────────────────────────────
                    # Shared state for dynamic status messages (thread-safe)
                    # Updated by callbacks during tool execution
                    # ─────────────────────────────────────────────────────────────
                    current_status = ["Analyzing query..."]
                    tools_called = []
                    
                    # Register a temporary callback to track tool calls
                    def status_tool_callback(**kwargs):
                        tool_name = kwargs.get('tool_name', '')
                        if tool_name:
                            tools_called.append(tool_name)
                            current_status[0] = f"Calling tool: {tool_name}..."
                    
                    # Store original callback and register ours (use the module's
                    # own lock so this doesn't race concurrent verbose agents)
                    with _callbacks_lock:
                        original_tool_callback = sync_display_callbacks.get('tool_call')
                        sync_display_callbacks['tool_call'] = status_tool_callback
                    
                    # Animation state
                    result_holder = [None]
                    error_holder = [None]
                    
                    # Temporarily disable verbose in chat to prevent duplicate output
                    original_verbose_chat = self.verbose
                    
                    def run_chat():
                        try:
                            # Suppress verbose during animation - we'll display result ourselves
                            self.verbose = False
                            current_status[0] = "Sending to LLM..."
                            
                            # Check for steering messages before starting chat
                            if hasattr(self, '_check_steering_messages'):
                                try:
                                    steering_msg = self._check_steering_messages()
                                    if steering_msg:
                                        # Inject steering message into prompt with clear separator
                                        prompt_with_steering = f"{prompt}\n\n{steering_msg}"
                                        current_status[0] = "Processing steering guidance..."
                                        result_holder[0] = self.chat(prompt_with_steering, **kwargs)
                                    else:
                                        result_holder[0] = self.chat(prompt, **kwargs)
                                except Exception as e:
                                    logger.warning(f"Steering check failed, continuing without steering: {e}")
                                    current_status[0] = "Steering failed, proceeding normally..."
                                    result_holder[0] = self.chat(prompt, **kwargs)
                            else:
                                result_holder[0] = self.chat(prompt, **kwargs)
                                
                            current_status[0] = "Finalizing response..."
                        except Exception as e:
                            error_holder[0] = e
                        finally:
                            self.verbose = original_verbose_chat
                            # Restore original callback under the lock. The identity
                            # check guards the entire restore, so we only mutate the
                            # entry while it's still ours and never clobber a callback
                            # a concurrent verbose agent has since installed.
                            with _callbacks_lock:
                                if sync_display_callbacks.get('tool_call') is status_tool_callback:
                                    if original_tool_callback:
                                        sync_display_callbacks['tool_call'] = original_tool_callback
                                    else:
                                        del sync_display_callbacks['tool_call']
                    
                    # Start chat in background thread
                    chat_thread = threading.Thread(target=run_chat)
                    chat_thread.start()
                    
                    from rich.panel import Panel
                    from rich.text import Text
                    from rich.markdown import Markdown
                    
                    # ─────────────────────────────────────────────────────────────
                    # Smart Agent Info: Only show if user provided meaningful info
                    # Skip if using defaults ("Agent"/"Assistant") with single agent
                    # ─────────────────────────────────────────────────────────────
                    has_custom_name = self.name and self.name not in ("Agent", "agent", None, "")
                    has_custom_role = self.role and self.role not in ("Assistant", "AI Assistant", "assistant", None, "")
                    has_tools = bool(self.tools)
                    
                    show_agent_info = has_custom_name or has_custom_role or has_tools
                    
                    agent_panel = None
                    if show_agent_info:
                        agent_info_parts = []
                        if has_custom_name:
                            agent_info_parts.append(f"[bold {PRAISON_COLORS['task']}]👤 Agent:[/] [{PRAISON_COLORS['agent_text']}]{self.name}[/]")
                        if has_custom_role:
                            agent_info_parts.append(f"[bold {PRAISON_COLORS['metrics']}]Role:[/] [{PRAISON_COLORS['agent_text']}]{self.role}[/]")
                        if has_tools:
                            tools_list = [t.__name__ if hasattr(t, '__name__') else str(t) for t in self.tools][:5]
                            tools_str = ", ".join(f"[italic {PRAISON_COLORS['response']}]{tool}[/]" for tool in tools_list)
                            agent_info_parts.append(f"[bold {PRAISON_COLORS['agent']}]Tools:[/] {tools_str}")
                        
                        agent_panel = Panel(
                            "\n".join(agent_info_parts), 
                            border_style=PRAISON_COLORS["agent"], 
                            title="[bold]Agent Info[/]", 
                            title_align="left", 
                            padding=(1, 2)
                        )
                    
                    # Create task panel
                    task_panel = Panel.fit(
                        Markdown(prompt) if self.markdown else Text(prompt),
                        title="Task",
                        border_style=PRAISON_COLORS["task"]
                    )
                    
                    # Show initial panels (agent info if applicable, then task)
                    if agent_panel:
                        console.print(agent_panel)
                    console.print(task_panel)
                    
                    # ─────────────────────────────────────────────────────────────
                    # Animate with Rich.Status showing DYNAMIC status from callbacks
                    # ─────────────────────────────────────────────────────────────
                    with console.status(
                        f"[bold yellow]Working...[/]  {current_status[0]}", 
                        spinner="dots",
                        spinner_style="yellow"
                    ) as status:
                        last_status = current_status[0]
                        while chat_thread.is_alive():
                            time_module.sleep(0.15)  # More responsive updates
                            # Only update if status changed (reduces flicker)
                            if current_status[0] != last_status:
                                last_status = current_status[0]
                            status.update(f"[bold yellow]Working...[/]  {current_status[0]}")
                    
                    # Calculate elapsed time
                    elapsed = time_module.time() - start_time
                    
                    # Re-raise any error from chat
                    if error_holder[0]:
                        raise error_holder[0]
                    
                    result = result_holder[0]
                    
                    # Display response panel
                    response_panel = Panel.fit(
                        Markdown(str(result)) if self.markdown else Text(str(result)),
                        title=f"Response ({elapsed:.1f}s)",
                        border_style=PRAISON_COLORS["response"]
                    )
                    console.print(response_panel)
                    
                    # Show tool activity summary if tools were called (deduplicated)
                    if tools_called:
                        # Use dict.fromkeys to preserve order while removing duplicates
                        unique_tools = list(dict.fromkeys(tools_called))
                        tools_summary = ", ".join(unique_tools)
                        console.print(f"[dim]🔧 Tools used: {tools_summary}[/dim]")
                else:
                    result = self.chat(prompt, **kwargs)
            
            # Auto-save session if enabled
            self._auto_save_session()
            
            # Auto-save output to file if configured
            if result and self._output_file:
                self._save_output_to_file(str(result))
            
            return result
        finally:
            # Restore original output settings
            self.verbose = original_verbose
            self.markdown = original_markdown

    def learn_skill(self, request: str, **kwargs: Any) -> Union[str, Generator[str, None, None], None]:
        """Author a grounded, reusable skill from sources you describe.

        Point the agent at real source material — a directory of code, API docs,
        PDFs/manuals, configs, pasted notes, or "what we just did in this chat" —
        and it gathers them with the tools it already has (file read, fetch, PDF
        read) and authors **one grounded SKILL.md** via the ``skill_manage`` tool.

        House-style rules keep self-written skills trustworthy: only flags, paths,
        and APIs that appear verbatim in the source are used (never invented), the
        SKILL.md is kept tight (~100-200 lines), and long material is moved to
        supporting files referenced by relative path. The result is a permanent,
        reusable skill, immediately invocable like any other skill.

        This is the **skill authoring** path and is intentionally distinct from
        the memory ``learn=`` constructor param (conversation→memory extraction)
        and the automatic ``self_improve`` loop. It is a prompt + entry point on
        top of existing tools, not a new distillation engine: it ensures
        ``skill_manage`` is available, then runs a single turn with :meth:`start`.

        Args:
            request: Natural-language description of the sources to learn from and
                the skill to produce, e.g.
                ``"Read ./my-repo and the docs in ./docs/*.pdf and make a
                'deploy-flow' skill"``.
            **kwargs: Additional arguments forwarded to :meth:`start`.

        Returns:
            The agent's response (the authored skill summary), as returned by
            :meth:`start`.

        Example::

            agent = Agent()
            agent.learn_skill("Read ./my-repo and make a 'deploy-flow' skill")
        """
        from praisonaiagents.skills import build_learn_prompt

        self._ensure_skill_management_tools()
        return self.start(build_learn_prompt(request), **kwargs)

    async def alearn_skill(self, request: str, **kwargs: Any) -> Union[str, Generator[str, None, None], None]:
        """Async variant of :meth:`learn_skill` (parity with ``start``/``astart``).

        Ensures ``skill_manage`` is available, then awaits a single turn via
        :meth:`astart` so async callers never block the event loop.

        Args:
            request: See :meth:`learn_skill`.
            **kwargs: Additional arguments forwarded to :meth:`astart`.

        Returns:
            The agent's response (the authored skill summary).
        """
        from praisonaiagents.skills import build_learn_prompt

        self._ensure_skill_management_tools()
        return await self.astart(build_learn_prompt(request), **kwargs)

    def learn(self, request: str, **kwargs: Any) -> Union[str, Generator[str, None, None], None]:
        """Backward-compatible alias for :meth:`learn_skill`.

        Retained so existing ``agent.learn("...")`` calls keep working. Prefer
        :meth:`learn_skill` to avoid confusion with the memory ``learn=`` param.
        """
        return self.learn_skill(request, **kwargs)

    async def alearn(self, request: str, **kwargs: Any) -> Union[str, Generator[str, None, None], None]:
        """Backward-compatible async alias for :meth:`alearn_skill`."""
        return await self.alearn_skill(request, **kwargs)

    def optimize_instructions(
        self,
        evalset: List[Any],
        *,
        metric: Optional[Any] = None,
        scorer: Optional[Any] = None,
        criteria: str = "",
        n_candidates: int = 6,
        apply: bool = True,
    ) -> Any:
        """Optimise this agent's own ``instructions`` against an eval set.

        Opt-in, off by default. Generates ``n_candidates`` instruction variants,
        scores each over ``evalset`` (LLM ``Judge`` by default, or a numeric
        ``metric`` you supply), keeps the highest-scoring one, and — when
        ``apply=True`` — writes it back to ``self.instructions``.

        Args:
            evalset: List of ``(prompt, expected)`` cases to score candidates on.
            metric: Optional numeric metric ``(output, expected) -> float``.
                When set, empirical scoring replaces the LLM Judge.
            scorer: Optional custom ``Judge`` instance (ignored if ``metric`` set).
            criteria: Optional criteria for the default Judge.
            n_candidates: Number of instruction variants to try (default: 6).
            apply: Write the winning instructions back to the agent (default: True).

        Returns:
            ``OptimizeResult`` with ``best_instructions``, ``best_score``,
            ``base_score`` and the full ``trials`` list.

        Example::

            result = agent.optimize_instructions(
                evalset=[("summarise X", gold_x)], metric=rouge_l,
            )
            print(result.best_score, result.best_instructions)
        """
        from praisonaiagents.eval.prompt_optimizer import PromptOptimizer

        return PromptOptimizer(
            self,
            evalset,
            scorer=scorer,
            metric=metric,
            criteria=criteria,
            n_candidates=n_candidates,
            apply=apply,
        ).optimize()

    async def aoptimize_instructions(
        self,
        evalset: List[Any],
        *,
        metric: Optional[Any] = None,
        scorer: Optional[Any] = None,
        criteria: str = "",
        n_candidates: int = 6,
        apply: bool = True,
    ) -> Any:
        """Async twin of :meth:`optimize_instructions`.

        The optimiser runs synchronous agent calls internally; this variant
        offloads the run to a worker thread so async callers never block the
        event loop.
        """
        import asyncio

        return await asyncio.to_thread(
            self.optimize_instructions,
            evalset,
            metric=metric,
            scorer=scorer,
            criteria=criteria,
            n_candidates=n_candidates,
            apply=apply,
        )

    def _ensure_skill_management_tools(self) -> None:
        """Ensure the agent has the ``skill_manage`` tool for authoring skills.

        Adds the skill-management tool (and lightweight file readers) to
        ``self.tools`` if they are not already present, so :meth:`learn` can
        author a skill without the caller wiring tools manually. Idempotent.
        """
        if not hasattr(self, 'tools') or self.tools is None:
            self.tools = []

        def _tool_id(tool: Any) -> str:
            # Mirror tool_execution.py: handle callables, dict/JSON specs, and
            # anything else via a stable string fallback so dedup never lets a
            # dict-form spec slip past the callable form (or vice versa).
            name = getattr(tool, '__name__', None)
            if isinstance(tool, dict):
                name = name or tool.get('name') or (tool.get('function') or {}).get('name')
            return name or str(tool)

        existing_names = {_tool_id(t) for t in self.tools}

        try:
            from praisonaiagents.tools.skill_tools import (
                skill_manage,
                read_skill_file,
                list_skill_scripts,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Could not import skill tools for learn_skill(): {exc}")
            return

        for tool in (skill_manage, read_skill_file, list_skill_scripts):
            if _tool_id(tool) not in existing_names:
                self.tools.append(tool)
                existing_names.add(_tool_id(tool))

    def execute(self, task: Any, context: Optional[Any] = None) -> Optional[str]:
        """Execute a task synchronously - backward compatibility method"""
        if hasattr(task, 'description'):
            prompt = task.description
        elif isinstance(task, str):
            prompt = task
        else:
            prompt = str(task)
        return self.chat(prompt)

    async def aexecute(self, task, context=None):
        """Execute a task asynchronously - backward compatibility method"""
        if hasattr(task, 'description'):
            prompt = task.description
        elif isinstance(task, str):
            prompt = task
        else:
            prompt = str(task)
        # Extract task info if available
        task_name = getattr(task, 'name', None)
        task_description = getattr(task, 'description', None)
        task_id = getattr(task, 'id', None)
        return await self.achat(prompt, task_name=task_name, task_description=task_description, task_id=task_id)

    async def execute_tool_async(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None, tools_override: Optional[List] = None) -> Any:
        """Async version of execute_tool with retry policy support.

        Routes through the user-supplied tool middleware (``Agent(hooks=[...])``)
        when present so ``before_tool``/``after_tool``/``wrap_tool_call`` gate
        async tool calls exactly as they do sync ones (security parity). The
        fast path (no tool hooks) calls straight into the retry loop with zero
        overhead.
        """

        # Record the tool name for this turn so the self-improve review policy
        # sees async tool usage too (issue #3037). Mirrors the sync path in
        # _execute_tool_with_context; skipped during a guarded review turn so
        # the review's own calls are not tracked and cannot recurse. Locked so
        # concurrent turns on the same Agent don't corrupt the buffer (#3307).
        self._record_turn_tool(function_name)

        # Result-aware tool-loop detection (async parity with the sync path in
        # tool_execution.py). Without this, an agent driven via achat()/astart()
        # that repeatedly calls the same tool with the same args gets no
        # stuck-loop detection, while the identical sync agent would be caught.
        # Zero overhead when the detector is disabled.
        _ld_enabled = False
        if hasattr(self, '_ensure_loop_detector'):
            from . import loop_detection as _loop_detection
            _ld_history, _ld_config = self._ensure_loop_detector()
            if _ld_config.enabled:
                _ld_enabled = True
                _loop_detection.record_tool_call(
                    _ld_history, function_name, arguments, _ld_config
                )
                _verdict = _loop_detection.detect_tool_loop(
                    _ld_history, function_name, arguments, _ld_config
                )
                if _verdict.get("stuck"):
                    if _verdict.get("level") == "critical":
                        return {
                            "error": _verdict.get("message", "loop detected"),
                            "loop_blocked": True,
                        }
                    elif not getattr(self, '_loop_warned_this_turn', False):
                        self._loop_warned_this_turn = True
                        self._pending_self_correction = (
                            f"[System: repeated {_verdict.get('detector')} detected. "
                            f"Try a different approach. {_verdict.get('message', '')}]"
                        )

        def _record_async_loop_outcome(_result):
            # Back-fill the result hash so the result-aware detector can tell a
            # genuine stall (identical output) from legitimate polling (changing
            # output) on the async path too. Without this, records keep
            # result_hash=None and no-progress detection never accumulates a
            # streak, so async poll-loops go undetected. Mirrors the sync
            # back-fill in tool_execution.py.
            if _ld_enabled:
                _loop_detection.record_tool_outcome(
                    _ld_history, function_name, arguments, _result, _ld_config
                )
            return _result

        # Enforce BEFORE_TOOL/AFTER_TOOL security hooks for every async caller,
        # mirroring the sync execute_tool path in tool_execution.py. Without
        # this the primary async path (_execute_unified_achat_completion) would
        # silently skip HookEvent.BEFORE_TOOL gating registered via
        # Agent(hooks=HookRegistry(...)). Zero overhead when no hooks apply.
        hook_runner = getattr(self, '_hook_runner', None)
        if hook_runner is not None:
            from ..hooks import HookEvent
            if hook_runner.registry.has_hooks(HookEvent.BEFORE_TOOL):
                from ..hooks import BeforeToolInput
                before_tool_input = BeforeToolInput(
                    session_id=getattr(self, '_session_id', 'default'),
                    cwd=os.getcwd(),
                    event_name=HookEvent.BEFORE_TOOL,
                    timestamp=str(time.time()),
                    agent_name=self.name,
                    tool_name=function_name,
                    tool_input=arguments,
                )
                before_results = await hook_runner.execute(
                    HookEvent.BEFORE_TOOL, before_tool_input, target=function_name
                )
                if hook_runner.is_blocked(before_results):
                    logging.warning(f"Tool {function_name} execution blocked by BEFORE_TOOL hook")
                    return f"Execution of {function_name} was blocked by security policy."
                for res in before_results:
                    if res.output and res.output.modified_input:
                        arguments.update(res.output.modified_input)

            result = await self._execute_tool_async_dispatch(
                function_name, arguments, tool_call_id, tools_override
            )

            if hook_runner.registry.has_hooks(HookEvent.AFTER_TOOL):
                from ..hooks import AfterToolInput
                after_tool_input = AfterToolInput(
                    session_id=getattr(self, '_session_id', 'default'),
                    cwd=os.getcwd(),
                    event_name=HookEvent.AFTER_TOOL,
                    timestamp=str(time.time()),
                    agent_name=self.name,
                    tool_name=function_name,
                    tool_input=arguments,
                    tool_output=result,
                )
                after_results = await hook_runner.execute(
                    HookEvent.AFTER_TOOL, after_tool_input, target=function_name
                )
                # Honour a post-tool block so a redacted/denied result never
                # reaches the model (mirrors the BEFORE_TOOL block path above).
                if hook_runner.is_blocked(after_results):
                    reason = hook_runner.get_blocking_reason(after_results)
                    logging.warning(f"Tool {function_name} result blocked by AFTER_TOOL hook")
                    return _record_async_loop_outcome(
                        reason or f"Result of {function_name} was blocked by security policy."
                    )
                # Read back any rewritten/redacted tool_output so a plugin can
                # scrub secrets before the result reaches the model.
                if getattr(after_tool_input, "tool_output", result) is not result:
                    result = after_tool_input.tool_output
                extra_context = hook_runner.aggregate_context(after_results)
                if extra_context:
                    if isinstance(result, str):
                        result = f"{result}\n\n{extra_context}"
                    elif isinstance(result, dict):
                        result.setdefault("_additional_context", extra_context)
            return _record_async_loop_outcome(result)

        return _record_async_loop_outcome(
            await self._execute_tool_async_dispatch(
                function_name, arguments, tool_call_id, tools_override
            )
        )

    async def _execute_tool_async_dispatch(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None, tools_override: Optional[List] = None) -> Any:
        """Route an async tool call through the middleware chain (if any) then retry loop."""
        # Route async tool calls through the same tool middleware chain as the
        # sync path. The chain (before_tool/after_tool/wrap_tool_call) is
        # synchronous, so we run it in a worker thread and bridge its final
        # handler back to this event loop via run_coroutine_threadsafe.
        manager = self._get_tool_middleware_manager()
        if manager is not None:
            return await self._execute_tool_async_via_middleware(
                manager, function_name, arguments, tool_call_id, tools_override
            )
        return await self._execute_tool_async_with_retry(
            function_name, arguments, tool_call_id, tools_override
        )

    async def _execute_tool_async_via_middleware(
        self, manager, function_name, arguments, tool_call_id, tools_override
    ):
        """Drive the (sync) tool middleware chain around an async tool call.

        The middleware manager and its ``wrap_tool_call`` chain are synchronous
        by contract, so they run in a thread-pool worker; the innermost handler
        schedules the actual async execution back on the current running loop
        and blocks the worker on the result. This preserves short-circuit,
        audit, and argument-mutation semantics for async tools.
        """
        from ..hooks import ToolRequest, ToolResponse, InvocationContext

        loop = asyncio.get_running_loop()
        request = ToolRequest(
            tool_name=function_name,
            arguments=arguments,
            context=InvocationContext(
                agent_id=self.name,
                run_id=getattr(self, '_current_run_id', 'unknown'),
                session_id=getattr(self, '_session_id', None) or 'default',
                tool_name=function_name,
                metadata={"tool_call_id": tool_call_id},
            ),
        )

        def _final_handler(req):
            future = asyncio.run_coroutine_threadsafe(
                self._execute_tool_async_with_retry(
                    req.tool_name, req.arguments, tool_call_id, tools_override
                ),
                loop,
            )
            result = future.result()
            return ToolResponse(tool_name=req.tool_name, result=result)

        def _run_chain():
            return manager.execute_tool_call(request, _final_handler)

        response = await loop.run_in_executor(None, _run_chain)
        return response.result if isinstance(response, ToolResponse) else response

    async def _execute_tool_async_with_retry(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None, tools_override: Optional[List] = None) -> Any:
        """Async tool execution with retry policy (middleware-agnostic core)."""
        from ..errors import ToolExecutionError

        # Get retry policy (tool-level > agent-level > default)
        retry_policy = self._get_tool_retry_policy(function_name)
        
        last_exception = None
        
        # Retry loop with exponential backoff
        for attempt in range(retry_policy.max_attempts):
            try:
                result = await self._execute_tool_async_impl(function_name, arguments, tool_call_id, tools_override)
                
                # Check if result is an error that should be retried
                if isinstance(result, dict) and result.get("error"):
                    # Skip retry for non-retryable errors (approval, permission, etc.).
                    # `retryable is False` covers async tool timeouts, whose executor
                    # work cannot be cancelled — retrying would duplicate side effects.
                    # `loop_blocked` is a terminal loop-guard decision — retrying would
                    # defeat the doom-loop protection this stop is meant to add.
                    if (result.get("approval_denied") or 
                        result.get("permission_denied") or 
                        result.get("approval_error") or
                        result.get("circuit_open") or
                        result.get("loop_blocked") or
                        result.get("_praison_retryable") is False):
                        result.pop("_praison_retryable", None)
                        return result

                    # The body already ran and may have completed its side effect
                    # before failing. Honour an explicit restart_safe=False /
                    # idempotent=False declaration, exactly as the sync loops do
                    # (tool_execution.py:884 and :2115). Without this the async
                    # path accepts the declaration and silently re-runs the tool
                    # up to max_attempts times -- charging a card three times for
                    # a tool the author marked "must never be silently re-executed".
                    if self._tool_declares_not_idempotent(function_name, tools_override):
                        result.pop("_praison_retryable", None)
                        return result

                    # Determine error type for retry policy
                    error_type = self._classify_error_type(result, last_exception)
                    
                    # Check if we should retry. A tool that *raised* is flattened
                    # into an error dict before it can be classified, so it always
                    # arrives here as "unknown" — which no default retry_on
                    # contains. The sync path escalates exactly those error types
                    # to its own retry loop (tool_execution.py:853-866); honouring
                    # the impl's explicit `retryable` flag is how the async path
                    # reaches the same decision instead of never retrying at all.
                    # `_praison_retryable` is a private control-plane key (see
                    # _execute_tool_async_impl): a tool's own result may legitimately
                    # contain "retryable" (common for HTTP-API wrappers) and must
                    # never steer our retry loop.
                    if (not retry_policy.should_retry(error_type, attempt)
                            and result.get("_praison_retryable") is not True):
                        result.pop("_praison_retryable", None)
                        return result
                    
                    # Don't retry on last attempt
                    if attempt == retry_policy.max_attempts - 1:
                        result.pop("_praison_retryable", None)
                        return result
                    
                    # Emit retry hook event  
                    delay_ms = retry_policy.get_delay_ms(attempt)
                    await self._emit_retry_hook_async(function_name, attempt + 1, delay_ms, result.get("error", "Unknown error"), retry_policy.max_attempts, error_type)
                    
                    # Wait before retry (async)
                    await asyncio.sleep(delay_ms / 1000.0)
                    continue
                else:
                    # Success - return result
                    return result
                    
            except ToolExecutionError:
                # A loop-guard HALT (raised in _execute_tool_async_impl) is a
                # terminal, non-retryable decision — let it propagate to stop the
                # run instead of retrying or swallowing it into an error dict.
                raise
            except Exception as e:
                last_exception = e
                # Determine if retryable
                is_retryable = not isinstance(e, (ValueError, TypeError, AttributeError))
                
                # Check if retryable and not last attempt
                if not is_retryable or attempt == retry_policy.max_attempts - 1:
                    # Return error dict instead of raising for consistency with sync version
                    return {"error": f"Error in execute_tool_async: {str(e)}"}
                
                # Determine error type  
                error_type = self._classify_error_type(None, e)
                
                if not retry_policy.should_retry(error_type, attempt):
                    return {"error": f"Error in execute_tool_async: {str(e)}"}
                
                # Emit retry hook event
                delay_ms = retry_policy.get_delay_ms(attempt)
                await self._emit_retry_hook_async(function_name, attempt + 1, delay_ms, str(e), retry_policy.max_attempts, error_type)
                
                # Wait before retry (async)
                await asyncio.sleep(delay_ms / 1000.0)
                continue
        
        # Should never reach here due to loop logic, but safety fallback
        if last_exception:
            return {"error": f"Error in execute_tool_async: {str(last_exception)}"}
        return {"error": "Maximum retry attempts exceeded"}

    async def _execute_tool_async_impl(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None, tools_override: Optional[List] = None) -> Any:
        """Internal async tool execution implementation"""
        from ..errors import ToolExecutionError
        try:
            logging.info(f"Executing async tool: {function_name} with arguments: {arguments}")
            
            # Check if approval is required for this tool (protocol-driven)
            try:
                result = await self._check_tool_approval_async(function_name, arguments)
                if isinstance(result, dict):
                    return result  # Error dict
                _, arguments = result
            except Exception as e:
                error_msg = f"Error during approval process: {str(e)}"
                logging.error(error_msg)
                return {"error": error_msg, "approval_error": True}

            # Policy/guardrail gate (protocol-driven). Mirrors the sync path in
            # _execute_tool_impl so async callers cannot bypass a PolicyEngine
            # deny or a tool-call guardrail. The check is pure/sync (no awaits).
            check = getattr(self, "_check_tool_policy_and_guardrails", None)
            if check is not None:
                policy_result = check(function_name, arguments)
                if isinstance(policy_result, dict):
                    return policy_result  # Error dict
                _, arguments = policy_result

            # Try to find the function in the override tools list first, then agent's tools list.
            # Resolve by BaseTool/FunctionTool ``.name`` (instances like BrowserBaseTool or
            # aliased decorated tools), plain callable ``__name__``, or class name so async
            # dispatch matches the robust sync resolution in _execute_tool_impl.
            func = None
            tools_to_search = tools_override if tools_override is not None else self.tools
            from ..tools.base import BaseTool
            for tool in tools_to_search:
                if isinstance(tool, BaseTool) and getattr(tool, 'name', None) == function_name:
                    func = tool
                    break
                if hasattr(tool, 'name') and getattr(tool, 'name', None) == function_name:
                    func = tool
                    break
                if (callable(tool) and getattr(tool, '__name__', '') == function_name) or \
                   (inspect.isclass(tool) and tool.__name__ == function_name):
                    func = tool
                    break
            
            if func is None:
                logging.error(f"Function {function_name} not found in tools")
                return {"error": f"Function {function_name} not found in tools"}

            # Circuit breaker (pre-execution) — parity with the sync path
            # (_execute_tool_with_circuit_breaker_impl). Without this the async
            # tool path never engages the per-agent breaker, so a persistently
            # failing external tool is hammered indefinitely via achat()/astart()
            # and the model never receives the ``circuit_open`` signal the async
            # retry loop already checks for. The helpers are pure/sync.
            breaker_precheck = getattr(self, '_circuit_breaker_precheck', None)
            if breaker_precheck is not None:
                open_result = breaker_precheck(function_name)
                if open_result is not None:
                    return open_result

            # Loop guard (pre-execution) — parity with the sync path in
            # tool_execution.py. The async path previously had no loop-guard or
            # doom-loop protection, so a repeatedly-failing tool could be hammered
            # every turn via achat()/async workflows. check() is pure/sync, so it
            # is safe to call here without awaiting.
            loop_guard = None
            if hasattr(self, '_ensure_loop_guard'):
                loop_guard = self._ensure_loop_guard()
                from ..escalation.loop_guard import GuardAction
                decision = loop_guard.check(function_name, arguments, is_pre_execution=True)
                if decision.action == GuardAction.BLOCK:
                    logging.warning(f"Loop guard blocked {function_name}: {decision.message}")
                    return {"error": f"[loop-guard] {decision.message}", "loop_blocked": True}
                elif decision.action == GuardAction.HALT:
                    raise ToolExecutionError(
                        f"[loop-guard] {decision.message}",
                        tool_name=function_name,
                        agent_id=self.name,
                        is_retryable=False,
                    )
                elif decision.action == GuardAction.WARN:
                    logging.warning(f"Loop guard warning for {function_name}: {decision.message}")

            # Activate the tool-progress channel so tools running under the async
            # path can stream incremental output (emit_tool_progress) and the
            # built-in todo tool can publish live updates (emit_todo_update),
            # mirroring the sync execute_tool path. Zero overhead when no stream
            # callbacks are registered — the sink stays None and the contextvar
            # is set to None (a no-op for emitters).
            _progress_sink = None
            _stream_emitter = self._get_existing_stream_emitter() if hasattr(self, "_get_existing_stream_emitter") else None
            if _stream_emitter is not None and _stream_emitter.has_callbacks:
                def _progress_sink(_event, _emitter=_stream_emitter):  # noqa: ANN001 — StreamEvent forwarder
                    _event.tool_call = {"name": function_name, "id": tool_call_id}
                    _event.agent_id = self.name
                    _emitter.emit(_event)

            from ..streaming.events import tool_progress_channel

            try:
                # BaseTool instances (plugin system, e.g. BrowserBaseTool) are not
                # directly callable — dispatch to their .run() method like the sync path.
                call_target = func.run if isinstance(func, BaseTool) else func
                try:
                    from .durable import get_durable_idempotency_key

                    durable_key = get_durable_idempotency_key()
                except ImportError:
                    durable_key = None
                call_arguments = arguments
                if durable_key:
                    try:
                        parameters = inspect.signature(call_target).parameters.values()
                    except (TypeError, ValueError):
                        parameters = ()
                    if any(
                        parameter.name == "idempotency_key"
                        or parameter.kind == inspect.Parameter.VAR_KEYWORD
                        for parameter in parameters
                    ):
                        call_arguments = dict(arguments)
                        call_arguments["idempotency_key"] = durable_key

                # Establish the injection context (Injected[T] params, including
                # the cooperative cancel_event) around dispatch so the async path
                # matches the sync execute_tool path. Without this, a long-running
                # tool (e.g. shell) executed via achat()/astart() never observes an
                # interrupt and runs until its own timeout. Built lazily and reused
                # for both the coroutine and executor branches.
                from ..tools.injected import with_injection_context
                _inject_state = None
                if hasattr(self, "_build_agent_state"):
                    try:
                        _inject_state = self._build_agent_state()
                    except Exception:
                        _inject_state = None

                async def _invoke():
                    # Set the tool-progress channel BEFORE dispatch so the sink
                    # propagates into the executor thread via contextvars, mirroring
                    # the sync execute_tool path.
                    if inspect.iscoroutinefunction(call_target):
                        logging.debug(f"Executing async function: {function_name}")
                        if _inject_state is not None:
                            with with_injection_context(_inject_state), tool_progress_channel(_progress_sink):
                                return await call_target(**call_arguments)
                        with tool_progress_channel(_progress_sink):
                            return await call_target(**call_arguments)
                    logging.debug(f"Executing sync function in executor: {function_name}")
                    loop = asyncio.get_running_loop()
                    from ..trace.context_events import copy_context_to_callable
                    # copy_context_to_callable snapshots the CURRENT context (incl.
                    # the injection contextvar) into the executor thread, so setting
                    # it here propagates cancel_event to the sync tool body too.
                    if _inject_state is not None:
                        with with_injection_context(_inject_state), tool_progress_channel(_progress_sink):
                            return await loop.run_in_executor(
                                None, copy_context_to_callable(lambda: call_target(**call_arguments))
                            )
                    with tool_progress_channel(_progress_sink):
                        return await loop.run_in_executor(
                            None, copy_context_to_callable(lambda: call_target(**call_arguments))
                        )

                # Circuit-breaker parity with the sync path (tool_execution.py).
                # The async tool path previously had no breaker, so a repeatedly
                # failing tool could be hammered every turn via achat()/async
                # workflows. Wrap the invocation through the same per-agent/per-tool
                # breaker (CircuitBreaker.acall is event-loop safe) so repeated
                # failures OPEN the circuit and short-circuit further calls. A
                # CircuitBreakerException is surfaced as an error dict carrying
                # circuit_open=True, which the retry loop in
                # _execute_tool_async_with_retry already treats as terminal.
                breaker = None
                # Sentinel exception type so the `except` clause below is always a
                # valid type even when the circuit_breaker module is unavailable
                # (a never-raised local class never matches a real exception).
                class _CircuitBreakerException(Exception):
                    pass
                try:
                    from ..tools.circuit_breaker import (
                        get_circuit_breaker,
                        CircuitBreakerConfig,
                        CircuitBreakerException as _CircuitBreakerException,
                    )
                    breaker_name = f"tool_{id(self)}_{function_name}"
                    breaker = get_circuit_breaker(
                        breaker_name,
                        CircuitBreakerConfig(
                            failure_threshold=5,
                            recovery_timeout=60.0,
                            timeout=30.0,
                            graceful_degradation=True,
                        ),
                    )
                    if hasattr(self, "_register_breaker_finalizer"):
                        self._register_breaker_finalizer(breaker_name)
                except ImportError:
                    # Circuit breaker not available - fall back to direct invocation.
                    logging.debug("Circuit breaker not available on async path, executing directly")

                # Sentinel used to register an error-dict result as a breaker
                # failure without losing the dict, mirroring the sync path's
                # _ToolFailure wrapper (tool_execution.py). Approval/permission/
                # policy/guardrail denials are NOT treated as breaker failures.
                class _ToolFailure(Exception):
                    def __init__(self, error_dict):
                        self.error_dict = error_dict
                        super().__init__(error_dict.get("error", "Tool execution failed"))

                async def _invoke_for_breaker():
                    r = await _invoke()
                    if isinstance(r, dict) and r.get("error") and \
                       not r.get("approval_denied") and \
                       not r.get("permission_denied") and \
                       not r.get("approval_error") and \
                       not r.get("policy_denied") and \
                       not r.get("guardrail_denied"):
                        raise _ToolFailure(r)
                    return r

                async def _invoke_guarded():
                    if breaker is None:
                        return await _invoke()
                    try:
                        return await breaker.acall(_invoke_for_breaker)
                    except _ToolFailure as tf:
                        # Failure was counted by the breaker; return the original dict.
                        return tf.error_dict

                def _circuit_open_result():
                    # Record the rejection as a failure so repeated open-circuit
                    # rejections still feed the loop guard, then surface an error
                    # dict carrying circuit_open=True — the retry loop in
                    # _execute_tool_async_with_retry treats it as terminal.
                    if loop_guard is not None:
                        loop_guard.record(function_name, arguments, False, result=None)
                    return {
                        "error": f"Tool '{function_name}' circuit breaker open - too many recent failures",
                        "circuit_open": True,
                        "agent_name": getattr(self, "name", None),
                        "session_id": getattr(self, "_session_id", None),
                        "remediation": "Wait for recovery_timeout (60s) or investigate recent tool failures.",
                    }

                # Apply the per-agent tool timeout (ToolConfig.timeout) so the async
                # path matches the sync path in tool_execution.py. asyncio.wait_for
                # cannot kill a stuck sync tool running in the executor (same caveat
                # the sync path has with future.cancel()), but it stops the awaiting
                # coroutine from hanging forever, which is the actual defect.
                tool_timeout = getattr(self, '_tool_timeout', None)
                if tool_timeout and tool_timeout > 0:
                    try:
                        result = await asyncio.wait_for(_invoke_guarded(), timeout=tool_timeout)
                    except _CircuitBreakerException as cbe:
                        logging.warning(f"Tool '{function_name}' circuit breaker open: {cbe}")
                        return _circuit_open_result()
                    except asyncio.TimeoutError:
                        logging.warning(f"Tool {function_name} timed out after {tool_timeout}s")
                        # Mark as non-retryable: asyncio.wait_for cannot cancel a sync
                        # tool already running in the executor, so retrying would launch
                        # a duplicate invocation while the original keeps executing —
                        # duplicating DB writes / API calls / file mutations. Surface the
                        # timeout once instead of re-running an uncancellable side effect.
                        # Fall through (not return) so the loop guard records this
                        # timeout as a failure — repeated timeouts must accumulate
                        # toward the BLOCK/HALT thresholds like any other failure.
                        result = {
                            "error": f"Tool timed out after {tool_timeout}s",
                            "timeout": True,
                            "_praison_retryable": False,
                        }
                else:
                    try:
                        result = await _invoke_guarded()
                    except _CircuitBreakerException as cbe:
                        logging.warning(f"Tool '{function_name}' circuit breaker open: {cbe}")
                        return _circuit_open_result()

                # Circuit breaker (post-execution) — record the outcome so
                # repeated failures open the breaker, mirroring the sync path's
                # breaker.call. Approval/permission/policy/guardrail denials are
                # NOT counted as tool failures (same exclusions the sync wrapper
                # applies in _execute_tool_with_circuit_breaker_impl), so a gated
                # tool never trips the breaker.
                breaker_record = getattr(self, '_circuit_breaker_record', None)
                if breaker_record is not None:
                    is_breaker_failure = (
                        isinstance(result, dict)
                        and result.get("error")
                        and not result.get("approval_denied")
                        and not result.get("permission_denied")
                        and not result.get("approval_error")
                        and not result.get("policy_denied")
                        and not result.get("guardrail_denied")
                    )
                    breaker_record(function_name, not is_breaker_failure)

                # Loop guard (post-execution) — record the outcome and surface a
                # block/halt decision back to the model on this same turn, mirroring
                # the sync path in tool_execution.py so repeated failures accumulate
                # toward the BLOCK/HALT thresholds instead of retrying unbounded.
                if loop_guard is not None:
                    is_success = result is not None and not (isinstance(result, dict) and result.get('error'))
                    loop_guard.record(function_name, arguments, is_success, result=result)
                    decision = loop_guard.check(function_name, arguments, is_pre_execution=False)
                    if decision.action.value in ("warn", "block", "halt"):
                        if isinstance(result, str):
                            result = f"{result}\n\n[loop-guard] {decision.message}"
                        elif isinstance(result, dict):
                            result["_loop_guard"] = {"message": decision.message, "action": decision.action.value}
                        else:
                            result = {"value": result, "_loop_guard": {"message": decision.message, "action": decision.action.value}}

                # Ensure result is JSON serializable
                logging.debug(f"Raw result from tool: {result}")
                if result is None:
                    return {"result": None}
                try:
                    json.dumps(result)  # Test serialization
                    return result
                except TypeError:
                    logging.warning(f"Result not JSON serializable, converting to string: {result}")
                    return {"result": str(result)}

            except Exception as e:
                logging.error(f"Error executing {function_name}: {str(e)}", exc_info=True)
                # Circuit breaker (failure on raised exception) — a raised tool
                # exception is a failure just like an error-dict result, and the
                # sync path's ``breaker.call`` counts it. Record it here so the
                # breaker still opens after repeated raises; otherwise the
                # post-invoke record block above is skipped and raised failures
                # never trip the breaker. Approval/permission/policy/guardrail
                # denials surface as error dicts (handled above), not raises, so
                # this path only ever sees genuine tool failures.
                breaker_record = getattr(self, '_circuit_breaker_record', None)
                if breaker_record is not None:
                    breaker_record(function_name, False)
                # Record the failed invocation so repeated identical failures
                # accumulate toward the loop-guard BLOCK/HALT thresholds — a raised
                # tool exception is a failure just like an error-dict result on the
                # sync path. The next pre-execution check will then BLOCK/HALT.
                if loop_guard is not None:
                    loop_guard.record(function_name, arguments, False, result=None)
                # Carry the retry verdict with the flattened exception. Without it
                # the caller only sees an opaque error string, classifies it as
                # "unknown" (never in RetryPolicy.retry_on) and gives up — while
                # the sync path, which still has the exception object, retries.
                # Mirror the sync path exactly: a ToolExecutionError already
                # carries an explicit is_retryable verdict (e.g. a terminal
                # non-retryable failure) and must be honoured verbatim; for any
                # other exception apply the same terminal rule — programming
                # errors are terminal, everything else may be retried.
                if isinstance(e, ToolExecutionError):
                    retryable = e.is_retryable
                else:
                    retryable = not isinstance(e, (ValueError, TypeError, AttributeError))
                # Private control-plane key: a tool's own result may legitimately
                # contain "retryable" (common for HTTP-API wrappers) and must not
                # collide with the framework's verdict nor leak to the model.
                return {
                    "error": f"Error executing {function_name}: {str(e)}",
                    "_praison_retryable": retryable,
                }

        except ToolExecutionError:
            # A loop-guard HALT must propagate to stop the run, mirroring the sync
            # path; do not swallow it into an error dict.
            raise
        except Exception as e:
            logging.error(f"Error in execute_tool_async: {str(e)}", exc_info=True)
            return {"error": f"Error in execute_tool_async: {str(e)}"}

    def launch(self, path: str = '/', port: int = 8000, host: str = '127.0.0.1', debug: bool = False, protocol: str = "http"):
        """
        Launch the agent as an HTTP API endpoint or MCP server.
        
        This method now delegates to protocol-based launchers to follow
        the protocol-driven architecture. Heavy implementations (FastAPI/uvicorn)
        are only imported when needed through lazy loading.

        Request authorisation matches ``PraisonAIAgents.launch``: when
        ``PRAISONAI_LAUNCH_AUTH_TOKEN`` is set, every HTTP route requires that
        bearer token (401 otherwise). When it is unset and ``host`` is
        non-loopback, a one-time token is generated and printed rather than
        serving an unauthenticated endpoint on all interfaces.

        Args:
            path: API endpoint path (default: '/') for HTTP, or base path for MCP.
            port: Server port (default: 8000)
            host: Server host (default: '127.0.0.1'; changed from '0.0.0.0' to
                avoid binding all interfaces by default — pass '0.0.0.0'
                explicitly to expose externally).
            debug: Enable debug mode (default: False)
            protocol: "http" to launch as FastAPI, "mcp" to launch as MCP server.
            
        Returns:
            None
        """
        # Delegate to protocol-specific launcher
        if protocol == "http":
            return self._launch_http_server(path, port, host, debug)
        elif protocol == "mcp":
            return self._launch_mcp_server(path, port, host, debug)
        else:
            raise ValueError(f"Unsupported protocol: {protocol}. Use 'http' or 'mcp'")

    def _launch_http_server(self, path: str, port: int, host: str, debug: bool):
        """
        Launch HTTP server using FastAPI (internal implementation).
        
        NOTE: This implementation will be moved to wrapper layer in future version.
        For now, it maintains backward compatibility while following lazy import patterns.
        """
        global _server_started, _registered_agents, _shared_apps, _server_lock

        from .launch_security import authorise_launch_request, resolve_launch_host

        # Try to import FastAPI dependencies - lazy loading
        try:
            import uvicorn
            from fastapi import FastAPI, HTTPException, Request
            from fastapi.responses import JSONResponse
            from pydantic import BaseModel
            import threading
            import time
            import asyncio
            
            # Define the request model here since we need pydantic
            class AgentQuery(BaseModel):
                query: str
                    
        except ImportError as e:
            # Check which specific module is missing
            missing_module = str(e).split("No module named '")[-1].rstrip("'")
            _get_display_functions()['display_error'](f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
            logging.error(f"Missing dependency: {missing_module}. Required for launch() method with HTTP mode.")
            print(f"\nTo add API capabilities, install the required dependencies:")
            print(f"pip install {missing_module}")
            print("\nOr install all API dependencies with:")
            print("pip install 'praisonaiagents[api]'")
            return None

        # Fail-closed bind guard: refuse to serve keyless on a non-loopback host
        # (auto-generates and prints a one-time token instead). Matches the
        # serve/jobs precedent and keeps this path in lock-step with
        # PraisonAIAgents.launch. Applied only after the dependency guard above
        # so a launch that bails out (missing deps) cannot mutate the
        # process-wide launch token and retroactively 401 a running endpoint.
        host = resolve_launch_host(host)

        should_start = False
        with _server_lock:
            # Initialize port-specific collections if needed (once per port)
            if port not in _registered_agents:
                _registered_agents[port] = {}

            # Initialize shared FastAPI app if not already created for this port
            if _shared_apps.get(port) is None:
                _shared_apps[port] = FastAPI(
                    title=f"PraisonAI Agents API (Port {port})",
                    description="API for interacting with PraisonAI Agents"
                )

                # Add a root endpoint with a welcome message
                @_shared_apps[port].get("/")
                async def root():
                    return {
                        "message": f"Welcome to PraisonAI Agents API on port {port}. See /docs for usage.",
                        "endpoints": list(_registered_agents[port].keys())
                    }

                # Add healthcheck endpoint
                @_shared_apps[port].get("/health")
                async def healthcheck():
                    return {
                        "status": "ok",
                        "endpoints": list(_registered_agents[port].keys())
                    }

            # The path registration below must run on EVERY call, not just when the
            # port is new, so multiple agents can share a single port.

            # Normalize path to ensure it starts with /
            if not path.startswith('/'):
                path = f'/{path}'

            # Check if path is already registered for this port
            if path in _registered_agents[port]:
                logging.warning(f"Path '{path}' is already registered on port {port}. Please use a different path.")
                print(f"⚠️ Warning: Path '{path}' is already registered on port {port}.")
                # Use a modified path to avoid conflicts
                original_path = path
                path = f"{path}_{self.agent_id[:6]}"
                logging.warning(f"Using '{path}' instead of '{original_path}'")
                print(f"🔄 Using '{path}' instead")

            # Register the agent to this path
            _registered_agents[port][path] = self.agent_id

            # Define the endpoint handler
            @_shared_apps[port].post(path)
            async def handle_agent_query(request: Request, query_data: Optional[AgentQuery] = None):
                if not authorise_launch_request(request):
                    raise HTTPException(status_code=401, detail="Unauthorized")
                # Handle both direct JSON with query field and form data
                if query_data is None:
                    try:
                        request_data = await request.json()
                        if "query" not in request_data:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                        query = request_data["query"]
                    except Exception:
                        # Fallback to form data or query params
                        form_data = await request.form()
                        if "query" in form_data:
                            query = form_data["query"]
                        else:
                            raise HTTPException(status_code=400, detail="Missing 'query' field in request")
                else:
                    query = query_data.query

                try:
                    # Use async version if available, otherwise use sync version
                    if asyncio.iscoroutinefunction(self.chat):
                        response = await self.achat(query, task_name=None, task_description=None, task_id=None)
                    else:
                        # Run sync function in a thread to avoid blocking
                        loop = asyncio.get_running_loop()
                        response = await loop.run_in_executor(None, lambda p=query: self.chat(p))

                    return {"response": response}
                except Exception as e:
                    logging.error(f"Error processing query: {str(e)}", exc_info=True)
                    return JSONResponse(
                        status_code=500,
                        content={"error": f"Error processing query: {str(e)}"}
                    )

            # Invalidate the cached OpenAPI schema so routes registered by later
            # shared-port launch() calls still show up in /openapi.json and /docs.
            # FastAPI caches app.openapi_schema on first access and does not
            # regenerate it when new routes are added afterwards.
            _shared_apps[port].openapi_schema = None

            print(f"🚀 Agent '{self.name}' available at http://{host}:{port}")

            # Check and mark server as started atomically to prevent race conditions
            should_start = not _server_started.get(port, False)
            if should_start:
                _server_started[port] = True

        # Server start/wait outside the lock to avoid holding it during sleep
        if should_start:
            # Start the server in a separate thread
            def run_server():
                try:
                    print(f"✅ FastAPI server started at http://{host}:{port}")
                    print(f"📚 API documentation available at http://{host}:{port}/docs")
                    print(f"🔌 Available endpoints: {', '.join(list(_registered_agents[port].keys()))}")
                    uvicorn.run(_shared_apps[port], host=host, port=port, log_level="debug" if debug else "info")
                except Exception as e:
                    logging.error(f"Error starting server: {str(e)}", exc_info=True)
                    print(f"❌ Error starting server: {str(e)}")

            # Run server in a background thread
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

            # Wait for a moment to allow the server to start and register endpoints
            self._safe_sleep(0.5)
        else:
            # If server is already running, wait a moment to make sure the endpoint is registered
            self._safe_sleep(0.1)
            print(f"🔌 Available endpoints on port {port}: {', '.join(list(_registered_agents[port].keys()))}")

        # Get the stack frame to check if this is the last launch() call in the script
        import inspect
        stack = inspect.stack()

        # If this is called from a Python script (not interactive), try to detect if it's the last launch call
        if len(stack) > 1 and stack[1].filename.endswith('.py'):
            caller_frame = stack[1]
            caller_line = caller_frame.lineno

            try:
                # Read the file to check if there are more launch calls after this one
                with open(caller_frame.filename, 'r') as f:
                    lines = f.readlines()

                # Check if there are more launch() calls after the current line
                has_more_launches = False
                for line_content in lines[caller_line:]: # renamed line to line_content
                    if '.launch(' in line_content and not line_content.strip().startswith('#'):
                        has_more_launches = True
                        break

                # If this is the last launch call, block the main thread
                if not has_more_launches:
                    try:
                        print("\nAll agents registered for HTTP mode. Press Ctrl+C to stop the servers.")
                        while True:
                            self._safe_sleep(1)
                    except KeyboardInterrupt:
                        print("\nServers stopped")
            except Exception as e:
                # If something goes wrong with detection, block anyway to be safe
                logging.error(f"Error in launch detection: {e}")
                try:
                    print("\nKeeping HTTP servers alive. Press Ctrl+C to stop.")
                    while True:
                        self._safe_sleep(1)
                except KeyboardInterrupt:
                    print("\nServers stopped")
        return None

    def _launch_mcp_server(self, path: str, port: int, host: str, debug: bool):
        """
        Launch this single agent as an MCP server.

        Delegates to the ``praisonai-mcp`` agent adapter via ``serve_agents([self])``
        so that ``Agent.launch(protocol="mcp")`` and
        ``PraisonAIAgents.launch(protocol="mcp")`` share one code path and one
        vocabulary (publishing ``ask_{agent_name}`` + ``list_agents``). The mcp
        package is an optional dependency imported lazily here so core keeps no
        hard dependency on it.
        """
        try:
            from praisonai_mcp import serve_agents

            # Keep the call inside the ImportError guard: serve_agents() lazily
            # imports its transport backend, so a package that is installed
            # without its optional transport extras surfaces the missing
            # dependency here rather than at the import line above. Catching it
            # in the same place yields one actionable install message instead of
            # an uncaught traceback.
            return serve_agents([self], host=host, port=port)
        except ImportError:
            _get_display_functions()['display_error'](
                "MCP serving requires the 'praisonai-mcp' package."
            )
            print("\nTo add MCP capabilities, install: pip install praisonai-mcp")
            return None

    async def _emit_retry_hook_async(self, tool_name, attempt, delay_ms, error, max_attempts, error_type):
        """Emit ON_RETRY hook event (async version).
        
        Args:
            tool_name: Name of the tool being retried
            attempt: Current attempt number (1-based)
            delay_ms: Delay before retry in milliseconds
            error: Error message or description
            max_attempts: Maximum number of attempts configured
            error_type: Classified error type
        """
        try:
            from ..hooks import HookEvent, OnRetryInput
            
            # Only emit if we have a hook runner
            hook_runner = getattr(self, '_hook_runner', None)
            if hook_runner is None:
                return
            
            retry_input = OnRetryInput(
                session_id=getattr(self, '_session_id', 'default'),
                cwd=os.getcwd(),
                event_name=HookEvent.ON_RETRY,
                timestamp=str(time.time()),
                agent_name=self.name,
                tool_name=tool_name,
                attempt=attempt,
                delay_ms=delay_ms,
                error=error,
                max_attempts=max_attempts,
                error_type=error_type
            )
            
            # Execute hook asynchronously if supported, otherwise use sync
            if hasattr(hook_runner, 'execute_async'):
                await hook_runner.execute_async(HookEvent.ON_RETRY, retry_input, target=tool_name)
            else:
                # Fallback to sync execution in executor to avoid blocking event loop
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: hook_runner.execute_sync(HookEvent.ON_RETRY, retry_input, target=tool_name)
                )
            
        except Exception as e:
            # Don't let hook failures break retry logic
            logging.debug(f"Failed to emit async retry hook: {e}")

