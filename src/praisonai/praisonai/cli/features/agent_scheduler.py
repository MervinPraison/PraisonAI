"""
Agent Scheduler CLI Feature.

Provides CLI commands for scheduling agents to run 24/7 at regular intervals.
"""

import logging

logger = logging.getLogger(__name__)


class AgentSchedulerHandler:
    """Handler for agent scheduler CLI commands."""
    
    @staticmethod
    def handle_schedule_command(args) -> int:
        """
        Handle the schedule command for running agents periodically.
        
        Args:
            args: Parsed command-line arguments
            
        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            from praisonai.scheduler import AgentScheduler
        except ImportError:
            print("Error: praisonai.scheduler module not found")
            print("Please ensure PraisonAI is properly installed")
            return 1
        
        # Get YAML file path (default to agents.yaml)
        yaml_path = getattr(args, 'schedule_yaml', None) or 'agents.yaml'
        
        # Get overrides from CLI
        interval_override = getattr(args, 'schedule_interval', None)
        max_retries_override = getattr(args, 'schedule_max_retries', None)
        verbose = getattr(args, 'verbose', False)
        
        # Set up logging
        if verbose:
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        try:
            # Create scheduler from YAML
            print(f"🤖 Loading agent configuration from: {yaml_path}")
            scheduler = AgentScheduler.from_yaml(
                yaml_path=yaml_path,
                interval_override=interval_override,
                max_retries_override=max_retries_override
            )
            
            # Display configuration
            agent_name = getattr(scheduler.agent, 'name', 'Agent')
            print(f"\n{'='*60}")
            print(f"🤖 Starting 24/7 {agent_name}")
            print(f"{'='*60}")
            print(f"Task: {scheduler.task[:80]}{'...' if len(scheduler.task) > 80 else ''}")
            
            # Get schedule info
            schedule_config = scheduler._yaml_schedule_config
            interval = interval_override or schedule_config.get('interval', 'hourly')
            max_retries = max_retries_override or schedule_config.get('max_retries', 3)
            
            print(f"Schedule: {interval}")
            print(f"Max Retries: {max_retries}")
            print(f"{'='*60}\n")
            
            # Start scheduler
            print("⏰ Starting scheduler... (Press Ctrl+C to stop)\n")
            scheduler.start_from_yaml_config()
            
            # Keep running until interrupted
            try:
                while scheduler.is_running:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\n🛑 Stopping scheduler...")
                scheduler.stop()
                
                # Display final stats
                stats = scheduler.get_stats()
                print("\n📊 Final Statistics:")
                print(f"  Total Executions: {stats['total_executions']}")
                print(f"  Successful: {stats['successful_executions']}")
                print(f"  Failed: {stats['failed_executions']}")
                print(f"  Success Rate: {stats['success_rate']:.1f}%")
                print("\n✅ Agent stopped successfully\n")
                
            return 0
            
        except FileNotFoundError as e:
            print(f"❌ Error: {e}")
            print(f"\nMake sure {yaml_path} exists in the current directory.")
            print("\nExample agents.yaml structure:")
            print("""
framework: praisonai

agents:
  - name: "AI News Monitor"
    role: "News Analyst"
    instructions: "Search and summarize AI news"
    tools:
      - search_tool

task: "Search for latest AI news"

schedule:
  interval: "hourly"
  max_retries: 3
  run_immediately: true
""")
            return 1
            
        except ValueError as e:
            print(f"❌ Configuration Error: {e}")
            return 1
            
        except Exception as e:
            print(f"❌ Error: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            return 1
            
    @staticmethod
    def add_schedule_arguments(subparsers):
        """
        Add schedule subcommand and arguments to parser.
        
        Args:
            subparsers: Subparsers object from argparse
        """
        schedule_parser = subparsers.add_parser(
            'schedule',
            help='Schedule an agent to run continuously at regular intervals'
        )
        
        schedule_parser.add_argument(
            'schedule_yaml',
            nargs='?',
            default='agents.yaml',
            help='Path to agents.yaml file (default: agents.yaml)'
        )
        
        schedule_parser.add_argument(
            '--interval',
            dest='schedule_interval',
            type=str,
            help='Override schedule interval (e.g., "hourly", "*/30m", "daily")'
        )
        
        schedule_parser.add_argument(
            '--max-retries',
            dest='schedule_max_retries',
            type=int,
            help='Override maximum retry attempts (default: from YAML or 3)'
        )
        
        schedule_parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Enable verbose logging'
        )
        
        schedule_parser.set_defaults(func=AgentSchedulerHandler.handle_schedule_command)


def setup_scheduler_cli(subparsers):
    """
    Setup scheduler CLI commands.
    
    Args:
        subparsers: Subparsers object from argparse
    """
    AgentSchedulerHandler.add_schedule_arguments(subparsers)
