"""CLI subcommand handlers (C8.4)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import yaml
from dotenv import load_dotenv
from rich import print

def handle_memory_command(self, action: str, action_args: list, user_id: str = None):
    """
    Handle memory subcommand actions.
    
    Args:
        action: The memory action (show, add, search, clear, save, resume, etc.)
        action_args: Additional arguments for the action
        user_id: User ID for memory isolation
    """
    try:
        from praisonaiagents.memory import FileMemory
        from rich import print
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        memory = FileMemory(user_id=user_id or "default")
        
        if action == 'show':
            stats = memory.get_stats()
            table = Table(title="Memory Statistics")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            for key, value in stats.items():
                table.add_row(str(key), str(value))
            
            console.print(table)
            
            # Show recent short-term memories
            print("\n[bold]Recent Short-term Memories:[/bold]")
            short_term = memory.get_short_term(limit=5)
            if short_term:
                for i, item in enumerate(short_term, 1):
                    content = item.get('content', str(item))[:100]
                    print(f"  {i}. {content}")
            else:
                print("  [dim]No short-term memories[/dim]")
            
            # Show long-term memories
            print("\n[bold]Long-term Memories:[/bold]")
            long_term = memory.get_long_term(limit=10)
            if long_term:
                for i, item in enumerate(long_term, 1):
                    # Handle both dict and MemoryItem objects
                    if hasattr(item, 'content'):
                        content = str(item.content)[:100]
                        importance = getattr(item, 'importance', 0)
                    else:
                        content = item.get('content', str(item))[:100]
                        importance = item.get('importance', 0)
                    print(f"  {i}. [{importance:.1f}] {content}")
            else:
                print("  [dim]No long-term memories[/dim]")
            
            # Show entities
            print("\n[bold]Entities:[/bold]")
            entities = memory.get_all_entities()
            if entities:
                for entity in entities[:10]:
                    # Handle both dict and Entity objects
                    if hasattr(entity, 'name'):
                        name = entity.name
                        entity_type = getattr(entity, 'entity_type', 'unknown')
                    else:
                        name = entity.get('name', 'Unknown')
                        entity_type = entity.get('entity_type', 'unknown')
                    print(f"  • {name} ({entity_type})")
            else:
                print("  [dim]No entities[/dim]")
            
        elif action == 'add':
            if not action_args:
                print("[red]ERROR: Content required. Usage: praisonai memory add \"Your memory content\"[/red]")
                return
            content = ' '.join(action_args)
            memory.add_long_term(content, importance=0.8)
            print(f"[green]✅ Added to long-term memory: {content[:50]}...[/green]")
            
        elif action == 'search':
            if not action_args:
                print("[red]ERROR: Query required. Usage: praisonai memory search \"query\"[/red]")
                return
            query = ' '.join(action_args)
            results = memory.search(query, limit=10)
            print(f"[bold]Search results for '{query}':[/bold]")
            for i, result in enumerate(results, 1):
                content = result.get('content', str(result))[:100]
                print(f"  {i}. {content}")
                
        elif action == 'clear':
            target = action_args[0] if action_args else 'short'
            if target == 'all':
                memory.clear_all()
                print("[green]✅ All memory cleared[/green]")
            else:
                memory.clear_short_term()
                print("[green]✅ Short-term memory cleared[/green]")
                
        elif action == 'save':
            if not action_args:
                print("[red]ERROR: Session name required. Usage: praisonai memory save <session_name>[/red]")
                return
            session_name = action_args[0]
            memory.save_session(session_name)
            print(f"[green]✅ Session saved: {session_name}[/green]")
            
        elif action == 'resume':
            if not action_args:
                print("[red]ERROR: Session name required. Usage: praisonai memory resume <session_name>[/red]")
                return
            session_name = action_args[0]
            memory.resume_session(session_name)
            print(f"[green]✅ Session resumed: {session_name}[/green]")
            
        elif action == 'sessions':
            sessions = memory.list_sessions()
            if sessions:
                print("[bold]Saved Sessions:[/bold]")
                for s in sessions:
                    print(f"  - {s.get('name', 'Unknown')} (saved: {s.get('saved_at', 'Unknown')})")
            else:
                print("[yellow]No saved sessions found[/yellow]")
                
        elif action == 'compress':
            print("[cyan]Compressing short-term memory...[/cyan]")
            # Note: compress requires an LLM function, so we'll just show stats
            stats = memory.get_stats()
            print(f"[green]Short-term items: {stats.get('short_term_count', 0)}[/green]")
            print("[yellow]Note: Full compression requires an LLM. Use programmatically with memory.compress(llm_func=...)[/yellow]")
            
        elif action == 'checkpoint':
            name = action_args[0] if action_args else None
            checkpoint_id = memory.create_checkpoint(name)
            print(f"[green]✅ Checkpoint created: {checkpoint_id}[/green]")
            
        elif action == 'restore':
            if not action_args:
                print("[red]ERROR: Checkpoint ID required. Usage: praisonai memory restore <checkpoint_id>[/red]")
                return
            checkpoint_id = action_args[0]
            memory.restore_checkpoint(checkpoint_id)
            print(f"[green]✅ Checkpoint restored: {checkpoint_id}[/green]")
            
        elif action == 'checkpoints':
            checkpoints = memory.list_checkpoints()
            if checkpoints:
                print("[bold]Checkpoints:[/bold]")
                for cp in checkpoints:
                    print(f"  - {cp.get('id', 'Unknown')} ({cp.get('name', 'Unnamed')})")
            else:
                print("[yellow]No checkpoints found[/yellow]")
                
        elif action == 'help' or action == '--help':
            print("[bold]Memory Commands:[/bold]")
            print("  praisonai memory show                    - Show memory statistics")
            print("  praisonai memory add <content>           - Add to long-term memory")
            print("  praisonai memory search <query>          - Search memories")
            print("  praisonai memory clear [short|all]       - Clear memory")
            print("  praisonai memory save <session_name>     - Save session")
            print("  praisonai memory resume <session_name>   - Resume session")
            print("  praisonai memory sessions                - List saved sessions")
            print("  praisonai memory compress                - Compress short-term memory")
            print("  praisonai memory checkpoint [name]       - Create checkpoint")
            print("  praisonai memory restore <checkpoint_id> - Restore checkpoint")
            print("  praisonai memory checkpoints             - List checkpoints")
            print("\n[bold]Options:[/bold]")
            print("  --user-id <id>                           - User ID for memory isolation")
        else:
            print(f"[red]Unknown memory action: {action}[/red]")
            print("Use 'praisonai memory help' for available commands")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import memory module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: Memory command failed: {e}[/red]")

def handle_rules_command(self, action: str, action_args: list):
    """
    Handle rules subcommand actions.
    
    Args:
        action: The rules action (list, show, create, delete, stats)
        action_args: Additional arguments for the action
    """
    try:
        from praisonaiagents.memory import RulesManager
        from rich import print
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        rules = RulesManager(workspace_path=os.getcwd())
        
        if action == 'list':
            all_rules = rules.get_all_rules()
            if all_rules:
                table = Table(title="Loaded Rules")
                table.add_column("Name", style="cyan")
                table.add_column("Description", style="white")
                table.add_column("Activation", style="green")
                table.add_column("Priority", style="yellow")
                
                for rule in all_rules:
                    table.add_row(
                        rule.name,
                        rule.description[:50] + "..." if len(rule.description) > 50 else rule.description,
                        rule.activation,
                        str(rule.priority)
                    )
                
                console.print(table)
            else:
                print("[yellow]No rules found. Create PRAISON.md, CLAUDE.md, or files in .praison/rules/[/yellow]")
                
        elif action == 'show':
            if not action_args:
                print("[red]ERROR: Rule name required. Usage: praisonai rules show <name>[/red]")
                return
            rule_name = action_args[0]
            rule = rules.get_rule_by_name(rule_name)
            if rule:
                print(f"[bold cyan]Rule: {rule.name}[/bold cyan]")
                print(f"[bold]Description:[/bold] {rule.description}")
                print(f"[bold]Activation:[/bold] {rule.activation}")
                print(f"[bold]Priority:[/bold] {rule.priority}")
                if rule.globs:
                    print(f"[bold]Globs:[/bold] {', '.join(rule.globs)}")
                print(f"\n[bold]Content:[/bold]\n{rule.content}")
            else:
                print(f"[red]Rule not found: {rule_name}[/red]")
                
        elif action == 'create':
            if len(action_args) < 2:
                print("[red]ERROR: Name and content required. Usage: praisonai rules create <name> <content>[/red]")
                return
            rule_name = action_args[0]
            content = ' '.join(action_args[1:])
            rules.create_rule(
                name=rule_name,
                content=content,
                description=f"Rule created via CLI: {rule_name}",
                activation="always",
                scope="workspace"
            )
            print(f"[green]✅ Rule created: {rule_name}[/green]")
            
        elif action == 'delete':
            if not action_args:
                print("[red]ERROR: Rule name required. Usage: praisonai rules delete <name>[/red]")
                return
            rule_name = action_args[0]
            rules.delete_rule(rule_name)
            print(f"[green]✅ Rule deleted: {rule_name}[/green]")
            
        elif action == 'stats':
            stats = rules.get_stats()
            table = Table(title="Rules Statistics")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            for key, value in stats.items():
                if isinstance(value, dict):
                    table.add_row(str(key), str(value))
                else:
                    table.add_row(str(key), str(value))
            
            console.print(table)
            
        elif action == 'help' or action == '--help':
            print("[bold]Rules Commands:[/bold]")
            print("  praisonai rules list                     - List all loaded rules")
            print("  praisonai rules show <name>              - Show specific rule details")
            print("  praisonai rules create <name> <content>  - Create a new rule")
            print("  praisonai rules delete <name>            - Delete a rule")
            print("  praisonai rules stats                    - Show rules statistics")
            print("\n[bold]Supported Rule Files:[/bold]")
            print("  PRAISON.md, CLAUDE.md, AGENTS.md, GEMINI.md")
            print("  .cursorrules, .windsurfrules")
            print("  .praison/rules/*.md, ~/.praison/rules/*.md")
        else:
            print(f"[red]Unknown rules action: {action}[/red]")
            print("Use 'praisonai rules help' for available commands")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import rules module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: Rules command failed: {e}[/red]")

def handle_hooks_command(self, action: str):
    """
    Handle hooks subcommand actions.
    
    Args:
        action: The hooks action (list, stats, init)
    """
    try:
        from praisonaiagents.memory import HooksManager
        from rich import print
        from rich.table import Table
        from rich.console import Console
        import json
        
        console = Console()
        hooks = HooksManager(workspace_path=os.getcwd())
        
        if action == 'list':
            stats = hooks.get_stats()
            if stats.get('total_hooks', 0) > 0:
                print("[bold]Configured Hooks:[/bold]")
                for event in stats.get('events', []):
                    print(f"  - {event}")
            else:
                print("[yellow]No hooks configured. Create .praison/hooks.json[/yellow]")
                
        elif action == 'stats':
            stats = hooks.get_stats()
            table = Table(title="Hooks Statistics")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="green")
            
            for key, value in stats.items():
                table.add_row(str(key), str(value))
            
            console.print(table)
            
        elif action == 'init':
            hooks_dir = os.path.join(os.getcwd(), ".praison")
            os.makedirs(hooks_dir, exist_ok=True)
            hooks_file = os.path.join(hooks_dir, "hooks.json")
            
            if os.path.exists(hooks_file):
                print(f"[yellow]hooks.json already exists at {hooks_file}[/yellow]")
            else:
                template = {
                    "enabled": True,
                    "timeout": 30,
                    "hooks": {
                        "pre_write_code": "./scripts/lint.sh",
                        "post_write_code": "./scripts/format.sh",
                        "pre_run_command": {
                            "command": "./scripts/validate.sh",
                            "timeout": 60,
                            "block_on_failure": True
                        }
                    }
                }
                with open(hooks_file, 'w') as f:
                    json.dump(template, f, indent=2)
                print(f"[green]✅ Created hooks.json at {hooks_file}[/green]")
                print("[cyan]Edit the file to configure your hooks[/cyan]")
                
        elif action == 'help' or action == '--help':
            print("[bold]Hooks Commands:[/bold]")
            print("  praisonai hooks list                     - List configured hooks")
            print("  praisonai hooks stats                    - Show hooks statistics")
            print("  praisonai hooks init                     - Create hooks.json template")
            print("\n[bold]Hook Events:[/bold]")
            print("  pre_read_code, post_read_code")
            print("  pre_write_code, post_write_code")
            print("  pre_run_command, post_run_command")
            print("  pre_user_prompt, post_user_prompt")
            print("  pre_mcp_tool_use, post_mcp_tool_use")
        else:
            print(f"[red]Unknown hooks action: {action}[/red]")
            print("Use 'praisonai hooks help' for available commands")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import hooks module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: Hooks command failed: {e}[/red]")

def handle_knowledge_command(self, action: str, action_args: list):
    """
    Handle knowledge subcommand actions.
    
    Args:
        action: The knowledge action (add, query, list, clear, stats, help)
        action_args: Additional arguments for the action (may include flags)
    """
    try:
        from ..features.knowledge import KnowledgeHandler
        
        # Parse flags from action_args
        vector_store = "chroma"
        retrieval_strategy = "basic"
        reranker = None
        index_type = "vector"
        query_mode = "default"
        session_id = None
        db = None
        workspace = os.getcwd()
        
        # Filter out flags and extract values
        filtered_args = []
        i = 0
        while i < len(action_args):
            arg = action_args[i]
            if arg in ("--vector-store", "--store"):
                if i + 1 < len(action_args):
                    vector_store = action_args[i + 1]
                    i += 2
                    continue
            elif arg in ("--retrieval-strategy", "--retrieval", "--strategy"):
                if i + 1 < len(action_args):
                    retrieval_strategy = action_args[i + 1]
                    i += 2
                    continue
            elif arg == "--reranker":
                if i + 1 < len(action_args):
                    reranker = action_args[i + 1]
                    i += 2
                    continue
            elif arg in ("--index-type", "--index"):
                if i + 1 < len(action_args):
                    index_type = action_args[i + 1]
                    i += 2
                    continue
            elif arg in ("--query-mode", "--mode"):
                if i + 1 < len(action_args):
                    query_mode = action_args[i + 1]
                    i += 2
                    continue
            elif arg == "--session":
                if i + 1 < len(action_args):
                    session_id = action_args[i + 1]
                    i += 2
                    continue
            elif arg == "--db":
                if i + 1 < len(action_args):
                    db = action_args[i + 1]
                    i += 2
                    continue
            elif arg == "--workspace":
                if i + 1 < len(action_args):
                    workspace = action_args[i + 1]
                    i += 2
                    continue
            filtered_args.append(arg)
            i += 1
        
        handler = KnowledgeHandler(
            verbose=True,
            workspace=workspace,
            vector_store=vector_store,
            retrieval_strategy=retrieval_strategy,
            reranker=reranker,
            index_type=index_type,
            query_mode=query_mode,
            session_id=session_id,
            db=db
        )
        handler.execute(action, filtered_args)
    except ImportError as e:
        print(f"[red]ERROR: Failed to import knowledge module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: Knowledge command failed: {e}[/red]")

def handle_docs_command(self, action: str, action_args: list):
    """
    Handle docs subcommand actions.
    
    Args:
        action: The docs action (list, show, create, delete, run, run-all, stats, etc.)
        action_args: Additional arguments for the action
    """
    # Code validation commands - delegate to typer app
    # Also handle 'cli' subcommand group for CLI validation
    code_validation_actions = {'run', 'run-all', 'stats', 'report', 'generate', 'serve', 'cli'}
    if action in code_validation_actions:
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module('praisonai.cli.commands.docs')
        docs_app = getattr(_mod, 'app')
        import typer
        # Build args list for typer
        typer_args = [action] + action_args
        try:
            typer.main.get_command(docs_app)(typer_args)
        except SystemExit as e:
            sys.exit(e.code if e.code is not None else 0)
        return
    
    try:
        from praisonaiagents.memory import DocsManager
        from rich import print
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        docs = DocsManager(workspace_path=os.getcwd())
        
        if action == 'list':
            all_docs = docs.list_docs()
            if all_docs:
                table = Table(title="Project Documentation")
                table.add_column("Name", style="cyan")
                table.add_column("Description", style="white")
                table.add_column("Priority", style="yellow")
                table.add_column("Tags", style="green")
                table.add_column("Scope", style="magenta")
                
                for doc in all_docs:
                    table.add_row(
                        doc["name"],
                        doc["description"][:40] + "..." if len(doc["description"]) > 40 else doc["description"],
                        str(doc["priority"]),
                        ", ".join(doc["tags"][:3]) if doc["tags"] else "",
                        doc["scope"]
                    )
                
                console.print(table)
            else:
                print("[yellow]No docs found. Create files in .praison/docs/[/yellow]")
                
        elif action == 'show':
            if not action_args:
                print("[red]ERROR: Doc name required. Usage: praisonai docs show <name>[/red]")
                return
            doc_name = action_args[0]
            doc = docs.get_doc(doc_name)
            if doc:
                print(f"[bold cyan]Doc: {doc.name}[/bold cyan]")
                print(f"[bold]Description:[/bold] {doc.description}")
                print(f"[bold]Priority:[/bold] {doc.priority}")
                if doc.tags:
                    print(f"[bold]Tags:[/bold] {', '.join(doc.tags)}")
                print(f"\n[bold]Content:[/bold]\n{doc.content}")
            else:
                print(f"[red]Doc not found: {doc_name}[/red]")
                
        elif action == 'create':
            if len(action_args) < 2:
                print("[red]ERROR: Name and content required. Usage: praisonai docs create <name> <content>[/red]")
                return
            doc_name = action_args[0]
            content = ' '.join(action_args[1:])
            docs.create_doc(
                name=doc_name,
                content=content,
                description=f"Doc created via CLI: {doc_name}",
                scope="workspace"
            )
            print(f"[green]✅ Doc created: {doc_name}[/green]")
            
        elif action == 'delete':
            if not action_args:
                print("[red]ERROR: Doc name required. Usage: praisonai docs delete <name>[/red]")
                return
            doc_name = action_args[0]
            if docs.delete_doc(doc_name):
                print(f"[green]✅ Doc deleted: {doc_name}[/green]")
            else:
                print(f"[red]Doc not found: {doc_name}[/red]")
            
        elif action == 'help' or action == '--help':
            print("[bold]Docs Commands:[/bold]")
            print("  praisonai docs list                     - List all docs")
            print("  praisonai docs show <name>              - Show specific doc")
            print("  praisonai docs create <name> <content>  - Create a new doc")
            print("  praisonai docs delete <name>            - Delete a doc")
            print("\n[bold]Doc Location:[/bold]")
            print("  .praison/docs/*.md, ~/.praison/docs/*.md")
        else:
            print(f"[red]Unknown docs action: {action}[/red]")
            print("Use 'praisonai docs help' for available commands")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import docs module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: Docs command failed: {e}[/red]")

def handle_mcp_command(self, action: str, action_args: list):
    """
    Handle mcp subcommand actions.
    
    Args:
        action: The mcp action (list, show, create, delete, enable, disable)
        action_args: Additional arguments for the action
    """
    try:
        from praisonaiagents.memory import MCPConfigManager
        from rich import print
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        mcp = MCPConfigManager(workspace_path=os.getcwd())
        
        if action == 'list':
            all_configs = mcp.list_configs()
            if all_configs:
                table = Table(title="MCP Server Configurations")
                table.add_column("Name", style="cyan")
                table.add_column("Command", style="white")
                table.add_column("Enabled", style="green")
                table.add_column("Scope", style="magenta")
                table.add_column("Description", style="yellow")
                
                for config in all_configs:
                    table.add_row(
                        config["name"],
                        config["command"],
                        "✅" if config["enabled"] else "❌",
                        config["scope"],
                        config["description"][:30] + "..." if len(config["description"]) > 30 else config["description"]
                    )
                
                console.print(table)
            else:
                print("[yellow]No MCP configs found. Create files in .praison/mcp/[/yellow]")
                
        elif action == 'show':
            if not action_args:
                print("[red]ERROR: Config name required. Usage: praisonai mcp show <name>[/red]")
                return
            config_name = action_args[0]
            config = mcp.get_config(config_name)
            if config:
                print(f"[bold cyan]MCP Config: {config.name}[/bold cyan]")
                print(f"[bold]Command:[/bold] {config.command}")
                print(f"[bold]Args:[/bold] {' '.join(config.args)}")
                print(f"[bold]Enabled:[/bold] {'Yes' if config.enabled else 'No'}")
                print(f"[bold]Description:[/bold] {config.description}")
                if config.env:
                    print("[bold]Environment:[/bold]")
                    for key, value in config.env.items():
                        # Mask sensitive values
                        masked = value[:4] + "..." if len(value) > 8 else "***"
                        print(f"  {key}: {masked}")
            else:
                print(f"[red]MCP config not found: {config_name}[/red]")
                
        elif action == 'create':
            if len(action_args) < 2:
                print("[red]ERROR: Name and command required. Usage: praisonai mcp create <name> <command> [args...][/red]")
                return
            config_name = action_args[0]
            command = action_args[1]
            args = action_args[2:] if len(action_args) > 2 else []
            mcp.create_config(
                name=config_name,
                command=command,
                args=args,
                description="MCP server created via CLI",
                scope="workspace"
            )
            print(f"[green]✅ MCP config created: {config_name}[/green]")
            
        elif action == 'delete':
            if not action_args:
                print("[red]ERROR: Config name required. Usage: praisonai mcp delete <name>[/red]")
                return
            config_name = action_args[0]
            if mcp.delete_config(config_name):
                print(f"[green]✅ MCP config deleted: {config_name}[/green]")
            else:
                print(f"[red]MCP config not found: {config_name}[/red]")
                
        elif action == 'enable':
            if not action_args:
                print("[red]ERROR: Config name required. Usage: praisonai mcp enable <name>[/red]")
                return
            config_name = action_args[0]
            if mcp.enable_config(config_name):
                print(f"[green]✅ MCP config enabled: {config_name}[/green]")
            else:
                print(f"[red]MCP config not found: {config_name}[/red]")
                
        elif action == 'disable':
            if not action_args:
                print("[red]ERROR: Config name required. Usage: praisonai mcp disable <name>[/red]")
                return
            config_name = action_args[0]
            if mcp.disable_config(config_name):
                print(f"[green]✅ MCP config disabled: {config_name}[/green]")
            else:
                print(f"[red]MCP config not found: {config_name}[/red]")
            
        elif action == 'serve':
            # Start MCP server
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module('praisonai.mcp_server.cli')
            mcp_serve_handler = getattr(_mod, 'handle_mcp_command')
            exit_code = mcp_serve_handler(['serve'] + action_args)
            sys.exit(exit_code)
        
        elif action == 'list-tools':
            # List MCP tools
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module('praisonai.mcp_server.cli')
            mcp_serve_handler = getattr(_mod, 'handle_mcp_command')
            exit_code = mcp_serve_handler(['list-tools'] + action_args)
            sys.exit(exit_code)
        
        elif action == 'config-generate':
            # Generate client config
            from praisonai_code._wrapper_bridge import import_wrapper_module
            _mod = import_wrapper_module('praisonai.mcp_server.cli')
            mcp_serve_handler = getattr(_mod, 'handle_mcp_command')
            exit_code = mcp_serve_handler(['config-generate'] + action_args)
            sys.exit(exit_code)
        
        elif action == 'help' or action == '--help':
            print("[bold]MCP Commands:[/bold]")
            print("\n[bold cyan]Server Commands:[/bold cyan]")
            print("  praisonai mcp serve                             - Start MCP server (STDIO)")
            print("  praisonai mcp serve --transport http-stream     - Start HTTP Stream server")
            print("  praisonai mcp list-tools                        - List available MCP tools")
            print("  praisonai mcp config-generate --client claude-desktop  - Generate client config")
            print("\n[bold cyan]Config Management:[/bold cyan]")
            print("  praisonai mcp list                              - List all MCP configs")
            print("  praisonai mcp show <name>                       - Show specific config")
            print("  praisonai mcp create <name> <cmd> [args...]     - Create a new config")
            print("  praisonai mcp delete <name>                     - Delete a config")
            print("  praisonai mcp enable <name>                     - Enable a config")
            print("  praisonai mcp disable <name>                    - Disable a config")
            print("\n[bold]Config Location:[/bold]")
            print("  .praison/mcp/*.json, ~/.praison/mcp/*.json")
            print("\n[bold]Examples:[/bold]")
            print("  praisonai mcp serve --transport stdio")
            print("  praisonai mcp serve --transport http-stream --port 8080")
            print("  praisonai mcp create filesystem npx -y @modelcontextprotocol/server-filesystem .")
        else:
            print(f"[red]Unknown mcp action: {action}[/red]")
            print("Use 'praisonai mcp help' for available commands")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import mcp module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except Exception as e:
        print(f"[red]ERROR: MCP command failed: {e}[/red]")

# Compiled regex patterns for sensitive data detection (compiled once, zero runtime cost)
_SENSITIVE_PATTERNS = None

def _get_sensitive_patterns():
    """Lazy-load and compile sensitive patterns only when needed."""
    global _SENSITIVE_PATTERNS
    if _SENSITIVE_PATTERNS is None:
        import re
        _SENSITIVE_PATTERNS = [
            # API Keys and Tokens
            (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "API Key"),
            (re.compile(r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Secret Key"),
            (re.compile(r'(?i)(access[_-]?token|accesstoken)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Access Token"),
            (re.compile(r'(?i)(auth[_-]?token|authtoken)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Auth Token"),
            # AWS
            (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key ID"),
            (re.compile(r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']?[a-zA-Z0-9/+=]{40}'), "AWS Secret Key"),
            # Passwords
            (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}'), "Password"),
            (re.compile(r'(?i)db[_-]?password\s*[=:]\s*["\']?[^\s"\']+'), "Database Password"),
            # Private Keys
            (re.compile(r'-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----'), "Private Key"),
            (re.compile(r'-----BEGIN PGP PRIVATE KEY BLOCK-----'), "PGP Private Key"),
            # GitHub/GitLab tokens
            (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub Personal Access Token"),
            (re.compile(r'gho_[a-zA-Z0-9]{36}'), "GitHub OAuth Token"),
            (re.compile(r'glpat-[a-zA-Z0-9\-]{20,}'), "GitLab Personal Access Token"),
            # Slack
            (re.compile(r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}'), "Slack Token"),
            # Generic secrets
            (re.compile(r'(?i)(client[_-]?secret)\s*[=:]\s*["\']?[a-zA-Z0-9_\-]{20,}'), "Client Secret"),
            (re.compile(r'(?i)(private[_-]?key)\s*[=:]\s*["\']?[a-zA-Z0-9_\-/+=]{20,}'), "Private Key Value"),
        ]
    return _SENSITIVE_PATTERNS

# Sensitive file patterns (simple string matching - very fast)
_SENSITIVE_FILES = {'.env', '.env.local', '.env.production', '.env.development',
                    'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
                    '.pem', '.key', '.p12', '.pfx', 'credentials', 'secrets.json',
                    'secrets.yaml', 'secrets.yml', '.htpasswd', '.netrc'}
_SENSITIVE_EXTENSIONS = {'.pem', '.key', '.p12', '.pfx', '.jks', '.keystore'}

def _check_sensitive_content(self, diff_content: str, staged_files: list) -> list:
    """
    Check for sensitive content in staged changes.
    
    Args:
        diff_content: The git diff content
        staged_files: List of staged file names
        
    Returns:
        List of (file, issue_type, match) tuples for detected issues
    """
    issues = []
    
    # Quick check for sensitive files by name/extension
    for file_path in staged_files:
        file_name = file_path.split('/')[-1].lower()
        # Check exact file names
        if file_name in _SENSITIVE_FILES:
            issues.append((file_path, "Sensitive File", file_name))
            continue
        # Check extensions
        for ext in _SENSITIVE_EXTENSIONS:
            if file_name.endswith(ext):
                issues.append((file_path, "Sensitive Extension", ext))
                break
    
    # Only scan diff content if it's not too large (performance guard)
    if len(diff_content) < 50000:
        patterns = _get_sensitive_patterns()
        # Scan only added lines (lines starting with +)
        for line in diff_content.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                for pattern, issue_type in patterns:
                    match = pattern.search(line)
                    if match:
                        # Truncate match for display
                        matched_text = match.group(0)[:50] + '...' if len(match.group(0)) > 50 else match.group(0)
                        issues.append(("diff", issue_type, matched_text))
                        break  # One issue per line is enough
    
    return issues

def _clean_commit_message(raw: str) -> str:
    """Strip markdown code fences and excess whitespace from LLM-generated commit messages."""
    msg = raw.strip()
    # Remove wrapping ```...``` (with optional language tag like ```text)
    if msg.startswith("```"):
        lines = msg.split("\n")
        # Remove first line (```<lang?>) and last line (```) if present
        if len(lines) >= 2 and lines[-1].strip() == "```":
            lines = lines[1:-1]
        elif lines[0].strip().startswith("```"):
            lines = lines[1:]
        msg = "\n".join(lines).strip()
    return msg

def handle_commit_command(self, args: list):
    """
    Handle AI commit message generation.
    
    Generates a commit message based on staged changes using AI.
    
    Args:
        args: Additional arguments:
            --push: Auto-push after commit
            -a, --auto: Full auto mode (stage, commit, push) - aborts on security issues
            --no-verify: Skip sensitive content check
    """
    try:
        import subprocess
        import os
        from rich import print
        from praisonaiagents import Agent
        
        # Get custom git author from environment variables
        git_user_name = os.getenv("PRAISONAI_GIT_USER_NAME")
        git_user_email = os.getenv("PRAISONAI_GIT_USER_EMAIL")
        git_author = None
        if git_user_name and git_user_email:
            git_author = f"{git_user_name} <{git_user_email}>"
        
        # Check if we're in a git repository
        try:
            subprocess.run(["git", "rev-parse", "--git-dir"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("[red]ERROR: Not in a git repository[/red]")
            return
        
        # Handle auto mode
        auto_mode = '-a' in args or '--auto' in args or '--all' in args
        if auto_mode:
            print("[cyan]Auto-staging all changes...[/cyan]")
            subprocess.run(["git", "add", "-A"], capture_output=True)
        
        # Get staged diff
        result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True,
            text=True
        )
        
        if not result.stdout.strip():
            print("[yellow]No staged changes. Use 'git add' to stage files first, or use -a/--auto.[/yellow]")
            return
        
        # Get detailed diff for context
        diff_result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True
        )
        
        # Limit diff size for context
        diff_content = diff_result.stdout[:8000] if len(diff_result.stdout) > 8000 else diff_result.stdout
        
        # Security check for sensitive content (unless --no-verify)
        if '--no-verify' not in args:
            # Extract staged file names from stat output
            staged_files = [line.split('|')[0].strip() for line in result.stdout.strip().split('\n') if '|' in line]
            issues = self._check_sensitive_content(diff_result.stdout, staged_files)
            
            if issues:
                print("\n[bold red]⚠️  SECURITY WARNING: Sensitive content detected![/bold red]")
                for file_path, issue_type, match in issues:
                    print(f"  [red]• {issue_type}[/red] in [yellow]{file_path}[/yellow]: {match}")
                print("\n[yellow]Options:[/yellow]")
                print("  [c] Continue anyway (not recommended)")
                print("  [a] Abort commit")
                print("  [i] Ignore and add to .gitignore")
                
                # In auto mode, abort on security issues
                if auto_mode:
                    print("[red]Auto mode aborted due to security concerns. Use --no-verify to skip.[/red]")
                    return
                
                sec_choice = input("\nYour choice [c/a/i]: ").strip().lower()
                if sec_choice == 'a':
                    print("[yellow]Commit aborted due to security concerns.[/yellow]")
                    return
                elif sec_choice == 'i':
                    # Add sensitive files to .gitignore
                    sensitive_file_paths = [f for f, t, _ in issues if t in ("Sensitive File", "Sensitive Extension")]
                    if sensitive_file_paths:
                        with open('.gitignore', 'a') as gi:
                            gi.write('\n# Auto-added by praisonai commit\n')
                            for fp in sensitive_file_paths:
                                gi.write(f'{fp}\n')
                        print(f"[green]Added {len(sensitive_file_paths)} file(s) to .gitignore[/green]")
                        # Unstage the sensitive files
                        subprocess.run(["git", "reset", "HEAD", "--"] + sensitive_file_paths, capture_output=True)
                        print("[cyan]Unstaged sensitive files. Please re-run commit.[/cyan]")
                        return
                # else continue
                print("[yellow]Proceeding despite security warnings...[/yellow]")
        
        print("[bold]Staged changes:[/bold]")
        print(result.stdout)
        print("\n[bold]Generating commit message...[/bold]")
        
        # Create agent for commit message generation
        agent = Agent(
            name="CommitMessageGenerator",
            role="Git Commit Message Writer",
            goal="Generate clear, concise, and conventional commit messages",
            instructions="""You are an expert at writing git commit messages.
            
Follow the Conventional Commits specification:
- feat: A new feature
- fix: A bug fix
- docs: Documentation changes
- style: Code style changes (formatting, etc.)
- refactor: Code refactoring
- test: Adding or updating tests
- chore: Maintenance tasks

Format:
<type>(<scope>): <short description>

<optional body with more details>

Keep the first line under 72 characters.
Be specific about what changed and why.""",
            llm=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        )
        
        prompt = f"""Generate a commit message for these changes:

{result.stdout}

Detailed diff:
{diff_content}

Provide ONLY the raw commit message text.
Do NOT wrap it in markdown code fences or backticks.
Do NOT add any explanations or formatting."""

        response = agent.chat(prompt)
        commit_message = _clean_commit_message(response)
        
        print("\n[bold green]Suggested commit message:[/bold green]")
        print(f"[cyan]{commit_message}[/cyan]")
        
        # In auto mode, skip confirmation and commit + push
        if auto_mode:
            commit_cmd = ["git", "commit", "-m", commit_message]
            if git_author:
                commit_cmd.extend(["--author", git_author])
            subprocess.run(commit_cmd, check=True)
            print("[green]✅ Committed successfully![/green]")
            subprocess.run(["git", "push"], check=True)
            print("[green]✅ Pushed to remote![/green]")
            return
        
        # Ask for confirmation
        print("\n[bold]Options:[/bold]")
        print("  [y] Use this message and commit")
        print("  [e] Edit the message")
        print("  [n] Cancel")
        
        choice = input("\nYour choice [y/e/n]: ").strip().lower()
        
        if choice == 'y':
            # Commit with the generated message
            commit_cmd = ["git", "commit", "-m", commit_message]
            if git_author:
                commit_cmd.extend(["--author", git_author])
            subprocess.run(commit_cmd, check=True)
            print("[green]✅ Committed successfully![/green]")
            
            # Check if --push was passed
            if '--push' in args:
                subprocess.run(["git", "push"], check=True)
                print("[green]✅ Pushed to remote![/green]")
                
        elif choice == 'e':
            # Open editor with the message
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(commit_message)
                temp_path = f.name
            
            editor = os.environ.get('EDITOR', 'nano')
            subprocess.run([editor, temp_path])
            
            with open(temp_path, 'r') as f:
                edited_message = f.read().strip()
            
            os.unlink(temp_path)
            
            if edited_message:
                commit_cmd = ["git", "commit", "-m", edited_message]
                if git_author:
                    commit_cmd.extend(["--author", git_author])
                subprocess.run(commit_cmd, check=True)
                print("[green]✅ Committed successfully![/green]")
            else:
                print("[yellow]Empty message, commit cancelled.[/yellow]")
        else:
            print("[yellow]Commit cancelled.[/yellow]")
            
    except ImportError as e:
        print(f"[red]ERROR: Failed to import required module: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
    except subprocess.CalledProcessError as e:
        print(f"[red]ERROR: Git command failed: {e}[/red]")
    except Exception as e:
        print(f"[red]ERROR: Commit command failed: {e}[/red]")

def handle_context_command(self, url: str, goal: str, auto_analyze: bool = False) -> str:
    """
    Handle the context command by creating a ContextAgent and running it.
    
    Args:
        url: Repository URL for context analysis
        goal: Goal for context engineering
        auto_analyze: Enable automatic analysis (default: False)
        
    Returns:
        str: Result from context engineering
    """
    try:
        from praisonaiagents import ContextAgent
        print("[bold green]Starting Context Engineering...[/bold green]")
        print(f"URL: {url}")
        print(f"Goal: {goal}")
        print(f"Auto-analyze: {auto_analyze}")
        
        # Use the same model configuration pattern as other CLI commands
        # Priority order: MODEL_NAME > OPENAI_MODEL_NAME for model selection
        model_name = os.environ.get("MODEL_NAME") or os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        
        # Create ContextAgent with user's LLM configuration
        agent = ContextAgent(llm=model_name, auto_analyze=auto_analyze)
        
        # Format input as expected by the start method: "url goal"
        input_text = f"{url} {goal}"
        
        # Execute the context engineering
        result = agent.start(input_text)
        
        print("\n[bold green]Context Engineering Complete![/bold green]")
        print(result)
        return result
        
    except ImportError as e:
        print(f"[red]ERROR: Failed to import ContextAgent: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        sys.exit(1)
    except Exception as e:
        print(f"[red]ERROR: Context engineering failed: {e}[/red]")
        sys.exit(1)

def handle_research_command(self, query: str, model: str = None, verbose: bool = False, save: bool = False, query_rewrite: bool = False, tools_path: str = None, rewrite_tools: str = None) -> str:
    """
    Handle the research command by creating a DeepResearchAgent and running it.
    
    Args:
        query: Research query/topic
        model: Model for deep research (optional, defaults to o4-mini-deep-research)
        verbose: Enable verbose output (default: False)
        save: Save output to file (default: False)
        query_rewrite: Rewrite query before research (default: False)
        tools_path: Path to tools.py file with custom tools (default: None)
        rewrite_tools: Tools for query rewriter (tool names or file path)
        
    Returns:
        str: Research report
    """
    try:
        from praisonaiagents import DeepResearchAgent
        
        # Suppress logging unless verbose
        if not verbose:
            logging.getLogger('google').setLevel(logging.WARNING)
            logging.getLogger('google.genai').setLevel(logging.WARNING)
            logging.getLogger('httpx').setLevel(logging.WARNING)
            logging.getLogger('httpcore').setLevel(logging.WARNING)
        
        # Rewrite query if requested
        if query_rewrite:
            query = self._rewrite_query(query, rewrite_tools, verbose)
        
        print("[bold green]Starting Deep Research...[/bold green]")
        print(f"Query: {query}")
        
        # Default model if not specified
        if not model:
            model = "o4-mini-deep-research"
        
        print(f"Model: {model}")
        
        # Load tools if specified
        tools_list = []
        if tools_path:
            # Check if it's a file path or comma-separated tool names
            if os.path.isfile(tools_path):
                # Load from file
                try:
                    import inspect
                    from praisonai_code._safe_loader import load_user_module
                    module = load_user_module(tools_path, name="tools_module", allow_outside_cwd=True)
                    if module is not None:
                        # Get all callable functions from the module
                        for name, obj in inspect.getmembers(module):
                            if inspect.isfunction(obj) and not name.startswith('_'):
                                tools_list.append(obj)
                        if tools_list:
                            print(f"[cyan]Loaded {len(tools_list)} tools from {tools_path}[/cyan]")
                    else:
                        print(f"[yellow]Warning: Tools loading disabled. Set PRAISONAI_ALLOW_LOCAL_TOOLS=true to enable.[/yellow]")
                except Exception as e:
                    print(f"[yellow]Warning: Failed to load tools from {tools_path}: {e}[/yellow]")
            else:
                # Treat as comma-separated tool names (e.g., "internet_search,wiki_search")
                try:
                    import inspect
                    from praisonai_code.tool_resolver import resolve_tool

                    tool_names = [t.strip() for t in tools_path.split(',') if t.strip()]
                    for tool_name in tool_names:
                        tool = resolve_tool(tool_name)
                        if tool is not None:
                            tools_list.append(tool() if inspect.isclass(tool) else tool)
                        else:
                            print(f"[yellow]Warning: Unknown tool '{tool_name}'[/yellow]")
                    if tools_list:
                        print(f"[cyan]Loaded {len(tools_list)} built-in tools: {', '.join(tool_names)}[/cyan]")
                except ImportError:
                    print("[yellow]Warning: Could not import tools module[/yellow]")
        
        # If tools are provided, use Agent with tools first, then DeepResearchAgent
        if tools_list:
            from praisonaiagents import Agent, Task, AgentTeam
            
            # Create a research assistant agent with tools
            research_assistant = Agent(
                name="Research Assistant",
                role="Information Gatherer",
                goal="Gather relevant information using available tools",
                backstory="You are an expert at using tools to gather information for research.",
                tools=tools_list,
                llm="gpt-4o-mini", output="minimal"
            )
            
            # Create task to gather initial information
            gather_task = Task(
                description=f"Use your tools to gather relevant information about: {query}",
                expected_output="A summary of information gathered from the tools",
                agent=research_assistant
            )
            
            print("[cyan]Gathering information with tools...[/cyan]")
            agents = AgentTeam(agents=[research_assistant], tasks=[gather_task], verbose=0)
            tool_results = agents.start()
            
            # Enhance query with tool results
            enhanced_query = f"{query}\n\nAdditional context from tools:\n{tool_results}"
            print("[cyan]Tools context gathered, starting deep research...[/cyan]")
            
            # Create DeepResearchAgent
            agent = DeepResearchAgent(model=model)
            result = agent.research(enhanced_query)
        else:
            # Create DeepResearchAgent (verbose=True is default for streaming output)
            agent = DeepResearchAgent(model=model)
            
            # Execute the research
            result = agent.research(query)
        
        print("\n[bold green]Research Complete![/bold green]")
        print("\n" + "="*60)
        print(result.report)
        print("="*60)
        
        # Show citations if available
        if result.citations:
            print(f"\n[bold]Citations ({len(result.citations)}):[/bold]")
            for i, citation in enumerate(result.citations, 1):
                title = getattr(citation, 'title', 'Untitled')
                url = getattr(citation, 'url', '')
                print(f"  {i}. {title}")
                if url:
                    print(f"     {url}")
        
        # Save output to file if --save flag is set
        if save:
            import re
            # Get first 10 words from query for filename
            words = query.split()[:10]
            filename_base = ' '.join(words)
            # Sanitize filename: remove invalid characters
            filename_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', filename_base)
            filename_base = filename_base.strip()[:100]  # Limit length
            if not filename_base:
                filename_base = "research_output"
            
            # Create output directory
            output_dir = os.path.join(os.getcwd(), "output", "research")
            os.makedirs(output_dir, exist_ok=True)
            
            # Build markdown content
            md_content = f"# {query}\n\n"
            md_content += result.report
            if result.citations:
                md_content += "\n\n## Citations\n\n"
                for i, citation in enumerate(result.citations, 1):
                    title = getattr(citation, 'title', 'Untitled')
                    url = getattr(citation, 'url', '')
                    if url:
                        md_content += f"{i}. [{title}]({url})\n"
                    else:
                        md_content += f"{i}. {title}\n"
            
            # Save to file
            output_path = os.path.join(output_dir, f"{filename_base}.md")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_content)
            
            print(f"\n[bold green]Saved to:[/bold green] {output_path}")
        
        return result.report
        
    except ImportError as e:
        print(f"[red]ERROR: Failed to import DeepResearchAgent: {e}[/red]")
        print("Make sure praisonaiagents is installed: pip install praisonaiagents")
        sys.exit(1)
    except Exception as e:
        print(f"[red]ERROR: Research failed: {e}[/red]")
        sys.exit(1)

def _load_cli_project_context(self, budget: int = 8000) -> str:
    """Auto-discover AGENTS.md/CLAUDE.md project context for the system prompt.

    Walks up from the current working directory to the project root,
    bounded by ``budget`` characters and cached for the process. Returns
    an empty string when the optional helper is unavailable or no context
    files are found.
    """
    cached = getattr(self, "_cli_project_context", None)
    if cached is not None:
        return cached

    context = ""
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module
        _mod = import_wrapper_module('praisonai.integration.context_files')
        load_context_files = getattr(_mod, 'load_context_files')
        context = load_context_files(walk_up=True) or ""
    except ImportError:
        context = ""  # Context files helper is optional
    except Exception:
        context = ""

    if budget and len(context) > budget:
        context = context[:budget] + "\n... [project context truncated]"

    self._cli_project_context = context
    return context
