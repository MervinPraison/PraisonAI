#!/usr/bin/env python3
"""
A2A (Agent-to-Agent) Server and Client Example

Demonstrates:
- Launching an agent as A2A server
- Agent card discovery
- Sending A2A messages
- JSON-RPC protocol

Usage:
    # Run this example (starts server)
    python a2a_server_client.py
    
    # Or use CLI:
    praisonai serve a2a --port 8082
    
    # Test with curl:
    curl http://localhost:8082/.well-known/agent.json
    curl -X POST http://localhost:8082/a2a \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"type":"text","text":"Hello!"}]}}}'
"""

import os
import sys
import json
import threading
import time

if not os.environ.get("OPENAI_API_KEY"):
    print("Error: OPENAI_API_KEY environment variable not set")
    sys.exit(1)


def run_server():
    """Run A2A server."""
    try:
        from praisonaiagents import Agent
        from praisonaiagents.ui.a2a import A2A
        from fastapi import FastAPI
        import uvicorn
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install with: pip install 'praisonaiagents[api]'")
        sys.exit(1)
    
    # Create agent
    agent = Agent(
        name="A2A-Assistant",
        role="Helpful AI Assistant",
        goal="Help other agents and users with their questions",
        backstory="You are a knowledgeable assistant accessible via A2A protocol.",
        llm="gpt-4o-mini"
    )
    
    # Create A2A interface
    a2a = A2A(
        agent=agent,
        url="http://localhost:8082/a2a",
        name="A2A-Assistant",
        description="A helpful AI assistant accessible via A2A protocol"
    )
    
    # Create FastAPI app
    app = FastAPI(title="PraisonAI A2A Server")
    app.include_router(a2a.get_router())
    
    # Add discovery endpoint
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": "praisonai-a2a",
            "providers": [{"type": "a2a", "name": "A2A Protocol", "capabilities": ["agent-card", "message-send"]}],
            "endpoints": [{"name": "a2a", "provider_type": "a2a", "streaming": ["sse"]}]
        }
    
    @app.get("/")
    async def root():
        return {
            "message": "PraisonAI A2A Server",
            "agent_card": "/.well-known/agent.json",
            "a2a_endpoint": "/a2a",
            "discovery": "/__praisonai__/discovery"
        }
    
    print("Starting A2A server on http://localhost:8082")
    print("Agent Card: http://localhost:8082/.well-known/agent.json")
    print("A2A Endpoint: http://localhost:8082/a2a")
    
    uvicorn.run(app, host="127.0.0.1", port=8082, log_level="warning")


def run_client():
    """Run A2A client test."""
    import urllib.request
    import urllib.error
    
    base_url = "http://localhost:8082"
    
    print("\n--- A2A Client Test ---")
    
    # 1. Get agent card
    print("\n1. Getting Agent Card...")
    try:
        req = urllib.request.Request(f"{base_url}/.well-known/agent.json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            agent_card = json.loads(resp.read().decode())
            print(f"   Agent: {agent_card.get('name')}")
            print(f"   URL: {agent_card.get('url')}")
            print(f"   Capabilities: {agent_card.get('capabilities', {})}")
    except Exception as e:
        print(f"   Error: {e}")
        return
    
    # 2. Send A2A message
    print("\n2. Sending A2A Message...")
    message = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "test-1",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello! What can you help me with?"}]
            }
        }
    }
    
    try:
        req = urllib.request.Request(
            f"{base_url}/a2a",
            data=json.dumps(message).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            response = json.loads(resp.read().decode())
            if "result" in response:
                result_msg = response["result"].get("message", {})
                parts = result_msg.get("parts", [])
                for part in parts:
                    if part.get("type") == "text":
                        print(f"   Response: {part.get('text', '')[:200]}...")
            elif "error" in response:
                print(f"   Error: {response['error']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 3. Check discovery
    print("\n3. Checking Discovery...")
    try:
        req = urllib.request.Request(f"{base_url}/__praisonai__/discovery")
        with urllib.request.urlopen(req, timeout=5) as resp:
            discovery = json.loads(resp.read().decode())
            print(f"   Server: {discovery.get('server_name')}")
            print(f"   Providers: {[p.get('type') for p in discovery.get('providers', [])]}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n✓ A2A client test completed!")


def main():
    print("=" * 60)
    print("A2A (Agent-to-Agent) Server and Client Example")
    print("=" * 60)
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "server"
    
    if mode == "client":
        run_client()
    elif mode == "test":
        # Start server in background, run client, then stop
        print("Starting server in background...")
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(3)  # Wait for server to start
        run_client()
    else:
        print("\nStarting A2A server...")
        print("Press Ctrl+C to stop")
        print("\nTo test, run in another terminal:")
        print("  python a2a_server_client.py client")
        run_server()


if __name__ == "__main__":
    main()
