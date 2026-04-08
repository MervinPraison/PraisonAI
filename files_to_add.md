# Files to Add to PraisonAI-Tools Repository

## Directory Structure to Create:
```
praisonai_tools/
└── gnap/
    ├── __init__.py
    └── storage_backend.py
```

## File Contents:

### 1. praisonai_tools/gnap/__init__.py
```python
# Content from gnap_module/__init__.py
```

### 2. praisonai_tools/gnap/storage_backend.py 
```python
# Content from gnap_module/storage_backend.py
```

### 3. pyproject.toml (UPDATE EXISTING)
Add to existing pyproject.toml:

```toml
# Bump version
version = "0.2.25"

# Add keywords
keywords = ["ai", "agents", "tools", "praisonai", "custom-tools", "plugin", "gnap", "git-native"]

# Add entry point
[project.entry-points."praisonaiagents.storage.backends"]
gnap = "praisonai_tools.gnap:get_gnap_backend"

# Add optional dependency
[project.optional-dependencies]
gnap = [
    "GitPython>=3.1.0",
]
```

### 4. README.md (ADD SECTION)
Add GNAP section to existing README or create separate docs/gnap.md

## Test Files (for CI/CD):

### tests/gnap/
```
tests/
└── gnap/
    ├── __init__.py
    ├── test_gnap_storage.py
    └── test_gnap_integration.py
```

## Documentation Files:

### docs/gnap.md
Complete documentation for GNAP backend usage.