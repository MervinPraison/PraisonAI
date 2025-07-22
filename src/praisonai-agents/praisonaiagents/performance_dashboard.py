"""
Performance Dashboard for PraisonAI

A web-based dashboard for viewing real-time performance metrics and analysis.
Provides detailed insights into function performance, API calls, and system health.
"""

import json
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from .performance_monitor import get_performance_monitor


class PerformanceDashboard:
    """
    Web-based performance dashboard for real-time monitoring.
    
    Provides a simple HTTP server that serves performance metrics
    and visualizations for PraisonAI applications.
    """
    
    def __init__(self, port: int = 8888, update_interval: int = 5):
        self.port = port
        self.update_interval = update_interval
        self.logger = logging.getLogger(__name__)
        self.server = None
        self.server_thread = None
        self.running = False
        
    def start(self):
        """Start the dashboard server."""
        if self.running:
            self.logger.warning("Dashboard is already running")
            return
            
        try:
            from http.server import HTTPServer, SimpleHTTPRequestHandler
            import urllib.parse
            
            class DashboardHandler(SimpleHTTPRequestHandler):
                def __init__(self, dashboard_instance, *args, **kwargs):
                    self.dashboard = dashboard_instance
                    super().__init__(*args, **kwargs)
                    
                def do_GET(self):
                    if self.path == '/':
                        self.serve_dashboard()
                    elif self.path == '/api/metrics':
                        self.serve_metrics()
                    elif self.path == '/api/summary':
                        self.serve_summary()
                    elif self.path == '/api/functions':
                        self.serve_function_metrics()
                    elif self.path == '/api/apis':
                        self.serve_api_metrics()
                    elif self.path == '/api/hierarchy':
                        self.serve_call_hierarchy()
                    else:
                        self.send_error(404)
                        
                def serve_dashboard(self):
                    """Serve the main dashboard HTML page."""
                    html_content = self.dashboard._get_dashboard_html()
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(html_content.encode())
                    
                def serve_metrics(self):
                    """Serve all performance metrics as JSON."""
                    monitor = get_performance_monitor()
                    data = {
                        'summary': monitor.get_performance_summary(),
                        'functions': monitor.get_function_metrics(),
                        'apis': monitor.get_api_metrics(),
                        'hierarchy': monitor.get_call_hierarchy(),
                        'timestamp': datetime.now().isoformat()
                    }
                    self.send_json_response(data)
                    
                def serve_summary(self):
                    """Serve performance summary."""
                    monitor = get_performance_monitor()
                    data = monitor.get_performance_summary()
                    self.send_json_response(data)
                    
                def serve_function_metrics(self):
                    """Serve function performance metrics."""
                    monitor = get_performance_monitor()
                    data = monitor.get_function_metrics()
                    self.send_json_response(data)
                    
                def serve_api_metrics(self):
                    """Serve API performance metrics."""
                    monitor = get_performance_monitor()
                    data = monitor.get_api_metrics()
                    self.send_json_response(data)
                    
                def serve_call_hierarchy(self):
                    """Serve call hierarchy data."""
                    monitor = get_performance_monitor()
                    data = monitor.get_call_hierarchy()
                    self.send_json_response(data)
                    
                def send_json_response(self, data):
                    """Send JSON response with CORS headers."""
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    json_str = json.dumps(data, default=str, indent=2)
                    self.wfile.write(json_str.encode())
                    
                def log_message(self, format, *args):
                    # Suppress HTTP server logs to reduce noise
                    pass
            
            # Create handler factory with dashboard instance
            handler_factory = lambda *args, **kwargs: DashboardHandler(self, *args, **kwargs)
            
            self.server = HTTPServer(('localhost', self.port), handler_factory)
            self.running = True
            
            # Start server in background thread
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            self.logger.info(f"Performance dashboard started at http://localhost:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Failed to start dashboard: {e}")
            self.running = False
            
    def stop(self):
        """Stop the dashboard server."""
        if not self.running:
            return
            
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            
        if self.server_thread:
            self.server_thread.join(timeout=5)
            
        self.running = False
        self.logger.info("Performance dashboard stopped")
        
    def is_running(self) -> bool:
        """Check if the dashboard is running."""
        return self.running
        
    def _get_dashboard_html(self) -> str:
        """Generate the dashboard HTML interface."""
        return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PraisonAI Performance Dashboard</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        .header h1 {
            margin: 0;
            font-size: 2.5em;
        }
        .header p {
            margin: 10px 0 0 0;
            opacity: 0.9;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .card h3 {
            margin-top: 0;
            color: #333;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        .metric:last-child {
            border-bottom: none;
        }
        .metric-value {
            font-weight: bold;
            color: #667eea;
        }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .status.active {
            background-color: #d4edda;
            color: #155724;
        }
        .status.inactive {
            background-color: #f8d7da;
            color: #721c24;
        }
        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin-bottom: 20px;
        }
        .refresh-btn:hover {
            background: #5a6fd8;
        }
        .table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        .table th,
        .table td {
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        .table th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .hierarchy {
            font-family: monospace;
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            max-height: 400px;
        }
        .hierarchy-item {
            margin: 2px 0;
            white-space: nowrap;
        }
        .depth-0 { margin-left: 0px; }
        .depth-1 { margin-left: 20px; }
        .depth-2 { margin-left: 40px; }
        .depth-3 { margin-left: 60px; }
        .depth-4 { margin-left: 80px; }
        .error { color: #dc3545; }
        .success { color: #28a745; }
        .auto-refresh {
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 PraisonAI Performance Dashboard</h1>
            <p>Real-time monitoring of agent performance, API calls, and system metrics</p>
        </div>
        
        <div style="text-align: center; margin-bottom: 20px;">
            <button class="refresh-btn" onclick="refreshData()">🔄 Refresh Data</button>
            <label class="auto-refresh">
                <input type="checkbox" id="autoRefresh" onchange="toggleAutoRefresh()"> Auto-refresh (10s)
            </label>
        </div>
        
        <div class="grid">
            <!-- System Overview -->
            <div class="card">
                <h3>📊 System Overview</h3>
                <div id="system-overview">Loading...</div>
            </div>
            
            <!-- Performance Summary -->
            <div class="card">
                <h3>⚡ Performance Summary</h3>
                <div id="performance-summary">Loading...</div>
            </div>
            
            <!-- Top Functions -->
            <div class="card">
                <h3>🔥 Slowest Functions</h3>
                <div id="top-functions">Loading...</div>
            </div>
            
            <!-- API Calls -->
            <div class="card">
                <h3>🌐 API Call Summary</h3>
                <div id="api-summary">Loading...</div>
            </div>
        </div>
        
        <!-- Function Details -->
        <div class="card">
            <h3>📋 Function Performance Details</h3>
            <div id="function-details">Loading...</div>
        </div>
        
        <!-- Call Hierarchy -->
        <div class="card">
            <h3>🌳 Call Hierarchy</h3>
            <div id="call-hierarchy">Loading...</div>
        </div>
    </div>

    <script>
        let autoRefreshInterval = null;
        
        async function fetchData(endpoint) {
            try {
                const response = await fetch(endpoint);
                return await response.json();
            } catch (error) {
                console.error('Error fetching data:', error);
                return null;
            }
        }
        
        function formatTime(seconds) {
            if (seconds < 0.001) return (seconds * 1000000).toFixed(1) + ' μs';
            if (seconds < 1) return (seconds * 1000).toFixed(1) + ' ms';
            return seconds.toFixed(3) + ' s';
        }
        
        function formatNumber(num) {
            return new Intl.NumberFormat().format(num);
        }
        
        async function updateSystemOverview() {
            const data = await fetchData('/api/summary');
            if (!data) return;
            
            const container = document.getElementById('system-overview');
            const status = data.total_function_calls > 0 ? 'active' : 'inactive';
            
            container.innerHTML = `
                <div class="metric">
                    <span>Monitoring Status</span>
                    <span class="status ${status}">${status.toUpperCase()}</span>
                </div>
                <div class="metric">
                    <span>Session Duration</span>
                    <span class="metric-value">${formatTime(data.session_duration || 0)}</span>
                </div>
                <div class="metric">
                    <span>Memory Usage</span>
                    <span class="metric-value">${data.memory_usage?.rss_mb || 0} MB</span>
                </div>
                <div class="metric">
                    <span>Total Errors</span>
                    <span class="metric-value ${data.errors > 0 ? 'error' : 'success'}">${formatNumber(data.errors || 0)}</span>
                </div>
            `;
        }
        
        async function updatePerformanceSummary() {
            const data = await fetchData('/api/summary');
            if (!data) return;
            
            const container = document.getElementById('performance-summary');
            container.innerHTML = `
                <div class="metric">
                    <span>Function Calls</span>
                    <span class="metric-value">${formatNumber(data.total_function_calls || 0)}</span>
                </div>
                <div class="metric">
                    <span>API Calls</span>
                    <span class="metric-value">${formatNumber(data.total_api_calls || 0)}</span>
                </div>
                <div class="metric">
                    <span>Total Execution Time</span>
                    <span class="metric-value">${formatTime(data.total_execution_time || 0)}</span>
                </div>
            `;
        }
        
        async function updateTopFunctions() {
            const data = await fetchData('/api/summary');
            if (!data || !data.slowest_functions) return;
            
            const container = document.getElementById('top-functions');
            const functions = data.slowest_functions.slice(0, 5);
            
            if (functions.length === 0) {
                container.innerHTML = '<p>No function data available</p>';
                return;
            }
            
            let html = '<table class="table"><tr><th>Function</th><th>Avg Time</th><th>Calls</th></tr>';
            functions.forEach(func => {
                html += `
                    <tr>
                        <td>${func.function}</td>
                        <td>${formatTime(func.average_time)}</td>
                        <td>${formatNumber(func.call_count)}</td>
                    </tr>
                `;
            });
            html += '</table>';
            
            container.innerHTML = html;
        }
        
        async function updateApiSummary() {
            const data = await fetchData('/api/summary');
            if (!data || !data.api_call_summary) return;
            
            const container = document.getElementById('api-summary');
            const apis = Object.entries(data.api_call_summary);
            
            if (apis.length === 0) {
                container.innerHTML = '<p>No API call data available</p>';
                return;
            }
            
            let html = '';
            apis.forEach(([apiType, stats]) => {
                html += `
                    <div class="metric">
                        <span>${apiType}</span>
                        <span class="metric-value">${formatNumber(stats.count)} calls (${formatTime(stats.average_time)} avg)</span>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        async function updateFunctionDetails() {
            const data = await fetchData('/api/functions');
            if (!data) return;
            
            const container = document.getElementById('function-details');
            const functions = Object.entries(data);
            
            if (functions.length === 0) {
                container.innerHTML = '<p>No detailed function data available</p>';
                return;
            }
            
            let html = '<table class="table"><tr><th>Function</th><th>Calls</th><th>Total Time</th><th>Avg Time</th><th>Min/Max</th></tr>';
            
            functions.slice(0, 20).forEach(([funcName, stats]) => {
                html += `
                    <tr>
                        <td>${funcName}</td>
                        <td>${formatNumber(stats.total_calls)}</td>
                        <td>${formatTime(stats.total_time)}</td>
                        <td>${formatTime(stats.average_time)}</td>
                        <td>${formatTime(stats.min_time)} / ${formatTime(stats.max_time)}</td>
                    </tr>
                `;
            });
            html += '</table>';
            
            container.innerHTML = html;
        }
        
        async function updateCallHierarchy() {
            const data = await fetchData('/api/hierarchy');
            if (!data || !data.call_hierarchy) return;
            
            const container = document.getElementById('call-hierarchy');
            
            function renderHierarchy(calls, depth = 0) {
                let html = '';
                calls.forEach(call => {
                    const indent = '  '.repeat(depth);
                    const statusClass = call.success ? 'success' : 'error';
                    html += `<div class="hierarchy-item depth-${Math.min(depth, 4)}">`;
                    html += `${indent}├─ <span class="${statusClass}">${call.function}</span> `;
                    html += `(${formatTime(call.duration || 0)})`;
                    html += `</div>`;
                    
                    if (call.children && call.children.length > 0) {
                        html += renderHierarchy(call.children, depth + 1);
                    }
                });
                return html;
            }
            
            if (data.call_hierarchy.length === 0) {
                container.innerHTML = '<p>No call hierarchy data available</p>';
                return;
            }
            
            const hierarchyHtml = renderHierarchy(data.call_hierarchy.slice(0, 5));
            container.innerHTML = `<div class="hierarchy">${hierarchyHtml}</div>`;
        }
        
        async function refreshData() {
            await Promise.all([
                updateSystemOverview(),
                updatePerformanceSummary(),
                updateTopFunctions(),
                updateApiSummary(),
                updateFunctionDetails(),
                updateCallHierarchy()
            ]);
        }
        
        function toggleAutoRefresh() {
            const checkbox = document.getElementById('autoRefresh');
            if (checkbox.checked) {
                autoRefreshInterval = setInterval(refreshData, 10000);
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        }
        
        // Initial load
        refreshData();
    </script>
</body>
</html>'''


# Global dashboard instance
_dashboard = None


def get_performance_dashboard() -> PerformanceDashboard:
    """Get the global performance dashboard instance."""
    global _dashboard
    if _dashboard is None:
        _dashboard = PerformanceDashboard()
    return _dashboard


def start_performance_dashboard(port: int = 8888) -> str:
    """
    Start the performance dashboard web server.
    
    Args:
        port: Port number to run the dashboard on
        
    Returns:
        URL of the dashboard
    """
    dashboard = get_performance_dashboard()
    dashboard.port = port
    dashboard.start()
    
    if dashboard.is_running():
        return f"http://localhost:{port}"
    else:
        return ""


def stop_performance_dashboard():
    """Stop the performance dashboard."""
    dashboard = get_performance_dashboard()
    dashboard.stop()