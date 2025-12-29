#!/usr/bin/env python3
"""
A2U (Agent-to-User) Event Stream Example

Demonstrates:
- Launching an A2U event stream server
- Subscribing to agent events
- SSE (Server-Sent Events) streaming
- Event filtering

Usage:
    # Run this example (starts server)
    python a2u_events_stream.py
    
    # Or use CLI:
    praisonai serve a2u --port 8083
    
    # Test with curl:
    curl http://localhost:8083/a2u/info
    curl -N http://localhost:8083/a2u/events/events
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
    """Run A2U server."""
    try:
        from fastapi import FastAPI
        import uvicorn
        from praisonai.endpoints.a2u_server import (
            create_a2u_routes,
            emit_agent_started,
            emit_agent_thinking,
            emit_agent_response,
            emit_agent_completed,
        )
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install with: pip install praisonai[serve]")
        sys.exit(1)
    
    app = FastAPI(title="PraisonAI A2U Server")
    
    # Add A2U routes
    create_a2u_routes(app)
    
    # Add discovery endpoint
    @app.get("/__praisonai__/discovery")
    async def discovery():
        return {
            "schema_version": "1.0.0",
            "server_name": "praisonai-a2u",
            "providers": [{"type": "a2u", "name": "A2U Event Stream", "capabilities": ["subscribe", "stream"]}],
            "endpoints": [{"name": "events", "provider_type": "a2u", "streaming": ["sse"]}]
        }
    
    @app.get("/")
    async def root():
        return {
            "message": "PraisonAI A2U Server",
            "info": "/a2u/info",
            "events": "/a2u/events/<stream>",
            "discovery": "/__praisonai__/discovery"
        }
    
    # Demo endpoint to emit events
    @app.post("/demo/emit")
    async def demo_emit():
        """Emit demo events for testing."""
        agent_id = "demo-agent-1"
        emit_agent_started(agent_id, "DemoAgent")
        emit_agent_thinking(agent_id, "Processing your request...")
        emit_agent_response(agent_id, "Here is my response to your query.")
        emit_agent_completed(agent_id, {"status": "success"})
        return {"message": "Demo events emitted", "agent_id": agent_id}
    
    print("Starting A2U server on http://localhost:8083")
    print("Info: http://localhost:8083/a2u/info")
    print("Events: http://localhost:8083/a2u/events/events")
    print("Demo: POST http://localhost:8083/demo/emit")
    
    uvicorn.run(app, host="127.0.0.1", port=8083, log_level="warning")


def run_client():
    """Run A2U client test."""
    import urllib.request
    import urllib.error
    
    base_url = "http://localhost:8083"
    
    print("\n--- A2U Client Test ---")
    
    # 1. Get A2U info
    print("\n1. Getting A2U Info...")
    try:
        req = urllib.request.Request(f"{base_url}/a2u/info")
        with urllib.request.urlopen(req, timeout=5) as resp:
            info = json.loads(resp.read().decode())
            print(f"   Name: {info.get('name')}")
            print(f"   Version: {info.get('version')}")
            print(f"   Streams: {info.get('streams')}")
            print(f"   Event Types: {info.get('event_types')}")
    except Exception as e:
        print(f"   Error: {e}")
        return
    
    # 2. Subscribe to events
    print("\n2. Subscribing to Events...")
    try:
        req = urllib.request.Request(
            f"{base_url}/a2u/subscribe",
            data=json.dumps({"stream": "events", "filters": []}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            sub = json.loads(resp.read().decode())
            print(f"   Subscription ID: {sub.get('subscription_id')}")
            print(f"   Stream URL: {sub.get('stream_url')}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 3. Emit demo events
    print("\n3. Emitting Demo Events...")
    try:
        req = urllib.request.Request(
            f"{base_url}/demo/emit",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            print(f"   {result.get('message')}")
            print(f"   Agent ID: {result.get('agent_id')}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 4. Check discovery
    print("\n4. Checking Discovery...")
    try:
        req = urllib.request.Request(f"{base_url}/__praisonai__/discovery")
        with urllib.request.urlopen(req, timeout=5) as resp:
            discovery = json.loads(resp.read().decode())
            print(f"   Server: {discovery.get('server_name')}")
            print(f"   Providers: {[p.get('type') for p in discovery.get('providers', [])]}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n✓ A2U client test completed!")
    print("\nTo stream events, run:")
    print(f"  curl -N {base_url}/a2u/events/events")


def main():
    print("=" * 60)
    print("A2U (Agent-to-User) Event Stream Example")
    print("=" * 60)
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "server"
    
    if mode == "client":
        run_client()
    elif mode == "test":
        print("Starting server in background...")
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(2)
        run_client()
    else:
        print("\nStarting A2U server...")
        print("Press Ctrl+C to stop")
        print("\nTo test, run in another terminal:")
        print("  python a2u_events_stream.py client")
        run_server()


if __name__ == "__main__":
    main()
