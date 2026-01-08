"""
Skills CLI Feature Handler

Provides CLI commands for managing Agent Skills:
- list: List available skills
- validate: Validate a skill directory
- create: Create a new skill from template
- prompt: Generate prompt XML for skills
"""

import os
from pathlib import Path
from typing import Optional, List


class SkillsHandler:
    """Handler for skills CLI commands."""
    
    def __init__(self, verbose: bool = True):
        """Initialize the skills handler.
        
        Args:
            verbose: Whether to print verbose output
        """
        self.verbose = verbose
    
    def list_skills(
        self,
        skill_dirs: Optional[List[str]] = None,
        include_defaults: bool = True
    ) -> List[dict]:
        """List all available skills.
        
        Args:
            skill_dirs: Optional list of directories to scan
            include_defaults: Whether to include default skill directories
            
        Returns:
            List of skill info dictionaries
        """
        from praisonaiagents.skills import discover_skills
        
        skills = discover_skills(skill_dirs, include_defaults)
        
        result = []
        for skill in skills:
            info = {
                "name": skill.name,
                "description": skill.description,
                "path": str(skill.path) if skill.path else None,
                "license": skill.license,
            }
            result.append(info)
            
            if self.verbose:
                print(f"  {skill.name}: {skill.description[:60]}...")
        
        if self.verbose and not result:
            print("No skills found.")
        
        return result
    
    def validate_skill(self, skill_path: str) -> dict:
        """Validate a skill directory.
        
        Args:
            skill_path: Path to the skill directory
            
        Returns:
            Validation result dictionary with 'valid' and 'errors' keys
        """
        from praisonaiagents.skills import validate
        
        path = Path(skill_path).expanduser().resolve()
        errors = validate(path)
        
        result = {
            "valid": len(errors) == 0,
            "path": str(path),
            "errors": errors
        }
        
        if self.verbose:
            if result["valid"]:
                print(f"✓ Skill at {path} is valid")
            else:
                print(f"✗ Skill at {path} has errors:")
                for error in errors:
                    print(f"  - {error}")
        
        return result
    
    def create_skill(
        self,
        name: str,
        description: str = "A custom skill",
        output_dir: Optional[str] = None,
        author: Optional[str] = None,
        license: Optional[str] = None,
        compatibility: Optional[str] = None,
        template: bool = False,
        use_ai: bool = True,
        generate_script: bool = False
    ) -> str:
        """Create a new skill from template or AI generation.
        
        Args:
            name: Skill name (kebab-case)
            description: Skill description (also used as prompt for AI)
            output_dir: Directory to create skill in (default: current dir)
            author: Author name for metadata
            license: License type (default: Apache-2.0)
            compatibility: Compatibility information
            template: If True, use template only (no AI)
            use_ai: If True, try to use AI to generate content
            generate_script: If True, generate scripts/skill.py
            
        Returns:
            Path to created skill directory
        """
        # Validate name format
        import re
        if not re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', name) and len(name) > 1:
            if not re.match(r'^[a-z]$', name):
                raise ValueError(
                    f"Invalid skill name '{name}'. "
                    "Must be lowercase, use hyphens, and not start/end with hyphen."
                )
        
        base_dir = Path(output_dir or os.getcwd())
        skill_dir = base_dir / name
        
        if skill_dir.exists():
            raise ValueError(f"Directory already exists: {skill_dir}")
        
        # Create directory structure
        skill_dir.mkdir(parents=True)
        (skill_dir / "scripts").mkdir()
        (skill_dir / "references").mkdir()
        (skill_dir / "assets").mkdir()
        
        # Set defaults
        author = author or "user"
        license = license or "Apache-2.0"
        compatibility = compatibility or "Works with PraisonAI Agents"
        
        # Try AI generation if requested and not in template mode
        ai_content = None
        if use_ai and not template:
            ai_content = self._generate_skill_content_with_ai(name, description)
        
        if ai_content and ai_content.get("skill_md"):
            # Use AI-generated content
            skill_md_content = ai_content["skill_md"]
            if self.verbose:
                print("✓ Generated SKILL.md with AI")
        else:
            # Use template
            skill_md_content = self._generate_template_content(
                name, description, author, license, compatibility,
                include_script=generate_script
            )
            if self.verbose and use_ai and not template:
                print("⚠ No API key found, using template")
        
        (skill_dir / "SKILL.md").write_text(skill_md_content)
        
        # Generate scripts/skill.py if requested or AI provided it
        if generate_script or (ai_content and ai_content.get("skill_py")):
            script_content = (ai_content or {}).get("skill_py") or self._generate_template_script(name, description)
            # Strip any remaining code blocks from script content
            script_content = self._strip_code_blocks(script_content)
            (skill_dir / "scripts" / "skill.py").write_text(script_content)
            if self.verbose:
                print("  - scripts/skill.py")
        else:
            (skill_dir / "scripts" / ".gitkeep").write_text("")
        
        # Create placeholder files
        (skill_dir / "references" / ".gitkeep").write_text("")
        (skill_dir / "assets" / ".gitkeep").write_text("")
        
        if self.verbose:
            print(f"✓ Created skill at {skill_dir}")
            print("  - SKILL.md")
            print("  - scripts/")
            print("  - references/")
            print("  - assets/")
        
        return str(skill_dir)
    
    def _generate_template_content(
        self,
        name: str,
        description: str,
        author: str,
        license: str,
        compatibility: str,
        include_script: bool = False
    ) -> str:
        """Generate template SKILL.md content."""
        title = name.replace('-', ' ').title()
        func_name = name.replace('-', '_')
        
        script_section = ""
        if include_script:
            script_section = f"""
## Script Usage

This skill includes a Python script at `scripts/skill.py` that provides the core functionality.

### Running the Script

```bash
python scripts/skill.py <input>
```

### Using as a Module

```python
from scripts.skill import {func_name}

result = {func_name}(input_data)
print(result)
```
"""
        
        return f"""---
name: {name}
description: {description}
license: {license}
compatibility: {compatibility}
metadata:
  author: {author}
  version: "1.0"
---

# {title}

## Overview

{description}
{script_section}
## Usage

Describe how to use this skill.

## Instructions

1. Step one
2. Step two
3. Step three
"""
    
    def _generate_template_script(self, name: str, description: str) -> str:
        """Generate description-relevant scripts/skill.py content."""
        func_name = name.replace('-', '_')
        
        # Analyze description to generate relevant code
        desc_lower = description.lower()
        
        # CSV/Data analysis patterns
        if any(kw in desc_lower for kw in ['csv', 'spreadsheet', 'data analysis', 'analyze data', 'tabular']):
            return self._generate_csv_script(name, description, func_name)
        
        # PDF patterns
        if any(kw in desc_lower for kw in ['pdf', 'document', 'extract text']):
            return self._generate_pdf_script(name, description, func_name)
        
        # Web/API patterns
        if any(kw in desc_lower for kw in ['api', 'http', 'request', 'web', 'fetch', 'url']):
            return self._generate_api_script(name, description, func_name)
        
        # File processing patterns
        if any(kw in desc_lower for kw in ['file', 'read', 'write', 'process', 'parse']):
            return self._generate_file_script(name, description, func_name)
        
        # Image patterns
        if any(kw in desc_lower for kw in ['image', 'photo', 'picture', 'resize', 'convert']):
            return self._generate_image_script(name, description, func_name)
        
        # JSON/YAML patterns
        if any(kw in desc_lower for kw in ['json', 'yaml', 'config', 'configuration']):
            return self._generate_json_script(name, description, func_name)
        
        # Text processing patterns
        if any(kw in desc_lower for kw in ['text', 'string', 'regex', 'search', 'replace', 'format']):
            return self._generate_text_script(name, description, func_name)
        
        # Default generic script
        return self._generate_generic_script(name, description, func_name)
    
    def _generate_csv_script(self, name: str, description: str, func_name: str) -> str:
        """Generate CSV analysis script."""
        return f'''"""
{name} - {description}

This script provides functionality for the {name} skill.
"""
import sys
import json
import pandas as pd


def json_serializer(obj):
    """Handle numpy types for JSON serialization."""
    if hasattr(obj, 'item'):
        return obj.item()
    elif hasattr(obj, 'tolist'):
        return obj.tolist()
    return str(obj)


def {func_name}(file_path: str) -> dict:
    """
    Analyze CSV file and return statistics.
    
    Args:
        file_path: Path to the CSV file to analyze
        
    Returns:
        Dictionary with analysis results
    """
    df = pd.read_csv(file_path)
    
    result = {{
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns),
        "dtypes": {{col: str(dtype) for col, dtype in df.dtypes.items()}},
        "missing_values": {{k: int(v) for k, v in df.isnull().sum().to_dict().items()}},
        "numeric_summary": {{}}
    }}
    
    numeric_cols = df.select_dtypes(include=['number']).columns
    for col in numeric_cols:
        result["numeric_summary"][col] = {{
            "mean": float(df[col].mean()),
            "std": float(df[col].std()) if len(df) > 1 else 0.0,
            "min": float(df[col].min()),
            "max": float(df[col].max())
        }}
    
    return result


def main():
    """Main entry point for the skill."""
    if len(sys.argv) > 1:
        result = {func_name}(sys.argv[1])
        print(json.dumps(result, indent=2, default=json_serializer))
    else:
        print("Usage: python skill.py <csv_file>")


if __name__ == "__main__":
    main()
'''
    
    def _generate_pdf_script(self, name: str, description: str, func_name: str) -> str:
        """Generate PDF processing script."""
        return f'''"""\n{name} - {description}\n\nThis script provides PDF processing functionality.\n"""\n\ndef {func_name}(file_path: str) -> dict:\n    """\n    Process PDF file and extract content.\n    \n    Args:\n        file_path: Path to the PDF file\n        \n    Returns:\n        Dictionary with extracted content\n    """\n    from pypdf import PdfReader\n    \n    reader = PdfReader(file_path)\n    \n    result = {{\n        "pages": len(reader.pages),\n        "metadata": {{\n            "title": reader.metadata.title if reader.metadata else None,\n            "author": reader.metadata.author if reader.metadata else None\n        }},\n        "text": []\n    }}\n    \n    for i, page in enumerate(reader.pages):\n        result["text"].append({{\n            "page": i + 1,\n            "content": page.extract_text()\n        }})\n    \n    return result\n\n\ndef main():\n    """Main entry point for the skill."""\n    import sys\n    import json\n    \n    if len(sys.argv) > 1:\n        result = {func_name}(sys.argv[1])\n        print(json.dumps(result, indent=2))\n    else:\n        print("Usage: python skill.py <pdf_file>")\n\n\nif __name__ == "__main__":\n    main()\n'''
    
    def _generate_api_script(self, name: str, description: str, func_name: str) -> str:
        """Generate API/HTTP request script."""
        return f'''"""\n{name} - {description}\n\nThis script provides API request functionality.\n"""\nimport requests\n\ndef {func_name}(url: str, method: str = "GET", data: dict = None) -> dict:\n    """\n    Make HTTP request to API endpoint.\n    \n    Args:\n        url: API endpoint URL\n        method: HTTP method (GET, POST, PUT, DELETE)\n        data: Optional request body data\n        \n    Returns:\n        Dictionary with response data\n    """\n    headers = {{"Content-Type": "application/json"}}\n    \n    if method.upper() == "GET":\n        response = requests.get(url, headers=headers)\n    elif method.upper() == "POST":\n        response = requests.post(url, json=data, headers=headers)\n    elif method.upper() == "PUT":\n        response = requests.put(url, json=data, headers=headers)\n    elif method.upper() == "DELETE":\n        response = requests.delete(url, headers=headers)\n    else:\n        raise ValueError(f"Unsupported method: {{method}}")\n    \n    return {{\n        "status_code": response.status_code,\n        "headers": dict(response.headers),\n        "data": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text\n    }}\n\n\ndef main():\n    """Main entry point for the skill."""\n    import sys\n    import json\n    \n    if len(sys.argv) > 1:\n        result = {func_name}(sys.argv[1])\n        print(json.dumps(result, indent=2))\n    else:\n        print("Usage: python skill.py <url>")\n\n\nif __name__ == "__main__":\n    main()\n'''
    
    def _generate_file_script(self, name: str, description: str, func_name: str) -> str:
        """Generate file processing script."""
        return f'''"""\n{name} - {description}\n\nThis script provides file processing functionality.\n"""\nfrom pathlib import Path\n\ndef {func_name}(file_path: str) -> dict:\n    """\n    Process file and return information.\n    \n    Args:\n        file_path: Path to the file to process\n        \n    Returns:\n        Dictionary with file information and content\n    """\n    path = Path(file_path)\n    \n    if not path.exists():\n        raise FileNotFoundError(f"File not found: {{file_path}}")\n    \n    stat = path.stat()\n    \n    result = {{\n        "name": path.name,\n        "extension": path.suffix,\n        "size_bytes": stat.st_size,\n        "is_file": path.is_file(),\n        "is_dir": path.is_dir()\n    }}\n    \n    if path.is_file() and stat.st_size < 1024 * 1024:\n        try:\n            result["content"] = path.read_text()\n            result["lines"] = len(result["content"].splitlines())\n        except UnicodeDecodeError:\n            result["content"] = "<binary file>"\n    \n    return result\n\n\ndef main():\n    """Main entry point for the skill."""\n    import sys\n    import json\n    \n    if len(sys.argv) > 1:\n        result = {func_name}(sys.argv[1])\n        print(json.dumps(result, indent=2))\n    else:\n        print("Usage: python skill.py <file_path>")\n\n\nif __name__ == "__main__":\n    main()\n'''
    
    def _generate_image_script(self, name: str, description: str, func_name: str) -> str:
        """Generate image processing script."""
        return f'''"""\n{name} - {description}\n\nThis script provides image processing functionality.\n"""\nfrom PIL import Image\n\ndef {func_name}(file_path: str, output_path: str = None, resize: tuple = None) -> dict:\n    """\n    Process image file.\n    \n    Args:\n        file_path: Path to the image file\n        output_path: Optional output path for processed image\n        resize: Optional tuple (width, height) to resize\n        \n    Returns:\n        Dictionary with image information\n    """\n    img = Image.open(file_path)\n    \n    result = {{\n        "format": img.format,\n        "mode": img.mode,\n        "size": img.size,\n        "width": img.width,\n        "height": img.height\n    }}\n    \n    if resize:\n        img = img.resize(resize)\n        result["resized_to"] = resize\n    \n    if output_path:\n        img.save(output_path)\n        result["saved_to"] = output_path\n    \n    return result\n\n\ndef main():\n    """Main entry point for the skill."""\n    import sys\n    import json\n    \n    if len(sys.argv) > 1:\n        result = {func_name}(sys.argv[1])\n        print(json.dumps(result, indent=2))\n    else:\n        print("Usage: python skill.py <image_file>")\n\n\nif __name__ == "__main__":\n    main()\n'''
    
    def _generate_json_script(self, name: str, description: str, func_name: str) -> str:
        """Generate JSON/YAML processing script."""
        return f'''"""\n{name} - {description}\n\nThis script provides JSON/YAML processing functionality.\n"""\nimport json\nfrom pathlib import Path\n\ndef {func_name}(file_path: str) -> dict:\n    """\n    Process JSON or YAML file.\n    \n    Args:\n        file_path: Path to the JSON/YAML file\n        \n    Returns:\n        Dictionary with parsed content and metadata\n    """\n    path = Path(file_path)\n    content = path.read_text()\n    \n    if path.suffix in [".yaml", ".yml"]:\n        import yaml\n        data = yaml.safe_load(content)\n    else:\n        data = json.loads(content)\n    \n    result = {{\n        "file": file_path,\n        "format": "yaml" if path.suffix in [".yaml", ".yml"] else "json",\n        "keys": list(data.keys()) if isinstance(data, dict) else None,\n        "length": len(data) if isinstance(data, (list, dict)) else None,\n        "data": data\n    }}\n    \n    return result\n\n\ndef main():\n    """Main entry point for the skill."""\n    import sys\n    \n    if len(sys.argv) > 1:\n        result = {func_name}(sys.argv[1])\n        print(json.dumps(result, indent=2))\n    else:\n        print("Usage: python skill.py <json_or_yaml_file>")\n\n\nif __name__ == "__main__":\n    main()\n'''
    
    def _generate_text_script(self, name: str, description: str, func_name: str) -> str:
        """Generate text processing script."""
        return f'''"""\n{name} - {description}\n\nThis script provides text processing functionality.\n"""\nimport re\n\ndef {func_name}(text: str, pattern: str = None, replacement: str = None) -> dict:\n    """\n    Process text with optional regex operations.\n    \n    Args:\n        text: Input text to process\n        pattern: Optional regex pattern to search\n        replacement: Optional replacement string\n        \n    Returns:\n        Dictionary with processing results\n    """\n    result = {{\n        "original_length": len(text),\n        "lines": len(text.splitlines()),\n        "words": len(text.split()),\n        "characters": len(text.replace(" ", ""))\n    }}\n    \n    if pattern:\n        matches = re.findall(pattern, text)\n        result["matches"] = matches\n        result["match_count"] = len(matches)\n        \n        if replacement is not None:\n            result["replaced_text"] = re.sub(pattern, replacement, text)\n    \n    return result\n\n\ndef main():\n    """Main entry point for the skill."""\n    import sys\n    import json\n    \n    if len(sys.argv) > 1:\n        with open(sys.argv[1]) as f:\n            text = f.read()\n        result = {func_name}(text)\n        print(json.dumps(result, indent=2))\n    else:\n        print("Usage: python skill.py <text_file>")\n\n\nif __name__ == "__main__":\n    main()\n'''
    
    def _generate_generic_script(self, name: str, description: str, func_name: str) -> str:
        """Generate generic script template."""
        return f'''"""
{name} - {description}

This script provides functionality for the {name} skill.
"""

def {func_name}(input_data: str) -> str:
    """
    Process input data for {name}.
    
    Args:
        input_data: The input to process
        
    Returns:
        Processed result
    """
    result = f"Processed: {{input_data}}"
    return result


def main():
    """Main entry point for the skill."""
    import sys
    if len(sys.argv) > 1:
        result = {func_name}(sys.argv[1])
        print(result)
    else:
        print("Usage: python skill.py <input>")


if __name__ == "__main__":
    main()
'''
    
    def _generate_skill_content_with_ai(
        self,
        name: str,
        description: str
    ) -> Optional[dict]:
        """Generate SKILL.md and optional skill.py using AI.
        
        Args:
            name: Skill name
            description: Skill description/prompt
            
        Returns:
            Dict with 'skill_md' and optionally 'skill_py', or None if no API key
        """
        # Check for API keys
        api_key = (
            os.environ.get("OPENAI_API_KEY") or
            os.environ.get("ANTHROPIC_API_KEY") or
            os.environ.get("GOOGLE_API_KEY") or
            os.environ.get("GEMINI_API_KEY")
        )
        
        if not api_key:
            return None
        
        try:
            from praisonaiagents import Agent
            
            # Create prompt for AI to generate skill content
            prompt = f"""Create a comprehensive SKILL.md file for an Agent Skill with the following details:

Name: {name}
Description: {description}

The SKILL.md must follow this exact format:

```markdown
---
name: {name}
description: {description}
license: Apache-2.0
compatibility: Works with PraisonAI Agents, Claude Code, and other Agent Skills compatible tools
metadata:
  author: user
  version: "1.0"
---

# [Title]

## Overview
[Detailed overview of what this skill does]

## When to Use
[Describe when this skill should be activated]

## Instructions
[Step-by-step instructions for the agent]

## Examples
[Provide concrete examples]

## Best Practices
[List best practices]
```

Generate detailed, practical content based on the description. Make it comprehensive but concise.
The skill should be immediately useful for an AI agent.

Also, if this skill requires any Python code to function, provide a skill.py that implements the core functionality.
The script MUST follow this pattern:
1. Have a main function that accepts file path as command line argument (sys.argv[1])
2. Print JSON output using json.dumps() with a custom default handler for numpy types
3. Include usage message if no arguments provided
4. Convert numpy types to native Python types (int, float) before JSON serialization

Example script pattern:
```python
import sys
import json

def json_serializer(obj):
    \"\"\"Handle numpy types for JSON serialization.\"\"\"
    if hasattr(obj, 'item'):
        return obj.item()
    elif hasattr(obj, 'tolist'):
        return obj.tolist()
    return str(obj)

def process_file(file_path: str) -> dict:
    # Core logic here
    return {{"result": "data"}}

def main():
    if len(sys.argv) > 1:
        result = process_file(sys.argv[1])
        print(json.dumps(result, indent=2, default=json_serializer))
    else:
        print("Usage: python skill.py <file_path>")

if __name__ == "__main__":
    main()
```

Format your response as:
---SKILL.MD---
[content]
---SKILL.PY---
[content or "NONE" if no script needed]
"""
            
            agent = Agent(
                name="SkillGenerator",
                role="Skill Content Generator",
                goal="Generate high-quality Agent Skill content",
                instructions="You are an expert at creating Agent Skills. Generate comprehensive, practical skill content.",
                llm=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"), output="minimal"
            )
            
            result = agent.start(prompt)
            
            # Parse the response
            if result and "---SKILL.MD---" in result:
                parts = result.split("---SKILL.MD---")
                if len(parts) > 1:
                    skill_md_part = parts[1]
                    skill_py = None
                    
                    if "---SKILL.PY---" in skill_md_part:
                        md_parts = skill_md_part.split("---SKILL.PY---")
                        skill_md = self._strip_code_blocks(md_parts[0].strip())
                        skill_py_content = md_parts[1].strip() if len(md_parts) > 1 else None
                        if skill_py_content and skill_py_content.upper() != "NONE":
                            skill_py = self._strip_code_blocks(skill_py_content)
                    else:
                        skill_md = self._strip_code_blocks(skill_md_part.strip())
                    
                    return {"skill_md": skill_md, "skill_py": skill_py}
            
            return None
            
        except Exception as e:
            if self.verbose:
                print(f"⚠ AI generation failed: {e}")
            return None
    
    def _strip_code_blocks(self, content: str) -> str:
        """Strip markdown code block wrappers from content.
        
        Args:
            content: Content that may be wrapped in ```markdown or ```python blocks
            
        Returns:
            Content with code block wrappers removed
        """
        import re
        # Match ```language at start and ``` at end
        pattern = r'^```(?:markdown|python|json|yaml|md)?\s*\n?(.*?)\n?```\s*$'
        match = re.match(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content
    
    def upload_skill(
        self,
        skill_path: str,
        display_title: Optional[str] = None
    ) -> Optional[str]:
        """Upload a skill to Anthropic Skills API.
        
        Args:
            skill_path: Path to the skill directory
            display_title: Optional display title for the skill
            
        Returns:
            Skill ID if successful, None otherwise
        """
        path = Path(skill_path).expanduser().resolve()
        
        if not path.exists():
            raise ValueError(f"Skill path does not exist: {path}")
        
        skill_md_path = path / "SKILL.md"
        if not skill_md_path.exists():
            raise ValueError(f"SKILL.md not found in {path}")
        
        # Check for Anthropic API key
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable is required")
            return None
        
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=api_key)
            
            # Read skill name from SKILL.md
            skill_md_content = skill_md_path.read_text()
            skill_name = path.name
            
            # Extract name from frontmatter if possible
            if "---" in skill_md_content:
                import re
                match = re.search(r'^name:\s*(.+)$', skill_md_content, re.MULTILINE)
                if match:
                    skill_name = match.group(1).strip()
            
            title = display_title or skill_name.replace('-', ' ').title()
            
            if self.verbose:
                print(f"Uploading skill '{skill_name}' to Anthropic...")
            
            # Create skill using Anthropic API
            with open(skill_md_path, 'rb') as f:
                response = client.beta.skills.create(
                    display_title=title,
                    files=[(f"{skill_name}/SKILL.md", f, "text/markdown")],
                    betas=["skills-2025-10-02"]
                )
            
            if self.verbose:
                print("✓ Skill uploaded successfully!")
                print(f"  ID: {response.id}")
                print(f"  Title: {response.display_title}")
            
            return response.id
            
        except ImportError:
            print("Error: anthropic package is required. Install with: pip install anthropic")
            return None
        except Exception as e:
            if self.verbose:
                print(f"❌ Upload failed: {e}")
            return None
    
    def generate_prompt(
        self,
        skill_dirs: Optional[List[str]] = None,
        include_defaults: bool = True
    ) -> str:
        """Generate prompt XML for available skills.
        
        Args:
            skill_dirs: Optional list of directories to scan
            include_defaults: Whether to include default skill directories
            
        Returns:
            XML string with <available_skills> block
        """
        from praisonaiagents.skills import SkillManager
        
        manager = SkillManager()
        
        if skill_dirs:
            manager.discover(skill_dirs, include_defaults=include_defaults)
        elif include_defaults:
            manager.discover(include_defaults=True)
        
        prompt = manager.to_prompt()
        
        if self.verbose:
            print(prompt)
        
        return prompt


def handle_skills_command(args) -> int:
    """Handle skills subcommand from CLI.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    handler = SkillsHandler(verbose=True)
    
    try:
        if args.skills_command == "list":
            dirs = args.dirs if hasattr(args, 'dirs') and args.dirs else None
            handler.list_skills(dirs, include_defaults=True)
            
        elif args.skills_command == "validate":
            if not hasattr(args, 'path') or not args.path:
                print("Error: --path is required for validate command")
                return 1
            result = handler.validate_skill(args.path)
            return 0 if result["valid"] else 1
            
        elif args.skills_command == "create":
            if not hasattr(args, 'name') or not args.name:
                print("Error: --name is required for create command")
                return 1
            
            # Get all optional arguments
            description = getattr(args, 'description', None) or "A custom skill"
            output_dir = getattr(args, 'output_dir', None) or getattr(args, 'output', None)
            author = getattr(args, 'author', None)
            license_type = getattr(args, 'license', None)
            compatibility = getattr(args, 'compatibility', None)
            template = getattr(args, 'template', False)
            generate_script = getattr(args, 'script', False)
            
            handler.create_skill(
                name=args.name,
                description=description,
                output_dir=output_dir,
                author=author,
                license=license_type,
                compatibility=compatibility,
                template=template,
                use_ai=not template,
                generate_script=generate_script
            )
            
        elif args.skills_command == "prompt":
            dirs = args.dirs if hasattr(args, 'dirs') and args.dirs else None
            handler.generate_prompt(dirs, include_defaults=True)
        
        elif args.skills_command == "upload":
            if not hasattr(args, 'path') or not args.path:
                print("Error: --path is required for upload command")
                return 1
            title = getattr(args, 'title', None)
            handler.upload_skill(args.path, title)
            
        else:
            print(f"Unknown skills command: {args.skills_command}")
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


def add_skills_parser(subparsers) -> None:
    """Add skills subcommand to argument parser.
    
    Args:
        subparsers: Subparsers object from argparse
    """
    # subparsers is already the skills subparsers object
    # We just need to add the subcommands to it
    
    # list command
    list_parser = subparsers.add_parser(
        'list',
        help='List available skills'
    )
    list_parser.add_argument(
        '--dirs',
        nargs='+',
        help='Directories to scan for skills'
    )
    
    # validate command
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate a skill directory'
    )
    validate_parser.add_argument(
        '--path',
        required=True,
        help='Path to skill directory'
    )
    
    # create command
    create_parser = subparsers.add_parser(
        'create',
        help='Create a new skill (uses AI by default, --template for template only)'
    )
    create_parser.add_argument(
        '--name',
        required=True,
        help='Skill name (kebab-case, e.g., my-skill)'
    )
    create_parser.add_argument(
        '--description',
        default='A custom skill',
        help='Skill description (used as prompt for AI generation)'
    )
    create_parser.add_argument(
        '--output-dir', '--output',
        dest='output_dir',
        help='Output directory (default: current directory)'
    )
    create_parser.add_argument(
        '--author',
        help='Author name for skill metadata'
    )
    create_parser.add_argument(
        '--license',
        help='License type (default: Apache-2.0)'
    )
    create_parser.add_argument(
        '--compatibility',
        help='Compatibility information'
    )
    create_parser.add_argument(
        '--template',
        action='store_true',
        help='Use template only, skip AI generation'
    )
    create_parser.add_argument(
        '--script',
        action='store_true',
        help='Generate scripts/skill.py with template code'
    )
    
    # prompt command
    prompt_parser = subparsers.add_parser(
        'prompt',
        help='Generate prompt XML for skills'
    )
    prompt_parser.add_argument(
        '--dirs',
        nargs='+',
        help='Directories to scan for skills'
    )
    
    # upload command - upload skill to Anthropic
    upload_parser = subparsers.add_parser(
        'upload',
        help='Upload skill to Anthropic Skills API'
    )
    upload_parser.add_argument(
        '--path',
        required=True,
        help='Path to skill directory'
    )
    upload_parser.add_argument(
        '--title',
        help='Display title for the skill'
    )
