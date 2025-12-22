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
        output_dir: Optional[str] = None
    ) -> str:
        """Create a new skill from template.
        
        Args:
            name: Skill name (kebab-case)
            description: Skill description
            output_dir: Directory to create skill in (default: current dir)
            
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
        
        # Create SKILL.md
        skill_md_content = f"""---
name: {name}
description: {description}
license: Apache-2.0
compatibility: Works with PraisonAI Agents
metadata:
  author: user
  version: "1.0"
---

# {name.replace('-', ' ').title()}

## Overview

{description}

## Usage

Describe how to use this skill.

## Instructions

1. Step one
2. Step two
3. Step three
"""
        (skill_dir / "SKILL.md").write_text(skill_md_content)
        
        # Create placeholder files
        (skill_dir / "scripts" / ".gitkeep").write_text("")
        (skill_dir / "references" / ".gitkeep").write_text("")
        (skill_dir / "assets" / ".gitkeep").write_text("")
        
        if self.verbose:
            print(f"✓ Created skill at {skill_dir}")
            print("  - SKILL.md")
            print("  - scripts/")
            print("  - references/")
            print("  - assets/")
        
        return str(skill_dir)
    
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
            description = args.description if hasattr(args, 'description') else "A custom skill"
            output_dir = args.output if hasattr(args, 'output') else None
            handler.create_skill(args.name, description, output_dir)
            
        elif args.skills_command == "prompt":
            dirs = args.dirs if hasattr(args, 'dirs') and args.dirs else None
            handler.generate_prompt(dirs, include_defaults=True)
            
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
        help='Create a new skill from template'
    )
    create_parser.add_argument(
        '--name',
        required=True,
        help='Skill name (kebab-case)'
    )
    create_parser.add_argument(
        '--description',
        default='A custom skill',
        help='Skill description'
    )
    create_parser.add_argument(
        '--output',
        help='Output directory (default: current directory)'
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
