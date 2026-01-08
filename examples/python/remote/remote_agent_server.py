#!/usr/bin/env python3
"""
Remote Agent Server Example

This example demonstrates how to set up an agent as a remote server
that can be accessed by other clients using the Session(agent_url=...) pattern.

Usage:
    python remote_agent_server.py

Then connect from another machine/process:
    python remote_agent_example.py
"""

from praisonaiagents import Agent
import time

def setup_remote_agent_server():
    """
    Set up an agent as a remote server accessible via HTTP API.
    """
    print("🚀 Setting up Remote Agent Server")
    print("=" * 50)
    
    # Create an agent that will serve as the remote agent
    agent = Agent(
        name="RemoteAssistant",
        role="Helpful Remote AI Assistant", 
        goal="Assist users with their queries via remote connections",
        backstory="I am an AI assistant running on a remote server, ready to help clients connect and interact with me.",
        llm="gpt-4o-mini",  # or any other supported model
        verbose=True
    )
    
    print(f"📝 Created agent: {agent}")
    print(f"🔧 Agent details:")
    print(f"   • Name: {agent.name}")
    print(f"   • Role: {agent.role}")
    print(f"   • Goal: {agent.goal}")
    
    # Launch the agent as an HTTP API server
    print(f"\n🌐 Launching agent server...")
    print(f"📡 Server will be accessible at:")
    print(f"   • Local: http://localhost:8000/agent")
    print(f"   • Network: http://<your-ip>:8000/agent")
    print(f"\n🔗 Clients can connect using:")
    print(f"   session = Session(agent_url='<server-ip>:8000/agent')")
    print(f"\n⏹️  Press Ctrl+C to stop the server")
    print("=" * 50)
    
    # This will start the HTTP server and block until interrupted
    try:
        agent.launch(path="/agent", port=8000, host="0.0.0.0")
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")

def setup_multiple_agents():
    """
    Example of setting up multiple agents on the same server.
    """
    print("🚀 Setting up Multiple Remote Agents")
    print("=" * 50)
    
    # Create different specialized agents
    research_agent = Agent(
        name="ResearchAgent",
        role="Research Specialist",
        instructions="You are a research specialist who helps with finding and analyzing information."
    )
    
    coding_agent = Agent(
        name="CodingAgent", 
        role="Programming Assistant",
        instructions="You are a programming assistant who helps with coding questions and debugging."
    )
    
    # Launch them on different endpoints
    print("🌐 Launching multiple agents:")
    print("📡 Research Agent: http://localhost:8000/research")
    print("📡 Coding Agent: http://localhost:8000/coding")
    print("\n🔗 Connect using:")
    print("   research_session = Session(agent_url='localhost:8000/research')")
    print("   coding_session = Session(agent_url='localhost:8000/coding')")
    
    try:
        # Launch both agents (this will start the server)
        research_agent.launch(path="/research", port=8000, host="0.0.0.0")
        coding_agent.launch(path="/coding", port=8000, host="0.0.0.0")
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--multiple":
        setup_multiple_agents()
    else:
        setup_remote_agent_server()
        
    print("\n\n✅ Remote agent server example completed!")
    print("💡 Tip: Use --multiple flag to run multiple agents example")