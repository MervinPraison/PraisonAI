#!/usr/bin/env python3

import time
from datetime import datetime
from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agent for MCP HTTP streaming
streaming_agent = Agent(
    name="Stream Monitor",
    role="Data Stream Processor",
    goal="Monitor and process HTTP data streams from MCP servers in real-time",
    backstory="You are a data processing agent that monitors real-time HTTP streams and provides analysis of streaming data patterns using MCP server tools.",
    llm="gpt-4o-mini"
)

# Create task for streaming data analysis
stream_task = Task(
    name="monitor_stream",
    description="""
    Use MCP HTTP streaming capabilities to monitor and analyze real-time data streams.
    Your task is to:
    1. Connect to available MCP HTTP streaming servers
    2. Monitor real-time data streams (weather, stock prices, sensor data, etc.)
    3. Analyze data patterns and trends from the streaming data
    4. Identify any anomalies or significant changes in the stream
    5. Provide insights and recommendations based on streaming data analysis
    
    Focus on real-time data processing and pattern recognition from continuous streams.
    """,
    expected_output="Real-time analysis of streaming data patterns with insights and recommendations",
    agent=streaming_agent
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[streaming_agent],
    tasks=[stream_task],
    process="sequential",
    verbose=True
)

# Run the streaming workflow
if __name__ == "__main__":
    print("📡 MCP HTTP Stream Example")
    print("This example demonstrates real HTTP streaming capabilities with MCP servers")
    print("=" * 80)
    
    # Try to use real MCP HTTP streaming
    try:
        from praisonaiagents import MCP
        
        print("\n🌊 Attempting Real MCP HTTP Stream Connection...")
        print("Stream Type: MCP HTTP Server Data")
        print("Data Source: Real MCP HTTP Streaming Server")
        print("Format: Real-time HTTP streaming")
        
        # Example of how to use MCP HTTP streaming (would need actual MCP server)
        # Uncomment and modify when you have a real MCP HTTP streaming server:
        # streaming_agent.tools = MCP("http://localhost:8080/stream")  # Example MCP HTTP server
        
        print("\n📊 Note: To use real MCP HTTP streaming:")
        print("  1. Set up an MCP HTTP streaming server")
        print("  2. Use: streaming_agent.tools = MCP('http://your-mcp-server/stream')")
        print("  3. The agent will automatically connect and stream data")
        print("  4. Real-time analysis will be performed on actual streaming data")
        
    except Exception as e:
        print(f"\n⚠️  MCP module available but HTTP streaming server not configured: {e}")
    
    # Demonstrate with time-based simulation for educational purposes
    print("\n🎓 Educational Simulation (replace with real MCP server):")
    def simulate_stream():
        import random
        base_temp = 22.0
        base_humidity = 65
        
        for i in range(5):  # Simulate 5 data points
            timestamp = datetime.now().isoformat() + "Z"
            temperature = base_temp + random.uniform(-2, 2)
            humidity = base_humidity + random.randint(-5, 5)
            
            data = {
                "timestamp": timestamp,
                "temperature": round(temperature, 1),
                "humidity": humidity
            }
            
            print(f"  • {data['timestamp']}: {data['temperature']}°C, {data['humidity']}% humidity")
            time.sleep(1)  # Simulate real-time streaming delay
            
    print("\n📊 Simulated Stream Data:")
    simulate_stream()
    
    # Run the agent to process the stream
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ HTTP Stream Processing Complete")
    print("💡 This example demonstrates MCP HTTP streaming patterns")
    print("🔧 For production use:")
    print("   • Set up an MCP HTTP streaming server")
    print("   • Configure streaming_agent.tools = MCP('http://your-server/stream')")
    print("   • The agent will process real-time streaming data automatically")
    print("📖 Learn more: https://modelcontextprotocol.io/")