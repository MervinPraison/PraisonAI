"""
Custom Skill Creation Example

This example demonstrates how to programmatically create and validate
custom Agent Skills using PraisonAI Agents.
"""

import tempfile
from pathlib import Path

from praisonaiagents.skills import (
    SkillManager,
    SkillLoader,
    validate,
    read_properties,
)


def create_custom_skill(
    name: str,
    description: str,
    instructions: str,
    base_dir: str = None
) -> Path:
    """Create a custom skill programmatically.
    
    Args:
        name: Skill name (kebab-case)
        description: What the skill does
        instructions: Markdown instructions for the skill
        base_dir: Directory to create skill in (default: temp dir)
        
    Returns:
        Path to the created skill directory
    """
    if base_dir is None:
        base_dir = tempfile.mkdtemp()
    
    skill_dir = Path(base_dir) / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    
    # Create SKILL.md
    skill_md_content = f"""---
name: {name}
description: {description}
license: Apache-2.0
metadata:
  author: custom
  version: "1.0"
---

{instructions}
"""
    (skill_dir / "SKILL.md").write_text(skill_md_content)
    
    # Create optional directories
    (skill_dir / "scripts").mkdir(exist_ok=True)
    (skill_dir / "references").mkdir(exist_ok=True)
    (skill_dir / "assets").mkdir(exist_ok=True)
    
    return skill_dir


def main():
    print("=" * 60)
    print("Custom Skill Creation Example")
    print("=" * 60)
    
    # Create a custom skill
    print("\n1. Creating a custom skill...")
    
    skill_path = create_custom_skill(
        name="code-review",
        description="Review code for best practices, bugs, and improvements. Use when asked to review or analyze code quality.",
        instructions="""
# Code Review Skill

## Overview
This skill enables thorough code review with focus on:
- Code quality and readability
- Potential bugs and edge cases
- Performance considerations
- Security vulnerabilities
- Best practices adherence

## Instructions

When reviewing code:

1. **Read the code carefully** - Understand the purpose and flow
2. **Check for bugs** - Look for null checks, edge cases, error handling
3. **Evaluate readability** - Variable names, comments, structure
4. **Consider performance** - Time/space complexity, unnecessary operations
5. **Security review** - Input validation, injection risks, data exposure
6. **Suggest improvements** - Provide actionable recommendations

## Output Format

Structure your review as:
- Summary: Brief overview of the code
- Issues: List of problems found (severity: high/medium/low)
- Suggestions: Recommended improvements
- Positive aspects: What's done well
"""
    )
    
    print(f"   Created skill at: {skill_path}")
    
    # Validate the skill
    print("\n2. Validating the skill...")
    errors = validate(skill_path)
    
    if errors:
        print("   Validation errors:")
        for error in errors:
            print(f"   - {error}")
    else:
        print("   ✓ Skill is valid!")
    
    # Load and inspect the skill
    print("\n3. Loading skill properties...")
    props = read_properties(skill_path)
    print(f"   Name: {props.name}")
    print(f"   Description: {props.description[:60]}...")
    print(f"   License: {props.license}")
    
    # Use with SkillLoader for progressive loading
    print("\n4. Using SkillLoader for progressive disclosure...")
    loader = SkillLoader()
    
    # Level 1: Load metadata only
    skill = loader.load_metadata(str(skill_path))
    print(f"   Level 1 - Metadata loaded: {skill.properties.name}")
    print(f"   Instructions loaded: {skill.is_activated}")
    
    # Level 2: Activate (load instructions)
    loader.activate(skill)
    print(f"   Level 2 - Activated: {skill.is_activated}")
    print(f"   Instructions preview: {skill.instructions[:100]}...")
    
    # Use with SkillManager
    print("\n5. Using with SkillManager...")
    manager = SkillManager()
    manager.add_skill(str(skill_path))
    
    # Generate prompt XML
    prompt = manager.to_prompt()
    print("   Generated prompt XML:")
    print(prompt)
    
    # Clean up
    print("\n6. Cleanup...")
    import shutil
    shutil.rmtree(skill_path.parent)
    print("   Temporary files removed.")
    
    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
