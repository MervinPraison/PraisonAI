#!/usr/bin/env python3
"""
Telemetry Integration Example

This example demonstrates how to integrate with the telemetry system
for automatic metrics tracking, PostHog integration, and custom telemetry events.
"""

import sys
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Any

# Add the praisonai-agents module to the Python path  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents.agent import Agent
from praisonaiagents.telemetry.metrics import TokenMetrics, PerformanceMetrics, MetricsCollector
from praisonaiagents.telemetry import get_telemetry

# Configure logging to see telemetry debug messages
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class TelemetryMonitor:
    """Enhanced monitoring with telemetry integration."""
    
    def __init__(self, enable_posthog: bool = False):
        self.telemetry = get_telemetry()
        self.enable_posthog = enable_posthog
        self.custom_events: List[Dict[str, Any]] = []
        
        print(f"📡 Telemetry Monitor Initialized")
        print(f"   Telemetry Enabled: {self.telemetry.enabled}")
        print(f"   Session ID: {self.telemetry.session_id}")
        print(f"   PostHog Integration: {enable_posthog}")
        
        # Configure PostHog if requested (requires POSTHOG_API_KEY env var)
        if enable_posthog:
            self._setup_posthog()
    
    def _setup_posthog(self):
        """Setup PostHog integration for analytics."""
        posthog_key = os.getenv('POSTHOG_API_KEY')
        if posthog_key:
            print(f"🔧 PostHog configured with API key")
        else:
            print(f"⚠️  PostHog API key not found in environment")
            print(f"   Set POSTHOG_API_KEY to enable PostHog integration")
    
    def track_custom_event(self, event_name: str, properties: Dict[str, Any]):
        """Track custom telemetry events."""
        
        # Add timestamp and session info
        enriched_properties = {
            **properties,
            'timestamp': datetime.now().isoformat(),
            'session_id': self.telemetry.session_id
        }
        
        # Store for local tracking
        event_record = {
            'event': event_name,
            'properties': enriched_properties,
            'tracked_at': time.time()
        }
        self.custom_events.append(event_record)
        
        print(f"📊 Custom Event: {event_name}")
        for key, value in properties.items():
            print(f"   {key}: {value}")
    
    def demonstrate_manual_telemetry(self):
        """Demonstrate manual telemetry tracking."""
        
        print(f"\n🔍 Manual Telemetry Tracking")
        print("-" * 40)
        
        # Track feature usage
        self.telemetry.track_feature_usage("manual_monitoring", {"demo": True})
        
        # Create and track token metrics
        token_metrics = TokenMetrics(
            input_tokens=120,
            output_tokens=80,
            total_tokens=200,
            cached_tokens=30,
            reasoning_tokens=15,
            audio_tokens=5
        )
        
        print(f"📤 Tracking token metrics...")
        self.telemetry.track_tokens(token_metrics)
        
        # Create and track performance metrics
        perf_metrics = PerformanceMetrics()
        perf_metrics.start_timing()
        time.sleep(0.3)  # Simulate work
        perf_metrics.mark_first_token()
        time.sleep(0.2)  # Simulate more work
        perf_metrics.end_timing(80)  # 80 tokens generated
        
        print(f"📈 Tracking performance metrics...")
        self.telemetry.track_performance(perf_metrics)
        
        # Track custom application events
        self.track_custom_event("workflow_started", {
            "workflow_type": "data_analysis",
            "expected_duration": 300,
            "complexity": "high"
        })
        
        return token_metrics, perf_metrics
    
    def demonstrate_agent_telemetry(self):
        """Demonstrate automatic agent telemetry integration."""
        
        print(f"\n🤖 Agent Telemetry Integration")
        print("-" * 40)
        
        # Create agent with metrics tracking (automatic telemetry)
        agent = Agent(
            name="TelemetryAgent",
            role="Data Processor", 
            goal="Process data with telemetry tracking",
            backstory="Specialized in monitored data processing workflows",
            track_metrics=True
        )
        
        print(f"✅ Agent created with telemetry integration")
        
        # Simulate agent tasks with telemetry
        tasks = [
            ("Process customer data", 150),
            ("Generate insights report", 200),
            ("Create visualization", 100)
        ]
        
        for i, (task, expected_tokens) in enumerate(tasks, 1):
            print(f"\n🎯 Task {i}: {task}")
            
            # Track task start
            self.track_custom_event("task_started", {
                "task_name": task,
                "agent": agent.name,
                "expected_tokens": expected_tokens
            })
            
            # Simulate task execution with metrics
            start_time = time.time()
            
            # Create simulated metrics (in real usage, these come from agent.chat())
            token_metrics = TokenMetrics(
                input_tokens=int(expected_tokens * 0.6),
                output_tokens=int(expected_tokens * 0.4),
                total_tokens=expected_tokens,
                cached_tokens=int(expected_tokens * 0.1)
            )
            
            perf_metrics = PerformanceMetrics()
            perf_metrics.start_timing()
            time.sleep(0.2)  # Simulate processing
            perf_metrics.mark_first_token()
            time.sleep(0.3)  # Simulate generation
            perf_metrics.end_timing(token_metrics.output_tokens)
            
            # Manually add to agent's metrics collector (normally automatic)
            if agent.metrics_collector:
                agent.metrics_collector.add_agent_metrics(
                    agent_name=agent.name,
                    token_metrics=token_metrics,
                    performance_metrics=perf_metrics,
                    model_name="gpt-4o"
                )
            
            # Track via telemetry (normally automatic in agent.chat())
            self.telemetry.track_tokens(token_metrics)
            self.telemetry.track_performance(perf_metrics)
            
            # Track task completion
            execution_time = time.time() - start_time
            self.track_custom_event("task_completed", {
                "task_name": task,
                "agent": agent.name,
                "execution_time": execution_time,
                "tokens_used": token_metrics.total_tokens,
                "tokens_per_second": perf_metrics.tokens_per_second
            })
            
            print(f"   ✅ Completed in {execution_time:.2f}s")
            print(f"   📊 {token_metrics.total_tokens} tokens, {perf_metrics.tokens_per_second:.1f} TPS")
        
        return agent
    
    def analyze_telemetry_data(self):
        """Analyze collected telemetry data."""
        
        print(f"\n📊 Telemetry Data Analysis")
        print("-" * 40)
        
        # Get telemetry metrics
        telemetry_metrics = self.telemetry.get_metrics()
        
        print(f"Telemetry Status:")
        print(f"  Enabled: {telemetry_metrics['enabled']}")
        print(f"  Session ID: {telemetry_metrics.get('session_id', 'N/A')}")
        
        if telemetry_metrics['enabled']:
            metrics_data = telemetry_metrics.get('metrics', {})
            print(f"  Collected Metrics: {len(metrics_data)} entries")
            
            # Show environment info
            env_info = telemetry_metrics.get('environment', {})
            print(f"\nEnvironment:")
            for key, value in env_info.items():
                print(f"  {key}: {value}")
        
        # Analyze custom events
        print(f"\nCustom Events Analysis:")
        print(f"  Total Events: {len(self.custom_events)}")
        
        # Group events by type
        event_types = {}
        for event in self.custom_events:
            event_name = event['event']
            event_types[event_name] = event_types.get(event_name, 0) + 1
        
        for event_type, count in event_types.items():
            print(f"  {event_type}: {count} events")
        
        # Show recent events
        if self.custom_events:
            print(f"\nRecent Events:")
            for event in self.custom_events[-3:]:  # Last 3 events
                print(f"  • {event['event']}: {list(event['properties'].keys())}")
        
        return telemetry_metrics
    
    def export_telemetry_report(self, output_file: str = "/tmp/telemetry_report.json"):
        """Export comprehensive telemetry report."""
        
        import json
        
        # Collect all telemetry data
        report_data = {
            'session_info': {
                'session_id': self.telemetry.session_id,
                'generated_at': datetime.now().isoformat(),
                'telemetry_enabled': self.telemetry.enabled
            },
            'telemetry_metrics': self.telemetry.get_metrics(),
            'custom_events': self.custom_events,
            'event_summary': {
                'total_events': len(self.custom_events),
                'event_types': {}
            }
        }
        
        # Summarize event types
        for event in self.custom_events:
            event_name = event['event']
            if event_name not in report_data['event_summary']['event_types']:
                report_data['event_summary']['event_types'][event_name] = {
                    'count': 0,
                    'first_seen': event['tracked_at'],
                    'last_seen': event['tracked_at']
                }
            
            summary = report_data['event_summary']['event_types'][event_name]
            summary['count'] += 1
            summary['last_seen'] = max(summary['last_seen'], event['tracked_at'])
        
        # Export to file
        try:
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            print(f"📄 Telemetry report exported to: {output_file}")
            return output_file
        except Exception as e:
            print(f"❌ Export failed: {e}")
            return None

def demonstrate_environment_setup():
    """Demonstrate telemetry environment configuration."""
    
    print(f"🔧 Telemetry Environment Configuration")
    print("-" * 50)
    
    # Show current environment variables relevant to telemetry
    relevant_env_vars = [
        'PRAISONAI_TELEMETRY_DISABLED',
        'POSTHOG_API_KEY', 
        'LOGLEVEL'
    ]
    
    print(f"Environment Variables:")
    for var in relevant_env_vars:
        value = os.getenv(var, 'Not set')
        print(f"  {var}: {value}")
    
    print(f"\n💡 Configuration Options:")
    print(f"• Set PRAISONAI_TELEMETRY_DISABLED=true to disable telemetry")
    print(f"• Set POSTHOG_API_KEY=<your_key> for PostHog integration")
    print(f"• Set LOGLEVEL=DEBUG to see detailed telemetry logs")
    print(f"• Use track_metrics=True on agents for automatic tracking")

def main():
    """Main demonstration function."""
    
    print(f"📡 Telemetry Integration Example")
    print("=" * 60)
    
    # Setup environment demonstration
    demonstrate_environment_setup()
    
    # Create telemetry monitor
    monitor = TelemetryMonitor(enable_posthog=False)  # Set to True if you have PostHog key
    
    # Demonstrate manual telemetry
    token_metrics, perf_metrics = monitor.demonstrate_manual_telemetry()
    
    # Demonstrate agent integration
    agent = monitor.demonstrate_agent_telemetry()
    
    # Analyze collected data
    telemetry_data = monitor.analyze_telemetry_data()
    
    # Show agent session metrics
    if agent.metrics_collector:
        print(f"\n🤖 Agent Session Metrics:")
        session_metrics = agent.metrics_collector.get_session_metrics()
        print(f"  Total Tokens: {session_metrics['total_tokens']['total_tokens']}")
        print(f"  Duration: {session_metrics['duration_seconds']:.1f}s")
        
        if session_metrics['performance']:
            for agent_name, perf in session_metrics['performance'].items():
                print(f"  {agent_name} Performance:")
                print(f"    Avg TTFT: {perf['average_ttft']:.3f}s")
                print(f"    Avg TPS: {perf['average_tokens_per_second']:.1f}")
                print(f"    Requests: {perf['request_count']}")
    
    # Export comprehensive report
    print(f"\n📄 Exporting Telemetry Report...")
    report_file = monitor.export_telemetry_report()
    
    # Flush telemetry data
    print(f"\n🚀 Flushing telemetry data...")
    monitor.telemetry.flush()
    
    print(f"\n✅ Telemetry Integration Example Complete!")
    print(f"\n💡 Key Telemetry Features:")
    print(f"• Automatic metrics tracking with track_metrics=True")
    print(f"• Manual telemetry via track_tokens() and track_performance()")
    print(f"• Custom event tracking for application-specific metrics")
    print(f"• PostHog integration for analytics (with API key)")
    print(f"• Environment-based configuration")
    print(f"• Debug logging for development and troubleshooting")
    print(f"• Session-level data aggregation and export")

if __name__ == "__main__":
    main()