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
""",
        "model-routing": """# Model Routing Workflow
name: Cost-Optimized Model Routing Workflow
description: Uses custom models with automatic routing based on task complexity

# Custom models configuration - define your own models with costs and capabilities
models:
  cheap-fast:
    provider: openai
    complexity: [simple]
    cost_per_1k: 0.0001
    capabilities: [text]
    context_window: 16000
  
  balanced:
    provider: openai
    complexity: [moderate]
    cost_per_1k: 0.001
    capabilities: [text, function-calling]
    context_window: 128000
  
  premium:
    provider: anthropic
    complexity: [complex, very_complex]
    cost_per_1k: 0.015
    capabilities: [text, vision, function-calling]
    context_window: 200000
    strengths: [reasoning, analysis, code-generation]

workflow:
  verbose: true
  router: true  # Enable model routing
  routing_strategy: cost-optimized  # Options: auto, cost-optimized, performance-optimized

agents:
  classifier:
    name: Classifier
    role: Request Classifier
    goal: Classify incoming requests by complexity
    instructions: "Classify the request as 'simple', 'moderate', or 'complex'."
    llm: cheap-fast  # Always use cheap model for classification

  researcher:
    name: Researcher
    role: Research Analyst
    goal: Research topics thoroughly
    instructions: "Research the topic and provide detailed findings."
    llm_routing: auto  # Auto-select based on task complexity
    llm_models: [balanced, premium]  # Models to choose from

  writer:
    name: Writer
    role: Content Writer
    goal: Write high-quality content
    instructions: "Write clear, engaging content based on research."
    llm: premium  # Always use premium for quality writing

steps:
  - agent: classifier
    action: "Classify complexity of: {{input}}"
    
  - name: routing
    route:
      simple: [researcher]
      moderate: [researcher]
      complex: [researcher, writer]
      default: [researcher]
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
        return ["run", "validate", "list", "create", "auto", "help"]
    
    def get_help_text(self) -> str:
        return """
Workflow Commands:
  praisonai workflow run <file.yaml>           - Run a YAML workflow
  praisonai workflow run <file.yaml> --var key=value  - Run with variables
  praisonai workflow validate <file.yaml>      - Validate a YAML workflow
  praisonai workflow list                      - List workflows in .praison/workflows/
  praisonai workflow create --template <name>  - Create from template
  praisonai workflow auto "topic" --pattern <pattern>  - Auto-generate workflow
  
Templates: simple, routing, parallel, loop, evaluator-optimizer, model-routing
Patterns: sequential, routing, parallel

Example:
  praisonai workflow run research.yaml --var topic="AI trends"
  praisonai workflow create --template routing --output my_workflow.yaml
  praisonai workflow auto "Research AI trends" --pattern parallel
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
            # Load raw YAML to check for non-canonical names
            import yaml
            with open(file_path, 'r') as f:
                raw_data = yaml.safe_load(f)
            
            # Check for non-canonical names and suggest canonical ones
            suggestions = self._get_canonical_suggestions(raw_data)
            
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
            
            # Show suggestions for canonical names
            if suggestions:
                rprint()
                rprint("[yellow]💡 Suggestions for canonical field names:[/yellow]")
                for suggestion in suggestions:
                    rprint(f"   [dim]•[/dim] {suggestion}")
                rprint()
                rprint("[dim]Note: Both old and new names work, but canonical names are recommended.[/dim]")
            
            return True
            
        except Exception as e:
            self.print_status(f"✗ Validation failed: {e}", "error")
            return False
    
    def _get_canonical_suggestions(self, data: Dict) -> List[str]:
        """
        Check for non-canonical field names and return suggestions.
        
        Canonical names (A-I-G-S mnemonic):
        - Agents (not roles)
        - Instructions (not backstory)
        - Goal (same)
        - Steps (not tasks)
        
        Also:
        - name (not topic)
        - action (not description)
        
        Args:
            data: Raw YAML data
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        if not data:
            return suggestions
        
        # Check top-level keys
        if 'roles' in data:
            suggestions.append("Use 'agents' instead of 'roles'")
        
        if 'topic' in data and 'name' not in data:
            suggestions.append("Use 'name' instead of 'topic'")
        
        # Check agent fields
        agents_data = data.get('agents', data.get('roles', {}))
        for agent_id, agent_config in agents_data.items():
            if isinstance(agent_config, dict):
                if 'backstory' in agent_config:
                    suggestions.append(f"Agent '{agent_id}': Use 'instructions' instead of 'backstory'")
                
                # Check nested tasks
                if 'tasks' in agent_config:
                    suggestions.append(f"Agent '{agent_id}': Use 'steps' at top level instead of nested 'tasks'")
        
        # Check step fields
        steps_data = data.get('steps', [])
        for i, step in enumerate(steps_data):
            if isinstance(step, dict):
                if 'description' in step and 'action' not in step:
                    step_name = step.get('name', f'step {i+1}')
                    suggestions.append(f"Step '{step_name}': Use 'action' instead of 'description'")
                
                # Check parallel steps
                if 'parallel' in step:
                    for j, parallel_step in enumerate(step['parallel']):
                        if isinstance(parallel_step, dict):
                            if 'description' in parallel_step and 'action' not in parallel_step:
                                suggestions.append(f"Parallel step {j+1}: Use 'action' instead of 'description'")
        
        return suggestions
    
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
    
    def action_auto(self, args: List[str], **kwargs) -> Optional[str]:
        """
        Auto-generate a workflow from a topic description.
        
        Args:
            args: ["topic description", --pattern, <pattern>, --output, <file.yaml>]
            
        Returns:
            Path to created file
        """
        # Parse arguments
        topic = None
        pattern = "sequential"
        output_file = None
        
        i = 0
        while i < len(args):
            if args[i] == "--pattern" and i + 1 < len(args):
                pattern = args[i + 1]
                i += 2
            elif args[i] == "--output" and i + 1 < len(args):
                output_file = args[i + 1]
                i += 2
            elif not args[i].startswith("--") and topic is None:
                topic = args[i]
                i += 1
            else:
                i += 1
        
        if not topic:
            self.print_status('Usage: praisonai workflow auto "topic" --pattern <pattern>', "error")
            self.print_status("Patterns: sequential, routing, parallel", "info")
            return None
        
        # Validate pattern
        valid_patterns = ["sequential", "routing", "parallel", "loop", "orchestrator-workers", "evaluator-optimizer"]
        if pattern not in valid_patterns:
            self.print_status(f"Unknown pattern: {pattern}", "error")
            self.print_status(f"Valid patterns: {', '.join(valid_patterns)}", "info")
            return None
        
        # Default output file
        if not output_file:
            # Create safe filename from topic
            safe_name = "".join(c if c.isalnum() else "_" for c in topic[:30]).lower()
            output_file = f"{safe_name}_workflow.yaml"
        
        # Check if file exists
        if os.path.exists(output_file):
            self.print_status(f"File already exists: {output_file}", "error")
            return None
        
        self.print_status(f"Generating {pattern} workflow for: {topic}", "info")
        
        try:
            # Lazy import to avoid performance impact
            from praisonai.auto import WorkflowAutoGenerator
            
            generator = WorkflowAutoGenerator(
                topic=topic,
                workflow_file=output_file
            )
            
            result_path = generator.generate(pattern=pattern)
            
            self.print_status(f"✓ Created workflow: {result_path}", "success")
            self.print_status(f"Run with: praisonai workflow run {output_file}", "info")
            
            return result_path
            
        except ImportError:
            self.print_status("Auto-generation requires litellm: pip install litellm", "error")
            return None
        except Exception as e:
            self.print_status(f"Generation failed: {e}", "error")
            return None
