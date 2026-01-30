"""
AI-powered content generation for the FDEP standardisation system.

Uses Agent() to generate:
- Documentation pages (concepts, features, cli, sdk)
- Example files (basic, advanced)

Features:
- Template-guided generation with REAL working examples
- Context-aware (SDK info, existing examples)
- Verification via Agent() and code execution
- Dry-run preview with execution testing
- Dynamic source analysis for comprehensive parameter coverage
- ACP/LSP tools integration for intelligent context gathering
- Incremental updates (modify only if needed)
"""

import ast
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import ArtifactType, FeatureSlug

# Setup logger for debug output
logger = logging.getLogger(__name__)
if os.environ.get("LOGLEVEL", "").lower() == "debug":
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)
from .templates import TemplateGenerator
from .example_verifier import ExampleVerifier


class SourceAnalyzer:
    """Analyze Python source files to extract class parameters and methods."""
    
    @staticmethod
    def extract_class_info(file_path: Path, class_name: str = None) -> Dict[str, Any]:
        """Extract class information including all parameters and methods."""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            
            result = {
                "classes": [],
                "functions": [],
                "constants": [],
                "source_preview": source[:3000],
            }
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if class_name and node.name != class_name:
                        continue
                    class_info = SourceAnalyzer._extract_class_details(node, source)
                    result["classes"].append(class_info)
                elif isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                    if node.col_offset == 0:  # Top-level function
                        func_info = SourceAnalyzer._extract_function_details(node, source)
                        result["functions"].append(func_info)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            result["constants"].append(target.id)
            
            return result
        except Exception as e:
            return {"error": str(e), "classes": [], "functions": [], "constants": []}
    
    @staticmethod
    def _extract_class_details(node: ast.ClassDef, source: str) -> Dict[str, Any]:
        """Extract detailed class information."""
        class_info = {
            "name": node.name,
            "docstring": ast.get_docstring(node) or "",
            "init_params": [],
            "methods": [],
            "class_vars": [],
        }
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == "__init__":
                    class_info["init_params"] = SourceAnalyzer._extract_params(item)
                elif not item.name.startswith("_"):
                    method_info = {
                        "name": item.name,
                        "params": SourceAnalyzer._extract_params(item),
                        "docstring": ast.get_docstring(item) or "",
                    }
                    class_info["methods"].append(method_info)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_info["class_vars"].append(target.id)
        
        return class_info
    
    @staticmethod
    def _extract_function_details(node: ast.FunctionDef, source: str) -> Dict[str, Any]:
        """Extract function details."""
        return {
            "name": node.name,
            "params": SourceAnalyzer._extract_params(node),
            "docstring": ast.get_docstring(node) or "",
        }
    
    @staticmethod
    def _extract_params(node: ast.FunctionDef) -> List[Dict[str, Any]]:
        """Extract function parameters with types and defaults."""
        params = []
        defaults = node.args.defaults
        num_defaults = len(defaults)
        num_args = len(node.args.args)
        
        for i, arg in enumerate(node.args.args):
            if arg.arg == "self":
                continue
            
            param_info = {"name": arg.arg, "type": "Any", "default": None}
            
            if arg.annotation:
                try:
                    param_info["type"] = ast.unparse(arg.annotation)
                except Exception:
                    param_info["type"] = "Any"
            
            # Check for default value
            default_index = i - (num_args - num_defaults)
            if default_index >= 0 and default_index < num_defaults:
                try:
                    param_info["default"] = ast.unparse(defaults[default_index])
                except Exception:
                    param_info["default"] = "..."
            
            params.append(param_info)
        
        # Handle keyword-only args
        for i, arg in enumerate(node.args.kwonlyargs):
            param_info = {"name": arg.arg, "type": "Any", "default": None, "kwonly": True}
            if arg.annotation:
                try:
                    param_info["type"] = ast.unparse(arg.annotation)
                except Exception:
                    pass
            if i < len(node.args.kw_defaults) and node.args.kw_defaults[i]:
                try:
                    param_info["default"] = ast.unparse(node.args.kw_defaults[i])
                except Exception:
                    pass
            params.append(param_info)
        
        return params
    
    @staticmethod
    def format_params_for_prompt(params: List[Dict[str, Any]]) -> str:
        """Format parameters for inclusion in prompt."""
        lines = []
        for p in params:
            default_str = f" = {p['default']}" if p.get('default') else ""
            lines.append(f"  - {p['name']}: {p['type']}{default_str}")
        return "\n".join(lines)


class AIGenerator:
    """AI-powered content generator using praisonaiagents.
    
    Designed to be extensible for 100+ features without hardcoding.
    Uses dynamic source analysis and FastContext for comprehensive coverage.
    """
    
    def __init__(self, 
                 model: str = "gpt-4o-mini",
                 sdk_root: Optional[Path] = None,
                 docs_root: Optional[Path] = None,
                 examples_root: Optional[Path] = None,
                 use_fast_context: bool = True):
        self.model = model
        self.sdk_root = sdk_root
        self.docs_root = docs_root
        self.examples_root = examples_root
        self.use_fast_context = use_fast_context
        self.template_generator = TemplateGenerator()
        self.example_verifier = ExampleVerifier(timeout=30)
        self._agent = None
        self._verifier = None
        self._fast_context_handler = None
        self._safe_edit_pipeline = None
        self._feature_source_cache: Dict[str, Dict[str, Any]] = {}
    
    def _get_safe_edit_pipeline(self):
        """Lazy-load SafeEditPipeline for incremental updates."""
        if self._safe_edit_pipeline is None:
            try:
                from praisonai.acp.safe_edit import SafeEditPipeline
                workspace = self.examples_root or self.sdk_root or Path.cwd()
                self._safe_edit_pipeline = SafeEditPipeline(workspace=workspace, auto_approve=False)
            except ImportError:
                pass
        return self._safe_edit_pipeline
    
    def _discover_feature_sources(self, slug_str: str) -> List[Path]:
        """Dynamically discover source files for any feature using multiple strategies."""
        if not self.sdk_root:
            return []
        
        sources = []
        feature_name = slug_str.replace("-", "_")
        
        # Strategy 1: Check for feature directory (e.g., memory/, tools/, guardrails/)
        feature_dir = self.sdk_root / feature_name
        if feature_dir.exists() and feature_dir.is_dir():
            for py_file in feature_dir.glob("*.py"):
                if not py_file.name.startswith("_"):
                    sources.append(py_file)
        
        # Strategy 2: Check for feature file directly (e.g., memory.py)
        direct_file = self.sdk_root / f"{feature_name}.py"
        if direct_file.exists():
            sources.append(direct_file)
        
        # Strategy 3: Use FastContext to search for relevant files
        if not sources and self.use_fast_context:
            handler = self._get_fast_context_handler()
            if handler:
                results = handler.search_context(
                    f"{slug_str} class parameters config",
                    str(self.sdk_root),
                    use_llm_keywords=False
                )
                for r in results[:5]:
                    file_path = self.sdk_root / r.get('file', '')
                    if file_path.exists() and file_path.suffix == '.py':
                        sources.append(file_path)
        
        # Strategy 4: Search in agents/ directory for agent-related features
        if not sources:
            agents_dir = self.sdk_root / "agents"
            if agents_dir.exists():
                for py_file in agents_dir.glob("*.py"):
                    if feature_name in py_file.name.lower() or slug_str in py_file.read_text(encoding="utf-8", errors="ignore").lower()[:5000]:
                        sources.append(py_file)
                        break
        
        return sources[:3]  # Limit to top 3 most relevant
    
    def _analyze_feature_source(self, slug_str: str) -> Dict[str, Any]:
        """Analyze source files for a feature to extract all parameters dynamically.
        
        Prioritizes the main class (matching feature name) and extracts ALL methods.
        """
        # Check cache first
        if slug_str in self._feature_source_cache:
            return self._feature_source_cache[slug_str]
        
        result = {
            "classes": [],
            "functions": [],
            "constants": [],
            "source_files": [],
            "source_preview": "",
            "main_class": None,  # The primary class for this feature
        }
        
        # Discover source files dynamically
        source_files = self._discover_feature_sources(slug_str)
        
        # Determine the expected main class name
        feature_name = slug_str.replace("-", "_")
        expected_class_names = [
            feature_name.title().replace("_", ""),  # e.g., "memory" -> "Memory"
            feature_name.title(),  # e.g., "memory" -> "Memory"
            feature_name.upper(),  # e.g., "memory" -> "MEMORY"
        ]
        
        all_classes = []
        for source_file in source_files:
            try:
                file_info = SourceAnalyzer.extract_class_info(source_file)
                all_classes.extend(file_info.get("classes", []))
                result["functions"].extend(file_info.get("functions", []))
                result["constants"].extend(file_info.get("constants", []))
                result["source_files"].append(str(source_file.name))
                if not result["source_preview"]:
                    result["source_preview"] = file_info.get("source_preview", "")
            except Exception:
                continue
        
        # Prioritize main class (matching feature name) first
        main_class = None
        other_classes = []
        for cls in all_classes:
            if cls["name"] in expected_class_names or cls["name"].lower() == feature_name:
                main_class = cls
            else:
                other_classes.append(cls)
        
        # Put main class first if found
        if main_class:
            result["classes"] = [main_class] + other_classes
            result["main_class"] = main_class
        else:
            result["classes"] = all_classes
            if all_classes:
                result["main_class"] = all_classes[0]
        
        # Cache the result
        self._feature_source_cache[slug_str] = result
        return result
    
    def _check_existing_example(self, slug: FeatureSlug, artifact_type: ArtifactType) -> Optional[str]:
        """Check if example already exists and return its content."""
        output_path = self.template_generator.get_expected_path(
            slug, artifact_type,
            docs_root=self.docs_root,
            examples_root=self.examples_root,
        )
        if output_path and output_path.exists():
            try:
                return output_path.read_text(encoding="utf-8")
            except Exception:
                pass
        return None
    
    def _should_update_example(self, existing: str, new_content: str) -> Tuple[bool, str]:
        """Determine if existing example should be updated."""
        if not existing:
            return True, "New file"
        
        # Normalize for comparison
        existing_lines = [line.strip() for line in existing.strip().split('\n') if line.strip()]
        new_lines = [line.strip() for line in new_content.strip().split('\n') if line.strip()]
        
        if existing_lines == new_lines:
            return False, "No changes needed"
        
        # Check if new content has more sections/features
        existing_sections = existing.count("# Section")
        new_sections = new_content.count("# Section")
        
        if new_sections > existing_sections:
            return True, f"New content has more sections ({new_sections} vs {existing_sections})"
        
        # Check if new content is significantly longer (more comprehensive)
        if len(new_content) > len(existing) * 1.2:
            return True, "New content is more comprehensive"
        
        return False, "Existing content is sufficient"
    
    def _get_fast_context_handler(self):
        """Lazy-load FastContext handler."""
        if self._fast_context_handler is None and self.use_fast_context:
            try:
                from praisonai.cli.features.fast_context import FastContextHandler
                self._fast_context_handler = FastContextHandler()
            except ImportError:
                pass
        return self._fast_context_handler
    
    def _detect_feature_capabilities(self, slug_str: str, source_info: Dict[str, Any]) -> Dict[str, Any]:
        """Detect feature capabilities from source analysis."""
        caps = {
            "supports_bool": True,
            "supports_list": False,
            "supports_dict": False,
            "supports_presets": [],
            "supports_url": False,
            "usage_forms": [],
            "decorator": None,
            "built_in_items": [],
        }
        
        # Feature-specific detection based on slug
        if slug_str == "tools":
            caps["supports_list"] = True
            caps["supports_bool"] = False
            caps["decorator"] = "@tool"
            caps["built_in_items"] = ["duckduckgo", "wikipedia_tools", "read_file", "execute_command"]
            caps["usage_forms"] = [
                "- List of tools: `tools=[my_func, another_func]`",
                "- Using @tool decorator to create custom tools",
                "- Using built-in tools: duckduckgo, wikipedia_tools, etc.",
            ]
        elif slug_str == "memory":
            caps["supports_dict"] = True
            caps["supports_presets"] = ["sqlite", "redis", "postgres", "qdrant", "chroma"]
            caps["supports_url"] = True
            caps["usage_forms"] = [
                "- Boolean: `memory=True`",
                "- Preset: `memory=\"sqlite\"` or `memory=\"redis\"`",
                "- URL: `memory=\"redis://localhost:6379\"`",
                "- Dict: `memory={\"provider\": \"qdrant\"}`",
            ]
        elif slug_str == "knowledge":
            caps["supports_dict"] = True
            caps["supports_list"] = True
            caps["usage_forms"] = [
                "- Boolean: `knowledge=True`",
                "- List of sources: `knowledge=[\"file.pdf\", \"doc.txt\"]`",
                "- Dict config: `knowledge={\"sources\": [...]}`",
            ]
        elif slug_str == "guardrails":
            caps["supports_list"] = True
            caps["decorator"] = "guardrail function"
            caps["usage_forms"] = [
                "- Boolean: `guardrails=True`",
                "- List of functions: `guardrails=[my_guardrail_func]`",
                "- Custom guardrail function returning GuardrailResult",
            ]
        elif slug_str == "streaming":
            caps["supports_bool"] = True
            caps["usage_forms"] = [
                "- Boolean: `output=\"stream\"` or iterate over agent.start()",
                "- Streaming with callbacks",
            ]
        else:
            # Generic detection from source
            caps["usage_forms"] = [f"- Boolean: `{slug_str}=True`"]
        
        logger.debug(f"Feature '{slug_str}' capabilities: {caps}")
        return caps
    
    def _get_agent(self):
        """Lazy-load the generation agent."""
        if self._agent is None:
            try:
                from praisonaiagents import Agent
                self._agent = Agent(
                    name="DocGenerator",
                    role="Technical Documentation Writer",
                    goal="Generate high-quality documentation and examples for PraisonAI features",
                    backstory="""You are an expert technical writer specializing in AI/ML documentation.
                    You write clear, concise, and user-friendly documentation with:
                    - Progressive disclosure (simple first, advanced later)
                    - Practical code examples
                    - Mermaid diagrams for concepts
                    - Consistent formatting and terminology""",
                    llm=self.model,
                )
            except ImportError:
                raise RuntimeError("praisonaiagents not available. Install with: pip install praisonaiagents")
        return self._agent
    
    def _get_verifier(self):
        """Lazy-load the verification agent."""
        if self._verifier is None:
            try:
                from praisonaiagents import Agent
                self._verifier = Agent(
                    name="DocVerifier",
                    role="Documentation Quality Reviewer",
                    goal="Verify documentation quality, accuracy, and completeness",
                    backstory="""You are a senior technical reviewer who ensures documentation:
                    - Is accurate and matches the actual SDK/API
                    - Follows best practices for technical writing
                    - Has no broken code examples
                    - Uses consistent terminology
                    - Is user-friendly and progressive""",
                    llm=self.model,
                )
            except ImportError:
                raise RuntimeError("praisonaiagents not available")
        return self._verifier
    
    def generate(self, slug: FeatureSlug, artifact_type: ArtifactType,
                 dry_run: bool = True, 
                 verify_execution: bool = True,
                 max_retries: int = 2,
                 force_update: bool = False) -> Tuple[str, Optional[str], Optional[dict]]:
        """
        Generate content for an artifact using AI with incremental update support.
        
        Args:
            slug: Feature slug
            artifact_type: Type of artifact to generate
            dry_run: If True, return content without writing
            verify_execution: If True, verify examples run before writing
            max_retries: Max retries if verification fails
            force_update: If True, regenerate even if existing content is sufficient
        
        Returns:
            Tuple of (generated_content, output_path or None, verification_info)
        """
        # Check for existing content (incremental update logic)
        existing_content = self._check_existing_example(slug, artifact_type)
        
        # Get template as base
        template = self.template_generator.generate(slug, artifact_type)
        
        # Gather context (includes source analysis for comprehensive coverage)
        context = self._gather_context(slug, artifact_type)
        
        # Build prompt with enhanced instructions for real examples
        prompt = self._build_generation_prompt(slug, artifact_type, template, context)
        
        # If existing content and not forcing update, include it in context for improvement
        if existing_content and not force_update:
            prompt = self._enhance_prompt_with_existing(prompt, existing_content, artifact_type)
        
        # Generate with AI
        agent = self._get_agent()
        result = agent.start(prompt)
        
        # Extract content
        content = self._extract_content(result, artifact_type)
        
        # Verification info
        verification_info = None
        
        # For example files, verify they run
        if artifact_type.value.startswith("example_") and verify_execution:
            for attempt in range(max_retries + 1):
                verification = self.example_verifier.verify(content)
                verification_info = {
                    "success": verification.success,
                    "syntax_valid": verification.syntax_valid,
                    "execution_passed": verification.execution_passed,
                    "requires_external": verification.requires_external,
                    "missing_libraries": verification.missing_libraries,
                    "error": verification.error[:500] if verification.error else None,
                    "attempt": attempt + 1,
                }
                
                if verification.can_write:
                    break
                
                # If failed and we have retries left, regenerate with error feedback
                if attempt < max_retries:
                    fix_prompt = self._build_fix_prompt(
                        slug, artifact_type, content, verification.error
                    )
                    result = agent.start(fix_prompt)
                    content = self._extract_content(result, artifact_type)
            
            # If still failing after retries and not due to external libs, don't write
            if not verification.can_write:
                return content, None, verification_info
        
        if dry_run:
            return content, None, verification_info
        
        # Write to file
        output_path = self.template_generator.get_expected_path(
            slug, artifact_type,
            docs_root=self.docs_root,
            examples_root=self.examples_root,
        )
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            return content, str(output_path), verification_info
        
        return content, None, verification_info
    
    def _build_fix_prompt(self, slug: FeatureSlug, artifact_type: ArtifactType,
                          code: str, error: str) -> str:
        """Build a prompt to fix broken code."""
        return f"""The following Python code for '{slug.normalised}' has an error:

```python
{code[:2000]}
```

Error:
{error[:500]}

Please fix the code to make it runnable. Requirements:
1. Fix the specific error mentioned
2. Ensure all imports are correct
3. Use mock data if needed instead of external dependencies
4. The code must be complete and runnable

Return ONLY the fixed Python code, no explanations."""
    
    def _enhance_prompt_with_existing(self, prompt: str, existing: str, 
                                       artifact_type: ArtifactType) -> str:
        """Enhance prompt with existing content for incremental improvement."""
        is_advanced = "advanced" in artifact_type.value
        
        enhancement = f"""
## EXISTING CONTENT (improve upon this, don't start from scratch):
```python
{existing[:2500]}
```

## IMPROVEMENT REQUIREMENTS:
- Keep what works well in the existing code
- Add MORE sections to cover additional parameters/options
- Make each section a clear real-world use case
- Ensure progressive complexity (simple to advanced)
{"- MUST have 5+ sections for advanced examples" if is_advanced else ""}

"""
        return prompt + enhancement
    
    def verify(self, content: str, artifact_type: ArtifactType,
               slug: FeatureSlug) -> Tuple[bool, str, List[str]]:
        """
        Verify generated content using AI.
        
        Returns:
            Tuple of (is_valid, summary, issues)
        """
        verifier = self._get_verifier()
        
        prompt = f"""Review this {artifact_type.value} documentation for the '{slug.normalised}' feature.

Content to review:
```
{content[:3000]}
```

Check for:
1. Technical accuracy
2. Code example correctness
3. Consistent terminology
4. Clear structure
5. User-friendliness

Respond with:
VALID: yes/no
SUMMARY: One sentence summary
ISSUES: List any issues found (or "None")
"""
        
        result = verifier.start(prompt)
        result_str = str(result)
        
        is_valid = "VALID: yes" in result_str.lower() or "valid:yes" in result_str.lower()
        
        # Extract summary
        summary = "Verification complete"
        if "SUMMARY:" in result_str:
            summary_start = result_str.find("SUMMARY:") + 8
            summary_end = result_str.find("\n", summary_start)
            if summary_end > summary_start:
                summary = result_str[summary_start:summary_end].strip()
        
        # Extract issues
        issues = []
        if "ISSUES:" in result_str:
            issues_start = result_str.find("ISSUES:") + 7
            issues_text = result_str[issues_start:].strip()
            if issues_text.lower() != "none":
                issues = [line.strip() for line in issues_text.split("\n") if line.strip()]
        
        return is_valid, summary, issues
    
    def _gather_context(self, slug: FeatureSlug, 
                        artifact_type: ArtifactType) -> Dict[str, str]:
        """Gather context for generation using FastContext and file search."""
        context = {}
        slug_str = slug.normalised
        
        logger.debug(f"Gathering context for feature '{slug_str}', artifact '{artifact_type.value}'")
        
        # Use FastContext to find relevant code in SDK
        fast_context = self._get_fast_context_handler()
        if fast_context and self.sdk_root:
            logger.debug(f"FastContext available, searching in {self.sdk_root}")
            try:
                # Search for feature-related code
                query = f"Find {slug_str} implementation, usage examples, and API"
                matches = fast_context.search_context(query, str(self.sdk_root), use_llm_keywords=False)
                
                logger.debug(f"FastContext found {len(matches)} matches for '{query}'")
                
                # Read matched files
                for match in matches[:3]:
                    file_path = self.sdk_root / match.get('file', '')
                    if file_path.exists():
                        try:
                            content = file_path.read_text(encoding="utf-8")[:2000]
                            context[f"sdk_{file_path.stem}"] = content
                            logger.debug(f"Added SDK context: {file_path.name} ({len(content)} chars)")
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"FastContext search failed: {e}")
        
        # Get SDK module info (fallback)
        if self.sdk_root and not context:
            sdk_path = self.sdk_root / slug_str.replace("-", "_")
            if sdk_path.exists():
                context["sdk_module"] = self._read_sdk_module(sdk_path)
            
            # Also check for init file
            init_file = sdk_path / "__init__.py" if sdk_path.exists() else None
            if init_file and init_file.exists():
                context["sdk_exports"] = init_file.read_text(encoding="utf-8")[:2000]
        
        # Use FastContext to find existing examples
        if fast_context and self.examples_root:
            try:
                query = f"{slug_str} example usage"
                matches = fast_context.search_context(query, str(self.examples_root), use_llm_keywords=False)
                
                for match in matches[:2]:
                    file_path = self.examples_root / match.get('file', '')
                    if file_path.exists() and file_path.suffix == '.py':
                        try:
                            content = file_path.read_text(encoding="utf-8")[:2000]
                            context[f"example_{file_path.stem}"] = content
                        except Exception:
                            pass
            except Exception:
                pass
        
        # Fallback: Get existing examples from feature directory
        if self.examples_root and f"example_{slug_str}" not in str(context.keys()):
            example_dir = self.examples_root / slug_str.replace("-", "_")
            if example_dir.exists():
                for py_file in list(example_dir.glob("*.py"))[:2]:
                    context[f"example_{py_file.stem}"] = py_file.read_text(encoding="utf-8")[:2000]
        
        # Get existing docs
        if self.docs_root:
            for doc_type in ["concepts", "features"]:
                doc_path = self.docs_root / doc_type / f"{slug_str}.mdx"
                if doc_path.exists():
                    context[f"existing_{doc_type}"] = doc_path.read_text(encoding="utf-8")[:2000]
        
        logger.debug(f"Context gathered for '{slug_str}': {list(context.keys())}")
        return context
    
    def _read_sdk_module(self, sdk_path: Path) -> str:
        """Read SDK module content for context."""
        content_parts = []
        
        for py_file in list(sdk_path.glob("*.py"))[:3]:
            if py_file.name.startswith("_"):
                continue
            try:
                file_content = py_file.read_text(encoding="utf-8")
                # Extract docstrings and class/function signatures
                lines = []
                for line in file_content.split("\n")[:100]:
                    if line.strip().startswith(("class ", "def ", '"""', "'''", "#")):
                        lines.append(line)
                content_parts.append(f"# {py_file.name}\n" + "\n".join(lines))
            except Exception:
                pass
        
        return "\n\n".join(content_parts)[:3000]
    
    def _build_generation_prompt(self, slug: FeatureSlug, 
                                  artifact_type: ArtifactType,
                                  template: str,
                                  context: Dict[str, str]) -> str:
        """Build the generation prompt with real example requirements."""
        # Different prompts for examples vs docs
        if artifact_type.value.startswith("example_"):
            return self._build_example_prompt(slug, artifact_type, template, context)
        else:
            return self._build_docs_prompt(slug, artifact_type, template, context)
    
    def _build_example_prompt(self, slug: FeatureSlug,
                               artifact_type: ArtifactType,
                               template: str,
                               context: Dict[str, str]) -> str:
        """Build prompt for generating REAL, RUNNABLE examples."""
        slug_str = slug.normalised
        name = slug_str.replace("-", " ").title()
        is_advanced = "advanced" in artifact_type.value
        
        if is_advanced:
            return self._build_advanced_example_prompt(slug_str, name, context)
        else:
            return self._build_basic_example_prompt(slug_str, name, context)
    
    def _build_basic_example_prompt(self, slug_str: str, name: str, 
                                     context: Dict[str, str]) -> str:
        """Build prompt for BASIC example - minimal, flat code."""
        # Get feature-specific basic structure
        feature_basic = self._get_feature_basic_structure(slug_str, name)
        
        prompt_parts = [
            f"Generate a BASIC Python example for '{name}' in PraisonAI.",
            "",
            "## CRITICAL RULES:",
            f"1. ONE-LINE docstring: `\"\"\"{name} - Basic Example\"\"\"`",
            "2. MUST use real imports: `from praisonaiagents import Agent`",
            "3. NO mock classes - use the REAL Agent class",
            "4. FLAT CODE - NO classes (simple def OK ONLY for tools/guardrails)",
            "5. Short # comments only (one line each)",
            "6. Call agent.start('task') to demonstrate the feature",
            "7. NO unnecessary boilerplate - only what's needed for this feature",
            "",
            f"## {name.upper()} BASIC STRUCTURE:",
            feature_basic,
            "",
        ]
        
        # Add feature-specific guidance
        prompt_parts.extend(self._get_feature_guidance(slug_str, False))
        
        # Add FastContext gathered context if available
        if context:
            prompt_parts.append("## Reference from codebase:")
            for key, value in list(context.items())[:2]:
                prompt_parts.append(f"### {key}:")
                prompt_parts.append(f"```python\n{value[:1500]}\n```")
        
        prompt_parts.extend([
            "",
            "Generate ONLY the Python code, no explanations:",
        ])
        
        return "\n".join(prompt_parts)
    
    def _get_feature_basic_structure(self, slug: str, name: str) -> str:
        """Get feature-specific basic example structure."""
        structures = {
            "guardrails": f'''```python
"""{name} - Basic Example"""
from praisonaiagents import Agent

# Simple guardrail function
def check_length(output):
    """Validate output length."""
    return (len(str(output)) > 5, output)

# Create agent with guardrail
agent = Agent(
    instructions="You are helpful",
    guardrails=check_length
)

# Run the agent
result = agent.start("Say hello")
print(result)
```''',
            "memory": f'''```python
"""{name} - Basic Example"""
from praisonaiagents import Agent

# Create agent with memory enabled
agent = Agent(
    instructions="Remember our conversation",
    memory=True
)

# Run the agent
result = agent.start("My name is John")
print(result)
```''',
            "tools": f'''```python
"""{name} - Basic Example"""
from praisonaiagents import Agent

# Define a simple tool
def calculator(expression: str) -> str:
    """Calculate a math expression."""
    return str(eval(expression))

# Create agent with tool
agent = Agent(
    instructions="Use the calculator tool",
    tools=[calculator]
)

# Run the agent
result = agent.start("What is 2 + 2?")
print(result)
```''',
            "knowledge": f'''```python
"""{name} - Basic Example"""
from praisonaiagents import Agent

# Create agent with knowledge
agent = Agent(
    instructions="Answer questions using your knowledge",
    knowledge=["Python was created by Guido van Rossum in 1991"]
)

# Run the agent
result = agent.start("When was Python created?")
print(result)
```''',
            "streaming": f'''```python
"""{name} - Basic Example"""
from praisonaiagents import Agent

# Create agent with streaming
agent = Agent(
    instructions="You are helpful",
    output="stream"
)

# Run the agent with streaming
for chunk in agent.start("Tell me a short story"):
    print(chunk, end="", flush=True)
```''',
        }
        
        return structures.get(slug, f'''```python
"""{name} - Basic Example"""
from praisonaiagents import Agent

# Create agent with {slug}
agent = Agent(
    instructions="You are helpful",
    {slug}=True
)

# Run the agent
result = agent.start("Hello")
print(result)
```''')
    
    def _build_advanced_example_prompt(self, slug_str: str, name: str,
                                        context: Dict[str, str]) -> str:
        """Build prompt for ADVANCED example - progressive sections with ALL parameters."""
        # Analyze source file to get all parameters dynamically
        source_info = self._analyze_feature_source(slug_str)
        
        # Get feature-specific example structure as base
        feature_example = self._get_feature_example_structure(slug_str, name)
        
        prompt_parts = [
            f"Generate a COMPREHENSIVE ADVANCED Python example for '{name}' in PraisonAI.",
            "",
            "## CRITICAL RULES:",
            f"1. ONE-LINE docstring: `\"\"\"{name} - Advanced Example\"\"\"`",
            "2. MUST use real imports: `from praisonaiagents import Agent, Task, Agents`",
            "3. Use AgentManager() NOT PraisonAIAgentManager() - Agents is the correct alias",
            "4. NO mock classes - use the REAL classes from praisonaiagents",
            "5. FLAT CODE - NO class definitions (simple def OK for tools/guardrails)",
            "6. Short # comments only (one line each)",
            "7. PROGRESSIVE sections - each section demonstrates MORE parameters/options",
            "8. Use agent.start('task') or agents.start() to run examples",
            f"9. THIS IS A {name.upper()} EXAMPLE - MUST showcase ALL {slug_str} options progressively",
            "10. Each section should be a REAL-WORLD use case that beginners can understand",
            "",
        ]
        
        # Get dynamic feature capabilities - NO hardcoded usage forms
        capabilities = self._detect_feature_capabilities(slug_str, source_info)
        
        # Add ONLY the usage forms this feature actually supports
        prompt_parts.append("## USAGE FORMS TO DEMONSTRATE (cover these progressively):")
        for usage_form in capabilities["usage_forms"]:
            prompt_parts.append(usage_form)
        
        # Add decorator info if applicable
        if capabilities.get("decorator"):
            prompt_parts.append(f"- MUST demonstrate the {capabilities['decorator']} pattern")
        
        # Add built-in items if applicable
        if capabilities.get("built_in_items"):
            items = ", ".join(capabilities["built_in_items"][:4])
            prompt_parts.append(f"- Built-in options to show: {items}")
        
        prompt_parts.append("")
        
        logger.debug(f"Feature '{slug_str}' usage forms: {capabilities['usage_forms']}")
        
        # Add dynamically extracted parameters if available
        main_class = source_info.get("main_class")
        if main_class:
            prompt_parts.append(f"## {main_class['name'].upper()} CLASS DETAILS (from source):")
            if main_class.get("init_params"):
                prompt_parts.append("\n### Constructor Parameters:")
                prompt_parts.append(SourceAnalyzer.format_params_for_prompt(main_class["init_params"]))
            if main_class.get("methods"):
                prompt_parts.append("\n### Key Methods (MUST demonstrate these):")
                for method in main_class["methods"][:12]:
                    params_str = ", ".join([p["name"] for p in method["params"][:4]])
                    doc = method.get("docstring", "")[:60] if method.get("docstring") else ""
                    prompt_parts.append(f"  - {method['name']}({params_str}) - {doc}")
            prompt_parts.append("")
            prompt_parts.append("## REQUIREMENT: Your example MUST progressively demonstrate these methods!")
            prompt_parts.append("")
        
        prompt_parts.extend([
            f"## {name.upper()} EXAMPLE STRUCTURE (use as inspiration, but cover MORE options):",
            feature_example,
            "",
        ])
        
        # Add feature-specific guidance with expanded options
        prompt_parts.extend(self._get_feature_guidance(slug_str, True))
        
        # Add FastContext gathered context if available
        if context:
            prompt_parts.append("\n## Reference from codebase (READ THIS for accurate API usage):")
            for key, value in list(context.items())[:3]:
                prompt_parts.append(f"\n### {key}:")
                prompt_parts.append(f"```python\n{value[:2000]}\n```")
        
        prompt_parts.extend([
            "",
            "## ADVANCED EXAMPLE REQUIREMENTS:",
            "- Section 1: Basic usage (simplest form)",
            "- Section 2: With configuration options (dict config, presets)",
            "- Section 3: With quality/filtering parameters",
            "- Section 4: Multi-agent with shared feature",
            "- Section 5: Advanced real-world scenario",
            "",
            "Generate ONLY the Python code (5+ sections covering ALL major options):",
        ])
        
        return "\n".join(prompt_parts)
    
    def _get_feature_example_structure(self, slug: str, name: str) -> str:
        """Generate feature-specific example structure dynamically.
        
        This method generates a template structure for ANY feature by analyzing
        the source code. It's designed to work with 100+ features without hardcoding.
        """
        # Get source analysis for this feature
        source_info = self._analyze_feature_source(slug)
        
        # Build dynamic example structure based on source analysis
        sections = []
        
        # Determine the parameter name and type from source analysis
        param_name = slug.replace("-", "_")
        param_value = "True"  # Default
        
        # Check if feature has specific configuration options
        if source_info.get("classes"):
            main_class = source_info["classes"][0]
            if main_class.get("init_params"):
                # Look for common config patterns
                for param in main_class["init_params"]:
                    if param["name"] in ["config", "options", "settings"]:
                        param_value = "{}"  # Dict config
                        break
        
        # Generate dynamic sections
        sections.append(f'''```python
"""{name} - Advanced Example"""
from praisonaiagents import Agent, Task, Agents

# Section 1: Basic {slug} usage
agent1 = Agent(instructions="Demonstrate {slug}", {param_name}={param_value})
result1 = agent1.start("Hello")
print(f'Section 1: {{result1}}')

# Section 2: With configuration options
# (Use dict config, presets, or URL-based config as appropriate)
agent2 = Agent(instructions="Configure {slug}", {param_name}={param_value})
result2 = agent2.start("Test configuration")
print(f'Section 2: {{result2}}')

# Section 3: With quality/filtering parameters
agent3 = Agent(instructions="Quality {slug}", {param_name}={param_value})
result3 = agent3.start("Test quality")
print(f'Section 3: {{result3}}')

# Section 4: Multi-agent with shared {slug}
agent4 = Agent(name="Agent4", instructions="Multi-agent {slug}", {param_name}={param_value})
task = Task(description="Use {slug}", agent=agent4)
agents = AgentManager(agents=[agent4], tasks=[task])
result4 = agents.start()
print(f'Section 4: {{result4}}')

# Section 5: Advanced real-world scenario
agent5 = Agent(instructions="Real-world {slug}", {param_name}={param_value})
result5 = agent5.start("Advanced use case")
print(f'Section 5: {{result5}}')
```''')
        
        return sections[0]
    
    def _get_feature_guidance(self, slug: str, is_advanced: bool) -> List[str]:
        """Generate feature-specific guidance dynamically from source analysis.
        
        This method is designed to work with ANY feature (100+) by analyzing
        the source code and extracting relevant information automatically.
        """
        name = slug.replace('-', ' ').title()
        
        # Get source analysis for this feature
        source_info = self._analyze_feature_source(slug)
        
        guidance = [f"## {name} {'ADVANCED' if is_advanced else 'Basic'} Guidance:"]
        
        # Use main_class if available, otherwise first class
        main_class = source_info.get("main_class")
        if not main_class and source_info.get("classes"):
            main_class = source_info["classes"][0]
        
        if main_class:
            # Add class-level guidance
            if main_class.get("docstring"):
                doc_lines = main_class["docstring"].split('\n')[:3]
                guidance.append(f"- {main_class['name']}: {doc_lines[0]}")
            
            # Add init params for configuration guidance
            if main_class.get("init_params"):
                guidance.append("- Constructor parameters:")
                for param in main_class["init_params"][:5]:
                    default_str = f" = {param['default']}" if param.get('default') else ""
                    guidance.append(f"  - {param['name']}: {param['type']}{default_str}")
            
            # Add method-based guidance for advanced examples
            if is_advanced and main_class.get("methods"):
                guidance.append("- Key methods to demonstrate:")
                for method in main_class["methods"][:10]:
                    params = ", ".join([p["name"] for p in method["params"][:3]])
                    doc_preview = method.get("docstring", "")[:50] if method.get("docstring") else ""
                    guidance.append(f"  - {method['name']}({params}) - {doc_preview}")
        
        # Add generic guidance based on feature type
        if is_advanced:
            guidance.extend([
                f"- MUST demonstrate ALL major {slug} options progressively",
                "- Section 1: Basic usage (simplest form)",
                "- Section 2: With configuration options (dict config, presets, URLs)",
                "- Section 3: With quality/filtering parameters",
                "- Section 4: Multi-agent with shared feature",
                "- Section 5: Advanced real-world scenario",
                "- Each section should be a clear, beginner-friendly real-world use case",
                "- IMPORTANT: Cover ALL usage forms (bool, string preset, URL, dict, array)",
            ])
        else:
            guidance.extend([
                f"- Keep it simple - demonstrate basic {slug} usage",
                "- Use agent.start() to run the example",
                "- NO mock data unless absolutely required",
            ])
        
        return guidance
    
    def _build_docs_prompt(self, slug: FeatureSlug,
                           artifact_type: ArtifactType,
                           template: str,
                           context: Dict[str, str]) -> str:
        """Build prompt for documentation pages."""
        slug_str = slug.normalised
        name = slug_str.replace("-", " ").title()
        
        prompt_parts = [
            f"Generate a {artifact_type.value} documentation page for the '{name}' feature in PraisonAI.",
            "",
            "## Template to follow:",
            "```",
            template[:2000],
            "```",
            "",
        ]
        
        if context:
            prompt_parts.append("## Context from existing code/docs:")
            for key, value in list(context.items())[:3]:
                prompt_parts.append(f"\n### {key}:")
                prompt_parts.append(f"```\n{value[:1500]}\n```")
        
        prompt_parts.extend([
            "",
            "## Requirements:",
            "1. Follow the template structure exactly",
            "2. Use REAL, WORKING code examples (not placeholders)",
            "3. Be concise but comprehensive",
            "4. Include a mermaid diagram if this is a concept page",
            "5. Use Mintlify MDX components (CodeGroup, Tabs, Cards)",
            "6. Ensure all imports are correct for praisonaiagents",
            "7. Code examples must be complete and runnable",
            "",
            "Generate the complete content now:",
        ])
        
        return "\n".join(prompt_parts)
    
    def _extract_content(self, result, artifact_type: ArtifactType) -> str:
        """Extract content from agent result."""
        result_str = str(result)
        
        # If result contains code blocks, extract them
        if "```" in result_str:
            # For MDX files, look for the full content
            if artifact_type.value.startswith("docs_"):
                # Find content starting with ---
                if "---" in result_str:
                    start = result_str.find("---")
                    return result_str[start:]
            
            # For Python files, extract code block
            if artifact_type.value.startswith("example_"):
                code_start = result_str.find("```python")
                if code_start >= 0:
                    code_start = result_str.find("\n", code_start) + 1
                    code_end = result_str.find("```", code_start)
                    if code_end > code_start:
                        return result_str[code_start:code_end]
        
        return result_str


class SDKDocGenerator:
    """Auto-generate SDK documentation from code."""
    
    def __init__(self, sdk_root: Path):
        self.sdk_root = sdk_root
    
    def generate_from_module(self, module_path: Path) -> str:
        """Generate SDK docs from a module's source code."""
        import ast
        self._ast = ast
        
        content_parts = []
        
        # Read module files
        for py_file in module_path.glob("*.py"):
            if py_file.name.startswith("_") and py_file.name != "__init__.py":
                continue
            
            try:
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        class_doc = self._extract_class_doc(node, source)
                        if class_doc:
                            content_parts.append(class_doc)
                    elif isinstance(node, ast.FunctionDef):
                        if not node.name.startswith("_"):
                            func_doc = self._extract_function_doc(node, source)
                            if func_doc:
                                content_parts.append(func_doc)
            except Exception:
                pass
        
        return "\n\n".join(content_parts)
    
    def _extract_class_doc(self, node, source: str) -> Optional[str]:
        """Extract documentation for a class."""
        import ast
        docstring = ast.get_docstring(node) or ""
        
        # Get class signature
        lines = source.split("\n")
        _ = lines[node.lineno - 1] if node.lineno <= len(lines) else ""  # For future use
        
        doc = f"### `{node.name}`\n\n"
        if docstring:
            doc += f"{docstring}\n\n"
        
        # Extract __init__ parameters
        import ast
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                params = self._extract_params(item)
                if params:
                    doc += "**Parameters:**\n\n"
                    for param_name, param_type in params:
                        doc += f"- `{param_name}`: {param_type}\n"
        
        return doc
    
    def _extract_function_doc(self, node, source: str) -> Optional[str]:
        """Extract documentation for a function."""
        import ast
        docstring = ast.get_docstring(node) or ""
        
        doc = f"#### `{node.name}()`\n\n"
        if docstring:
            doc += f"{docstring}\n\n"
        
        return doc
    
    def _extract_params(self, node) -> List[Tuple[str, str]]:
        """Extract parameters from a function."""
        import ast
        params = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            param_type = "Any"
            if arg.annotation:
                param_type = ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else str(arg.annotation)
            params.append((arg.arg, param_type))
        return params
