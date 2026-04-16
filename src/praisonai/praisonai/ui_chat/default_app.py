"""PraisonAI Clean Chat UI — minimal chat interface with external agent support.

Loaded by ``praisonai ui`` → ``aiui run app.py``.
Clean chat with external agent selection in sidebar.

Requires: pip install "praisonai[ui]"
Set OPENAI_API_KEY before running.

Run:
    praisonai ui
"""

import os
from typing import Dict, Any, List, Optional

import praisonaiui as aiui

# ── Dashboard style with sidebar for external agent settings ─────────────
aiui.set_style("dashboard")
aiui.set_dashboard(sidebar=True, page_header=False)
aiui.set_branding(title="PraisonAI Chat", logo="🤖")
aiui.set_theme(preset="blue", dark_mode=True, radius="lg")
aiui.set_pages(["chat"])

# Module-level cache for available agents (read-only)
_available_agents_cache = {}


def _get_external_agents_handler():
    """Lazy load external agents handler."""
    try:
        from praisonai.cli.features.external_agents import ExternalAgentsHandler
        return ExternalAgentsHandler()
    except ImportError:
        return None


def _check_available_agents() -> Dict[str, bool]:
    """Check which external agents are available."""
    handler = _get_external_agents_handler()
    if handler:
        return handler.check_availability()
    return {}


def _get_agent_with_tools(model: str, selected_agents: List[str]):
    """Create or get cached PraisonAI agent with external agent tools."""
    # Get session-scoped state
    if not hasattr(aiui, 'session_state'):
        session_state = {}
    else:
        session_state = aiui.session_state
    
    # Simple caching based on model and selected agents
    cache_key = f"{model}:{','.join(sorted(selected_agents))}"
    cached_agent = session_state.get('agent_instance')
    if cached_agent and getattr(cached_agent, '_cache_key', '') == cache_key:
        return cached_agent
    
    try:
        from praisonaiagents import Agent
        
        # Build tools list from selected external agents
        tools = []
        if selected_agents:
            handler = _get_external_agents_handler()
            if handler:
                for agent_name in selected_agents:
                    try:
                        integration = handler.get_integration(agent_name)
                        if integration and integration.is_available:
                            tools.append(integration.as_tool())
                    except Exception as e:
                        print(f"Warning: Could not load {agent_name}: {e}")
        
        # Create agent with or without tools
        agent = Agent(
            name="assistant",
            instructions="You are a helpful assistant with access to external AI agents. Use @claude, @gemini, @codex, or @cursor to delegate specific tasks.",
            llm=model,
            tools=tools if tools else None
        )
        agent._cache_key = cache_key
        session_state['agent_instance'] = agent
        return agent
        
    except ImportError:
        # Fallback if praisonaiagents not available
        return None


@aiui.sidebar
async def external_agents_settings():
    """Render external agents selection in sidebar."""
    # Get session-scoped state
    if not hasattr(aiui, 'session_state'):
        # Fallback if session_state not available
        session_state = {}
    else:
        session_state = aiui.session_state
    
    # Check available agents (cached at module level for performance)
    if not _available_agents_cache:
        _available_agents_cache.update(_check_available_agents())
    
    if not any(_available_agents_cache.values()):
        aiui.markdown("**No External Agents**")
        aiui.markdown("No external AI agents are installed. Install them to enable delegation:")
        aiui.markdown("- `curl -fsSL https://claude.ai/install.sh | sh` (Claude Code)")
        aiui.markdown("- `npm install -g @google/generative-ai-cli` (Gemini)")
        return
    
    aiui.markdown("**External Agents**")
    aiui.markdown("Select AI agents to enable in chat:")
    
    # Create checkboxes for available agents
    agent_descriptions = {
        "claude": "Claude Code (coding, refactoring)",
        "gemini": "Gemini CLI (analysis, search)",
        "codex": "Codex CLI (code generation)",
        "cursor": "Cursor CLI (IDE tasks)"
    }
    
    # Get current selection from session state
    current_selection = session_state.get('selected_agents', [])
    updated_selection = []
    
    for agent_name, is_available in _available_agents_cache.items():
        if is_available:
            description = agent_descriptions.get(agent_name, agent_name)
            is_selected = agent_name in current_selection
            
            # Create toggle button as checkbox alternative
            if is_selected:
                button_label = f"✅ {description}"
                if aiui.button(button_label, key=f"toggle_{agent_name}"):
                    # Button clicked - remove from selection (toggle off)
                    pass  # Don't add to updated_selection
                else:
                    # Button not clicked - keep in selection
                    updated_selection.append(agent_name)
            else:
                button_label = f"☐ {description}"
                if aiui.button(button_label, key=f"toggle_{agent_name}"):
                    # Button clicked - add to selection (toggle on)
                    updated_selection.append(agent_name)
    
    # Update session-scoped selection if changed
    if updated_selection != current_selection:
        session_state['selected_agents'] = updated_selection
        # Clear agent cache to recreate with new tools
        session_state['agent_instance'] = None
        
        if updated_selection:
            aiui.success(f"External agents enabled: {', '.join(updated_selection)}")
        else:
            aiui.info("All external agents disabled")



@aiui.starters
async def get_starters():
    """Suggest conversation starters."""
    return [
        {"label": "Research", "message": "Research the latest AI trends", "icon": "🔬"},
        {"label": "Write", "message": "Write a blog post about AI agents", "icon": "✍️"},
        {"label": "Code", "message": "Write a Python function to sort a list", "icon": "💻"},
        {"label": "Brainstorm", "message": "Give me 5 startup ideas using AI agents", "icon": "💡"},
    ]


@aiui.welcome
async def on_welcome():
    """Greet the user."""
    await aiui.say("👋 Hi! I'm your PraisonAI assistant. Ask me anything!")


@aiui.reply
async def on_message(message: str):
    """Process message with PraisonAI agent or fallback to OpenAI."""
    await aiui.think("Thinking...")
    
    model = os.getenv("PRAISONAI_MODEL", "gpt-4o-mini")
    
    # Get session-scoped state
    if not hasattr(aiui, 'session_state'):
        session_state = {}
    else:
        session_state = aiui.session_state
    
    # Try to use PraisonAI agent with external agents
    selected_agents = session_state.get('selected_agents', [])
    agent = _get_agent_with_tools(model, selected_agents)
    if agent:
        try:
            # Check for @mentions for direct delegation
            agent_mentions = {
                "@claude": "claude",
                "@gemini": "gemini", 
                "@codex": "codex",
                "@cursor": "cursor"
            }
            
            mentioned_agent = None
            import re
            for mention, agent_name in agent_mentions.items():
                if agent_name in selected_agents:
                    pattern = re.compile(rf'(?<!\w){re.escape(mention)}\b', re.IGNORECASE)
                    if pattern.search(message):
                        mentioned_agent = agent_name
                        message = pattern.sub("", message).strip()
                        break
            
            if mentioned_agent:
                await aiui.say(f"🤖 Delegating to {mentioned_agent}...")
            
            # Use PraisonAI agent (supports async)
            response = await agent.achat(message)
            if hasattr(response, 'content'):
                content = response.content
            elif hasattr(response, 'result'):
                content = response.result  
            else:
                content = str(response)
            
            await aiui.say(content)
            return
            
        except Exception as e:
            await aiui.say(f"⚠️ PraisonAI agent error: {e}. Falling back to OpenAI...")
    
    # Fallback to direct OpenAI
    try:
        from openai import AsyncOpenAI
    except ImportError:
        await aiui.say("❌ Please install openai: `pip install openai` or praisonaiagents: `pip install praisonaiagents`")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        await aiui.say("❌ Please set OPENAI_API_KEY environment variable.")
        return

    client = AsyncOpenAI(api_key=api_key)
    stream = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful, concise assistant. Use markdown for formatting."},
            {"role": "user", "content": str(message)},
        ],
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            await aiui.stream_token(delta.content)


@aiui.cancel
async def on_cancel():
    await aiui.say("⏹️ Stopped.")
