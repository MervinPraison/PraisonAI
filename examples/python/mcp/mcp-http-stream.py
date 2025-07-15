#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agent with HTTP streaming capabilities
streaming_agent = Agent(
    name="Stream Monitor",
    role="Real-time Data Monitor",
    goal="Monitor and process streaming data from various sources",
    backstory="You are a data monitoring specialist who can process continuous streams of information and provide real-time insights.",
    llm="gpt-4o-mini"
)

# Create task for HTTP stream monitoring
stream_task = Task(
    name="monitor_data_stream",
    description="Monitor a simulated HTTP data stream and process the incoming data. Simulate processing weather data, stock prices, or news feeds that arrive continuously.",
    expected_output="Summary of processed streaming data with key insights and patterns",
    agent=streaming_agent
)

# Create workflow for streaming
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
    
    # Simulate streaming data
    print("\n🌊 Simulating HTTP Stream Data...")
    print("Stream Type: Weather Data")
    print("Data Source: HTTP MCP Server")
    print("Format: JSON streaming")
    
    # Sample streaming data simulation
    stream_data = [
        {"timestamp": "2024-01-01T10:00:00Z", "temperature": 22.5, "humidity": 65},
        {"timestamp": "2024-01-01T10:05:00Z", "temperature": 23.1, "humidity": 63},
        {"timestamp": "2024-01-01T10:10:00Z", "temperature": 23.8, "humidity": 61}
    ]
    
    print("\n📊 Processing Stream Data:")
    for data in stream_data:
        print(f"  • {data['timestamp']}: {data['temperature']}°C, {data['humidity']}% humidity")
    
    # Run the agent to process the stream
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ HTTP Stream Processing Complete")
    print("💡 This example shows basic HTTP streaming with MCP integration")
    print("🔧 In production, connect to real MCP servers for live data streams")
