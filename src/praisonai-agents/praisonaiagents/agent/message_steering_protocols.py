"""
Message Steering Protocol Definitions.

Provides Protocol interfaces for real-time message steering during agent execution.
This enables users to send guidance messages to agents while they are executing
long-running tasks.
"""
from typing import Protocol, runtime_checkable, Optional, Any, List, Dict
from enum import Enum
from dataclasses import dataclass


class SteeringPriority(Enum):
    """Priority levels for steering messages."""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20
    INTERRUPT = 30  # Immediate interruption


@dataclass
class SteeringMessage:
    """A steering message with priority and metadata."""
    content: str
    priority: SteeringPriority = SteeringPriority.NORMAL
    metadata: Optional[Dict[str, Any]] = None


@runtime_checkable
class MessageSteeringProtocol(Protocol):
    """
    Protocol for message steering during agent execution.
    
    This protocol enables real-time communication with agents during
    long-running operations, allowing users to provide mid-execution
    guidance, feedback, and course corrections.
    
    Example:
        ```python
        class BasicMessageSteering:
            def queue_message(self, message: str, priority: int = 5) -> str:
                # Add to internal queue
                return "msg_001"
            
            def get_pending_messages(self) -> List[SteeringMessage]:
                # Return queued messages
                return []
            
            def process_steering(self, context: dict) -> bool:
                # Check for messages and update context
                return False
        
        agent = Agent(name="assistant", message_steering=BasicMessageSteering())
        ```
    """
    
    def queue_message(self, message: str, priority: int = 5) -> str:
        """
        Queue a steering message for the agent.
        
        Args:
            message: The steering message content
            priority: Message priority (higher = more urgent)
            
        Returns:
            Message ID for tracking
        """
        ...
    
    def get_pending_messages(self) -> List[SteeringMessage]:
        """
        Get all pending steering messages.
        
        Returns:
            List of pending messages ordered by priority
        """
        ...
    
    def process_steering(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Process any pending steering messages and update execution context.
        
        This method is called during agent execution to check for
        and process any steering messages that have been queued.
        
        Args:
            context: Optional execution context to update
            
        Returns:
            True if messages were processed, False otherwise
        """
        ...
    
    def clear_messages(self) -> int:
        """
        Clear all pending messages.
        
        Returns:
            Number of messages cleared
        """
        ...
    
    def has_pending_messages(self) -> bool:
        """
        Check if there are pending steering messages.
        
        Returns:
            True if messages are pending, False otherwise
        """
        ...


@runtime_checkable
class AgentSteeringProtocol(Protocol):
    """
    Protocol for agents that support message steering.
    
    This extends the agent interface with steering capabilities,
    allowing real-time message injection during execution.
    """
    
    def steer(self, message: str, priority: int = 5) -> str:
        """
        Send a steering message to the agent during execution.
        
        This can be called while the agent is running to provide
        real-time guidance or course corrections.
        
        Args:
            message: The steering message
            priority: Message priority (higher = more urgent)
            
        Returns:
            Message ID for tracking
        """
        ...
    
    def get_steering_status(self) -> Dict[str, Any]:
        """
        Get current steering status.
        
        Returns:
            Dict with pending message count, last processed time, etc.
        """
        ...
    
    @property
    def message_steering_enabled(self) -> bool:
        """Whether message steering is enabled for this agent."""
        ...


__all__ = [
    'SteeringPriority',
    'SteeringMessage', 
    'MessageSteeringProtocol',
    'AgentSteeringProtocol',
]