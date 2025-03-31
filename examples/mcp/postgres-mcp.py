from praisonaiagents import Agent, MCP
import os

# PostgreSQL connection string
postgres_url = "postgresql://localhost/mydb"

# Use a single string command with PostgreSQL configuration
postgres_agent = Agent(
    instructions="""You are a helpful assistant that can interact with PostgreSQL databases.
    Use the available tools when relevant to manage database operations.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-postgres", args=[postgres_url])
)

postgres_agent.start("List all tables in the database") 