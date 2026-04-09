# PraisonAI CLI Router Architecture Documentation

## Overview

The PraisonAI CLI implements a sophisticated hybrid routing system that seamlessly combines modern Typer-based commands with legacy argparse support. This architecture provides both backward compatibility for existing users and a modern, extensible CLI experience for new features.

## Architecture Components

### 1. Entry Point Flow (`main.py`)

**File**: `src/praisonai/praisonai/cli/main.py`

The CLI entry point implements a clear routing hierarchy that prioritizes modern Typer commands while maintaining legacy compatibility:

```python
def main():
    """Unified CLI entry point — Typer-first, legacy fallback."""
    # 1. --version / -V          → print version and exit
    # 2. --help / -h             → Typer help (global or command-level)  
    # 3. No arguments            → Typer interactive TUI
    # 4. First arg is a Typer cmd→ Typer (auto-discovered from app.py)
    # 5. Everything else         → Legacy (prompt, .yaml, deprecated flags)
```

**Key Features:**
- **Auto-discovery**: Uses Click introspection to discover Typer commands dynamically
- **Flag parsing**: Intelligent parsing that skips global flags (`--json`, `--output-format`, etc.)
- **Minimal imports**: Version check happens without loading the full CLI stack
- **Graceful fallback**: Unknown commands route to legacy argparse system

### 2. Typer Application Setup (`app.py`)

**File**: `src/praisonai/praisonai/cli/app.py`

The core Typer application serves as the command registry and global state manager:

```python
app = typer.Typer(
    name="praisonai",
    help="PraisonAI - AI Agents Framework CLI",
    add_completion=False,  # We handle completion manually
    no_args_is_help=False,  # Allow running without args for legacy compatibility
    rich_markup_mode="rich",
)
```

#### Global State Management

The application maintains a `GlobalState` class that tracks:
- Output format preferences (text, JSON, stream-JSON)
- Color and verbosity settings
- Screen reader compatibility flags
- Output controller instances with run/trace IDs

```python
class GlobalState:
    """Global state for CLI options."""
    output_format: OutputFormat = OutputFormat.text
    no_color: bool = False
    quiet: bool = False
    verbose: bool = False
    screen_reader: bool = False
    output_controller: Optional[OutputController] = None
```

### 3. Command Registration Architecture

The `register_commands()` function in `app.py` (lines 168-543) implements a modular command registration pattern:

#### Standard Command Registration Pattern

```python
# Import command modules - Core commands
from .commands.config import app as config_app
from .commands.traces import app as traces_app
# ... additional imports

# Register sub-apps - Core commands
app.add_typer(config_app, name="config", help="Configuration management")
app.add_typer(traces_app, name="traces", help="Trace collection management")
# ... additional registrations
```

#### Special Registration Patterns

The system supports multiple registration patterns for different use cases:

1. **Direct Command Registration** (for complex commands):
```python
@app.command(name="app")
def app_cmd(parameters...):
    """Start an AgentOS server for production deployment."""
    # Implementation
```

2. **Module-based Registration** (for command groups):
```python
retrieval_module.register_commands(app)
```

3. **Dynamic Sub-app Creation** (for feature-specific commands):
```python
standardise_app = typer.Typer(name="standardise", help="...")
@standardise_app.command("check")
def standardise_check(...):
    # Implementation
app.add_typer(standardise_app, name="standardise", help="...")
```

### 4. Command Module Structure

Each command module follows a consistent architectural pattern:

**Example**: `src/praisonai/praisonai/cli/commands/config.py`

```python
import typer
from ..output.console import get_output_controller

app = typer.Typer(help="Configuration management")

@app.command("list")
def config_list(
    scope: str = typer.Option(
        "all", "--scope", "-s", 
        help="Scope to list: all, user, project"
    ),
):
    """List all configuration values."""
    output = get_output_controller()
    # Implementation with consistent output formatting
```

**Architectural Principles:**
- Each module exports an `app` variable (Typer instance)
- Commands use consistent parameter patterns with `typer.Option`/`typer.Argument`
- Output controller integration for consistent formatting across all commands
- JSON output support via centralized output controller
- State management through context identifiers

### 5. Legacy Integration Patterns

The system maintains backward compatibility through sophisticated delegation patterns:

#### Delegation from Legacy to Typer

```python
# Handle replay command - context replay for debugging agent execution
if args.command == 'replay':
    from .app import app as typer_app, register_commands
    register_commands()
    import sys as _sys
    _sys.argv = ['praisonai', 'replay'] + unknown_args
    try:
        typer_app()
    except SystemExit as e:
        sys.exit(e.code if e.code else 0)
    sys.exit(0)
```

**Delegation Flow:**
1. Import typer app and register all commands
2. Rebuild `sys.argv` with proper command structure
3. Invoke typer app with comprehensive exception handling
4. Ensure proper exit code propagation

#### Legacy Fallback Routing

The `legacy.py` module provides:

```python
def route_to_legacy(argv):
    """Route to the legacy argparse CLI."""
    from praisonai.cli.main import PraisonAI
    # Execution with argv manipulation for backward compatibility
```

### 6. Command Discovery Mechanism

The system implements automatic command discovery using Click introspection:

```python
def _get_typer_commands():
    """Auto-discover registered Typer commands via Click introspection."""
    from praisonai.cli.app import app, register_commands
    register_commands()
    
    import typer.main
    import click
    click_app = typer.main.get_command(app)
    ctx = click.Context(click_app, info_name="praisonai")
    _typer_commands_cache = set(click_app.list_commands(ctx))
```

**Benefits:**
- Eliminates manual command lists that can become outdated
- Enables automatic routing decisions
- Supports dynamic command registration
- Reduces maintenance overhead

### 7. Output and State Management Architecture

#### Unified Output Controller

The system implements a centralized output management system:

```python
state.output_controller = OutputController(
    mode=mode,
    no_color=state.no_color,
    run_id=context.run_id,
    trace_id=context.trace_id,
)
set_output_controller(state.output_controller)
```

**Features:**
- Multiple output modes: JSON, text, stream, quiet, verbose
- Screen reader compatibility support
- Consistent color management across all commands
- Run and trace ID correlation for observability

#### Global State Flow

1. `app.py` callback processes global CLI options
2. Creates output controller with unique context identifiers
3. Sets global state accessible to all command modules
4. Commands use `get_output_controller()` for consistent output formatting

### 8. Command Categories and Organization

The CLI organizes commands into logical functional categories:

#### Core Infrastructure Commands
- **config**: Configuration management and inspection
- **traces**: Trace collection and analysis
- **env**: Environment diagnostics and validation
- **session**: Session lifecycle management
- **debug**: Development and debugging utilities

#### Terminal-Native Commands
- **chat**: Interactive REPL-style chat interface
- **code**: Terminal-native code assistant
- **call**: Voice and call interaction modes
- **realtime**: Real-time interaction capabilities

#### Agent Management Commands
- **agents**: Agent lifecycle and management
- **skills**: Skill definition and management
- **tools**: Tool registry and management
- **workflow**: Workflow definition and execution

#### Development and Testing Commands
- **test**: Test suite execution with provider options
- **examples**: Example file management and execution
- **eval**: Evaluation and benchmarking
- **profile**: Performance profiling and analysis

#### Integration Commands
- **bot**: Multi-platform messaging bot deployment
- **gateway**: WebSocket gateway server management
- **browser**: Browser automation and control
- **plugins**: Plugin system management

#### Specialized Commands
- **retrieval**: Unified index/query operations (Agent-first approach)
- **standardise**: Documentation and example standardization
- **mcp**: Model Context Protocol server management

## Routing Flow Diagram

```
CLI Entry Point (main.py)
├── Version Check (--version/-V) → Exit
├── Help Request (--help/-h) → Typer Help System
├── No Arguments → Interactive TUI Mode
├── Typer Command Detection
│   ├── Auto-discover via Click introspection
│   ├── Flag parsing and global option extraction
│   └── Route to Typer App (app.py)
│       ├── Global State Management
│       ├── Output Controller Setup
│       ├── Command Registry Lookup
│       └── Execute Specific Command Module
└── Legacy Fallback
    ├── Argparse-based routing
    ├── YAML file processing
    ├── Direct prompt execution
    └── Deprecated flag handling
```

## Key Architectural Strengths

### 1. Extensibility and Modularity
- Adding new commands requires only module creation and import
- Command modules are completely independent and testable
- Plugin-like architecture enables feature isolation

### 2. Backward Compatibility
- Legacy argparse commands continue to function seamlessly
- Gradual migration path from legacy to modern commands
- No breaking changes for existing users

### 3. Performance Optimization
- Lazy loading prevents importing unused command modules
- Auto-discovery eliminates static command registration overhead
- Minimal startup time for version and help operations

### 4. Consistent User Experience
- All commands share unified output formatting
- Global options work consistently across all commands
- JSON output support available universally

### 5. Development Efficiency
- Auto-discovery reduces maintenance overhead
- Each command module can be developed independently
- Consistent patterns reduce cognitive load

### 6. Testing and Reliability
- Each command module can be unit tested in isolation
- Global state management is centralized and predictable
- Error handling is consistent across all commands

## Implementation Guidelines

### Adding New Commands

1. **Create Command Module**: `src/praisonai/praisonai/cli/commands/newcommand.py`
```python
import typer
from ..output.console import get_output_controller

app = typer.Typer(help="New command functionality")

@app.command("subcommand")
def new_subcommand(param: str = typer.Option(..., help="Parameter")):
    """Subcommand description."""
    output = get_output_controller()
    # Implementation
```

2. **Register in app.py**:
```python
from .commands.newcommand import app as newcommand_app
app.add_typer(newcommand_app, name="newcommand", help="New command functionality")
```

3. **Follow Output Patterns**:
- Use `get_output_controller()` for all output
- Support JSON mode via `output.is_json_mode`
- Use consistent parameter naming conventions

### Legacy Command Migration

1. **Identify Legacy Command**: Find in `main.py` argparse handling
2. **Create Typer Module**: Following standard patterns
3. **Add Delegation**: Route legacy calls to new Typer command
4. **Deprecation Warning**: Add warnings for legacy usage
5. **Remove Legacy**: After deprecation period

## Conclusion

The PraisonAI CLI Router Architecture successfully balances modern CLI design principles with practical backward compatibility requirements. The hybrid approach enables gradual modernization while maintaining a consistent, extensible, and performant command-line interface.

This architecture serves as a template for building sophisticated CLI applications that need to evolve over time while maintaining compatibility with existing users and workflows.