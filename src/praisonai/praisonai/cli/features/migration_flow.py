"""
Agent-Driven Migration Flow.

Uses AgentFlow with specialized agents to migrate code from various
agent frameworks to PraisonAI format.

Architecture:
1. Analyzer Agent - Scans all files, understands relationships
2. Converter Agent - Transforms code using migration spec
3. Evaluator Agent - Uses LLM-as-Judge to validate conversion
4. Error Agent - Analyzes failures and suggests fixes

The flow includes a retry loop (max 3 iterations) for error recovery.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context for a single file in the migration."""
    path: str
    content: str
    patterns_found: List[str] = field(default_factory=list)
    converted_content: Optional[str] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class MigrationContext:
    """Complete context for multi-file migration."""
    source_path: str
    files: Dict[str, FileContext] = field(default_factory=dict)
    all_imports: List[str] = field(default_factory=list)
    all_classes: List[str] = field(default_factory=list)
    all_functions: List[str] = field(default_factory=list)
    cross_file_deps: Dict[str, List[str]] = field(default_factory=dict)
    
    def to_prompt(self) -> str:
        """Convert context to a prompt for LLM agents."""
        lines = [
            f"# Project Analysis: {self.source_path}",
            f"Total files: {len(self.files)}",
            "",
            "## Files:",
        ]
        for path, ctx in self.files.items():
            lines.append(f"- {path}: {len(ctx.content)} chars, patterns: {ctx.patterns_found}")
        
        if self.cross_file_deps:
            lines.append("")
            lines.append("## Cross-file Dependencies:")
            for file, deps in self.cross_file_deps.items():
                lines.append(f"- {file} imports from: {deps}")
        
        return "\n".join(lines)


@dataclass
class MigrationResult:
    """Result of the migration flow."""
    success: bool
    files_converted: int = 0
    files_failed: int = 0
    iterations: int = 0
    evaluation_score: float = 0.0
    converted_files: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class MigrationFlow:
    """
    Agent-driven migration flow using AgentFlow.
    
    Uses specialized agents to analyze, convert, evaluate, and fix
    code migration from various agent frameworks to PraisonAI.
    
    Example:
        flow = MigrationFlow(
            source_path="./my-project",
            output_path="./converted",
            max_retries=3
        )
        result = flow.run()
    """
    
    def __init__(
        self,
        source_path: str,
        output_path: Optional[str] = None,
        max_retries: int = 3,
        llm: str = "gpt-4o-mini",
        dry_run: bool = True,
    ):
        self.source_path = source_path
        self.output_path = output_path or f"{source_path}_converted"
        self.max_retries = max_retries
        self.llm = llm
        self.dry_run = dry_run
        self._context: Optional[MigrationContext] = None
        self._spec = None
    
    def _gather_files(self) -> MigrationContext:
        """Gather all Python files and build context."""
        context = MigrationContext(source_path=self.source_path)
        
        source = Path(self.source_path)
        
        if source.is_file():
            # Single file
            with open(source, 'r', encoding='utf-8') as f:
                content = f.read()
            context.files[str(source)] = FileContext(
                path=str(source),
                content=content
            )
        else:
            # Directory - scan for Python files
            exclude_dirs = {'venv', '.venv', '__pycache__', '.git', 'node_modules', '.tox', 'dist', 'build'}
            
            for root, dirs, files in os.walk(source):
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for filename in files:
                    if filename.endswith('.py'):
                        filepath = os.path.join(root, filename)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                content = f.read()
                            rel_path = os.path.relpath(filepath, source)
                            context.files[rel_path] = FileContext(
                                path=rel_path,
                                content=content
                            )
                        except Exception as e:
                            logger.warning(f"Could not read {filepath}: {e}")
        
        # Analyze cross-file dependencies
        self._analyze_dependencies(context)
        
        return context
    
    def _analyze_dependencies(self, context: MigrationContext) -> None:
        """Analyze imports and cross-file dependencies."""
        import re
        
        for path, file_ctx in context.files.items():
            # Extract imports
            import_pattern = r'^(?:from\s+(\S+)\s+)?import\s+(.+)$'
            for line in file_ctx.content.split('\n'):
                match = re.match(import_pattern, line.strip())
                if match:
                    module = match.group(1) or match.group(2).split(',')[0].strip()
                    context.all_imports.append(module)
                    
                    # Check if it's a local import
                    for other_path in context.files:
                        other_module = other_path.replace('/', '.').replace('.py', '')
                        if module.startswith(other_module) or other_module.endswith(module):
                            if path not in context.cross_file_deps:
                                context.cross_file_deps[path] = []
                            context.cross_file_deps[path].append(other_path)
            
            # Extract class and function names
            class_pattern = r'^class\s+(\w+)'
            func_pattern = r'^def\s+(\w+)'
            for line in file_ctx.content.split('\n'):
                match = re.match(class_pattern, line)
                if match:
                    context.all_classes.append(match.group(1))
                match = re.match(func_pattern, line)
                if match:
                    context.all_functions.append(match.group(1))
    
    def _create_agents(self):
        """Create the specialized migration agents."""
        # Lazy import to avoid circular dependencies
        from praisonaiagents import Agent
        from .migration_spec import get_default_spec, PRAISONAI_REFERENCE
        
        self._spec = get_default_spec()
        spec_prompt = self._spec.to_prompt()
        
        # Analyzer Agent
        analyzer = Agent(
            name="Analyzer",
            role="Code Analyzer",
            goal="Analyze source code to identify agent patterns and dependencies",
            instructions=f"""You are a code analysis expert. Analyze the provided source code to:
1. Identify all agent-related patterns (Agent, Task, Team, Workflow definitions)
2. Map dependencies between files
3. Identify import patterns that need conversion
4. List all classes and functions that are part of the agent system

Use this specification to identify patterns:
{spec_prompt}

Output a structured analysis with:
- List of detected patterns per file
- Cross-file dependencies
- Recommended conversion order
""",
            llm=self.llm,
        )
        
        # Converter Agent
        converter = Agent(
            name="Converter",
            role="Code Converter",
            goal="Convert source code to PraisonAI format",
            instructions=f"""You are a code conversion expert. Convert the provided source code to PraisonAI format.

Use this specification for conversion:
{spec_prompt}

Reference for PraisonAI code:
{PRAISONAI_REFERENCE}

Rules:
1. Preserve all logic and behavior
2. Convert imports to praisonaiagents
3. Map parameters according to the spec
4. Handle cross-file dependencies correctly
5. Ensure the converted code is syntactically valid Python
6. Do NOT include any framework names in comments

Output the complete converted code for each file.
""",
            llm=self.llm,
        )
        
        # Evaluator Agent (LLM-as-Judge)
        evaluator = Agent(
            name="Evaluator",
            role="Migration Evaluator",
            goal="Evaluate the quality of code migration",
            instructions="""You are a code quality evaluator using LLM-as-Judge methodology.

Evaluate the converted code on these criteria (score 1-10 each):
1. **Syntax Correctness**: Is the code valid Python?
2. **Import Completeness**: Are all necessary imports present?
3. **Functional Equivalence**: Does it preserve the original behavior?
4. **Pattern Accuracy**: Are agent patterns correctly converted?
5. **Dependency Handling**: Are cross-file dependencies handled?

Output format:
```json
{
    "scores": {
        "syntax": 8,
        "imports": 9,
        "equivalence": 7,
        "patterns": 8,
        "dependencies": 9
    },
    "overall_score": 8.2,
    "passed": true,
    "issues": ["list of specific issues if any"],
    "suggestions": ["list of improvements if any"]
}
```

A score of 8.0 or higher means PASSED.
""",
            llm=self.llm,
        )
        
        # Error Agent
        error_agent = Agent(
            name="ErrorAnalyzer",
            role="Error Analyzer",
            goal="Analyze migration errors and suggest fixes",
            instructions="""You are an error analysis expert. When migration evaluation fails:

1. Analyze the specific errors reported
2. Identify the root cause
3. Suggest specific fixes
4. Provide corrected code snippets

Output format:
```json
{
    "root_cause": "description of the main issue",
    "affected_files": ["list of files with issues"],
    "fixes": [
        {
            "file": "filename",
            "issue": "what's wrong",
            "fix": "how to fix it",
            "corrected_code": "the fixed code snippet"
        }
    ],
    "retry_recommended": true
}
```
""",
            llm=self.llm,
        )
        
        return analyzer, converter, evaluator, error_agent
    
    def run(self) -> MigrationResult:
        """Run the migration flow."""
        result = MigrationResult(success=False)
        
        # Gather all files
        logger.info(f"Gathering files from {self.source_path}")
        self._context = self._gather_files()
        
        if not self._context.files:
            result.errors.append("No Python files found")
            return result
        
        logger.info(f"Found {len(self._context.files)} files to analyze")
        
        # Create agents
        analyzer, converter, evaluator, error_agent = self._create_agents()
        
        # Build the combined context for all files
        all_code = []
        for path, file_ctx in self._context.files.items():
            all_code.append(f"# File: {path}\n{file_ctx.content}")
        combined_code = "\n\n---\n\n".join(all_code)
        
        # Retry loop
        for iteration in range(self.max_retries):
            result.iterations = iteration + 1
            logger.info(f"Migration iteration {iteration + 1}/{self.max_retries}")
            
            try:
                # Step 1: Analyze
                analysis_prompt = f"""Analyze this codebase for migration:

{self._context.to_prompt()}

Full code:
{combined_code}
"""
                analysis = analyzer.start(analysis_prompt)
                logger.info("Analysis complete")
                
                # Step 2: Convert
                convert_prompt = f"""Convert this code to PraisonAI format.

Analysis results:
{analysis}

Original code:
{combined_code}

Convert ALL files and output the complete converted code for each file.
Format: Start each file with "# FILE: filename.py" followed by the converted code.
"""
                converted = converter.start(convert_prompt)
                logger.info("Conversion complete")
                
                # Parse converted files
                self._parse_converted_output(converted, result)
                
                # Step 3: Evaluate
                eval_prompt = f"""Evaluate this migration:

Original code:
{combined_code}

Converted code:
{converted}

Evaluate and score the migration quality.
"""
                evaluation = evaluator.start(eval_prompt)
                logger.info("Evaluation complete")
                
                # Parse evaluation result
                import json
                import re
                
                # Try to extract JSON from evaluation
                json_match = re.search(r'\{[\s\S]*\}', evaluation)
                if json_match:
                    try:
                        eval_result = json.loads(json_match.group())
                        result.evaluation_score = eval_result.get('overall_score', 0)
                        
                        if eval_result.get('passed', False) or result.evaluation_score >= 8.0:
                            result.success = True
                            result.files_converted = len(result.converted_files)
                            logger.info(f"Migration PASSED with score {result.evaluation_score}")
                            break
                        else:
                            # Evaluation failed, run error analysis
                            issues = eval_result.get('issues', [])
                            result.warnings.extend(issues)
                            
                            if iteration < self.max_retries - 1:
                                error_prompt = f"""Migration evaluation failed.

Issues found:
{issues}

Converted code:
{converted}

Analyze the errors and suggest fixes.
"""
                                _ = error_agent.start(error_prompt)
                                logger.info("Error analysis complete, retrying...")
                                # The next iteration will use the error analysis context
                    except json.JSONDecodeError:
                        result.warnings.append("Could not parse evaluation result")
                else:
                    result.warnings.append("No evaluation JSON found")
                    
            except Exception as e:
                result.errors.append(f"Iteration {iteration + 1} failed: {str(e)}")
                logger.error(f"Migration error: {e}")
        
        if not result.success:
            result.errors.append(f"Migration failed after {self.max_retries} attempts")
        
        # Save converted files if not dry run
        if not self.dry_run and result.success:
            self._save_converted_files(result)
        
        return result
    
    def _parse_converted_output(self, converted: str, result: MigrationResult) -> None:
        """Parse the converted output into individual files."""
        import re
        
        # Split by file markers
        file_pattern = r'#\s*FILE:\s*(\S+\.py)'
        parts = re.split(file_pattern, converted)
        
        # parts[0] is before first file, then alternating filename, content
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                filename = parts[i].strip()
                content = parts[i + 1].strip()
                # Clean up code blocks
                content = re.sub(r'^```python\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                result.converted_files[filename] = content
    
    def _save_converted_files(self, result: MigrationResult) -> None:
        """Save converted files to output directory."""
        output_dir = Path(self.output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for filename, content in result.converted_files.items():
            filepath = output_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Saved: {filepath}")
