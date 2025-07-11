#!/usr/bin/env python3
"""
Example showing how to configure PraisonAI logging programmatically.

This demonstrates:
- Setting log levels in code (without environment variables)
- Module-specific logging configuration
- Custom log formatting
- Writing logs to files
"""

import logging
import os
from datetime import datetime
from rich.logging import RichHandler
from rich.console import Console

# Check if praisonaiagents is installed
try:
    from praisonaiagents import Agent, Task, PraisonAIAgents
except ImportError:
    print("Error: praisonaiagents is not installed!")
    print("Install with: pip install praisonaiagents")
    exit(1)

console = Console()

def configure_logging():
    """Configure comprehensive logging for PraisonAI."""
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with Rich
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_level=True
    )
    console_handler.setLevel(logging.INFO)
    
    # File handler for all logs
    all_logs_handler = logging.FileHandler(
        f'logs/praisonai_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    )
    all_logs_handler.setLevel(logging.DEBUG)
    all_logs_handler.setFormatter(file_formatter)
    
    # Error file handler
    error_handler = logging.FileHandler(
        f'logs/praisonai_errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(all_logs_handler)
    root_logger.addHandler(error_handler)
    
    # Configure module-specific logging
    modules_config = {
        'praisonaiagents': logging.DEBUG,
        'praisonaiagents.agent': logging.DEBUG,
        'praisonaiagents.task': logging.DEBUG,
        'praisonaiagents.tools': logging.INFO,
        'praisonaiagents.llm': logging.INFO,
        'praisonaiagents.memory': logging.WARNING,
        'praisonaiagents.telemetry': logging.WARNING,
    }
    
    for module, level in modules_config.items():
        logger = logging.getLogger(module)
        logger.setLevel(level)
    
    # Suppress noisy third-party loggers
    for logger_name in ['litellm', 'litellm.utils', 'chromadb', 'markdown_it']:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    console.print("[green]Logging configured successfully![/green]")
    console.print(f"[yellow]Log files will be saved in:[/yellow] logs/")
    console.print(f"[cyan]Console log level:[/cyan] INFO")
    console.print(f"[cyan]File log level:[/cyan] DEBUG\n")

def create_demo_agents():
    """Create agents for demonstration."""
    
    # Create a researcher agent
    researcher = Agent(
        name="Researcher",
        role="Information Gatherer",
        goal="Research and collect information",
        backstory="You are an expert researcher skilled at finding relevant information",
        llm="gpt-4o-mini",
        self_reflect=True,
        verbose=True
    )
    
    # Create a writer agent
    writer = Agent(
        name="Writer",
        role="Content Creator",
        goal="Transform research into clear, concise content",
        backstory="You are a skilled writer who creates engaging content",
        llm="gpt-4o-mini",
        verbose=True
    )
    
    return researcher, writer

def create_demo_tasks(researcher, writer):
    """Create tasks for demonstration."""
    
    research_task = Task(
        name="research_task",
        description="Research the topic of 'AI agent logging and monitoring'",
        expected_output="Key points about AI agent logging and monitoring",
        agent=researcher
    )
    
    writing_task = Task(
        name="writing_task",
        description="Create a brief summary based on the research",
        expected_output="A concise summary of AI agent logging best practices",
        agent=writer,
        context=[research_task]
    )
    
    return research_task, writing_task

def main():
    """Main demonstration function."""
    console.print("[bold blue]PraisonAI Programmatic Logging Example[/bold blue]\n")
    
    # Configure logging
    configure_logging()
    
    # Create a logger for this module
    logger = logging.getLogger(__name__)
    
    # Log some test messages
    logger.debug("Starting PraisonAI workflow")
    logger.info("Creating agents and tasks")
    
    try:
        # Create agents and tasks
        researcher, writer = create_demo_agents()
        research_task, writing_task = create_demo_tasks(researcher, writer)
        
        # Create and run workflow
        workflow = PraisonAIAgents(
            agents=[researcher, writer],
            tasks=[research_task, writing_task],
            process="sequential",
            verbose=True
        )
        
        logger.info("Starting agent workflow")
        result = workflow.start()
        
        logger.info("Workflow completed successfully")
        console.print(f"\n[green]Result:[/green] {result}")
        
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        console.print(f"\n[red]Error:[/red] {e}")
    
    # Show log file locations
    console.print("\n[yellow]Check the log files for detailed information:[/yellow]")
    console.print("[cyan]- logs/praisonai_*.log[/cyan] - All logs")
    console.print("[cyan]- logs/praisonai_errors_*.log[/cyan] - Error logs only")

# Example of custom logging context manager
class LoggingContext:
    """Context manager for temporary log level changes."""
    
    def __init__(self, logger_name, level):
        self.logger = logging.getLogger(logger_name)
        self.original_level = self.logger.level
        self.temp_level = level
    
    def __enter__(self):
        self.logger.setLevel(self.temp_level)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.original_level)

# Example usage of custom context
def demonstrate_logging_context():
    """Show how to temporarily change log levels."""
    logger = logging.getLogger('praisonaiagents.llm')
    
    console.print("\n[yellow]Demonstrating temporary log level change:[/yellow]")
    
    # Normal logging
    logger.info("This is at normal log level")
    
    # Temporarily enable debug logging
    with LoggingContext('praisonaiagents.llm', logging.DEBUG):
        logger.debug("This debug message is visible due to context manager")
    
    # Back to normal
    logger.debug("This debug message won't be visible")

if __name__ == "__main__":
    main()
    demonstrate_logging_context()