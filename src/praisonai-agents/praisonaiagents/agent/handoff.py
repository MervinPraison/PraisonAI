"""
Handoff functionality for agent-to-agent delegation.

This module provides handoff capabilities that allow agents to delegate tasks
to other agents, similar to the OpenAI Agents SDK implementation.
"""

from typing import Optional, Any, Callable, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
import inspect
import logging

if TYPE_CHECKING:
    from .agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class HandoffInputData:
    """Data passed to a handoff target agent."""
    messages: list = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    
class Handoff:
    """
    Represents a handoff configuration for delegating tasks to another agent.
    
    Handoffs are represented as tools to the LLM, allowing agents to transfer
    control to specialized agents for specific tasks.
    """
    
    def __init__(
        self,
        agent: 'Agent',
        tool_name_override: Optional[str] = None,
        tool_description_override: Optional[str] = None,
        on_handoff: Optional[Callable] = None,
        input_type: Optional[type] = None,
        input_filter: Optional[Callable[[HandoffInputData], HandoffInputData]] = None
    ):
        """
        Initialize a Handoff configuration.
        
        Args:
            agent: The target agent to hand off to
            tool_name_override: Custom tool name (defaults to transfer_to_<agent_name>)
            tool_description_override: Custom tool description
            on_handoff: Callback function executed when handoff is invoked
            input_type: Type of input expected by the handoff (for structured data)
            input_filter: Function to filter/transform input before passing to target agent
        """
        self.agent = agent
        self.tool_name_override = tool_name_override
        self.tool_description_override = tool_description_override
        self.on_handoff = on_handoff
        self.input_type = input_type
        self.input_filter = input_filter
        
    @property
    def tool_name(self) -> str:
        """Get the tool name for this handoff."""
        if self.tool_name_override:
            return self.tool_name_override
        return self.default_tool_name()
        
    @property
    def tool_description(self) -> str:
        """Get the tool description for this handoff."""
        if self.tool_description_override:
            return self.tool_description_override
        return self.default_tool_description()
        
    def default_tool_name(self) -> str:
        """Generate default tool name based on agent name."""
        # Convert agent name to snake_case for tool name
        agent_name = self.agent.name.lower().replace(' ', '_')
        return f"transfer_to_{agent_name}"
        
    def default_tool_description(self) -> str:
        """Generate default tool description based on agent role and goal."""
        agent_desc = f"Transfer task to {self.agent.name}"
        if hasattr(self.agent, 'role') and self.agent.role:
            agent_desc += f" ({self.agent.role})"
        if hasattr(self.agent, 'goal') and self.agent.goal:
            agent_desc += f" - {self.agent.goal}"
        return agent_desc
        
    def to_tool_function(self, source_agent: 'Agent') -> Callable:
        """
        Convert this handoff to a tool function that can be called by the LLM.
        
        Args:
            source_agent: The agent that will be using this handoff
            
        Returns:
            A callable function that performs the handoff
        """
        def handoff_tool(**kwargs):
            """Execute the handoff to the target agent."""
            try:
                # Execute on_handoff callback if provided
                if self.on_handoff:
                    try:
                        sig = inspect.signature(self.on_handoff)
                        # Get parameters excluding those with defaults and varargs/varkwargs
                        required_params = [
                            p for p in sig.parameters.values()
                            if p.default == inspect.Parameter.empty
                            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                        ]
                        num_required = len(required_params)
                        
                        if num_required == 0:
                            self.on_handoff()
                        elif num_required == 1:
                            self.on_handoff(source_agent)
                        elif num_required == 2:
                            if self.input_type and kwargs:
                                try:
                                    input_data = self.input_type(**kwargs)
                                    self.on_handoff(source_agent, input_data)
                                except TypeError as e:
                                    logger.error(f"Failed to create input_type instance: {e}")
                                    self.on_handoff(source_agent, kwargs)
                            else:
                                # No input_type or no kwargs: pass raw kwargs or empty dict
                                self.on_handoff(source_agent, kwargs or {})
                        else:
                            raise ValueError(
                                f"Callback {self.on_handoff.__name__} requires {num_required} parameters, "
                                "but only 0-2 are supported"
                            )
                    except Exception as e:
                        logger.error(f"Error invoking callback {self.on_handoff.__name__}: {e}")
                        # Continue with handoff even if callback fails
                
                # Prepare handoff data
                handoff_data = HandoffInputData(
                    messages=getattr(source_agent, 'chat_history', []),
                    context={'source_agent': source_agent.name}
                )
                
                # Apply input filter if provided
                if self.input_filter:
                    handoff_data = self.input_filter(handoff_data)
                
                # Get the last user message or context to pass to target agent
                last_message = None
                for msg in reversed(handoff_data.messages):
                    if isinstance(msg, dict) and msg.get('role') == 'user':
                        last_message = msg.get('content', '')
                        break
                
                if not last_message and handoff_data.messages:
                    # If no user message, use the last message
                    last_msg = handoff_data.messages[-1]
                    if isinstance(last_msg, dict):
                        last_message = last_msg.get('content', '')
                    else:
                        last_message = str(last_msg)
                
                # Prepare context information
                context_info = f"[Handoff from {source_agent.name}] "
                if kwargs and self.input_type:
                    # Include structured input data in context
                    context_info += f"Context: {kwargs} "
                
                # Execute the target agent
                if last_message:
                    prompt = context_info + last_message
                    logger.info(f"Handing off to {self.agent.name} with prompt: {prompt}")
                    response = self.agent.chat(prompt)
                    return f"Handoff successful. {self.agent.name} response: {response}"
                return f"Handoff to {self.agent.name} completed, but no specific task was provided."
                    
            except Exception as e:
                logger.error(f"Error during handoff to {self.agent.name}: {str(e)}")
                return f"Error during handoff to {self.agent.name}: {str(e)}"
        
        # Set function metadata for tool definition generation
        handoff_tool.__name__ = self.tool_name
        handoff_tool.__doc__ = self.tool_description
        
        # Add input type annotations if provided
        if self.input_type and hasattr(self.input_type, '__annotations__'):
            sig_params = []
            for field_name, field_type in self.input_type.__annotations__.items():
                sig_params.append(
                    inspect.Parameter(
                        field_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=field_type
                    )
                )
            handoff_tool.__signature__ = inspect.Signature(sig_params)
        
        return handoff_tool


def handoff(
    agent: 'Agent',
    tool_name_override: Optional[str] = None,
    tool_description_override: Optional[str] = None,
    on_handoff: Optional[Callable] = None,
    input_type: Optional[type] = None,
    input_filter: Optional[Callable[[HandoffInputData], HandoffInputData]] = None
) -> Handoff:
    """
    Create a handoff configuration for delegating tasks to another agent.
    
    This is a convenience function that creates a Handoff instance with the
    specified configuration.
    
    Args:
        agent: The target agent to hand off to
        tool_name_override: Custom tool name (defaults to transfer_to_<agent_name>)
        tool_description_override: Custom tool description
        on_handoff: Callback function executed when handoff is invoked
        input_type: Type of input expected by the handoff (for structured data)
        input_filter: Function to filter/transform input before passing to target agent
        
    Returns:
        A configured Handoff instance
        
    Example:
        ```python
        from praisonaiagents import Agent, handoff
        
        billing_agent = Agent(name="Billing Agent")
        refund_agent = Agent(name="Refund Agent")
        
        triage_agent = Agent(
            name="Triage Agent",
            handoffs=[billing_agent, handoff(refund_agent)]
        )
        ```
    """
    return Handoff(
        agent=agent,
        tool_name_override=tool_name_override,
        tool_description_override=tool_description_override,
        on_handoff=on_handoff,
        input_type=input_type,
        input_filter=input_filter
    )


# Handoff filters - common patterns for filtering handoff data
class handoff_filters:
    """Common handoff input filters."""
    
    @staticmethod
    def remove_all_tools(data: HandoffInputData) -> HandoffInputData:
        """Remove all tool calls from the message history."""
        filtered_messages = []
        for msg in data.messages:
            if isinstance(msg, dict) and (msg.get('tool_calls') or msg.get('role') == 'tool'):
                # Skip messages with tool calls
                continue
            filtered_messages.append(msg)
        
        data.messages = filtered_messages
        return data
    
    @staticmethod
    def keep_last_n_messages(n: int) -> Callable[[HandoffInputData], HandoffInputData]:
        """Keep only the last n messages in the history."""
        def filter_func(data: HandoffInputData) -> HandoffInputData:
            data.messages = data.messages[-n:]
            return data
        return filter_func
    
    @staticmethod
    def remove_system_messages(data: HandoffInputData) -> HandoffInputData:
        """Remove all system messages from the history."""
        filtered_messages = []
        for msg in data.messages:
            if (isinstance(msg, dict) and msg.get('role') != 'system') or not isinstance(msg, dict):
                filtered_messages.append(msg)
        
        data.messages = filtered_messages
        return data


# Recommended prompt prefix for agents that use handoffs
RECOMMENDED_PROMPT_PREFIX = """You have the ability to transfer tasks to specialized agents when appropriate. 
When you determine that a task would be better handled by another agent with specific expertise, 
use the transfer tool to hand off the task. The receiving agent will have the full context of 
the conversation and will continue helping the user."""


def prompt_with_handoff_instructions(base_prompt: str, agent: 'Agent') -> str:
    """
    Add handoff instructions to an agent's prompt.
    
    Args:
        base_prompt: The original prompt/instructions
        agent: The agent that will use handoffs
        
    Returns:
        Updated prompt with handoff instructions
    """
    if not hasattr(agent, 'handoffs') or not agent.handoffs:
        return base_prompt
    
    handoff_info = "\n\nAvailable handoff agents:\n"
    for h in agent.handoffs:
        if isinstance(h, Handoff):
            handoff_info += f"- {h.agent.name}: {h.tool_description}\n"
        else:
            # Direct agent reference - create a temporary Handoff to get the default description
            temp_handoff = Handoff(agent=h)
            handoff_info += f"- {h.name}: {temp_handoff.tool_description}\n"
    
    return RECOMMENDED_PROMPT_PREFIX + handoff_info + "\n\n" + base_prompt