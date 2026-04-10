"""
Execution and orchestration mixin for the Agent class.

Contains all methods for run/start/launch lifecycle, planning,
and server endpoints. Extracted from agent.py for maintainability.
"""

import os
import time
import json
import logging
from praisonaiagents._logging import get_logger

import asyncio
import threading


# Fallback helpers to avoid circular imports
def _get_console():
    from rich.console import Console
    return Console

def _get_live():
    from rich.live import Live
    return Live

def _get_display_functions():
    from ..main import (
        display_error, display_instruction, display_interaction,
        display_generating, display_self_reflection, ReflectionOutput,
        adisplay_instruction, execute_sync_callback
    )
    return {
        'display_error': display_error,
        'display_instruction': display_instruction,
        'display_interaction': display_interaction,
        'display_generating': display_generating,
        'display_self_reflection': display_self_reflection,
        'ReflectionOutput': ReflectionOutput,
        'adisplay_instruction': adisplay_instruction,
        'execute_sync_callback': execute_sync_callback,
    }

logger = logging.getLogger(__name__)



from typing import List, Optional, Any, Dict, Union, Generator, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ExecutionMixin:
    """Mixin providing execution methods for the Agent class."""

    def _safe_sleep(self, duration: float) -> None:
        """Synchronous sleep - safe for sync contexts only."""
        time.sleep(duration)

    async def _safe_sleep_async(self, duration: float) -> None:
        """Async sleep - use this in async contexts."""
        await asyncio.sleep(duration)

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

    async def arun(self, prompt: str, **kwargs):
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
            **kwargs: Additional arguments passed to achat()
            
        Returns:
            The agent's response as a string, or AutonomyResult if autonomy enabled
            
        Note:
            If autonomy=True was set on the agent, astart() automatically uses
            the autonomous loop (run_autonomous_async) instead of single-turn chat.
        """
        import sys
        
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
                
        Returns:
            The agent's response as a string
            
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
        # Production defaults: no streaming, no display
        if 'stream' not in kwargs:
            kwargs['stream'] = False
        
        # Substitute dynamic variables ({{today}}, {{now}}, {{uuid}}, etc.)
        if prompt and "{{" in prompt:
            from praisonaiagents.utils.variables import substitute_variables
            prompt = substitute_variables(prompt, {})
        
        # Load history context
        self._load_history_context()
        
        # Check if planning mode is enabled
        if self.planning:
            result = self._start_with_planning(prompt, **kwargs)
        else:
            result = self.chat(prompt, **kwargs)
        
        # Auto-save session if enabled
        self._auto_save_session()
        
        return result

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
                    from ..main import PRAISON_COLORS, sync_display_callbacks
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
                    
                    # Store original callback and register ours
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
                            result_holder[0] = self.chat(prompt, **kwargs)
                            current_status[0] = "Finalizing response..."
                        except Exception as e:
                            error_holder[0] = e
                        finally:
                            self.verbose = original_verbose_chat
                            # Restore original callback
                            if original_tool_callback:
                                sync_display_callbacks['tool_call'] = original_tool_callback
                            elif 'tool_call' in sync_display_callbacks:
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

    async def execute_tool_async(self, function_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None) -> Any:
        """Async version of execute_tool"""
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
            
            # Try to find the function in the agent's tools list first
            func = None
            for tool in self.tools:
                if (callable(tool) and getattr(tool, '__name__', '') == function_name):
                    func = tool
                    break
            
            if func is None:
                logging.error(f"Function {function_name} not found in tools")
                return {"error": f"Function {function_name} not found in tools"}

            try:
                if inspect.iscoroutinefunction(func):
                    logging.debug(f"Executing async function: {function_name}")
                    result = await func(**arguments)
                else:
                    logging.debug(f"Executing sync function in executor: {function_name}")
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, lambda: func(**arguments))
                
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
                return {"error": f"Error executing {function_name}: {str(e)}"}

        except Exception as e:
            logging.error(f"Error in execute_tool_async: {str(e)}", exc_info=True)
            return {"error": f"Error in execute_tool_async: {str(e)}"}

    def launch(self, path: str = '/', port: int = 8000, host: str = '0.0.0.0', debug: bool = False, protocol: str = "http"):
        """
        Launch the agent as an HTTP API endpoint or MCP server.
        
        This method now delegates to protocol-based launchers to follow
        the protocol-driven architecture. Heavy implementations (FastAPI/uvicorn)
        are only imported when needed through lazy loading.
        
        Args:
            path: API endpoint path (default: '/') for HTTP, or base path for MCP.
            port: Server port (default: 8000)
            host: Server host (default: '0.0.0.0')
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
                
        with _server_lock:
            # Initialize port-specific collections if needed
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
        Launch MCP server (internal implementation).
        
        NOTE: This implementation will be moved to wrapper layer in future version.
        For now, it maintains backward compatibility while following lazy import patterns.
        """
        # For now, delegate to the existing MCP implementation 
        # This will be extracted to a proper adapter in the future
        try:
            import uvicorn
            from mcp.server.fastmcp import FastMCP
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Mount
            import threading
            import time
            import asyncio
            
            mcp_server_instance_name = f"{self.name}_mcp_server" if self.name else "agent_mcp_server"
            mcp = FastMCP(mcp_server_instance_name)

            # Determine the MCP tool name based on self.name
            actual_mcp_tool_name = f"execute_{self.name.lower().replace(' ', '_').replace('-', '_')}_task" if self.name else "execute_task"

            @mcp.tool(name=actual_mcp_tool_name)
            async def execute_agent_task(prompt: str) -> str:
                """Executes the agent's primary task with the given prompt."""
                try:
                    if hasattr(self, 'achat') and asyncio.iscoroutinefunction(self.achat):
                        response = await self.achat(prompt, tools=self.tools, task_name=None, task_description=None, task_id=None)
                    elif hasattr(self, 'chat'):
                        from ..trace.context_events import copy_context_to_callable
                        loop = asyncio.get_event_loop()
                        response = await loop.run_in_executor(None, copy_context_to_callable(lambda p=prompt: self.chat(p, tools=self.tools)))
                    else:
                        return f"Error: Agent {self.name} misconfigured for MCP."
                    return response if response is not None else "Agent returned no response."
                except Exception as e:
                    return f"Error executing task: {str(e)}"

            # Create and run MCP server
            transport = SseServerTransport(f"{path}/sse")
            starlette_app = Starlette(
                routes=[Mount(f"{path}", mcp.create_app())]
            )

            def run_mcp_server():
                try:
                    uvicorn.run(starlette_app, host=host, port=port, log_level="debug" if debug else "info")
                except Exception as e:
                    logging.error(f"Error starting MCP server: {str(e)}", exc_info=True)

            server_thread = threading.Thread(target=run_mcp_server, daemon=True)
            server_thread.start()
            self._safe_sleep(0.5)

            try:
                print("\nKeeping MCP server alive. Press Ctrl+C to stop.")
                while True:
                    self._safe_sleep(1)
            except KeyboardInterrupt:
                print("\nMCP Server stopped")
            return None
            
        except ImportError as e:
            missing_module = str(e).split("No module named '")[-1].rstrip("'")
            _get_display_functions()['display_error'](f"Missing dependency: {missing_module}. Required for MCP mode.")
            print(f"\nTo add MCP capabilities, install: pip install {missing_module}")
            return None 

