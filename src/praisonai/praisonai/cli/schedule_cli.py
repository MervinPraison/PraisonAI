"""
Simple CLI entry point for praisonai schedule command.

This provides a standalone entry point that can be called from main.py
"""

import sys
from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler


def main():
    """Main entry point for schedule CLI command."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Schedule an agent to run continuously at regular intervals'
    )
    
    parser.add_argument(
        'schedule_yaml',
        nargs='?',
        default='agents.yaml',
        help='Path to agents.yaml file (default: agents.yaml)'
    )
    
    parser.add_argument(
        '--interval',
        dest='schedule_interval',
        type=str,
        help='Override schedule interval (e.g., "hourly", "*/30m", "daily")'
    )
    
    parser.add_argument(
        '--max-retries',
        dest='schedule_max_retries',
        type=int,
        help='Override maximum retry attempts (default: from YAML or 3)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Call the handler
    exit_code = AgentSchedulerHandler.handle_schedule_command(args)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
