#!/usr/bin/env python3
"""
Test script to demonstrate PraisonAI logging capabilities.

This script shows how to:
1. Enable debug logging
2. View agent activities
3. Track task execution
4. Monitor tool usage

Usage:
    # Default logging (INFO level)
    python test_logging.py
    
    # Debug logging
    LOGLEVEL=DEBUG python test_logging.py
    
    # Only errors
    LOGLEVEL=ERROR python test_logging.py
"""

import os
import sys
import logging
from rich.logging import RichHandler
from rich.console import Console
from rich.panel import Panel

console = Console()

# Check if praisonaiagents is installed
try:
    from praisonaiagents import Agent, Task, PraisonAIAgents
    from praisonaiagents.tools import DuckDuckGoSearchTool
except ImportError:
    console.print(Panel(
        "[red]Error: praisonaiagents is not installed![/red]\n\n"
        "Please install it with:\n"
        "[yellow]pip install praisonaiagents[/yellow]",
        title="Installation Required"
    ))
    sys.exit(1)

def setup_logging(level="INFO"):
    """Configure logging with Rich handler."""
    # Get log level from environment or parameter
    log_level = os.environ.get('LOGLEVEL', level).upper()
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    # Return the configured level for display
    return log_level

def main():
    """Main function to demonstrate logging."""
    # Setup logging
    log_level = setup_logging()
    
    console.print(Panel(
        f"[green]PraisonAI Logging Test[/green]\n\n"
        f"Current Log Level: [yellow]{log_level}[/yellow]\n"
        f"To change, set LOGLEVEL environment variable:\n"
        f"  [cyan]export LOGLEVEL=DEBUG[/cyan]",
        title="Logging Configuration"
    ))
    
    # Create logger for this module
    logger = logging.getLogger(__name__)
    
    # Log at different levels to show what's visible
    logger.debug("This is a DEBUG message - detailed information")
    logger.info("This is an INFO message - general information")
    logger.warning("This is a WARNING message - something to pay attention to")
    logger.error("This is an ERROR message - something went wrong")
    
    console.print("\n[yellow]Creating agents and tasks...[/yellow]\n")
    
    # Create a simple agent with self-reflection
    researcher = Agent(
        name="LogTestAgent",
        role="Logging Demonstrator",
        goal="Demonstrate logging capabilities",
        backstory="You are an agent created to show how logging works in PraisonAI",
        llm="gpt-4o-mini",  # Using a smaller model for testing
        self_reflect=True,
        min_reflect=1,
        max_reflect=2,
        tools=[DuckDuckGoSearchTool()],
        verbose=True
    )
    
    # Create a simple task
    demo_task = Task(
        name="logging_demo",
        description="Search for 'Python logging best practices' and summarize in 2-3 sentences",
        expected_output="A brief summary of Python logging best practices",
        agent=researcher
    )
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=[researcher],
        tasks=[demo_task],
        verbose=True
    )
    
    console.print("\n[green]Starting agent workflow...[/green]\n")
    console.print("[dim]Watch the logs to see agent activities, tool usage, and self-reflection[/dim]\n")
    
    # Run the workflow
    try:
        result = workflow.start()
        
        console.print(Panel(
            f"[green]Task completed successfully![/green]\n\n"
            f"Result: {result}",
            title="Workflow Result"
        ))
        
        # Show how to access error logs
        from praisonaiagents.main import error_logs
        if error_logs:
            console.print(Panel(
                f"[red]Errors encountered during execution:[/red]\n" +
                "\n".join(f"- {error}" for error in error_logs),
                title="Error Logs"
            ))
        else:
            console.print("\n[green]No errors logged during execution[/green]")
            
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        console.print(f"\n[red]Error: {e}[/red]")
    
    # Demonstrate module-specific logging
    console.print(Panel(
        "[yellow]Tip: Enable module-specific debugging[/yellow]\n\n"
        "Add this to your code:\n"
        "[cyan]logging.getLogger('praisonaiagents.agent').setLevel(logging.DEBUG)[/cyan]\n"
        "[cyan]logging.getLogger('praisonaiagents.task').setLevel(logging.DEBUG)[/cyan]",
        title="Advanced Logging"
    ))

if __name__ == "__main__":
    main()