"""
Interactive REPL for PraisonAI.

This is the main entry point for interactive chat mode.
Uses PraisonIO for input/output (prompt_toolkit is used SYNCHRONOUSLY).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .praison_io import PraisonIO, IOConfig

logger = logging.getLogger(__name__)

# Sentinel marking a failed registry build so it is not retried every command.
_REGISTRY_FAILED = object()


@dataclass
class REPLConfig:
    """Configuration for the interactive REPL."""
    model: str = "gpt-4o-mini"
    verbose: bool = False
    memory: bool = False
    tools: Optional[List] = None
    session_id: Optional[str] = None
    continue_session: bool = False
    workspace: Optional[str] = None
    autonomy: bool = True


# Default slash commands
DEFAULT_COMMANDS: Dict[str, str] = {
    "help": "Show available commands",
    "exit": "Exit interactive mode",
    "quit": "Exit interactive mode",
    "clear": "Clear conversation history",
    "session": "Show current session info",
    "model": "Show or change model",
    "cost": "Show token usage and cost",
    "history": "Show conversation history",
    "export": "Export conversation to file",
    "compact": "Toggle compact output mode",
    "multiline": "Toggle multiline input mode",
    "btw": "Ask a side question in a throwaway context (main task untouched)",
    "undo": "Undo the last turn (files + conversation)",
    "revert": "Revert the last N turns (files + conversation)",
}


class _InMemoryConversationStore:
    """Adapt the REPL's in-memory history list to the checkpoint store surface.

    ``SessionCheckpointManager`` rewinds a conversation via the small
    ``get_messages``/``revert_to_message``/``clear_messages`` protocol (mirroring
    the core ``HierarchicalSessionStore``). The modern REPL keeps history as a
    plain ``list[dict]`` rather than a persisted store, so this thin adapter lets
    the *same* coherent revert engine keep files and chat history in lockstep on
    the default path — no new persistence layer, just a view over the list.

    The interactive surfaces reuse a single warm ``Agent`` across turns, so the
    agent keeps its **own** ``chat_history`` that grows independently of this
    view. Rewinding only the view would leave the reused agent replaying the
    undone exchange on the next turn. When an ``agent_provider`` is supplied the
    adapter also truncates the live agent's ``chat_history`` to the same
    turn boundary (matched by user-message count, so it is robust to interleaved
    tool/system messages), keeping the agent's active context in lockstep too.
    """

    def __init__(self, history: List[Dict], agent_provider=None):
        self._history = history
        self._agent_provider = agent_provider

    def get_messages(self, session_id):  # noqa: ARG002 - single-session view
        return list(self._history)

    def revert_to_message(self, session_id, message_index):  # noqa: ARG002
        if message_index < 0 or message_index >= len(self._history):
            return False
        del self._history[message_index + 1:]
        self._sync_agent_history()
        return True

    def clear_messages(self, session_id):  # noqa: ARG002
        self._history.clear()
        self._sync_agent_history()
        return True

    def _sync_agent_history(self) -> None:
        """Rewind the reused agent's ``chat_history`` to the same boundary.

        Matches by the number of ``user`` messages remaining in the view so that
        interleaved system/tool/assistant messages in the agent's own history do
        not throw the boundary off. Best-effort and non-raising: a warm-agent
        sync failure must never corrupt the already-restored files/history.
        """
        provider = self._agent_provider
        if provider is None:
            return
        try:
            agent = provider()
            if agent is None:
                return
            history = getattr(agent, "chat_history", None)
            if history is None:
                return
            keep_user_turns = sum(
                1 for m in self._history
                if isinstance(m, dict) and m.get("role") == "user"
            )
            new_history: List[Dict] = []
            seen_user = 0
            for msg in history:
                role = msg.get("role") if isinstance(msg, dict) else None
                if role == "user":
                    if seen_user >= keep_user_turns:
                        break
                    seen_user += 1
                new_history.append(msg)
            agent.chat_history = new_history
        except Exception:
            pass


class InteractiveREPL:
    """
    Interactive REPL for PraisonAI chat.
    
    Key design:
    - Uses PraisonIO for all I/O (prompt_toolkit used synchronously)
    - Agent execution is async but input is sync
    - Clean separation between I/O and agent logic
    """
    
    def __init__(
        self,
        config: Optional[REPLConfig] = None,
        io_config: Optional[IOConfig] = None,
    ):
        self.config = config or REPLConfig()
        self.io = PraisonIO(io_config)
        self._agent = None
        self._running = False
        self._conversation_history: List[Dict] = []
        self._session_id: Optional[str] = None
        self._total_tokens = 0
        self._total_cost = 0.0
        self._registry = None  # Unified command registry (lazy)
        self._pending_context: List[str] = []  # `!!cmd` output for next turn
        self._checkpoints = None  # SessionCheckpointManager (lazy)
        self._checkpoints_ready = False
        
        # Setup commands
        self.io.add_commands(DEFAULT_COMMANDS)

    def _get_checkpoints(self):
        """Lazily build the coherent turn-checkpoint manager for this session.

        Binds ``SessionCheckpointManager`` to a view over the REPL's in-memory
        conversation history so ``/undo`` and ``/revert`` roll back **files and
        chat history together** — the same engine the legacy REPL uses, now on
        the default path. Enabled by default for interactive runs (``default``
        ``True``); opt out with ``checkpoints.auto: false`` or
        ``PRAISONAI_CHECKPOINTS=off``. Degrades to ``None`` on any failure so a
        checkpoint problem never breaks the REPL.
        """
        if self._checkpoints_ready:
            return self._checkpoints
        self._checkpoints_ready = True
        try:
            import os

            from ..features.session_checkpoints import SessionCheckpointManager

            config = None
            try:
                from ..configuration.resolver import resolve_config

                config = resolve_config().extra
            except Exception:
                config = None

            store = _InMemoryConversationStore(
                self._conversation_history,
                agent_provider=lambda: self._agent,
            )
            mgr = SessionCheckpointManager.from_config(
                workspace_dir=(
                    os.environ.get("PRAISONAI_WORKSPACE")
                    or self.config.workspace
                    or os.getcwd()
                ),
                config=config,
                verbose=self.config.verbose,
                session_store=store,
                session_id=self._session_id or "repl",
                default=True,
            )
            if mgr.enabled:
                mgr.checkpoint_turn("session start")
                self._checkpoints = mgr
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Session checkpoints unavailable: %s", exc)
            self._checkpoints = None
        return self._checkpoints

    def _checkpoint_turn(self, label: str) -> None:
        """Record a pre-turn checkpoint so the revert timeline exists."""
        ckpt = self._get_checkpoints()
        if ckpt is not None:
            try:
                ckpt.checkpoint_turn(label)
            except Exception:  # pragma: no cover - never break a turn
                pass

    def _handle_undo(self) -> None:
        """/undo — roll files + conversation back to the previous turn."""
        ckpt = self._get_checkpoints()
        if ckpt is None or not getattr(ckpt, "enabled", False) or not ckpt.turns:
            self.io.tool_warning("Nothing to undo.")
            return
        self.io.info("Changes that will be undone (last turn):")
        ckpt.preview(1)
        restored = ckpt.revert(1)
        if restored:
            self.io.success(f"Reverted files + conversation to {restored.short_id}")
        else:
            self.io.tool_warning("No checkpoint to undo.")

    def _handle_revert(self, args: str) -> None:
        """/revert [n] — roll files + conversation back n turns (default 1)."""
        ckpt = self._get_checkpoints()
        if ckpt is None or not getattr(ckpt, "enabled", False):
            self.io.tool_warning(
                "Checkpointing is disabled. Enable with checkpoints.auto: true "
                "or PRAISONAI_CHECKPOINTS=on."
            )
            return
        if not ckpt.turns:
            self.io.tool_warning("No checkpoints to revert to.")
            return
        n = 1
        token = str(args).strip().lower()
        if token and token != "last":
            try:
                n = int(token)
            except ValueError:
                self.io.tool_warning("Usage: /revert [n|last]")
                return
        if n < 1 or n > len(ckpt.turns):
            self.io.tool_warning(f"Can only revert 1..{len(ckpt.turns)} turn(s).")
            return
        self.io.info(f"Changes that will be undone (last {n} turn(s)):")
        ckpt.preview(n)
        restored = ckpt.revert(n)
        if restored:
            self.io.success(f"Reverted files + conversation to {restored.short_id}")
        else:
            self.io.tool_warning("Failed to revert.")

    def _get_registry(self):
        """Lazily build the unified command registry (built-ins + custom).

        Makes ``.praisonai/commands/*.md`` custom commands first-class ``/name``
        commands in the REPL, resolved via the same discovery that powers
        ``praisonai run --command``. Degrades to built-ins only on failure.
        """
        if self._registry is None:
            try:
                from .command_registry import create_default_registry

                self._registry = create_default_registry(
                    DEFAULT_COMMANDS, include_custom=True, include_skills=True
                )
                # Surface custom/skill/mcp commands in the ``/`` completion menu
                # too — the built-ins are registered at init, but discovered
                # commands (e.g. installed skills) must be added here so typing
                # ``/`` offers them alongside the built-ins.
                self.io.add_commands(
                    {
                        c.name: c.description
                        for c in self._registry.list_commands()
                        if c.kind.value != "builtin"
                    }
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Command registry unavailable: %s", exc)
                self._registry = _REGISTRY_FAILED
        if self._registry is _REGISTRY_FAILED:
            return None
        return self._registry
    
    def _get_agent(self):
        """Lazy-load the agent."""
        if self._agent is None:
            try:
                from praisonaiagents import Agent
                
                agent_kwargs = {
                    "name": "InteractiveAgent",
                    "role": "Assistant",
                    "goal": "Help the user with their requests",
                    "instructions": "You are a helpful AI assistant. Be concise and helpful.",
                }
                
                if self.config.model:
                    agent_kwargs["llm"] = self.config.model
                
                if self.config.memory:
                    agent_kwargs["memory"] = True
                
                if self.config.tools:
                    agent_kwargs["tools"] = self.config.tools
                
                self._agent = Agent(**agent_kwargs)
                
            except ImportError as e:
                self.io.tool_error(f"Failed to import praisonaiagents: {e}")
                raise
        
        return self._agent
    
    def _handle_command(self, command: str) -> bool:
        """
        Handle slash commands.
        
        Returns True if command was handled, False otherwise.
        """
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower().lstrip("/")
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in ("exit", "quit", "q"):
            self._running = False
            self.io.info("Goodbye!")
            return True
        
        elif cmd == "help":
            commands = dict(DEFAULT_COMMANDS)
            registry = self._get_registry()
            if registry:
                for c in registry.list_commands():
                    if c.name not in commands and c.kind.value != "builtin":
                        commands[c.name] = c.description
            self.io.print_help(commands)
            return True
        
        elif cmd == "clear":
            self._conversation_history.clear()
            self.io.success("Conversation cleared.")
            return True
        
        elif cmd == "session":
            if self._session_id:
                self.io.info(f"Session: {self._session_id}")
            else:
                self.io.info("No active session")
            return True
        
        elif cmd == "model":
            if args:
                self.config.model = args
                self._agent = None  # Reset agent to use new model
                self.io.success(f"Model changed to: {args}")
            else:
                self.io.info(f"Current model: {self.config.model}")
            return True
        
        elif cmd == "cost":
            self.io.info(f"Total tokens: {self._total_tokens}")
            self.io.info(f"Estimated cost: ${self._total_cost:.4f}")
            return True
        
        elif cmd == "history":
            if not self._conversation_history:
                self.io.info("No conversation history")
            else:
                for i, msg in enumerate(self._conversation_history[-10:], 1):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")[:100]
                    self.io.info(f"{i}. [{role}] {content}...")
            return True
        
        elif cmd == "export":
            filename = args or "conversation.txt"
            try:
                with open(filename, "w") as f:
                    for msg in self._conversation_history:
                        f.write(f"[{msg.get('role', 'unknown')}]\n")
                        f.write(f"{msg.get('content', '')}\n\n")
                self.io.success(f"Exported to {filename}")
            except Exception as e:
                self.io.tool_error(f"Export failed: {e}")
            return True
        
        elif cmd == "compact":
            self.io.config.pretty = not self.io.config.pretty
            mode = "disabled" if self.io.config.pretty else "enabled"
            self.io.info(f"Compact mode {mode}")
            return True
        
        elif cmd == "multiline":
            self.io.config.multiline_mode = not self.io.config.multiline_mode
            mode = "enabled" if self.io.config.multiline_mode else "disabled"
            self.io.info(f"Multiline mode {mode}")
            return True
        
        elif cmd == "btw":
            self._handle_btw(args)
            return True
        
        elif cmd == "undo":
            self._handle_undo()
            return True
        
        elif cmd == "revert":
            self._handle_revert(args)
            return True
        
        else:
            # Not a built-in: consult the unified command registry so custom
            # .praisonai/commands/*.md commands are first-class /name commands.
            registry = self._get_registry()
            resolved = registry.get(cmd) if registry else None
            if resolved is not None and resolved.handler is not None:
                try:
                    prompt = resolved.handler(args)
                except Exception as exc:
                    self.io.tool_error(f"Command /{cmd} failed: {exc}")
                    return True
                if prompt:
                    self.io.print_assistant_start()
                    response = self._execute_prompt(prompt)
                    if response:
                        self.io.print_assistant_response(response)
                else:
                    self.io.info(f"Command /{cmd} produced no output.")
                return True
            self.io.tool_warning(f"Unknown command: /{cmd}")
            self.io.info("Type /help for available commands")
            return True
    
    def _handle_shell_escape(self, user_input: str) -> None:
        """Handle a ``!cmd`` (or ``!!cmd``) shell escape.

        Runs the command through the shared gated executor and renders its
        output inline. ``!!cmd`` additionally stashes the output so it is
        attached as context on the next model turn. This never consumes a model
        turn.
        """
        attach = user_input.startswith("!!")
        command = user_input[2:] if attach else user_input[1:]

        try:
            from ..features.custom_definitions import run_shell_escape
        except Exception as exc:  # pragma: no cover - defensive
            self.io.tool_error(f"Shell escape unavailable: {exc}")
            return

        result = run_shell_escape(command)

        if not result.enabled:
            self.io.info(result.output)
            return

        if result.output:
            if result.error:
                self.io.tool_error(result.output)
            else:
                self.io.info(result.output)

        if attach:
            self._pending_context.append(
                f"$ {result.command}\n{result.output}"
            )
            self.io.success("Output attached as context for the next message.")

    def _execute_prompt(self, prompt: str) -> Optional[str]:
        """Execute a prompt and return the response."""
        try:
            agent = self._get_agent()

            # Prepend any `!!cmd` shell output stashed for this turn. Retain it
            # until the model call succeeds so an error does not silently drop
            # context the user explicitly attached.
            attached_context = self._pending_context
            if attached_context:
                context = "\n\n".join(attached_context)
                prompt = f"[shell output]\n{context}\n\n{prompt}"

            # Add to history
            self._conversation_history.append({
                "role": "user",
                "content": prompt
            })
            
            # Execute
            response = agent.start(prompt)

            # Model call succeeded: the attached context has been consumed.
            if attached_context:
                self._pending_context = []
            
            # Add response to history
            if response:
                self._conversation_history.append({
                    "role": "assistant", 
                    "content": str(response)
                })
            
            return str(response) if response else None
            
        except Exception as e:
            logger.exception("Error executing prompt")
            self.io.tool_error(f"Error: {e}")
            return None
    
    def _handle_btw(self, args: str) -> None:
        """Answer a side question in a throwaway, parallel context.

        ``/btw <question>`` runs the question against a fresh, read-only agent
        with a minimal context (just the question + cwd). The main
        conversation's ``_conversation_history`` is **never** touched, so the
        primary task's place and momentum stay intact — that is the whole point.

        Flags:
            ``--keep``: record a one-line note of the exchange in the main
                history (opt-in; default is fully throwaway).
        """
        keep = False
        question = args.strip()
        # Parse the opt-in --keep flag only when it is the leading option, so a
        # legitimate question like "/btw what does --keep mean?" is untouched.
        tokens = question.split(maxsplit=1)
        if tokens and tokens[0] == "--keep":
            keep = True
            question = tokens[1].strip() if len(tokens) > 1 else ""

        if not question:
            self.io.tool_warning("Usage: /btw [--keep] <question>")
            return

        answer = self._run_side_question(question)
        if answer is None:
            return

        # Render in a visually distinct block so it reads as a side note,
        # not part of the main assistant transcript.
        if self.io.console and self.io.config.pretty:
            from rich.markdown import Markdown
            from rich.panel import Panel

            try:
                body = Markdown(answer)
            except Exception:
                body = answer
            self.io.console.print(
                Panel(body, title="btw", border_style="magenta", padding=(0, 1))
            )
        else:
            print(f"\n[btw] {answer}")

        # Deliberately do NOT append the side exchange to the main history.
        # Only record a one-line note when the user opts in with --keep.
        if keep:
            self._conversation_history.append({
                "role": "note",
                "content": f"[btw] {question}",
            })

    def _build_side_agent(self):
        """Build a throwaway, read-only agent for side questions.

        Fresh minimal context, no tools (read-only), never shares the main
        agent's history. Reuses the existing ``Agent`` class — no new params.
        """
        from praisonaiagents import Agent

        agent_kwargs = {
            "name": "SideQuestionAgent",
            "role": "Assistant",
            "goal": "Answer a quick side question without side effects",
            "instructions": (
                "You are a helpful assistant answering a quick side question. "
                "Be concise. Do not modify any files or run commands."
            ),
            # Explicitly disabled so a side question can never trigger the
            # autonomous tool-using loop, regardless of ambient config.
            "autonomy": False,
        }
        if self.config.model:
            agent_kwargs["llm"] = self.config.model
        return Agent(**agent_kwargs)

    def _run_side_question(self, question: str) -> Optional[str]:
        """Run ``question`` against a throwaway agent and return its answer."""
        try:
            import os

            agent = self._build_side_agent()
            prompt = f"(cwd: {os.getcwd()})\n\n{question}"
            # Force non-streaming: in a TTY ``start()`` auto-streams and returns
            # a generator, which would otherwise be str()'d into a repr rather
            # than the answer. Fall back for agents that take no kwargs.
            try:
                response = agent.start(prompt, stream=False)
            except TypeError:
                response = agent.start(prompt)
            # Defensively materialize any generator that still slips through.
            if hasattr(response, "__iter__") and not isinstance(response, (str, bytes)):
                response = "".join(str(chunk) for chunk in response)
            return str(response) if response else None
        except Exception as exc:
            logger.exception("Error answering side question")
            self.io.tool_error(f"btw failed: {exc}")
            return None

    def run(self) -> None:
        """
        Run the interactive REPL.
        
        This is the main entry point. It runs synchronously,
        using prompt_toolkit for input (which must be sync).
        """
        self._running = True
        
        # Get tools count for display
        tools_count = len(self.config.tools) if self.config.tools else 0
        
        # Generate session ID
        import uuid
        self._session_id = self.config.session_id or str(uuid.uuid4())
        
        # Print welcome
        self.io.print_welcome(
            model=self.config.model,
            tools_count=tools_count,
            session_id=self._session_id
        )

        # Warm the command registry so discovered commands (custom + installed
        # skills) populate the ``/`` completion menu before the first slash is
        # typed, not only after the first custom/skill invocation.
        self._get_registry()

        while self._running:
            try:
                # Get input (SYNC - this is the key!)
                user_input = self.io.get_input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle `!cmd` shell escape (does not consume a model turn)
                if user_input.startswith("!"):
                    self._handle_shell_escape(user_input)
                    continue
                
                # Handle slash commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue
                
                # Checkpoint files + conversation at the turn boundary before
                # the agent may mutate the workspace, so /undo and /revert can
                # roll both back together to this point.
                self._checkpoint_turn(user_input[:60])
                
                # Show thinking indicator
                self.io.print_assistant_start()
                
                # Execute prompt
                response = self._execute_prompt(user_input)
                
                # Display response
                if response:
                    self.io.print_assistant_response(response)
                
            except KeyboardInterrupt:
                self.io.info("\nUse /exit to quit")
            except EOFError:
                self._running = False
                self.io.info("Goodbye!")
            except Exception as e:
                logger.exception("Error in REPL loop")
                self.io.tool_error(f"Error: {e}")
    
    def run_single(self, prompt: str) -> Optional[str]:
        """Run a single prompt and return the response."""
        return self._execute_prompt(prompt)


def start_interactive(
    model: str = "gpt-4o-mini",
    verbose: bool = False,
    memory: bool = False,
    tools: Optional[List] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Start the interactive REPL.
    
    This is the main entry point for `praisonai chat` and `praisonai` (no args).
    """
    config = REPLConfig(
        model=model,
        verbose=verbose,
        memory=memory,
        tools=tools,
        session_id=session_id,
    )
    
    repl = InteractiveREPL(config=config)
    repl.run()
