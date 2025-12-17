"""
Workflow Handler for CLI.

Provides YAML workflow management commands.
Usage: praisonai workflow run research.yaml
       praisonai workflow validate research.yaml
       praisonai workflow list
       praisonai workflow create --template routing
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base import CommandHandler


class WorkflowHandler(CommandHandler):
    """
    Handler for workflow command.
    
    Manages YAML workflow files - run, validate, list, and create from templates.
    
    Example:
        praisonai workflow run research.yaml --var topic="AI"
        praisonai workflow validate research.yaml
        praisonai workflow list
        praisonai workflow create --template routing --output my_workflow.yaml
    """
    
    # Workflow templates
    TEMPLATES = {
        "simple": """# Simple Sequential Workflow
name: Simple Workflow
description: A simple sequential workflow

workflow:
  verbose: true

agents:
  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics
    instructions: "Provide concise, factual information."

  writer:
    name: Writer
    role: Content Writer
    goal: Write content
    instructions: "Write clear, engaging content."

steps:
  - agent: researcher
    action: "Research: {{input}}"
    
  - agent: writer
    action: "Write summary based on: {{previous_output}}"
""",
        "routing": """# Routing Workflow
name: Routing Workflow
description: Classifier routes to specialized agents

workflow:
  verbose: true

agents:
  classifier:
    name: Classifier
    role: Request Classifier
    goal: Classify requests
    instructions: "Respond with ONLY 'technical', 'creative', or 'general'."

  tech_agent:
    name: TechExpert
    role: Technical Expert
    goal: Handle technical questions
    instructions: "Provide technical answers."

  creative_agent:
    name: Creative
    role: Creative Writer
    goal: Handle creative requests
    instructions: "Write creative content."

  general_agent:
    name: General
    role: General Assistant
    goal: Handle general requests
    instructions: "Provide helpful responses."

steps:
  - agent: classifier
    action: "Classify: {{input}}"
    
  - name: routing
    route:
      technical: [tech_agent]
      creative: [creative_agent]
      default: [general_agent]
""",
        "parallel": """# Parallel Workflow
name: Parallel Research Workflow
description: Multiple agents work concurrently

workflow:
  verbose: true

agents:
  researcher1:
    name: MarketResearcher
    role: Market Analyst
    goal: Research market trends
    instructions: "Provide market insights."

  researcher2:
    name: CompetitorResearcher
    role: Competitor Analyst
    goal: Research competitors
    instructions: "Provide competitor insights."

  aggregator:
    name: Aggregator
    role: Synthesizer
    goal: Combine findings
    instructions: "Synthesize all research."

steps:
  - name: parallel_research
    parallel:
      - agent: researcher1
        action: "Research market for: {{input}}"
      - agent: researcher2
        action: "Research competitors for: {{input}}"
        
  - agent: aggregator
    action: "Combine all findings"
""",
        "loop": """# Loop Workflow
name: Loop Processing Workflow
description: Process multiple items in a loop

workflow:
  verbose: true

variables:
  items:
    - Item 1
    - Item 2
    - Item 3

agents:
  processor:
    name: Processor
    role: Item Processor
    goal: Process each item
    instructions: "Process the given item thoroughly."

  summarizer:
    name: Summarizer
    role: Summarizer
    goal: Summarize results
    instructions: "Summarize all processed items."

steps:
  - agent: processor
    action: "Process: {{item}}"
    loop:
      over: items
      
  - agent: summarizer
    action: "Summarize all processed items"
""",
        "evaluator-optimizer": """# Evaluator-Optimizer Workflow
name: Evaluator Optimizer Workflow
description: Generate and improve until approved

workflow:
  verbose: true

agents:
  generator:
    name: Generator
    role: Content Generator
    goal: Generate content
    instructions: "Generate content. Improve based on feedback if provided."

  evaluator:
    name: Evaluator
    role: Evaluator
    goal: Evaluate content
    instructions: "If good, respond 'APPROVED'. Otherwise provide feedback."

steps:
  - agent: generator
    action: "Generate content for: {{input}}"
    
  - agent: evaluator
    action: "Evaluate: {{previous_output}}"
    repeat:
      until: "approved"
      max_iterations: 3
"""
    }
    
    def __init__(self, verbose: bool = False):
        super().__init__(verbose)
        self._manager = None
        self._parser = None
    
    @property
    def feature_name(self) -> str:
        return "workflow"
    
    def get_actions(self) -> List[str]:
        return ["run", "validate", "list", "create", "help"]
    
    def get_help_text(self) -> str:
        return """
Workflow Commands:
  praisonai workflow run <file.yaml>           - Run a YAML workflow
  praisonai workflow run <file.yaml> --var key=value  - Run with variables
  praisonai workflow validate <file.yaml>      - Validate a YAML workflow
  praisonai workflow list                      - List workflows in .praison/workflows/
  praisonai workflow create --template <name>  - Create from template
  
Templates: simple, routing, parallel, loop, evaluator-optimizer

Example:
  praisonai workflow run research.yaml --var topic="AI trends"
  praisonai workflow create --template routing --output my_workflow.yaml
"""
    
    def _get_manager(self):
        """Get WorkflowManager lazily."""
        if self._manager is None:
            try:
                from praisonaiagents.workflows import WorkflowManager
                self._manager = WorkflowManager()
            except ImportError:
                self.print_status(
                    "Workflows require praisonaiagents. Install with: pip install praisonaiagents",
                    "error"
                )
                return None
        return self._manager
    
    def _get_parser(self):
        """Get YAMLWorkflowParser lazily."""
        if self._parser is None:
            try:
                from praisonaiagents.workflows import YAMLWorkflowParser
                self._parser = YAMLWorkflowParser()
            except ImportError:
                self.print_status(
                    "Workflows require praisonaiagents. Install with: pip install praisonaiagents",
                    "error"
                )
                return None
        return self._parser
    
    def _parse_variables(self, args: List[str]) -> Dict[str, Any]:
        """Parse --var key=value arguments."""
        variables = {}
        i = 0
        while i < len(args):
            if args[i] == "--var" and i + 1 < len(args):
                var_str = args[i + 1]
                if "=" in var_str:
                    key, value = var_str.split("=", 1)
                    variables[key.strip()] = value.strip()
                i += 2
            else:
                i += 1
        return variables
    
    def _get_file_from_args(self, args: List[str]) -> Optional[str]:
        """Get the file path from arguments."""
        for arg in args:
            if arg.endswith(('.yaml', '.yml')) and not arg.startswith('--'):
                return arg
        return None
    
    def action_run(self, args: List[str], **kwargs) -> Any:
        """
        Run a YAML workflow file.
        
        Args:
            args: [file.yaml, --var, key=value, ...]
            
        Returns:
            Workflow execution result
        """
        file_path = self._get_file_from_args(args)
        if not file_path:
            self.print_status("Usage: praisonai workflow run <file.yaml>", "error")
            return None
        
        if not os.path.exists(file_path):
            self.print_status(f"File not found: {file_path}", "error")
            return None
        
        manager = self._get_manager()
        if not manager:
            return None
        
        # Parse variables
        variables = self._parse_variables(args)
        
        # Get input if provided
        input_data = kwargs.get('input', '')
        
        # Check for --verbose flag
        verbose = '--verbose' in args or '-v' in args
        
        self.print_status(f"Running workflow: {file_path}", "info")
        if variables:
            self.print_status(f"Variables: {variables}", "info")
        
        try:
            result = manager.execute_yaml(
                file_path,
                input_data=input_data,
                variables=variables,
                verbose=verbose
            )
            
            self.print_status("Workflow completed!", "success")
            
            # Print output
            if result.get('output'):
                from rich import print as rprint
                rprint("\n[bold]Output:[/bold]")
                rprint(result['output'])
            
            return result
            
        except Exception as e:
            self.print_status(f"Workflow failed: {e}", "error")
            return None
    
    def action_validate(self, args: List[str], **kwargs) -> bool:
        """
        Validate a YAML workflow file.
        
        Args:
            args: [file.yaml]
            
        Returns:
            True if valid, False otherwise
        """
        file_path = self._get_file_from_args(args)
        if not file_path:
            self.print_status("Usage: praisonai workflow validate <file.yaml>", "error")
            return False
        
        if not os.path.exists(file_path):
            self.print_status(f"File not found: {file_path}", "error")
            return False
        
        parser = self._get_parser()
        if not parser:
            return False
        
        self.print_status(f"Validating: {file_path}", "info")
        
        try:
            workflow = parser.parse_file(file_path)
            
            # Print validation results
            from rich import print as rprint
            from rich.table import Table
            
            table = Table(title="Workflow Validation")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Name", workflow.name)
            table.add_row("Description", getattr(workflow, 'description', 'N/A'))
            table.add_row("Steps", str(len(workflow.steps)))
            table.add_row("Variables", str(len(workflow.variables)))
            table.add_row("Planning", str(workflow.planning))
            table.add_row("Reasoning", str(workflow.reasoning))
            
            rprint(table)
            self.print_status("✓ Workflow is valid!", "success")
            return True
            
        except Exception as e:
            self.print_status(f"✗ Validation failed: {e}", "error")
            return False
    
    def action_list(self, args: List[str], **kwargs) -> List[str]:
        """
        List available workflows in .praison/workflows/ directory.
        
        Returns:
            List of workflow file names
        """
        workflows_dir = Path(".praison/workflows")
        
        if not workflows_dir.exists():
            self.print_status("No .praison/workflows/ directory found", "warning")
            self.print_status("Create one with: mkdir -p .praison/workflows", "info")
            return []
        
        # Find all YAML files
        yaml_files = list(workflows_dir.glob("*.yaml")) + list(workflows_dir.glob("*.yml"))
        
        if not yaml_files:
            self.print_status("No workflow files found in .praison/workflows/", "warning")
            return []
        
        from rich import print as rprint
        from rich.table import Table
        
        table = Table(title="Available Workflows")
        table.add_column("File", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Steps", style="yellow")
        
        parser = self._get_parser()
        workflow_names = []
        
        for yaml_file in yaml_files:
            try:
                if parser:
                    workflow = parser.parse_file(yaml_file)
                    table.add_row(
                        yaml_file.name,
                        workflow.name,
                        str(len(workflow.steps))
                    )
                else:
                    table.add_row(yaml_file.name, "N/A", "N/A")
                workflow_names.append(yaml_file.name)
            except Exception as e:
                table.add_row(yaml_file.name, f"Error: {e}", "N/A")
        
        rprint(table)
        return workflow_names
    
    def action_create(self, args: List[str], **kwargs) -> Optional[str]:
        """
        Create a workflow from a template.
        
        Args:
            args: [--template, <name>, --output, <file.yaml>]
            
        Returns:
            Path to created file
        """
        # Parse arguments
        template_name = None
        output_file = None
        
        i = 0
        while i < len(args):
            if args[i] == "--template" and i + 1 < len(args):
                template_name = args[i + 1]
                i += 2
            elif args[i] == "--output" and i + 1 < len(args):
                output_file = args[i + 1]
                i += 2
            else:
                i += 1
        
        if not template_name:
            self.print_status("Usage: praisonai workflow create --template <name>", "error")
            self.print_status(f"Available templates: {', '.join(self.TEMPLATES.keys())}", "info")
            return None
        
        if template_name not in self.TEMPLATES:
            self.print_status(f"Unknown template: {template_name}", "error")
            self.print_status(f"Available templates: {', '.join(self.TEMPLATES.keys())}", "info")
            return None
        
        # Default output file
        if not output_file:
            output_file = f"{template_name}_workflow.yaml"
        
        # Check if file exists
        if os.path.exists(output_file):
            self.print_status(f"File already exists: {output_file}", "error")
            return None
        
        # Write template
        template_content = self.TEMPLATES[template_name]
        
        with open(output_file, 'w') as f:
            f.write(template_content)
        
        self.print_status(f"✓ Created workflow: {output_file}", "success")
        self.print_status(f"Run with: praisonai workflow run {output_file}", "info")
        
        return output_file
