"""
Recipes CLI - Commands for managing and running Agent-Recipes.

Provides commands for:
- praison recipes list - List available recipes
- praison recipes info <name> - Show recipe details
- praison recipes run <name> <input> - Run a recipe
- praison recipes doctor <name> - Check recipe dependencies
- praison recipes explain <name> - Show recipe execution plan
- praison recipes init <name> - Initialize recipe in current directory
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Recipe discovery paths in order of precedence
RECIPE_PATHS = [
    Path.home() / ".praison" / "templates",
    Path.home() / ".config" / "praison" / "templates",
    Path.cwd() / ".praison" / "templates",
    Path("/Users/praison/Agent-Recipes/agent_recipes/templates"),
]


def find_recipe_paths() -> List[Path]:
    """Find all valid recipe directories."""
    paths = []
    for p in RECIPE_PATHS:
        if p.exists() and p.is_dir():
            paths.append(p)
    return paths


def list_recipes() -> List[Dict[str, Any]]:
    """List all available recipes."""
    recipes = []
    seen = set()
    
    for base_path in find_recipe_paths():
        for recipe_dir in base_path.iterdir():
            if not recipe_dir.is_dir():
                continue
            
            template_file = recipe_dir / "TEMPLATE.yaml"
            if not template_file.exists():
                continue
            
            name = recipe_dir.name
            if name in seen:
                continue
            seen.add(name)
            
            try:
                with open(template_file) as f:
                    template = yaml.safe_load(f)
                recipes.append({
                    "name": name,
                    "description": template.get("description", ""),
                    "version": template.get("version", "1.0.0"),
                    "tags": template.get("tags", []),
                    "path": str(recipe_dir),
                })
            except Exception as e:
                logger.warning(f"Failed to load recipe {name}: {e}")
    
    return sorted(recipes, key=lambda x: x["name"])


def get_recipe(name: str) -> Optional[Dict[str, Any]]:
    """Get recipe by name."""
    for base_path in find_recipe_paths():
        recipe_dir = base_path / name
        template_file = recipe_dir / "TEMPLATE.yaml"
        
        if template_file.exists():
            with open(template_file) as f:
                template = yaml.safe_load(f)
            template["path"] = str(recipe_dir)
            return template
    
    return None


def check_dependencies(recipe: Dict[str, Any]) -> Dict[str, bool]:
    """Check if recipe dependencies are satisfied."""
    results = {}
    requires = recipe.get("requires", {})
    
    # Check environment variables
    for env_var in requires.get("env", []):
        results[f"env:{env_var}"] = bool(os.environ.get(env_var))
    
    # Check Python packages
    for package in requires.get("packages", []):
        try:
            __import__(package.replace("-", "_").split("[")[0])
            results[f"package:{package}"] = True
        except ImportError:
            results[f"package:{package}"] = False
    
    # Check external tools
    import shutil
    for tool in requires.get("external", []):
        results[f"external:{tool}"] = shutil.which(tool) is not None
    
    # Check recipe tools
    for tool in requires.get("tools", []):
        try:
            from praisonai_tools.recipe_tools import __all__ as available_tools
            # Check if tool class exists
            tool_class = tool.replace("_tool", "").title() + "Tool"
            results[f"tool:{tool}"] = tool_class in available_tools or tool in str(available_tools)
        except ImportError:
            results[f"tool:{tool}"] = False
    
    return results


def cmd_list(args: argparse.Namespace) -> int:
    """List available recipes."""
    recipes = list_recipes()
    
    if args.json:
        print(json.dumps(recipes, indent=2))
        return 0
    
    if not recipes:
        print("No recipes found.")
        return 0
    
    # Group by first tag if available
    if args.group:
        groups = {}
        for r in recipes:
            tag = r["tags"][0] if r["tags"] else "other"
            if tag not in groups:
                groups[tag] = []
            groups[tag].append(r)
        
        for group, group_recipes in sorted(groups.items()):
            print(f"\n{group.upper()}:")
            for r in group_recipes:
                print(f"  {r['name']:<35} {r['description'][:50]}")
    else:
        print(f"{'Recipe':<35} {'Description':<50} {'Version'}")
        print("-" * 95)
        for r in recipes:
            desc = r["description"][:47] + "..." if len(r["description"]) > 50 else r["description"]
            print(f"{r['name']:<35} {desc:<50} {r['version']}")
    
    print(f"\nTotal: {len(recipes)} recipes")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Show recipe details."""
    recipe = get_recipe(args.name)
    
    if not recipe:
        print(f"Recipe not found: {args.name}")
        return 1
    
    if args.json:
        print(json.dumps(recipe, indent=2, default=str))
        return 0
    
    print(f"Name: {recipe.get('name', args.name)}")
    print(f"Version: {recipe.get('version', '1.0.0')}")
    print(f"Description: {recipe.get('description', '')}")
    print(f"Author: {recipe.get('author', 'unknown')}")
    print(f"License: {recipe.get('license', 'unknown')}")
    print(f"Path: {recipe.get('path', '')}")
    
    if recipe.get("tags"):
        print(f"Tags: {', '.join(recipe['tags'])}")
    
    requires = recipe.get("requires", {})
    if requires:
        print("\nRequirements:")
        if requires.get("env"):
            print(f"  Environment: {', '.join(requires['env'])}")
        if requires.get("packages"):
            print(f"  Packages: {', '.join(requires['packages'])}")
        if requires.get("external"):
            print(f"  External: {', '.join(requires['external'])}")
        if requires.get("tools"):
            print(f"  Tools: {', '.join(requires['tools'])}")
    
    cli = recipe.get("cli", {})
    if cli:
        print("\nCLI:")
        print(f"  Command: {cli.get('command', '')}")
        if cli.get("examples"):
            print("  Examples:")
            for ex in cli["examples"]:
                print(f"    {ex}")
    
    safety = recipe.get("safety", {})
    if safety:
        print("\nSafety:")
        print(f"  Dry-run default: {safety.get('dry_run_default', False)}")
        if safety.get("requires_consent"):
            print(f"  Requires consent: {safety.get('consent_message', 'Yes')}")
        if safety.get("legal_disclaimer"):
            print(f"  Legal disclaimer: {safety.get('legal_disclaimer')}")
    
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check recipe dependencies."""
    recipe = get_recipe(args.name)
    
    if not recipe:
        print(f"Recipe not found: {args.name}")
        return 1
    
    print(f"Checking dependencies for: {args.name}")
    print("-" * 50)
    
    deps = check_dependencies(recipe)
    all_ok = True
    
    for dep, status in sorted(deps.items()):
        icon = "✓" if status else "✗"
        color = "\033[92m" if status else "\033[91m"
        reset = "\033[0m"
        print(f"  {color}{icon}{reset} {dep}")
        if not status:
            all_ok = False
    
    print("-" * 50)
    if all_ok:
        print("All dependencies satisfied!")
        return 0
    else:
        print("\nMissing dependencies. Install with:")
        requires = recipe.get("requires", {})
        
        if requires.get("packages"):
            missing_pkgs = [p for p in requires["packages"] if not deps.get(f"package:{p}", True)]
            if missing_pkgs:
                print(f"  pip install {' '.join(missing_pkgs)}")
        
        if requires.get("external"):
            missing_ext = [e for e in requires["external"] if not deps.get(f"external:{e}", True)]
            if missing_ext:
                print(f"  # Install external tools: {', '.join(missing_ext)}")
        
        if requires.get("env"):
            missing_env = [e for e in requires["env"] if not deps.get(f"env:{e}", True)]
            if missing_env:
                print(f"  # Set environment variables: {', '.join(missing_env)}")
        
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Run a recipe."""
    recipe = get_recipe(args.name)
    
    if not recipe:
        print(f"Recipe not found: {args.name}")
        return 1
    
    # Check safety requirements
    safety = recipe.get("safety", {})
    
    if safety.get("requires_consent") and not args.consent:
        print(f"This recipe requires consent: {safety.get('consent_message', '')}")
        print("Use --consent flag to acknowledge.")
        return 1
    
    if safety.get("legal_disclaimer"):
        print(f"LEGAL DISCLAIMER: {safety['legal_disclaimer']}")
    
    # Check dependencies
    if not args.skip_checks:
        deps = check_dependencies(recipe)
        missing = [k for k, v in deps.items() if not v]
        if missing:
            print(f"Missing dependencies: {', '.join(missing)}")
            print("Run 'praison recipes doctor {args.name}' for details.")
            if not args.force:
                return 1
    
    # Dry run mode
    if args.dry_run or (safety.get("dry_run_default") and not args.write):
        print(f"DRY RUN: Would execute recipe '{args.name}'")
        print(f"  Input: {args.input}")
        print(f"  Output: {args.output or 'default'}")
        print("\nUse --write to execute.")
        return 0
    
    # Execute recipe
    print(f"Running recipe: {args.name}")
    print(f"Input: {args.input}")
    
    # TODO: Implement actual recipe execution via praisonaiagents
    # For now, show what would be executed
    print("\nRecipe execution would involve:")
    for tool in recipe.get("requires", {}).get("tools", []):
        print(f"  - Using {tool}")
    
    print("\nRecipe execution completed (placeholder).")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    """Explain recipe execution plan."""
    recipe = get_recipe(args.name)
    
    if not recipe:
        print(f"Recipe not found: {args.name}")
        return 1
    
    print(f"Execution Plan for: {args.name}")
    print("=" * 50)
    
    print("\n1. Dependency Check:")
    for tool in recipe.get("requires", {}).get("tools", []):
        print(f"   - Load {tool}")
    
    print("\n2. Input Processing:")
    inputs = recipe.get("inputs", {})
    for name, spec in inputs.items():
        print(f"   - {name}: {spec.get('type', 'unknown')}")
    
    print("\n3. Execution:")
    print(f"   - Run recipe workflow")
    
    print("\n4. Output:")
    outputs = recipe.get("outputs", {})
    for name, spec in outputs.items():
        print(f"   - {name}: {spec.get('type', 'unknown')}")
    
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize recipe in current directory."""
    recipe = get_recipe(args.name)
    
    if not recipe:
        print(f"Recipe not found: {args.name}")
        return 1
    
    target_dir = Path(args.output) if args.output else Path.cwd() / args.name
    
    if target_dir.exists() and not args.force:
        print(f"Directory already exists: {target_dir}")
        print("Use --force to overwrite.")
        return 1
    
    import shutil
    source_dir = Path(recipe["path"])
    
    if args.dry_run:
        print(f"DRY RUN: Would copy {source_dir} to {target_dir}")
        return 0
    
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy recipe files
    for item in source_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, target_dir / item.name)
    
    print(f"Initialized recipe '{args.name}' in {target_dir}")
    return 0


def setup_parser(subparsers: argparse._SubParsersAction) -> None:
    """Setup recipes subcommand parser."""
    recipes_parser = subparsers.add_parser(
        "recipes",
        help="Manage and run Agent-Recipes",
        description="Commands for managing and running Agent-Recipes templates.",
    )
    
    recipes_subparsers = recipes_parser.add_subparsers(dest="recipes_command")
    
    # List command
    list_parser = recipes_subparsers.add_parser("list", help="List available recipes")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.add_argument("--group", action="store_true", help="Group by category")
    list_parser.set_defaults(func=cmd_list)
    
    # Info command
    info_parser = recipes_subparsers.add_parser("info", help="Show recipe details")
    info_parser.add_argument("name", help="Recipe name")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")
    info_parser.set_defaults(func=cmd_info)
    
    # Doctor command
    doctor_parser = recipes_subparsers.add_parser("doctor", help="Check recipe dependencies")
    doctor_parser.add_argument("name", help="Recipe name")
    doctor_parser.set_defaults(func=cmd_doctor)
    
    # Run command
    run_parser = recipes_subparsers.add_parser("run", help="Run a recipe")
    run_parser.add_argument("name", help="Recipe name")
    run_parser.add_argument("input", nargs="?", help="Input file or value")
    run_parser.add_argument("--output", "-o", help="Output directory")
    run_parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    run_parser.add_argument("--write", action="store_true", help="Actually execute (for dry-run-default recipes)")
    run_parser.add_argument("--force", action="store_true", help="Force execution despite missing deps")
    run_parser.add_argument("--consent", action="store_true", help="Acknowledge consent requirements")
    run_parser.add_argument("--skip-checks", action="store_true", help="Skip dependency checks")
    run_parser.add_argument("--json", action="store_true", help="Output as JSON")
    run_parser.set_defaults(func=cmd_run)
    
    # Explain command
    explain_parser = recipes_subparsers.add_parser("explain", help="Explain recipe execution plan")
    explain_parser.add_argument("name", help="Recipe name")
    explain_parser.set_defaults(func=cmd_explain)
    
    # Init command
    init_parser = recipes_subparsers.add_parser("init", help="Initialize recipe in directory")
    init_parser.add_argument("name", help="Recipe name")
    init_parser.add_argument("--output", "-o", help="Target directory")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing")
    init_parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    init_parser.set_defaults(func=cmd_init)


def handle_recipes_command(args: argparse.Namespace) -> int:
    """Handle recipes subcommand."""
    if not hasattr(args, "func"):
        # No subcommand specified, show help
        print("Usage: praison recipes <command> [options]")
        print("\nCommands:")
        print("  list     List available recipes")
        print("  info     Show recipe details")
        print("  doctor   Check recipe dependencies")
        print("  run      Run a recipe")
        print("  explain  Explain recipe execution plan")
        print("  init     Initialize recipe in directory")
        return 0
    
    return args.func(args)
