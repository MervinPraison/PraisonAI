#!/usr/bin/env python3
"""
Remote Agent Connectivity Example

This example demonstrates how to connect to agents running on remote servers,
similar to Google ADK's agent connectivity pattern.

Usage:
1. First, start a remote agent server:
   python remote_agent_server.py

2. Then run this client to connect to it:
   python remote_agent_example.py
"""

from praisonaiagents import Session
import time

def example_remote_agent_connection():
    """
    Example demonstrating remote agent connectivity similar to Google ADK.
    """
    print("🌐 Remote Agent Connectivity Example")
    print("=" * 50)
    
    # Example 1: Connect to remote agent using IP:port format
    try:
        print("\n1. Connecting to remote agent at 192.168.1.10:8000...")
        
        # Create a session with remote agent URL (similar to Google ADK)
        session = Session(agent_url="192.168.1.10:8000/agent")
        
        print(f"✅ Connected! Session: {session}")
        
        # Send a message to the remote agent
        response = session.chat("Hello from the client!")
        print(f"📨 Sent: 'Hello from the client!'")
        print(f"📨 Received: {response}")
        
        # Send another message using the alias method (Google ADK pattern)
        response = session.send_message("What can you help me with?")
        print(f"📨 Sent: 'What can you help me with?'")
        print(f"📨 Received: {response}")
        
    except ConnectionError as e:
        print(f"❌ Connection failed: {e}")
        print("💡 Make sure the remote agent server is running at 192.168.1.10:8000")
    
    # Example 2: Connect to localhost for testing
    try:
        print("\n2. Connecting to localhost for testing...")
        
        # Connect to local server (for testing)
        session = Session(agent_url="localhost:8000/agent")
        
        print(f"✅ Connected! Session: {session}")
        
        # Test the connection
        response = session.chat("Test message")
        print(f"📨 Response: {response}")
        
    except ConnectionError as e:
        print(f"❌ Connection failed: {e}")
        print("💡 Start a local agent server first with: python remote_agent_server.py")

def example_error_handling():
    """
    Example demonstrating error handling for remote sessions.
    """
    print("\n\n🚨 Error Handling Examples")
    print("=" * 50)
    
    try:
        # Create a remote session
        session = Session(agent_url="localhost:8000/agent")
        
        # These operations are not available for remote sessions
        print("\n❌ Attempting to access memory (should fail)...")
        session.memory.store_short_term("test")
        
    except ConnectionError:
        print("⚠️  Cannot connect to remote agent (expected if server not running)")
    except ValueError as e:
        print(f"✅ Correctly caught error: {e}")
    
    try:
        session = Session(agent_url="localhost:8000/agent")
        print("\n❌ Attempting to create local agent (should fail)...")
        agent = session.Agent(name="Test", role="Assistant")
        
    except ConnectionError:
        print("⚠️  Cannot connect to remote agent (expected if server not running)")
    except ValueError as e:
        print(f"✅ Correctly caught error: {e}")

def comparison_with_google_adk():
    """
    Shows the comparison between Google ADK and PraisonAI patterns.
    """
    print("\n\n🔄 Comparison with Google ADK")
    print("=" * 50)
    
    print("\n📋 Google ADK Pattern:")
    print("""
    from adk.agent import Agent
    from adk.session import Session

    # Connect to remote agent
    session = Session(agent_url="192.168.1.10:8000")
    response = session.send_message("Hello from client!")
    """)
    
    print("📋 PraisonAI Pattern:")
    print("""
    from praisonaiagents import Session

    # Connect to remote agent
    session = Session(agent_url="192.168.1.10:8000/agent")
    response = session.chat("Hello from client!")
    # OR
    response = session.send_message("Hello from client!")
    """)
    
    print("✨ Key similarities:")
    print("• Direct agent URL connectivity")
    print("• Simple session-based API")
    print("• Similar message sending patterns")
    print("• Error handling for connection issues")

if __name__ == "__main__":
    example_remote_agent_connection()
    example_error_handling()
    comparison_with_google_adk()
    
    print("\n\n🎯 Summary")
    print("=" * 50)
    print("✅ Remote agent connectivity implemented")
    print("✅ Google ADK-like API pattern supported")  
    print("✅ Backward compatibility maintained")
    print("✅ Proper error handling for remote sessions")
    print("\n💡 To test with a real server, run remote_agent_server.py first!")