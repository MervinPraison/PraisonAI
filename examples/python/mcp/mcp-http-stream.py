#!/usr/bin/env python3

import time
import json
from datetime import datetime
from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agent for MCP HTTP streaming
streaming_agent = Agent(
    name="Stream Monitor",
    role="Data Stream Processor",
    goal="Monitor and process HTTP data streams from MCP servers",
    backstory="You are a data processing agent that monitors real-time HTTP streams and provides analysis of streaming data patterns.",
    llm="gpt-4o-mini"
)

# Create task for streaming data analysis
stream_task = Task(
    name="monitor_stream",
    description="Monitor and analyze this simulated HTTP stream data from an MCP server. Provide insights about data patterns, trends, and any anomalies detected.",
    expected_output="Analysis of streaming data patterns with insights and recommendations",
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
    print("This example demonstrates HTTP streaming capabilities with MCP servers")
    print("=" * 80)
    
    # Simulate real-time streaming data
    print("\n🌊 Simulating HTTP Stream Data...")
    print("Stream Type: Weather Data")
    print("Data Source: HTTP MCP Server")
    print("Format: JSON streaming")
    
    # Simulate continuous streaming with time delays
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
            
    print("\n📊 Processing Stream Data:")
    simulate_stream()
    
    # Run the agent to process the stream
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ HTTP Stream Processing Complete")
    print("💡 This example shows basic HTTP streaming with MCP integration")
    print("🔧 In production, integrate with actual MCP servers using praisonaiagents.mcp module")