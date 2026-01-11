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
}


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
        
        # Setup commands
        self.io.add_commands(DEFAULT_COMMANDS)
    
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
            self.io.print_help(DEFAULT_COMMANDS)
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
        
        else:
            self.io.tool_warning(f"Unknown command: /{cmd}")
            self.io.info("Type /help for available commands")
            return True
    
    def _execute_prompt(self, prompt: str) -> Optional[str]:
        """Execute a prompt and return the response."""
        try:
            agent = self._get_agent()
            
            # Add to history
            self._conversation_history.append({
                "role": "user",
                "content": prompt
            })
            
            # Execute
            response = agent.start(prompt)
            
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
        
        while self._running:
            try:
                # Get input (SYNC - this is the key!)
                user_input = self.io.get_input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle slash commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    continue
                
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
