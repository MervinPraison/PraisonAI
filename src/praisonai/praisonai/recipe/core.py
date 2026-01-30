"""
Recipe Core API

Provides the main recipe execution functions.
"""

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

from .models import (
    RecipeResult,
    RecipeEvent,
    RecipeConfig,
    RecipeInfo,
    RecipeStatus,
    ValidationResult,
)
from .exceptions import (
    RecipeError,
    RecipeNotFoundError,
    RecipeDependencyError,
    RecipePolicyError,
    RecipeTimeoutError,
)


# Default denied tools (dangerous by default)
DEFAULT_DENIED_TOOLS = [
    "shell.exec",
    "shell.run", 
    "shell_tool",
    "file.write",
    "file.delete",
    "fs.write",
    "fs.delete",
    "network.unrestricted",
    "db.write",
    "db.delete",
    "execute_command",
]


def _generate_run_id() -> str:
    """Generate a unique run ID."""
    return f"run-{uuid.uuid4().hex[:12]}"


def _generate_trace_id() -> str:
    """Generate a trace ID for distributed tracing."""
    return uuid.uuid4().hex


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def get_template_search_paths() -> List[Path]:
    """
    Get list of paths to search for recipe templates.
    
    Precedence order:
    1. PRAISONAI_RECIPE_PATH environment variable (colon-separated)
    2. Current working directory ./recipes
    3. User home ~/.praison/recipes
    4. Agent-Recipes package templates (if installed)
    5. Built-in templates
    
    Returns:
        List of Path objects to search for templates
    """
    paths = []
    
    # 1. Environment variable
    env_path = os.environ.get("PRAISONAI_RECIPE_PATH")
    if env_path:
        for p in env_path.split(os.pathsep):
            path = Path(p).expanduser()
            if path.exists():
                paths.append(path)
    
    # 2. Current working directory
    cwd_recipes = Path.cwd() / "recipes"
    if cwd_recipes.exists():
        paths.append(cwd_recipes)
    
    # 3. User home
    home_recipes = Path.home() / ".praison" / "recipes"
    if home_recipes.exists():
        paths.append(home_recipes)
    
    # 4. Agent-Recipes package (lazy import)
    try:
        import agent_recipes
        if hasattr(agent_recipes, 'get_template_path'):
            agent_path = Path(agent_recipes.get_template_path(""))
            if agent_path.parent.exists():
                paths.append(agent_path.parent)
        elif hasattr(agent_recipes, '__file__'):
            agent_templates = Path(agent_recipes.__file__).parent / "templates"
            if agent_templates.exists():
                paths.append(agent_templates)
    except ImportError:
        pass
    
    # 5. Built-in templates (relative to this package)
    builtin = Path(__file__).parent.parent / "templates"
    if builtin.exists():
        paths.append(builtin)
    
    return paths


def reload_registry():
    """
    Reload the recipe registry, clearing any cached templates.
    
    This is useful for hot-reloading recipes during development
    or when using the /admin/reload endpoint.
    """
    global _recipe_cache
    if '_recipe_cache' in globals():
        _recipe_cache.clear()
    
    # Also clear any module-level caches
    import importlib
    try:
        from praisonai import recipe as recipe_module
        importlib.reload(recipe_module)
    except Exception:
        pass


# Recipe cache for performance
_recipe_cache: Dict[str, Any] = {}


def run(
    name: str,
    input: Union[str, Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> RecipeResult:
    """
    Run a recipe by name.
    
    Args:
        name: Recipe name or URI (e.g., "support-reply", "github:user/repo/recipe")
        input: Input data (string path or dict)
        config: Optional config overrides
        session_id: Optional session ID for state grouping
        options: Execution options:
            - timeout_sec: Timeout in seconds (default: 300)
            - dry_run: Validate without executing (default: False)
            - verbose: Enable verbose output (default: False)
            - force: Force execution even with missing deps (default: False)
            - offline: Use only cached templates (default: False)
            - mode: Execution mode - "dev" or "prod" (default: "dev")
            - allow_dangerous_tools: Allow dangerous tools (default: False)
            
    Returns:
        RecipeResult with run_id, status, output, metrics, trace
        
    Example:
        >>> from praisonai import recipe
        >>> result = recipe.run("support-reply", input={"ticket_id": "T-123"})
        >>> if result.ok:
        ...     print(result.output["reply"])
    """
    options = options or {}
    config = config or {}
    input = input or {}
    
    # Generate identifiers - use custom trace_name if provided
    run_id = options.get("trace_name") or _generate_run_id()
    trace_id = _generate_trace_id()
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    
    start_time = time.time()
    
    trace = {
        "run_id": run_id,
        "trace_id": trace_id,
        "session_id": session_id,
    }
    
    # Initialize replay trace writer if --save flag is set
    trace_writer = None
    trace_emitter = None
    trace_emitter_token = None  # Token for resetting global emitter
    if options.get("save_replay", False):
        try:
            from praisonai.replay import ContextTraceWriter
            from praisonaiagents.trace.context_events import ContextTraceEmitter, set_context_emitter
            trace_writer = ContextTraceWriter(session_id=run_id)
            trace_emitter = ContextTraceEmitter(sink=trace_writer, session_id=run_id, full_content=True)
            # Set as global emitter so agents can access it
            trace_emitter_token = set_context_emitter(trace_emitter)
            trace_emitter.session_start({"recipe": name, "run_id": run_id})
            print(f"📝 Replay trace enabled: {run_id}")
        except ImportError as e:
            import logging
            logging.debug(f"Replay module not available: {e}")
        except Exception as e:
            import logging
            logging.warning(f"Failed to initialize trace writer: {e}")
    
    try:
        # Load template
        recipe_config = _load_recipe(name, offline=options.get("offline", False))
        
        if recipe_config is None:
            return RecipeResult(
                run_id=run_id,
                recipe=name,
                version="unknown",
                status=RecipeStatus.FAILED,
                error=f"Recipe not found: {name}",
                metrics={"duration_sec": time.time() - start_time},
                trace=trace,
            )
        
        # Check dependencies
        if not options.get("force", False):
            dep_result = _check_dependencies(recipe_config)
            if not dep_result["all_satisfied"]:
                missing = _format_missing_deps(dep_result)
                return RecipeResult(
                    run_id=run_id,
                    recipe=recipe_config.name,
                    version=recipe_config.version,
                    status=RecipeStatus.MISSING_DEPS,
                    error=f"Missing dependencies: {', '.join(missing)}",
                    metrics={"duration_sec": time.time() - start_time},
                    trace=trace,
                )
        
        # Check tool permissions
        if not options.get("allow_dangerous_tools", False):
            policy_error = _check_tool_policy(recipe_config)
            if policy_error:
                return RecipeResult(
                    run_id=run_id,
                    recipe=recipe_config.name,
                    version=recipe_config.version,
                    status=RecipeStatus.POLICY_DENIED,
                    error=policy_error,
                    metrics={"duration_sec": time.time() - start_time},
                    trace=trace,
                )
        
        # Dry run mode
        if options.get("dry_run", False):
            # Close trace writer for dry-run
            if trace_emitter:
                trace_emitter.session_end()
            if trace_writer:
                trace_writer.close()
            return RecipeResult(
                run_id=run_id,
                recipe=recipe_config.name,
                version=recipe_config.version,
                status=RecipeStatus.DRY_RUN,
                output={
                    "plan": "Would execute recipe with provided config",
                    "recipe": recipe_config.name,
                    "config": {**recipe_config.defaults, **config},
                },
                metrics={"duration_sec": time.time() - start_time},
                trace=trace,
            )
        
        # Merge input and config with built-in variables
        # Add built-in template variables that should always be resolved
        builtin_vars = {
            "today": datetime.now().strftime("%B %d, %Y"),  # e.g., "January 24, 2026"
            "date": datetime.now().strftime("%Y-%m-%d"),     # e.g., "2026-01-24"
            "time": datetime.now().strftime("%H:%M:%S"),     # e.g., "14:30:00"
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "year": datetime.now().strftime("%Y"),
            "month": datetime.now().strftime("%B"),
        }
        
        if isinstance(input, str):
            merged_config = {**builtin_vars, **recipe_config.defaults, "input": input, **config}
        else:
            merged_config = {**builtin_vars, **recipe_config.defaults, **input, **config}
        
        # Execute recipe (pass trace_emitter for event tracking)
        output = _execute_recipe(
            recipe_config,
            merged_config,
            session_id,
            options,
            trace_emitter=trace_emitter,
        )
        
        duration = time.time() - start_time
        
        # Close trace writer on success
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
            print(f"📝 Replay trace saved: {run_id}")
        # Reset global emitter
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        
        return RecipeResult(
            run_id=run_id,
            recipe=recipe_config.name,
            version=recipe_config.version,
            status=RecipeStatus.SUCCESS,
            output=output,
            metrics={"duration_sec": round(duration, 2)},
            trace=trace,
        )
        
    except RecipeNotFoundError as e:
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        return RecipeResult(
            run_id=run_id,
            recipe=name,
            version="unknown",
            status=RecipeStatus.FAILED,
            error=str(e),
            metrics={"duration_sec": time.time() - start_time},
            trace=trace,
        )
    except RecipeDependencyError as e:
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        return RecipeResult(
            run_id=run_id,
            recipe=e.recipe or name,
            version="unknown",
            status=RecipeStatus.MISSING_DEPS,
            error=str(e),
            metrics={"duration_sec": time.time() - start_time},
            trace=trace,
        )
    except RecipePolicyError as e:
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        return RecipeResult(
            run_id=run_id,
            recipe=e.recipe or name,
            version="unknown",
            status=RecipeStatus.POLICY_DENIED,
            error=str(e),
            metrics={"duration_sec": time.time() - start_time},
            trace=trace,
        )
    except RecipeTimeoutError as e:
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        return RecipeResult(
            run_id=run_id,
            recipe=name,
            version="unknown",
            status=RecipeStatus.TIMEOUT,
            error=str(e),
            metrics={"duration_sec": time.time() - start_time},
            trace=trace,
        )
    except Exception as e:
        if trace_emitter:
            trace_emitter.session_end()
        if trace_writer:
            trace_writer.close()
        if trace_emitter_token:
            from praisonaiagents.trace.context_events import reset_context_emitter
            reset_context_emitter(trace_emitter_token)
        return RecipeResult(
            run_id=run_id,
            recipe=name,
            version="unknown",
            status=RecipeStatus.FAILED,
            error=str(e),
            metrics={"duration_sec": time.time() - start_time},
            trace=trace,
        )


def run_stream(
    name: str,
    input: Union[str, Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Iterator[RecipeEvent]:
    """
    Run a recipe with streaming events.
    
    Yields RecipeEvent objects for progress tracking.
    
    Args:
        name: Recipe name or URI
        input: Input data
        config: Optional config overrides
        session_id: Optional session ID
        options: Execution options
        
    Yields:
        RecipeEvent objects with event_type and data
        
    Example:
        >>> for event in recipe.run_stream("transcript-generator", input="audio.mp3"):
        ...     print(f"[{event.event_type}] {event.data}")
    """
    options = options or {}
    config = config or {}
    input = input or {}
    
    run_id = _generate_run_id()
    trace_id = _generate_trace_id()
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    
    # Started event
    yield RecipeEvent(
        event_type="started",
        data={
            "run_id": run_id,
            "recipe": name,
            "trace_id": trace_id,
            "session_id": session_id,
        },
    )
    
    try:
        # Load recipe
        yield RecipeEvent(
            event_type="progress",
            data={"step": "loading", "message": f"Loading recipe: {name}"},
        )
        
        recipe_config = _load_recipe(name, offline=options.get("offline", False))
        
        if recipe_config is None:
            yield RecipeEvent(
                event_type="error",
                data={"code": "not_found", "message": f"Recipe not found: {name}"},
            )
            return
        
        # Check dependencies
        yield RecipeEvent(
            event_type="progress",
            data={"step": "checking_deps", "message": "Checking dependencies"},
        )
        
        if not options.get("force", False):
            dep_result = _check_dependencies(recipe_config)
            if not dep_result["all_satisfied"]:
                missing = _format_missing_deps(dep_result)
                yield RecipeEvent(
                    event_type="error",
                    data={
                        "code": "missing_deps",
                        "message": f"Missing dependencies: {', '.join(missing)}",
                        "missing": missing,
                    },
                )
                return
        
        # Dry run
        if options.get("dry_run", False):
            yield RecipeEvent(
                event_type="completed",
                data={
                    "run_id": run_id,
                    "status": RecipeStatus.DRY_RUN,
                    "message": "Dry run completed",
                },
            )
            return
        
        # Execute
        yield RecipeEvent(
            event_type="progress",
            data={"step": "executing", "message": "Executing recipe"},
        )
        
        # Merge config
        if isinstance(input, str):
            merged_config = {**recipe_config.defaults, "input": input, **config}
        else:
            merged_config = {**recipe_config.defaults, **input, **config}
        
        start_time = time.time()
        output = _execute_recipe(recipe_config, merged_config, session_id, options)
        duration = time.time() - start_time
        
        # Output event
        yield RecipeEvent(
            event_type="output",
            data={"output": output},
        )
        
        # Completed event
        yield RecipeEvent(
            event_type="completed",
            data={
                "run_id": run_id,
                "status": RecipeStatus.SUCCESS,
                "duration_sec": round(duration, 2),
            },
        )
        
    except Exception as e:
        yield RecipeEvent(
            event_type="error",
            data={"code": "execution_error", "message": str(e)},
        )


def validate(name: str, offline: bool = False) -> ValidationResult:
    """
    Validate a recipe and check dependencies.
    
    Args:
        name: Recipe name or URI
        offline: Use only cached templates
        
    Returns:
        ValidationResult with valid status, errors, warnings, dependencies
        
    Example:
        >>> result = recipe.validate("support-reply")
        >>> if result.valid:
        ...     print("Recipe is valid")
        >>> else:
        ...     print(f"Errors: {result.errors}")
    """
    errors = []
    warnings = []
    
    try:
        recipe_config = _load_recipe(name, offline=offline)
        
        if recipe_config is None:
            return ValidationResult(
                valid=False,
                recipe=name,
                version="unknown",
                errors=[f"Recipe not found: {name}"],
            )
        
        # Check dependencies
        dep_result = _check_dependencies(recipe_config)
        
        # Check for missing required deps
        for pkg in dep_result.get("packages", []):
            if not pkg.get("available", False):
                errors.append(f"Missing package: {pkg['name']}")
        
        for env in dep_result.get("env", []):
            if not env.get("available", False):
                errors.append(f"Missing env var: ${env['name']}")
        
        for ext in dep_result.get("external", []):
            if not ext.get("available", False):
                warnings.append(f"Missing external tool: {ext['name']}")
        
        # Check tool policy
        policy_error = _check_tool_policy(recipe_config)
        if policy_error:
            warnings.append(f"Tool policy: {policy_error}")
        
        return ValidationResult(
            valid=len(errors) == 0,
            recipe=recipe_config.name,
            version=recipe_config.version,
            errors=errors,
            warnings=warnings,
            dependencies=dep_result,
        )
        
    except Exception as e:
        return ValidationResult(
            valid=False,
            recipe=name,
            version="unknown",
            errors=[str(e)],
        )


def list_recipes(
    source_filter: Optional[str] = None,
    tags: Optional[List[str]] = None,
    offline: bool = False,
) -> List[RecipeInfo]:
    """
    List available recipes.
    
    Args:
        source_filter: Filter by source (local, package, github)
        tags: Filter by tags
        offline: Use only cached templates
        
    Returns:
        List of RecipeInfo objects
        
    Example:
        >>> recipes = recipe.list_recipes(tags=["video"])
        >>> for r in recipes:
        ...     print(f"{r.name}: {r.description}")
    """
    try:
        from praisonai.templates import TemplateDiscovery
        
        discovery = TemplateDiscovery()
        templates = discovery.list_templates(source_filter=source_filter)
        
        recipes = []
        for t in templates:
            # Filter by tags if specified
            if tags:
                template_tags = getattr(t, 'tags', []) or []
                if not any(tag in template_tags for tag in tags):
                    continue
            
            recipes.append(RecipeInfo(
                name=t.name,
                version=getattr(t, 'version', '1.0.0'),
                description=getattr(t, 'description', ''),
                tags=getattr(t, 'tags', []) or [],
                path=str(t.path) if hasattr(t, 'path') else '',
                source=getattr(t, 'source', 'local'),
            ))
        
        return recipes
        
    except Exception:
        return []


def describe(name: str, offline: bool = False) -> Optional[RecipeConfig]:
    """
    Get detailed information about a recipe.
    
    Args:
        name: Recipe name or URI
        offline: Use only cached templates
        
    Returns:
        RecipeConfig with full recipe details, or None if not found
        
    Example:
        >>> info = recipe.describe("support-reply")
        >>> print(f"Required env vars: {info.get_required_env()}")
    """
    return _load_recipe(name, offline=offline)


# --- Internal Functions ---

def _load_recipe(name: str, offline: bool = False) -> Optional[RecipeConfig]:
    """Load a recipe by name or URI or path."""
    try:
        from praisonai.templates import TemplateDiscovery, TemplateLoader
        
        # Check if name is an absolute path to a recipe directory
        name_path = Path(name)
        if name_path.is_absolute() and name_path.exists() and name_path.is_dir():
            # Check for agents.yaml or TEMPLATE.yaml in the directory
            agents_yaml = name_path / "agents.yaml"
            template_yaml = name_path / "TEMPLATE.yaml"
            
            if agents_yaml.exists() or template_yaml.exists():
                loader = TemplateLoader(offline=offline)
                template = loader.load(str(name_path))
                
                return RecipeConfig(
                    name=template.name,
                    version=template.version,
                    description=template.description,
                    author=template.author,
                    license=template.license,
                    tags=template.tags,
                    requires=template.requires,
                    tools=template.raw.get("tools", {}),
                    config_schema=template.config_schema,
                    defaults=template.defaults,
                    outputs=template.raw.get("outputs", []),
                    governance=template.raw.get("governance", {}),
                    data_policy=template.raw.get("data_policy", {}),
                    path=str(template.path) if template.path else None,
                    raw=template.raw,
                )
        
        discovery = TemplateDiscovery()
        discovered = discovery.find_template(name)
        
        if discovered:
            loader = TemplateLoader(offline=offline)
            template = loader.load(str(discovered.path))
            
            return RecipeConfig(
                name=template.name,
                version=template.version,
                description=template.description,
                author=template.author,
                license=template.license,
                tags=template.tags,
                requires=template.requires,
                tools=template.raw.get("tools", {}),
                config_schema=template.config_schema,
                defaults=template.defaults,
                outputs=template.raw.get("outputs", []),
                governance=template.raw.get("governance", {}),
                data_policy=template.raw.get("data_policy", {}),
                path=str(template.path) if template.path else None,
                raw=template.raw,
            )
        
        # Try loading directly as URI
        loader = TemplateLoader(offline=offline)
        try:
            template = loader.load(name)
            return RecipeConfig(
                name=template.name,
                version=template.version,
                description=template.description,
                author=template.author,
                license=template.license,
                tags=template.tags,
                requires=template.requires,
                tools=template.raw.get("tools", {}),
                config_schema=template.config_schema,
                defaults=template.defaults,
                outputs=template.raw.get("outputs", []),
                governance=template.raw.get("governance", {}),
                data_policy=template.raw.get("data_policy", {}),
                path=str(template.path) if template.path else None,
                raw=template.raw,
            )
        except Exception:
            pass
        
        return None
        
    except Exception:
        return None


def _check_package_installed(package_name: str) -> bool:
    """
    Check if a Python package is installed using importlib.metadata.
    
    This is more reliable than trying to import the package because:
    1. Package names often differ from import names (e.g., tavily-python -> tavily)
    2. importlib.metadata checks the actual installed packages
    3. No side effects from importing modules
    
    Args:
        package_name: The pip package name (e.g., 'tavily-python', 'pillow')
        
    Returns:
        True if package is installed, False otherwise
    """
    try:
        from importlib.metadata import distributions
        
        # Normalize package name for comparison (pip normalizes - and _ and case)
        normalized = package_name.lower().replace("-", "_").replace(".", "_")
        
        for dist in distributions():
            dist_name = dist.metadata.get("Name", "").lower().replace("-", "_").replace(".", "_")
            if dist_name == normalized:
                return True
        
        return False
    except Exception:
        # Fallback: try to import with common name transformations
        try:
            import_name = package_name.replace("-", "_")
            __import__(import_name)
            return True
        except ImportError:
            return False


def _check_dependencies(recipe_config: RecipeConfig) -> Dict[str, Any]:
    """Check if recipe dependencies are satisfied."""
    result = {
        "all_satisfied": True,
        "packages": [],
        "env": [],
        "tools": [],
        "external": [],
    }
    
    # Check Python packages
    for pkg in recipe_config.get_required_packages():
        available = _check_package_installed(pkg)
        result["packages"].append({"name": pkg, "available": available})
        if not available:
            result["all_satisfied"] = False
    
    # Check environment variables
    for env_var in recipe_config.get_required_env():
        available = env_var in os.environ
        result["env"].append({"name": env_var, "available": available})
        if not available:
            result["all_satisfied"] = False
    
    # Check external tools
    import shutil
    for ext in recipe_config.get_external_deps():
        ext_name = ext.get("name", ext) if isinstance(ext, dict) else ext
        available = shutil.which(ext_name) is not None
        result["external"].append({"name": ext_name, "available": available})
        # External tools are warnings, not errors
    
    return result


def _format_missing_deps(dep_result: Dict[str, Any]) -> List[str]:
    """Format missing dependencies as a list of strings."""
    missing = []
    
    for pkg in dep_result.get("packages", []):
        if not pkg.get("available", False):
            missing.append(pkg["name"])
    
    for env in dep_result.get("env", []):
        if not env.get("available", False):
            missing.append(f"${env['name']}")
    
    return missing


def _check_tool_policy(recipe_config: RecipeConfig) -> Optional[str]:
    """Check if recipe uses denied tools. Returns error message or None."""
    allowed = set(recipe_config.get_allowed_tools())
    denied = set(recipe_config.get_denied_tools())
    required = set(recipe_config.get_required_tools())
    
    # Check if any required tools are in default denied list
    for tool in required:
        if tool in DEFAULT_DENIED_TOOLS and tool not in allowed:
            return f"Tool '{tool}' is denied by default. Use allow_dangerous_tools=True to override."
    
    # Check explicit denials
    for tool in required:
        if tool in denied:
            return f"Tool '{tool}' is explicitly denied by recipe policy."
    
    return None


def _execute_recipe(
    recipe_config: RecipeConfig,
    merged_config: Dict[str, Any],
    session_id: str,
    options: Dict[str, Any],
    trace_emitter: Any = None,
) -> Any:
    """Execute the recipe workflow."""
    try:
        from praisonai.templates import TemplateLoader
        from praisonai.templates.tool_override import create_tool_registry_with_overrides
        
        loader = TemplateLoader()
        
        # Load workflow config
        from praisonai.templates.loader import TemplateConfig as LoaderTemplateConfig
        
        # Create a TemplateConfig compatible with loader
        template_path = Path(recipe_config.path) if recipe_config.path else None
        
        # Determine workflow file - check for agents.yaml if workflow.yaml not specified
        workflow_raw = recipe_config.raw.get("workflow", "workflow.yaml")
        agents_raw = recipe_config.raw.get("agents", "agents.yaml")
        
        # Handle case where "workflow" or "agents" is a dict (inline definition) vs string (file path)
        workflow_file = workflow_raw if isinstance(workflow_raw, str) else "workflow.yaml"
        agents_file = "agents.yaml"  # Always use agents.yaml as the file path
        
        # If workflow.yaml doesn't exist but agents.yaml does, use agents.yaml as workflow
        if template_path:
            workflow_path = template_path / workflow_file
            agents_path = template_path / agents_file
            if not workflow_path.exists() and agents_path.exists():
                workflow_file = agents_file
        
        loader_config = LoaderTemplateConfig(
            name=recipe_config.name,
            description=recipe_config.description,
            version=recipe_config.version,
            author=recipe_config.author,
            license=recipe_config.license,
            tags=recipe_config.tags,
            requires=recipe_config.requires,
            workflow_file=workflow_file,
            agents_file=agents_file,
            config_schema=recipe_config.config_schema,
            defaults=merged_config,
            skills=recipe_config.raw.get("skills", []),
            cli=recipe_config.raw.get("cli", {}),
            raw=recipe_config.raw,
            path=template_path,
        )
        
        workflow_config = loader.load_workflow_config(loader_config)
        
        # Build tool registry
        tool_registry = create_tool_registry_with_overrides(
            include_defaults=True,
            template_dir=recipe_config.path,
        )
        
        # Execute based on workflow type
        if "agents" in workflow_config and "tasks" in workflow_config:
            return _execute_praisonai_workflow(
                workflow_config, merged_config, tool_registry, options
            )
        elif "steps" in workflow_config:
            # Pass the workflow file path for proper execution
            workflow_file_path = template_path / workflow_file if template_path else None
            merged_config["_workflow_file"] = str(workflow_file_path) if workflow_file_path else None
            return _execute_steps_workflow(
                workflow_config, merged_config, tool_registry, options
            )
        else:
            # Simple agent execution
            return _execute_simple_agent(
                workflow_config, merged_config, tool_registry, options
            )
            
    except ImportError as e:
        raise RecipeError(f"Missing dependency for recipe execution: {e}")
    except Exception as e:
        raise RecipeError(f"Recipe execution failed: {e}")


def _execute_praisonai_workflow(
    workflow_config: Dict[str, Any],
    config: Dict[str, Any],
    tool_registry: Any,
    options: Dict[str, Any],
) -> Any:
    """Execute a PraisonAI agents/tasks workflow."""
    from praisonaiagents import Agent, Task, Agents
    from praisonai.templates.tool_override import resolve_tools
    
    agents = []
    agent_map = {}
    
    agents_cfg = workflow_config.get("agents", [])
    if isinstance(agents_cfg, dict):
        # Convert dict of agents to list of dicts, including the key as 'name'
        agents_list = []
        for name, cfg in agents_cfg.items():
            if isinstance(cfg, dict):
                cfg["name"] = cfg.get("name", name)
                agents_list.append(cfg)
        agents_cfg = agents_list
    
    for agent_cfg in agents_cfg:
        agent_tools = resolve_tools(
            agent_cfg.get("tools", []),
            registry=tool_registry,
        )
        
        # Use output= instead of verbose= (DRY: same as Workflow)
        output_mode = options.get("output")
        if not output_mode and options.get("verbose"):
            output_mode = "verbose"
        
        agent = Agent(
            name=agent_cfg.get("name", "Agent"),
            role=agent_cfg.get("role", ""),
            goal=agent_cfg.get("goal", ""),
            backstory=agent_cfg.get("backstory", ""),
            tools=agent_tools if agent_tools else None,
            llm=agent_cfg.get("llm"),
            output=output_mode,  # Use output= instead of deprecated verbose=
        )
        agents.append(agent)
        agent_map[agent_cfg.get("name")] = agent
    
    tasks = []
    for task_cfg in workflow_config.get("tasks", []):
        agent_name = task_cfg.get("agent")
        agent = agent_map.get(agent_name, agents[0] if agents else None)
        
        # Substitute config values in description
        description = task_cfg.get("description", "")
        try:
            description = description.format(**config)
        except KeyError:
            pass
        
        task = Task(
            name=task_cfg.get("name", "Task"),
            description=description,
            expected_output=task_cfg.get("expected_output", ""),
            agent=agent,
        )
        tasks.append(task)
    
    # Use output mode for Agents as well (DRY approach)
    output_mode = options.get("output")
    if not output_mode and options.get("verbose"):
        output_mode = "verbose"
    
    praison = AgentManager(
        agents=agents,
        tasks=tasks,
        process=workflow_config.get("process", "sequential"),
    )
    
    return praison.start()


def _execute_steps_workflow(
    workflow_config: Dict[str, Any],
    config: Dict[str, Any],
    tool_registry: Any,
    options: Dict[str, Any],
) -> Any:
    """
    Execute a steps-based workflow using praisonaiagents Workflow.
    
    This properly executes the workflow with all features:
    - include steps (modular recipes)
    - loop steps (parallel/sequential)
    - output_variable
    - agent execution
    - CLI variable overrides via --var
    """
    from praisonaiagents.workflows import YAMLWorkflowParser
    
    # Get the workflow file path from config if available
    workflow_file = config.get("_workflow_file")
    
    # Extract CLI variable overrides (everything except internal keys)
    extra_vars = {k: v for k, v in config.items() if not k.startswith("_")}
    
    if workflow_file:
        # Use YAMLWorkflowParser to properly parse and execute the workflow
        # This handles include steps, loops, variables, tools, etc.
        parser = YAMLWorkflowParser(tool_registry=tool_registry)
        workflow = parser.parse_file(workflow_file, extra_vars=extra_vars)
        return workflow.start()
    
    # Fallback: Create workflow from config dict using parser
    from praisonaiagents import Workflow
    
    # Merge YAML variables with CLI overrides (CLI takes precedence)
    yaml_vars = workflow_config.get("variables", {})
    merged_vars = {**yaml_vars, **extra_vars}
    
    workflow = Workflow(
        name=workflow_config.get("name", "RecipeWorkflow"),
        steps=workflow_config.get("steps", []),
        variables=merged_vars,
    )
    return workflow.start()



def _execute_simple_agent(
    workflow_config: Dict[str, Any],
    config: Dict[str, Any],
    tool_registry: Any,
    options: Dict[str, Any],
) -> Any:
    """Execute a simple single-agent workflow."""
    from praisonaiagents import Agent
    
    # Use output= instead of verbose= (DRY: same as Workflow)
    output_mode = options.get("output")
    if not output_mode and options.get("verbose"):
        output_mode = "verbose"
    
    agent = Agent(
        name=workflow_config.get("name", "RecipeAgent"),
        role=workflow_config.get("role", "AI Assistant"),
        goal=workflow_config.get("goal", "Complete the task"),
        backstory=workflow_config.get("backstory", ""),
        output=output_mode,  # Use output= instead of deprecated verbose=
    )
    
    prompt = config.get("input", config.get("prompt", ""))
    if prompt:
        return agent.chat(prompt)
    
    return {"message": "Recipe executed", "config": config}
