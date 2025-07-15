#!/usr/bin/env python3

from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agent with telemetry capabilities
telemetry_agent = Agent(
    name="Analytics Agent",
    role="Data Analytics Specialist",
    goal="Analyze real telemetry data and generate insights",
    backstory="You are a data analyst who specializes in understanding usage patterns and generating actionable insights from telemetry data collected from PraisonAI agents.",
    llm="gpt-4o-mini"
)

# Create task for telemetry analysis
telemetry_task = Task(
    name="analyze_telemetry",
    description="""
    Analyze real telemetry data from PraisonAI agents and provide insights:
    
    Your task is to:
    1. Collect current telemetry metrics from the system
    2. Analyze performance patterns and trends
    3. Identify usage patterns and optimization opportunities
    4. Review error patterns and provide recommendations
    5. Assess user experience and satisfaction indicators
    
    Provide analysis of:
    1. Agent execution metrics and performance trends
    2. Task completion rates and success patterns
    3. Tool usage patterns and optimization opportunities
    4. Error analysis and recommendations for improvement
    5. System health and reliability indicators
    """,
    expected_output="Real telemetry analysis with actionable insights and recommendations based on actual system metrics",
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
    print("This example demonstrates real telemetry collection and analysis for AI agents")
    print("=" * 80)
    
    # Enable and collect real telemetry data
    try:
        from praisonaiagents.telemetry import get_telemetry, enable_telemetry
        
        # Enable telemetry
        enable_telemetry()
        telemetry = get_telemetry()
        
        # Simulate some agent activities for demonstration
        print("\n🔬 Collecting Real Telemetry Data...")
        telemetry.track_agent_execution("Analytics Agent", success=True)
        telemetry.track_task_completion("analyze_telemetry", success=True)
        telemetry.track_tool_usage("search_tool", success=True)
        telemetry.track_feature_usage("telemetry_analysis")
        
        # Get current metrics
        metrics = telemetry.get_metrics()
        
        # Display real telemetry data
        print("\n📈 Real Telemetry Metrics:")
        print("┌─────────────────────────────────────────────────────┐")
        print("│ Performance Metrics                                 │")
        print("├─────────────────────────────────────────────────────┤")
        print(f"│ • Agent Executions: {metrics.get('metrics', {}).get('agent_executions', 0):<29} │")
        print(f"│ • Task Completions: {metrics.get('metrics', {}).get('task_completions', 0):<29} │")
        print(f"│ • Tool Calls: {metrics.get('metrics', {}).get('tool_calls', 0):<33} │")
        print(f"│ • Errors: {metrics.get('metrics', {}).get('errors', 0):<37} │")
        print(f"│ • Session ID: {metrics.get('session_id', 'N/A')[:20]:<27} │")
        print("└─────────────────────────────────────────────────────┘")
        
        print("\n🔧 System Environment:")
        print("┌─────────────────────────────────────────────────────┐")
        env = metrics.get('environment', {})
        print(f"│ • Python Version: {env.get('python_version', 'N/A'):<25} │")
        print(f"│ • OS Type: {env.get('os_type', 'N/A'):<34} │")
        print(f"│ • Framework Version: {env.get('framework_version', 'N/A'):<22} │")
        print(f"│ • Telemetry Enabled: {metrics.get('enabled', False):<23} │")
        print("└─────────────────────────────────────────────────────┘")
        
        print("\n🔒 Privacy Information:")
        print("┌─────────────────────────────────────────────────────┐")
        print("│ • No personal data collected                        │")
        print("│ • No prompts, responses, or user content tracked    │")
        print("│ • Only anonymous usage metrics                      │")
        print("│ • Respects DO_NOT_TRACK environment variable        │")
        print("│ • Can be disabled via PRAISONAI_TELEMETRY_DISABLED  │")
        print("└─────────────────────────────────────────────────────┘")
        
    except Exception as e:
        print(f"\n⚠️  Real telemetry unavailable: {e}")
        print("Falling back to demonstration mode...")
        
        # Show sample telemetry data as fallback
        print("\n📈 Sample Telemetry Metrics:")
        print("┌─────────────────────────────────────────────────────┐")
        print("│ Performance Metrics                                 │")
        print("├─────────────────────────────────────────────────────┤")
        print("│ • Total Agent Executions: 1,234                    │")
        print("│ • Average Response Time: 2.3 seconds               │")
        print("│ • Success Rate: 98.5%                              │")
        print("│ • Uptime: 99.9%                                    │")
        print("└─────────────────────────────────────────────────────┘")
    
    # Run the agent to analyze the telemetry
    _ = workflow.start()
    
    print("\n" + "=" * 80)
    print("✅ Telemetry Analysis Complete")
    print("💡 Key Benefits of Telemetry:")
    print("   • Monitor performance and reliability")
    print("   • Identify usage patterns and optimization opportunities")
    print("   • Enable data-driven improvements")
    print("   • Detect and prevent issues proactively")
    print("   • Privacy-first design - no personal data collected")
    print("🔧 Configure telemetry: set PRAISONAI_TELEMETRY_DISABLED=true to disable")
