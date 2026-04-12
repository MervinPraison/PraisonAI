from praisonai import Agent, ManagedAgent, ManagedConfig

# MCP servers: configure agent with remote MCP tool servers
# Note: Anthropic's managed agents only support URL-based (SSE) MCP servers
managed = ManagedAgent(
    config=ManagedConfig(
        name="MCP Agent",
        model="claude-haiku-4-5",
        system="You are a helpful assistant with access to MCP servers.",
        tools=[
            {"type": "agent_toolset_20260401"},
            {"type": "mcp_toolset", "mcp_server_name": "deepwiki"},
        ],
        mcp_servers=[
            {
                "type": "url",
                "url": "https://mcp.deepwiki.com/sse",
                "name": "deepwiki",
            },
        ],
        networking={
            "type": "limited",
            "allow_mcp_servers": True,
            "allow_package_managers": True,
        },
    ),
)

agent = Agent(name="mcp-agent", backend=managed)
result = agent.start(
    "Use the deepwiki MCP to read the wiki page for the anthropics/anthropic-cookbook github repo and give a one sentence summary",
    stream=True,
)

print("\nAgent finished.")
