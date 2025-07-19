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
        """Extract common code patterns from the project."""
        patterns = {"classes": [], "functions": [], "imports": [], "decorators": []}
        
        try:
            # Analyze Python files for patterns
            for root, _dirs, files in os.walk(project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            # Simple pattern extraction using string analysis
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line.startswith('class '):
                                    class_name = line.split('(')[0].replace('class ', '').strip(':')
                                    patterns["classes"].append(class_name)
                                elif line.startswith('def '):
                                    func_name = line.split('(')[0].replace('def ', '')
                                    patterns["functions"].append(func_name)
                                elif line.startswith('import ') or line.startswith('from '):
                                    patterns["imports"].append(line)
                                elif line.startswith('@'):
                                    patterns["decorators"].append(line)
                        except Exception:
                            continue  # Skip files that can't be read
        except Exception as e:
            patterns["error"] = str(e)
        
        return patterns

    def _analyze_naming_conventions(self, project_path: str, file_patterns: List[str]) -> Dict[str, Any]:
        """Analyze naming conventions used in the project."""
        conventions = {"style": "unknown", "patterns": [], "exceptions": []}
        
        try:
            snake_case_count = 0
            camel_case_count = 0
            
            for root, _dirs, files in os.walk(project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line.startswith('def ') or line.startswith('class '):
                                    name = line.split('(')[0].split(':')[0]
                                    if 'def ' in name:
                                        name = name.replace('def ', '')
                                    elif 'class ' in name:
                                        name = name.replace('class ', '')
                                    
                                    if '_' in name:
                                        snake_case_count += 1
                                    elif any(c.isupper() for c in name[1:]):
                                        camel_case_count += 1
                        except Exception:
                            continue
            
            if snake_case_count > camel_case_count:
                conventions["style"] = "snake_case"
            elif camel_case_count > snake_case_count:
                conventions["style"] = "camelCase"
            else:
                conventions["style"] = "mixed"
                
            conventions["patterns"] = [f"snake_case: {snake_case_count}", f"camelCase: {camel_case_count}"]
            
        except Exception as e:
            conventions["error"] = str(e)
        
        return conventions

    def _analyze_import_patterns(self, project_path: str, file_patterns: List[str]) -> Dict[str, Any]:
        """Analyze import patterns and dependencies."""
        imports = {"relative": [], "absolute": [], "external": [], "patterns": []}
        
        try:
            for root, _dirs, files in os.walk(project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line.startswith('from .'):
                                    imports["relative"].append(line)
                                elif line.startswith('import ') or line.startswith('from '):
                                    if any(stdlib in line for stdlib in ['os', 'sys', 'json', 'typing', 'pathlib']):
                                        imports["absolute"].append(line)
                                    else:
                                        imports["external"].append(line)
                        except Exception:
                            continue
            
            # Analyze patterns
            if imports["relative"]:
                imports["patterns"].append("Uses relative imports")
            if imports["absolute"]:
                imports["patterns"].append("Uses standard library imports")
            if imports["external"]:
                imports["patterns"].append("Uses external dependencies")
                
        except Exception as e:
            imports["error"] = str(e)
        
        return imports

    def _analyze_architecture(self, project_path: str) -> Dict[str, Any]:
        """Analyze the overall architecture patterns."""
        architecture = {"primary_pattern": "unknown", "layers": [], "components": []}
        
        try:
            structure = self._analyze_project_structure(project_path)
            directories = structure.get("directories", [])
            
            # Detect common architectural patterns
            mvc_indicators = ["models", "views", "controllers"]
            layered_indicators = ["service", "repository", "dao", "entity"]
            microservice_indicators = ["api", "gateway", "auth", "user"]
            
            mvc_score = sum(1 for dir_name in directories if any(mvc in dir_name.lower() for mvc in mvc_indicators))
            layered_score = sum(1 for dir_name in directories if any(layer in dir_name.lower() for layer in layered_indicators))
            microservice_score = sum(1 for dir_name in directories if any(micro in dir_name.lower() for micro in microservice_indicators))
            
            if mvc_score > 0:
                architecture["primary_pattern"] = "mvc"
                architecture["components"].extend([d for d in directories if any(mvc in d.lower() for mvc in mvc_indicators)])
            elif layered_score > 0:
                architecture["primary_pattern"] = "layered"
                architecture["components"].extend([d for d in directories if any(layer in d.lower() for layer in layered_indicators)])
            elif microservice_score > 0:
                architecture["primary_pattern"] = "microservices"
                architecture["components"].extend([d for d in directories if any(micro in d.lower() for micro in microservice_indicators)])
            else:
                architecture["primary_pattern"] = "modular"
                architecture["components"] = directories[:5]  # First 5 directories as components
            
            architecture["layers"] = [d for d in directories if "/" not in d]  # Top-level directories
            
        except Exception as e:
            architecture["error"] = str(e)
        
        return architecture

    def _analyze_documentation_style(self, project_path: str) -> Dict[str, Any]:
        """Analyze documentation style and conventions."""
        doc_style = {"format": "unknown", "structure": [], "conventions": []}
        
        try:
            # Look for documentation files
            doc_files = []
            for root, _dirs, files in os.walk(project_path):
                for file in files:
                    if file.lower() in ['readme.md', 'readme.rst', 'readme.txt', 'docs.md'] or file.endswith('.md'):
                        doc_files.append(file)
                        if file.endswith('.md'):
                            doc_style["format"] = "markdown"
                        elif file.endswith('.rst'):
                            doc_style["format"] = "restructuredtext"
            
            doc_style["structure"] = doc_files[:10]  # Limit to first 10
            
            # Analyze Python docstrings
            docstring_styles = []
            for root, _dirs, files in os.walk(project_path):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            
                            if '"""' in content:
                                docstring_styles.append("triple_quotes")
                            if "Args:" in content or "Returns:" in content:
                                docstring_styles.append("structured")
                        except Exception:
                            continue
            
            if docstring_styles:
                doc_style["conventions"] = list(set(docstring_styles))
            
        except Exception as e:
            doc_style["error"] = str(e)
        
        return doc_style

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
        """Generate step-by-step implementation plan."""
        steps = []
        
        try:
            # Generate contextual steps based on analysis
            architecture = analysis.get('architecture_insights', {})
            code_patterns = analysis.get('code_patterns', {})
            
            steps.append(f"1. Analyze requirements: {feature_request}")
            steps.append(f"2. Review existing {architecture.get('primary_pattern', 'architecture')} pattern")
            
            if code_patterns.get('classes'):
                steps.append("3. Identify existing classes to extend or modify")
            
            steps.append("4. Design implementation following existing patterns")
            steps.append("5. Implement core functionality")
            steps.append("6. Add error handling and validation")
            steps.append("7. Write unit tests following project conventions")
            steps.append("8. Integration testing")
            steps.append("9. Documentation and code review")
            steps.append("10. Deploy and monitor")
            
        except Exception:
            # Fallback to generic steps
            steps = [
                f"1. Analyze {feature_request}",
                "2. Design implementation",
                "3. Implement core functionality",
                "4. Add tests",
                "5. Review and deploy"
            ]
        
        return steps

    def _identify_file_modifications(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Identify which files need modification."""
        files_to_modify = []
        
        try:
            # Analyze project structure to suggest realistic file modifications
            structure = analysis.get('project_structure', {})
            key_files = structure.get('key_files', [])
            
            # Add common files that typically need modification
            common_files = ['__init__.py', 'main.py', 'app.py', 'setup.py']
            for file in key_files:
                if any(common in file for common in common_files):
                    files_to_modify.append(file)
            
            # Add architecture-specific files
            architecture = analysis.get('architecture_insights', {})
            if architecture.get('primary_pattern') == 'mvc':
                files_to_modify.extend(['models.py', 'views.py', 'controllers.py'])
            elif 'api' in feature_request.lower():
                files_to_modify.extend(['api.py', 'routes.py', 'endpoints.py'])
            
            # Fallback if no files identified
            if not files_to_modify:
                files_to_modify = ['main.py', 'utils.py']
                
        except Exception:
            files_to_modify = ['main.py', 'utils.py']
        
        return files_to_modify[:10]  # Limit to 10 files

    def _identify_new_files(self, feature_request: str, analysis: Dict[str, Any]) -> List[str]:
        """Identify new files that need to be created."""
        new_files = []
        
        try:
            # Generate contextual file names based on feature request
            feature_name = feature_request.lower().replace(' ', '_')
            
            # Extract key concepts from feature request
            if 'auth' in feature_request.lower():
                new_files.extend(['auth.py', 'auth_middleware.py', 'user_models.py'])
            elif 'api' in feature_request.lower():
                new_files.extend(['api_handlers.py', 'api_models.py'])
            elif 'database' in feature_request.lower() or 'db' in feature_request.lower():
                new_files.extend(['database.py', 'migrations.py', 'schemas.py'])
            elif 'test' in feature_request.lower():
                new_files.extend(['test_' + feature_name + '.py'])
            else:
                # Generic new file based on feature name
                new_files.append(feature_name + '.py')
            
            # Add test files
            for file in new_files[:]:
                if not file.startswith('test_'):
                    test_file = 'test_' + file
                    new_files.append(test_file)
            
        except Exception:
            new_files = ['new_feature.py']
        
        return new_files[:5]  # Limit to 5 files

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