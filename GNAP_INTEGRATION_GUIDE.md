# GNAP Integration Guide for PraisonAI-Tools

This guide shows how to integrate the GNAP plugin implementation into the PraisonAI-Tools repository.

## Files to Copy

Copy these files from the current implementation to PraisonAI-Tools:

### 1. Plugin Directory Structure

```
PraisonAI-Tools/praisonai_tools/plugins/gnap/
├── __init__.py          # From: gnap_plugin_init.py
├── gnap_plugin.py       # From: gnap_plugin.py  
├── storage.py           # From: gnap_storage.py
├── tools.py             # From: gnap_tools.py
└── tests/
    ├── test_gnap_unit.py     # From: test_gnap_unit.py
    └── test_gnap_agentic.py  # From: test_gnap_agentic.py
```

### 2. Update pyproject.toml

Replace the existing pyproject.toml with the updated version that includes:

```toml
[project.optional-dependencies]
gnap = [
    "GitPython>=3.1.0",
]

[project.entry-points."praisonaiagents.plugins"]
gnap = "praisonai_tools.plugins.gnap:get_gnap_plugin"

[project.entry-points."praisonaiagents.storage_backends"] 
gnap = "praisonai_tools.plugins.gnap:get_gnap_backend"
```

Version bump: `0.2.24` → `0.2.25`

## Installation Commands

After integration, users can install GNAP with:

```bash
# Install with GNAP support
pip install praisonai-tools[gnap]

# Or upgrade existing installation
pip install --upgrade praisonai-tools[gnap]
```

## Usage Examples

### As Storage Backend
```python
from praisonai_tools.plugins.gnap import GNAPStorageBackend

backend = GNAPStorageBackend(repo_path="./my_project")
backend.save("task_123", {"status": "completed"})
task = backend.load("task_123")
```

### As Agent Tools
```python
from praisonaiagents import Agent
from praisonai_tools.plugins.gnap import gnap_save_state, gnap_load_state

agent = Agent(
    name="persistent_agent",
    tools=[gnap_save_state, gnap_load_state]
)
```

### Via Entry Points
```python
# Plugin discovery
from praisonaiagents.plugins import get_plugin
gnap_plugin = get_plugin("gnap")

# Storage backend discovery  
from praisonaiagents.storage.backends import get_backend
gnap_backend = get_backend("gnap", repo_path="./project")
```

## Testing Integration

Run tests to verify integration:

```bash
cd PraisonAI-Tools

# Unit tests
python -m pytest praisonai_tools/plugins/gnap/tests/test_gnap_unit.py -v

# Agentic tests (requires LLM access)
python -m pytest praisonai_tools/plugins/gnap/tests/test_gnap_agentic.py -v

# All tests
python -m pytest praisonai_tools/plugins/gnap/tests/ -v
```

## File Modifications Needed

### 1. Fix Import Paths

Update relative imports in the copied files:

#### `__init__.py`
```python
from .gnap_plugin import GnapPlugin
from .storage import GNAPStorageBackend  
from .tools import gnap_save_state, gnap_load_state, gnap_list_tasks, gnap_commit
```

#### `storage.py`
```python
from .gnap_plugin import GnapPlugin
```

#### `tools.py`  
```python
from .gnap_plugin import GnapPlugin
```

### 2. Update Test Imports

Fix test imports to use the new module structure:

```python
# In test files, change:
from gnap_plugin import GnapPlugin
from gnap_storage import GNAPStorageBackend

# To:
from praisonai_tools.plugins.gnap import GnapPlugin, GNAPStorageBackend
```

## Verification Checklist

After integration, verify:

- [ ] `pip install praisonai-tools[gnap]` installs GitPython
- [ ] Entry points are discoverable: `get_plugin("gnap")`  
- [ ] Storage backend works: `get_backend("gnap")`
- [ ] Tools are importable: `from praisonai_tools.plugins.gnap import gnap_save_state`
- [ ] Unit tests pass
- [ ] Agentic tests pass (with LLM access)
- [ ] No import errors or missing dependencies

## Architecture Compliance

This implementation follows all AGENTS.md requirements:

✅ **Correct Routing**: External tool integration in PraisonAI-Tools  
✅ **No Duplication**: Extends existing storage with git persistence  
✅ **Protocol Compliance**: Implements StorageBackendProtocol + PluginProtocol  
✅ **Lazy Loading**: GitPython imported only when needed  
✅ **Optional Dependencies**: `pip install praisonai-tools[gnap]`  
✅ **Real Agentic Tests**: Agent calls LLM end-to-end  
✅ **Thread Safety**: Concurrent multi-agent support  

## Support and Troubleshooting

For issues:
1. Check GitPython installation: `pip list | grep GitPython`  
2. Verify git repository: `git status` in repo_path
3. Check environment variables: `GNAP_REPO_PATH`, `GNAP_AUTO_COMMIT`
4. Review git history: `git log --oneline .gnap/`

The GNAP plugin is now ready for integration into PraisonAI-Tools!