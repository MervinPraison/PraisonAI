#!/usr/bin/env python3
"""
Comprehensive Session Monitoring Example

This example demonstrates advanced monitoring capabilities including:
- Multi-agent session monitoring
- Real-time performance tracking
- Detailed analytics and reporting
- Export capabilities
- Custom monitoring hooks
"""

import sys
import os
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Add the praisonai-agents module to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents.agent import Agent
from praisonaiagents.telemetry.metrics import TokenMetrics, PerformanceMetrics, MetricsCollector

class AdvancedMonitoringSession:
    """Advanced session monitoring with real-time analytics."""
    
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.session_start = datetime.now()
        self.metrics_collector = MetricsCollector()
        self.agents: Dict[str, Agent] = {}
        self.task_history: List[Dict[str, Any]] = []
        self.performance_thresholds = {
            'max_ttft': 2.0,  # seconds
            'min_tokens_per_sec': 10.0,
            'max_total_time': 30.0
        }
        self.alerts: List[Dict[str, Any]] = []
        
        print(f"🚀 Advanced Monitoring Session: {session_name}")
        print(f"📅 Started at: {self.session_start.isoformat()}")
        print("-" * 60)
    
    def create_agent(self, name: str, role: str, goal: str, backstory: str) -> Agent:
        """Create a monitored agent."""
        agent = Agent(
            name=name,
            role=role, 
            goal=goal,
            backstory=backstory,
            track_metrics=True,
            metrics_collector=self.metrics_collector
        )
        
        self.agents[name] = agent
        print(f"👤 Agent created: {name} ({role})")
        return agent
    
    def execute_monitored_task(self, agent_name: str, task: str, 
                              expected_tokens: int = 100) -> Dict[str, Any]:
        """Execute a task with comprehensive monitoring."""
        
        if agent_name not in self.agents:
            raise ValueError(f"Agent {agent_name} not found")
        
        agent = self.agents[agent_name]
        task_start = time.time()
        
        print(f"\n🎯 Executing Task: {task[:50]}...")
        print(f"👤 Agent: {agent_name}")
        
        # Create performance metrics for this task
        perf_metrics = PerformanceMetrics()
        perf_metrics.start_timing()
        
        # Simulate task execution (in real usage, call agent.chat(task))
        execution_time = 0.5 + (expected_tokens / 100) * 0.3  # Simulate based on expected tokens
        time.sleep(execution_time)
        
        # Simulate first token timing
        time.sleep(0.1)
        perf_metrics.mark_first_token()
        
        # Complete timing
        perf_metrics.end_timing(expected_tokens)
        
        # Create simulated token metrics
        token_metrics = TokenMetrics(
            input_tokens=int(expected_tokens * 0.7),
            output_tokens=int(expected_tokens * 0.3),
            total_tokens=expected_tokens,
            cached_tokens=int(expected_tokens * 0.1),
            reasoning_tokens=int(expected_tokens * 0.05)
        )
        
        # Add to metrics collector
        self.metrics_collector.add_agent_metrics(
            agent_name=agent_name,
            token_metrics=token_metrics,
            performance_metrics=perf_metrics,
            model_name="gpt-4o"
        )
        
        # Create task record
        task_record = {
            'timestamp': datetime.now().isoformat(),
            'agent': agent_name,
            'task': task,
            'execution_time': time.time() - task_start,
            'tokens': {
                'input': token_metrics.input_tokens,
                'output': token_metrics.output_tokens,
                'total': token_metrics.total_tokens,
                'cached': token_metrics.cached_tokens,
                'reasoning': token_metrics.reasoning_tokens
            },
            'performance': {
                'ttft': perf_metrics.time_to_first_token,
                'total_time': perf_metrics.total_time,
                'tokens_per_second': perf_metrics.tokens_per_second
            }
        }
        
        self.task_history.append(task_record)
        
        # Check performance thresholds
        self._check_performance_alerts(agent_name, perf_metrics, token_metrics)
        
        # Display real-time metrics
        self._display_task_metrics(task_record)
        
        return task_record
    
    def _check_performance_alerts(self, agent_name: str, perf: PerformanceMetrics, 
                                tokens: TokenMetrics):
        """Check for performance threshold violations."""
        alerts = []
        
        if perf.time_to_first_token > self.performance_thresholds['max_ttft']:
            alerts.append(f"High TTFT: {perf.time_to_first_token:.3f}s")
        
        if perf.tokens_per_second < self.performance_thresholds['min_tokens_per_sec']:
            alerts.append(f"Low TPS: {perf.tokens_per_second:.1f}")
        
        if perf.total_time > self.performance_thresholds['max_total_time']:
            alerts.append(f"Long execution: {perf.total_time:.3f}s")
        
        if alerts:
            alert_record = {
                'timestamp': datetime.now().isoformat(),
                'agent': agent_name,
                'alerts': alerts,
                'metrics': {
                    'ttft': perf.time_to_first_token,
                    'tps': perf.tokens_per_second,
                    'total_time': perf.total_time
                }
            }
            self.alerts.append(alert_record)
            
            print(f"⚠️  Performance Alert for {agent_name}:")
            for alert in alerts:
                print(f"   • {alert}")
    
    def _display_task_metrics(self, task_record: Dict[str, Any]):
        """Display real-time task metrics."""
        tokens = task_record['tokens']
        perf = task_record['performance']
        
        print(f"📊 Task Metrics:")
        print(f"   Tokens: {tokens['total']} (↑{tokens['input']} ↓{tokens['output']})")
        print(f"   Performance: TTFT={perf['ttft']:.3f}s, TPS={perf['tokens_per_second']:.1f}")
        print(f"   Efficiency: {tokens['cached']} cached, {tokens['reasoning']} reasoning")
    
    def get_session_analytics(self) -> Dict[str, Any]:
        """Generate comprehensive session analytics."""
        
        session_metrics = self.metrics_collector.get_session_metrics()
        current_time = datetime.now()
        session_duration = current_time - self.session_start
        
        # Calculate additional analytics
        total_tasks = len(self.task_history)
        tasks_per_minute = total_tasks / (session_duration.total_seconds() / 60) if session_duration.total_seconds() > 0 else 0
        
        # Agent performance rankings
        agent_rankings = []
        if session_metrics['performance']:
            for agent_name, perf in session_metrics['performance'].items():
                ranking_score = (
                    (1 / max(perf['average_ttft'], 0.001)) * 0.3 +
                    perf['average_tokens_per_second'] * 0.4 +
                    (1 / max(perf['average_total_time'], 0.001)) * 0.3
                )
                agent_rankings.append({
                    'agent': agent_name,
                    'score': ranking_score,
                    'requests': perf['request_count'],
                    'avg_tps': perf['average_tokens_per_second']
                })
        
        agent_rankings.sort(key=lambda x: x['score'], reverse=True)
        
        # Token usage analysis
        token_analysis = {
            'efficiency_ratio': 0,
            'cache_hit_ratio': 0,
            'reasoning_ratio': 0
        }
        
        if session_metrics['total_tokens']['total_tokens'] > 0:
            total = session_metrics['total_tokens']['total_tokens']
            token_analysis['efficiency_ratio'] = session_metrics['total_tokens']['output_tokens'] / session_metrics['total_tokens']['input_tokens'] if session_metrics['total_tokens']['input_tokens'] > 0 else 0
            token_analysis['cache_hit_ratio'] = session_metrics['total_tokens']['cached_tokens'] / total
            token_analysis['reasoning_ratio'] = session_metrics['total_tokens']['reasoning_tokens'] / total
        
        return {
            'session_info': {
                'name': self.session_name,
                'start_time': self.session_start.isoformat(),
                'duration_seconds': session_duration.total_seconds(),
                'duration_formatted': str(session_duration).split('.')[0]
            },
            'task_summary': {
                'total_tasks': total_tasks,
                'tasks_per_minute': tasks_per_minute,
                'unique_agents': len(self.agents),
                'alerts_count': len(self.alerts)
            },
            'token_analysis': token_analysis,
            'agent_rankings': agent_rankings,
            'alerts': self.alerts,
            'raw_metrics': session_metrics
        }
    
    def export_comprehensive_report(self, output_dir: str = "/tmp"):
        """Export comprehensive monitoring report."""
        
        analytics = self.get_session_analytics()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export detailed JSON report
        json_file = os.path.join(output_dir, f"monitoring_report_{timestamp}.json")
        with open(json_file, 'w') as f:
            json.dump(analytics, f, indent=2, default=str)
        
        # Export human-readable summary
        summary_file = os.path.join(output_dir, f"monitoring_summary_{timestamp}.txt")
        with open(summary_file, 'w') as f:
            f.write(f"Session Monitoring Report: {self.session_name}\n")
            f.write("=" * 60 + "\n\n")
            
            # Session info
            info = analytics['session_info']
            f.write(f"Session Duration: {info['duration_formatted']}\n")
            f.write(f"Started: {info['start_time']}\n\n")
            
            # Task summary
            summary = analytics['task_summary']
            f.write(f"Tasks Executed: {summary['total_tasks']}\n")
            f.write(f"Tasks per Minute: {summary['tasks_per_minute']:.1f}\n")
            f.write(f"Agents Used: {summary['unique_agents']}\n")
            f.write(f"Performance Alerts: {summary['alerts_count']}\n\n")
            
            # Token analysis
            tokens = analytics['token_analysis']
            f.write("Token Analysis:\n")
            f.write(f"  Efficiency Ratio: {tokens['efficiency_ratio']:.2f}\n")
            f.write(f"  Cache Hit Ratio: {tokens['cache_hit_ratio']:.2f}\n")
            f.write(f"  Reasoning Ratio: {tokens['reasoning_ratio']:.2f}\n\n")
            
            # Agent rankings
            f.write("Agent Performance Rankings:\n")
            for i, agent in enumerate(analytics['agent_rankings'], 1):
                f.write(f"  {i}. {agent['agent']} (Score: {agent['score']:.1f}, TPS: {agent['avg_tps']:.1f})\n")
        
        return json_file, summary_file
    
    def display_live_dashboard(self):
        """Display a live monitoring dashboard."""
        
        analytics = self.get_session_analytics()
        
        print("\n" + "=" * 80)
        print(f"📈 LIVE MONITORING DASHBOARD - {self.session_name}")
        print("=" * 80)
        
        # Session overview
        info = analytics['session_info']
        summary = analytics['task_summary']
        
        print(f"⏰ Session Duration: {info['duration_formatted']}")
        print(f"📋 Tasks: {summary['total_tasks']} ({summary['tasks_per_minute']:.1f}/min)")
        print(f"👥 Agents: {summary['unique_agents']}")
        print(f"⚠️  Alerts: {summary['alerts_count']}")
        
        # Token metrics
        raw = analytics['raw_metrics']
        print(f"\n💰 Token Usage:")
        print(f"   Total: {raw['total_tokens']['total_tokens']:,}")
        print(f"   Input/Output: {raw['total_tokens']['input_tokens']:,}/{raw['total_tokens']['output_tokens']:,}")
        print(f"   Cached: {raw['total_tokens']['cached_tokens']:,}")
        print(f"   Reasoning: {raw['total_tokens']['reasoning_tokens']:,}")
        
        # Performance by agent
        if raw['performance']:
            print(f"\n🚀 Performance by Agent:")
            for agent_name, perf in raw['performance'].items():
                print(f"   {agent_name}:")
                print(f"     TTFT: {perf['average_ttft']:.3f}s")
                print(f"     Speed: {perf['average_tokens_per_second']:.1f} tokens/sec")
                print(f"     Requests: {perf['request_count']}")
        
        # Recent alerts
        if analytics['alerts']:
            print(f"\n⚠️  Recent Alerts:")
            for alert in analytics['alerts'][-3:]:  # Show last 3
                print(f"   {alert['agent']}: {', '.join(alert['alerts'])}")
        
        print("=" * 80)

def main():
    """Demonstrate comprehensive session monitoring."""
    
    # Create monitoring session
    session = AdvancedMonitoringSession("Multi-Agent Analytics Session")
    
    # Create multiple agents with different roles
    data_analyst = session.create_agent(
        "DataAnalyst",
        "Senior Data Analyst", 
        "Analyze data and provide insights",
        "Expert in statistical analysis and data visualization"
    )
    
    content_writer = session.create_agent(
        "ContentWriter",
        "Content Strategist",
        "Create engaging content",
        "Experienced writer specializing in technical content"
    )
    
    researcher = session.create_agent(
        "Researcher", 
        "Research Specialist",
        "Conduct thorough research",
        "PhD-level researcher with expertise in multiple domains"
    )
    
    # Define complex workflow with varying token requirements
    workflow_tasks = [
        ("DataAnalyst", "Analyze Q4 sales performance with statistical significance", 150),
        ("ContentWriter", "Write an executive summary of the sales analysis", 200),
        ("Researcher", "Research market trends affecting our sales performance", 180),
        ("DataAnalyst", "Create data visualizations for the executive report", 120),
        ("ContentWriter", "Draft recommendations based on analysis and research", 160),
        ("Researcher", "Validate recommendations against industry best practices", 140),
        ("DataAnalyst", "Perform final statistical validation of recommendations", 100),
    ]
    
    print(f"\n🎯 Executing {len(workflow_tasks)} tasks in monitored workflow...")
    
    # Execute workflow with monitoring
    for i, (agent_name, task, expected_tokens) in enumerate(workflow_tasks, 1):
        print(f"\n--- Task {i}/{len(workflow_tasks)} ---")
        
        try:
            session.execute_monitored_task(agent_name, task, expected_tokens)
            
            # Show live dashboard every few tasks
            if i % 3 == 0:
                session.display_live_dashboard()
                time.sleep(1)  # Brief pause for readability
                
        except Exception as e:
            print(f"❌ Task failed: {e}")
    
    # Final dashboard and analytics
    print(f"\n🏁 Workflow Complete!")
    session.display_live_dashboard()
    
    # Export comprehensive report
    print(f"\n📄 Generating comprehensive report...")
    try:
        json_file, summary_file = session.export_comprehensive_report()
        print(f"✅ Reports exported:")
        print(f"   📊 Detailed JSON: {json_file}")
        print(f"   📝 Summary: {summary_file}")
    except Exception as e:
        print(f"⚠️  Export failed: {e}")
    
    # Final analytics summary
    analytics = session.get_session_analytics()
    
    print(f"\n🎊 Session Complete: {session.session_name}")
    print(f"⌚ Total Duration: {analytics['session_info']['duration_formatted']}")
    print(f"📈 Productivity: {analytics['task_summary']['tasks_per_minute']:.1f} tasks/min")
    print(f"🏆 Top Performer: {analytics['agent_rankings'][0]['agent'] if analytics['agent_rankings'] else 'N/A'}")
    print(f"💰 Total Tokens: {analytics['raw_metrics']['total_tokens']['total_tokens']:,}")
    
    print("\n💡 Advanced Monitoring Features Demonstrated:")
    print("• Multi-agent session tracking")
    print("• Real-time performance monitoring") 
    print("• Automated performance alerts")
    print("• Comprehensive analytics and rankings")
    print("• Export capabilities (JSON + summary)")
    print("• Live monitoring dashboard")

if __name__ == "__main__":
    main()