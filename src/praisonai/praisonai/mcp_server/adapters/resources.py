"""
MCP Resources Adapter

Registers MCP resources for PraisonAI:
- praisonai://memory/sessions
- praisonai://memory/{session_id}
- praisonai://workflows
- praisonai://tools
- praisonai://agents
- praisonai://knowledge/sources
"""

import logging

from ..registry import register_resource

logger = logging.getLogger(__name__)


def register_mcp_resources() -> None:
    """Register MCP resources."""
    
    @register_resource("praisonai://memory/sessions")
    def memory_sessions_resource() -> dict:
        """List all memory sessions."""
        try:
            from praisonaiagents.memory import Memory
            memory = Memory()
            sessions = memory.list_sessions()
            return {"sessions": sessions}
        except ImportError:
            return {"error": "Memory module not available", "sessions": []}
        except Exception as e:
            return {"error": str(e), "sessions": []}
    
    @register_resource("praisonai://workflows")
    def workflows_resource() -> dict:
        """List available workflows in current directory."""
        try:
            import os
            import glob
            workflows = []
            for pattern in ["*.yaml", "*.yml"]:
                for f in glob.glob(pattern):
                    if "agent" in f.lower() or "workflow" in f.lower():
                        workflows.append(f)
            return {"workflows": workflows, "cwd": os.getcwd()}
        except Exception as e:
            return {"error": str(e), "workflows": []}
    
    @register_resource("praisonai://tools")
    def tools_resource() -> dict:
        """List available tools."""
        try:
            from ..registry import get_tool_registry
            registry = get_tool_registry()
            tools = registry.list_schemas()
            return {"tools": [t["name"] for t in tools], "count": len(tools)}
        except Exception as e:
            return {"error": str(e), "tools": []}
    
    @register_resource("praisonai://agents")
    def agents_resource() -> dict:
        """List agent configurations."""
        try:
            import os
            import yaml
            agents = []
            for f in ["agents.yaml", "agents.yml"]:
                if os.path.exists(f):
                    with open(f, 'r') as file:
                        config = yaml.safe_load(file)
                        if config and "roles" in config:
                            agents.extend(list(config["roles"].keys()))
            return {"agents": agents}
        except Exception as e:
            return {"error": str(e), "agents": []}
    
    @register_resource("praisonai://knowledge/sources")
    def knowledge_sources_resource() -> dict:
        """List knowledge sources."""
        try:
            from praisonaiagents.knowledge import Knowledge
            knowledge = Knowledge()
            sources = knowledge.list_sources()
            return {"sources": sources}
        except ImportError:
            return {"error": "Knowledge module not available", "sources": []}
        except Exception as e:
            return {"error": str(e), "sources": []}
    
    @register_resource("praisonai://config")
    def config_resource() -> dict:
        """Get current configuration."""
        try:
            import os
            config = {
                "openai_api_key_set": bool(os.environ.get("OPENAI_API_KEY")),
                "anthropic_api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "google_api_key_set": bool(os.environ.get("GOOGLE_API_KEY")),
                "cwd": os.getcwd(),
            }
            return config
        except Exception as e:
            return {"error": str(e)}
    
    @register_resource("praisonai://mcp/status")
    def mcp_status_resource() -> dict:
        """Get MCP server status."""
        try:
            from ..registry import get_tool_registry, get_resource_registry, get_prompt_registry
            from ..server import PROTOCOL_VERSION
            
            return {
                "protocol_version": PROTOCOL_VERSION,
                "tools_count": len(get_tool_registry().list_all()),
                "resources_count": len(get_resource_registry().list_all()),
                "prompts_count": len(get_prompt_registry().list_all()),
                "status": "healthy",
            }
        except Exception as e:
            return {"error": str(e), "status": "error"}
    
    logger.info("Registered MCP resources")
