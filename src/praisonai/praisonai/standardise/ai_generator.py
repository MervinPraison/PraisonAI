"""
AI-powered content generation for the FDEP standardisation system.

Uses Agent() to generate:
- Documentation pages (concepts, features, cli, sdk)
- Example files (basic, advanced)

Features:
- Template-guided generation
- Context-aware (SDK info, existing examples)
- Verification via Agent()
- Dry-run preview
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import ArtifactType, FeatureSlug
from .templates import TemplateGenerator


class AIGenerator:
    """AI-powered content generator using praisonaiagents."""
    
    def __init__(self, 
                 model: str = "gpt-4o-mini",
                 sdk_root: Optional[Path] = None,
                 docs_root: Optional[Path] = None,
                 examples_root: Optional[Path] = None):
        self.model = model
        self.sdk_root = sdk_root
        self.docs_root = docs_root
        self.examples_root = examples_root
        self.template_generator = TemplateGenerator()
        self._agent = None
        self._verifier = None
    
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
                    verbose=False,
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
                    verbose=False,
                )
            except ImportError:
                raise RuntimeError("praisonaiagents not available")
        return self._verifier
    
    def generate(self, slug: FeatureSlug, artifact_type: ArtifactType,
                 dry_run: bool = True) -> Tuple[str, Optional[str]]:
        """
        Generate content for an artifact using AI.
        
        Args:
            slug: Feature slug
            artifact_type: Type of artifact to generate
            dry_run: If True, return content without writing
        
        Returns:
            Tuple of (generated_content, output_path or None if dry_run)
        """
        # Get template as base
        template = self.template_generator.generate(slug, artifact_type)
        
        # Gather context
        context = self._gather_context(slug, artifact_type)
        
        # Build prompt
        prompt = self._build_generation_prompt(slug, artifact_type, template, context)
        
        # Generate with AI
        agent = self._get_agent()
        result = agent.start(prompt)
        
        # Extract content
        content = self._extract_content(result, artifact_type)
        
        if dry_run:
            return content, None
        
        # Write to file
        output_path = self.template_generator.get_expected_path(
            slug, artifact_type,
            docs_root=self.docs_root,
            examples_root=self.examples_root,
        )
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            return content, str(output_path)
        
        return content, None
    
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
        """Gather context for generation."""
        context = {}
        slug_str = slug.normalised
        
        # Get SDK module info
        if self.sdk_root:
            sdk_path = self.sdk_root / slug_str.replace("-", "_")
            if sdk_path.exists():
                context["sdk_module"] = self._read_sdk_module(sdk_path)
            
            # Also check for init file
            init_file = sdk_path / "__init__.py" if sdk_path.exists() else None
            if init_file and init_file.exists():
                context["sdk_exports"] = init_file.read_text(encoding="utf-8")[:2000]
        
        # Get existing examples
        if self.examples_root:
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
        """Build the generation prompt."""
        slug_str = slug.normalised
        name = slug_str.replace("-", " ").title()
        
        prompt_parts = [
            f"Generate a {artifact_type.value} for the '{name}' feature in PraisonAI.",
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
            "2. Use real, working code examples",
            "3. Be concise but comprehensive",
            "4. Include a mermaid diagram if this is a concept page",
            "5. Use Mintlify MDX components (CodeGroup, Tabs, Cards)",
            "6. Ensure all imports are correct for praisonaiagents",
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
