#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agent with telemetry capabilities
telemetry_agent = Agent(
    name="Analytics Agent",
    role="Data Analytics Specialist",
    goal="Analyze usage patterns and generate insights",
    backstory="You are a data analyst who specializes in understanding usage patterns and generating actionable insights from telemetry data.",
    llm="gpt-4o-mini"
)

# Create task for telemetry analysis
telemetry_task = Task(
    name="analyze_telemetry",
    description="""
    Analyze this sample telemetry data and provide insights:
    
    SAMPLE TELEMETRY DATA:
    - Agent executions: 1,234 total
    - Average response time: 2.3 seconds
    - Success rate: 98.5%
    - Top tools used: search (45%), calculator (30%), file_operations (15%)
    - Peak usage hours: 9-11 AM, 2-4 PM
    - Error types: timeout (8), rate_limit (3), invalid_input (2)
    - User satisfaction: 4.2/5.0
    
    Provide analysis of:
    1. Performance metrics and trends
    2. Usage patterns and optimization opportunities
    3. Error analysis and recommendations
    4. User experience insights
    """,
    expected_output="Comprehensive telemetry analysis with actionable insights and recommendations",
    agent=telemetry_agent
)

# Create workflow
workflow = PraisonAIAgents(
    agents=[telemetry_agent],
    tasks=[telemetry_task],
    process="sequential",
    verbose=True
)

# Run the telemetry analysis
if __name__ == "__main__":
    print("📊 Comprehensive Telemetry Example")
    print("This example demonstrates telemetry collection and analysis for AI agents")
    print("=" * 80)
    
    # Show sample telemetry data
    print("\n📈 Sample Telemetry Metrics:")
    print("┌─────────────────────────────────────────────────────┐")
    print("│ Performance Metrics                                 │")
    print("├─────────────────────────────────────────────────────┤")
    print("│ • Total Agent Executions: 1,234                    │")
    print("│ • Average Response Time: 2.3 seconds               │")
    print("│ • Success Rate: 98.5%                              │")
    print("│ • Uptime: 99.9%                                    │")
    print("└─────────────────────────────────────────────────────┘")
    
    print("\n🔧 Tool Usage Analytics:")
    print("┌─────────────────────────────────────────────────────┐")
    print("│ • Search Tool: 45% (most popular)                  │")
    print("│ • Calculator: 30%                                  │")
    print("│ • File Operations: 15%                             │")
    print("│ • Other Tools: 10%                                 │")
    print("└─────────────────────────────────────────────────────┘")
    
    print("\n⏰ Usage Patterns:")
    print("┌─────────────────────────────────────────────────────┐")
    print("│ • Peak Hours: 9-11 AM, 2-4 PM                      │")
    print("│ • Low Activity: 12-1 PM, 6-8 PM                    │")
    print("│ • Weekend Usage: 60% of weekday average            │")
    print("└─────────────────────────────────────────────────────┘")
    
    print("\n❌ Error Analysis:")
    print("┌─────────────────────────────────────────────────────┐")
    print("│ • Timeout Errors: 8 occurrences                    │")
    print("│ • Rate Limit Errors: 3 occurrences                 │")
    print("│ • Invalid Input Errors: 2 occurrences              │")
    print("│ • Total Error Rate: 1.5%                           │")
    print("└─────────────────────────────────────────────────────┘")
    
    print("\n😊 User Experience:")
    print("┌─────────────────────────────────────────────────────┐")
    print("│ • Average Satisfaction: 4.2/5.0                    │")
    print("│ • Response Quality: 4.5/5.0                        │")
    print("│ • Ease of Use: 4.0/5.0                             │")
    print("│ • Overall Experience: 4.2/5.0                      │")
    print("└─────────────────────────────────────────────────────┘")
    
    # Run the agent to analyze the telemetry
    result = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ Telemetry Analysis Complete")
    print("💡 Key Benefits of Telemetry:")
    print("   • Monitor performance and reliability")
    print("   • Identify usage patterns and optimization opportunities")
    print("   • Track user satisfaction and experience")
    print("   • Enable data-driven improvements")
    print("   • Detect and prevent issues proactively")
    print("🔧 Configure telemetry in your agents for production monitoring")