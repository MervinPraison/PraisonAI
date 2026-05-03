"""
CLI Tools Adapter

Maps PraisonAI CLI features to MCP tools:
- Workflow management
- Rules management
- Hooks management
- Session management
- Todo management
- Docs management
- Schedule management
- Profile management
- Deploy management
"""

import logging
from typing import Optional

from ..registry import register_tool

logger = logging.getLogger(__name__)


def register_cli_tools() -> None:
    """Register CLI-based MCP tools."""
    
    # Workflow tools
    @register_tool("praisonai.workflow.list")
    def workflow_list() -> str:
        """List available workflows."""
        try:
            import glob
            workflows = []
            for pattern in ["*.yaml", "*.yml", "agents*.yaml", "workflow*.yaml"]:
                workflows.extend(glob.glob(pattern))
            if not workflows:
                return "No workflows found in current directory"
            return f"Available workflows: {workflows}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.workflow.validate")
    def workflow_validate(file_path: str) -> str:
        """Validate a workflow YAML file."""
        try:
            import yaml
            with open(file_path, 'r') as f:
                config = yaml.safe_load(f)
            
            required = ["framework", "topic"]
            missing = [k for k in required if k not in config]
            if missing:
                return f"Invalid workflow: missing {missing}"
            
            return f"Workflow valid: {file_path}"
        except yaml.YAMLError as e:
            return f"YAML error: {e}"
        except FileNotFoundError:
            return f"File not found: {file_path}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.workflow.show")
    def workflow_show(file_path: str) -> str:
        """Show workflow configuration."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            return f"File not found: {file_path}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.workflow.auto")
    def workflow_auto(topic: str, pattern: str = "sequential") -> str:
        """Auto-generate a workflow for a topic."""
        try:
            from praisonai.auto import AutoGenerator
            generator = AutoGenerator(topic=topic)
            result = generator.generate(pattern=pattern)
            return str(result)
        except ImportError:
            return "Error: AutoGenerator not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Rules tools
    def _resolve_rule_path(rule_name: str):
        """Resolve a rule_name to a path strictly inside ``~/.praison/rules``.

        ``rule_name`` is treated as a single filename (no separators, no
        traversal, no leading dot). The fully-resolved path must remain
        within the rules directory; otherwise the input is rejected. This
        prevents arbitrary file write/read/delete (e.g. dropping a
        ``.pth`` file in user site-packages) when an untrusted MCP caller
        invokes ``praisonai.rules.*``.
        """
        import os
        from pathlib import Path
        if not isinstance(rule_name, str) or not rule_name:
            raise ValueError("rule_name must be a non-empty string")
        # Reject any directory separator, traversal token, NUL byte, or
        # leading dot (which would target hidden files / parent dirs).
        if (
            "/" in rule_name
            or "\\" in rule_name
            or "\x00" in rule_name
            or rule_name.startswith(".")
            or rule_name in ("..", ".")
            or os.path.sep in rule_name
            or (os.path.altsep and os.path.altsep in rule_name)
        ):
            raise ValueError(f"invalid rule_name: {rule_name!r}")
        rules_dir = Path(os.path.expanduser("~/.praison/rules")).resolve()
        candidate = (rules_dir / rule_name).resolve()
        # Ensure no symlink-or-traversal escape from rules_dir.
        try:
            candidate.relative_to(rules_dir)
        except ValueError as exc:
            raise ValueError(f"invalid rule_name: {rule_name!r}") from exc
        return rules_dir, candidate

    @register_tool("praisonai.rules.list")
    def rules_list() -> str:
        """List active rules."""
        try:
            import os
            rules_dir = os.path.expanduser("~/.praison/rules")
            if not os.path.exists(rules_dir):
                return "No rules directory found"
            rules = os.listdir(rules_dir)
            return f"Active rules: {rules}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.rules.show")
    def rules_show(rule_name: str) -> str:
        """Show a specific rule."""
        try:
            _, rule_path = _resolve_rule_path(rule_name)
            if not rule_path.exists():
                return f"Rule not found: {rule_name}"
            return rule_path.read_text()
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.rules.create")
    def rules_create(rule_name: str, content: str) -> str:
        """Create a new rule."""
        try:
            rules_dir, rule_path = _resolve_rule_path(rule_name)
            rules_dir.mkdir(parents=True, exist_ok=True)
            rule_path.write_text(content)
            return f"Rule created: {rule_name}"
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.rules.delete")
    def rules_delete(rule_name: str) -> str:
        """Delete a rule."""
        try:
            _, rule_path = _resolve_rule_path(rule_name)
            if not rule_path.exists():
                return f"Rule not found: {rule_name}"
            rule_path.unlink()
            return f"Rule deleted: {rule_name}"
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
    
    # Hooks tools
    @register_tool("praisonai.hooks.list")
    def hooks_list() -> str:
        """List registered hooks."""
        try:
            from praisonaiagents.hooks import get_hook_manager
            manager = get_hook_manager()
            hooks = manager.list_hooks()
            return str(hooks)
        except ImportError:
            return "Error: Hooks not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.hooks.stats")
    def hooks_stats() -> str:
        """Get hook execution statistics."""
        try:
            from praisonaiagents.hooks import get_hook_manager
            manager = get_hook_manager()
            stats = manager.get_stats()
            return str(stats)
        except ImportError:
            return "Error: Hooks not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Session tools
    @register_tool("praisonai.session.list")
    def session_list() -> str:
        """List active sessions."""
        try:
            from praisonaiagents.session import SessionManager
            manager = SessionManager()
            sessions = manager.list_sessions()
            return str(sessions)
        except ImportError:
            return "Error: Session management not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.session.info")
    def session_info(session_id: str) -> str:
        """Get session information."""
        try:
            from praisonaiagents.session import SessionManager
            manager = SessionManager()
            info = manager.get_session(session_id)
            return str(info)
        except ImportError:
            return "Error: Session management not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.session.delete")
    def session_delete(session_id: str) -> str:
        """Delete a session."""
        try:
            from praisonaiagents.session import SessionManager
            manager = SessionManager()
            manager.delete_session(session_id)
            return f"Session deleted: {session_id}"
        except ImportError:
            return "Error: Session management not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Todo tools
    @register_tool("praisonai.todo.list")
    def todo_list() -> str:
        """List todo items."""
        try:
            import os
            import json
            todo_path = os.path.expanduser("~/.praison/todo.json")
            if not os.path.exists(todo_path):
                return "No todos found"
            with open(todo_path, 'r') as f:
                todos = json.load(f)
            return str(todos)
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.todo.add")
    def todo_add(content: str, priority: str = "medium") -> str:
        """Add a todo item."""
        try:
            import os
            import json
            import uuid
            todo_path = os.path.expanduser("~/.praison/todo.json")
            os.makedirs(os.path.dirname(todo_path), exist_ok=True)
            
            todos = []
            if os.path.exists(todo_path):
                with open(todo_path, 'r') as f:
                    todos = json.load(f)
            
            todo = {
                "id": str(uuid.uuid4())[:8],
                "content": content,
                "priority": priority,
                "status": "pending",
            }
            todos.append(todo)
            
            with open(todo_path, 'w') as f:
                json.dump(todos, f, indent=2)
            
            return f"Todo added: {todo['id']}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.todo.complete")
    def todo_complete(todo_id: str) -> str:
        """Mark a todo as complete."""
        try:
            import os
            import json
            todo_path = os.path.expanduser("~/.praison/todo.json")
            if not os.path.exists(todo_path):
                return "No todos found"
            
            with open(todo_path, 'r') as f:
                todos = json.load(f)
            
            for todo in todos:
                if todo.get("id") == todo_id:
                    todo["status"] = "completed"
                    break
            else:
                return f"Todo not found: {todo_id}"
            
            with open(todo_path, 'w') as f:
                json.dump(todos, f, indent=2)
            
            return f"Todo completed: {todo_id}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.todo.delete")
    def todo_delete(todo_id: str) -> str:
        """Delete a todo item."""
        try:
            import os
            import json
            todo_path = os.path.expanduser("~/.praison/todo.json")
            if not os.path.exists(todo_path):
                return "No todos found"
            
            with open(todo_path, 'r') as f:
                todos = json.load(f)
            
            todos = [t for t in todos if t.get("id") != todo_id]
            
            with open(todo_path, 'w') as f:
                json.dump(todos, f, indent=2)
            
            return f"Todo deleted: {todo_id}"
        except Exception as e:
            return f"Error: {e}"
    
    # Tools discovery
    @register_tool("praisonai.tools.list")
    def tools_list() -> str:
        """List available tools."""
        try:
            from praisonaiagents.tools import get_available_tools
            tools = get_available_tools()
            return str(tools)
        except ImportError:
            return "Error: Tools module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.tools.info")
    def tools_info(tool_name: str) -> str:
        """Get information about a tool."""
        try:
            from praisonaiagents.tools import get_tool_info
            info = get_tool_info(tool_name)
            return str(info)
        except ImportError:
            return "Error: Tools module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.tools.search")
    def tools_search(query: str) -> str:
        """Search for tools by name or description."""
        try:
            from praisonaiagents.tools import search_tools
            results = search_tools(query)
            return str(results)
        except ImportError:
            return "Error: Tools module not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Schedule tools
    @register_tool("praisonai.schedule.list")
    def schedule_list() -> str:
        """List scheduled tasks."""
        try:
            from praisonaiagents.tools.schedule_tools import schedule_list as _schedule_list
            return _schedule_list()
        except ImportError:
            return "Error: Schedule tools not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.schedule.add")
    def schedule_add(
        task_name: str,
        cron: str,
        workflow_path: str,
    ) -> str:
        """Add a scheduled task."""
        try:
            from praisonaiagents.tools.schedule_tools import schedule_add as _schedule_add
            return _schedule_add(task_name, cron, workflow_path)
        except ImportError:
            return "Error: Schedule tools not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.schedule.remove")
    def schedule_remove(task_name: str) -> str:
        """Remove a scheduled task."""
        try:
            from praisonaiagents.tools.schedule_tools import schedule_remove as _schedule_remove
            return _schedule_remove(task_name)
        except ImportError:
            return "Error: Schedule tools not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Deploy tools
    @register_tool("praisonai.deploy.validate")
    def deploy_validate(config_path: str = "deploy.yaml") -> str:
        """Validate deployment configuration."""
        try:
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            required = ["name", "type"]
            missing = [k for k in required if k not in config]
            if missing:
                return f"Invalid config: missing {missing}"
            
            return f"Deployment config valid: {config_path}"
        except FileNotFoundError:
            return f"Config not found: {config_path}"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.deploy.status")
    def deploy_status(deployment_name: Optional[str] = None) -> str:
        """Get deployment status."""
        try:
            from praisonai.deploy import get_deployment_status
            status = get_deployment_status(deployment_name)
            return str(status)
        except ImportError:
            return "Error: Deploy module not available"
        except Exception as e:
            return f"Error: {e}"
    
    # Doctor/diagnostics tools
    @register_tool("praisonai.doctor.env")
    def doctor_env() -> str:
        """Check environment configuration."""
        try:
            import os
            checks = {
                "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
                "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY")),
            }
            return str(checks)
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.doctor.config")
    def doctor_config() -> str:
        """Check configuration files."""
        try:
            import os
            config_files = [
                "agents.yaml",
                "config.yaml",
                ".env",
                "pyproject.toml",
            ]
            results = {}
            for f in config_files:
                results[f] = os.path.exists(f)
            return str(results)
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.doctor.mcp")
    def doctor_mcp() -> str:
        """Check MCP server configuration."""
        try:
            from ..registry import get_tool_registry, get_resource_registry, get_prompt_registry
            
            tools = get_tool_registry().list_all()
            resources = get_resource_registry().list_all()
            prompts = get_prompt_registry().list_all()
            
            return f"MCP Status: {len(tools)} tools, {len(resources)} resources, {len(prompts)} prompts"
        except Exception as e:
            return f"Error: {e}"
    
    # Eval tools
    @register_tool("praisonai.eval.accuracy")
    def eval_accuracy(
        agent_config: str,
        input_text: str,
        expected_output: str,
        iterations: int = 3,
    ) -> str:
        """Run accuracy evaluation on an agent."""
        try:
            from praisonaiagents.eval import AccuracyEval
            from praisonaiagents import Agent
            
            agent = Agent.from_yaml(agent_config)
            eval_runner = AccuracyEval(
                agent=agent,
                input=input_text,
                expected_output=expected_output,
                num_iterations=iterations,
            )
            result = eval_runner.run()
            return str(result)
        except ImportError:
            return "Error: Eval module not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.eval.performance")
    def eval_performance(
        agent_config: str,
        input_text: str,
        iterations: int = 10,
    ) -> str:
        """Run performance evaluation on an agent."""
        try:
            from praisonaiagents.eval import PerformanceEval
            from praisonaiagents import Agent
            
            agent = Agent.from_yaml(agent_config)
            eval_runner = PerformanceEval(
                func=lambda: agent.chat(input_text),
                num_iterations=iterations,
            )
            result = eval_runner.run()
            return str(result)
        except ImportError:
            return "Error: Eval module not available"
        except Exception as e:
            return f"Error: {e}"
    
    # MCP config management
    @register_tool("praisonai.mcp_config.list")
    def mcp_config_list() -> str:
        """List MCP server configurations."""
        try:
            from praisonaiagents.memory.mcp_config import MCPConfigManager
            manager = MCPConfigManager()
            configs = manager.list_configs()
            return str(configs)
        except ImportError:
            return "Error: MCP config manager not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.mcp_config.show")
    def mcp_config_show(config_name: str) -> str:
        """Show MCP server configuration."""
        try:
            from praisonaiagents.memory.mcp_config import MCPConfigManager
            manager = MCPConfigManager()
            config = manager.get_config(config_name)
            return str(config)
        except ImportError:
            return "Error: MCP config manager not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.mcp_config.enable")
    def mcp_config_enable(config_name: str) -> str:
        """Enable an MCP server configuration."""
        try:
            from praisonaiagents.memory.mcp_config import MCPConfigManager
            manager = MCPConfigManager()
            manager.enable_config(config_name)
            return f"MCP config enabled: {config_name}"
        except ImportError:
            return "Error: MCP config manager not available"
        except Exception as e:
            return f"Error: {e}"
    
    @register_tool("praisonai.mcp_config.disable")
    def mcp_config_disable(config_name: str) -> str:
        """Disable an MCP server configuration."""
        try:
            from praisonaiagents.memory.mcp_config import MCPConfigManager
            manager = MCPConfigManager()
            manager.disable_config(config_name)
            return f"MCP config disabled: {config_name}"
        except ImportError:
            return "Error: MCP config manager not available"
        except Exception as e:
            return f"Error: {e}"
    
    logger.info("Registered CLI MCP tools")
