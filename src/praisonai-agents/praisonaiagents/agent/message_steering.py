"""
Message Steering Implementation.

Core implementation of real-time message steering during agent execution.
Integrates with existing message queue infrastructure.
"""
import time
import logging
from typing import List, Optional, Dict, Any
from .message_queue import AgentMessageQueue, MessagePriority
from .protocols import (
    MessageSteeringProtocol, 
    SteeringMessage, 
    SteeringPriority,
    AgentSteeringProtocol
)

logger = logging.getLogger(__name__)


class MessageSteering:
    """
    Core message steering implementation.
    
    Provides real-time message queuing and processing for agents
    during execution. Uses the existing AgentMessageQueue infrastructure.
    """
    
    def __init__(self, max_messages: int = 50):
        """
        Initialize message steering.
        
        Args:
            max_messages: Maximum number of pending messages
        """
        self._message_queue = AgentMessageQueue(max_size=max_messages)
        self._enabled = True
        self._last_check = 0.0
        self._check_interval = 0.1  # Check every 100ms
        
    def queue_message(self, message: str, priority: int = 5) -> str:
        """Queue a steering message."""
        if not self._enabled:
            return ""
            
        # Convert priority to SteeringPriority
        try:
            steering_priority = SteeringPriority(priority)
        except ValueError:
            steering_priority = SteeringPriority.NORMAL
            
        steering_msg = SteeringMessage(
            content=message,
            priority=steering_priority,
            metadata={"timestamp": time.time()}
        )
        
        # Use existing message queue with priority mapping
        # Special handling for INTERRUPT - give it maximum priority
        if steering_priority == SteeringPriority.INTERRUPT:
            queue_priority = MessagePriority.URGENT.value + 1  # Higher than URGENT
        else:
            queue_priority = min(priority, MessagePriority.URGENT.value)
        success = self._message_queue.enqueue(
            content=steering_msg,
            priority=queue_priority,
            metadata={"type": "steering", "original_priority": priority}
        )
        
        if success:
            msg_id = f"steer_{int(time.time() * 1000)}"
            logger.debug(f"Queued steering message: {msg_id}")
            return msg_id
        else:
            logger.warning("Failed to queue steering message - queue full")
            return ""
    
    def get_pending_messages(self) -> List[SteeringMessage]:
        """Get all pending steering messages."""
        if not self._enabled:
            return []
            
        messages = []
        all_messages = self._message_queue.get_all()
        
        for msg in all_messages:
            if isinstance(msg, SteeringMessage):
                messages.append(msg)
                
        return messages
    
    def process_steering(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Process pending steering messages.
        
        This is called during agent execution to check for and process
        any steering messages. Uses rate limiting to avoid excessive checking,
        but allows INTERRUPT priority messages to bypass rate limiting.
        
        Args:
            context: Execution context that can be updated with steering info
            
        Returns:
            True if messages were processed, False otherwise
        """
        if not self._enabled:
            return False
            
        # Check if we have high priority messages that bypass rate limiting
        has_urgent_messages = False
        all_messages = self._message_queue.get_all()
        for msg in all_messages:
            if isinstance(msg, SteeringMessage) and msg.priority.value >= SteeringPriority.HIGH.value:
                has_urgent_messages = True
                break
        
        # Rate limiting - only check every 100ms unless we have urgent messages
        current_time = time.time()
        if not has_urgent_messages and current_time - self._last_check < self._check_interval:
            return False
            
        self._last_check = current_time
        
        if self._message_queue.is_empty():
            return False
            
        # Process one message per check to avoid blocking
        msg_content = self._message_queue.dequeue(timeout=0)
        if msg_content is None:
            return False
            
        if not isinstance(msg_content, SteeringMessage):
            return False
            
        # Update context with steering message
        if context is not None:
            if "steering_messages" not in context:
                context["steering_messages"] = []
            context["steering_messages"].append({
                "content": msg_content.content,
                "priority": msg_content.priority.name,
                "timestamp": msg_content.metadata.get("timestamp") if msg_content.metadata else None
            })
            
        logger.info(f"Processed steering message: {msg_content.content[:50]}...")
        return True
    
    def clear_messages(self) -> int:
        """Clear all pending messages."""
        return self._message_queue.clear()
    
    def has_pending_messages(self) -> bool:
        """Check if there are pending steering messages."""
        return not self._message_queue.is_empty()
    
    def enable(self) -> None:
        """Enable message steering."""
        self._enabled = True
        
    def disable(self) -> None:
        """Disable message steering."""
        self._enabled = False
        
    @property
    def enabled(self) -> bool:
        """Whether message steering is enabled."""
        return self._enabled


class SteeringMixin:
    """
    Mixin to add message steering capabilities to Agent class.
    
    This provides the agent interface for message steering while
    delegating implementation to MessageSteering.
    """
    
    def _init_message_steering(self, message_steering=False):
        """Initialize message steering if enabled."""
        if message_steering is True:
            # Use default implementation
            self._message_steering = MessageSteering()
        elif message_steering is False or message_steering is None:
            # Disabled
            self._message_steering = None
        else:
            # Custom implementation provided
            self._message_steering = message_steering
    
    def steer(self, message: str, priority: int = 5) -> str:
        """
        Send a steering message to the agent during execution.
        
        This can be called while the agent is running to provide
        real-time guidance or course corrections.
        
        Args:
            message: The steering message
            priority: Message priority (1=low, 5=normal, 10=high, 20=urgent, 30=interrupt)
            
        Returns:
            Message ID for tracking, empty string if steering disabled
            
        Example:
            ```python
            agent = Agent(name="research", message_steering=True)
            
            # Start long-running task
            import threading
            def run_task():
                return agent.start("Research AI trends comprehensively")
            thread = threading.Thread(target=run_task)
            thread.start()
            
            # Send steering messages while running
            agent.steer("Focus on the business impact, not technical details")
            agent.steer("Also include information about market size", priority=10)
            ```
        """
        if self._message_steering is None:
            logger.warning("Message steering not enabled - call ignored")
            return ""
            
        return self._message_steering.queue_message(message, priority)
    
    def get_steering_status(self) -> Dict[str, Any]:
        """Get current steering status."""
        if self._message_steering is None:
            return {"enabled": False, "pending_count": 0}
            
        return {
            "enabled": self._message_steering.enabled,
            "pending_count": len(self._message_steering.get_pending_messages()),
            "has_pending": self._message_steering.has_pending_messages()
        }
    
    @property
    def message_steering_enabled(self) -> bool:
        """Whether message steering is enabled for this agent."""
        return self._message_steering is not None and self._message_steering.enabled
    
    def _check_steering_messages(self) -> Optional[str]:
        """
        Check for and process steering messages.
        
        This is called during agent execution loops to process
        any pending steering messages.
        
        Returns:
            Steering message to inject into conversation, or None
        """
        if self._message_steering is None:
            return None
            
        # Process steering messages
        context = {}
        if self._message_steering.process_steering(context):
            steering_messages = context.get("steering_messages", [])
            if steering_messages:
                # Get the most recent message
                latest = steering_messages[-1]
                content = latest["content"]
                priority = latest["priority"]
                
                # Format as system message
                if priority == "INTERRUPT":
                    return f"\n[INTERRUPT USER GUIDANCE]: {content}\nPlease stop current work and follow this guidance immediately."
                elif priority in ("HIGH", "URGENT"):
                    return f"\n[URGENT USER GUIDANCE]: {content}\nPlease acknowledge and adjust your approach accordingly."
                else:
                    return f"\n[USER GUIDANCE]: {content}\nPlease consider this feedback as you continue."
        
        return None