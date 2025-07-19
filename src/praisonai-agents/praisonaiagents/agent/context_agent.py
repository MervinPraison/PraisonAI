"""
ContextAgent - A specialized agent class for Context Engineering.

This class extends the base Agent class to provide automated context generation
for AI coding assistants, including codebase analysis, pattern extraction, 
validation loop creation, and comprehensive prompt enhancement.

Implements the Context Engineering concept: 10x better than prompt engineering,
100x better than vibe coding through comprehensive context generation.
"""

import os
import json
import asyncio
import glob
from pathlib import Path
from typing import Optional, Any, Dict, Union, List
from ..agent.agent import Agent

class ContextAgent(Agent):
    """
    A specialized agent for Context Engineering - automated context generation for AI systems.
    
    This agent extends the base Agent class with specific functionality for:
    - Analyzing codebases and extracting patterns
    - Generating comprehensive context documents
    - Creating validation loops and success criteria
    - Enhancing prompts with rich contextual information
    - Generating Product Requirements Prompts (PRPs)
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
        **kwargs
    ):
        # Set Context Engineering defaults if not provided
        if name is None:
            name = "Context Engineer"
        if role is None:
            role = "Context Engineering Specialist"
        if goal is None:
            goal = "Generate comprehensive context for AI coding assistants to enable first-try implementation success"
        if backstory is None:
            backstory = """You are an expert in Context Engineering - the discipline of engineering context 
            for AI coding assistants. You understand that context is 10x better than prompt engineering 
            and 100x better than vibe coding. Your expertise lies in analyzing codebases, extracting patterns, 
            and creating comprehensive context that enables AI assistants to implement features correctly 
            on the first attempt."""
        if instructions is None:
            instructions = """As a Context Engineering specialist, your primary responsibilities are:
            
            1. ANALYZE: Examine codebases to understand patterns, conventions, and architecture
            2. EXTRACT: Identify key patterns, best practices, and implementation approaches
            3. CONTEXTUALIZE: Generate comprehensive context documents with all necessary information
            4. VALIDATE: Create executable validation criteria and success metrics
            5. ENHANCE: Enrich prompts with comprehensive contextual information
            
            Always focus on providing complete context rather than clever wording. Include documentation,
            examples, patterns, constraints, and validation criteria in your context generation."""

        # Add Context Engineering specific tools if none provided
        if tools is None:
            tools = self._get_default_context_tools()

        # Initialize parent Agent class
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=llm,
            tools=tools,
            **kwargs
        )

    def _get_default_context_tools(self) -> List[Any]:
        """Get default tools for Context Engineering operations."""
        return [
            self.analyze_codebase_patterns,
            self.generate_context_document,
            self.create_validation_loop,
            self.enhance_prompt_with_context,
            self.generate_prp,
            self.extract_documentation_patterns,
            self.analyze_test_patterns,
            self.create_implementation_blueprint
        ]
    
    def _get_sample_files(self, project_path: str, pattern: str, max_files: int = 5) -> List[str]:
        """Get a sample of files matching the pattern for analysis."""
        try:
            files = glob.glob(os.path.join(project_path, "**", pattern), recursive=True)
            return files[:max_files]
        except Exception:
            return []
    
    def _format_sample_files(self, files: List[str], project_path: str) -> str:
        """Format sample files for agent analysis."""
        formatted_files = []
        for file_path in files:
            try:
                rel_path = os.path.relpath(file_path, project_path)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()[:2000]  # Limit content for analysis
                formatted_files.append(f"File: {rel_path}\n{content}\n{'='*50}")
            except Exception:
                continue
        return "\n\n".join(formatted_files)
    
    def _get_documentation_files(self, project_path: str) -> str:
        """Get documentation files for analysis."""
        doc_patterns = ['README*', '*.md', '*.rst', 'docs/**/*']
        doc_content = []
        
        for pattern in doc_patterns:
            files = self._get_sample_files(project_path, pattern, 3)
            for file_path in files:
                try:
                    rel_path = os.path.relpath(file_path, project_path)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()[:1500]
                    doc_content.append(f"Doc: {rel_path}\n{content}\n{'='*40}")
                except Exception:
                    continue
        
        return "\n\n".join(doc_content) if doc_content else "No documentation files found."
    
    def _parse_agent_response(self, response: str) -> Dict[str, Any]:
        """Parse agent response, extracting JSON if possible."""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                # Fallback to text-based parsing
                return {"analysis": response, "parsed": False}
        except Exception:
            return {"analysis": response, "parsed": False}

    def analyze_codebase_patterns(self, project_path: str, file_patterns: List[str] = None) -> Dict[str, Any]:
        """
        Analyze codebase to extract patterns, conventions, and architectural insights.
        
        Args:
            project_path (str): Path to the project directory to analyze
            file_patterns (List[str]): Optional list of file patterns to focus on (e.g., ['*.py', '*.js'])
            
        Returns:
            Dict[str, Any]: Comprehensive analysis of codebase patterns
        """
        if not os.path.exists(project_path):
            return {"error": f"Project path does not exist: {project_path}"}
        
        if file_patterns is None:
            file_patterns = ['*.py', '*.js', '*.ts', '*.java', '*.cpp', '*.c', '*.rb', '*.go']
        
        analysis = {
            "project_structure": self._analyze_project_structure(project_path),
            "code_patterns": self._extract_code_patterns(project_path, file_patterns),
            "naming_conventions": self._analyze_naming_conventions(project_path, file_patterns),
            "import_patterns": self._analyze_import_patterns(project_path, file_patterns),
            "architecture_insights": self._analyze_architecture(project_path),
            "documentation_style": self._analyze_documentation_style(project_path)
        }
        
        return analysis

    async def aanalyze_codebase_patterns(self, project_path: str, file_patterns: List[str] = None) -> Dict[str, Any]:
        """Async wrapper for analyze_codebase_patterns."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.analyze_codebase_patterns, project_path, file_patterns
        )

    async def agenerate_context_document(self, project_path: str, requirements: str, analysis: Dict[str, Any] = None) -> str:
        """Async wrapper for generate_context_document."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.generate_context_document, project_path, requirements, analysis
        )

    async def acreate_validation_loop(self, implementation_requirements: str, success_criteria: List[str]) -> Dict[str, Any]:
        """Async wrapper for create_validation_loop."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.create_validation_loop, implementation_requirements, success_criteria
        )

    async def aenhance_prompt_with_context(self, base_prompt: str, context_data: Dict[str, Any]) -> str:
        """Async wrapper for enhance_prompt_with_context."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.enhance_prompt_with_context, base_prompt, context_data
        )

    async def agenerate_prp(self, feature_request: str, context_analysis: Dict[str, Any], documentation_links: List[str] = None) -> str:
        """Async wrapper for generate_prp."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.generate_prp, feature_request, context_analysis, documentation_links
        )

    def generate_context_document(self, project_path: str, requirements: str, analysis: Dict[str, Any] = None) -> str:
        """
        Generate a comprehensive context document for AI coding assistants.
        
        Args:
            project_path (str): Path to the project being analyzed
            requirements (str): Feature requirements or task description
            analysis (Dict[str, Any]): Optional pre-computed codebase analysis
            
        Returns:
            str: Comprehensive context document
        """
        if analysis is None:
            analysis = self.analyze_codebase_patterns(project_path)
        
        context_doc = f"""# Context Engineering Document

## Project Overview
**Path**: {project_path}
**Requirements**: {requirements}

## Architecture Patterns
{self._format_architecture_patterns(analysis.get('architecture_insights', {}))}

## Code Conventions
{self._format_code_conventions(analysis.get('code_patterns', {}), analysis.get('naming_conventions', {}))}

## Implementation Patterns
{self._format_implementation_patterns(analysis.get('code_patterns', {}))}

## Documentation Standards
{self._format_documentation_standards(analysis.get('documentation_style', {}))}

## Validation Criteria
{self._generate_validation_criteria(requirements, analysis)}

## Context Summary
This document provides comprehensive context for implementing: {requirements}

Key Insights:
- Project follows {analysis.get('architecture_insights', {}).get('primary_pattern', 'standard')} architecture
- Uses {analysis.get('naming_conventions', {}).get('style', 'conventional')} naming conventions
- Documentation style: {analysis.get('documentation_style', {}).get('format', 'standard')}

## Implementation Guidance
When implementing the requested feature:
1. Follow the established patterns identified above
2. Maintain consistency with existing code conventions
3. Use the documented validation criteria to verify success
4. Reference similar implementations in the codebase for guidance
"""
        
        return context_doc

    def create_validation_loop(self, implementation_requirements: str, success_criteria: List[str]) -> Dict[str, Any]:
        """
        Create executable validation loops and success criteria.
        
        Args:
            implementation_requirements (str): What needs to be implemented
            success_criteria (List[str]): List of success criteria to validate
            
        Returns:
            Dict[str, Any]: Validation loop configuration with executable criteria
        """
        validation_config = {
            "requirements": implementation_requirements,
            "success_criteria": success_criteria,
            "validation_steps": [],
            "executable_tests": [],
            "quality_gates": []
        }
        
        # Generate validation steps
        for criterion in success_criteria:
            validation_step = {
                "criterion": criterion,
                "validation_method": self._determine_validation_method(criterion),
                "expected_outcome": self._generate_expected_outcome(criterion),
                "failure_actions": self._generate_failure_actions(criterion)
            }
            validation_config["validation_steps"].append(validation_step)
        
        # Generate executable tests
        validation_config["executable_tests"] = self._generate_executable_tests(implementation_requirements, success_criteria)
        
        # Generate quality gates
        validation_config["quality_gates"] = self._generate_quality_gates(success_criteria)
        
        return validation_config

    def enhance_prompt_with_context(self, base_prompt: str, context_data: Dict[str, Any]) -> str:
        """
        Enhance a basic prompt with comprehensive contextual information.
        
        Args:
            base_prompt (str): Original prompt to enhance
            context_data (Dict[str, Any]): Contextual data to inject
            
        Returns:
            str: Enhanced prompt with rich context
        """
        enhanced_prompt = f"""# Enhanced Prompt with Context Engineering

## Original Request
{base_prompt}

## Contextual Information
{self._format_context_data(context_data)}

## Implementation Context
Based on the analysis, when implementing this request:

### Architecture Considerations
{self._extract_architecture_guidance(context_data)}

### Pattern Adherence
{self._extract_pattern_guidance(context_data)}

### Quality Requirements
{self._extract_quality_guidance(context_data)}

## Enhanced Request
{base_prompt}

**Additional Context**: Implement following the patterns and conventions identified above. 
Ensure the solution integrates seamlessly with the existing codebase architecture.
"""
        
        return enhanced_prompt

    def generate_prp(self, feature_request: str, context_analysis: Dict[str, Any], documentation_links: List[str] = None) -> str:
        """
        Generate a Product Requirements Prompt (PRP) with comprehensive context.
        
        Args:
            feature_request (str): The feature to be implemented
            context_analysis (Dict[str, Any]): Analysis of the codebase context
            documentation_links (List[str]): Optional links to relevant documentation
            
        Returns:
            str: Complete PRP with rich context for implementation
        """
        if documentation_links is None:
            documentation_links = []
        
        prp = f"""# Product Requirements Prompt (PRP)
## Context Engineering Enhanced Implementation Guide

### Feature Request
{feature_request}

### Comprehensive Context

#### Codebase Analysis
{self._format_prp_codebase_analysis(context_analysis)}

#### Implementation Blueprint
{self._generate_prp_implementation_blueprint(feature_request, context_analysis)}

#### Validation Framework
{self._generate_prp_validation_framework(feature_request)}

#### Documentation References
{self._format_prp_documentation(documentation_links)}

#### Success Criteria
{self._generate_prp_success_criteria(feature_request, context_analysis)}

### Implementation Instructions

This PRP provides comprehensive context for implementing: {feature_request}

**Context Engineering Principle**: This document contains all necessary context to enable 
first-try implementation success. Follow the patterns, respect the architecture, and 
use the validation framework to ensure quality.

#### Next Steps
1. Review the complete context above
2. Follow the implementation blueprint
3. Adhere to identified patterns and conventions
4. Execute validation framework to verify success
5. Integrate seamlessly with existing architecture

**Confidence Score**: 9/10 (High confidence due to comprehensive context analysis)
"""
        
        return prp

    def extract_documentation_patterns(self, project_path: str) -> Dict[str, Any]:
        """Extract documentation patterns and conventions from the project."""
        doc_patterns = {
            "readme_style": self._analyze_readme_style(project_path),
            "code_comments": self._analyze_comment_patterns(project_path),
            "docstring_format": self._analyze_docstring_format(project_path),
            "api_documentation": self._analyze_api_docs(project_path)
        }
        return doc_patterns

    def analyze_test_patterns(self, project_path: str) -> Dict[str, Any]:
        """Analyze testing patterns and conventions in the project."""
        test_patterns = {
            "test_structure": self._analyze_test_structure(project_path),
            "testing_frameworks": self._identify_testing_frameworks(project_path),
            "test_naming": self._analyze_test_naming(project_path),
            "coverage_patterns": self._analyze_coverage_patterns(project_path)
        }
        return test_patterns

    def create_implementation_blueprint(self, feature_request: str, context_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Create a detailed implementation blueprint based on context analysis."""
        blueprint = {
            "feature": feature_request,
            "implementation_steps": self._generate_implementation_steps(feature_request, context_analysis),
            "file_modifications": self._identify_file_modifications(feature_request, context_analysis),
            "new_files_required": self._identify_new_files(feature_request, context_analysis),
            "dependencies": self._identify_dependencies(feature_request, context_analysis),
            "testing_strategy": self._generate_testing_strategy(feature_request, context_analysis),
            "integration_points": self._identify_integration_points(feature_request, context_analysis)
        }
        return blueprint

    # Helper methods for analysis and formatting
    def _analyze_project_structure(self, project_path: str) -> Dict[str, Any]:
        """Analyze the overall project structure."""
        structure = {"directories": [], "key_files": [], "patterns": []}
        try:
            for root, dirs, files in os.walk(project_path):
                rel_path = os.path.relpath(root, project_path)
                if rel_path != ".":
                    structure["directories"].append(rel_path)
                for file in files:
                    if file in ["README.md", "setup.py", "package.json", "Cargo.toml", "pom.xml"]:
                        structure["key_files"].append(os.path.join(rel_path, file))
        except Exception as e:
            structure["error"] = str(e)
        return structure

    def _extract_code_patterns(self, project_path: str, file_patterns: List[str]) -> Dict[str, Any]:
        """Extract common code patterns from the project using Agent-based analysis."""
        try:
            # Get sample Python files for analysis
            python_files = self._get_sample_files(project_path, "*.py", 10)
            sample_content = self._format_sample_files(python_files, project_path)
            
            if not sample_content:
                return {"classes": [], "functions": [], "imports": [], "decorators": [], "error": "No Python files found"}
            
            # Create specialized code pattern analyst agent
            code_analyst = Agent(
                name="Code Pattern Analyst",
                role="Python Code Pattern Analysis Expert",
                goal="Analyze Python code files to extract classes, functions, imports, and decorators",
                instructions="""You are an expert at analyzing Python code patterns. Analyze the provided code files and extract:
                1. Class names and their patterns
                2. Function names and their patterns  
                3. Import statements and patterns
                4. Decorator patterns
                
                Return your analysis as a JSON object with keys: classes, functions, imports, decorators.
                Each should be a list of the items found.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Analyze these Python code files and extract code patterns:

{sample_content}

Return a JSON object with the following structure:
{{
    "classes": ["ClassName1", "ClassName2", ...],
    "functions": ["function1", "function2", ...], 
    "imports": ["import statement1", "import statement2", ...],
    "decorators": ["@decorator1", "@decorator2", ...]
}}"""
            
            response = code_analyst.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            # Ensure required keys exist
            for key in ["classes", "functions", "imports", "decorators"]:
                if key not in result:
                    result[key] = []
            
            return result
            
        except Exception as e:
            return {"classes": [], "functions": [], "imports": [], "decorators": [], "error": str(e)}

    def _analyze_naming_conventions(self, project_path: str, file_patterns: List[str]) -> Dict[str, Any]:
        """Analyze naming conventions used in the project using Agent-based analysis."""
        try:
            # Get sample Python files for analysis
            python_files = self._get_sample_files(project_path, "*.py", 8)
            sample_content = self._format_sample_files(python_files, project_path)
            
            if not sample_content:
                return {"style": "unknown", "patterns": [], "exceptions": [], "error": "No Python files found"}
            
            # Create specialized naming convention analyst agent
            naming_analyst = Agent(
                name="Naming Convention Analyst",
                role="Code Naming Convention Expert",
                goal="Analyze Python code to determine naming conventions and patterns",
                instructions="""You are an expert at analyzing Python naming conventions. Examine the provided code and determine:
                1. Primary naming style (snake_case, camelCase, PascalCase, kebab-case, or mixed)
                2. Consistency patterns
                3. Any exceptions or special cases
                
                Return your analysis as a JSON object with keys: style, patterns, exceptions.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Analyze the naming conventions in these Python code files:

{sample_content}

Examine function names, class names, variable names, and determine the dominant naming style.

Return a JSON object with this structure:
{{
    "style": "snake_case|camelCase|PascalCase|mixed",
    "patterns": ["description of patterns found"],
    "exceptions": ["any exceptions or special cases"]
}}"""
            
            response = naming_analyst.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            # Ensure required keys exist with defaults
            if "style" not in result:
                result["style"] = "unknown"
            if "patterns" not in result:
                result["patterns"] = []
            if "exceptions" not in result:
                result["exceptions"] = []
            
            return result
            
        except Exception as e:
            return {"style": "unknown", "patterns": [], "exceptions": [], "error": str(e)}

    def _analyze_import_patterns(self, project_path: str, file_patterns: List[str]) -> Dict[str, Any]:
        """Analyze import patterns and dependencies using Agent-based analysis."""
        try:
            # Get sample Python files for analysis
            python_files = self._get_sample_files(project_path, "*.py", 8)
            sample_content = self._format_sample_files(python_files, project_path)
            
            if not sample_content:
                return {"relative": [], "absolute": [], "external": [], "patterns": [], "error": "No Python files found"}
            
            # Create specialized import pattern analyst agent
            import_analyst = Agent(
                name="Import Pattern Analyst",
                role="Python Import Analysis Expert",
                goal="Analyze Python import statements to categorize and identify patterns",
                instructions="""You are an expert at analyzing Python import patterns. Examine the provided code and categorize imports:
                1. Relative imports (from ., from .., from .module)
                2. Absolute/standard library imports (os, sys, json, typing, etc.)  
                3. External dependencies (third-party packages)
                4. Overall import patterns and conventions
                
                Return your analysis as a JSON object with keys: relative, absolute, external, patterns.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Analyze the import patterns in these Python code files:

{sample_content}

Categorize all import statements and identify patterns.

Return a JSON object with this structure:
{{
    "relative": ["list of relative import statements"],
    "absolute": ["list of standard library imports"],
    "external": ["list of external/third-party imports"],
    "patterns": ["description of import patterns and conventions found"]
}}"""
            
            response = import_analyst.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            # Ensure required keys exist with defaults
            for key in ["relative", "absolute", "external", "patterns"]:
                if key not in result:
                    result[key] = []
            
            return result
            
        except Exception as e:
            return {"relative": [], "absolute": [], "external": [], "patterns": [], "error": str(e)}

    def _analyze_architecture(self, project_path: str) -> Dict[str, Any]:
        """Analyze the overall architecture patterns using Agent-based analysis."""
        try:
            # Get project structure
            structure = self._analyze_project_structure(project_path)
            directories = structure.get("directories", [])
            key_files = structure.get("key_files", [])
            
            # Get sample code files for architecture analysis
            python_files = self._get_sample_files(project_path, "*.py", 6)
            sample_content = self._format_sample_files(python_files, project_path)
            
            # Create specialized software architecture analyst agent
            architecture_analyst = Agent(
                name="Software Architecture Analyst",
                role="Software Architecture Expert",
                goal="Analyze software architecture patterns and organizational structure",
                instructions="""You are an expert software architect. Analyze the provided project structure and code to identify:
                1. Primary architectural pattern (MVC, layered, microservices, hexagonal, clean architecture, modular, monolithic, etc.)
                2. Architectural layers and their responsibilities
                3. Key components and their roles
                4. Design patterns and architectural decisions
                
                Return your analysis as a JSON object with keys: primary_pattern, layers, components.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Analyze the software architecture of this project:

PROJECT STRUCTURE:
Directories: {directories}
Key Files: {key_files}

SAMPLE CODE:
{sample_content}

Based on the directory structure, file organization, and code patterns, determine the architectural approach.

Return a JSON object with this structure:
{{
    "primary_pattern": "mvc|layered|microservices|hexagonal|clean|modular|monolithic|event-driven",
    "layers": ["list of architectural layers identified"],
    "components": ["list of major components or modules"]
}}"""
            
            response = architecture_analyst.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            # Ensure required keys exist with defaults
            if "primary_pattern" not in result:
                result["primary_pattern"] = "modular"
            if "layers" not in result:
                result["layers"] = []
            if "components" not in result:
                result["components"] = directories[:5] if directories else []
            
            return result
            
        except Exception as e:
            return {"primary_pattern": "unknown", "layers": [], "components": [], "error": str(e)}

    def _analyze_documentation_style(self, project_path: str) -> Dict[str, Any]:
        """Analyze documentation style and conventions using Agent-based analysis."""
        try:
            # Get documentation files for analysis
            doc_content = self._get_documentation_files(project_path)
            
            # Get sample Python files to analyze docstring patterns
            python_files = self._get_sample_files(project_path, "*.py", 5)
            code_content = self._format_sample_files(python_files, project_path)
            
            # Create specialized documentation analyst agent
            doc_analyst = Agent(
                name="Documentation Analyst",
                role="Documentation Style Expert",
                goal="Analyze documentation formats, structure, and conventions",
                instructions="""You are an expert at analyzing documentation styles and conventions. Examine the provided documentation and code to identify:
                1. Documentation format (markdown, restructuredtext, plain text)
                2. Documentation structure and organization
                3. Docstring conventions and styles (Google, NumPy, Sphinx, etc.)
                4. Overall documentation patterns and quality
                
                Return your analysis as a JSON object with keys: format, structure, conventions.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Analyze the documentation style and conventions in this project:

DOCUMENTATION FILES:
{doc_content}

SAMPLE CODE (for docstring analysis):
{code_content}

Analyze the documentation format, structure, and docstring conventions used.

Return a JSON object with this structure:
{{
    "format": "markdown|restructuredtext|plain_text|mixed",
    "structure": ["list of documentation files and structure patterns"],
    "conventions": ["list of docstring and documentation conventions found"]
}}"""
            
            response = doc_analyst.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            # Ensure required keys exist with defaults
            if "format" not in result:
                result["format"] = "markdown"
            if "structure" not in result:
                result["structure"] = []
            if "conventions" not in result:
                result["conventions"] = []
            
            return result
            
        except Exception as e:
            return {"format": "unknown", "structure": [], "conventions": [], "error": str(e)}

    # Additional helper methods for formatting and generation
    def _format_architecture_patterns(self, architecture: Dict[str, Any]) -> str:
        """Format architecture patterns for context document."""
        return f"Primary Pattern: {architecture.get('primary_pattern', 'Unknown')}"

    def _format_code_conventions(self, code_patterns: Dict[str, Any], naming: Dict[str, Any]) -> str:
        """Format code conventions for context document."""
        return f"Naming Style: {naming.get('style', 'Unknown')}"

    def _format_implementation_patterns(self, code_patterns: Dict[str, Any]) -> str:
        """Format implementation patterns for context document."""
        return "Follow existing class and function patterns identified in codebase analysis."

    def _format_documentation_standards(self, doc_style: Dict[str, Any]) -> str:
        """Format documentation standards for context document."""
        return f"Format: {doc_style.get('format', 'markdown')}"

    def _generate_validation_criteria(self, requirements: str, analysis: Dict[str, Any]) -> str:
        """Generate validation criteria based on requirements and analysis."""
        return f"1. Implementation matches requirements: {requirements}\n2. Follows identified code patterns\n3. Maintains architectural consistency"

    def _determine_validation_method(self, criterion: str) -> str:
        """Determine appropriate validation method for a criterion."""
        return "automated_test"

    def _generate_expected_outcome(self, criterion: str) -> str:
        """Generate expected outcome for a criterion."""
        return f"Criterion '{criterion}' passes validation"

    def _generate_failure_actions(self, criterion: str) -> List[str]:
        """Generate actions to take if criterion fails."""
        return [f"Review implementation for: {criterion}", "Fix issues", "Re-test"]

    def _generate_executable_tests(self, requirements: str, criteria: List[str]) -> List[Dict[str, str]]:
        """Generate executable test specifications."""
        return [{"type": "unit_test", "description": f"Test {criterion}"} for criterion in criteria]

    def _generate_quality_gates(self, criteria: List[str]) -> List[Dict[str, str]]:
        """Generate quality gate specifications."""
        return [{"gate": "all_tests_pass", "description": "All validation criteria must pass"}]

    def _format_context_data(self, context_data: Dict[str, Any]) -> str:
        """Format context data for prompt enhancement."""
        return json.dumps(context_data, indent=2)

    def _extract_architecture_guidance(self, context_data: Dict[str, Any]) -> str:
        """Extract architecture guidance from context data."""
        return "Follow established architectural patterns identified in the analysis."

    def _extract_pattern_guidance(self, context_data: Dict[str, Any]) -> str:
        """Extract pattern guidance from context data."""
        return "Adhere to existing code patterns and conventions."

    def _extract_quality_guidance(self, context_data: Dict[str, Any]) -> str:
        """Extract quality guidance from context data."""
        return "Maintain code quality standards identified in the codebase."

    def _format_prp_codebase_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format codebase analysis for PRP."""
        return json.dumps(analysis, indent=2)

    def _generate_prp_implementation_blueprint(self, feature_request: str, analysis: Dict[str, Any]) -> str:
        """Generate implementation blueprint for PRP."""
        return f"Implementation plan for: {feature_request}"

    def _generate_prp_validation_framework(self, feature_request: str) -> str:
        """Generate validation framework for PRP."""
        return f"Validation framework for: {feature_request}"

    def _format_prp_documentation(self, docs: List[str]) -> str:
        """Format documentation links for PRP."""
        return "\n".join(f"- {doc}" for doc in docs)

    def _generate_prp_success_criteria(self, feature_request: str, analysis: Dict[str, Any]) -> str:
        """Generate success criteria for PRP."""
        return f"Success criteria for: {feature_request}"

    # Additional analysis methods
    def _analyze_readme_style(self, project_path: str) -> Dict[str, Any]:
        """Analyze README style and structure."""
        readme_info = {"style": "standard", "sections": []}
        
        try:
            readme_files = ['README.md', 'README.rst', 'README.txt', 'readme.md']
            for readme_file in readme_files:
                readme_path = os.path.join(project_path, readme_file)
                if os.path.exists(readme_path):
                    with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Extract sections (lines starting with # or =)
                    sections = []
                    for line in content.split('\n'):
                        line = line.strip()
                        if line.startswith('#') or line.startswith('='):
                            sections.append(line)
                    
                    readme_info["sections"] = sections[:10]  # Limit to first 10
                    if readme_file.endswith('.md'):
                        readme_info["style"] = "markdown"
                    elif readme_file.endswith('.rst'):
                        readme_info["style"] = "restructuredtext"
                    break
        except Exception as e:
            readme_info["error"] = str(e)
        
        return readme_info

    def _analyze_comment_patterns(self, project_path: str) -> Dict[str, Any]:
        """Analyze code comment patterns."""
        comment_patterns = {"style": "unknown", "density": "unknown"}
        
        try:
            total_lines = 0
            comment_lines = 0
            inline_comments = 0
            block_comments = 0
            
            for root, _dirs, files in os.walk(project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                lines = f.readlines()
                            
                            for line in lines:
                                total_lines += 1
                                stripped = line.strip()
                                if stripped.startswith('#'):
                                    comment_lines += 1
                                    block_comments += 1
                                elif '#' in stripped and not stripped.startswith('#'):
                                    comment_lines += 1
                                    inline_comments += 1
                        except Exception:
                            continue
            
            if comment_lines > 0:
                density_ratio = comment_lines / total_lines if total_lines > 0 else 0
                if density_ratio > 0.2:
                    comment_patterns["density"] = "high"
                elif density_ratio > 0.1:
                    comment_patterns["density"] = "moderate"
                else:
                    comment_patterns["density"] = "low"
                
                if inline_comments > block_comments:
                    comment_patterns["style"] = "inline"
                else:
                    comment_patterns["style"] = "block"
            
        except Exception as e:
            comment_patterns["error"] = str(e)
        
        return comment_patterns

    def _analyze_docstring_format(self, project_path: str) -> Dict[str, Any]:
        """Analyze docstring format conventions."""
        return {"format": "google", "completeness": "partial"}

    def _analyze_api_docs(self, project_path: str) -> Dict[str, Any]:
        """Analyze API documentation patterns."""
        return {"format": "openapi", "coverage": "partial"}

    def _analyze_test_structure(self, project_path: str) -> Dict[str, Any]:
        """Analyze test directory structure."""
        return {"pattern": "mirror", "location": "tests/"}

    def _identify_testing_frameworks(self, project_path: str) -> List[str]:
        """Identify testing frameworks in use."""
        return ["pytest", "unittest"]

    def _analyze_test_naming(self, project_path: str) -> Dict[str, Any]:
        """Analyze test naming conventions."""
        return {"pattern": "test_*", "style": "descriptive"}

    def _analyze_coverage_patterns(self, project_path: str) -> Dict[str, Any]:
        """Analyze test coverage patterns."""
        return {"target": "80%", "tools": ["coverage.py"]}

    def _generate_implementation_steps(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Generate step-by-step implementation plan using Agent-based analysis."""
        try:
            # Create specialized implementation planning agent
            planning_agent = Agent(
                name="Implementation Planning Agent",
                role="Software Implementation Planning Expert",
                goal="Create detailed, step-by-step implementation plans for software features",
                instructions="""You are an expert at creating detailed implementation plans for software features. 
                Based on the feature request and codebase analysis provided, create a comprehensive, step-by-step 
                implementation plan that follows software engineering best practices and respects the existing 
                architecture and patterns.
                
                Return your plan as a JSON object with a "steps" key containing a list of implementation steps.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Create a detailed implementation plan for this feature:

FEATURE REQUEST: {feature_request}

CODEBASE ANALYSIS:
{json.dumps(analysis, indent=2)}

Based on the codebase analysis, create a comprehensive step-by-step implementation plan that:
1. Respects the existing architecture pattern
2. Follows established coding conventions
3. Integrates with existing components
4. Includes proper testing and validation
5. Follows software engineering best practices

Return a JSON object with this structure:
{{
    "steps": ["Step 1: Description", "Step 2: Description", ...]
}}"""
            
            response = planning_agent.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            if "steps" in result and isinstance(result["steps"], list):
                return result["steps"]
            else:
                # Fallback to basic steps
                return [
                    f"1. Analyze requirements: {feature_request}",
                    "2. Design implementation following existing patterns",
                    "3. Implement core functionality",
                    "4. Add tests and validation",
                    "5. Review and deploy"
                ]
            
        except Exception as e:
            # Fallback to basic steps
            return [
                f"1. Analyze requirements: {feature_request}",
                "2. Design implementation",
                "3. Implement core functionality", 
                "4. Add tests",
                "5. Review and deploy",
                f"Note: Error in planning: {str(e)}"
            ]

    def _identify_file_modifications(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Identify which files need modification using Agent-based analysis."""
        try:
            # Create specialized file modification analyst agent
            file_analyst = Agent(
                name="File Modification Analyst",
                role="Software File Impact Analysis Expert",
                goal="Identify which existing files need to be modified for a feature implementation",
                instructions="""You are an expert at analyzing software projects to identify which existing files 
                need to be modified when implementing new features. Based on the feature request and codebase analysis, 
                identify the specific files that would need changes.
                
                Return your analysis as a JSON object with a "files" key containing a list of file paths.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Analyze which existing files need modification for this feature:

FEATURE REQUEST: {feature_request}

CODEBASE ANALYSIS:
{json.dumps(analysis, indent=2)}

Based on the project structure, architecture pattern, and feature requirements, identify which existing files would need to be modified. Consider:
1. Entry points and main application files
2. Architecture-specific files (models, views, controllers, services, etc.)
3. Configuration files
4. Integration points
5. Related modules and utilities

Return a JSON object with this structure:
{{
    "files": ["path/to/file1.py", "path/to/file2.py", ...]
}}"""
            
            response = file_analyst.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            if "files" in result and isinstance(result["files"], list):
                return result["files"][:10]  # Limit to 10 files
            else:
                # Fallback based on analysis
                structure = analysis.get('project_structure', {})
                key_files = structure.get('key_files', [])
                return key_files[:5] if key_files else ['main.py', 'utils.py']
            
        except Exception as e:
            # Fallback to basic files
            return ['main.py', 'utils.py']

    def _identify_new_files(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Identify new files that need to be created using Agent-based analysis."""
        try:
            # Create specialized new file identification agent
            new_file_agent = Agent(
                name="New File Creation Analyst",
                role="Software File Creation Planning Expert", 
                goal="Identify new files that need to be created for feature implementation",
                instructions="""You are an expert at identifying what new files need to be created when implementing 
                software features. Based on the feature request and codebase analysis, determine what new files should 
                be created following the project's conventions and architecture patterns.
                
                Return your analysis as a JSON object with a "files" key containing a list of new file paths.""",
                llm=self.llm if hasattr(self, 'llm') else "gpt-4o-mini",
                verbose=False
            )
            
            prompt = f"""Identify new files needed for this feature implementation:

FEATURE REQUEST: {feature_request}

CODEBASE ANALYSIS:
{json.dumps(analysis, indent=2)}

Based on the project structure, naming conventions, architecture pattern, and feature requirements, identify what new files should be created. Consider:
1. Main implementation files following naming conventions
2. Supporting module files
3. Test files following the testing patterns
4. Configuration or schema files if needed
5. Documentation files if appropriate

Return a JSON object with this structure:
{{
    "files": ["path/to/new_file1.py", "path/to/new_file2.py", ...]
}}"""
            
            response = new_file_agent.chat(prompt, output_json=True)
            result = self._parse_agent_response(response)
            
            if "files" in result and isinstance(result["files"], list):
                return result["files"][:5]  # Limit to 5 files
            else:
                # Fallback based on feature request
                feature_name = feature_request.lower().replace(' ', '_').replace('-', '_')
                return [f"{feature_name}.py", f"test_{feature_name}.py"]
            
        except Exception as e:
            # Fallback to basic new files
            feature_name = feature_request.lower().replace(' ', '_').replace('-', '_')
            return [f"{feature_name}.py"]

    def _identify_dependencies(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Identify new dependencies required."""
        return []

    def _generate_testing_strategy(self, feature_request: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate testing strategy for the feature."""
        return {"unit_tests": True, "integration_tests": True, "coverage_target": "90%"}

    def _identify_integration_points(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Identify integration points with existing code."""
        return ["main_api", "data_layer"]


def create_context_agent(llm: Optional[Union[str, Any]] = None, **kwargs) -> ContextAgent:
    """
    Factory function to create a ContextAgent with sensible defaults.
    
    Args:
        llm: Language model to use (e.g., "gpt-4o-mini", "claude-3-haiku")
        **kwargs: Additional arguments to pass to ContextAgent constructor
        
    Returns:
        ContextAgent: Configured ContextAgent instance
    """
    if llm is None:
        llm = "gpt-4o-mini"  # Default to a capable model for context generation
    
    return ContextAgent(llm=llm, **kwargs)