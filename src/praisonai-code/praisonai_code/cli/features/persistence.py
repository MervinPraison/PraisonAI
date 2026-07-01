"""
Persistence CLI feature for PraisonAI.

Provides commands for database persistence configuration and management:
- praisonai persistence doctor  - Validate DB connectivity
- praisonai persistence run     - Run agent with persistence
- praisonai persistence resume  - Resume a session
"""

import os
import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def handle_persistence_command(args: list) -> bool:
    """
    Handle persistence subcommands.
    
    Args:
        args: Command line arguments after 'persistence'
    
    Returns:
        True if command was handled, False otherwise
    """
    if not args:
        print_persistence_help()
        return True
    
    subcommand = args[0].lower()
    sub_args = args[1:]
    
    if subcommand == "doctor":
        return handle_doctor(sub_args)
    elif subcommand == "run":
        return handle_run(sub_args)
    elif subcommand == "resume":
        return handle_resume(sub_args)
    elif subcommand == "export":
        return handle_export(sub_args)
    elif subcommand == "import":
        return handle_import(sub_args)
    elif subcommand == "migrate":
        return handle_migrate(sub_args)
    elif subcommand == "status":
        return handle_status(sub_args)
    elif subcommand in ("--help", "-h", "help"):
        print_persistence_help()
        return True
    else:
        print(f"Unknown persistence subcommand: {subcommand}")
        print_persistence_help()
        return True


def print_persistence_help():
    """Print persistence command help."""
    help_text = """
PraisonAI Persistence Commands
==============================

Usage: praisonai persistence <command> [options]

Commands:
  doctor    Validate database connectivity and configuration
  run       Run an agent with persistence enabled
  resume    Resume an existing session

Doctor Command:
  praisonai persistence doctor [options]
  
  Options:
    --conversation-url URL    Conversation store URL (postgres/mysql/sqlite)
    --knowledge-url URL       Knowledge store URL (qdrant/chroma/pinecone)
    --state-url URL           State store URL (redis/memory)
    --all                     Test all configured stores
  
  Environment Variables:
    PRAISON_CONVERSATION_URL  Default conversation store URL
    PRAISON_KNOWLEDGE_URL     Default knowledge store URL
    PRAISON_STATE_URL         Default state store URL

Run Command:
  praisonai persistence run [options] "prompt"
  
  Options:
    --session-id ID           Session identifier (auto-generated if not provided)
    --user-id ID              User identifier (default: "default")
    --conversation-url URL    Conversation store URL
    --knowledge-url URL       Knowledge store URL
    --state-url URL           State store URL
    --agent-name NAME         Agent name (default: "Assistant")
    --agent-instructions TEXT Agent instructions
    --dry-run                 Show configuration without running

Resume Command:
  praisonai persistence resume --session-id ID [options]
  
  Options:
    --session-id ID           Session to resume (required)
    --conversation-url URL    Conversation store URL
    --show-history            Display conversation history
    --continue "prompt"       Continue with a new prompt

Export/Import Commands:
  praisonai persistence export --session-id ID [options]
  praisonai persistence import --file FILE [options]
  
  Options:
    --session-id ID           Session to export (required for export)
    --conversation-url URL    Conversation store URL
    --file FILE               File path for export/import (JSONL format)
    --output FILE             Output file path (default: session-{id}.jsonl)

Examples:
  # Check PostgreSQL connectivity
  praisonai persistence doctor --conversation-url "postgresql://localhost/mydb"
  
  # Run agent with persistence
  praisonai persistence run --session-id "my-session" "Hello, remember my name is Alice"
  
  # Resume a session
  praisonai persistence resume --session-id "my-session" --show-history
  
  # Continue a session
  praisonai persistence resume --session-id "my-session" --continue "What's my name?"
  
  # Export a session
  praisonai persistence export --session-id "my-session" --output session.jsonl
  
  # Import a session
  praisonai persistence import --file session.jsonl
"""
    print(help_text)


def parse_persistence_args(args: list) -> dict:
    """Parse persistence command arguments."""
    config = {
        "session_id": None,
        "user_id": "default",
        "conversation_url": os.getenv("PRAISON_CONVERSATION_URL"),
        "knowledge_url": os.getenv("PRAISON_KNOWLEDGE_URL"),
        "state_url": os.getenv("PRAISON_STATE_URL"),
        "agent_name": "Assistant",
        "agent_instructions": "You are a helpful assistant.",
        "dry_run": False,
        "show_history": False,
        "all_stores": False,
        "prompt": None,
        "continue_prompt": None,
        "output_file": None,
        "input_file": None,
    }
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg == "--session-id" and i + 1 < len(args):
            config["session_id"] = args[i + 1]
            i += 2
        elif arg == "--user-id" and i + 1 < len(args):
            config["user_id"] = args[i + 1]
            i += 2
        elif arg == "--conversation-url" and i + 1 < len(args):
            config["conversation_url"] = args[i + 1]
            i += 2
        elif arg == "--knowledge-url" and i + 1 < len(args):
            config["knowledge_url"] = args[i + 1]
            i += 2
        elif arg == "--state-url" and i + 1 < len(args):
            config["state_url"] = args[i + 1]
            i += 2
        elif arg == "--agent-name" and i + 1 < len(args):
            config["agent_name"] = args[i + 1]
            i += 2
        elif arg == "--agent-instructions" and i + 1 < len(args):
            config["agent_instructions"] = args[i + 1]
            i += 2
        elif arg == "--dry-run":
            config["dry_run"] = True
            i += 1
        elif arg == "--show-history":
            config["show_history"] = True
            i += 1
        elif arg == "--all":
            config["all_stores"] = True
            i += 1
        elif arg == "--continue" and i + 1 < len(args):
            config["continue_prompt"] = args[i + 1]
            i += 2
        elif arg == "--output" and i + 1 < len(args):
            config["output_file"] = args[i + 1]
            i += 2
        elif arg == "--file" and i + 1 < len(args):
            config["input_file"] = args[i + 1]
            i += 2
        elif not arg.startswith("-"):
            config["prompt"] = arg
            i += 1
        else:
            i += 1
    
    return config


def handle_doctor(args: list) -> bool:
    """Handle persistence doctor command."""
    config = parse_persistence_args(args)
    
    print("=" * 50)
    print("PraisonAI Persistence Doctor")
    print("=" * 50)
    
    results = []
    
    # Test conversation store
    if config["conversation_url"] or config["all_stores"]:
        url = config["conversation_url"]
        if url:
            print(f"\n[Conversation Store] Testing: {_mask_url(url)}")
            success, msg = _test_conversation_store(url)
            results.append(("Conversation", success, msg))
            print(f"  {'✅' if success else '❌'} {msg}")
        else:
            print("\n[Conversation Store] Not configured (set --conversation-url or PRAISON_CONVERSATION_URL)")
    
    # Test knowledge store
    if config["knowledge_url"] or config["all_stores"]:
        url = config["knowledge_url"]
        if url:
            print(f"\n[Knowledge Store] Testing: {_mask_url(url)}")
            success, msg = _test_knowledge_store(url)
            results.append(("Knowledge", success, msg))
            print(f"  {'✅' if success else '❌'} {msg}")
        else:
            print("\n[Knowledge Store] Not configured (set --knowledge-url or PRAISON_KNOWLEDGE_URL)")
    
    # Test state store
    if config["state_url"] or config["all_stores"]:
        url = config["state_url"]
        if url:
            print(f"\n[State Store] Testing: {_mask_url(url)}")
            success, msg = _test_state_store(url)
            results.append(("State", success, msg))
            print(f"  {'✅' if success else '❌'} {msg}")
        else:
            print("\n[State Store] Not configured (set --state-url or PRAISON_STATE_URL)")
    
    # Summary
    print("\n" + "=" * 50)
    if results:
        passed = sum(1 for _, s, _ in results if s)
        total = len(results)
        print(f"Results: {passed}/{total} stores connected successfully")
    else:
        print("No stores configured. Use --conversation-url, --knowledge-url, or --state-url")
    print("=" * 50)
    
    return True


def handle_run(args: list) -> bool:
    """Handle persistence run command."""
    config = parse_persistence_args(args)
    
    if not config["prompt"]:
        print("Error: No prompt provided")
        print("Usage: praisonai persistence run [options] \"your prompt\"")
        return True
    
    if not config["conversation_url"]:
        print("Error: No conversation URL configured")
        print("Set --conversation-url or PRAISON_CONVERSATION_URL")
        return True
    
    if config["dry_run"]:
        print("=" * 50)
        print("Dry Run - Configuration")
        print("=" * 50)
        print(f"Session ID: {config['session_id'] or '(auto-generated)'}")
        print(f"User ID: {config['user_id']}")
        print(f"Conversation URL: {_mask_url(config['conversation_url'])}")
        print(f"Agent Name: {config['agent_name']}")
        print(f"Prompt: {config['prompt'][:50]}...")
        return True
    
    # Run agent with persistence
    try:
        from praisonaiagents import Agent, db
        
        db_instance = db(
            database_url=config["conversation_url"],
            state_url=config["state_url"],
            knowledge_url=config["knowledge_url"],
        )
        
        agent = Agent(
            name=config["agent_name"],
            instructions=config["agent_instructions"],
            db=db_instance,
            session_id=config["session_id"],
            verbose=True
        )
        
        print(f"\n[Session: {agent.session_id}]")
        response = agent.chat(config["prompt"])
        print(f"\nAgent: {response}")
        
        db_instance.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return True
    
    return True


def handle_resume(args: list) -> bool:
    """Handle persistence resume command."""
    config = parse_persistence_args(args)
    
    if not config["session_id"]:
        print("Error: --session-id is required for resume")
        return True
    
    if not config["conversation_url"]:
        print("Error: No conversation URL configured")
        print("Set --conversation-url or PRAISON_CONVERSATION_URL")
        return True
    
    try:
        from praisonaiagents import db
        
        db_instance = db(database_url=config["conversation_url"])
        
        # Get session history
        history = db_instance.on_agent_start(
            agent_name="Resume",
            session_id=config["session_id"],
            user_id=config["user_id"]
        )
        
        print(f"\n[Session: {config['session_id']}]")
        print(f"Messages in history: {len(history)}")
        
        if config["show_history"]:
            print("\n--- Conversation History ---")
            for msg in history:
                role = msg.role.upper()
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                print(f"[{role}] {content}")
            print("--- End History ---\n")
        
        if config["continue_prompt"]:
            from praisonaiagents import Agent
            
            agent = Agent(
                name=config["agent_name"],
                instructions=config["agent_instructions"],
                db=db_instance,
                session_id=config["session_id"],
                verbose=True
            )
            
            response = agent.chat(config["continue_prompt"])
            print(f"\nAgent: {response}")
        
        db_instance.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return True
    
    return True


def handle_export(args: list) -> bool:
    """Handle persistence export command."""
    config = parse_persistence_args(args)
    
    if not config["session_id"]:
        print("Error: --session-id is required for export")
        return True
    
    if not config["conversation_url"]:
        print("Error: No conversation URL configured")
        return True
    
    try:
        from praisonaiagents import db
        import json
        
        db_instance = db(database_url=config["conversation_url"])
        
        # Export session
        data = db_instance.export_session(config["session_id"])
        
        if not data:
            print(f"Error: Session {config['session_id']} not found")
            db_instance.close()
            return True
        
        # Determine output file
        output_file = config.get("output_file") or f"session-{config['session_id']}.jsonl"
        
        with open(output_file, 'w') as f:
            f.write(json.dumps(data, default=str) + '\n')
        
        print(f"Exported session to: {output_file}")
        print(f"Messages: {len(data.get('messages', []))}")
        
        db_instance.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return True
    
    return True


def handle_import(args: list) -> bool:
    """Handle persistence import command."""
    config = parse_persistence_args(args)
    
    input_file = config.get("input_file")
    if not input_file:
        print("Error: --file is required for import")
        return True
    
    if not config["conversation_url"]:
        print("Error: No conversation URL configured")
        return True
    
    try:
        from praisonaiagents import db
        import json
        
        db_instance = db(database_url=config["conversation_url"])
        
        with open(input_file, 'r') as f:
            data = json.loads(f.readline())
        
        session_id = db_instance.import_session(data)
        
        print(f"Imported session: {session_id}")
        print(f"Messages: {len(data.get('messages', []))}")
        
        db_instance.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return True
    
    return True


def handle_migrate(args: list) -> bool:
    """Handle persistence migrate command."""
    config = parse_persistence_args(args)
    
    if not config["conversation_url"] and not config["state_url"]:
        print("Error: No database URL configured")
        print("Set --conversation-url or --state-url")
        return True
    
    try:
        from praisonaiagents import db
        from praisonai.persistence.migrations import MigrationManager
        
        db_instance = db(
            database_url=config["conversation_url"],
            state_url=config["state_url"]
        )
        
        manager = MigrationManager(db_instance)
        
        # Check for --up or --down flags
        direction = "up"
        target = None
        for i, arg in enumerate(args):
            if arg == "--down":
                direction = "down"
            elif arg == "--target" and i + 1 < len(args):
                target = args[i + 1]
        
        if direction == "up":
            print("Applying pending migrations...")
            applied = manager.migrate_up(target)
            if applied:
                print(f"Applied migrations: {', '.join(applied)}")
            else:
                print("No pending migrations")
        else:
            if not target:
                print("Error: --target required for --down migration")
                return True
            print(f"Rolling back to version {target}...")
            rolled_back = manager.migrate_down(target)
            if rolled_back:
                print(f"Rolled back: {', '.join(rolled_back)}")
            else:
                print("No migrations to rollback")
        
        db_instance.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return True
    
    return True


def handle_status(args: list) -> bool:
    """Handle persistence status command."""
    config = parse_persistence_args(args)
    
    if not config["conversation_url"] and not config["state_url"]:
        print("Error: No database URL configured")
        return True
    
    try:
        from praisonaiagents import db
        from praisonai.persistence.migrations import MigrationManager
        
        db_instance = db(
            database_url=config["conversation_url"],
            state_url=config["state_url"]
        )
        
        manager = MigrationManager(db_instance)
        status = manager.get_migration_status()
        
        print("\n=== Schema Status ===")
        print(f"Current version: {status['current_version'] or '(not set)'}")
        print(f"Latest version:  {status['latest_version']}")
        print(f"Pending:         {status['pending_count']} migration(s)")
        
        if status['pending_versions']:
            print(f"Pending versions: {', '.join(status['pending_versions'])}")
        
        db_instance.close()
        
    except Exception as e:
        print(f"Error: {e}")
        return True
    
    return True


def _mask_url(url: str) -> str:
    """Mask sensitive parts of URL."""
    if not url:
        return "(not set)"
    
    # Mask password in URLs
    import re
    masked = re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', url)
    return masked


def _test_conversation_store(url: str) -> tuple:
    """Test conversation store connectivity."""
    try:
        from praisonai.persistence.factory import create_conversation_store
        
        # Detect backend
        if "postgresql" in url or "postgres" in url:
            backend = "postgres"
        elif "mysql" in url:
            backend = "mysql"
        elif url.endswith(".db") or "sqlite" in url:
            backend = "sqlite"
        else:
            backend = "sqlite"
        
        store = create_conversation_store(backend, url=url)
        
        # Try a simple operation
        sessions = store.list_sessions(limit=1)
        store.close()
        
        return True, f"Connected ({backend})"
    except Exception as e:
        return False, str(e)


def _test_knowledge_store(url: str) -> tuple:
    """Test knowledge store connectivity."""
    try:
        from praisonai.persistence.factory import create_knowledge_store
        
        # Detect backend
        if "qdrant" in url or ":6333" in url:
            backend = "qdrant"
        elif "chroma" in url:
            backend = "chroma"
        else:
            backend = "qdrant"
        
        store = create_knowledge_store(backend, url=url)
        
        # Try a simple operation
        exists = store.collection_exists("test_doctor")
        store.close()
        
        return True, f"Connected ({backend})"
    except Exception as e:
        return False, str(e)


def _test_state_store(url: str) -> tuple:
    """Test state store connectivity."""
    try:
        from praisonai.persistence.factory import create_state_store
        
        # Detect backend
        if "redis" in url:
            backend = "redis"
        else:
            backend = "memory"
        
        store = create_state_store(backend, url=url)
        
        # Try a simple operation
        store.set("_doctor_test", "ok", ttl=5)
        value = store.get("_doctor_test")
        store.delete("_doctor_test")
        store.close()
        
        return True, f"Connected ({backend})"
    except Exception as e:
        return False, str(e)
