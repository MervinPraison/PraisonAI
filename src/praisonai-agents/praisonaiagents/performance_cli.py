"""
Performance Analysis CLI Tool for PraisonAI

Command-line interface for analyzing performance metrics, generating reports,
and managing performance monitoring without code changes.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import logging

from .performance_monitor import get_performance_monitor
from .performance_dashboard import start_performance_dashboard, stop_performance_dashboard
from .auto_instrument import enable_auto_instrumentation, disable_auto_instrumentation


class PerformanceCLI:
    """Command-line interface for PraisonAI performance monitoring."""
    
    def __init__(self):
        self.monitor = get_performance_monitor()
        self.logger = logging.getLogger(__name__)
        
    def run(self, args=None):
        """Run the CLI with provided arguments."""
        parser = self.create_parser()
        parsed_args = parser.parse_args(args)
        
        try:
            if hasattr(parsed_args, 'func'):
                return parsed_args.func(parsed_args)
            else:
                parser.print_help()
                return 1
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser."""
        parser = argparse.ArgumentParser(
            prog='praisonai-perf',
            description='PraisonAI Performance Monitoring and Analysis Tool'
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Enable command
        enable_parser = subparsers.add_parser('enable', help='Enable performance monitoring')
        enable_parser.add_argument('--auto-instrument', action='store_true',
                                 help='Enable automatic instrumentation of PraisonAI functions')
        enable_parser.set_defaults(func=self.enable_monitoring)
        
        # Disable command  
        disable_parser = subparsers.add_parser('disable', help='Disable performance monitoring')
        disable_parser.add_argument('--restore-functions', action='store_true',
                                   help='Restore original functions from auto-instrumentation')
        disable_parser.set_defaults(func=self.disable_monitoring)
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show monitoring status')
        status_parser.set_defaults(func=self.show_status)
        
        # Summary command
        summary_parser = subparsers.add_parser('summary', help='Show performance summary')
        summary_parser.add_argument('--json', action='store_true',
                                   help='Output in JSON format')
        summary_parser.set_defaults(func=self.show_summary)
        
        # Functions command
        functions_parser = subparsers.add_parser('functions', help='Analyze function performance')
        functions_parser.add_argument('--function', type=str,
                                     help='Analyze specific function')
        functions_parser.add_argument('--top', type=int, default=10,
                                     help='Show top N slowest functions')
        functions_parser.add_argument('--json', action='store_true',
                                     help='Output in JSON format')
        functions_parser.set_defaults(func=self.analyze_functions)
        
        # APIs command
        apis_parser = subparsers.add_parser('apis', help='Analyze API call performance')
        apis_parser.add_argument('--type', type=str,
                                help='Filter by API type (llm, http, tool)')
        apis_parser.add_argument('--json', action='store_true',
                                help='Output in JSON format')
        apis_parser.set_defaults(func=self.analyze_apis)
        
        # Hierarchy command
        hierarchy_parser = subparsers.add_parser('hierarchy', help='Show call hierarchy')
        hierarchy_parser.add_argument('--depth', type=int, default=5,
                                     help='Maximum depth to show')
        hierarchy_parser.add_argument('--json', action='store_true',
                                     help='Output in JSON format')
        hierarchy_parser.set_defaults(func=self.show_hierarchy)
        
        # Export command
        export_parser = subparsers.add_parser('export', help='Export performance data')
        export_parser.add_argument('--format', choices=['json'], default='json',
                                  help='Export format')
        export_parser.add_argument('--output', type=str,
                                  help='Output file path')
        export_parser.set_defaults(func=self.export_data)
        
        # Clear command
        clear_parser = subparsers.add_parser('clear', help='Clear performance data')
        clear_parser.add_argument('--confirm', action='store_true',
                                 help='Confirm clearing all data')
        clear_parser.set_defaults(func=self.clear_data)
        
        # Dashboard command
        dashboard_parser = subparsers.add_parser('dashboard', help='Start web dashboard')
        dashboard_parser.add_argument('--port', type=int, default=8888,
                                     help='Port to run dashboard on')
        dashboard_parser.add_argument('--stop', action='store_true',
                                     help='Stop running dashboard')
        dashboard_parser.set_defaults(func=self.manage_dashboard)
        
        # Report command
        report_parser = subparsers.add_parser('report', help='Generate performance report')
        report_parser.add_argument('--output', type=str,
                                  help='Output file path')
        report_parser.add_argument('--format', choices=['text', 'json'], default='text',
                                  help='Report format')
        report_parser.set_defaults(func=self.generate_report)
        
        return parser
    
    def enable_monitoring(self, args):
        """Enable performance monitoring."""
        self.monitor.enable()
        print("✅ Performance monitoring enabled")
        
        if args.auto_instrument:
            try:
                enable_auto_instrumentation()
                print("✅ Auto-instrumentation enabled")
            except Exception as e:
                print(f"⚠️ Auto-instrumentation failed: {e}")
        
        return 0
    
    def disable_monitoring(self, args):
        """Disable performance monitoring."""
        self.monitor.disable()
        print("🔴 Performance monitoring disabled")
        
        if args.restore_functions:
            try:
                disable_auto_instrumentation()
                print("✅ Original functions restored")
            except Exception as e:
                print(f"⚠️ Function restoration failed: {e}")
        
        return 0
    
    def show_status(self, args):
        """Show monitoring status."""
        status = "🟢 ENABLED" if self.monitor.is_enabled() else "🔴 DISABLED"
        print(f"Performance Monitoring: {status}")
        
        summary = self.monitor.get_performance_summary()
        print(f"Session Duration: {summary.get('session_duration', 0):.2f}s")
        print(f"Function Calls: {summary.get('total_function_calls', 0):,}")
        print(f"API Calls: {summary.get('total_api_calls', 0):,}")
        print(f"Errors: {summary.get('errors', 0):,}")
        
        memory = summary.get('memory_usage', {})
        if memory.get('rss_mb', 0) > 0:
            print(f"Memory Usage: {memory['rss_mb']} MB ({memory.get('percent', 0):.1f}%)")
        
        return 0
    
    def show_summary(self, args):
        """Show performance summary."""
        summary = self.monitor.get_performance_summary()
        
        if args.json:
            print(json.dumps(summary, indent=2, default=str))
        else:
            self._print_summary_table(summary)
        
        return 0
    
    def analyze_functions(self, args):
        """Analyze function performance."""
        if args.function:
            # Analyze specific function
            metrics = self.monitor.get_function_metrics(args.function)
            if args.json:
                print(json.dumps(metrics, indent=2, default=str))
            else:
                self._print_function_details(args.function, metrics)
        else:
            # Analyze all functions
            metrics = self.monitor.get_function_metrics()
            if args.json:
                print(json.dumps(metrics, indent=2, default=str))
            else:
                self._print_function_table(metrics, args.top)
        
        return 0
    
    def analyze_apis(self, args):
        """Analyze API call performance."""
        metrics = self.monitor.get_api_metrics(args.type)
        
        if args.json:
            print(json.dumps(metrics, indent=2, default=str))
        else:
            self._print_api_table(metrics)
        
        return 0
    
    def show_hierarchy(self, args):
        """Show call hierarchy."""
        hierarchy = self.monitor.get_call_hierarchy(args.depth)
        
        if args.json:
            print(json.dumps(hierarchy, indent=2, default=str))
        else:
            self._print_hierarchy(hierarchy)
        
        return 0
    
    def export_data(self, args):
        """Export performance data."""
        try:
            data = self.monitor.export_metrics(args.format, args.output)
            
            if args.output:
                print(f"✅ Data exported to {args.output}")
            else:
                print(data)
            
            return 0
        except Exception as e:
            print(f"❌ Export failed: {e}")
            return 1
    
    def clear_data(self, args):
        """Clear performance data."""
        if not args.confirm:
            print("⚠️ This will clear all performance data. Use --confirm to proceed.")
            return 1
        
        self.monitor.clear_metrics()
        print("✅ Performance data cleared")
        return 0
    
    def manage_dashboard(self, args):
        """Manage web dashboard."""
        if args.stop:
            stop_performance_dashboard()
            print("🔴 Dashboard stopped")
        else:
            url = start_performance_dashboard(args.port)
            if url:
                print(f"🚀 Dashboard started at {url}")
                print("Press Ctrl+C to stop")
                try:
                    import time
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    stop_performance_dashboard()
                    print("\n🔴 Dashboard stopped")
            else:
                print("❌ Failed to start dashboard")
                return 1
        
        return 0
    
    def generate_report(self, args):
        """Generate performance report."""
        report_data = {
            'summary': self.monitor.get_performance_summary(),
            'functions': self.monitor.get_function_metrics(),
            'apis': self.monitor.get_api_metrics(),
            'hierarchy': self.monitor.get_call_hierarchy()
        }
        
        if args.format == 'json':
            report = json.dumps(report_data, indent=2, default=str)
        else:
            report = self._generate_text_report(report_data)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"✅ Report generated: {args.output}")
        else:
            print(report)
        
        return 0
    
    def _print_summary_table(self, summary: Dict[str, Any]):
        """Print summary in table format."""
        print("\n📊 Performance Summary")
        print("=" * 50)
        
        duration = summary.get('session_duration', 0)
        print(f"Session Duration:     {duration:.2f}s")
        print(f"Function Calls:       {summary.get('total_function_calls', 0):,}")
        print(f"API Calls:            {summary.get('total_api_calls', 0):,}")
        print(f"Execution Time:       {summary.get('total_execution_time', 0):.3f}s")
        print(f"Errors:               {summary.get('errors', 0):,}")
        
        memory = summary.get('memory_usage', {})
        if memory.get('rss_mb', 0) > 0:
            print(f"Memory Usage:         {memory['rss_mb']} MB ({memory.get('percent', 0):.1f}%)")
        
        # Show slowest functions
        slowest = summary.get('slowest_functions', [])[:5]
        if slowest:
            print(f"\n🐌 Slowest Functions:")
            for func in slowest:
                print(f"  {func['function']}: {func['average_time']:.3f}s ({func['call_count']} calls)")
        
        # Show API summary
        api_summary = summary.get('api_call_summary', {})
        if api_summary:
            print(f"\n🌐 API Call Summary:")
            for api_type, stats in api_summary.items():
                print(f"  {api_type}: {stats['count']} calls, {stats['average_time']:.3f}s avg")
    
    def _print_function_details(self, function_name: str, metrics: Dict[str, Any]):
        """Print detailed function metrics."""
        if not metrics:
            print(f"No data available for function: {function_name}")
            return
        
        print(f"\n🔍 Function Details: {function_name}")
        print("=" * 50)
        print(f"Total Calls:          {metrics.get('total_calls', 0):,}")
        print(f"Total Time:           {metrics.get('total_time', 0):.3f}s")
        print(f"Average Time:         {metrics.get('average_time', 0):.3f}s")
        print(f"Min Time:             {metrics.get('min_time', 0):.3f}s")
        print(f"Max Time:             {metrics.get('max_time', 0):.3f}s")
        print(f"Success Rate:         {metrics.get('success_rate', 0):.1%}")
    
    def _print_function_table(self, metrics: Dict[str, Any], top_n: int):
        """Print function metrics table."""
        if not metrics:
            print("No function performance data available")
            return
        
        # Sort by average time descending
        sorted_functions = sorted(
            metrics.items(),
            key=lambda x: x[1].get('average_time', 0),
            reverse=True
        )[:top_n]
        
        print(f"\n🚀 Top {top_n} Functions by Average Time")
        print("=" * 80)
        print(f"{'Function':<30} {'Calls':<8} {'Total':<10} {'Average':<10} {'Max':<10}")
        print("-" * 80)
        
        for func_name, stats in sorted_functions:
            print(f"{func_name:<30} "
                  f"{stats.get('total_calls', 0):<8} "
                  f"{stats.get('total_time', 0):<10.3f} "
                  f"{stats.get('average_time', 0):<10.3f} "
                  f"{stats.get('max_time', 0):<10.3f}")
    
    def _print_api_table(self, metrics: Dict[str, Any]):
        """Print API metrics table."""
        if not metrics:
            print("No API performance data available")
            return
        
        print(f"\n🌐 API Performance Summary")
        print("=" * 50)
        print(f"Total Calls:          {metrics.get('total_calls', 0):,}")
        print(f"Successful Calls:     {metrics.get('successful_calls', 0):,}")
        print(f"Success Rate:         {metrics.get('success_rate', 0):.1%}")
        print(f"Total Time:           {metrics.get('total_time', 0):.3f}s")
        print(f"Average Time:         {metrics.get('average_time', 0):.3f}s")
        print(f"Min Time:             {metrics.get('min_time', 0):.3f}s")
        print(f"Max Time:             {metrics.get('max_time', 0):.3f}s")
        
        by_provider = metrics.get('by_provider', {})
        if by_provider:
            print(f"\n📊 By Provider:")
            for provider, stats in by_provider.items():
                print(f"  {provider}: {stats['count']} calls, {stats['average_time']:.3f}s avg")
    
    def _print_hierarchy(self, hierarchy: Dict[str, Any]):
        """Print call hierarchy."""
        calls = hierarchy.get('call_hierarchy', [])
        if not calls:
            print("No call hierarchy data available")
            return
        
        print(f"\n🌳 Call Hierarchy")
        print("=" * 50)
        
        def print_call(call, depth=0):
            indent = "  " * depth
            symbol = "├─" if depth > 0 else "└─"
            status = "✅" if call.get('success', True) else "❌"
            duration = call.get('duration', 0)
            
            print(f"{indent}{symbol} {status} {call['function']} ({duration:.3f}s)")
            
            for child in call.get('children', []):
                print_call(child, depth + 1)
        
        for call in calls:
            print_call(call)
            print()
    
    def _generate_text_report(self, data: Dict[str, Any]) -> str:
        """Generate a comprehensive text report."""
        report = []
        report.append("📊 PraisonAI Performance Report")
        report.append("=" * 50)
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        # Summary
        summary = data.get('summary', {})
        report.append("📈 Summary")
        report.append("-" * 20)
        report.append(f"Session Duration:     {summary.get('session_duration', 0):.2f}s")
        report.append(f"Function Calls:       {summary.get('total_function_calls', 0):,}")
        report.append(f"API Calls:            {summary.get('total_api_calls', 0):,}")
        report.append(f"Total Execution Time: {summary.get('total_execution_time', 0):.3f}s")
        report.append(f"Errors:               {summary.get('errors', 0):,}")
        report.append("")
        
        # Top Functions
        functions = data.get('functions', {})
        if functions:
            sorted_funcs = sorted(
                functions.items(),
                key=lambda x: x[1].get('average_time', 0),
                reverse=True
            )[:10]
            
            report.append("🚀 Top Functions by Average Time")
            report.append("-" * 40)
            for func_name, stats in sorted_funcs:
                report.append(f"{func_name}: {stats.get('average_time', 0):.3f}s "
                            f"({stats.get('total_calls', 0)} calls)")
            report.append("")
        
        # API Summary
        apis = data.get('apis', {})
        if apis:
            report.append("🌐 API Performance")
            report.append("-" * 20)
            report.append(f"Total API Calls:   {apis.get('total_calls', 0):,}")
            report.append(f"Success Rate:      {apis.get('success_rate', 0):.1%}")
            report.append(f"Average Time:      {apis.get('average_time', 0):.3f}s")
            report.append("")
        
        return "\n".join(report)


def main():
    """Main entry point for the CLI."""
    cli = PerformanceCLI()
    return cli.run()


if __name__ == '__main__':
    sys.exit(main())