#!/usr/bin/env python3
"""
JIRA Agent Watch Example

This example demonstrates how to use the JIRA watch tools with PraisonAI agents.
The agent can monitor JIRA issues and projects for changes, search for issues,
and get detailed issue information.

Setup:
1. Install JIRA library: pip install jira
2. Set environment variables:
   - JIRA_EMAIL=your_email@example.com (for cloud JIRA)
   - JIRA_API_TOKEN=your_api_token
   - Or use JIRA_USERNAME + JIRA_API_TOKEN for server JIRA

Usage:
    python jira_agent_example.py
"""

import os
from praisonaiagents import Agent
from praisonaiagents.tools import jira_tools


def main():
    """Demonstrate JIRA agent watch capabilities."""
    
    # Check if JIRA credentials are available
    jira_email = os.getenv('JIRA_EMAIL')
    jira_token = os.getenv('JIRA_API_TOKEN')
    jira_username = os.getenv('JIRA_USERNAME')
    
    if not jira_token:
        print("❌ JIRA_API_TOKEN environment variable not set")
        print("Please set your JIRA API token:")
        print("export JIRA_API_TOKEN='your_token_here'")
        return
        
    if not (jira_email or jira_username):
        print("❌ JIRA credentials incomplete")
        print("Please set either:")
        print("- JIRA_EMAIL (for cloud JIRA)")
        print("- JIRA_USERNAME (for server JIRA)")
        return

    # Create agent with JIRA tools
    agent = Agent(
        name="JIRA Monitor Agent",
        instructions="""
        You are a JIRA monitoring agent. You can:
        
        1. Watch specific JIRA issues for changes
        2. Monitor JIRA projects for new issues and updates  
        3. Search for issues using JQL queries
        4. Get detailed information about specific issues
        
        When using JIRA tools, always provide the full JIRA URL 
        (e.g., https://yourcompany.atlassian.net).
        
        Be helpful and provide clear summaries of JIRA activity.
        """,
        tools=jira_tools(),  # Add all JIRA tools
        llm="gpt-4o-mini"
    )
    
    print("🎯 JIRA Agent Watch Example")
    print("=" * 50)
    print()
    print("Available JIRA tools:")
    print("- jira_watch_issue: Monitor a specific issue for changes")
    print("- jira_watch_project: Monitor a project for new/updated issues")
    print("- jira_get_issue_info: Get detailed info about an issue")  
    print("- jira_search_issues: Search issues using JQL")
    print()
    
    # Example interactions
    example_prompts = [
        "Get information about JIRA issue DEMO-1 from https://praisonai.atlassian.net",
        "Search for open issues in project DEMO from https://praisonai.atlassian.net using JQL: 'project = DEMO AND status = Open'",
        "Watch JIRA issue DEMO-1 from https://praisonai.atlassian.net for 2 minutes (check every 60 seconds, max 2 checks)",
    ]
    
    print("📝 Example prompts you can try:")
    for i, prompt in enumerate(example_prompts, 1):
        print(f"{i}. {prompt}")
    print()
    
    # Interactive mode
    print("💬 Interactive JIRA Agent (type 'quit' to exit)")
    print("-" * 50)
    
    while True:
        try:
            user_input = input("\n🧑 You: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
                
            if not user_input:
                continue
                
            print("🤖 Agent: ", end="", flush=True)
            response = agent.start(user_input)
            print(response)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()