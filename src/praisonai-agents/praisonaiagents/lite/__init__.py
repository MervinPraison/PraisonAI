"""
PraisonAI Agents Lite - Minimal agent framework without heavy dependencies.

This subpackage provides a lightweight version of PraisonAI Agents that:
- Does NOT import litellm, chromadb, or other heavy dependencies at import time
- Provides core Agent/Task/Tools abstractions
- Allows users to bring their own LLM client (BYO-LLM)
- Has minimal import time (<50ms) and memory footprint (<10MB)

Usage:
    from praisonaiagents.lite import LiteAgent, LiteTask, Tools
    
    # Create a lite agent with your own LLM function
    def my_llm(messages):
        # Your LLM implementation here
        return "response"
    
    agent = LiteAgent(
        name="Assistant",
        llm_fn=my_llm,
        tools=[my_tool]
    )
    
    response = agent.chat("Hello!")

For full functionality with litellm integration, use the main package:
    from praisonaiagents import Agent
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
import threading


@dataclass
class LiteToolResult:
    """Result from a tool execution."""
    output: Any
    success: bool = True
    error: Optional[str] = None


@dataclass
class LiteTask:
    """
    Lightweight task definition without heavy dependencies.
    
    Attributes:
        description: What the task should accomplish
        expected_output: Description of expected output format
        agent: Optional agent assigned to this task
        context: Additional context for the task
        result: Result after task execution
    """
    description: str
    expected_output: str = ""
    agent: Optional['LiteAgent'] = None
    context: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    
    def execute(self, input_text: Optional[str] = None) -> str:
        """Execute the task using the assigned agent."""
        if self.agent is None:
            raise ValueError("No agent assigned to this task")
        
        prompt = input_text or self.description
        if self.expected_output:
            prompt += f"\n\nExpected output format: {self.expected_output}"
        
        self.result = self.agent.chat(prompt)
        return self.result


class LiteAgent:
    """
    Lightweight agent that works with any LLM function.
    
    This agent does NOT import litellm or other heavy dependencies.
    Users provide their own LLM function for chat completions.
    
    Args:
        name: Agent name
        llm_fn: Function that takes messages list and returns response string.
                Signature: (messages: List[Dict]) -> str
        instructions: System instructions for the agent
        tools: List of tool functions the agent can use
        verbose: Enable verbose output
    
    Example:
        def my_openai_llm(messages):
            import openai
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            return response.choices[0].message.content
        
        agent = LiteAgent(
            name="Assistant",
            llm_fn=my_openai_llm,
            instructions="You are a helpful assistant."
        )
        
        response = agent.chat("Hello!")
    """
    
    def __init__(
        self,
        name: str = "LiteAgent",
        llm_fn: Optional[Callable[[List[Dict]], str]] = None,
        instructions: str = "You are a helpful assistant.",
        tools: Optional[List[Callable]] = None,
        verbose: bool = False,
    ):
        self.name = name
        self.llm_fn = llm_fn
        self.instructions = instructions
        self.tools = tools or []
        self.verbose = verbose
        
        # Thread-safe chat history
        self.chat_history: List[Dict[str, str]] = []
        self._history_lock = threading.Lock()
        
        # Tool registry
        self._tool_map: Dict[str, Callable] = {}
        for tool_fn in self.tools:
            tool_name = getattr(tool_fn, '__name__', str(tool_fn))
            self._tool_map[tool_name] = tool_fn
    
    def _build_messages(self, user_message: str) -> List[Dict[str, str]]:
        """Build messages list for LLM call."""
        messages = [{"role": "system", "content": self.instructions}]
        
        with self._history_lock:
            messages.extend(self.chat_history.copy())
        
        messages.append({"role": "user", "content": user_message})
        return messages
    
    def _add_to_history(self, role: str, content: str):
        """Thread-safe addition to chat history."""
        with self._history_lock:
            self.chat_history.append({"role": role, "content": content})
    
    def chat(self, message: str) -> str:
        """
        Send a message to the agent and get a response.
        
        Args:
            message: User message
            
        Returns:
            Agent's response string
        """
        if self.llm_fn is None:
            raise ValueError(
                "No LLM function provided. Please provide an llm_fn when creating the agent.\n"
                "Example:\n"
                "  def my_llm(messages):\n"
                "      # Your LLM implementation\n"
                "      return 'response'\n"
                "  agent = LiteAgent(llm_fn=my_llm)"
            )
        
        messages = self._build_messages(message)
        
        if self.verbose:
            print(f"[{self.name}] Processing: {message[:50]}...")
        
        response = self.llm_fn(messages)
        
        # Add to history
        self._add_to_history("user", message)
        self._add_to_history("assistant", response)
        
        if self.verbose:
            print(f"[{self.name}] Response: {response[:100]}...")
        
        return response
    
    def clear_history(self):
        """Clear chat history."""
        with self._history_lock:
            self.chat_history.clear()
    
    def execute_tool(self, tool_name: str, **kwargs) -> LiteToolResult:
        """
        Execute a tool by name.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments to pass to the tool
            
        Returns:
            LiteToolResult with output or error
        """
        if tool_name not in self._tool_map:
            return LiteToolResult(
                output=None,
                success=False,
                error=f"Tool '{tool_name}' not found"
            )
        
        try:
            tool_fn = self._tool_map[tool_name]
            result = tool_fn(**kwargs)
            return LiteToolResult(output=result, success=True)
        except Exception as e:
            return LiteToolResult(
                output=None,
                success=False,
                error=str(e)
            )


def create_openai_llm_fn(
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
    **kwargs
) -> Callable[[List[Dict]], str]:
    """
    Create an LLM function using the OpenAI SDK.
    
    This is a convenience function for users who want to use OpenAI
    without the full litellm dependency.
    
    Args:
        model: OpenAI model name
        api_key: OpenAI API key (or use OPENAI_API_KEY env var)
        **kwargs: Additional arguments to pass to OpenAI
        
    Returns:
        LLM function compatible with LiteAgent
        
    Example:
        llm_fn = create_openai_llm_fn(model="gpt-4o-mini")
        agent = LiteAgent(llm_fn=llm_fn)
    """
    def llm_fn(messages: List[Dict]) -> str:
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package is required for create_openai_llm_fn. "
                "Install with: pip install openai"
            )
        
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content or ""
    
    return llm_fn


def create_anthropic_llm_fn(
    model: str = "claude-3-5-sonnet-20241022",
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
    **kwargs
) -> Callable[[List[Dict]], str]:
    """
    Create an LLM function using the Anthropic SDK.
    
    Args:
        model: Anthropic model name
        api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
        max_tokens: Maximum tokens in response
        **kwargs: Additional arguments to pass to Anthropic
        
    Returns:
        LLM function compatible with LiteAgent
    """
    def llm_fn(messages: List[Dict]) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required for create_anthropic_llm_fn. "
                "Install with: pip install anthropic"
            )
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # Extract system message
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)
        
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=chat_messages,
            **kwargs
        )
        return response.content[0].text
    
    return llm_fn


# Re-export Tools from main package (lightweight, no heavy deps)
from ..tools.tools import Tools
from ..tools.base import BaseTool, ToolResult
from ..tools.decorator import tool


__all__ = [
    "LiteAgent",
    "LiteTask",
    "LiteToolResult",
    "Tools",
    "BaseTool",
    "ToolResult",
    "tool",
    "create_openai_llm_fn",
    "create_anthropic_llm_fn",
]
