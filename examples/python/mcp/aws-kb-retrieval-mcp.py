from praisonaiagents import Agent, MCP
import os

# Get AWS credentials from environment
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_REGION")

# Use a single string command with AWS KB Retrieval configuration
aws_kb_agent = Agent(
    instructions="""You are a helpful assistant that can interact with AWS Knowledge Base.
    Use the available tools when relevant to retrieve and process AWS information.""",
    llm="gpt-4o-mini",
    tools=MCP("npx -y @modelcontextprotocol/server-aws-kb-retrieval",
              env={
                  "AWS_ACCESS_KEY_ID": aws_access_key,
                  "AWS_SECRET_ACCESS_KEY": aws_secret_key,
                  "AWS_REGION": aws_region
              })
)

aws_kb_agent.start("Search AWS documentation about EC2 instances") 