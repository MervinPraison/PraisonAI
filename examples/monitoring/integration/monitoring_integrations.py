#!/usr/bin/env python3
"""
Monitoring Integration Examples

This example demonstrates how to integrate PraisonAI monitoring with:
- Custom dashboards
- External monitoring systems
- Webhooks and alerts
- Database logging
- API endpoints
"""

import sys
import os
import time
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, asdict
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request

# Add the praisonai-agents module to the Python path  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src', 'praisonai-agents'))

from praisonaiagents.agent import Agent
from praisonaiagents.telemetry.metrics import TokenMetrics, PerformanceMetrics, MetricsCollector

@dataclass
class AlertConfig:
    """Configuration for performance alerts."""
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    webhook_url: Optional[str] = None
    email_recipient: Optional[str] = None
    cooldown_seconds: int = 300  # 5 minutes

class DatabaseLogger:
    """Log monitoring data to SQLite database."""
    
    def __init__(self, db_path: str = "/tmp/monitoring.db"):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_seconds REAL,
                total_tokens INTEGER,
                total_requests INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                agent_name TEXT,
                task_name TEXT,
                timestamp TIMESTAMP,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                cached_tokens INTEGER,
                reasoning_tokens INTEGER,
                ttft REAL,
                total_time REAL,
                tokens_per_second REAL,
                model_name TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                alert_name TEXT,
                timestamp TIMESTAMP,
                message TEXT,
                severity TEXT,
                resolved BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"🗄️  Database initialized: {self.db_path}")
    
    def log_session_start(self, session_id: str):
        """Log session start."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT OR REPLACE INTO sessions (id, start_time) VALUES (?, ?)",
            (session_id, datetime.now())
        )
        
        conn.commit()
        conn.close()
    
    def log_agent_metrics(self, session_id: str, agent_name: str, task_name: str,
                         token_metrics: TokenMetrics, perf_metrics: PerformanceMetrics,
                         model_name: str = "unknown"):
        """Log agent execution metrics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO agent_metrics (
                session_id, agent_name, task_name, timestamp,
                input_tokens, output_tokens, total_tokens, cached_tokens, reasoning_tokens,
                ttft, total_time, tokens_per_second, model_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id, agent_name, task_name, datetime.now(),
            token_metrics.input_tokens, token_metrics.output_tokens, token_metrics.total_tokens,
            token_metrics.cached_tokens, token_metrics.reasoning_tokens,
            perf_metrics.time_to_first_token, perf_metrics.total_time, 
            perf_metrics.tokens_per_second, model_name
        ))
        
        conn.commit()
        conn.close()
    
    def log_alert(self, session_id: str, alert_name: str, message: str, severity: str = "warning"):
        """Log performance alert."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO alerts (session_id, alert_name, timestamp, message, severity) VALUES (?, ?, ?, ?, ?)",
            (session_id, alert_name, datetime.now(), message, severity)
        )
        
        conn.commit()
        conn.close()
    
    def update_session_end(self, session_id: str, total_tokens: int, total_requests: int):
        """Update session end metrics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sessions 
            SET end_time = ?, total_tokens = ?, total_requests = ?,
                duration_seconds = (
                    SELECT (julianday(?) - julianday(start_time)) * 86400 
                    FROM sessions 
                    WHERE id = ?
                )
            WHERE id = ?
        ''', (datetime.now(), total_tokens, total_requests, datetime.now(), session_id, session_id))
        
        conn.commit()
        conn.close()
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get comprehensive session statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get session info
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        session_row = cursor.fetchone()
        
        # Get agent metrics
        cursor.execute("""
            SELECT agent_name, COUNT(*) as requests, 
                   AVG(ttft) as avg_ttft, AVG(total_time) as avg_total_time,
                   AVG(tokens_per_second) as avg_tps, SUM(total_tokens) as total_tokens
            FROM agent_metrics 
            WHERE session_id = ? 
            GROUP BY agent_name
        """, (session_id,))
        agent_stats = cursor.fetchall()
        
        # Get alerts
        cursor.execute("SELECT * FROM alerts WHERE session_id = ?", (session_id,))
        alerts = cursor.fetchall()
        
        conn.close()
        
        return {
            'session': session_row,
            'agent_stats': agent_stats,
            'alerts': alerts
        }

class WebhookNotifier:
    """Send monitoring data via webhooks."""
    
    def __init__(self):
        self.webhook_urls: List[str] = []
        self.last_sent: Dict[str, float] = {}
    
    def add_webhook(self, url: str):
        """Add webhook URL."""
        self.webhook_urls.append(url)
        print(f"🔗 Webhook added: {url}")
    
    def send_alert(self, alert_name: str, data: Dict[str, Any], cooldown: int = 300):
        """Send alert via webhook with cooldown."""
        
        # Check cooldown
        now = time.time()
        if alert_name in self.last_sent:
            if now - self.last_sent[alert_name] < cooldown:
                print(f"⏰ Alert {alert_name} in cooldown, skipping")
                return
        
        payload = {
            'alert_name': alert_name,
            'timestamp': datetime.now().isoformat(),
            'data': data,
            'severity': data.get('severity', 'warning')
        }
        
        for webhook_url in self.webhook_urls:
            try:
                # Simulate webhook call (in real usage, use requests library)
                print(f"📤 Sending webhook to {webhook_url}")
                print(f"   Alert: {alert_name}")
                print(f"   Data: {json.dumps(data, indent=2)}")
                
                # In real implementation:
                # import requests
                # response = requests.post(webhook_url, json=payload, timeout=10)
                # response.raise_for_status()
                
                self.last_sent[alert_name] = now
                print(f"✅ Webhook sent successfully")
                
            except Exception as e:
                print(f"❌ Webhook failed: {e}")

class MonitoringDashboardHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for monitoring dashboard."""
    
    monitoring_data = {}
    
    def do_GET(self):
        """Handle GET requests for dashboard."""
        if self.path == "/":
            self.send_dashboard()
        elif self.path == "/api/metrics":
            self.send_metrics_api()
        else:
            self.send_response(404)
            self.end_headers()
    
    def send_dashboard(self):
        """Send HTML dashboard."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>PraisonAI Monitoring Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .metric-box { border: 1px solid #ccc; padding: 15px; margin: 10px; border-radius: 5px; }
                .alert { background-color: #ffebee; border-color: #f44336; }
                .success { background-color: #e8f5e8; border-color: #4caf50; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
            </style>
            <script>
                function refreshData() {
                    fetch('/api/metrics')
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('metrics-data').innerHTML = 
                                '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                        });
                }
                setInterval(refreshData, 5000); // Refresh every 5 seconds
            </script>
        </head>
        <body>
            <h1>🔍 PraisonAI Monitoring Dashboard</h1>
            <div class="metric-box success">
                <h2>Real-time Metrics</h2>
                <div id="metrics-data">Loading...</div>
            </div>
            <script>refreshData();</script>
        </body>
        </html>
        """
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def send_metrics_api(self):
        """Send metrics as JSON API."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response_data = {
            'timestamp': datetime.now().isoformat(),
            'monitoring_data': self.monitoring_data
        }
        
        self.wfile.write(json.dumps(response_data, indent=2, default=str).encode())
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

class IntegratedMonitoringSystem:
    """Comprehensive monitoring system with multiple integrations."""
    
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.session_id = f"session_{int(time.time())}_{id(self)}"
        self.metrics_collector = MetricsCollector()
        
        # Initialize integrations
        self.db_logger = DatabaseLogger()
        self.webhook_notifier = WebhookNotifier()
        self.alerts: List[AlertConfig] = []
        
        # Start session
        self.db_logger.log_session_start(self.session_id)
        
        # Configure default alerts
        self._setup_default_alerts()
        
        print(f"🚀 Integrated Monitoring System: {session_name}")
        print(f"🆔 Session ID: {self.session_id}")
    
    def _setup_default_alerts(self):
        """Setup default performance alerts."""
        
        # High TTFT Alert
        self.add_alert(AlertConfig(
            name="high_ttft",
            condition=lambda data: data.get('ttft', 0) > 2.0,
            cooldown_seconds=300
        ))
        
        # Low TPS Alert  
        self.add_alert(AlertConfig(
            name="low_tps",
            condition=lambda data: data.get('tokens_per_second', 0) < 10.0,
            cooldown_seconds=300
        ))
        
        # High Token Usage Alert
        self.add_alert(AlertConfig(
            name="high_token_usage",
            condition=lambda data: data.get('total_tokens', 0) > 500,
            cooldown_seconds=600
        ))
    
    def add_alert(self, alert_config: AlertConfig):
        """Add performance alert configuration."""
        self.alerts.append(alert_config)
        print(f"⚠️  Alert configured: {alert_config.name}")
    
    def add_webhook(self, url: str):
        """Add webhook for notifications."""
        self.webhook_notifier.add_webhook(url)
    
    def execute_monitored_task(self, agent: Agent, task: str, expected_tokens: int = 100):
        """Execute task with comprehensive monitoring."""
        
        print(f"\n🎯 Task: {task[:50]}...")
        
        # Create performance metrics
        perf_metrics = PerformanceMetrics()
        perf_metrics.start_timing()
        
        # Simulate execution
        time.sleep(0.2)
        perf_metrics.mark_first_token()
        time.sleep(0.3)
        
        # Create token metrics (normally from agent response)
        token_metrics = TokenMetrics(
            input_tokens=int(expected_tokens * 0.7),
            output_tokens=int(expected_tokens * 0.3),
            total_tokens=expected_tokens,
            cached_tokens=int(expected_tokens * 0.1),
            reasoning_tokens=int(expected_tokens * 0.05)
        )
        
        perf_metrics.end_timing(token_metrics.output_tokens)
        
        # Add to metrics collector
        self.metrics_collector.add_agent_metrics(
            agent_name=agent.name,
            token_metrics=token_metrics,
            performance_metrics=perf_metrics,
            model_name="gpt-4o"
        )
        
        # Log to database
        self.db_logger.log_agent_metrics(
            self.session_id, agent.name, task, token_metrics, perf_metrics, "gpt-4o"
        )
        
        # Check alerts
        alert_data = {
            'agent': agent.name,
            'task': task,
            'ttft': perf_metrics.time_to_first_token,
            'total_time': perf_metrics.total_time,  
            'tokens_per_second': perf_metrics.tokens_per_second,
            'total_tokens': token_metrics.total_tokens,
            'session_id': self.session_id
        }
        
        self._check_alerts(alert_data)
        
        # Update dashboard data
        MonitoringDashboardHandler.monitoring_data[agent.name] = {
            'last_task': task,
            'last_update': datetime.now().isoformat(),
            'metrics': alert_data
        }
        
        print(f"✅ Task completed: {perf_metrics.tokens_per_second:.1f} TPS")
        
        return token_metrics, perf_metrics
    
    def _check_alerts(self, data: Dict[str, Any]):
        """Check if any alerts should be triggered."""
        
        for alert in self.alerts:
            if alert.condition(data):
                message = f"Alert triggered: {alert.name} for agent {data.get('agent', 'unknown')}"
                
                # Log alert to database
                self.db_logger.log_alert(
                    self.session_id, alert.name, message, "warning"
                )
                
                # Send webhook notification
                self.webhook_notifier.send_alert(
                    alert.name, data, alert.cooldown_seconds
                )
                
                print(f"🚨 ALERT: {message}")
    
    def start_dashboard_server(self, port: int = 8080):
        """Start HTTP dashboard server in background."""
        
        def run_server():
            try:
                server = HTTPServer(('localhost', port), MonitoringDashboardHandler)
                print(f"🌐 Dashboard server started: http://localhost:{port}")
                server.serve_forever()
            except Exception as e:
                print(f"❌ Dashboard server failed: {e}")
        
        # Start server in background thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
    
    def finalize_session(self):
        """Finalize monitoring session."""
        
        session_metrics = self.metrics_collector.get_session_metrics()
        
        # Update database with final metrics
        self.db_logger.update_session_end(
            self.session_id,
            session_metrics['total_tokens']['total_tokens'],
            len([task for tasks in session_metrics['by_agent'].values() for task in [tasks]])
        )
        
        # Get final statistics
        stats = self.db_logger.get_session_stats(self.session_id)
        
        print(f"\n📊 Session Finalized: {self.session_name}")
        print(f"   Total Tokens: {session_metrics['total_tokens']['total_tokens']:,}")
        print(f"   Duration: {session_metrics['duration_seconds']:.1f}s")
        print(f"   Alerts Generated: {len(stats['alerts'])}")
        
        return stats

def main():
    """Demonstrate monitoring integrations."""
    
    print("🔗 Monitoring Integration Examples")
    print("=" * 60)
    
    # Create integrated monitoring system
    monitor = IntegratedMonitoringSystem("Integration Demo Session")
    
    # Add webhook (replace with real URL for testing)
    monitor.add_webhook("https://hooks.slack.com/services/YOUR/WEBHOOK/URL")
    
    # Start dashboard server
    monitor.start_dashboard_server(8080)
    
    # Create agents
    agents = [
        Agent(
            name="Analyst",
            role="Data Analyst",
            goal="Analyze complex datasets",
            backstory="Expert in statistical analysis",
            track_metrics=True,
            metrics_collector=monitor.metrics_collector
        ),
        Agent(
            name="Writer", 
            role="Content Writer",
            goal="Create comprehensive reports",
            backstory="Experienced technical writer",
            track_metrics=True,
            metrics_collector=monitor.metrics_collector
        )
    ]
    
    # Execute monitored workflow
    tasks = [
        ("Analyst", "Analyze quarterly sales data with trends", 200),
        ("Writer", "Write executive summary of sales analysis", 300),
        ("Analyst", "Create statistical models for forecasting", 250),
        ("Writer", "Document methodology and findings", 180),
        ("Analyst", "Perform sensitivity analysis on models", 150),
    ]
    
    print(f"\n🎯 Executing {len(tasks)} monitored tasks...")
    
    for i, (agent_name, task, expected_tokens) in enumerate(tasks, 1):
        agent = next((a for a in agents if a.name == agent_name), None)
        if agent:
            print(f"\n--- Task {i}/{len(tasks)} ---")
            monitor.execute_monitored_task(agent, task, expected_tokens)
            
            # Brief pause between tasks
            time.sleep(0.5)
    
    # Finalize session
    final_stats = monitor.finalize_session()
    
    print(f"\n📋 Integration Summary:")
    print(f"• Database logging: {monitor.db_logger.db_path}")
    print(f"• Webhook notifications: {len(monitor.webhook_notifier.webhook_urls)} configured")
    print(f"• Performance alerts: {len(monitor.alerts)} configured")
    print(f"• Dashboard server: http://localhost:8080")
    
    print(f"\n💡 Integration Capabilities Demonstrated:")
    print(f"• SQLite database logging for persistence")
    print(f"• Webhook notifications with cooldowns")
    print(f"• Real-time dashboard with API endpoints")
    print(f"• Configurable performance alerts")
    print(f"• Multi-agent session tracking")
    print(f"• Comprehensive statistics and reporting")
    
    print(f"\n🌐 Visit http://localhost:8080 to see the live dashboard!")
    print(f"   (Dashboard will run in background - press Ctrl+C to exit)")
    
    # Keep the dashboard running for a while
    try:
        time.sleep(30)  # Run for 30 seconds for demo
    except KeyboardInterrupt:
        print(f"\n👋 Dashboard stopped.")

if __name__ == "__main__":
    main()