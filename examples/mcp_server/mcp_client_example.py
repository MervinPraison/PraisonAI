#!/usr/bin/env python3
"""
MCP Client Example

Example of connecting to a PraisonAI MCP server as a client.

Prerequisites:
    1. Start the MCP server first:
       praisonai mcp serve --transport http-stream --port 8080
    
    2. Then run this client:
       python mcp_client_example.py

Environment Variables:
    OPENAI_API_KEY - Required for chat completion tools
"""

import requests


def main():
    """Connect to MCP server and call tools."""
    base_url = "http://127.0.0.1:8080/mcp"
    session_id = None
    
    print("PraisonAI MCP Client Example")
    print("=" * 40)
    
    # 1. Initialize connection
    print("\n1. Initializing connection...")
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {
                "name": "example-client",
                "version": "1.0.0",
            },
        },
    }
    
    response = requests.post(
        base_url,
        json=init_request,
        headers={"Content-Type": "application/json"},
    )
    
    if response.status_code == 200:
        result = response.json()
        session_id = response.headers.get("MCP-Session-Id")
        print(f"   Connected! Session ID: {session_id}")
        print(f"   Server: {result.get('result', {}).get('serverInfo', {})}")
        print(f"   Protocol: {result.get('result', {}).get('protocolVersion')}")
    else:
        print(f"   Error: {response.status_code}")
        return
    
    # 2. Send initialized notification
    print("\n2. Sending initialized notification...")
    init_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    requests.post(
        base_url,
        json=init_notification,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    print("   Done")
    
    # 3. List available tools
    print("\n3. Listing available tools...")
    list_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    
    response = requests.post(
        base_url,
        json=list_request,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    
    if response.status_code == 200:
        result = response.json()
        tools = result.get("result", {}).get("tools", [])
        print(f"   Found {len(tools)} tools")
        for tool in tools[:5]:  # Show first 5
            print(f"   - {tool.get('name')}")
        if len(tools) > 5:
            print(f"   ... and {len(tools) - 5} more")
    
    # 4. List available resources
    print("\n4. Listing available resources...")
    list_resources = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "resources/list",
        "params": {},
    }
    
    response = requests.post(
        base_url,
        json=list_resources,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    
    if response.status_code == 200:
        result = response.json()
        resources = result.get("result", {}).get("resources", [])
        print(f"   Found {len(resources)} resources")
        for res in resources:
            print(f"   - {res.get('uri')}")
    
    # 5. List available prompts
    print("\n5. Listing available prompts...")
    list_prompts = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "prompts/list",
        "params": {},
    }
    
    response = requests.post(
        base_url,
        json=list_prompts,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    
    if response.status_code == 200:
        result = response.json()
        prompts = result.get("result", {}).get("prompts", [])
        print(f"   Found {len(prompts)} prompts")
        for prompt in prompts:
            print(f"   - {prompt.get('name')}")
    
    # 6. Read a resource
    print("\n6. Reading MCP status resource...")
    read_resource = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "resources/read",
        "params": {
            "uri": "praisonai://mcp/status",
        },
    }
    
    response = requests.post(
        base_url,
        json=read_resource,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    
    if response.status_code == 200:
        result = response.json()
        contents = result.get("result", {}).get("contents", [])
        if contents:
            print(f"   Status: {contents[0].get('text', 'N/A')}")
    
    # 7. Get a prompt
    print("\n7. Getting deep-research prompt...")
    get_prompt = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "prompts/get",
        "params": {
            "name": "deep-research",
            "arguments": {
                "topic": "AI agents",
                "depth": "medium",
            },
        },
    }
    
    response = requests.post(
        base_url,
        json=get_prompt,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    
    if response.status_code == 200:
        result = response.json()
        messages = result.get("result", {}).get("messages", [])
        if messages:
            content = messages[0].get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            print(f"   Prompt preview: {text[:100]}...")
    
    # 8. Ping
    print("\n8. Pinging server...")
    ping_request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "ping",
        "params": {},
    }
    
    response = requests.post(
        base_url,
        json=ping_request,
        headers={
            "Content-Type": "application/json",
            "MCP-Session-Id": session_id,
        },
    )
    
    if response.status_code == 200:
        print("   Pong!")
    
    print("\n" + "=" * 40)
    print("MCP client example completed successfully!")


if __name__ == "__main__":
    main()
