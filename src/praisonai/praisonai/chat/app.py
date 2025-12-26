"""
PraisonAI Chat - Default Chainlit Application

This is the default chat application that runs when using `praisonai chat`.
It integrates with PraisonAI agents for multi-agent conversations.
"""

import os
import chainlit as cl

# Check if we're in PraisonAI Chat mode with registered agents
PRAISONAI_CHAT_MODE = os.environ.get("PRAISONAI_CHAT_MODE", "false").lower() == "true"


def get_agents():
    """Get registered agents from the chat module."""
    try:
        from praisonai.chat import get_registered_agents
        return get_registered_agents()
    except ImportError:
        return {}


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session."""
    agents = get_agents()
    
    if agents:
        agent_names = list(agents.keys())
        cl.user_session.set("agents", agents)
        cl.user_session.set("current_agent", agent_names[0] if agent_names else None)
        
        await cl.Message(
            content=f"Welcome to PraisonAI Chat! Available agents: {', '.join(agent_names)}"
        ).send()
    else:
        await cl.Message(
            content="Welcome to PraisonAI Chat! No agents configured. "
                    "Use the API to register agents or configure via YAML."
        ).send()
    
    cl.user_session.set("message_history", [])


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages."""
    agents = cl.user_session.get("agents", {})
    current_agent_name = cl.user_session.get("current_agent")
    message_history = cl.user_session.get("message_history", [])
    
    # Add user message to history
    message_history.append({"role": "user", "content": message.content})
    
    if not agents or not current_agent_name:
        # No agents configured - use a simple echo response
        response = f"Echo: {message.content}\n\n(No agents configured. Register agents to enable AI responses.)"
        await cl.Message(content=response).send()
        return
    
    agent = agents.get(current_agent_name)
    if agent is None:
        await cl.Message(content=f"Agent '{current_agent_name}' not found.").send()
        return
    
    # Create a step for the agent response
    async with cl.Step(name=current_agent_name, type="llm") as step:
        step.input = message.content
        
        try:
            # Try to call the agent
            if hasattr(agent, "chat"):
                # PraisonAI Agent with chat method
                response = await _call_agent_async(agent, message.content)
            elif hasattr(agent, "run"):
                # Agent with run method
                response = await _call_agent_async(agent, message.content, method="run")
            elif callable(agent):
                # Callable agent
                response = agent(message.content)
            else:
                response = f"Agent '{current_agent_name}' does not have a callable interface."
            
            step.output = str(response)
            
        except Exception as e:
            response = f"Error calling agent: {str(e)}"
            step.output = response
    
    # Add assistant response to history
    message_history.append({"role": "assistant", "content": str(response)})
    cl.user_session.set("message_history", message_history)
    
    # Send the response
    await cl.Message(content=str(response)).send()


async def _call_agent_async(agent, message: str, method: str = "chat"):
    """Call an agent method, handling both sync and async."""
    import asyncio
    
    func = getattr(agent, method)
    
    if asyncio.iscoroutinefunction(func):
        return await func(message)
    else:
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, message)


@cl.on_chat_resume
async def on_chat_resume(thread):
    """Resume a chat session."""
    message_history = []
    
    root_messages = [m for m in thread.get("steps", []) if m.get("parentId") is None]
    for msg in root_messages:
        if msg.get("type") == "user_message":
            message_history.append({"role": "user", "content": msg.get("output", "")})
        elif msg.get("type") == "assistant_message":
            message_history.append({"role": "assistant", "content": msg.get("output", "")})
    
    cl.user_session.set("message_history", message_history)
