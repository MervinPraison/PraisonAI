"""
Linear Agent Example for PraisonAI.

Demonstrates how to create a Linear bot that responds to issue mentions
and assignments with full coding capabilities.
"""

import asyncio
from praisonaiagents import Agent
from praisonai.bots import LinearBot

# Create an agent with Linear tools and coding capabilities
agent = Agent(
    name="PraisonAI Coder",
    instructions="""
    You are an autonomous coding agent integrated with Linear.
    
    When you are mentioned or assigned an issue:
    1. Analyze the issue description and requirements
    2. Break down complex tasks into smaller steps  
    3. Use available tools to implement solutions
    4. Update the issue with progress comments
    5. Create GitHub pull requests when code changes are needed
    
    Focus on being helpful, thorough, and providing clear updates.
    """,
    llm="gpt-4o-mini",
    tools=[
        "linear_search_issues",
        "linear_get_issue", 
        "linear_add_comment",
        "linear_update_issue",
        "linear_list_teams",
        "linear_list_issue_states",
        "github_create_branch",
        "github_commit_and_push", 
        "github_create_pull_request",
        "read_file",
        "write_file",
        "execute_command"
    ],
    memory=True,
    web_search=True,
    auto_approve_tools=True,
)

# Create Linear bot
bot = LinearBot(
    token="your-linear-oauth-token",  # or set LINEAR_OAUTH_TOKEN env var
    signing_secret="your-webhook-secret",  # or set LINEAR_WEBHOOK_SECRET env var
    agent=agent,
    webhook_port=8080,
)

async def main():
    """Start the Linear bot."""
    print("Starting Linear bot...")
    print("Set up your Linear webhook to point to: http://your-host:8080/webhook")
    print("Configure AgentSession and Comment events in Linear webhook settings")
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nStopping bot...")
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())