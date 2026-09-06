"""
Python Feature Extractor for PraisonAI SDK.

Extracts features from praisonaiagents package using AST analysis.
This is the source of truth for feature parity tracking.
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ._paths import find_repo_root


@dataclass
class PythonExport:
    """Information about a Python export."""
    name: str
    module_path: str
    kind: str  # 'class', 'function', 'constant', 'type'
    category: str = 'other'  # agent, tool, workflow, memory, etc.


@dataclass
class PythonModule:
    """Information about a Python module."""
    name: str
    exports: List[str] = field(default_factory=list)


@dataclass
class PythonFeatures:
    """Extracted features from Python SDK."""
    exports: List[PythonExport] = field(default_factory=list)
    modules: Dict[str, PythonModule] = field(default_factory=dict)
    cli_features: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'exports': [e.name for e in self.exports],
            'modules': {
                name: {'exports': mod.exports}
                for name, mod in self.modules.items()
            },
            'cliFeatures': self.cli_features,
        }


class PythonFeatureExtractor:
    """
    Extracts features from praisonaiagents package using AST analysis.
    
    This extractor parses the __init__.py file to find:
    - ``_LAZY_IMPORTS`` dictionary entries, including later
      ``_LAZY_IMPORTS.update({...})`` calls
    - ``__all__`` exports
    - direct top-level imports -- ``from . import X``,
      ``from .module import Y as Z``, ``from praisonaiagents.m import Y``

    A direct import is skipped when the bound name is private (``_x``) or when
    it comes from a private submodule (``from ._lazy import ..``): those are
    internal plumbing, not public surface. Imports of stdlib or third-party
    modules are not part of this SDK's surface and are skipped too.

    It categorizes exports into modules based on their import paths.

    Every mechanism named above is implemented. Anything that looks like one
    but cannot be read -- a ``_LAZY_IMPORTS.update`` whose argument is not a
    literal dict, for instance -- raises instead of silently contributing
    nothing, because a partial loss here shows up downstream as parity.
    """
    
    # Category mapping based on module paths
    CATEGORY_MAPPING = {
        'agent': ['agent.agent', 'agent.image_agent', 'agent.video_agent', 
                  'agent.audio_agent', 'agent.ocr_agent', 'agent.context_agent',
                  'agent.deep_research_agent', 'agent.query_rewriter_agent',
                  'agent.prompt_expander_agent', 'agent.vision_agent',
                  'agent.embedding_agent', 'agent.realtime_agent', 'agent.code_agent',
                  'agent.handoff'],
        'agents': ['agents.agents', 'agents.autoagents', 'agents.auto_rag_agent'],
        'task': ['task.task'],
        'tools': ['tools.tools', 'tools.base', 'tools.decorator', 'tools.registry'],
        'llm': ['llm.llm', 'llm.failover'],
        'memory': ['memory.memory'],
        'knowledge': ['knowledge.knowledge', 'knowledge.chunking'],
        'db': ['db'],
        'obs': ['obs'],
        'mcp': ['mcp.mcp'],
        'workflows': ['workflows'],
        'guardrails': ['guardrails'],
        'eval': ['eval'],
        'skills': ['skills'],
        'telemetry': ['telemetry'],
        'context': ['context.fast', 'context.manager', 'context.models'],
        'session': ['session'],
        'ui': ['ui.agui', 'ui.a2a', 'ui.a2ui'],
        'rag': ['rag'],
        'planning': ['planning'],
        'config': ['config.feature_configs', 'config.param_resolver', 
                   'config.presets', 'config.parse_utils', 'config.loader'],
        'trace': ['trace'],
        'plugins': ['plugins'],
        'gateway': ['gateway.protocols', 'gateway.config'],
        'bots': ['bots.protocols', 'bots.config'],
        'sandbox': ['sandbox.protocols', 'sandbox.config'],
        'app': ['app.protocols', 'app.config', 'app'],
        'embedding': ['embedding.embed', 'embedding.result', 'embedding.dimensions'],
        'conditions': ['conditions.protocols', 'conditions.evaluator'],
        'main': ['main'],
        'flow_display': ['flow_display'],
    }
    
    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize extractor with repository root path."""
        if repo_root is None:
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()
        self.agents_pkg = self.repo_root / "src" / "praisonai-agents" / "praisonaiagents"
        self.wrapper_pkg = self.repo_root / "src" / "praisonai" / "praisonai"
    
    def _find_repo_root(self) -> Path:
        """Find the monorepo root (see ``_paths.find_repo_root``)."""
        return find_repo_root()
    
    def extract(self) -> PythonFeatures:
        """Extract all features from Python SDK."""
        features = PythonFeatures()
        
        # Extract from praisonaiagents __init__.py
        init_file = self.agents_pkg / "__init__.py"
        if init_file.exists():
            lazy_imports = self._extract_lazy_imports(init_file)
            all_exports = self._extract_all_exports(init_file)
            direct_imports = self._extract_direct_imports(init_file)

            # Combine lazy imports, direct imports and __all__ exports
            all_names = set(lazy_imports) | set(direct_imports) | all_exports

            for name in sorted(all_names):
                if name in lazy_imports:
                    module_path, _ = lazy_imports[name]
                    category = self._categorize(module_path)
                elif name in direct_imports:
                    module_path = direct_imports[name]
                    category = self._categorize(module_path)
                else:
                    module_path = 'praisonaiagents'
                    category = 'other'
                kind = self._infer_kind(name)
                
                features.exports.append(PythonExport(
                    name=name,
                    module_path=module_path,
                    kind=kind,
                    category=category
                ))
                
                # Add to module
                if category not in features.modules:
                    features.modules[category] = PythonModule(name=category)
                features.modules[category].exports.append(name)
        
        # Extract CLI features from wrapper
        features.cli_features = self._extract_cli_features()
        
        return features
    
    def _extract_lazy_imports(self, init_file: Path) -> Dict[str, Tuple[str, str]]:
        """Extract _LAZY_IMPORTS dictionary from __init__.py."""
        lazy_imports: Dict[str, Tuple[str, str]] = {}
        
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return lazy_imports
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '_LAZY_IMPORTS':
                        if isinstance(node.value, ast.Dict):
                            entries = self._read_lazy_dict(node.value)
                            if entries is not None:
                                lazy_imports.update(entries)
            elif self._is_lazy_update(node):
                # `_LAZY_IMPORTS.update({...})` adds public names just like the
                # literal above; ignoring it lost them silently.
                entries = (
                    self._read_lazy_dict(node.args[0])
                    if len(node.args) == 1 and not node.keywords
                    and isinstance(node.args[0], ast.Dict)
                    else None
                )
                if entries is None:
                    raise RuntimeError(
                        f"{init_file}:{getattr(node, 'lineno', '?')}: cannot read "
                        f"this _LAZY_IMPORTS.update(...) call. Only a literal dict "
                        f"of 'Name': ('module', 'attr') entries is supported. "
                        f"Refusing to report parity for a public surface this "
                        f"extractor cannot see."
                    )
                lazy_imports.update(entries)

        return lazy_imports

    @staticmethod
    def _is_lazy_update(node: ast.AST) -> bool:
        """True for a ``_LAZY_IMPORTS.update(..)`` call node."""
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'update'
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == '_LAZY_IMPORTS'
        )

    @staticmethod
    def _read_lazy_dict(node: ast.Dict) -> Optional[Dict[str, Tuple[str, str]]]:
        """Read a ``{'Name': ('module', 'attr')}`` literal, or None if it is not one."""
        entries: Dict[str, Tuple[str, str]] = {}
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                return None
            if not (isinstance(value, ast.Tuple) and len(value.elts) >= 2):
                return None
            module_elt, attr_elt = value.elts[0], value.elts[1]
            if not (isinstance(module_elt, ast.Constant)
                    and isinstance(module_elt.value, str)
                    and isinstance(attr_elt, ast.Constant)
                    and isinstance(attr_elt.value, str)):
                return None
            entries[key.value] = (module_elt.value, attr_elt.value)
        return entries

    def _extract_direct_imports(self, init_file: Path) -> Dict[str, str]:
        """Extract top-level ``from ... import ...`` bindings from __init__.py.

        These are public exports added the ordinary way -- ``praisonaiagents.X``
        resolves to them with no ``__getattr__`` involved -- and they were
        invisible to this extractor, so adding one closed no gap and raised no
        alarm.

        Returns a mapping of bound name -> module path it came from.
        """
        direct: Dict[str, str] = {}

        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return direct

        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ''
            if node.level:
                # relative: `from . import X` / `from .agent.agent import Y`
                base = f"praisonaiagents.{module}" if module else "praisonaiagents"
            elif module == 'praisonaiagents' or module.startswith('praisonaiagents.'):
                base = module
            else:
                continue  # stdlib / third-party: not this SDK's surface
            if any(part.startswith('_') for part in base.split('.')[1:]):
                continue  # private submodule -> internal plumbing

            for alias in node.names:
                name = alias.asname or alias.name
                if alias.name == '*' or name.startswith('_') or alias.name.startswith('_'):
                    continue
                # `from . import workflows` binds the submodule itself
                direct[name] = base if module else f"praisonaiagents.{alias.name}"

        return direct
    
    def _extract_all_exports(self, init_file: Path) -> Set[str]:
        """Extract __all__ list from __init__.py."""
        all_exports: Set[str] = set()
        
        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            return all_exports
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_exports.add(elt.value)
        
        return all_exports
    
    def _categorize(self, module_path: str) -> str:
        """Categorize an export based on its module path."""
        # Remove 'praisonaiagents.' prefix
        if module_path.startswith('praisonaiagents.'):
            module_path = module_path[len('praisonaiagents.'):]
        
        for category, patterns in self.CATEGORY_MAPPING.items():
            for pattern in patterns:
                if module_path.startswith(pattern) or module_path == pattern:
                    return category
        
        return 'other'
    
    def _infer_kind(self, name: str) -> str:
        """Infer the kind of export based on naming conventions."""
        # Check for all-uppercase constants first (e.g., RECOMMENDED_PROMPT_PREFIX)
        if name.isupper() or (name[0].isupper() and '_' in name and name == name.upper()):
            return 'constant'
        if name[0].isupper():
            if name.endswith('Config') or name.endswith('Result') or name.endswith('Error'):
                return 'type'
            if name.endswith('Protocol'):
                return 'protocol'
            return 'class'
        elif name.startswith('get_') or name.startswith('create_') or name.startswith('enable_'):
            return 'function'
        else:
            return 'function'
    
    def _extract_cli_features(self) -> List[str]:
        """Extract CLI feature names from wrapper package."""
        cli_features = []
        features_dir = self.wrapper_pkg / "cli" / "features"
        
        if features_dir.exists():
            for py_file in sorted(features_dir.glob("*.py")):
                if py_file.name.startswith('_'):
                    continue
                # Convert filename to feature name
                feature_name = py_file.stem
                cli_features.append(feature_name)
        
        return cli_features
