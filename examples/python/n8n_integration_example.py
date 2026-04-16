"""Complete n8n Integration Example for PraisonAI

This example demonstrates the complete bidirectional n8n ↔ PraisonAI integration:

1. PraisonAI → n8n: Agents executing n8n workflows (using PraisonAI-Tools)
2. n8n → PraisonAI: n8n workflows invoking PraisonAI agents (using API endpoint)

Prerequisites:
1. Install dependencies:
   pip install "praisonai-tools[n8n]" fastapi uvicorn

2. Set up n8n instance:
   docker run -it --rm --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n

3. Environment variables:
   export N8N_URL="http://localhost:5678"
   export N8N_API_KEY="your-api-key"  # optional for local testing

Usage:
    python examples/python/n8n_integration_example.py
"""

import os
import asyncio
import uvicorn
from fastapi import FastAPI
from praisonaiagents import Agent


def setup_praisonai_agents():
    """Set up PraisonAI agents with n8n tools."""
    print("🚀 Setting up PraisonAI agents with n8n capabilities...")
    
    try:
        from praisonai_tools.n8n import n8n_workflow, n8n_list_workflows
        
        # Create automation agent with n8n tools
        automation_agent = Agent(
            name="automation-agent",
            instructions="""
            You are an automation specialist with access to n8n's 400+ integrations.
            You can help users automate workflows across platforms like:
            
            - Communication: Slack, Discord, Telegram, Gmail, Teams
            - Productivity: Notion, Google Sheets, Airtable, Trello
            - Databases: PostgreSQL, MongoDB, MySQL, Redis
            - APIs: REST, GraphQL, webhooks
            
            When asked to perform automation tasks:
            1. First list available n8n workflows if needed
            2. Execute the appropriate workflow with the provided data
            3. Explain what the workflow accomplished
            
            Always be helpful and provide clear explanations.
            """,
            tools=[n8n_workflow, n8n_list_workflows],
            llm="gpt-4o-mini"
        )
        
        # Create notification agent focused on messaging
        notification_agent = Agent(
            name="notification-agent", 
            instructions="""
            You specialize in sending notifications and messages across platforms.
            You have access to n8n workflows for various messaging platforms.
            
            When asked to send notifications:
            1. Determine the best platform for the message
            2. Use appropriate n8n workflow for that platform
            3. Include relevant context and formatting
            
            Be efficient and reliable with notifications.
            """,
            tools=[n8n_workflow],
            llm="gpt-4o-mini"
        )
        
        return {
            "automation": automation_agent,
            "notification": notification_agent
        }
        
    except ImportError as e:
        print(f"❌ Error importing n8n tools: {e}")
        print("💡 Install with: pip install 'praisonai-tools[n8n]'")
        return {}


def setup_api_server_with_agents(agents):
    """Set up FastAPI server with agent invoke endpoints."""
    print("🌐 Setting up API server for n8n → PraisonAI integration...")
    
    from praisonai.api.agent_invoke import register_agent, router
    
    # Create FastAPI app
    app = FastAPI(
        title="PraisonAI n8n Integration Server",
        description="API server for n8n to invoke PraisonAI agents",
        version="1.0.0"
    )
    
    # Include agent invoke router
    app.include_router(router)
    
    # Register agents
    for agent_id, agent in agents.items():
        register_agent(agent_id, agent)
        print(f"📋 Registered agent: {agent_id}")
    
    @app.get("/")
    async def root():
        """Root endpoint with integration information."""
        return {
            "message": "PraisonAI n8n Integration Server",
            "available_agents": list(agents.keys()),
            "endpoints": {
                "invoke_agent": "/api/v1/agents/{agent_id}/invoke",
                "list_agents": "/api/v1/agents",
                "agent_info": "/api/v1/agents/{agent_id}"
            },
            "n8n_integration": {
                "description": "Use HTTP Request node in n8n to invoke agents",
                "example_url": "http://localhost:8000/api/v1/agents/automation/invoke",
                "example_body": {
                    "message": "Send a Slack message to #general saying 'Hello from n8n!'",
                    "session_id": "n8n-workflow-123"
                }
            }
        }
    
    return app


async def demo_praisonai_to_n8n(agents):
    """Demonstrate PraisonAI agents calling n8n workflows."""
    print("\n🔄 Demo: PraisonAI → n8n Integration")
    print("=" * 50)
    
    if not agents:
        print("❌ No agents available for demo")
        return
    
    automation_agent = agents.get("automation")
    if not automation_agent:
        print("❌ Automation agent not available")
        return
    
    try:
        print("📋 Testing agent with n8n workflow listing...")
        response = automation_agent.start(
            "Can you list the available n8n workflows?"
        )
        print(f"🤖 Agent: {response}")
        
        print("\n🚀 Testing workflow execution...")
        response = automation_agent.start(
            "I need to send a notification that our deployment was successful. "
            "Can you help me send this via Slack to the #deployments channel?"
        )
        print(f"🤖 Agent: {response}")
        
    except Exception as e:
        print(f"❌ Demo error: {e}")


async def demo_n8n_to_praisonai():
    """Demonstrate n8n invoking PraisonAI agents via HTTP."""
    print("\n🔄 Demo: n8n → PraisonAI Integration")
    print("=" * 50)
    
    try:
        import httpx
        
        # Simulate n8n HTTP Request node call
        print("📡 Simulating n8n HTTP Request node call...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/api/v1/agents/notification/invoke",
                json={
                    "message": "A new user has signed up: john@example.com. Please send a welcome email.",
                    "session_id": "n8n-user-signup-workflow"
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success: {data['result']}")
                print(f"📊 Session: {data['session_id']}")
            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
                
    except httpx.ConnectError:
        print("❌ Connection error: Make sure the API server is running")
        print("💡 Start server in another terminal: python examples/python/n8n_integration_example.py --server")
    except Exception as e:
        print(f"❌ Demo error: {e}")


def create_n8n_workflow_examples():
    """Show examples of n8n workflow configurations."""
    print("\n📝 n8n Workflow Configuration Examples")
    print("=" * 50)
    
    print("""
🔹 HTTP Request Node (n8n → PraisonAI):
   Method: POST
   URL: http://localhost:8000/api/v1/agents/automation/invoke
   Body:
   {
     "message": "{{ $json.user_message }}",
     "session_id": "{{ $json.session_id || workflow.id }}"
   }
   
🔹 Webhook Trigger for PraisonAI response:
   URL: http://localhost:8000/webhook/praisonai-response
   Method: POST
   
🔹 Slack notification after agent response:
   Channel: {{ $json.channel || '#general' }}
   Message: Agent response: {{ $json.agent_result }}
""")


async def run_interactive_demo():
    """Run interactive demo of the integration."""
    print("\n🎮 Interactive Demo")
    print("=" * 20)
    
    # Set up agents
    agents = setup_praisonai_agents()
    if not agents:
        print("❌ Cannot run interactive demo without agents")
        return
    
    automation_agent = agents.get("automation")
    if not automation_agent:
        print("❌ Automation agent not available")
        return
    
    print("💬 Chat with the automation agent (type 'quit' to exit)")
    print("💡 Try: 'List available n8n workflows'")
    print("💡 Try: 'Send a Slack message to #general'")
    
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            if not user_input:
                continue
                
            print("🤖 Agent: ", end="", flush=True)
            response = automation_agent.start(user_input)
            print(response)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")


def run_server(port=8000):
    """Run the API server for n8n integration."""
    print(f"\n🚀 Starting PraisonAI n8n Integration Server on port {port}...")
    
    # Set up agents
    agents = setup_praisonai_agents()
    
    # Create app
    app = setup_api_server_with_agents(agents)
    
    print(f"✅ Server ready at http://localhost:{port}")
    print(f"📊 Available agents: {list(agents.keys())}")
    print("\n🔗 n8n HTTP Request Node Configuration:")
    print(f"   URL: http://localhost:{port}/api/v1/agents/{{agent_id}}/invoke")
    print("   Method: POST")
    print('   Body: {"message": "Your message here", "session_id": "optional"}')
    
    # Run server
    uvicorn.run(app, host="0.0.0.0", port=port)


async def main():
    """Main function to run demos."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PraisonAI n8n Integration Demo")
    parser.add_argument("--server", action="store_true", help="Run API server")
    parser.add_argument("--demo", action="store_true", help="Run demos")
    parser.add_argument("--interactive", action="store_true", help="Run interactive demo")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    
    args = parser.parse_args()
    
    if args.server:
        run_server(args.port)
    elif args.interactive:
        await run_interactive_demo()
    elif args.demo:
        # Set up agents for demos
        agents = setup_praisonai_agents()
        
        # Run demos
        await demo_praisonai_to_n8n(agents)
        create_n8n_workflow_examples()
        print("\n💡 To test n8n → PraisonAI, start the server:")
        print("   python examples/python/n8n_integration_example.py --server")
        print("   Then run: python examples/python/n8n_integration_example.py --test-api")
        
    else:
        # Default: show info and run basic demo
        print("🔗 PraisonAI ↔ n8n Bidirectional Integration")
        print("=" * 50)
        
        print("\n📋 Integration Components:")
        print("1. 🔧 PraisonAI-Tools: n8n workflow execution tools")
        print("2. 🌐 API Endpoint: Agent invoke endpoint for n8n")
        print("3. 🤖 Agents: PraisonAI agents with n8n capabilities")
        
        print("\n🚀 Available Commands:")
        print("   --demo        Run integration demos")
        print("   --server      Start API server for n8n")
        print("   --interactive Run interactive agent chat")
        
        # Quick demo
        agents = setup_praisonai_agents()
        if agents:
            await demo_praisonai_to_n8n(agents)
            create_n8n_workflow_examples()


if __name__ == "__main__":
    asyncio.run(main())