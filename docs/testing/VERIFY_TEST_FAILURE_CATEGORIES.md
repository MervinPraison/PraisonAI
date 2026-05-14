# Verification notes for known pytest failure categories (May 2026)

These checks confirm whether failures are **real product bugs** or **stale tests / mocks**. Run from the repository root (`PraisonAI`).

## 1. Stale framework registry mock (`get_instance`)

```bash
PYTHONPATH=src/praisonai python3 -c "
from praisonai.framework_adapters.registry import FrameworkAdapterRegistry
print('FrameworkAdapterRegistry.get_instance exists:', hasattr(FrameworkAdapterRegistry, 'get_instance'))
from praisonai.framework_adapters.registry import get_default_registry
print('get_default_registry exists:', callable(get_default_registry))
"
```

**Expected:** `get_instance` is **False**; validators use `get_default_registry()` (see `praisonai/framework_adapters/validators.py`). Unit tests that patch `get_instance` are wrong and must patch `praisonai.framework_adapters.validators.get_default_registry` instead.

## 2. `execute_code` lazy export (`praisonaiagents.tools`)

```bash
PYTHONPATH=src/praisonai-agents python3 -c "
from praisonaiagents.tools import execute_code
print('execute_code:', execute_code)
"
```

**If this raises `ImportError`:** `TOOL_MAPPINGS` still maps `execute_code` to the `PythonTools` class factory while `execute_code` is a **module-level function** in `python_tools.py`. Fix: map `execute_code` with `class_name=None` and include `execute_code` in the direct-function allow-list in `praisonaiagents/tools/__init__.py`.

## 3. Bot `_BUILTIN_PLATFORMS` shape (lazy loaders)

```bash
PYTHONPATH=src/praisonai python3 -c "
from praisonai.bots._registry import _BUILTIN_PLATFORMS
v = _BUILTIN_PLATFORMS['agentmail']
print(type(v).__name__, 'callable:', callable(v))
"
```

**Expected:** `function` and `callable: True`. Tests asserting `("praisonai.bots.agentmail", "AgentMailBot")` tuples are **stale**; `resolve_adapter` / `get_platform_registry()` still resolve to the class at runtime.

## 4. aiui datastore default store patch target

```bash
PYTHONPATH=src/praisonai python3 -c "
import praisonai.ui._aiui_datastore as aiui_mod
import praisonaiagents.session as session_mod
print('get_hierarchical_session_store at aiui module level:', hasattr(aiui_mod, 'get_hierarchical_session_store'))
print('get_hierarchical_session_store in session module:', hasattr(session_mod, 'get_hierarchical_session_store'))
"
```

**Expected:** `False` at aiui level, `True` in session module. `PraisonAISessionDataStore` calls `get_hierarchical_session_store` from **`praisonaiagents.session`** inside `_build_impl_cls()`. Tests should patch `praisonaiagents.session.get_hierarchical_session_store` and reset `praisonai.ui._aiui_datastore._impl_cls` before constructing the adapter when the impl class was already cached.

## 5. Wrapper test env keys

```bash
PYTHONPATH=src/praisonai python3 -c "
import os
os.environ['OPENAI_API_KEY'] = 'my-real-key'
print('Before import, OPENAI_API_KEY:', os.environ.get('OPENAI_API_KEY'))
# Simulating conftest behavior for non-real tests
test_keys = {'OPENAI_API_KEY': 'test-key'}
for key, value in test_keys.items():
    os.environ[key] = value  # Current implementation: unconditional overwrite
print('After conftest logic, OPENAI_API_KEY:', os.environ.get('OPENAI_API_KEY'))
"
```

**Current behavior:** Always `test-key` (unconditional overwrite). **Expected behavior:** The autouse fixture should only set placeholders when the variable is **unset or empty**, preserving real keys for mixed testing approaches (integration/live paths unchanged).
