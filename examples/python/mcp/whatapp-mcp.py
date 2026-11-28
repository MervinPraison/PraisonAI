from praisonaiagents import Agent, MCP

whatsapp_agent = Agent(
    instructions="Whatsapp Agent",
    model="gpt-4o-mini",
    tools=MCP("python /Users/praison/whatsapp-mcp/whatsapp-mcp-server/main.py")
)

whatsapp_agent.start("Send Hello to Mervin Praison")