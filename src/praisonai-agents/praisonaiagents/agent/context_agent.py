"""
ContextAgent - Advanced Context Engineering for AI Coding Assistants

This class implements proper Context Engineering principles following the PRD template:
- 10x better than prompt engineering
- 100x better than vibe coding
- Comprehensive context generation for first-try implementation success
- Systematic codebase analysis with modern tools
- PRP (Product Requirements Prompt) generation
- Validation loops and quality gates
- SAVES EVERY AGENT RESPONSE ALONG THE WAY for complete traceability
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, Union, List, TYPE_CHECKING

# Lazy imports for performance - these are only loaded when needed
_subprocess = None
_glob = None
_ast = None
_asyncio = None

def _get_subprocess():
    """Lazy import subprocess to avoid import-time overhead."""
    global _subprocess
    if _subprocess is None:
        import subprocess
        _subprocess = subprocess
    return _subprocess

def _get_glob():
    """Lazy import glob to avoid import-time overhead."""
    global _glob
    if _glob is None:
        import glob
        _glob = glob
    return _glob

def _get_ast():
    """Lazy import ast to avoid import-time overhead."""
    global _ast
    if _ast is None:
        import ast
        _ast = ast
    return _ast

def _get_asyncio():
    """Lazy import asyncio to avoid import-time overhead."""
    global _asyncio
    if _asyncio is None:
        import asyncio
        _asyncio = asyncio
    return _asyncio

async def _async_subprocess_run(cmd: list, timeout: int = 60) -> tuple:
    """
    Run subprocess asynchronously (non-blocking).
    
    Args:
        cmd: Command list to execute
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (stdout, stderr, returncode)
    """
    asyncio = _get_asyncio()
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        return (
            stdout.decode() if stdout else "",
            stderr.decode() if stderr else "",
            process.returncode
        )
    except asyncio.TimeoutError:
        if process:
            process.kill()
            await process.wait()
        raise
    except FileNotFoundError:
        raise

from ..agent.agent import Agent
from ..task import Task


class ContextAgent(Agent):
    """
    Advanced Context Engineering Agent - Comprehensive context generation for AI coding assistants.
    
    Implements the Context Engineering methodology from the PRD template:
    
    Phase 1: Deep Codebase Analysis (using gitingest, AST analysis, etc.)
    Phase 2: Pattern Extraction and Documentation
    Phase 3: Comprehensive PRP Generation 
    Phase 4: Validation Framework Creation
    Phase 5: Implementation Blueprint Generation
    
    This follows the exact principles from the PRD template but adapted for PraisonAI architecture.
    
    NEW: Saves every single agent response along the way for complete traceability!
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[Union[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        project_path: Optional[str] = None,
        auto_analyze: bool = True,
        **kwargs
    ):
        # Context Engineering specific defaults following PRD template
        default_name = name or "Context Engineering Specialist"
        default_role = role or "Expert Context Engineer and Product Requirements Analyst"
        default_goal = goal or "Perform comprehensive codebase analysis and generate detailed PRPs for feature implementation"
        default_backstory = backstory or """You are a world-class Context Engineering specialist with deep expertise in:
        - Product Requirements Document (PRD) methodology
        - Comprehensive codebase analysis and reverse engineering
        - Feature implementation planning and architecture design
        - Git repository ingestion and structured analysis
        - Multi-agent orchestration for complex analysis tasks
        
        Your approach follows systematic context engineering principles to understand codebases
        deeply and generate actionable implementation guidance."""
        
        # Initialize parent Agent
        # Note: self.verbose is set by parent Agent based on output= parameter
        super().__init__(
            name=default_name,
            role=default_role,
            goal=default_goal,
            backstory=default_backstory,
            instructions=instructions,
            llm=llm,
            tools=tools or self._get_context_engineering_tools(),
            **kwargs
        )
        
        # Context Engineering specific attributes
        self.project_path = project_path
        self.auto_analyze = auto_analyze
        self.analysis_results = {}
        self.prp_results = {}
        self.context_documentation = {}
        self.implementation_blueprint = {}
        
        # Enhanced logging and output management
        self.debug_mode = os.getenv('LOGLEVEL', '').lower() == 'debug'
        self.output_dir = Path(".praison/prp")  # Save in .praison/prp folder
        self.setup_output_directories()  # Create directories first
        self.setup_logging()              # Then setup logging
        
        # Agent interaction tracking for comprehensive output
        self.agent_interactions = []
        self.interaction_counter = 0
        
        # Auto-analyze if requested and project_path provided
        if self.auto_analyze and self.project_path:
            self._perform_context_engineering_analysis()

    def _log(self, message: str, level: str = "info"):
        """
        Configurable logging that respects verbose flag.
        
        Args:
            message: Message to log
            level: Log level (info, debug, warning, error)
        """
        if level == "debug":
            if hasattr(self, 'logger'):
                self.logger.debug(message)
            if self.debug_mode:
                print(f"🐛 {message}")
        elif level == "warning":
            if hasattr(self, 'logger'):
                self.logger.warning(message)
            if self.verbose:
                print(f"⚠️ {message}")
        elif level == "error":
            if hasattr(self, 'logger'):
                self.logger.error(message)
            print(f"❌ {message}")  # Always show errors
        else:  # info
            if hasattr(self, 'logger'):
                self.logger.info(message)
            if self.verbose:
                print(message)

    def setup_logging(self):
        """Setup comprehensive logging based on debug mode."""
        try:
            # Create logger
            self.logger = logging.getLogger(f"ContextAgent_{id(self)}")
            self.logger.setLevel(logging.DEBUG if self.debug_mode else logging.INFO)
            
            # Clear existing handlers
            self.logger.handlers.clear()
            
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG if self.debug_mode else logging.INFO)
            
            # File handler for debug mode
            if self.debug_mode:
                try:
                    log_file = self.output_dir / "debug_logs" / f"context_agent_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                    # Ensure the debug_logs directory exists
                    log_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    file_handler = logging.FileHandler(log_file)
                    file_handler.setLevel(logging.DEBUG)
                    
                    # Detailed formatter for debug
                    debug_formatter = logging.Formatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
                    )
                    file_handler.setFormatter(debug_formatter)
                    self.logger.addHandler(file_handler)
                    
                    print(f"🐛 Debug logging enabled: {log_file}")
                except Exception as e:
                    print(f"⚠️ Warning: Could not setup debug file logging: {e}")
                    # Continue without file logging if it fails
            
            # Console formatter
            console_formatter = logging.Formatter('%(levelname)s - %(message)s')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
            
        except Exception as e:
            print(f"⚠️ Warning: Could not setup logging: {e}")
            # Create a minimal logger as fallback
            self.logger = logging.getLogger(f"ContextAgent_{id(self)}")
            self.logger.setLevel(logging.INFO)

    def setup_output_directories(self):
        """Setup all output directories for comprehensive saving."""
        directories = [
            self.output_dir,
            self.output_dir / "agent_responses",
            self.output_dir / "markdown_outputs", 
            self.output_dir / "debug_logs",
            self.output_dir / "final_results"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            
        if self.debug_mode:
            print(f"🐛 Debug: Output directories created: {[str(d) for d in directories]}")

    def log_debug(self, message: str, **kwargs):
        """Enhanced debug logging with optional data."""
        if self.debug_mode and hasattr(self, 'logger') and self.logger:
            self.logger.debug(f"{message} {kwargs if kwargs else ''}")
        elif self.debug_mode:
            # Fallback to print if logger not ready
            print(f"🐛 DEBUG: {message} {kwargs if kwargs else ''}")

    def save_markdown_output(self, content: str, filename: str, section_title: str = "Output"):
        """Save content as markdown file with proper formatting."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        markdown_content = f"""# {section_title}

**Generated:** {timestamp}  
**ContextAgent Session:** {id(self)}

---

{content}

---
*Generated by ContextAgent - Context Engineering Specialist*
"""
        
        # Save to markdown outputs directory
        md_file = self.output_dir / "markdown_outputs" / f"{filename}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_content)
            
        print(f"📝 Markdown saved: {md_file}")
        self.log_debug(f"Markdown output saved", file=str(md_file), length=len(content))
        
        return str(md_file)

    def save_comprehensive_session_report(self):
        """Save a comprehensive markdown report of the entire session (debug mode only)."""
        if not self.debug_mode:
            self.log_debug("Skipping comprehensive session report - not in debug mode")
            return
            
        if not self.agent_interactions:
            self.log_debug("No agent interactions to save in comprehensive report")
            return
            
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        
        # Generate comprehensive markdown report
        report = f"""# ContextAgent Session Report

**Session ID:** {id(self)}  
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Total Agent Interactions:** {len(self.agent_interactions)}  
**Debug Mode:** {'✅ Enabled' if self.debug_mode else '❌ Disabled'}

---

## 📋 Session Summary

This report contains all agent interactions and outputs from a complete ContextAgent session.

### 🎯 Agent Interactions Overview

"""
        
        # Add interaction summary table
        report += "| # | Agent | Phase | Response Length | Timestamp |\n"
        report += "|---|-------|-------|-----------------|----------|\n"
        
        for interaction in self.agent_interactions:
            report += f"| {interaction['interaction_id']} | {interaction['agent_name']} | {interaction['phase']} | {len(interaction['response'])} chars | {interaction['timestamp']} |\n"
        
        report += "\n---\n\n"
        
        # Add detailed interactions
        for i, interaction in enumerate(self.agent_interactions, 1):
            report += f"""## 🤖 Agent {i}: {interaction['agent_name']}

**Phase:** {interaction['phase']}  
**Timestamp:** {interaction['timestamp']}  
**Response Length:** {len(interaction['response'])} characters

### 📝 Prompt
```
{interaction['prompt'][:1000]}{'... [truncated]' if len(interaction['prompt']) > 1000 else ''}
```

### 🎯 Response
{interaction['response']}

---

"""
        
        # Save comprehensive report
        report_file = self.save_markdown_output(
            report, 
            f"comprehensive_session_report_{timestamp}",
            "ContextAgent Comprehensive Session Report"
        )
        
        # Also save to final results
        final_report_file = self.output_dir / "final_results" / f"session_report_{timestamp}.md"
        with open(final_report_file, "w", encoding="utf-8") as f:
            f.write(report)
            
        print(f"📊 Comprehensive session report saved: {final_report_file}")
        self.log_debug("Comprehensive session report generated", file=str(final_report_file))
        
        return str(final_report_file)

    def _save_agent_response(self, agent_name: str, prompt: str, response: str, phase: str = "", metadata: Dict[str, Any] = None) -> str:
        """Save individual agent response with mode-aware saving strategy."""
        self.interaction_counter += 1
        timestamp = datetime.now().isoformat()
        
        # Enhanced debug logging
        self.log_debug(f"Saving agent response", 
                       agent=agent_name, 
                       phase=phase, 
                       response_length=len(response),
                       prompt_length=len(prompt))
        
        interaction_data = {
            "interaction_id": self.interaction_counter,
            "timestamp": timestamp,
            "phase": phase,
            "agent_name": agent_name,
            "prompt": prompt if self.debug_mode else prompt[:2000],  # Full prompt in debug mode
            "response": response,
            "metadata": metadata or {}
        }
        
        # ALWAYS add to interactions list for final PRP
        self.agent_interactions.append(interaction_data)
        
        # ONLY save individual files in DEBUG MODE
        if self.debug_mode:
            # Save individual response file (JSON) - debug only
            safe_agent_name = agent_name.lower().replace(' ', '_').replace('-', '_')
            response_filename = f"{self.interaction_counter:03d}_{safe_agent_name}_{timestamp.replace(':', '_')}.json"
            response_path = os.path.join(self.output_dir, "agent_responses", response_filename)
            
            with open(response_path, "w") as f:
                json.dump(interaction_data, f, indent=2)
            
            # Save individual markdown files - debug only
            md_filename = f"{self.interaction_counter:03d}_{safe_agent_name}_{timestamp.replace(':', '_')}"
            self.save_markdown_output(
                content=f"""## Agent: {agent_name}
**Phase:** {phase}  
**Timestamp:** {timestamp}  
**Response Length:** {len(response)} characters

### Prompt
```
{prompt[:1000]}{'... [truncated]' if len(prompt) > 1000 else ''}
```

### Response
{response}
""",
                filename=md_filename,
                section_title=f"{agent_name} - {phase}"
            )
            
            print(f"💾 Agent response saved: {response_filename}")
            self.log_debug(f"Agent response and markdown saved", json_file=response_filename, interaction_id=self.interaction_counter)
            return response_path
        else:
            # In non-debug mode, just collect for final PRP
            print(f"📝 Agent response collected for final PRP: {agent_name}")
            return "collected_for_final_prp"

    def _chat_with_agent_and_save(self, agent: Agent, prompt: str, phase: str = "") -> str:
        """Chat with agent and automatically save the response."""
        print(f"  💬 Chatting with {agent.name}...")
        response = agent.chat(prompt)
        
        # Save the interaction
        self._save_agent_response(
            agent_name=agent.name,
            prompt=prompt,
            response=response,
            phase=phase,
            metadata={
                "agent_role": agent.role,
                "agent_goal": agent.goal,
                "response_length": len(response)
            }
        )
        
        return response

    def _get_context_engineering_tools(self) -> List[Any]:
        """Get Context Engineering specific tools following PRD methodology."""
        return [
            self.analyze_codebase_with_gitingest,
            self.perform_ast_analysis,
            self.extract_implementation_patterns,
            self.analyze_test_patterns,
            self.generate_comprehensive_prp,
            self.create_validation_framework,
            self.build_implementation_blueprint,
            self.compile_context_documentation,
            self.analyze_integration_points,
            self.create_quality_gates
        ]

    def _perform_context_engineering_analysis(self):
        """Perform comprehensive Context Engineering analysis following PRD template phases."""
        try:
            print("📊 PHASE 1: Deep Codebase Analysis with Modern Tools...")
            self.codebase_analysis = self.analyze_codebase_with_gitingest(self.project_path)
            
            print("🏗️ PHASE 2: AST Analysis and Pattern Extraction...")
            ast_analysis = self.perform_ast_analysis(self.project_path)
            self.pattern_library = self.extract_implementation_patterns(self.project_path, ast_analysis)
            
            print("🔗 PHASE 3: Integration Point Analysis...")
            self.integration_points = self.analyze_integration_points(self.project_path)
            
            print("📚 PHASE 4: Context Documentation Compilation...")
            self.context_documentation = self.compile_context_documentation(self.project_path)
            
            print("✅ PHASE 5: Validation Framework Creation...")
            self.validation_framework = self.create_validation_framework(self.project_path)
            
            print("🎯 Context Engineering analysis complete following PRD methodology!")
            self._save_context_engineering_results()
            
            # Generate summary report following PRD template
            self._generate_analysis_summary()
            
        except Exception as e:
            print(f"❌ Context Engineering analysis failed: {e}")
            # Fallback to basic analysis if advanced tools fail
            self._perform_fallback_analysis()

    def analyze_codebase_with_gitingest(self, project_path: str) -> Dict[str, Any]:
        """Analyze codebase using gitingest for comprehensive understanding."""
        print("  🤖 Creating Gitingest-Powered Codebase Analyst...")
        
        try:
            # Try to use gitingest for comprehensive analysis
            digest_content = self._run_gitingest_analysis(project_path)
            
            if digest_content:
                # Create specialized analyst to process gitingest output
                gitingest_analyst = Agent(
                    name="Gitingest Codebase Analyst",
                    role="Expert Codebase Analysis Specialist using Gitingest",
                    goal="Perform comprehensive codebase analysis using gitingest output following PRD methodology",
                    instructions="""You are an expert at analyzing gitingest codebase digests following the PRD template methodology.
                    
                    Analyze the gitingest output to extract:
                    1. PROJECT STRUCTURE: Complete directory organization and file hierarchies
                    2. CODE PATTERNS: All classes, functions, decorators, inheritance patterns
                    3. ARCHITECTURAL INSIGHTS: Design patterns, architectural styles, layer organization
                    4. NAMING CONVENTIONS: Consistent naming styles and patterns across the codebase
                    5. IMPORT PATTERNS: Module dependencies, relative vs absolute imports
                    6. TESTING PATTERNS: Test organization, frameworks, coverage approaches
                    7. DOCUMENTATION PATTERNS: Docstring styles, README structure, API documentation
                    8. CONFIGURATION PATTERNS: Environment handling, settings management
                    9. ERROR HANDLING: Exception patterns, logging approaches, error management
                    10. INTEGRATION PATTERNS: API integrations, database patterns, external services
                    
                    Provide comprehensive analysis that follows the PRD template principles and enables 
                    AI assistants to implement features that perfectly match existing codebase patterns.""",
                    llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                )
                
                prompt = f"""Analyze this gitingest codebase digest following PRD template methodology:

PROJECT PATH: {project_path}

GITINGEST COMPREHENSIVE ANALYSIS:
{digest_content[:8000]}  # Limit for context window

Perform deep analysis following the 10 categories above. Focus on patterns that would 
enable an AI assistant to implement new features that perfectly match the existing 
codebase style and architecture following PRD template principles."""
                
                print("  🔍 Gitingest Analyst analyzing comprehensive codebase digest...")
                # Use the new save method
                response = self._chat_with_agent_and_save(gitingest_analyst, prompt, "PHASE_1_GITINGEST_ANALYSIS")
                
                analysis = {
                    "analysis_method": "gitingest",
                    "project_structure": {"analysis": response[:1000]},
                    "code_patterns": {"analysis": response},
                    "architectural_insights": {"analysis": response},
                    "gitingest_digest": digest_content[:2000],
                    "full_analysis": response
                }
                
                print(f"  ✅ Gitingest comprehensive analysis complete")
                return analysis
                
        except Exception as e:
            print(f"  ⚠️ Gitingest analysis failed: {e}, falling back to manual analysis")
        
        # Fallback to manual analysis if gitingest fails
        return self._perform_manual_codebase_analysis(project_path)

    def _run_gitingest_analysis(self, project_path: str) -> str:
        """Run gitingest analysis on the codebase."""
        try:
            # Try to run gitingest command
            result = _get_subprocess().run(
                ["gitingest", project_path, "--output", "-"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                print(f"  ⚠️ Gitingest command failed: {result.stderr}")
                return None
                
        except _get_subprocess().TimeoutExpired:
            print("  ⚠️ Gitingest analysis timed out")
            return None
        except FileNotFoundError:
            print("  ⚠️ Gitingest not found, trying alternative analysis")
            return None
        except Exception as e:
            print(f"  ⚠️ Gitingest error: {e}")
            return None

    def _perform_manual_codebase_analysis(self, project_path: str) -> Dict[str, Any]:
        """Fallback manual codebase analysis when gitingest is not available."""
        print("  🔧 Performing manual codebase analysis...")
        
        # Get comprehensive file samples using manual methods
        python_files = self._get_filtered_files(project_path, "*.py", 20)
        config_files = self._get_filtered_files(project_path, "*.json", 5)
        config_files.extend(self._get_filtered_files(project_path, "*.toml", 5))
        config_files.extend(self._get_filtered_files(project_path, "*.yaml", 5))
        doc_files = self._get_filtered_files(project_path, "*.md", 10)
        
        # Create comprehensive manual analyst
        manual_analyst = Agent(
            name="Manual Codebase Analyst",
            role="Expert Manual Codebase Analysis Specialist",
            goal="Perform comprehensive manual codebase analysis following PRD methodology",
            instructions="""Analyze the codebase samples following PRD template methodology for complete understanding.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Format comprehensive sample
        comprehensive_content = self._format_comprehensive_samples(
            python_files, config_files, doc_files, project_path
        )
        
        prompt = f"""Perform comprehensive manual codebase analysis following PRD template methodology:

PROJECT PATH: {project_path}

COMPREHENSIVE CODEBASE SAMPLES:
{comprehensive_content}

Analyze following PRD principles to extract patterns, conventions, and architectural insights."""
        
        print("  🔍 Manual Analyst analyzing codebase samples...")
        # Use the new save method
        response = self._chat_with_agent_and_save(manual_analyst, prompt, "PHASE_1_MANUAL_ANALYSIS")
        
        analysis = {
            "analysis_method": "manual",
            "project_structure": {"analysis": response[:1000]},
            "code_patterns": {"analysis": response},
            "architectural_insights": {"analysis": response},
            "full_analysis": response
        }
        
        print(f"  ✅ Manual codebase analysis complete")
        return analysis

    def perform_ast_analysis(self, project_path: str) -> Dict[str, Any]:
        """Perform AST (Abstract Syntax Tree) analysis for code patterns."""
        print("  🤖 Creating AST Pattern Analyzer...")
        
        ast_analyzer = Agent(
            name="AST Pattern Analyzer",
            role="Abstract Syntax Tree Analysis Expert",
            goal="Extract code patterns and structures using AST analysis following PRD methodology",
            instructions="""You are an expert at AST analysis for pattern extraction following PRD principles.
            Analyze the AST information to identify:
            1. Class hierarchies and inheritance patterns
            2. Function signatures and patterns
            3. Import dependencies and module structure
            4. Decorator usage patterns
            5. Exception handling patterns
            6. Design pattern implementations
            7. Code complexity metrics
            8. API and interface patterns""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Perform AST analysis on Python files
        python_files = self._get_filtered_files(project_path, "*.py", 15)
        ast_data = self._extract_ast_patterns(python_files)
        
        prompt = f"""Analyze AST patterns from this codebase following PRD methodology:

PROJECT PATH: {project_path}

AST ANALYSIS DATA:
{json.dumps(ast_data, indent=2)[:4000]}

Extract comprehensive patterns that follow PRD template principles for implementation guidance."""
        
        print("  🔍 AST Analyzer processing code patterns...")
        # Use the new save method
        response = self._chat_with_agent_and_save(ast_analyzer, prompt, "PHASE_2_AST_ANALYSIS")
        
        patterns = {
            "ast_method": True,
            "class_patterns": ast_data.get("classes", []),
            "function_patterns": ast_data.get("functions", []),
            "import_patterns": ast_data.get("imports", []),
            "decorator_patterns": ast_data.get("decorators", []),
            "full_analysis": response
        }
        
        print(f"  ✅ AST analysis complete: {len(patterns.get('class_patterns', []))} classes, {len(patterns.get('function_patterns', []))} functions analyzed")
        return patterns

    def extract_implementation_patterns(self, project_path: str, ast_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        """Extract reusable implementation patterns following PRD methodology."""
        print("  🤖 Creating Implementation Pattern Extractor...")
        
        pattern_extractor = Agent(
            name="Implementation Pattern Extractor",
            role="Code Pattern Recognition Expert following PRD methodology",
            goal="Extract reusable implementation patterns and best practices following PRD template principles",
            instructions="""You are an expert at identifying and extracting reusable implementation 
            patterns from codebases following PRD template methodology. Focus on patterns that enable
            first-try implementation success. Analyze to find:
            
            1. DESIGN PATTERNS: Factory, Observer, Strategy, Singleton, etc.
            2. ARCHITECTURAL PATTERNS: MVC, Repository, Service Layer, etc.
            3. CODE ORGANIZATION: Module structure, class hierarchies, function patterns
            4. ERROR HANDLING: Try-catch patterns, custom exceptions, logging
            5. DATA HANDLING: Validation patterns, serialization, database interactions
            6. TESTING PATTERNS: Test structure, mocking approaches, fixture patterns
            7. ASYNC PATTERNS: Async/await usage, concurrency patterns
            8. INTEGRATION PATTERNS: API clients, external service patterns
            9. CONFIGURATION PATTERNS: Settings management, environment variables
            10. UTILITY PATTERNS: Common helper functions, decorators, context managers
            
            For each pattern, provide the pattern name, where it's used, and how to replicate it 
            following PRD template principles.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Get representative code samples
        samples = self._get_pattern_samples(project_path)
        
        # Include AST analysis if available
        ast_info = ""
        if ast_analysis:
            ast_info = f"\nAST ANALYSIS:\n{json.dumps(ast_analysis, indent=2)[:2000]}"
        
        prompt = f"""Extract implementation patterns following PRD methodology:

PROJECT PATH: {project_path}

CODE SAMPLES:
{samples}
{ast_info}

Identify and document all reusable implementation patterns that follow PRD template 
principles and would help an AI assistant implement new features using the same 
patterns and best practices for first-try success."""
        
        print("  🔍 Pattern Extractor analyzing implementation patterns...")
        # Use the new save method
        response = self._chat_with_agent_and_save(pattern_extractor, prompt, "PHASE_2_PATTERN_EXTRACTION")
        
        patterns = {
            "patterns_identified": response.count("PATTERN"),
            "design_patterns": [],
            "architectural_patterns": [],
            "testing_patterns": [],
            "integration_patterns": [],
            "full_analysis": response
        }
        
        print(f"  ✅ Extracted implementation patterns following PRD methodology")
        return patterns

    def analyze_test_patterns(self, project_path: str) -> Dict[str, Any]:
        """Analyze testing patterns for validation framework creation."""
        print("  🤖 Creating Test Pattern Analyzer...")
        
        test_analyzer = Agent(
            name="Test Pattern Analyzer",
            role="Testing Pattern Recognition Expert",
            goal="Analyze testing patterns for comprehensive validation framework design",
            instructions="""Analyze testing patterns to understand validation approaches and create 
            comprehensive test frameworks following PRD methodology.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Get test files
        test_files = self._get_filtered_files(project_path, "*test*.py", 10)
        test_files.extend(self._get_filtered_files(project_path, "test_*.py", 10))
        test_files.extend(self._get_filtered_files(project_path, "conftest.py", 5))
        
        test_content = self._format_sample_files(test_files, project_path)
        
        prompt = f"""Analyze testing patterns following PRD methodology:

PROJECT PATH: {project_path}

TEST PATTERNS:
{test_content}

Extract testing patterns for validation framework creation following PRD principles."""
        
        print("  🔍 Test Analyzer processing testing patterns...")
        # Use the new save method
        response = self._chat_with_agent_and_save(test_analyzer, prompt, "PHASE_2_TEST_ANALYSIS")
        
        patterns = {
            "test_files_analyzed": len(test_files),
            "testing_frameworks": [],
            "test_patterns": [],
            "validation_approaches": [],
            "full_analysis": response
        }
        
        print(f"  ✅ Test pattern analysis complete: {len(test_files)} test files analyzed")
        return patterns

    def generate_comprehensive_prp(self, feature_request: str, context_analysis: Dict[str, Any] = None) -> str:
        """Generate comprehensive Product Requirements Prompt following PRD template exactly."""
        print("  🤖 Creating PRP Generation Specialist following PRD template...")
        
        if context_analysis is None:
            context_analysis = {
                "codebase_analysis": self.codebase_analysis,
                "pattern_library": self.pattern_library,
                "integration_points": getattr(self, 'integration_points', {}),
                "validation_framework": self.validation_framework,
                "context_documentation": self.context_documentation
            }
        
        prp_generator = Agent(
            name="PRP Generation Specialist",
            role="Product Requirements Prompt Expert following PRD Template",
            goal="Generate comprehensive PRPs following the exact PRD template methodology for first-try implementation success",
            instructions="""You are an expert at generating comprehensive Product Requirements Prompts (PRPs) 
            following the exact PRD template methodology. Your PRPs must follow the PRD template structure exactly:

            ## Purpose
            Clear statement of what needs to be built
            
            ## Core Principles  
            1. Context is King: Include ALL necessary documentation, examples, and caveats
            2. Validation Loops: Provide executable tests/lints the AI can run and fix
            3. Information Dense: Use keywords and patterns from the codebase
            4. Progressive Success: Start simple, validate, then enhance
            
            ## Goal
            What needs to be built - specific about end state
            
            ## Why
            - Business value and user impact
            - Integration with existing features
            - Problems this solves
            
            ## What
            User-visible behavior and technical requirements
            
            ### Success Criteria
            - [ ] Specific measurable outcomes
            
            ## All Needed Context
            
            ### Documentation & References
            Complete list of all context needed
            
            ### Current Codebase tree
            Run tree command output
            
            ### Desired Codebase tree  
            Files to be added with responsibilities
            
            ### Known Gotchas & Library Quirks
            Critical implementation details
            
            ## Implementation Blueprint
            
            ### Data models and structure
            Core data models for type safety
            
            ### List of tasks to be completed
            Ordered task list for implementation
            
            ### Per task pseudocode
            Detailed pseudocode with critical details
            
            ### Integration Points
            Database, config, route changes needed
            
            ## Validation Loop
            
            ### Level 1: Syntax & Style
            Executable commands for validation
            
            ### Level 2: Unit Tests  
            Test cases with expected outcomes
            
            ### Level 3: Integration Test
            End-to-end validation steps
            
            ## Final Validation Checklist
            Complete checklist for verification
            
            ## Anti-Patterns to Avoid
            Common mistakes to prevent
            
            ## Confidence Score: X/10
            Confidence level for one-pass implementation
            
            Generate PRPs following this EXACT structure for first-try implementation success.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        prompt = f"""Generate a comprehensive Product Requirements Prompt (PRP) following the EXACT PRD template structure:

FEATURE REQUEST: {feature_request}

COMPREHENSIVE CONTEXT ANALYSIS:
{json.dumps(context_analysis, indent=2)[:6000]}

PROJECT PATH: {self.project_path}

Create a PRP that follows the PRD template methodology EXACTLY with all sections:
- Purpose and Core Principles
- Goal, Why, What with Success Criteria  
- All Needed Context with Documentation & References
- Implementation Blueprint with tasks and pseudocode
- Validation Loop with executable commands
- Final checklist and confidence score

Include ALL necessary context for an AI assistant to implement this feature correctly 
on the first try following PRD template principles."""
        
        print("  🔍 PRP Generator creating comprehensive PRP following PRD template...")
        # Use the new save method
        prp = self._chat_with_agent_and_save(prp_generator, prompt, "PHASE_3_PRP_GENERATION")
        
        print(f"  ✅ Comprehensive PRP generated following PRD template ({len(prp)} characters)")
        return prp

    # Continue with remaining methods using the new save approach...
    def create_validation_framework(self, project_path: str) -> Dict[str, Any]:
        """Create comprehensive validation framework following PRD methodology."""
        print("  🤖 Creating Validation Framework Architect...")
        
        validation_architect = Agent(
            name="Validation Framework Architect",
            role="Quality Assurance Expert following PRD methodology",
            goal="Design comprehensive validation frameworks following PRD template principles",
            instructions="""Design validation frameworks following PRD methodology that include:
            1. SYNTAX VALIDATION: Linting, formatting, type checking
            2. UNIT TESTING: Comprehensive test coverage strategies
            3. INTEGRATION TESTING: End-to-end testing approaches
            4. PERFORMANCE VALIDATION: Performance benchmarks
            5. SECURITY VALIDATION: Security best practices
            6. CODE QUALITY: Complexity analysis, maintainability
            7. DOCUMENTATION VALIDATION: Documentation completeness
            8. DEPENDENCY VALIDATION: Dependency analysis and security""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Analyze existing validation patterns
        test_files = self._get_filtered_files(project_path, "*test*.py", 10)
        config_files = self._get_filtered_files(project_path, "*.toml", 3)
        config_files.extend(self._get_filtered_files(project_path, "pyproject.toml", 1))
        
        validation_content = self._format_sample_files(test_files + config_files, project_path)
        
        prompt = f"""Design comprehensive validation framework following PRD methodology:

PROJECT PATH: {project_path}

EXISTING VALIDATION PATTERNS:
{validation_content}

Create validation framework with all 8 validation types and executable commands 
following PRD template principles."""
        
        print("  🔍 Validation Architect designing framework...")
        # Use the new save method
        response = self._chat_with_agent_and_save(validation_architect, prompt, "PHASE_5_VALIDATION_FRAMEWORK")
        
        framework = {
            "syntax_validation": ["ruff check", "mypy"],
            "testing_validation": ["pytest", "pytest --cov"],
            "quality_gates": ["coverage report", "complexity analysis"],
            "integration_tests": ["end-to-end test commands"],
            "full_framework": response
        }
        
        print(f"  ✅ Validation framework created following PRD methodology")
        return framework

    def compile_context_documentation(self, project_path: str) -> Dict[str, Any]:
        """Compile all context documentation following PRD methodology."""
        print("  🤖 Creating Context Documentation Compiler...")
        
        doc_compiler = Agent(
            name="Context Documentation Compiler",
            role="Documentation Analysis Expert following PRD methodology",
            goal="Compile comprehensive context documentation following PRD template principles",
            instructions="""Compile all available documentation following PRD methodology including:
            README files, API documentation, setup guides, architecture docs, and any other 
            relevant documentation that provides context for implementation.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Get documentation files
        doc_files = self._get_filtered_files(project_path, "*.md", 10)
        doc_files.extend(self._get_filtered_files(project_path, "*.rst", 5))
        doc_files.extend(self._get_filtered_files(project_path, "*.txt", 5))
        
        doc_content = self._format_sample_files(doc_files, project_path)
        
        prompt = f"""Compile context documentation following PRD methodology:

PROJECT PATH: {project_path}

DOCUMENTATION FILES:
{doc_content}

Extract and organize all documentation that provides context for implementation 
following PRD template principles."""
        
        print("  🔍 Documentation Compiler processing context docs...")
        # Use the new save method
        response = self._chat_with_agent_and_save(doc_compiler, prompt, "PHASE_4_DOCUMENTATION_COMPILATION")
        
        docs = {
            "readme_files": [f for f in doc_files if "readme" in f.lower()],
            "api_docs": [f for f in doc_files if "api" in f.lower()],
            "setup_docs": [f for f in doc_files if any(term in f.lower() for term in ["setup", "install", "config"])],
            "full_documentation": response
        }
        
        print(f"  ✅ Context documentation compiled: {len(doc_files)} files analyzed")
        return docs

    def analyze_integration_points(self, project_path: str) -> Dict[str, Any]:
        """Analyze integration points and external dependencies following PRD methodology."""
        print("  🤖 Creating Integration Point Analyzer...")
        
        integration_analyzer = Agent(
            name="Integration Point Analyzer", 
            role="Integration Analysis Expert following PRD methodology",
            goal="Analyze all integration points and dependencies following PRD template principles",
            instructions="""Analyze integration points following PRD methodology including:
            APIs, databases, external services, configuration points, and any other 
            integration requirements that affect implementation.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Get configuration and dependency files
        config_files = self._get_filtered_files(project_path, "*.toml", 5)
        config_files.extend(self._get_filtered_files(project_path, "requirements*.txt", 5))
        config_files.extend(self._get_filtered_files(project_path, "*.yaml", 5))
        config_files.extend(self._get_filtered_files(project_path, "*.yml", 5))
        config_files.extend(self._get_filtered_files(project_path, "*.json", 5))
        
        integration_content = self._format_sample_files(config_files, project_path)
        
        prompt = f"""Analyze integration points following PRD methodology:

PROJECT PATH: {project_path}

CONFIGURATION AND DEPENDENCY FILES:
{integration_content}

Identify all integration points, APIs, databases, and external dependencies 
following PRD template principles."""
        
        print("  🔍 Integration Analyzer processing integration points...")
        # Use the new save method
        response = self._chat_with_agent_and_save(integration_analyzer, prompt, "PHASE_3_INTEGRATION_ANALYSIS")
        
        integration_points = {
            "apis": [],
            "databases": [],
            "external_services": [],
            "configuration_points": [],
            "dependencies": config_files,
            "full_analysis": response
        }
        
        print(f"  ✅ Integration point analysis complete: {len(config_files)} config files analyzed")
        return integration_points

    def build_implementation_blueprint(self, feature_request: str, context_analysis: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build detailed implementation blueprint following PRD template."""
        print("  🤖 Creating Implementation Blueprint Architect...")
        
        if context_analysis is None:
            context_analysis = self.codebase_analysis
        
        blueprint_architect = Agent(
            name="Implementation Blueprint Architect",
            role="Software Implementation Planning Expert following PRD methodology",
            goal="Create detailed implementation blueprints following PRD template principles",
            instructions="""Create implementation blueprints following PRD methodology that include:
            1. TASK BREAKDOWN: Detailed task list in implementation order
            2. FILE MODIFICATIONS: Specific files to modify and how
            3. NEW FILE CREATION: New files needed and their purpose
            4. DEPENDENCY MANAGEMENT: Dependencies to add/update
            5. DATABASE CHANGES: Schema modifications if needed
            6. CONFIGURATION UPDATES: Config changes required
            7. TESTING REQUIREMENTS: Tests to create/update
            8. DOCUMENTATION UPDATES: Documentation to create/update
            9. INTEGRATION STEPS: How to integrate with existing systems
            10. VALIDATION CHECKPOINTS: Validation steps at each phase""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        prompt = f"""Create detailed implementation blueprint following PRD methodology:

FEATURE REQUEST: {feature_request}

CONTEXT ANALYSIS:
{json.dumps(context_analysis, indent=2)[:3000]}

PROJECT PATH: {self.project_path}

Create comprehensive blueprint following PRD template with all 10 components for 
detailed, actionable implementation steps."""
        
        print("  🔍 Blueprint Architect creating detailed implementation plan...")
        # Use the new save method
        response = self._chat_with_agent_and_save(blueprint_architect, prompt, "PHASE_5_IMPLEMENTATION_BLUEPRINT")
        
        blueprint = {
            "task_breakdown": [],
            "file_modifications": [],
            "new_files": [],
            "dependencies": [],
            "validation_checkpoints": [],
            "full_blueprint": response
        }
        
        print(f"  ✅ Implementation blueprint created following PRD methodology")
        return blueprint

    # Helper methods and remaining functionality...
    def _get_filtered_files(self, project_path: str, pattern: str, max_files: int) -> List[str]:
        """Get filtered files excluding unwanted directories following PRD principles."""
        try:
            files = _get_glob().glob(os.path.join(project_path, "**", pattern), recursive=True)
            
            # Filter out unwanted files following PRD methodology
            filtered = []
            exclude_patterns = [
                '__pycache__', '.pytest_cache', '.git', 'node_modules', 
                '.venv', 'venv', 'dist', 'build', '.praison', '.chroma_db',
                '.ruff_cache', '.mypy_cache', 'context_engineering_output'
            ]
            
            for file_path in files:
                if not any(exclude in file_path for exclude in exclude_patterns):
                    filtered.append(file_path)
                    
            return filtered[:max_files]
        except Exception:
            return []

    def _format_comprehensive_samples(self, python_files: List[str], config_files: List[str], 
                                    doc_files: List[str], project_path: str) -> str:
        """Format comprehensive samples following PRD methodology."""
        content = []
        
        # Python files
        if python_files:
            content.append("=== PYTHON CODE SAMPLES ===")
            content.append(self._format_sample_files(python_files, project_path))
        
        # Config files
        if config_files:
            content.append("\n=== CONFIGURATION SAMPLES ===")
            content.append(self._format_sample_files(config_files, project_path))
            
        # Documentation files  
        if doc_files:
            content.append("\n=== DOCUMENTATION SAMPLES ===")
            content.append(self._format_sample_files(doc_files, project_path))
            
        return "\n".join(content)

    def _format_sample_files(self, files: List[str], project_path: str) -> str:
        """Format sample files for analysis following PRD principles."""
        formatted = []
        for file_path in files:
            try:
                rel_path = os.path.relpath(file_path, project_path)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()[:3000]
                formatted.append(f"File: {rel_path}\n{content}\n{'='*80}")
            except Exception:
                continue
        return "\n\n".join(formatted)

    def _get_pattern_samples(self, project_path: str) -> str:
        """Get representative samples for pattern extraction following PRD methodology."""
        samples = []
        
        # Get diverse file types following PRD principles
        patterns = ["*.py", "test_*.py", "*_test.py", "conftest.py", "setup.py", "__init__.py", "pyproject.toml"]
        for pattern in patterns:
            files = self._get_filtered_files(project_path, pattern, 3)
            if files:
                samples.extend(files)
        
        return self._format_sample_files(samples, project_path)

    def create_quality_gates(self, requirements: List[str]) -> Dict[str, Any]:
        """Create quality gates for validation following PRD methodology."""
        return {
            "syntax_gates": ["ruff check", "mypy"],
            "test_gates": ["pytest --cov=80"],
            "quality_gates": ["complexity check", "security scan"],
            "integration_gates": ["integration tests"],
            "requirements": requirements
        }

    def _save_context_engineering_results(self):
        """Save all Context Engineering results following PRD methodology."""
        # Save comprehensive analysis
        with open(os.path.join(self.output_dir, "comprehensive_analysis.json"), "w") as f:
            json.dump(self.codebase_analysis, f, indent=2)
        
        # Save pattern library
        with open(os.path.join(self.output_dir, "pattern_library.json"), "w") as f:
            json.dump(self.pattern_library, f, indent=2)
            
        # Save validation framework
        with open(os.path.join(self.output_dir, "validation_framework.json"), "w") as f:
            json.dump(self.validation_framework, f, indent=2)
            
        # Save all agent interactions summary
        with open(os.path.join(self.output_dir, "all_agent_interactions.json"), "w") as f:
            json.dump(self.agent_interactions, f, indent=2)
        
        print(f"💾 Context Engineering results saved to: {self.output_dir}/")
        print(f"💾 Agent interactions ({len(self.agent_interactions)} total) saved to: agent_responses/")

    def _generate_analysis_summary(self):
        """Generate analysis summary following PRD methodology."""
        summary = f"""
# Context Engineering Analysis Summary

## Analysis Method: {self.codebase_analysis.get('analysis_method', 'manual')}
## Project Path: {self.project_path}
## Analysis Completion: ✅
## Total Agent Interactions: {len(self.agent_interactions)}

### Agent Interaction Tracking
All {len(self.agent_interactions)} agent responses have been saved with complete traceability:
- Individual response files in agent_responses/ directory
- Complete interaction log in all_agent_interactions.json
- Timestamps, prompts, responses, and metadata preserved

### Codebase Analysis
- Method: {self.codebase_analysis.get('analysis_method', 'manual')}
- Categories Analyzed: {len(self.codebase_analysis)}

### Pattern Library  
- Patterns Identified: {self.pattern_library.get('patterns_identified', 0)}
- Implementation Patterns: Available
- Testing Patterns: Available

### Validation Framework
- Validation Types: {len(self.validation_framework)}
- Quality Gates: Configured
- Test Frameworks: Identified

### Context Documentation
- Documentation Files: {len(self.context_documentation.get('readme_files', []))} README files
- API Documentation: {len(self.context_documentation.get('api_docs', []))} API docs
- Setup Documentation: Available

### Integration Points
- Dependencies Analyzed: {len(getattr(self, 'integration_points', {}).get('dependencies', []))}
- Configuration Points: Identified
- External Services: Catalogued

## Ready for PRP Generation ✅
The Context Engineering analysis is complete and ready to generate comprehensive 
Product Requirements Prompts following PRD template methodology.

## Complete Traceability ✅
Every agent interaction has been saved for full audit trail and reproducibility.
"""
        
        with open(os.path.join(self.output_dir, "analysis_summary.md"), "w") as f:
            f.write(summary)
        
        print(f"📋 Analysis summary saved following PRD methodology")
        print(f"📋 Complete agent interaction audit trail available")

    def _perform_fallback_analysis(self):
        """Perform fallback analysis if main analysis fails."""
        print("🔄 Performing fallback Context Engineering analysis...")
        
        # Basic fallback analysis
        self.codebase_analysis = {"analysis_method": "fallback", "basic_structure": "analyzed"}
        self.pattern_library = {"patterns_identified": 0, "fallback_mode": True}
        self.validation_framework = {"basic_validation": ["pytest", "ruff check"]}
        
        print("✅ Fallback analysis complete")

    def generate_feature_prp(self, feature_request: str) -> str:
        """Generate a comprehensive PRP for a specific feature request following PRD methodology."""
        print(f"🎯 Generating comprehensive PRP following PRD template for: {feature_request}")
        
        # Use all available context following PRD methodology
        full_context = {
            "codebase_analysis": self.codebase_analysis,
            "pattern_library": self.pattern_library,
            "integration_points": getattr(self, 'integration_points', {}),
            "validation_framework": self.validation_framework,
            "context_documentation": self.context_documentation
        }
        
        prp = self.generate_comprehensive_prp(feature_request, full_context)
        
        # If auto_analyze was True and we have agent interactions, create combined response
        if hasattr(self, 'agent_interactions') and self.agent_interactions and len(self.agent_interactions) > 0:
            print(f"📊 Creating combined response with {len(self.agent_interactions)} agent interactions...")
            return self._generate_combined_analysis(feature_request)
        
        # Otherwise just save and return the PRP
        safe_filename = feature_request.lower().replace(' ', '_').replace('-', '_')[:50]
        prp_path = os.path.join(self.output_dir, "PRPs", f"{safe_filename}.md")
        
        with open(prp_path, "w") as f:
            f.write(prp)
        
        print(f"📄 Comprehensive PRP following PRD template saved to: {prp_path}")
        return prp

    def execute_prp(self, prp_file_path: str) -> Dict[str, Any]:
        """Execute a PRP following PRD methodology (placeholder for future implementation)."""
        print(f"🚀 PRP execution capability - ready for implementation following PRD methodology")
        return {"status": "ready", "prp_file": prp_file_path}

    def start(self, input_text: str) -> str:
        """Start Context Engineering analysis with structured input parsing."""
        print(f"🚀 Starting Context Engineering analysis with structured input parsing...")
        
        # First, parse the input to extract codebase and goal
        parsed_input = self._parse_structured_input(input_text)
        
        codebase = parsed_input.get('codebase', '')
        goal = parsed_input.get('goal', '')
        
        print(f"📊 Parsed Input:")
        print(f"   🔗 Codebase: {codebase}")
        print(f"   🎯 Goal: {goal}")
        
        if codebase:
            if codebase.startswith(('http://', 'https://')):
                # Handle GitHub URL analysis with specific goal
                if 'github.com' in codebase:
                    print(f"🌐 GitHub repository analysis focused on goal: {goal}")
                    return self._analyze_github_with_goal(codebase, goal)
                else:
                    print(f"🌐 General URL analysis focused on goal: {goal}")
                    return self._analyze_url_with_goal(codebase, goal)
            else:
                # Handle local path analysis with specific goal
                if os.path.exists(codebase):
                    print(f"📁 Local codebase analysis focused on goal: {goal}")
                    self.project_path = codebase
                    self._perform_context_engineering_analysis()
                    return self._generate_goal_focused_analysis(codebase, goal)
                else:
                    print(f"⚠️ Codebase path not found: {codebase}, using current project path")
                    return self._generate_goal_focused_analysis(self.project_path, goal)
        else:
            # No specific codebase provided, use current directory
            print(f"📁 Using current directory with goal: {goal}")
            return self._generate_goal_focused_analysis(self.project_path, goal)

    def _parse_structured_input(self, input_text: str) -> Dict[str, str]:
        """Parse structured input to extract codebase and goal using a specialized agent."""
        print("  🤖 Creating Structured Input Parser Agent...")
        
        parser_agent = Agent(
            name="Structured Input Parser",
            role="Expert Input Analysis and Extraction Specialist",
            goal="Extract codebase URLs/paths and implementation goals from user input",
            instructions="""You are an expert at parsing user input to extract structured information.
            
            From the provided input, extract:
            1. CODEBASE: Any GitHub URLs, repository paths, or local directory paths mentioned
            2. GOAL: The specific task, feature, or implementation goal the user wants to achieve
            
            Rules for extraction:
            - Look for GitHub URLs (https://github.com/owner/repo)
            - Look for local paths (/path/to/directory)
            - Look for implementation goals (add authentication, implement feature X, etc.)
            - If multiple goals are mentioned, combine them into a coherent objective
            - If no explicit codebase is mentioned, return empty string for codebase
            - Always extract a meaningful goal even if it's implied
            
            Return your analysis in this exact format:
            CODEBASE: [extracted codebase URL or path]
            GOAL: [extracted implementation goal]
            
            Be precise and extract only what is explicitly mentioned or clearly implied.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        prompt = f"""Parse this user input to extract codebase and goal:

USER INPUT: {input_text}

Extract the codebase (GitHub URL, repository path, or local directory) and the implementation goal.
Return in the exact format specified in your instructions."""
        
        print("  🔍 Parsing structured input...")
        response = self._chat_with_agent_and_save(parser_agent, prompt, "INPUT_PARSING")
        
        # Parse the response to extract codebase and goal
        parsed = self._extract_codebase_and_goal(response)
        
        print(f"  ✅ Input parsing complete: Codebase='{parsed.get('codebase', '')}', Goal='{parsed.get('goal', '')}'")
        return parsed

    def _extract_codebase_and_goal(self, parser_response: str) -> Dict[str, str]:
        """Extract codebase and goal from parser agent response."""
        codebase = ""
        goal = ""
        
        lines = parser_response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('CODEBASE:'):
                codebase = line.replace('CODEBASE:', '').strip()
            elif line.startswith('GOAL:'):
                goal = line.replace('GOAL:', '').strip()
        
        # Fallback parsing if format wasn't followed exactly
        if not codebase or not goal:
            # Look for GitHub URLs
            import re
            github_pattern = r'https://github\.com/[^\s]+'
            github_matches = re.findall(github_pattern, parser_response)
            if github_matches and not codebase:
                codebase = github_matches[0]
            
            # Look for common goal keywords
            goal_keywords = ['add', 'implement', 'create', 'build', 'develop', 'need to', 'authentication', 'feature']
            if not goal:
                for keyword in goal_keywords:
                    if keyword.lower() in parser_response.lower():
                        # Extract sentence containing the keyword
                        sentences = parser_response.split('.')
                        for sentence in sentences:
                            if keyword.lower() in sentence.lower():
                                goal = sentence.strip()
                                break
                        if goal:
                            break
        
        return {
            'codebase': codebase,
            'goal': goal or "Comprehensive codebase analysis and context generation"
        }

    def _analyze_github_with_goal(self, github_url: str, goal: str) -> str:
        """Analyze GitHub repository with gitingest, focusing on specific goal."""
        print(f"  🌐 Analyzing GitHub repository with goal focus...")
        
        # Step 1: Get complete repository structure and file listing
        print("  📊 Step 1: Getting complete repository structure...")
        repo_structure = self._get_repository_structure(github_url)
        
        # Step 2: Have agent select relevant files based on goal
        print("  🎯 Step 2: Agent selecting relevant files for goal...")
        selected_files = self._select_relevant_files_for_goal(repo_structure, goal, github_url)
        
        # Step 3: Analyze only selected files with gitingest
        print("  📋 Step 3: Analyzing selected files with gitingest...")
        return self._analyze_selected_files(github_url, goal, selected_files)

    def _get_repository_structure(self, github_url: str) -> Dict[str, Any]:
        """Get complete repository structure with detailed file metadata."""
        self.log_debug("Starting repository structure analysis", github_url=github_url)
        
        try:
            # Step 1: Get basic file structure
            print("    📋 Getting basic repository structure...")
            self.log_debug("Getting basic repository structure")
            basic_structure = self._get_basic_structure(github_url)
            self.log_debug("Basic structure obtained", file_count=basic_structure.get('file_count', 0))
            
            # Step 2: Get enhanced metadata for key files
            print("    🔍 Extracting detailed file metadata...")
            self.log_debug("Starting enhanced metadata extraction")
            enhanced_structure = self._get_enhanced_file_metadata(github_url, basic_structure)
            self.log_debug("Enhanced metadata extraction complete", 
                           enhanced=enhanced_structure.get('enhanced', False),
                           metadata_length=len(enhanced_structure.get('file_metadata', '')))
            
            return enhanced_structure
                
        except Exception as e:
            print(f"    ⚠️ Repository structure analysis failed: {e}")
            self.log_debug("Repository structure analysis failed", error=str(e))
            return {
                "method": "failed",
                "structure": "Unable to retrieve repository structure",
                "file_count": 0,
                "success": False
            }

    def _get_basic_structure(self, github_url: str) -> Dict[str, Any]:
        """Get basic repository file structure."""
        try:
            # Try using gitingest with structure-only flag first
            result = _get_subprocess().run(
                ["gitingest", github_url, "--tree-only", "--output", "-"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return {
                    "method": "gitingest_tree",
                    "structure": result.stdout,
                    "file_count": result.stdout.count('\n'),
                    "success": True
                }
            else:
                print(f"    ⚠️ Gitingest tree failed, using GitHub API...")
                return self._get_structure_fallback(github_url)
                
        except (_get_subprocess().TimeoutExpired, FileNotFoundError) as e:
            print(f"    ⚠️ Gitingest not available: {e}, using GitHub API...")
            return self._get_structure_fallback(github_url)

    def _get_enhanced_file_metadata(self, github_url: str, basic_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Extract enhanced metadata including functions, classes, and docstrings."""
        print("    🔍 Extracting detailed file metadata...")
        
        # Step 1: Get raw content from repository
        sample_content = self._get_repository_sample_content(github_url, basic_structure.get('structure', ''))
        
        # Step 2: Parse the content to extract structured metadata
        parsed_metadata = self._parse_code_metadata(sample_content, basic_structure)
        
        # DEBUG: Check what metadata was actually parsed
        print(f"    🔍 DEBUG: Parsed metadata length: {len(parsed_metadata)} chars")
        print(f"    🔍 DEBUG: Metadata preview: {parsed_metadata[:200]}...")
        
        # Step 3: Create enhanced structure with parsed metadata
        enhanced_structure = {
            "method": "enhanced_metadata",
            "basic_structure": basic_structure,
            "file_metadata": parsed_metadata,
            "file_count": basic_structure.get('file_count', 0),
            "success": True,
            "enhanced": True
        }
        
        print(f"    ✅ Enhanced structure created with metadata length: {len(enhanced_structure.get('file_metadata', ''))}")
        return enhanced_structure

    def _parse_code_metadata(self, sample_content: str, basic_structure: Dict[str, Any]) -> str:
        """Parse code content to extract functions, classes, docstrings, and other metadata."""
        print("  🤖 Creating Code Metadata Parser Agent...")
        
        # Check if we have actual content to parse
        if not sample_content or len(sample_content.strip()) < 100:
            print("    ⚠️ No substantial content available for metadata parsing")
            return """
METADATA EXTRACTION STATUS: Limited content available

BASIC FILE STRUCTURE ANALYSIS:
- Repository appears to contain Python, JavaScript, and configuration files
- Authentication-related files likely in: auth/, user/, login/, security/ directories
- Configuration files: settings.py, config.py, .env files
- API files: api/, routes/, endpoints/ directories

RECOMMENDED FILE SELECTION APPROACH:
- Look for files with 'auth', 'login', 'user', 'security' in names
- Include main application files (app.py, main.py, server.py)
- Include configuration files (settings.py, config.py)
- Include API route files
- Include requirements.txt, package.json for dependencies

Note: Detailed function/class metadata not available due to content access limitations.
"""
        
        # Truncate sample content if too large to prevent context overflow
        max_content_length = 60000  # Increased from 50K to 60K for better metadata
        if len(sample_content) > max_content_length:
            sample_content = sample_content[:max_content_length] + "\n\n... [Content truncated for analysis] ..."
            print(f"    📏 Sample content truncated to {max_content_length} chars for metadata parsing")
        
        metadata_parser = Agent(
            name="Code Metadata Parser",
            role="Expert Code Analysis and Metadata Extraction Specialist",
            goal="Parse code content to extract detailed metadata including functions, classes, and docstrings",
            instructions="""You are an expert at parsing code content and extracting structured metadata.

            From the provided code content, extract detailed metadata for each file:
            
            FOR PYTHON FILES (.py):
            - FUNCTIONS: Extract function names with their docstrings and parameters
              Format: "function_name(params): docstring_summary"
            - CLASSES: Extract class names with their docstrings and key methods
              Format: "ClassName: docstring_summary, methods: [method1, method2]"
            - MODULE_DOCSTRING: Top-level file description
            - KEY_IMPORTS: Important imports and dependencies
            - DECORATORS: Common decorators used (@app.route, @property, etc.)
            
            FOR JAVASCRIPT/TYPESCRIPT FILES (.js, .ts, .jsx, .tsx):
            - FUNCTIONS: Function names and purposes
            - CLASSES/COMPONENTS: React components or ES6 classes
            - EXPORTS: What the file exports
            - IMPORTS: Key dependencies
            
            FOR CONFIGURATION FILES (.json, .toml, .yaml, .env):
            - PURPOSE: What this configuration controls
            - KEY_SECTIONS: Main configuration categories
            - DEPENDENCIES: Packages or services configured
            
            FOR DOCUMENTATION FILES (.md, .rst, .txt):
            - TITLE: Document title/purpose
            - SECTIONS: Main topics covered
            - API_DOCS: If it documents APIs or functions
            
            **CRITICAL**: Return structured data that clearly shows:
            1. File name and type
            2. Functions/classes with their purposes
            3. Key imports and dependencies
            4. Configuration purposes
            5. Documentation topics
            
            Make the output easy for a file selection agent to understand which files contain what functionality.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        structure_text = basic_structure.get('structure', '')
        
        prompt = f"""Parse this repository content to extract detailed metadata:

REPOSITORY STRUCTURE:
{structure_text}

REPOSITORY CONTENT TO PARSE:
{sample_content}

Extract structured metadata for each file showing:
- Functions and their purposes
- Classes and their purposes  
- Key imports and dependencies
- Configuration sections
- Documentation topics

Focus on creating clear, structured metadata that will help with intelligent file selection."""
        
        print("  🔍 Code Parser extracting functions, classes, and docstrings...")
        response = self._chat_with_agent_and_save(metadata_parser, prompt, "CODE_METADATA_PARSING")
        
        # Ensure we return the actual parsed metadata response
        print(f"    ✅ Extracted metadata length: {len(response)} characters")
        if len(response) < 100:
            print("    ⚠️ Warning: Very short metadata response - may indicate parsing issues")
        
        return response

    def _get_repository_sample_content(self, github_url: str, structure_text: str) -> str:
        """Get actual code content from key repository files for metadata extraction."""
        try:
            print("    📋 Getting actual code content from repository files...")
            
            # Validate GitHub token first
            github_token = os.getenv('GITHUB_TOKEN')
            if github_token:
                print(f"    🔑 GitHub token found: {github_token[:8]}...{github_token[-4:]} (length: {len(github_token)})")
                
                # Validate token format
                import re
                github_pat_pattern = r"^(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59})$"
                if not re.match(github_pat_pattern, github_token):
                    print("    ⚠️ Token format looks invalid - may cause authentication issues")
                    print("    📝 Valid formats: ghp_xxxx or github_pat_xxxx")
                else:
                    print("    ✅ Token format is valid")
                    
                # Quick test of token validity
                try:
                    import requests
                    test_headers = {'Authorization': f'Bearer {github_token}'}
                    test_response = requests.get('https://api.github.com/user', headers=test_headers, timeout=5)
                    if test_response.status_code == 200:
                        user_data = test_response.json()
                        print(f"    ✅ Token is valid for user: {user_data.get('login')}")
                    elif test_response.status_code == 401:
                        print("    ❌ Token is invalid or expired!")
                        print("    📝 Generate new token at: https://github.com/settings/tokens")
                    elif test_response.status_code == 403:
                        print("    ❌ Token lacks required permissions!")
                        print("    📝 Required scopes: 'repo' or 'public_repo'")
                    else:
                        print(f"    ⚠️ Unexpected token test result: {test_response.status_code}")
                except Exception as e:
                    print(f"    ⚠️ Could not validate token: {e}")
            else:
                print("    ⚠️ No GitHub token found - may hit rate limits")
            
            # Try gitingest Python package first for actual content
            try:
                from gitingest import ingest
                print("    🔧 Using gitingest Python package to fetch actual code content...")
                
                # Get comprehensive content including actual code
                # Use better limits for codebase overview while avoiding context overflow
                summary, tree, content = ingest(
                    github_url, 
                    max_file_size=10000,  # 10KB per file for better overview (was 5KB)
                    include_patterns={'*.py', '*.js', '*.ts', '*.json', '*.md', '*.yaml', '*.toml'},  # Include more file types for overview
                    exclude_patterns={'*test*', '*__pycache__*', '*.pyc', '*migrations*', '*node_modules*', '*.min.js', '*.bundle.js'},  # Exclude generated/test files
                    token=github_token
                )
                
                # More conservative truncation to ensure we keep actual code content
                max_content_for_metadata = 80000  # 80K chars for metadata extraction
                if len(content) > max_content_for_metadata:
                    # Keep the beginning (which has most file headers) and truncate the rest
                    content = content[:max_content_for_metadata] + "\n\n... [Content truncated but metadata extracted from available content] ..."
                    print(f"    📏 Content size: {len(content)}, keeping first {max_content_for_metadata} chars for metadata")
                
                # Return actual code content for parsing - this is crucial for metadata extraction
                return f"REPOSITORY SUMMARY:\n{summary}\n\nFILE TREE:\n{tree}\n\nACTUAL CODE CONTENT:\n{content}"
                
            except ImportError:
                print("    ⚠️ gitingest Python package not available, using command line...")
                
                # Fallback to command line gitingest for actual content
                result = _get_subprocess().run(
                    ["gitingest", github_url, "--output", "-"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    # This should contain actual file contents, not just structure
                    return result.stdout
                else:
                    print(f"    ⚠️ Gitingest command failed: {result.stderr}")
                    return self._get_github_sample_files(github_url, structure_text)
                    
        except Exception as e:
            print(f"    ⚠️ Sample content extraction failed: {e}")
            return self._get_github_sample_files(github_url, structure_text)

    def _get_github_sample_files(self, github_url: str, structure_text: str) -> str:
        """Fallback to get sample file contents directly from GitHub."""
        try:
            print("    🔄 Attempting to fetch sample file contents from GitHub...")
            
            # Extract repo info
            repo_parts = github_url.replace('https://github.com/', '').strip('/')
            
            # Check for GitHub token for better rate limits
            github_token = os.getenv('GITHUB_TOKEN')
            headers = {}
            if github_token:
                headers['Authorization'] = f'Bearer {github_token}'  # Use Bearer instead of token
                print("    🔑 Using GitHub token for enhanced rate limits")
            
            # Select important files to fetch content from
            important_files = []
            for line in structure_text.split('\n'):
                line = line.strip()
                if line and any(ext in line for ext in ['.py', '.js', '.ts', '.json', '.md']):
                    # Prioritize likely important files
                    if any(keyword in line.lower() for keyword in [
                        'main', 'app', 'server', 'index', 'config', 'setup', 
                        'auth', 'user', 'login', 'api', 'route', 'model'
                    ]):
                        important_files.append(line)
                        if len(important_files) >= 10:  # Limit to avoid too many API calls
                            break
            
            # Fetch content from important files
            file_contents = []
            for file_path in important_files[:5]:  # Limit to 5 files to avoid rate limits
                try:
                    api_url = f"https://api.github.com/repos/{repo_parts}/contents/{file_path}"
                    
                    import urllib.request
                    import json
                    import base64
                    
                    request = urllib.request.Request(api_url, headers=headers)
                    
                    with urllib.request.urlopen(request) as response:
                        file_data = json.loads(response.read())
                        
                    if file_data.get('content') and file_data.get('encoding') == 'base64':
                        content = base64.b64decode(file_data['content']).decode('utf-8')
                        file_contents.append(f"\n--- FILE: {file_path} ---\n{content[:2000]}")  # First 2000 chars
                        
                except Exception as e:
                    print(f"    ⚠️ Failed to fetch {file_path}: {e}")
                    continue
            
            if file_contents:
                return f"SAMPLE FILE CONTENTS:\n{''.join(file_contents)}"
            else:
                return "No sample content available - file fetching failed"
                
        except Exception as e:
            print(f"    ⚠️ GitHub sample file fetching failed: {e}")
            return "No sample content available - GitHub API failed"

    def _select_relevant_files_for_goal(self, repo_structure: Dict[str, Any], goal: str, github_url: str) -> List[str]:
        """Have an agent intelligently select relevant files based on goal and enhanced metadata."""
        print("  🤖 Creating Enhanced File Selection Agent...")
        
        file_selector = Agent(
            name="Enhanced File Selection Agent",
            role="Expert File Selection Specialist with Metadata Analysis",
            goal=f"Select most relevant files for implementing: {goal}",
            instructions=f"""You are an expert at selecting the most relevant files from a repository for a specific goal: {goal}

            You have access to enhanced metadata including:
            - File structure and organization
            - Functions and classes in each file
            - Docstrings and descriptions
            - Configuration purposes
            - Documentation coverage
            - Import dependencies

            CORE FILES TO ALWAYS INCLUDE (if they exist):
            - README.md, setup.py, pyproject.toml, package.json, requirements.txt
            - Main entry points: main.py, app.py, index.js, server.py
            - Configuration files: config.py, settings.py, .env.example
            - Key documentation: CONTRIBUTING.md, API.md, docs/

            GOAL-SPECIFIC SELECTION for "{goal}":
            - Files with functions/classes directly related to goal keywords
            - Files mentioned in docstrings related to the goal
            - Configuration files that would need updates for the goal
            - Test files that cover similar functionality
            - Documentation that explains related features
            - Dependencies and imports relevant to the goal

            ENHANCED SELECTION CRITERIA:
            1. Core project files (always include)
            2. Files with functions/classes matching goal keywords
            3. Files with docstrings mentioning goal-related concepts
            4. Files in directories related to the goal
            5. Configuration files that would be affected
            6. Test files for related functionality
            7. Documentation explaining similar features
            8. Dependency files showing required packages

            METADATA-BASED PRIORITIZATION:
            - High Priority: Files with functions/classes directly implementing goal features
            - Medium Priority: Files with related functionality or configuration
            - Low Priority: Files with tangential connections
            
            Use the enhanced metadata to make intelligent decisions about file relevance.
            
            Return ONLY a Python list of file paths, like:
            ["README.md", "src/auth/login.py", "config/settings.py", ...]
            
            Maximum 50 files for efficient analysis.""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        # Prepare enhanced structure information
        basic_structure = repo_structure.get('basic_structure', {}).get('structure', '')
        file_metadata = repo_structure.get('file_metadata', '')
        file_count = repo_structure.get('file_count', 0)
        
        # DEBUG: Check what metadata is actually available
        print(f"    🔍 DEBUG: Received metadata length: {len(file_metadata)} chars")
        print(f"    🔍 DEBUG: Enhanced flag: {repo_structure.get('enhanced', False)}")
        print(f"    🔍 DEBUG: Metadata preview: {file_metadata[:200] if file_metadata else 'NO METADATA'}...")
        
        prompt = f"""Select the most relevant files for goal: {goal}

REPOSITORY: {github_url}
GOAL: {goal}
TOTAL FILES: {file_count}
ENHANCED METADATA AVAILABLE: {repo_structure.get('enhanced', False)}

REPOSITORY STRUCTURE:
{basic_structure}

PARSED CODE METADATA (Functions, Classes, Docstrings):
{file_metadata}

Based on the goal "{goal}" and the parsed metadata showing actual functions/classes/docstrings:"""
        
        # DEBUG: Verify f-string substitution worked
        print(f"    🔍 DEBUG: Variable values before f-string:")
        print(f"    🔍 DEBUG: goal = '{goal}'")
        print(f"    🔍 DEBUG: file_count = {file_count}")
        print(f"    🔍 DEBUG: enhanced = {repo_structure.get('enhanced', False)}")
        print(f"    🔍 DEBUG: file_metadata is None: {file_metadata is None}")
        print(f"    🔍 DEBUG: file_metadata is empty string: {repr(file_metadata == '')}")
        print(f"    🔍 DEBUG: type(file_metadata) = {type(file_metadata)}")
        
        # Continue building the prompt
        prompt += """

INTELLIGENT SELECTION CRITERIA:
1. **FUNCTION-LEVEL MATCHING**: Select files that contain functions directly related to "{goal}"
2. **CLASS-LEVEL MATCHING**: Select files with classes that handle "{goal}" functionality  
3. **DOCSTRING MATCHING**: Select files whose docstrings mention "{goal}" concepts
4. **DEPENDENCY MATCHING**: Select files that import libraries relevant to "{goal}"
5. **CONFIGURATION MATCHING**: Select config files that would need updates for "{goal}"
6. **TEST MATCHING**: Select test files that cover "{goal}" functionality
7. **DOCUMENTATION MATCHING**: Select docs that explain "{goal}" or similar features

EXAMPLES FOR AUTHENTICATION GOAL:
- Files with functions like: login(), authenticate(), verify_token()
- Files with classes like: User, AuthManager, SecurityHandler
- Files with docstrings mentioning: "authentication", "login", "security", "user management"
- Files importing: jwt, bcrypt, passport, oauth libraries
- Config files with: security settings, database user models, API keys
- Test files testing: login flows, authentication endpoints
- Docs explaining: API authentication, user management

Use the detailed metadata to make precise selections based on actual code content, not just filenames.

Return as a Python list: ["file1.py", "file2.js", ...]
Maximum 50 files.""".format(goal=goal)
        
        print("  🔍 Enhanced File Selector analyzing metadata...")
        
        # DEBUG: Show the actual prompt being sent
        print(f"    🔍 DEBUG: Full prompt length: {len(prompt)} chars")
        print(f"    🔍 DEBUG: Prompt preview (first 500 chars):")
        print(f"    {prompt[:500]}...")
        
        # DEBUG: Check specifically for metadata in the prompt
        metadata_start = prompt.find("PARSED CODE METADATA")
        if metadata_start != -1:
            metadata_section = prompt[metadata_start:metadata_start+1000]
            print(f"    🔍 DEBUG: Found metadata section at position {metadata_start}:")
            print(f"    {metadata_section}...")
        else:
            print(f"    ❌ DEBUG: 'PARSED CODE METADATA' section NOT FOUND in prompt!")
            
        # DEBUG: Check the actual file_metadata variable content
        print(f"    🔍 DEBUG: file_metadata variable length: {len(file_metadata)}")
        print(f"    🔍 DEBUG: file_metadata first 300 chars: {file_metadata[:300]}...")
        
        response = self._chat_with_agent_and_save(file_selector, prompt, "ENHANCED_FILE_SELECTION")
        
        # Parse the response to extract file list
        selected_files = self._parse_file_list_from_response(response)
        
        print(f"  ✅ Selected {len(selected_files)} relevant files from {file_count} total files using enhanced metadata")
        return selected_files

    def _parse_file_list_from_response(self, response: str) -> List[str]:
        """Parse file list from agent response."""
        import re
        
        # Look for Python list pattern
        list_pattern = r'\[(.*?)\]'
        matches = re.findall(list_pattern, response, re.DOTALL)
        
        if matches:
            # Take the first list found
            list_content = matches[0]
            # Extract quoted strings
            file_pattern = r'["\']([^"\']+)["\']'
            files = re.findall(file_pattern, list_content)
            return files[:50]  # Limit to 50 files
        
        # Fallback: look for lines that look like file paths
        lines = response.split('\n')
        files = []
        for line in lines:
            line = line.strip()
            if line and ('.' in line or '/' in line) and not line.startswith('#'):
                # Remove quotes and clean up
                clean_line = line.strip('"\'`- ')
                if clean_line and not clean_line.startswith('//'):
                    files.append(clean_line)
                    if len(files) >= 50:
                        break
        
        return files

    def _analyze_selected_files(self, github_url: str, goal: str, selected_files: List[str]) -> str:
        """Analyze only the selected relevant files with gitingest."""
        print(f"  🔍 Creating Focused Repository Analyzer for {len(selected_files)} files...")
        
        # Try to get content for selected files only
        if selected_files:
            focused_content = self._get_focused_content(github_url, selected_files)
        else:
            print("  ⚠️ No files selected, falling back to full analysis...")
            focused_content = self._run_gitingest_for_github(github_url)
        
        focused_analyzer = Agent(
            name="Focused Repository Analyst",
            role="Expert Repository Analysis Specialist with Focused File Selection",
            goal=f"Analyze selected repository files specifically for implementing: {goal}",
            instructions=f"""You are analyzing carefully selected files from a GitHub repository with this specific goal: {goal}
            
            These files were intelligently selected to be most relevant for: {goal}
            
            Focus your analysis on:
            1. GOAL-RELEVANT COMPONENTS: How these files relate to {goal}
            2. ARCHITECTURE: How {goal} should fit into the existing architecture
            3. PATTERNS: Existing implementation patterns to follow for {goal}
            4. DEPENDENCIES: What dependencies are needed for {goal}
            5. TESTING: How to test the {goal} implementation
            6. INTEGRATION: How {goal} integrates with existing features
            7. CONFIGURATION: Setup and configuration needs for {goal}
            8. EXAMPLES: Similar features that can guide {goal} implementation
            
            Since these files were pre-selected for relevance, provide deep analysis of how each contributes to implementing: {goal}""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        prompt = f"""Analyze these carefully selected repository files for implementing: {goal}

REPOSITORY: {github_url}
GOAL: {goal}
SELECTED FILES: {len(selected_files)}

FILES ANALYZED:
{', '.join(selected_files[:20])}{'...' if len(selected_files) > 20 else ''}

FOCUSED CONTENT:
{focused_content[:30000] if focused_content else "No content available"}

Provide comprehensive analysis focused specifically on implementing the goal: {goal}
Since these files were pre-selected for relevance, explain how each contributes to the goal."""
        
        print("  🔍 Focused Analyzer processing selected files...")
        analysis_response = self._chat_with_agent_and_save(focused_analyzer, prompt, "FOCUSED_FILE_ANALYSIS")
        
        # Generate goal-focused PRP
        return self._generate_goal_focused_prp(github_url, goal, analysis_response, selected_files)

    def _run_gitingest_for_github(self, github_url: str) -> str:
        """Run gitingest analysis specifically for GitHub repositories."""
        try:
            # Try using gitingest Python package first
            try:
                from gitingest import ingest
                print(f"    🔧 Using gitingest Python package for GitHub repository...")
                summary, tree, content = ingest(github_url)
                return f"SUMMARY:\n{summary}\n\nTREE:\n{tree}\n\nCONTENT:\n{content}"
            except ImportError:
                print(f"    ⚠️ gitingest Python package not available, trying command line...")
                # Fallback to command line gitingest
                result = _get_subprocess().run(
                    ["gitingest", github_url, "--output", "-"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    return result.stdout
                else:
                    print(f"    ⚠️ Gitingest command failed: {result.stderr}")
                    return None
                    
        except _get_subprocess().TimeoutExpired:
            print("    ⚠️ Gitingest analysis timed out")
            return None
        except FileNotFoundError:
            print("    ⚠️ Gitingest not found")
            return None
        except Exception as e:
            print(f"    ⚠️ Gitingest error: {e}")
            return None

    def _get_focused_content(self, github_url: str, selected_files: List[str]) -> str:
        """Get content for only the selected files."""
        try:
            # For now, fallback to full analysis since gitingest file filtering might not be available
            print(f"    📋 Getting focused content for {len(selected_files)} selected files...")
            return self._run_gitingest_for_github(github_url)
                
        except Exception as e:
            print(f"    ⚠️ Focused content extraction failed: {e}")
            return self._run_gitingest_for_github(github_url)

    def _generate_goal_focused_prp(self, codebase: str, goal: str, analysis_response: str, selected_files: Union[List[str], List[Dict]] = None) -> str:
        """Generate a comprehensive PRP focused on the specific goal."""
        print(f"  📝 Creating Goal-Focused PRP Generator...")
        
        prp_generator = Agent(
            name="Goal-Focused PRP Generator",
            role="Expert Goal-Focused Product Requirements Prompt Specialist",
            goal=f"Generate comprehensive PRP for implementing: {goal}",
            instructions=f"""You are generating a comprehensive PRP specifically for this goal: {goal}
            
            Create a PRP following PRD template methodology that includes:
            
            ## Purpose
            Clear statement for implementing: {goal}
            
            ## Goal-Specific Context
            All context needed specifically for: {goal}
            
            ## Implementation Blueprint for {goal}
            - Specific files to modify for {goal}
            - New files needed for {goal}
            - Dependencies required for {goal}
            - Configuration changes for {goal}
            
            ## Goal-Focused Validation
            - Tests specific to {goal}
            - Quality gates for {goal}
            - Success criteria for {goal}
            
            Focus everything on successfully implementing: {goal}""",
            llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
        )
        
        chunk_info = ""
        if selected_files:
            chunk_info = f"\n\nSELECTED FILES ANALYZED:\n{len(selected_files)} files pre-selected for relevance"
        
        prompt = f"""Generate a comprehensive Goal-Focused PRP:

CODEBASE: {codebase}
GOAL: {goal}

REPOSITORY ANALYSIS:
{analysis_response}
{chunk_info}

Create a complete PRP following PRD template methodology, focused specifically on implementing: {goal}
Include all necessary context, implementation guidance, and validation for this specific goal."""
        
        print("  📝 Generating goal-focused PRP...")
        prp_response = self._chat_with_agent_and_save(prp_generator, prompt, "GOAL_FOCUSED_PRP_GENERATION")
        
        # Create final combined response
        all_responses = []
        
        # Add parsing response
        all_responses.append({
            "agent": "Structured Input Parser",
            "phase": "Input Analysis", 
            "response": f"Extracted Codebase: {codebase}\nExtracted Goal: {goal}"
        })
        
        # Add repository analysis
        all_responses.append({
            "agent": "Goal-Focused Repository Analyst",
            "phase": "Repository Analysis",
            "response": analysis_response
        })
        
        # Add chunk analyses if any
        if selected_files:
            for file_path in selected_files:
                all_responses.append({
                    "agent": "Intelligent File Selector",
                    "phase": "File Selection",
                    "response": f"Selected file: {file_path}"
                })
        
        # Add final PRP
        all_responses.append({
            "agent": "Goal-Focused PRP Generator",
            "phase": "Goal-Focused PRP Generation",
            "response": prp_response
        })
        
        # Create combined response focused on the goal
        return self._create_goal_focused_combined_response(all_responses, codebase, goal)

    def _generate_goal_focused_analysis(self, codebase: str, goal: str) -> str:
        """Generate goal-focused analysis for local codebase."""
        # If we have existing agent interactions from auto_analyze, incorporate them
        if hasattr(self, 'agent_interactions') and self.agent_interactions:
            return self._create_goal_focused_from_existing(codebase, goal)
        else:
            # Perform fresh analysis focused on the goal
            return self._perform_fresh_goal_analysis(codebase, goal)

    def _create_goal_focused_combined_response(self, agent_responses: List[Dict], codebase: str, goal: str) -> str:
        """Create a comprehensive PRP focused on the specific goal."""
        
        # Create comprehensive PRP content structured for LLM implementation
        prp_content = f"""# Product Requirements Prompt (PRP): {goal}

## 📋 Implementation Overview
**Target Codebase:** {codebase}  
**Implementation Goal:** {goal}  
**Analysis Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 🎯 Executive Summary
This comprehensive Product Requirements Prompt (PRP) provides all necessary context and implementation guidance for successfully implementing **{goal}** in the specified codebase. The analysis follows Context Engineering principles to ensure first-try implementation success.

## 📊 Repository Analysis
"""
        
        # Extract key information from agent responses
        repository_analysis = ""
        file_selections = ""
        implementation_guidance = ""
        
        for response_data in agent_responses:
            agent_name = response_data.get("agent", "")
            phase = response_data.get("phase", "")
            response = response_data.get("response", "")
            
            if "Repository" in phase or "Structure" in phase:
                repository_analysis += f"### {phase}\n{response}\n\n"
            elif "File Selection" in phase or "Enhanced File" in phase:
                file_selections += f"### {phase}\n{response}\n\n"
            elif "PRP Generation" in phase or "Analysis" in phase:
                implementation_guidance += f"### {phase}\n{response}\n\n"
            else:
                implementation_guidance += f"### {agent_name} - {phase}\n{response}\n\n"
        
        # Build structured PRP
        prp_content += repository_analysis
        
        if file_selections:
            prp_content += f"""## 📁 File Selection Strategy
{file_selections}"""
        
        prp_content += f"""## 🚀 Implementation Guidance
{implementation_guidance}

## ✅ Implementation Checklist
Based on the analysis above, follow these steps to implement **{goal}**:

1. **Review Selected Files**: Focus on the files identified in the analysis as most relevant to {goal}
2. **Follow Implementation Patterns**: Use the patterns and structures identified in the repository analysis
3. **Implement Core Functionality**: Based on the detailed guidance provided above
4. **Test Implementation**: Ensure the implementation works with existing codebase patterns
5. **Validate Goal Achievement**: Confirm that {goal} has been successfully implemented

## 🎯 Success Criteria
- [ ] {goal} functionality is fully implemented
- [ ] Implementation follows existing codebase patterns and conventions
- [ ] All identified files are properly updated
- [ ] Implementation is tested and validated
- [ ] Goal requirements are completely satisfied

## 📚 Context Engineering Benefits
This PRP provides:
- 🎯 **Goal-Focused Analysis**: Every insight directed toward implementing {goal}
- 🔧 **Repository Intelligence**: Deep understanding of codebase structure and patterns
- 📋 **Actionable Guidance**: Step-by-step implementation instructions
- ✅ **Quality Assurance**: Built-in validation and success criteria

**Result:** Complete implementation-ready PRP for {goal} in {codebase}
"""
        
        # Save output based on debug mode
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        safe_goal = goal.replace(' ', '_').replace('/', '_')[:50]
        
        if self.debug_mode:
            # Debug mode: Save comprehensive report + individual files (already saved)
            self.save_comprehensive_session_report()
            final_output_file = self.save_markdown_output(
                content=prp_content,
                filename=f"comprehensive_prp_{safe_goal}_{timestamp}",
                section_title=f"Comprehensive PRP: {goal}"
            )
            print(f"🐛 Debug mode: Comprehensive session report + individual files + final PRP saved")
        else:
            # Non-debug mode: Save ONLY the final comprehensive PRP directly in .praison/prp
            # Use clean filename: goal name + timestamp
            final_output_file = self.output_dir / f"{safe_goal}_prp_{timestamp}.md"
            final_output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Add markdown header for standalone file
            standalone_prp = f"""# Implementation PRP: {goal}

**Generated by ContextAgent**  
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Codebase:** {codebase}

---

{prp_content}

---
*This PRP contains all necessary context for implementing {goal}. Use this as your complete implementation guide.*
"""
            
            with open(final_output_file, "w", encoding="utf-8") as f:
                f.write(standalone_prp)
        
        print(f"✅ Implementation PRP complete with {len(self.agent_interactions)} agent interactions")
        print(f"📝 Final PRP saved: {final_output_file}")
        if not self.debug_mode:
            print(f"📋 Single file mode: Only comprehensive PRP saved (use LOGLEVEL=debug for detailed logs)")
        
        # Enhanced debug summary
        self.log_debug("Session completed", 
                       total_interactions=len(self.agent_interactions),
                       final_output=str(final_output_file),
                       goal=goal,
                       codebase=codebase,
                       debug_mode=self.debug_mode)
        
        return prp_content

    def _analyze_url_with_goal(self, url: str, goal: str) -> str:
        """Analyze general URL with specific goal focus."""
        return self.generate_feature_prp(f"Analyze {url} and implement {goal}")

    def _create_goal_focused_from_existing(self, codebase: str, goal: str) -> str:
        """Create goal-focused analysis from existing agent interactions."""
        # Filter and refocus existing interactions on the specific goal
        goal_focused_prp = self.generate_comprehensive_prp(
            f"Implement {goal} in {codebase}",
            {
                "codebase_analysis": self.codebase_analysis,
                "pattern_library": self.pattern_library,
                "integration_points": getattr(self, 'integration_points', {}),
                "validation_framework": self.validation_framework,
                "context_documentation": self.context_documentation,
                "specific_goal": goal
            }
        )
        
        return self._create_goal_focused_combined_response([
            {
                "agent": "Goal-Focused Context Refiner",
                "phase": "Goal-Focused Analysis",
                "response": goal_focused_prp
            }
        ], codebase, goal)

    def _perform_fresh_goal_analysis(self, codebase: str, goal: str) -> str:
        """Perform fresh analysis focused on the specific goal."""
        # Trigger analysis if not already done
        if not hasattr(self, 'codebase_analysis') or not self.codebase_analysis:
            self._perform_context_engineering_analysis()
        
        return self._generate_goal_focused_analysis(codebase, goal)

    def get_agent_interaction_summary(self) -> Dict[str, Any]:
        """Get summary of all agent interactions."""
        return {
            "total_interactions": len(self.agent_interactions),
            "phases_completed": list(set([interaction.get("phase", "") for interaction in self.agent_interactions])),
            "agents_used": list(set([interaction.get("agent_name", "") for interaction in self.agent_interactions])),
            "output_directory": self.output_dir,
            "interactions_saved": True
        }

    def _get_structure_fallback(self, github_url: str) -> Dict[str, Any]:
        """Fallback method to get repository structure using GitHub API."""
        try:
            # Extract repo info from URL
            repo_parts = github_url.replace('https://github.com/', '').strip('/')
            
            # Try using GitHub API for tree structure
            api_url = f"https://api.github.com/repos/{repo_parts}/git/trees/main?recursive=1"
            
            import urllib.request
            import json
            
            with urllib.request.urlopen(api_url) as response:
                data = json.loads(response.read())
                
            file_structure = []
            for item in data.get('tree', []):
                if item['type'] == 'blob':  # Files only
                    file_structure.append(item['path'])
            
            return {
                "method": "github_api",
                "structure": '\n'.join(file_structure),
                "file_count": len(file_structure),
                "success": True
            }
            
        except Exception as e:
            print(f"    ⚠️ GitHub API fallback failed: {e}")
            return {
                "method": "failed",
                "structure": "Unable to retrieve repository structure",
                "file_count": 0,
                "success": False
            }

    # ============================================================================
    # P1: Protocol-Compatible Aliases (ContextEngineerProtocol compliance)
    # ============================================================================
    
    def analyze_codebase(self, project_path: str) -> Dict[str, Any]:
        """
        Protocol-compatible alias for analyze_codebase_with_gitingest.
        
        Args:
            project_path: Path to the project directory
            
        Returns:
            Analysis results including patterns, architecture, conventions
        """
        return self.analyze_codebase_with_gitingest(project_path)
    
    def generate_prp(
        self, 
        feature_request: str, 
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Protocol-compatible alias for generate_comprehensive_prp.
        
        Args:
            feature_request: Description of the feature to implement
            context_analysis: Optional codebase analysis to include
            
        Returns:
            Comprehensive PRP document as string
        """
        return self.generate_comprehensive_prp(feature_request, context_analysis)
    
    def create_implementation_blueprint(
        self,
        feature_request: str,
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Protocol-compatible alias for build_implementation_blueprint.
        
        Args:
            feature_request: Description of the feature
            context_analysis: Optional codebase analysis
            
        Returns:
            Blueprint with implementation steps, files to modify, etc.
        """
        return self.build_implementation_blueprint(feature_request, context_analysis)

    # ============================================================================
    # P3: Async Methods (ContextEngineerProtocol compliance)
    # ============================================================================
    
    async def aanalyze_codebase(self, project_path: str) -> Dict[str, Any]:
        """
        Async version of analyze_codebase.
        
        Uses async subprocess for non-blocking execution.
        """
        asyncio = _get_asyncio()
        # Run sync method in executor for now (subprocess calls are blocking)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.analyze_codebase_with_gitingest,
            project_path
        )
    
    async def agenerate_prp(
        self,
        feature_request: str,
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Async version of generate_prp.
        """
        asyncio = _get_asyncio()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_comprehensive_prp(feature_request, context_analysis)
        )
    
    async def acreate_implementation_blueprint(
        self,
        feature_request: str,
        context_analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Async version of create_implementation_blueprint.
        """
        asyncio = _get_asyncio()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.build_implementation_blueprint(feature_request, context_analysis)
        )


def create_context_agent(llm: Optional[Union[str, Any]] = None, **kwargs) -> ContextAgent:
    """
    Factory function to create a ContextAgent following Context Engineering and PRD methodology.
    
    Args:
        llm: Language model to use (e.g., "gpt-4o-mini", "claude-3-haiku")
        **kwargs: Additional arguments to pass to ContextAgent constructor
        
    Returns:
        ContextAgent: Configured ContextAgent for comprehensive context generation following PRD principles
    """
    if llm is None:
        llm = "gpt-4o-mini"
    
    return ContextAgent(llm=llm, **kwargs)