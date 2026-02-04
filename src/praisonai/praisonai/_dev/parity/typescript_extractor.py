"""
TypeScript Feature Extractor for PraisonAI SDK.

Extracts features from praisonai-ts package using regex-based analysis.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class TypeScriptExport:
    """Information about a TypeScript export."""
    name: str
    source_file: str
    is_type: bool = False
    kind: str = 'export'  # 'class', 'function', 'type', 'const'


@dataclass
class TypeScriptModule:
    """Information about a TypeScript module."""
    name: str
    exports: List[str] = field(default_factory=list)


@dataclass
class TypeScriptFeatures:
    """Extracted features from TypeScript SDK."""
    exports: List[TypeScriptExport] = field(default_factory=list)
    modules: Dict[str, TypeScriptModule] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'exports': [e.name for e in self.exports if not e.is_type],
            'modules': {
                name: mod.exports
                for name, mod in self.modules.items()
            },
        }
    
    def get_export_names(self) -> Set[str]:
        """Get set of all export names."""
        return {e.name for e in self.exports}


class TypeScriptFeatureExtractor:
    """
    Extracts features from praisonai-ts package using regex analysis.
    
    This extractor parses the index.ts file to find:
    - export { Name } from './path' statements
    - export type { Name } from './path' statements
    - export * from './path' statements
    
    It categorizes exports into modules based on their source paths.
    """
    
    # Module category mapping based on source paths
    MODULE_MAPPING = {
        'agent': ['./agent'],
        'auto': ['./auto'],
        'task': ['./task'],
        'tools': ['./tools'],
        'llm': ['./llm'],
        'memory': ['./memory'],
        'knowledge': ['./knowledge'],
        'db': ['./db'],
        'session': ['./session'],
        'workflows': ['./workflows'],
        'guardrails': ['./guardrails'],
        'eval': ['./eval'],
        'skills': ['./skills'],
        'telemetry': ['./telemetry'],
        'context': ['./context'],
        'observability': ['./observability'],
        'planning': ['./planning'],
        'cache': ['./cache'],
        'events': ['./events'],
        'hooks': ['./hooks'],
        'mcp': ['./mcp'],
        'integrations': ['./integrations'],
        'ai': ['./ai'],
        'os': ['./os'],
        'process': ['./process'],
        'cli': ['./cli'],
        'utils': ['./utils'],
    }
    
    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize extractor with repository root path."""
        if repo_root is None:
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()
        self.ts_pkg = self.repo_root / "src" / "praisonai-ts"
    
    def _find_repo_root(self) -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path("/Users/praison/praisonai-package")
    
    def extract(self) -> TypeScriptFeatures:
        """Extract all features from TypeScript SDK."""
        features = TypeScriptFeatures()
        
        index_file = self.ts_pkg / "src" / "index.ts"
        if not index_file.exists():
            return features
        
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return features
        
        # Parse regular exports: export { Name1, Name2 } from './path'
        export_pattern = r"export\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]"
        for match in re.finditer(export_pattern, content):
            names_str = match.group(1)
            source = match.group(2)
            
            for name in self._parse_export_names(names_str):
                if name.startswith('type '):
                    # Handle inline type exports: export { type Name }
                    actual_name = name[5:].strip()
                    features.exports.append(TypeScriptExport(
                        name=actual_name,
                        source_file=source,
                        is_type=True,
                        kind='type'
                    ))
                else:
                    features.exports.append(TypeScriptExport(
                        name=name,
                        source_file=source,
                        is_type=False,
                        kind=self._infer_kind(name)
                    ))
                
                # Add to module
                module_name = self._categorize(source)
                if module_name not in features.modules:
                    features.modules[module_name] = TypeScriptModule(name=module_name)
                features.modules[module_name].exports.append(name.replace('type ', ''))
        
        # Parse type exports: export type { Name1, Name2 } from './path'
        type_export_pattern = r"export\s+type\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]"
        for match in re.finditer(type_export_pattern, content):
            names_str = match.group(1)
            source = match.group(2)
            
            for name in self._parse_export_names(names_str):
                features.exports.append(TypeScriptExport(
                    name=name,
                    source_file=source,
                    is_type=True,
                    kind='type'
                ))
                
                # Add to module
                module_name = self._categorize(source)
                if module_name not in features.modules:
                    features.modules[module_name] = TypeScriptModule(name=module_name)
                if name not in features.modules[module_name].exports:
                    features.modules[module_name].exports.append(name)
        
        return features
    
    def _parse_export_names(self, names_str: str) -> List[str]:
        """Parse export names from a comma-separated string."""
        names = []
        for part in names_str.split(','):
            part = part.strip()
            if not part:
                continue
            # Handle 'Name as Alias' syntax
            if ' as ' in part:
                part = part.split(' as ')[1].strip()
            names.append(part)
        return names
    
    def _categorize(self, source_path: str) -> str:
        """Categorize an export based on its source path."""
        for module_name, patterns in self.MODULE_MAPPING.items():
            for pattern in patterns:
                if source_path.startswith(pattern):
                    return module_name
        return 'other'
    
    def _infer_kind(self, name: str) -> str:
        """Infer the kind of export based on naming conventions."""
        if name[0].isupper():
            if name.endswith('Config') or name.endswith('Result') or name.endswith('Error'):
                return 'type'
            if name.endswith('Provider') or name.endswith('Adapter'):
                return 'class'
            return 'class'
        elif name.startswith('create') or name.startswith('get') or name.startswith('use'):
            return 'function'
        else:
            return 'function'
