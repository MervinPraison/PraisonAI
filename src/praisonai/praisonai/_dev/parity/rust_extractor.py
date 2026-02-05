"""
Rust Feature Extractor for PraisonAI SDK.

Extracts features from praisonai-rust package using regex-based analysis.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class RustExport:
    """Information about a Rust export."""
    name: str
    source_file: str
    kind: str = 'export'  # 'struct', 'enum', 'fn', 'trait', 'type', 'const', 'macro'
    is_public: bool = True


@dataclass
class RustModule:
    """Information about a Rust module."""
    name: str
    exports: List[str] = field(default_factory=list)


@dataclass
class RustFeatures:
    """Extracted features from Rust SDK."""
    exports: List[RustExport] = field(default_factory=list)
    modules: Dict[str, RustModule] = field(default_factory=dict)
    cargo_features: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'exports': [e.name for e in self.exports],
            'modules': {
                name: mod.exports
                for name, mod in self.modules.items()
            },
            'cargoFeatures': self.cargo_features,
        }
    
    def get_export_names(self) -> Set[str]:
        """Get set of all export names."""
        return {e.name for e in self.exports}


class RustFeatureExtractor:
    """
    Extracts features from praisonai-rust package using regex analysis.
    
    This extractor parses Rust source files to find:
    - pub use statements (re-exports)
    - pub struct, pub enum, pub fn declarations
    - pub trait definitions
    - Cargo.toml feature flags
    
    It categorizes exports into modules based on their source paths.
    """
    
    # Module category mapping based on source paths
    MODULE_MAPPING = {
        'agent': ['agent'],
        'config': ['config'],
        'error': ['error'],
        'llm': ['llm'],
        'memory': ['memory'],
        'tools': ['tools'],
        'workflows': ['workflows'],
    }
    
    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize extractor with repository root path."""
        if repo_root is None:
            repo_root = self._find_repo_root()
        self.repo_root = Path(repo_root).resolve()
        self.rust_pkg = self.repo_root / "src" / "praisonai-rust" / "praisonai"
    
    def _find_repo_root(self) -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path("/Users/praison/praisonai-package")
    
    def extract(self) -> RustFeatures:
        """Extract all features from Rust SDK."""
        features = RustFeatures()
        
        # Extract from lib.rs (main entry point)
        lib_file = self.rust_pkg / "src" / "lib.rs"
        if lib_file.exists():
            self._extract_from_lib_rs(lib_file, features)
        
        # Extract Cargo features
        cargo_file = self.rust_pkg / "Cargo.toml"
        if cargo_file.exists():
            self._extract_cargo_features(cargo_file, features)
        
        # Scan module files for additional exports
        src_dir = self.rust_pkg / "src"
        if src_dir.exists():
            self._scan_module_files(src_dir, features)
        
        return features
    
    def _extract_from_lib_rs(self, lib_file: Path, features: RustFeatures) -> None:
        """Extract public exports from lib.rs."""
        try:
            with open(lib_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return
        
        # Parse "pub use" re-exports: pub use module::{Item1, Item2};
        # Pattern matches: pub use path::{items};
        pub_use_pattern = r"pub\s+use\s+([a-zA-Z_][a-zA-Z0-9_:]*)::\{([^}]+)\};"
        for match in re.finditer(pub_use_pattern, content):
            source_module = match.group(1)
            items_str = match.group(2)
            
            for item in self._parse_items(items_str):
                features.exports.append(RustExport(
                    name=item,
                    source_file=source_module,
                    kind=self._infer_kind(item),
                    is_public=True
                ))
                
                # Add to module
                module_name = self._categorize(source_module)
                if module_name not in features.modules:
                    features.modules[module_name] = RustModule(name=module_name)
                if item not in features.modules[module_name].exports:
                    features.modules[module_name].exports.append(item)
        
        # Parse single re-exports: pub use module::Item;
        single_use_pattern = r"pub\s+use\s+([a-zA-Z_][a-zA-Z0-9_:]+)::([a-zA-Z_][a-zA-Z0-9_]*);"
        for match in re.finditer(single_use_pattern, content):
            source_module = match.group(1)
            item = match.group(2)
            
            # Avoid duplicates from the braced pattern
            if not any(e.name == item for e in features.exports):
                features.exports.append(RustExport(
                    name=item,
                    source_file=source_module,
                    kind=self._infer_kind(item),
                    is_public=True
                ))
                
                module_name = self._categorize(source_module)
                if module_name not in features.modules:
                    features.modules[module_name] = RustModule(name=module_name)
                if item not in features.modules[module_name].exports:
                    features.modules[module_name].exports.append(item)
        
        # Parse declared modules: pub mod name;
        mod_pattern = r"pub\s+mod\s+([a-zA-Z_][a-zA-Z0-9_]*);"
        for match in re.finditer(mod_pattern, content):
            mod_name = match.group(1)
            if mod_name not in features.modules:
                features.modules[mod_name] = RustModule(name=mod_name)
    
    def _extract_cargo_features(self, cargo_file: Path, features: RustFeatures) -> None:
        """Extract feature flags from Cargo.toml."""
        try:
            with open(cargo_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError):
            return
        
        # Look for [features] section
        in_features_section = False
        for line in content.split('\n'):
            line = line.strip()
            if line == '[features]':
                in_features_section = True
                continue
            elif line.startswith('[') and in_features_section:
                break
            elif in_features_section and '=' in line:
                feature_name = line.split('=')[0].strip()
                if feature_name and not feature_name.startswith('#'):
                    features.cargo_features.append(feature_name)
    
    def _scan_module_files(self, src_dir: Path, features: RustFeatures) -> None:
        """Scan module files for public exports not in lib.rs."""
        existing_exports = {e.name for e in features.exports}
        
        for rs_file in src_dir.rglob("*.rs"):
            if rs_file.name == "lib.rs":
                continue
            
            try:
                with open(rs_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except (IOError, UnicodeDecodeError):
                continue
            
            rel_path = rs_file.relative_to(src_dir)
            module_name = rel_path.stem if rel_path.stem != "mod" else rel_path.parent.name
            
            # Extract pub struct
            for match in re.finditer(r"pub\s+struct\s+([A-Z][a-zA-Z0-9_]*)", content):
                name = match.group(1)
                if name not in existing_exports:
                    self._add_export(features, name, str(rel_path), 'struct', module_name)
                    existing_exports.add(name)
            
            # Extract pub enum
            for match in re.finditer(r"pub\s+enum\s+([A-Z][a-zA-Z0-9_]*)", content):
                name = match.group(1)
                if name not in existing_exports:
                    self._add_export(features, name, str(rel_path), 'enum', module_name)
                    existing_exports.add(name)
            
            # Extract pub trait
            for match in re.finditer(r"pub\s+trait\s+([A-Z][a-zA-Z0-9_]*)", content):
                name = match.group(1)
                if name not in existing_exports:
                    self._add_export(features, name, str(rel_path), 'trait', module_name)
                    existing_exports.add(name)
            
            # Extract pub fn (only top-level, not impl methods)
            for match in re.finditer(r"^pub\s+(?:async\s+)?fn\s+([a-z_][a-zA-Z0-9_]*)", content, re.MULTILINE):
                name = match.group(1)
                if name not in existing_exports and not name.startswith('_'):
                    self._add_export(features, name, str(rel_path), 'fn', module_name)
                    existing_exports.add(name)
    
    def _add_export(self, features: RustFeatures, name: str, source: str, kind: str, module_name: str) -> None:
        """Add an export to features."""
        features.exports.append(RustExport(
            name=name,
            source_file=source,
            kind=kind,
            is_public=True
        ))
        
        if module_name not in features.modules:
            features.modules[module_name] = RustModule(name=module_name)
        if name not in features.modules[module_name].exports:
            features.modules[module_name].exports.append(name)
    
    def _parse_items(self, items_str: str) -> List[str]:
        """Parse items from a comma-separated string in braces."""
        items = []
        for part in items_str.split(','):
            part = part.strip()
            if not part:
                continue
            # Handle 'Name as Alias' syntax
            if ' as ' in part:
                part = part.split(' as ')[1].strip()
            items.append(part)
        return items
    
    def _categorize(self, source_path: str) -> str:
        """Categorize an export based on its source path."""
        # Clean the path - remove leading :: or crate::
        clean_path = source_path.replace('crate::', '').strip(':')
        
        for module_name, patterns in self.MODULE_MAPPING.items():
            for pattern in patterns:
                if clean_path.startswith(pattern) or pattern in clean_path:
                    return module_name
        return 'core'
    
    def _infer_kind(self, name: str) -> str:
        """Infer the kind of export based on naming conventions."""
        if name[0].isupper():
            if name.endswith('Config') or name.endswith('Result'):
                return 'struct'
            if name.endswith('Error'):
                return 'enum'
            if name.endswith('Builder'):
                return 'struct'
            if name.endswith('Provider') or name.endswith('Adapter'):
                return 'trait'
            return 'struct'
        elif name.endswith('!'):
            return 'macro'
        else:
            return 'fn'
