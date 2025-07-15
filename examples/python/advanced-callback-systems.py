"""
Advanced Callback Systems Example (Corrected)

This example demonstrates comprehensive callback systems using PraisonAI Agents' actual
callback architecture for real-time monitoring, metrics collection, and performance tracking.
"""

import time
import json
from datetime import datetime
from typing import Dict, Any, List
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.display_callback import register_display_callback, get_callback_manager
from praisonaiagents.tools import internet_search

print("=== Advanced Callback Systems Example (Corrected) ===\n")

# Custom Callback Classes adapted for PraisonAI Agents
class PerformanceMonitorCallback:
    """Monitor agent performance and execution metrics"""
    
    def __init__(self):
        self.metrics = {
            "interactions": 0,
            "tool_calls": 0,
            "errors": 0,
            "generation_events": 0,
            "start_time": time.time(),
            "agent_performance": {},
            "tool_usage": {}
        }
        self.active_operations = {}
    
    def handle_interaction(self, data: Dict[str, Any]):
        """Handle interaction callback"""
        self.metrics["interactions"] += 1
        agent_name = data.get("agent_name", "unknown")
        
        print(f"📋 Interaction: {agent_name} - {data.get('type', 'unknown')}")
        
        if agent_name not in self.metrics["agent_performance"]:
            self.metrics["agent_performance"][agent_name] = {
                "interactions": 0,
                "start_time": time.time()
            }
        
        self.metrics["agent_performance"][agent_name]["interactions"] += 1
    
    def handle_tool_call(self, data: Dict[str, Any]):
        """Handle tool usage callback"""
        self.metrics["tool_calls"] += 1
        tool_name = data.get("tool_name", "unknown")
        agent_name = data.get("agent_name", "unknown")
        
        print(f"🔧 Tool Usage: {agent_name} using {tool_name}")
        
        if tool_name not in self.metrics["tool_usage"]:
            self.metrics["tool_usage"][tool_name] = {"count": 0, "agents": set()}
        
        self.metrics["tool_usage"][tool_name]["count"] += 1
        self.metrics["tool_usage"][tool_name]["agents"].add(agent_name)
    
    def handle_error(self, data: Dict[str, Any]):
        """Handle error callback"""
        self.metrics["errors"] += 1
        agent_name = data.get("agent_name", "unknown")
        error_msg = data.get("error", "Unknown error")
        
        print(f"❌ Error: {agent_name} - {error_msg}")
    
    def handle_generation(self, data: Dict[str, Any]):
        """Handle content generation callback"""
        self.metrics["generation_events"] += 1
        agent_name = data.get("agent_name", "unknown")
        
        print(f"✍️  Generation: {agent_name} generating content")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        runtime = time.time() - self.metrics["start_time"]
        
        # Convert sets to lists for JSON serialization
        tool_usage_serializable = {}
        for tool, info in self.metrics["tool_usage"].items():
            tool_usage_serializable[tool] = {
                "count": info["count"],
                "agents": list(info["agents"])
            }
        
        return {
            "runtime_seconds": runtime,
            "total_interactions": self.metrics["interactions"],
            "total_tool_calls": self.metrics["tool_calls"],
            "total_errors": self.metrics["errors"],
            "generation_events": self.metrics["generation_events"],
            "interactions_per_minute": (self.metrics["interactions"] / runtime * 60) if runtime > 0 else 0,
            "agent_performance": self.metrics["agent_performance"],
            "tool_usage": tool_usage_serializable
        }

class RealTimeMonitoringCallback:
    """Real-time monitoring and alerting"""
    
    def __init__(self, alert_threshold_seconds: float = 30.0):
        self.alert_threshold = alert_threshold_seconds
        self.alerts = []
        self.operation_times = {}
    
    def handle_interaction(self, data: Dict[str, Any]):
        """Track interaction timing for alerts"""
        interaction_type = data.get("type", "unknown")
        agent_name = data.get("agent_name", "unknown")
        
        if interaction_type == "start":
            operation_id = f"{agent_name}_{time.time()}"
            self.operation_times[operation_id] = {
                "agent": agent_name,
                "start_time": time.time(),
                "type": "interaction"
            }
        elif interaction_type == "complete":
            # Find and close matching operation
            for op_id, op_info in list(self.operation_times.items()):
                if op_info["agent"] == agent_name:
                    duration = time.time() - op_info["start_time"]
                    if duration > self.alert_threshold:
                        alert = {
                            "type": "SLOW_OPERATION",
                            "agent": agent_name,
                            "duration": duration,
                            "threshold": self.alert_threshold,
                            "timestamp": datetime.now().isoformat()
                        }
                        self.alerts.append(alert)
                        print(f"⚠️  ALERT: Slow operation - {agent_name} took {duration:.2f}s")
                    
                    del self.operation_times[op_id]
                    break
    
    def handle_error(self, data: Dict[str, Any]):
        """Handle error events with alerting"""
        alert = {
            "type": "ERROR",
            "agent": data.get("agent_name", "unknown"),
            "error": data.get("error", "Unknown error"),
            "timestamp": datetime.now().isoformat()
        }
        self.alerts.append(alert)
        print(f"🚨 ERROR ALERT: {alert['agent']} - {alert['error']}")
    
    def get_active_operations(self) -> List[Dict[str, Any]]:
        """Get currently running operations"""
        current_time = time.time()
        active_ops = []
        
        for op_id, op_info in self.operation_times.items():
            runtime = current_time - op_info["start_time"]
            active_ops.append({
                "operation_id": op_id[:8],
                "agent": op_info["agent"],
                "runtime": runtime,
                "type": op_info["type"],
                "status": "RUNNING" if runtime < self.alert_threshold else "SLOW"
            })
        
        return active_ops
    
    def get_alerts_summary(self) -> Dict[str, Any]:
        """Get summary of all alerts"""
        if not self.alerts:
            return {"total_alerts": 0}
        
        alert_types = {}
        for alert in self.alerts:
            alert_type = alert["type"]
            alert_types[alert_type] = alert_types.get(alert_type, 0) + 1
        
        return {
            "total_alerts": len(self.alerts),
            "alert_types": alert_types,
            "recent_alerts": self.alerts[-3:] if len(self.alerts) >= 3 else self.alerts
        }

class BusinessMetricsCallback:
    """Collect business-relevant metrics"""
    
    def __init__(self):
        self.business_metrics = {
            "session_start": time.time(),
            "user_interactions": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "total_content_generated": 0,
            "tool_efficiency": {}
        }
    
    def handle_interaction(self, data: Dict[str, Any]):
        """Track business interactions"""
        self.business_metrics["user_interactions"] += 1
        
        interaction_type = data.get("type", "unknown")
        if interaction_type == "complete":
            self.business_metrics["successful_operations"] += 1
    
    def handle_error(self, data: Dict[str, Any]):
        """Track failed operations for business metrics"""
        self.business_metrics["failed_operations"] += 1
    
    def handle_generation(self, data: Dict[str, Any]):
        """Track content generation for business value"""
        content_length = len(str(data.get("content", "")))
        self.business_metrics["total_content_generated"] += content_length
    
    def handle_tool_call(self, data: Dict[str, Any]):
        """Track tool efficiency"""
        tool_name = data.get("tool_name", "unknown")
        
        if tool_name not in self.business_metrics["tool_efficiency"]:
            self.business_metrics["tool_efficiency"][tool_name] = {
                "calls": 0,
                "last_used": None
            }
        
        self.business_metrics["tool_efficiency"][tool_name]["calls"] += 1
        self.business_metrics["tool_efficiency"][tool_name]["last_used"] = datetime.now().isoformat()
    
    def get_business_report(self) -> Dict[str, Any]:
        """Generate business intelligence report"""
        session_duration = time.time() - self.business_metrics["session_start"]
        total_operations = self.business_metrics["successful_operations"] + self.business_metrics["failed_operations"]
        
        success_rate = (self.business_metrics["successful_operations"] / total_operations * 100) if total_operations > 0 else 0
        
        return {
            "session_duration_minutes": session_duration / 60,
            "user_interactions": self.business_metrics["user_interactions"],
            "success_rate_percentage": success_rate,
            "total_content_generated_chars": self.business_metrics["total_content_generated"],
            "operations_per_hour": (total_operations / session_duration * 3600) if session_duration > 0 else 0,
            "tool_efficiency": self.business_metrics["tool_efficiency"],
            "productivity_score": min(100, success_rate * (self.business_metrics["user_interactions"] / 10))
        }

# Initialize callback instances
perf_monitor = PerformanceMonitorCallback()
realtime_monitor = RealTimeMonitoringCallback(alert_threshold_seconds=15.0)
business_metrics = BusinessMetricsCallback()

# Register callbacks with PraisonAI Agents callback system
print("Registering callbacks with PraisonAI Agents...")

# Register performance monitoring callbacks
register_display_callback('interaction', perf_monitor.handle_interaction)
register_display_callback('tool_call', perf_monitor.handle_tool_call)
register_display_callback('error', perf_monitor.handle_error)
register_display_callback('generating', perf_monitor.handle_generation)

# Register real-time monitoring callbacks
register_display_callback('interaction', realtime_monitor.handle_interaction)
register_display_callback('error', realtime_monitor.handle_error)

# Register business metrics callbacks
register_display_callback('interaction', business_metrics.handle_interaction)
register_display_callback('error', business_metrics.handle_error)
register_display_callback('generating', business_metrics.handle_generation)
register_display_callback('tool_call', business_metrics.handle_tool_call)

print("✅ All callbacks registered successfully\n")

# Example 1: Single Agent with Monitoring
print("Example 1: Single Agent with Comprehensive Monitoring")
print("-" * 50)

research_agent = Agent(
    name="Research Agent",
    role="Information Researcher",
    goal="Conduct thorough research on topics",
    backstory="Expert researcher with access to various information sources",
    tools=[internet_search],
    verbose=True
)

# Execute a research task
print("Starting research task...")
research_result = research_agent.start("Research the latest developments in renewable energy technology")
print(f"Research completed: {research_result[:100]}...\n")

# Example 2: Multi-Agent System with Coordinated Monitoring
print("Example 2: Multi-Agent System Monitoring")
print("-" * 40)

# Create additional agents
analyst_agent = Agent(
    name="Data Analyst",
    role="Data Analysis Specialist",
    goal="Analyze data and generate insights",
    backstory="Expert in data analysis and pattern recognition",
    tools=[internet_search]
)

writer_agent = Agent(
    name="Technical Writer", 
    role="Content Creator",
    goal="Create comprehensive reports",
    backstory="Skilled technical writer who creates clear, detailed reports"
)

# Create coordinated tasks
analysis_task = Task(
    description="Analyze current trends in electric vehicle adoption",
    expected_output="Detailed analysis with data points and trends",
    agent=analyst_agent
)

report_task = Task(
    description="Create a comprehensive report on electric vehicle trends",
    expected_output="Well-structured report with insights and recommendations", 
    agent=writer_agent,
    context=[analysis_task]
)

# Execute multi-agent workflow
print("Starting multi-agent workflow...")
multi_agent_system = PraisonAIAgents(
    agents=[analyst_agent, writer_agent],
    tasks=[analysis_task, report_task],
    process="sequential"
)

workflow_result = multi_agent_system.start()
print(f"Multi-agent workflow completed: {workflow_result[:100]}...\n")

# Example 3: Real-Time Monitoring Dashboard
print("Example 3: Real-Time Monitoring Dashboard")
print("-" * 40)

# Check active operations
active_ops = realtime_monitor.get_active_operations()
print("Active Operations:")
if active_ops:
    for op in active_ops:
        print(f"  {op['operation_id']} | {op['agent']} | {op['runtime']:.1f}s | {op['status']}")
else:
    print("  No currently active operations")

# Show alerts
alerts_summary = realtime_monitor.get_alerts_summary()
print(f"\nAlerts Summary:")
print(f"  Total alerts: {alerts_summary['total_alerts']}")
if "alert_types" in alerts_summary:
    for alert_type, count in alerts_summary["alert_types"].items():
        print(f"  {alert_type}: {count}")

if "recent_alerts" in alerts_summary:
    print("  Recent alerts:")
    for alert in alerts_summary["recent_alerts"]:
        print(f"    - {alert['type']}: {alert.get('agent', 'N/A')}")

# Example 4: Performance Analytics
print("\nExample 4: Performance Analytics Dashboard")
print("-" * 40)

perf_report = perf_monitor.get_performance_report()
print(f"Session Runtime: {perf_report['runtime_seconds']:.1f} seconds")
print(f"Total Interactions: {perf_report['total_interactions']}")
print(f"Tool Calls Made: {perf_report['total_tool_calls']}")
print(f"Errors Encountered: {perf_report['total_errors']}")
print(f"Generation Events: {perf_report['generation_events']}")
print(f"Interactions/Minute: {perf_report['interactions_per_minute']:.1f}")

print("\nAgent Performance:")
for agent, stats in perf_report['agent_performance'].items():
    print(f"  {agent}: {stats['interactions']} interactions")

print("\nTool Usage:")
for tool, stats in perf_report['tool_usage'].items():
    print(f"  {tool}: {stats['count']} calls by {len(stats['agents'])} agents")

# Example 5: Business Intelligence Dashboard
print("\nExample 5: Business Intelligence Dashboard")
print("-" * 40)

business_report = business_metrics.get_business_report()
print(f"Session Duration: {business_report['session_duration_minutes']:.1f} minutes")
print(f"User Interactions: {business_report['user_interactions']}")
print(f"Success Rate: {business_report['success_rate_percentage']:.1f}%")
print(f"Content Generated: {business_report['total_content_generated_chars']:,} characters")
print(f"Operations/Hour: {business_report['operations_per_hour']:.1f}")
print(f"Productivity Score: {business_report['productivity_score']:.1f}/100")

print("\nTool Efficiency:")
for tool, efficiency in business_report['tool_efficiency'].items():
    print(f"  {tool}: {efficiency['calls']} calls")

print("\n=== Callback Systems Summary ===")
print("✅ Performance monitoring: Active and collecting metrics")
print("✅ Real-time alerts: Configured with thresholds")
print("✅ Business intelligence: Tracking productivity metrics")
print("✅ Multi-agent coordination: Monitoring all agents")
print("✅ Error tracking: Comprehensive error logging")
print(f"📊 Overall system health: {business_report['success_rate_percentage']:.1f}% success rate")

print("\nAdvanced callback systems example complete!")
print("Note: This example uses PraisonAI Agents' actual callback architecture.")