"""
Config Migration CLI for PraisonAI.

Provides migration tools for converting configurations between formats.
"""

from __future__ import annotations

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ConfigMigrator:
    """Configuration migrator for PraisonAI."""
    
    def migrate(
        self,
        source: str,
        target: Optional[str] = None,
        source_format: Optional[str] = None,
        target_format: str = "praisonai",
    ) -> Dict[str, Any]:
        """Migrate configuration from one format to another.
        
        Args:
            source: Source configuration file path
            target: Target file path (optional)
            source_format: Source format (auto-detected if not provided)
            target_format: Target format (default: praisonai)
            
        Returns:
            Migration result
        """
        if not os.path.exists(source):
            return {"success": False, "error": f"Source file not found: {source}"}
        
        if not source_format:
            source_format = self._detect_format(source)
        
        try:
            config = self._load_config(source, source_format)
        except Exception as e:
            return {"success": False, "error": f"Failed to load source: {e}"}
        
        try:
            converted = self._convert_config(config, source_format, target_format)
        except Exception as e:
            return {"success": False, "error": f"Failed to convert: {e}"}
        
        if target:
            try:
                self._save_config(converted, target, target_format)
            except Exception as e:
                return {"success": False, "error": f"Failed to save: {e}"}
        
        return {
            "success": True,
            "source_format": source_format,
            "target_format": target_format,
            "config": converted,
            "target_file": target,
        }
    
    def _detect_format(self, path: str) -> str:
        """Detect configuration format from file."""
        import yaml
        
        with open(path, "r") as f:
            content = f.read()
        
        try:
            config = yaml.safe_load(content)
        except Exception:
            return "unknown"
        
        if not isinstance(config, dict):
            return "unknown"
        
        if "framework" in config and config.get("framework") == "praisonai":
            return "praisonai"
        if "agents" in config and "tasks" in config:
            return "crewai"
        if "config_list" in config or "llm_config" in config:
            return "autogen"
        if "agents" in config:
            return "praisonai"
        
        return "unknown"
    
    def _load_config(self, path: str, format: str) -> Dict[str, Any]:
        """Load configuration from file."""
        import yaml
        
        with open(path, "r") as f:
            return yaml.safe_load(f)
    
    def _convert_config(
        self,
        config: Dict[str, Any],
        source_format: str,
        target_format: str,
    ) -> Dict[str, Any]:
        """Convert configuration between formats."""
        if source_format == target_format:
            return config
        
        if source_format == "crewai" and target_format == "praisonai":
            return self._convert_crewai_to_praisonai(config)
        if source_format == "autogen" and target_format == "praisonai":
            return self._convert_autogen_to_praisonai(config)
        if source_format == "praisonai" and target_format == "crewai":
            return self._convert_praisonai_to_crewai(config)
        
        return config
    
    def _convert_crewai_to_praisonai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert CrewAI config to PraisonAI format."""
        result = {
            "framework": "praisonai",
            "topic": config.get("topic", "Converted from CrewAI"),
            "agents": [],
            "steps": [],
        }
        
        for agent in config.get("agents", []):
            result["agents"].append({
                "name": agent.get("role", "agent").lower().replace(" ", "_"),
                "role": agent.get("role", "Agent"),
                "goal": agent.get("goal", ""),
                "backstory": agent.get("backstory", ""),
                "tools": agent.get("tools", []),
            })
        
        for i, task in enumerate(config.get("tasks", [])):
            agent_name = task.get("agent", "")
            if isinstance(agent_name, dict):
                agent_name = agent_name.get("role", "agent").lower().replace(" ", "_")
            
            result["steps"].append({
                "name": f"step_{i+1}",
                "agent": agent_name,
                "action": task.get("description", ""),
                "expected_output": task.get("expected_output", ""),
            })
        
        return result
    
    def _convert_autogen_to_praisonai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert AutoGen config to PraisonAI format."""
        result = {
            "framework": "praisonai",
            "topic": "Converted from AutoGen",
            "agents": [],
            "steps": [],
        }
        
        llm_config = config.get("llm_config", {})
        model = "gpt-4o-mini"
        if "config_list" in llm_config:
            config_list = llm_config["config_list"]
            if config_list:
                model = config_list[0].get("model", model)
        
        for agent in config.get("agents", []):
            result["agents"].append({
                "name": agent.get("name", "agent"),
                "role": agent.get("name", "Agent"),
                "goal": agent.get("system_message", ""),
                "backstory": "",
                "llm": model,
            })
        
        return result
    
    def _convert_praisonai_to_crewai(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert PraisonAI config to CrewAI format."""
        result = {
            "agents": [],
            "tasks": [],
        }
        
        for agent in config.get("agents", []):
            result["agents"].append({
                "role": agent.get("role", agent.get("name", "Agent")),
                "goal": agent.get("goal", ""),
                "backstory": agent.get("backstory", ""),
                "tools": agent.get("tools", []),
            })
        
        for step in config.get("steps", []):
            result["tasks"].append({
                "description": step.get("action", ""),
                "expected_output": step.get("expected_output", ""),
                "agent": step.get("agent", ""),
            })
        
        return result
    
    def _save_config(self, config: Dict[str, Any], path: str, format: str) -> None:
        """Save configuration to file."""
        import yaml
        
        with open(path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def handle_migrate_command(args) -> None:
    """Handle migrate CLI command."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax
    except ImportError:
        print("Error: Rich library required")
        return
    
    console = Console()
    migrator = ConfigMigrator()
    
    source = getattr(args, "source", None)
    target = getattr(args, "target", None)
    source_format = getattr(args, "from_format", None)
    target_format = getattr(args, "to_format", "praisonai")
    
    if not source:
        console.print("[red]Error: Source file required[/red]")
        return
    
    result = migrator.migrate(
        source=source,
        target=target,
        source_format=source_format,
        target_format=target_format,
    )
    
    if not result["success"]:
        console.print(f"[red]Migration failed: {result['error']}[/red]")
        return
    
    console.print(Panel.fit(
        f"[green]Migration successful![/green]\n\n"
        f"Source format: {result['source_format']}\n"
        f"Target format: {result['target_format']}",
        title="Config Migration",
    ))
    
    if target:
        console.print(f"\nSaved to: {target}")
    else:
        import yaml
        yaml_str = yaml.dump(result["config"], default_flow_style=False, sort_keys=False)
        console.print("\nConverted configuration:")
        console.print(Syntax(yaml_str, "yaml"))


def add_migrate_parser(subparsers) -> None:
    """Add migrate subparser to CLI."""
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Migrate configuration between formats",
    )
    migrate_parser.add_argument(
        "source",
        help="Source configuration file",
    )
    migrate_parser.add_argument(
        "--target", "-o",
        help="Target output file",
    )
    migrate_parser.add_argument(
        "--from", dest="from_format",
        choices=["praisonai", "crewai", "autogen"],
        help="Source format (auto-detected if not provided)",
    )
    migrate_parser.add_argument(
        "--to", dest="to_format",
        choices=["praisonai", "crewai"],
        default="praisonai",
        help="Target format (default: praisonai)",
    )
    migrate_parser.set_defaults(func=handle_migrate_command)
