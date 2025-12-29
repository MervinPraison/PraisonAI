"""
Agent Scheduler CLI Feature.

Provides CLI commands for scheduling agents to run 24/7 at regular intervals.
"""

import logging

logger = logging.getLogger(__name__)


class AgentSchedulerHandler:
    """Handler for agent scheduler CLI commands."""
    
    @staticmethod
    def handle_daemon_command(subcommand: str, args, unknown_args=None) -> int:
        """
        Handle daemon management commands (start, list, stop, logs, restart).
        
        Args:
            subcommand: Command to execute (start, list, stop, logs, restart)
            args: Parsed command-line arguments
            unknown_args: Additional arguments
            
        Returns:
            Exit code
        """
        from praisonai.scheduler.state_manager import SchedulerStateManager
        from praisonai.scheduler.daemon_manager import DaemonManager
        
        state_manager = SchedulerStateManager()
        daemon_manager = DaemonManager()
        
        if subcommand == "start":
            return AgentSchedulerHandler._handle_start(args, unknown_args, state_manager, daemon_manager)
        elif subcommand == "list":
            return AgentSchedulerHandler._handle_list(state_manager)
        elif subcommand == "stop":
            return AgentSchedulerHandler._handle_stop(unknown_args, state_manager, daemon_manager)
        elif subcommand == "logs":
            return AgentSchedulerHandler._handle_logs(unknown_args, daemon_manager)
        elif subcommand == "restart":
            return AgentSchedulerHandler._handle_restart(unknown_args, state_manager, daemon_manager)
        elif subcommand == "delete":
            return AgentSchedulerHandler._handle_delete(unknown_args, state_manager)
        elif subcommand == "describe":
            return AgentSchedulerHandler._handle_describe(unknown_args, state_manager, daemon_manager)
        elif subcommand == "save":
            return AgentSchedulerHandler._handle_save(unknown_args, state_manager)
        elif subcommand == "stop-all":
            return AgentSchedulerHandler._handle_stop_all(state_manager, daemon_manager)
        elif subcommand == "stats":
            return AgentSchedulerHandler._handle_stats(state_manager, unknown_args, daemon_manager)
        else:
            print(f"❌ Unknown subcommand: {subcommand}")
            print("\nAvailable commands:")
            print("  start, list, stop, logs, restart, delete, describe, save, stop-all, stats")
            return 1
    
    @staticmethod
    def _handle_start(args, unknown_args, state_manager, daemon_manager) -> int:
        """Handle 'schedule start' command."""
        from datetime import datetime
        
        if not unknown_args:
            print("❌ Error: Please provide scheduler name and task/recipe")
            print("\nUsage:")
            print('  praisonai schedule start <name> "Your task" --interval hourly')
            print('  praisonai schedule start <name> --recipe <recipe-name> --interval hourly')
            print("\nExample:")
            print('  praisonai schedule start news-checker "Check AI news" --interval hourly')
            print('  praisonai schedule start news-checker --recipe news-monitor --interval hourly')
            return 1
        
        # Parse arguments
        name = unknown_args[0]
        
        # Check for --recipe flag in unknown_args
        recipe_name = None
        task = None
        if "--recipe" in unknown_args:
            recipe_idx = unknown_args.index("--recipe")
            if recipe_idx + 1 < len(unknown_args):
                recipe_name = unknown_args[recipe_idx + 1]
        else:
            task = unknown_args[1] if len(unknown_args) > 1 else None
        
        if not task and not recipe_name:
            print("❌ Error: Please provide a task or --recipe <name>")
            return 1
        
        # Get options
        interval = getattr(args, 'schedule_interval', None) or 'hourly'
        max_retries = getattr(args, 'schedule_max_retries', None) or 3
        timeout = getattr(args, 'timeout', None)
        max_cost = getattr(args, 'max_cost', None)
        
        # Check if name already exists
        existing = state_manager.load_state(name)
        if existing and daemon_manager.get_status(existing.get('pid', 0))['is_alive']:
            print(f"❌ Error: Scheduler '{name}' is already running (PID: {existing['pid']})")
            print(f"   Use 'praisonai schedule stop {name}' to stop it first")
            return 1
        
        # Start daemon
        print(f"🚀 Starting scheduler '{name}'...")
        if recipe_name:
            print(f"   Recipe: {recipe_name}")
        else:
            print(f"   Task: {task}")
        print(f"   Interval: {interval}")
        if timeout:
            print(f"   Timeout: {timeout}s")
        if max_cost:
            print(f"   Budget: ${max_cost}")
        
        pid = daemon_manager.start_scheduler_daemon(
            name=name,
            task=task,
            recipe_name=recipe_name,
            interval=interval,
            max_cost=max_cost,
            timeout=timeout,
            max_retries=max_retries
        )
        
        # Save state
        state = {
            "name": name,
            "pid": pid,
            "task": task,
            "recipe_name": recipe_name,
            "interval": interval,
            "timeout": timeout,
            "max_cost": max_cost,
            "max_retries": max_retries,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "executions": 0,
            "cost": 0.0
        }
        state_manager.save_state(name, state)
        
        print(f"\n✅ Scheduler '{name}' started successfully!")
        print(f"   PID: {pid}")
        print(f"   Logs: ~/.praisonai/logs/{name}.log")
        print(f"\nManage:")
        print(f"   praisonai schedule list")
        print(f"   praisonai schedule describe {name}")
        print(f"   praisonai schedule logs {name} --follow")
        print(f"   praisonai schedule stop {name}")
        
        return 0
    
    @staticmethod
    def _handle_list(state_manager) -> int:
        """Handle 'schedule list' command."""
        states = state_manager.list_all()
        
        if not states:
            print("No schedulers running.")
            print("\nStart one with:")
            print('  praisonai schedule start <name> "Your task" --interval hourly')
            return 0
        
        # Clean up dead processes
        state_manager.cleanup_dead_processes()
        states = state_manager.list_all()
        
        # Display table
        print(f"\n{'Name':<20} {'Status':<10} {'PID':<8} {'Interval':<12} {'Task':<40}")
        print("=" * 90)
        
        for state in states:
            name = state.get('name', 'unknown')[:20]
            pid = state.get('pid', 0)
            status = "running" if state_manager.is_process_alive(pid) else "stopped"
            interval = state.get('interval', 'unknown')[:12]
            task = state.get('task', '')[:40]
            
            status_icon = "🟢" if status == "running" else "🔴"
            print(f"{name:<20} {status_icon} {status:<8} {pid:<8} {interval:<12} {task:<40}")
        
        print(f"\nTotal: {len(states)} scheduler(s)")
        return 0
    
    @staticmethod
    def _handle_stats(state_manager, unknown_args=None, daemon_manager=None) -> int:
        """Handle 'schedule stats' command - show aggregate or individual statistics."""
        # If a name is provided, show individual stats (alias for describe)
        if unknown_args and len(unknown_args) > 0:
            name = unknown_args[0]
            return AgentSchedulerHandler._handle_describe([name], state_manager, daemon_manager)
        
        # Otherwise show aggregate stats
        states = state_manager.list_all()
        
        if not states:
            print("No schedulers found.")
            print("\nStart one with:")
            print('  praisonai schedule start <name> "Your task" --interval hourly')
            return 0
        
        # Calculate aggregate stats
        total_schedulers = len(states)
        running = sum(1 for s in states if s.get('status') == 'running')
        stopped = total_schedulers - running
        total_executions = sum(s.get('executions', 0) for s in states)
        total_cost = sum(s.get('cost', 0.0) for s in states)
        
        print(f"\n{'='*60}")
        print(f"📊 Aggregate Scheduler Statistics")
        print(f"{'='*60}")
        print(f"Total Schedulers:     {total_schedulers}")
        print(f"  🟢 Running:         {running}")
        print(f"  🔴 Stopped:         {stopped}")
        print(f"\nTotal Executions:     {total_executions}")
        print(f"Total Cost:           ${total_cost:.4f}")
        
        if total_executions > 0:
            avg_cost = total_cost / total_executions
            print(f"Avg Cost/Execution:   ${avg_cost:.4f}")
        
        print(f"{'='*60}\n")
        
        # Show per-scheduler breakdown
        print("Per-Scheduler Breakdown:")
        print(f"{'Name':<20} {'Status':<10} {'Executions':<12} {'Cost':<12}")
        print("="*60)
        
        for state in sorted(states, key=lambda x: x.get('executions', 0), reverse=True):
            name = state['name'][:20]
            status = state.get('status', 'unknown')
            executions = state.get('executions', 0)
            cost = state.get('cost', 0.0)
            
            status_icon = "🟢" if status == "running" else "🔴"
            print(f"{name:<20} {status_icon} {status:<8} {executions:<12} ${cost:<11.4f}")
        
        return 0
    
    @staticmethod
    def _handle_stop_all(state_manager, daemon_manager) -> int:
        """Handle 'schedule stop-all' command."""
        states = state_manager.list_all()
        
        if not states:
            print("No schedulers running.")
            return 0
        
        print(f"\n🛑 Stopping all schedulers ({len(states)} total)...\n")
        
        stopped = 0
        failed = 0
        
        for state in states:
            name = state['name']
            pid = state['pid']
            
            try:
                if daemon_manager.stop_daemon(pid):
                    state_manager.delete_state(name)
                    print(f"✅ Stopped '{name}' (PID: {pid})")
                    stopped += 1
                else:
                    print(f"❌ Failed to stop '{name}' (PID: {pid})")
                    failed += 1
            except Exception as e:
                print(f"❌ Error stopping '{name}': {e}")
                failed += 1
        
        print(f"\n📊 Summary: {stopped} stopped, {failed} failed")
        return 0 if failed == 0 else 1
    
    @staticmethod
    def _handle_stop(unknown_args, state_manager, daemon_manager) -> int:
        """Handle 'schedule stop' command."""
        if not unknown_args:
            print("❌ Error: Please provide scheduler name")
            print("\nUsage: praisonai schedule stop <name>")
            return 1
        
        name = unknown_args[0]
        state = state_manager.load_state(name)
        
        if not state:
            print(f"❌ Error: Scheduler '{name}' not found")
            print("\nList schedulers with: praisonai schedule list")
            return 1
        
        pid = state.get('pid')
        if not pid:
            print(f"❌ Error: No PID found for scheduler '{name}'")
            return 1
        
        print(f"🛑 Stopping scheduler '{name}' (PID: {pid})...")
        
        success = daemon_manager.stop_daemon(pid)
        
        if success:
            state['status'] = 'stopped'
            state_manager.save_state(name, state)
            print(f"✅ Scheduler '{name}' stopped successfully")
            return 0
        else:
            print(f"❌ Failed to stop scheduler '{name}'")
            return 1
    
    @staticmethod
    def _handle_logs(unknown_args, daemon_manager) -> int:
        """Handle 'schedule logs' command."""
        if not unknown_args:
            print("❌ Error: Please provide scheduler name")
            print("\nUsage: praisonai schedule logs <name> [-f]")
            return 1
        
        name = unknown_args[0]
        follow = '-f' in unknown_args or '--follow' in unknown_args
        
        if follow:
            print(f"📋 Following logs for '{name}' (Ctrl+C to stop)...")
            import subprocess
            log_file = daemon_manager.log_dir / f"{name}.log"
            if not log_file.exists():
                print(f"❌ Error: Log file not found for '{name}'")
                return 1
            
            try:
                subprocess.run(['tail', '-f', str(log_file)])
            except KeyboardInterrupt:
                print("\n✅ Stopped following logs")
            return 0
        else:
            logs = daemon_manager.read_logs(name, lines=50)
            if logs:
                print(f"📋 Last 50 lines of logs for '{name}':\n")
                print(logs)
                return 0
            else:
                print(f"❌ Error: No logs found for '{name}'")
                return 1
    
    @staticmethod
    def _handle_restart(unknown_args, state_manager, daemon_manager) -> int:
        """Handle 'schedule restart' command."""
        from datetime import datetime
        import time
        
        if not unknown_args:
            print("❌ Error: Please provide scheduler name")
            print("\nUsage: praisonai schedule restart <name>")
            return 1
        
        name = unknown_args[0]
        state = state_manager.load_state(name)
        
        if not state:
            print(f"❌ Error: Scheduler '{name}' not found")
            return 1
        
        print(f"🔄 Restarting scheduler '{name}'...")
        
        # Stop if running
        pid = state.get('pid')
        if pid and state_manager.is_process_alive(pid):
            daemon_manager.stop_daemon(pid)
            time.sleep(1)
        
        # Start again
        new_pid = daemon_manager.start_scheduler_daemon(
            name=name,
            task=state['task'],
            interval=state['interval'],
            max_cost=state.get('max_cost'),
            timeout=state.get('timeout'),
            max_retries=state.get('max_retries', 3)
        )
        
        state['pid'] = new_pid
        state['status'] = 'running'
        state['started_at'] = datetime.now().isoformat()
        state_manager.save_state(name, state)
        
        print(f"✅ Scheduler '{name}' restarted (PID: {new_pid})")
        return 0
    
    @staticmethod
    def _handle_delete(unknown_args, state_manager) -> int:
        """Handle 'schedule delete' command."""
        if not unknown_args:
            print("❌ Error: Please provide scheduler name")
            print("\nUsage: praisonai schedule delete <name>")
            return 1
        
        name = unknown_args[0]
        
        if state_manager.delete_state(name):
            print(f"✅ Scheduler '{name}' deleted from list")
            return 0
        else:
            print(f"❌ Error: Scheduler '{name}' not found")
            return 1
    
    @staticmethod
    def _handle_describe(unknown_args, state_manager, daemon_manager) -> int:
        """Handle 'schedule describe' command."""
        from datetime import datetime
        
        if not unknown_args:
            print("❌ Error: Please provide scheduler name")
            print("\nUsage: praisonai schedule describe <name>")
            return 1
        
        name = unknown_args[0]
        state = state_manager.load_state(name)
        
        if not state:
            print(f"❌ Error: Scheduler '{name}' not found")
            print("\nList schedulers with: praisonai schedule list")
            return 1
        
        # Get process status
        pid = state.get('pid', 0)
        is_alive = state_manager.is_process_alive(pid)
        status = "🟢 running" if is_alive else "🔴 stopped"
        
        # Calculate uptime
        started_at = state.get('started_at')
        uptime = "N/A"
        if started_at:
            try:
                start_time = datetime.fromisoformat(started_at)
                uptime_delta = datetime.now() - start_time
                hours = int(uptime_delta.total_seconds() // 3600)
                minutes = int((uptime_delta.total_seconds() % 3600) // 60)
                uptime = f"{hours}h {minutes}m"
            except:
                pass
        
        # Display detailed info
        print(f"\n{'='*60}")
        print(f"📋 Scheduler Details: {name}")
        print(f"{'='*60}")
        print(f"Status:       {status}")
        print(f"PID:          {pid}")
        print(f"Uptime:       {uptime}")
        print(f"Task:         {state.get('task', 'N/A')}")
        print(f"Interval:     {state.get('interval', 'N/A')}")
        print(f"Max Retries:  {state.get('max_retries', 'N/A')}")
        
        if state.get('timeout'):
            print(f"Timeout:      {state['timeout']}s")
        
        if state.get('max_cost'):
            print(f"Budget:       ${state['max_cost']}")
        
        print(f"Executions:   {state.get('executions', 0)}")
        print(f"Total Cost:   ${state.get('cost', 0.0):.4f}")
        print(f"Started:      {started_at or 'N/A'}")
        
        # Log file location
        log_file = daemon_manager.log_dir / f"{name}.log"
        print(f"Logs:         {log_file}")
        
        print(f"{'='*60}\n")
        
        return 0
    
    @staticmethod
    def _handle_save(unknown_args, state_manager) -> int:
        """Handle 'schedule save' command."""
        import yaml
        
        if not unknown_args:
            print("❌ Error: Please provide scheduler name")
            print("\nUsage: praisonai schedule save <name> [output.yaml]")
            return 1
        
        name = unknown_args[0]
        output_file = unknown_args[1] if len(unknown_args) > 1 else f"{name}.yaml"
        
        state = state_manager.load_state(name)
        
        if not state:
            print(f"❌ Error: Scheduler '{name}' not found")
            return 1
        
        # Create YAML config from state
        yaml_config = {
            'framework': 'praisonai',
            'agents': [{
                'name': name,
                'role': 'Task Executor',
                'goal': state.get('task', ''),
                'instructions': state.get('task', ''),
                'verbose': True
            }],
            'task': state.get('task', ''),
            'schedule': {
                'interval': state.get('interval', 'hourly'),
                'max_retries': state.get('max_retries', 3),
                'run_immediately': True
            }
        }
        
        # Add optional fields
        if state.get('timeout'):
            yaml_config['schedule']['timeout'] = state['timeout']
        
        if state.get('max_cost'):
            yaml_config['schedule']['max_cost'] = state['max_cost']
        
        # Write to file
        try:
            with open(output_file, 'w') as f:
                yaml.dump(yaml_config, f, default_flow_style=False, sort_keys=False)
            
            print(f"✅ Configuration saved to: {output_file}")
            print(f"\nRun with:")
            print(f"  praisonai schedule {output_file}")
            return 0
        except Exception as e:
            print(f"❌ Error saving configuration: {e}")
            return 1
    
    @staticmethod
    def handle_schedule_command(args, unknown_args, daemon_mode=False) -> int:
        """
        Handle the schedule command for running agents periodically.
        
        Supports two modes:
        1. YAML mode: praisonai schedule agents.yaml
        2. Prompt mode: praisonai schedule "Your task here" --interval hourly
        
        Args:
            args: Parsed command-line arguments
            unknown_args: Additional arguments after the command
            
        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            from praisonai.scheduler import AgentScheduler
            from praisonaiagents import Agent
        except ImportError:
            print("Error: praisonai.scheduler or praisonaiagents module not found")
            print("Please ensure PraisonAI is properly installed")
            print("pip install praisonai praisonaiagents")
            return 1
        
        # Check if first arg is a YAML file or a prompt
        first_arg = unknown_args[0] if unknown_args else None
        is_yaml_mode = first_arg and (first_arg.endswith('.yaml') or first_arg.endswith('.yml'))
        
        # Get overrides from CLI
        interval_override = getattr(args, 'schedule_interval', None) or 'hourly'
        max_retries_override = getattr(args, 'schedule_max_retries', None) or 3
        timeout_override = getattr(args, 'timeout', None)
        max_cost_override = getattr(args, 'max_cost', None)
        verbose = getattr(args, 'verbose', False)
        
        # Set up logging - only show logs if verbose
        if verbose:
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            # Suppress scheduler logs in non-verbose mode
            logging.getLogger('praisonai.scheduler').setLevel(logging.WARNING)
        
        try:
            # Check if this is a recipe name (not a file, not a prompt with spaces)
            is_recipe_mode = False
            if first_arg and not is_yaml_mode:
                # Try to resolve as recipe if it looks like a recipe name (no spaces, no file extension)
                if ' ' not in first_arg and not first_arg.endswith('.yaml') and not first_arg.endswith('.yml'):
                    try:
                        from praisonai.recipe.bridge import resolve
                        resolve(first_arg)  # Just check if it resolves
                        is_recipe_mode = True
                    except Exception:
                        pass  # Not a recipe, continue with prompt mode
            
            if is_yaml_mode:
                # YAML mode: Load from agents.yaml
                yaml_path = first_arg
                print(f"🤖 Loading agent configuration from: {yaml_path}")
                scheduler = AgentScheduler.from_yaml(
                    yaml_path=yaml_path,
                    interval_override=interval_override,
                    max_retries_override=max_retries_override,
                    timeout_override=timeout_override,
                    max_cost_override=max_cost_override
                )
            elif is_recipe_mode:
                # Recipe mode: Load from recipe name
                print(f"🍳 Loading recipe: {first_arg}")
                scheduler = AgentScheduler.from_recipe(
                    recipe_name=first_arg,
                    interval_override=interval_override,
                    max_retries_override=max_retries_override,
                    timeout_override=timeout_override,
                    max_cost_override=max_cost_override
                )
            else:
                # Prompt mode: Create agent from direct prompt
                if not first_arg:
                    print("❌ Error: Please provide either a YAML file, recipe name, or a task prompt")
                    print("\nExamples:")
                    print("  praisonai schedule agents.yaml")
                    print("  praisonai schedule my-recipe --interval hourly")
                    print('  praisonai schedule "Check news every hour" --interval hourly')
                    return 1
                
                task = first_arg
                
                # Create agent
                agent = Agent(
                    name="Scheduled Agent",
                    role="Task Executor",
                    goal=task,
                    instructions=task,
                    verbose=True  # Enable verbose to see output in logs
                )
                
                # Create scheduler
                scheduler = AgentScheduler(
                    agent=agent,
                    task=task,
                    timeout=timeout_override,
                    max_cost=max_cost_override
                )
            
            # Get configuration
            interval = interval_override
            max_retries = max_retries_override
            
            if is_yaml_mode:
                schedule_config = scheduler._yaml_schedule_config
                interval = interval_override or schedule_config.get('interval', 'hourly')
                max_retries = max_retries_override or schedule_config.get('max_retries', 3)
            
            print(f"Schedule: {interval}")
            print(f"Max Retries: {max_retries}")
            if scheduler.timeout:
                print(f"Timeout: {scheduler.timeout}s")
            if scheduler.max_cost:
                print(f"Budget: ${scheduler.max_cost}")
            print(f"{'='*60}\n")
            
            # Start scheduler
            if is_yaml_mode:
                scheduler.start_from_yaml_config()
            else:
                scheduler.start(schedule_expr=interval, max_retries=max_retries, run_immediately=True)
            
            # If daemon mode, block to keep process alive
            if daemon_mode:
                import time
                try:
                    while scheduler.is_running:
                        time.sleep(1)
                except KeyboardInterrupt:
                    scheduler.stop()
            else:
                # Foreground mode - wait for Ctrl+C
                print("⏰ Starting scheduler... (Press Ctrl+C to stop)\n")
                import time
                try:
                    while scheduler.is_running:
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
