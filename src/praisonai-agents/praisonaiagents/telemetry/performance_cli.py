"""
Performance Monitoring CLI for PraisonAI

Command-line interface for accessing performance monitoring features.
Provides easy access to function performance, API call tracking, and flow analysis.

Usage:
    python -m praisonaiagents.telemetry.performance_cli [command] [options]
    
Or import and use programmatically:
    from praisonaiagents.telemetry.performance_cli import PerformanceCLI
    cli = PerformanceCLI()
    cli.show_performance_report()
"""

import argparse
import json
import sys
from typing import Optional
import logging

try:
    from .performance_monitor import performance_monitor, get_performance_report
    from .performance_utils import (
        analyze_function_flow, visualize_execution_flow, 
        analyze_performance_trends, generate_comprehensive_report
    )
    PERFORMANCE_TOOLS_AVAILABLE = True
except ImportError:
    PERFORMANCE_TOOLS_AVAILABLE = False

logger = logging.getLogger(__name__)


class PerformanceCLI:
    """Command-line interface for performance monitoring."""
    
    def __init__(self):
        if not PERFORMANCE_TOOLS_AVAILABLE:
            print("❌ Performance monitoring tools not available")
            sys.exit(1)
    
    def show_performance_report(self, detailed: bool = False) -> None:
        """Show performance monitoring report."""
        print("📊 PraisonAI Performance Monitoring Report")
        print("=" * 60)
        
        if detailed:
            report = generate_comprehensive_report()
        else:
            report = get_performance_report()
        
        print(report)
    
    def show_function_stats(self, function_name: Optional[str] = None) -> None:
        """Show function performance statistics."""
        stats = performance_monitor.get_function_performance(function_name)
        
        if not stats:
            print("❌ No function performance data available")
            return
        
        print("🔧 Function Performance Statistics")
        print("=" * 50)
        
        for func, data in stats.items():
            print(f"\n📝 Function: {func}")
            print(f"   Calls: {data['call_count']}")
            print(f"   Total Time: {data['total_time']:.3f}s")
            if data['call_count'] > 0:
                print(f"   Average Time: {data.get('average_time', 0):.3f}s")
                print(f"   Min Time: {data['min_time']:.3f}s")
                print(f"   Max Time: {data['max_time']:.3f}s")
                print(f"   Success Rate: {data.get('success_rate', 0)*100:.1f}%")
                print(f"   Errors: {data['error_count']}")
    
    def show_api_stats(self, api_name: Optional[str] = None) -> None:
        """Show API call performance statistics."""
        stats = performance_monitor.get_api_call_performance(api_name)
        
        if not stats:
            print("❌ No API performance data available")
            return
        
        print("🌐 API Call Performance Statistics")
        print("=" * 50)
        
        for api, data in stats.items():
            print(f"\n🔗 API: {api}")
            print(f"   Calls: {data['call_count']}")
            print(f"   Total Time: {data['total_time']:.3f}s")
            if data['call_count'] > 0:
                print(f"   Average Time: {data.get('average_time', 0):.3f}s")
                print(f"   Min Time: {data['min_time']:.3f}s")
                print(f"   Max Time: {data['max_time']:.3f}s")
                print(f"   Success Rate: {data.get('success_rate', 0)*100:.1f}%")
                print(f"   Successful Calls: {data['success_count']}")
                print(f"   Failed Calls: {data['error_count']}")
    
    def show_slowest_functions(self, limit: int = 10) -> None:
        """Show slowest performing functions."""
        slowest = performance_monitor.get_slowest_functions(limit)
        
        if not slowest:
            print("❌ No function performance data available")
            return
        
        print(f"🐌 Top {limit} Slowest Functions")
        print("=" * 50)
        
        for i, func in enumerate(slowest, 1):
            print(f"{i:2d}. {func['function']}")
            print(f"     Average: {func['average_time']:.3f}s")
            print(f"     Max: {func['max_time']:.3f}s")
            print(f"     Calls: {func['call_count']}")
            print()
    
    def show_slowest_apis(self, limit: int = 10) -> None:
        """Show slowest performing API calls."""
        slowest = performance_monitor.get_slowest_api_calls(limit)
        
        if not slowest:
            print("❌ No API performance data available")
            return
        
        print(f"🐌 Top {limit} Slowest API Calls")
        print("=" * 50)
        
        for i, api in enumerate(slowest, 1):
            print(f"{i:2d}. {api['api']}")
            print(f"     Average: {api['average_time']:.3f}s")
            print(f"     Max: {api['max_time']:.3f}s") 
            print(f"     Success Rate: {api['success_rate']*100:.1f}%")
            print(f"     Calls: {api['call_count']}")
            print()
    
    def show_function_flow(self, format: str = "text", events: int = 50) -> None:
        """Show function execution flow."""
        print(f"🔄 Function Execution Flow (Last {events} events)")
        print("=" * 60)
        
        flow_data = performance_monitor.get_function_flow(events)
        if not flow_data:
            print("❌ No flow data available")
            return
        
        if format == "json":
            print(json.dumps(flow_data, indent=2))
        else:
            visualization = visualize_execution_flow(format=format)
            print(visualization)
    
    def analyze_flow(self) -> None:
        """Analyze function execution flow for bottlenecks and patterns."""
        print("🔍 Function Flow Analysis")
        print("=" * 50)
        
        analysis = analyze_function_flow()
        
        if "error" in analysis:
            print(f"❌ {analysis['error']}")
            return
        
        if "message" in analysis:
            print(f"ℹ️  {analysis['message']}")
            return
        
        # Show bottlenecks
        bottlenecks = analysis.get("bottlenecks", [])
        if bottlenecks:
            print("🚨 Identified Bottlenecks:")
            for bottleneck in bottlenecks:
                severity_emoji = "🔴" if bottleneck["severity"] == "high" else "🟡"
                print(f"  {severity_emoji} {bottleneck['function']}")
                print(f"     Average: {bottleneck['average_duration']:.3f}s")
                print(f"     Max: {bottleneck['max_duration']:.3f}s")
                print(f"     Calls: {bottleneck['call_count']}")
                print()
        else:
            print("✅ No significant bottlenecks identified")
        
        # Show statistics
        stats = analysis.get("statistics", {})
        if stats:
            print("\n📊 Flow Statistics:")
            print(f"   Total Function Calls: {stats.get('function_calls', 0)}")
            print(f"   Completed Calls: {stats.get('completed_calls', 0)}")
            print(f"   Success Rate: {stats.get('success_rate', 0)*100:.1f}%")
            print(f"   Total Execution Time: {stats.get('total_execution_time', 0):.3f}s")
            print(f"   Average Execution Time: {stats.get('average_execution_time', 0):.3f}s")
        
        # Show parallelism info
        parallelism = analysis.get("parallelism", {})
        if parallelism:
            print("\n🧵 Parallelism Analysis:")
            print(f"   Total Threads: {parallelism.get('total_threads', 0)}")
            print(f"   Peak Concurrency: {parallelism.get('peak_concurrency', 0)}")
    
    def show_active_calls(self) -> None:
        """Show currently active function calls."""
        active = performance_monitor.get_active_calls()
        
        print("⚡ Currently Active Function Calls")
        print("=" * 50)
        
        if not active:
            print("✅ No active function calls")
            return
        
        for _call_id, info in active.items():
            print(f"🔄 {info['function']}")
            print(f"   Duration: {info['duration']:.1f}s")
            print(f"   Thread: {info['thread_id']}")
            print(f"   Started: {info['started_at']}")
            print()
    
    def show_trends(self) -> None:
        """Show performance trends analysis."""
        print("📈 Performance Trends Analysis")
        print("=" * 50)
        
        trends = analyze_performance_trends()
        
        if "error" in trends:
            print(f"❌ {trends['error']}")
            return
        
        # Show recommendations
        recommendations = trends.get("recommendations", [])
        if recommendations:
            print("💡 Performance Recommendations:")
            for rec in recommendations:
                print(f"  {rec}")
            print()
        
        # Show function trends
        func_trends = trends.get("function_trends", {})
        improving = func_trends.get("improving", [])
        degrading = func_trends.get("degrading", [])
        
        if improving:
            print("📈 Improving Functions:")
            for trend in improving:
                print(f"  ✅ {trend['function']} ({trend['change_percent']:+.1f}%)")
        
        if degrading:
            print("\n📉 Degrading Functions:")
            for trend in degrading:
                print(f"  ⚠️  {trend['function']} ({trend['change_percent']:+.1f}%)")
        
        # Show API trends
        api_trends = trends.get("api_trends", {})
        slowest_apis = api_trends.get("slowest_apis", [])
        least_reliable = api_trends.get("least_reliable", [])
        
        if slowest_apis:
            print("\n🐌 Slowest APIs:")
            for api in slowest_apis[:3]:
                print(f"  • {api['api']}: {api['average_time']:.3f}s avg")
        
        if least_reliable:
            print("\n⚠️  Least Reliable APIs:")
            for api in least_reliable[:3]:
                if api['success_rate'] < 1.0:
                    print(f"  • {api['api']}: {api['success_rate']*100:.1f}% success rate")
    
    def export_data(self, format: str = "json", output_file: Optional[str] = None) -> None:
        """Export performance data to file or stdout."""
        data = performance_monitor.export_data(format)
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    f.write(data)
                print(f"✅ Data exported to {output_file}")
            except (IOError, OSError) as e:
                print(f"❌ Error exporting to file: {e}")
        else:
            print(data)
    
    def clear_data(self) -> None:
        """Clear all performance monitoring data."""
        performance_monitor.clear_statistics()
        print("✅ All performance monitoring data cleared")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="PraisonAI Performance Monitoring CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m praisonaiagents.telemetry.performance_cli report
  python -m praisonaiagents.telemetry.performance_cli functions
  python -m praisonaiagents.telemetry.performance_cli apis
  python -m praisonaiagents.telemetry.performance_cli slowest-functions 5
  python -m praisonaiagents.telemetry.performance_cli flow
  python -m praisonaiagents.telemetry.performance_cli analyze-flow
  python -m praisonaiagents.telemetry.performance_cli trends
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Show performance report')
    report_parser.add_argument('--detailed', action='store_true', 
                              help='Show detailed comprehensive report')
    
    # Functions command
    func_parser = subparsers.add_parser('functions', help='Show function statistics')
    func_parser.add_argument('--name', help='Specific function name')
    
    # APIs command  
    api_parser = subparsers.add_parser('apis', help='Show API call statistics')
    api_parser.add_argument('--name', help='Specific API name')
    
    # Slowest functions command
    slowest_func_parser = subparsers.add_parser('slowest-functions', 
                                               help='Show slowest functions')
    slowest_func_parser.add_argument('limit', type=int, nargs='?', default=10,
                                    help='Number of functions to show')
    
    # Slowest APIs command
    slowest_api_parser = subparsers.add_parser('slowest-apis',
                                              help='Show slowest API calls')
    slowest_api_parser.add_argument('limit', type=int, nargs='?', default=10,
                                   help='Number of APIs to show')
    
    # Flow command
    flow_parser = subparsers.add_parser('flow', help='Show function execution flow')
    flow_parser.add_argument('--format', choices=['text', 'json', 'mermaid'], 
                           default='text', help='Output format')
    flow_parser.add_argument('--events', type=int, default=50,
                           help='Number of recent events to show')
    
    # Analyze flow command
    subparsers.add_parser('analyze-flow', help='Analyze function flow for bottlenecks')
    
    # Active calls command
    subparsers.add_parser('active', help='Show currently active function calls')
    
    # Trends command
    subparsers.add_parser('trends', help='Show performance trends analysis')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export performance data')
    export_parser.add_argument('--format', choices=['json', 'dict'], default='json',
                              help='Export format')
    export_parser.add_argument('--output', help='Output file (default: stdout)')
    
    # Clear command
    subparsers.add_parser('clear', help='Clear all performance data')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        cli = PerformanceCLI()
        
        if args.command == 'report':
            cli.show_performance_report(detailed=args.detailed)
        elif args.command == 'functions':
            cli.show_function_stats(args.name)
        elif args.command == 'apis':
            cli.show_api_stats(args.name)
        elif args.command == 'slowest-functions':
            cli.show_slowest_functions(args.limit)
        elif args.command == 'slowest-apis':
            cli.show_slowest_apis(args.limit)
        elif args.command == 'flow':
            cli.show_function_flow(args.format, args.events)
        elif args.command == 'analyze-flow':
            cli.analyze_flow()
        elif args.command == 'active':
            cli.show_active_calls()
        elif args.command == 'trends':
            cli.show_trends()
        elif args.command == 'export':
            cli.export_data(args.format, args.output)
        elif args.command == 'clear':
            cli.clear_data()
    
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()