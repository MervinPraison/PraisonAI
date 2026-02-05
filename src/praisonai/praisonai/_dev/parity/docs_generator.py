"""
Documentation Parity Generator for PraisonAI SDKs.

Compares each SDK's implemented features against its documentation.
- Python: praisonaiagents features vs docs/concepts, docs/features, etc.
- Rust: praisonai-rust features vs docs/rust/
- TypeScript: praisonai-ts features vs docs/js/

Features are GROUPED by module/category, not listed individually.
This is NOT a cross-SDK comparison. Each SDK is compared against its own docs.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

from .docs_extractor import DocsFeatures, DocsTopic, BaseDocsExtractor
from .ts_docs_extractor import TypeScriptDocsExtractor
from .rust_docs_extractor import RustDocsExtractor
from .python_docs_extractor import PythonDocsExtractor
from .topic_normalizer import normalize_topic

# Import feature extractors for SDK features
from .python_extractor import PythonFeatureExtractor
from .rust_extractor import RustFeatureExtractor
from .typescript_extractor import TypeScriptFeatureExtractor


# Feature grouping categories - maps prefixes to category names
FEATURE_CATEGORIES = {
    # Core Agent Features
    'a2a': 'Agent-to-Agent (A2A)',
    'a2u': 'Agent-to-User (A2U)',
    'agent': 'Agent',
    'agui': 'AGUI',  # Dedicated feature, not a UI
    'auto': 'Auto Generation',
    'autonomy': 'Autonomy',
    'handoff': 'Handoffs',
    'routing': 'Routing',
    'team': 'Teams',
    'flow': 'Flow',
    
    # UI & Display
    'bot': 'Bots',
    'chat': 'Chat',
    'display': 'Display',
    'realtime': 'Realtime',
    
    # AI & LLM (including specific providers)
    'ai': 'AI SDK',
    'llm': 'LLM',
    'provider': 'Providers',
    'openai': 'Providers',
    'anthropic': 'Providers',
    'groq': 'Providers',
    'ollama': 'Providers',
    'mistral': 'Providers',
    'cohere': 'Providers',
    'deepseek': 'Providers',
    'together': 'Providers',
    'openrouter': 'Providers',
    'google': 'Providers',
    'gemini': 'Providers',
    'aws': 'Providers',
    'bedrock': 'Providers',
    'embed': 'Embeddings',
    'vision': 'Vision',
    'ocr': 'OCR',
    'image': 'Image',
    'audio': 'Audio',
    'video': 'Video',
    'voice': 'Voice',
    
    # Execution & Control
    'approval': 'Approval',
    'callback': 'Callbacks',
    'condition': 'Conditions',
    'execution': 'Execution',
    'loop': 'Loops',
    'ralph': 'Loops',  # ralph-loops.mdx docs
    'parallel': 'Parallel Execution',
    'pipeline': 'Workflows',  # Pipelines are same as workflows
    'repeat': 'Loops',
    'sandbox': 'Sandbox',
    
    # Memory & Knowledge
    'cache': 'Caching',
    'chunking': 'Chunking',
    'context': 'Context Management',
    'document': 'Documents',
    'knowledge': 'Knowledge',
    'memory': 'Memory',
    'rag': 'RAG',
    'retrieval': 'Retrieval',
    
    # Database & Storage (including specific databases)
    'db': 'Database',
    'database': 'Database',
    'postgres': 'Database',
    'postgresql': 'Database',
    'pgvector': 'Database',
    'mysql': 'Database',
    'sqlite': 'Database',
    'mongodb': 'Database',
    'mongo': 'Database',
    'redis': 'Database',
    'cassandra': 'Database',
    'dynamodb': 'Database',
    'cosmosdb': 'Database',
    'firestore': 'Database',
    'couchbase': 'Database',
    'clickhouse': 'Database',
    'neon': 'Database',
    'supabase': 'Database',
    'surrealdb': 'Database',
    'json': 'Database',
    'lancedb': 'Vector Store',
    'chroma': 'Vector Store',
    'chromadb': 'Vector Store',
    'pinecone': 'Vector Store',
    'qdrant': 'Vector Store',
    'milvus': 'Vector Store',
    'weaviate': 'Vector Store',
    'faiss': 'Vector Store',
    'vector': 'Vector Store',
    'gcs': 'Storage',
    's3': 'Storage',
    'storage': 'Storage',
    
    # Tools & Extensions
    'guardrail': 'Guardrails',
    'hook': 'Hooks',
    'mcp': 'MCP',
    'middleware': 'Middleware',
    'plugin': 'Plugins',
    'skill': 'Skills',
    'tool': 'Tools',
    
    # Planning & Evaluation
    'criteria': 'Criteria',
    'eval': 'Evaluation',
    'optimizer': 'Optimizer',
    'plan': 'Planning',
    'planning': 'Planning',
    'reflection': 'Reflection',
    
    # Infrastructure
    'cli': 'CLI',
    'config': 'Configuration',
    'deploy': 'Deployment',
    'event': 'Events',
    'failover': 'Failover',
    'gateway': 'Gateway',
    'job': 'Jobs',
    'observability': 'Observability',
    'process': 'Process',
    'pubsub': 'PubSub',
    'scheduler': 'Scheduler',
    'security': 'Security',
    'session': 'Sessions',
    'telemetry': 'Telemetry',
    'trace': 'Tracing',
    'tracing': 'Tracing',
    
    # Content & Output
    'code': 'Code Execution',
    'deep-research': 'Deep Research',
    'file': 'Files',
    'output': 'Output',
    'prompt': 'Prompts',
    'query': 'Query',
    'stream': 'Streaming',
    'task': 'Tasks',
    'template': 'Templates',
    'token': 'Token Management',
    'web': 'Web',
    'workflow': 'Workflows',
    
    # Additional
    'budget': 'Budget',
    'citation': 'Citations',
    'resource': 'Sandbox',  # ResourceLimits is part of sandbox execution
}


# Minimum lines for a doc to be considered "real" (not a stub)
MIN_DOC_LINES = 50


@dataclass
class CategoryParity:
    """Parity information for a feature category."""
    name: str
    display_name: str
    has_features: bool = True
    has_docs: bool = False
    feature_count: int = 0
    doc_count: int = 0
    doc_lines: int = 0  # Total lines of documentation for this category
    is_stub: bool = False  # True if docs exist but are < MIN_DOC_LINES (stubs)


@dataclass
class DocsParitySummary:
    """Summary statistics for documentation parity."""
    total_categories: int = 0
    documented_categories: int = 0
    undocumented_categories: int = 0
    parity_percent: float = 0.0


class DocsParityGenerator:
    """
    Generates documentation parity tracker files.
    
    Compares each SDK's implemented features against its own documentation.
    Features are grouped by module/category for cleaner reporting.
    """
    
    def __init__(
        self,
        docs_root: Optional[Path] = None,
        repo_root: Optional[Path] = None
    ):
        """Initialize generator with documentation and repository root paths."""
        if docs_root is None:
            docs_root = Path("/Users/praison/PraisonAIDocs/docs")
        if repo_root is None:
            repo_root = self._find_repo_root()
        
        self.docs_root = Path(docs_root).resolve()
        self.repo_root = Path(repo_root).resolve()
        
        # Documentation extractors
        self.python_docs_extractor = PythonDocsExtractor(self.docs_root)
        self.ts_docs_extractor = TypeScriptDocsExtractor(self.docs_root)
        self.rust_docs_extractor = RustDocsExtractor(self.docs_root)
        
        # Feature extractors (from existing parity module)
        self.python_feature_extractor = PythonFeatureExtractor(self.repo_root)
        self.ts_feature_extractor = TypeScriptFeatureExtractor(self.repo_root)
        self.rust_feature_extractor = RustFeatureExtractor(self.repo_root)
        
        # Output paths
        self.python_md_output = self.repo_root / "src" / "praisonai-agents" / "DOCS_PARITY.md"
        self.ts_md_output = self.repo_root / "src" / "praisonai-ts" / "DOCS_PARITY.md"
        self.rust_md_output = self.repo_root / "src" / "praisonai-rust" / "DOCS_PARITY.md"
    
    def _find_repo_root(self) -> Path:
        """Find repository root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path("/Users/praison/praisonai-package")
    
    def _categorize_feature(self, feature_name: str) -> str:
        """Map a feature name to its category."""
        normalized = normalize_topic(feature_name)
        
        # Try to find a matching prefix
        for prefix in sorted(FEATURE_CATEGORIES.keys(), key=len, reverse=True):
            if normalized.startswith(prefix):
                return prefix
        
        # Special handling for compound names
        if 'agent' in normalized and 'team' in normalized:
            return 'team'
        if 'agent' in normalized and 'flow' in normalized:
            return 'flow'
        if 'agent' in normalized:
            return 'agent'
        
        return 'other'
    
    def _categorize_doc(self, doc_name: str) -> str:
        """Map a doc topic name to its category."""
        normalized = normalize_topic(doc_name)
        
        # Direct matches first
        if normalized in FEATURE_CATEGORIES:
            return normalized
        
        # Try to find a matching prefix
        for prefix in sorted(FEATURE_CATEGORIES.keys(), key=len, reverse=True):
            if normalized.startswith(prefix):
                return prefix
        
        # Special cases
        if 'agent' in normalized and 'team' in normalized:
            return 'team'
        if 'agent' in normalized and 'flow' in normalized:
            return 'flow'
        if normalized in ('agent', 'agents'):
            return 'agent'
        
        return 'other'
    
    def _group_features(self, exports: list) -> Dict[str, List[str]]:
        """Group feature exports by category."""
        groups: Dict[str, List[str]] = {}
        
        for export in exports:
            name = export.name if hasattr(export, 'name') else str(export)
            category = self._categorize_feature(name)
            if category not in groups:
                groups[category] = []
            groups[category].append(name)
        
        return groups
    
    def _group_docs(self, docs: DocsFeatures) -> Dict[str, tuple[List[str], int]]:
        """Group documentation topics by category, returning names and total lines."""
        groups: Dict[str, tuple[List[str], int]] = {}
        
        for topic in docs.topics:
            # First try to categorize by filename
            category = self._categorize_doc(topic.name)
            # If filename doesn't match, try the folder (topic.category)
            if category == 'other' and topic.category:
                folder_category = self._categorize_doc(topic.category)
                if folder_category != 'other':
                    category = folder_category
            
            if category not in groups:
                groups[category] = ([], 0)
            names, lines = groups[category]
            names.append(topic.name)
            groups[category] = (names, lines + topic.line_count)
        
        return groups
    
    def _calculate_category_parity(
        self,
        feature_groups: Dict[str, List[str]],
        doc_groups: Dict[str, tuple[List[str], int]]
    ) -> tuple[DocsParitySummary, List[CategoryParity]]:
        """Calculate parity at category level, grouped by display name."""
        # Convert prefix-based groups to display-name-based groups
        def group_features_by_display_name(groups: Dict[str, List[str]]) -> Dict[str, List[str]]:
            result: Dict[str, List[str]] = {}
            for prefix, items in groups.items():
                if prefix == 'other':
                    continue
                display_name = FEATURE_CATEGORIES.get(prefix, prefix.title())
                if display_name not in result:
                    result[display_name] = []
                result[display_name].extend(items)
            return result
        
        def group_docs_by_display_name(groups: Dict[str, tuple[List[str], int]]) -> Dict[str, tuple[List[str], int]]:
            result: Dict[str, tuple[List[str], int]] = {}
            for prefix, (items, lines) in groups.items():
                if prefix == 'other':
                    continue
                display_name = FEATURE_CATEGORIES.get(prefix, prefix.title())
                if display_name not in result:
                    result[display_name] = ([], 0)
                existing_names, existing_lines = result[display_name]
                existing_names.extend(items)
                result[display_name] = (existing_names, existing_lines + lines)
            return result
        
        feature_by_display = group_features_by_display_name(feature_groups)
        doc_by_display = group_docs_by_display_name(doc_groups)
        
        all_display_names = set(feature_by_display.keys()) | set(doc_by_display.keys())
        
        categories = []
        documented = 0
        
        for display_name in sorted(all_display_names):
            has_features = display_name in feature_by_display
            has_docs = display_name in doc_by_display
            
            doc_names, doc_lines = doc_by_display.get(display_name, ([], 0))
            
            # Check if docs are just stubs (< MIN_DOC_LINES)
            is_stub = has_docs and doc_lines < MIN_DOC_LINES
            
            parity = CategoryParity(
                name=display_name.lower().replace(' ', '-').replace('(', '').replace(')', ''),
                display_name=display_name,
                has_features=has_features,
                has_docs=has_docs,
                feature_count=len(feature_by_display.get(display_name, [])),
                doc_count=len(doc_names),
                doc_lines=doc_lines,
                is_stub=is_stub,
            )
            categories.append(parity)
            
            # Only count as documented if has real docs (not stubs)
            if has_features and has_docs and not is_stub:
                documented += 1
        
        # Categories that have features
        feature_categories = [c for c in categories if c.has_features]
        total = len(feature_categories)
        parity_percent = round((documented / total * 100) if total > 0 else 0, 1)
        
        summary = DocsParitySummary(
            total_categories=total,
            documented_categories=documented,
            undocumented_categories=total - documented,
            parity_percent=parity_percent,
        )
        
        return summary, categories
    
    def generate_python_parity(self) -> Dict:
        """Generate Python documentation parity data."""
        # Get Python features and docs
        python_features = self.python_feature_extractor.extract()
        docs = self.python_docs_extractor.extract()
        
        # Group by category
        feature_groups = self._group_features(python_features.exports)
        doc_groups = self._group_docs(docs)
        
        # Calculate parity
        summary, categories = self._calculate_category_parity(feature_groups, doc_groups)
        
        # Build category lists - stubs are separate from documented
        documented = [c for c in categories if c.has_features and c.has_docs and not c.is_stub]
        stubs = [c for c in categories if c.has_features and c.has_docs and c.is_stub]
        undocumented = [c for c in categories if c.has_features and not c.has_docs]
        extra_docs = [c for c in categories if not c.has_features and c.has_docs]
        
        return {
            'lastUpdated': date.today().isoformat(),
            'sdk': 'Python',
            'summary': {
                'totalCategories': summary.total_categories,
                'documentedCategories': summary.documented_categories,
                'undocumentedCategories': summary.undocumented_categories,
                'parityPercent': summary.parity_percent,
            },
            'documented': documented,
            'stubs': stubs,
            'undocumented': undocumented,
            'extraDocs': extra_docs,
            'featureGroups': feature_groups,
            'docGroups': doc_groups,
        }
    
    def generate_typescript_parity(self) -> Dict:
        """Generate TypeScript documentation parity data."""
        # Get TypeScript features and docs
        ts_features = self.ts_feature_extractor.extract()
        docs = self.ts_docs_extractor.extract()
        
        # Group by category
        feature_groups = self._group_features(ts_features.exports)
        doc_groups = self._group_docs(docs)
        
        # Calculate parity
        summary, categories = self._calculate_category_parity(feature_groups, doc_groups)
        
        # Build category lists - stubs are separate from documented
        documented = [c for c in categories if c.has_features and c.has_docs and not c.is_stub]
        stubs = [c for c in categories if c.has_features and c.has_docs and c.is_stub]
        undocumented = [c for c in categories if c.has_features and not c.has_docs]
        extra_docs = [c for c in categories if not c.has_features and c.has_docs]
        
        return {
            'lastUpdated': date.today().isoformat(),
            'sdk': 'TypeScript/JavaScript',
            'summary': {
                'totalCategories': summary.total_categories,
                'documentedCategories': summary.documented_categories,
                'undocumentedCategories': summary.undocumented_categories,
                'parityPercent': summary.parity_percent,
            },
            'documented': documented,
            'stubs': stubs,
            'undocumented': undocumented,
            'extraDocs': extra_docs,
            'featureGroups': feature_groups,
            'docGroups': doc_groups,
        }
    
    def generate_rust_parity(self) -> Dict:
        """Generate Rust documentation parity data."""
        # Get Rust features and docs
        rust_features = self.rust_feature_extractor.extract()
        docs = self.rust_docs_extractor.extract()
        
        # Group by category
        feature_groups = self._group_features(rust_features.exports)
        doc_groups = self._group_docs(docs)
        
        # Calculate parity
        summary, categories = self._calculate_category_parity(feature_groups, doc_groups)
        
        # Build category lists - stubs are separate from documented
        documented = [c for c in categories if c.has_features and c.has_docs and not c.is_stub]
        stubs = [c for c in categories if c.has_features and c.has_docs and c.is_stub]
        undocumented = [c for c in categories if c.has_features and not c.has_docs]
        extra_docs = [c for c in categories if not c.has_features and c.has_docs]
        
        return {
            'lastUpdated': date.today().isoformat(),
            'sdk': 'Rust',
            'summary': {
                'totalCategories': summary.total_categories,
                'documentedCategories': summary.documented_categories,
                'undocumentedCategories': summary.undocumented_categories,
                'parityPercent': summary.parity_percent,
            },
            'documented': documented,
            'stubs': stubs,
            'undocumented': undocumented,
            'extraDocs': extra_docs,
            'featureGroups': feature_groups,
            'docGroups': doc_groups,
        }
    
    def _write_markdown(self, data: Dict, output_path: Path, sdk_name: str, docs_path: str, check: bool = False) -> int:
        """Write documentation parity Markdown for any SDK."""
        summary = data['summary']
        
        lines = []
        lines.append(f"# Documentation Parity Tracker ({sdk_name})")
        lines.append("")
        lines.append(f"> **Categories:** {summary['totalCategories']} | **Documented:** {summary['documentedCategories']} | **Parity:** {summary['parityPercent']}%")
        lines.append("")
        lines.append(f"This report compares **{sdk_name} SDK feature categories** against **{sdk_name} documentation** ({docs_path}).")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Feature Categories | {summary['totalCategories']} |")
        lines.append(f"| **Documented Categories** | **{summary['documentedCategories']}** |")
        lines.append(f"| **Undocumented Categories** | **{summary['undocumentedCategories']}** |")
        lines.append(f"| **Parity** | **{summary['parityPercent']}%** |")
        lines.append("")
        
        # Documented categories
        if data['documented']:
            lines.append("## Documented Categories")
            lines.append("")
            lines.append("| Category | Features | Docs | Lines |")
            lines.append("|----------|----------|------|-------|")
            for cat in data['documented']:
                lines.append(f"| ✅ {cat.display_name} | {cat.feature_count} | {cat.doc_count} | {cat.doc_lines} |")
            lines.append("")
        
        # Stub categories (have docs but < MIN_DOC_LINES)
        if data['stubs']:
            lines.append("## Stub Documentation (Need Content)")
            lines.append("")
            lines.append(f"These categories have documentation files but < {MIN_DOC_LINES} lines (stubs):")
            lines.append("")
            lines.append("| Category | Features | Docs | Lines |")
            lines.append("|----------|----------|------|-------|")
            for cat in data['stubs']:
                lines.append(f"| ⚠️ {cat.display_name} | {cat.feature_count} | {cat.doc_count} | {cat.doc_lines} |")
            lines.append("")
        
        # Undocumented categories
        if data['undocumented']:
            lines.append("## Undocumented Categories (Need Documentation)")
            lines.append("")
            lines.append("| Category | Features |")
            lines.append("|----------|----------|")
            for cat in data['undocumented']:
                lines.append(f"| ❌ {cat.display_name} | {cat.feature_count} |")
            lines.append("")
        
        # Extra docs
        if data['extraDocs']:
            lines.append("## Documentation Without Features")
            lines.append("")
            lines.append("These docs exist but don't match any implemented feature category:")
            lines.append("")
            for cat in data['extraDocs']:
                lines.append(f"- ℹ️ {cat.display_name} ({cat.doc_count} docs, {cat.doc_lines} lines)")
            lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append("*Generated by `praisonai._dev.parity.docs_generator`*")
        lines.append("")
        
        content = '\n'.join(lines)
        
        if check:
            if output_path.exists():
                existing = output_path.read_text()
                existing_lines = [l for l in existing.split('\n') if not l.startswith('>')]
                content_lines = [l for l in content.split('\n') if not l.startswith('>')]
                if existing_lines == content_lines:
                    print(f"✓ {output_path} is up to date")
                    return 0
                print(f"✗ {output_path} is out of date")
                return 1
            print(f"✗ {output_path} does not exist")
            return 1
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        print(f"✓ Generated {output_path}")
        return 0
    
    def write_python_markdown(self, check: bool = False) -> int:
        """Write Python documentation parity Markdown."""
        data = self.generate_python_parity()
        return self._write_markdown(data, self.python_md_output, "Python", "docs/concepts, docs/features, etc.", check)
    
    def write_typescript_markdown(self, check: bool = False) -> int:
        """Write TypeScript documentation parity Markdown."""
        data = self.generate_typescript_parity()
        return self._write_markdown(data, self.ts_md_output, "TypeScript/JavaScript", "docs/js/", check)
    
    def write_rust_markdown(self, check: bool = False) -> int:
        """Write Rust documentation parity Markdown."""
        data = self.generate_rust_parity()
        return self._write_markdown(data, self.rust_md_output, "Rust", "docs/rust/", check)
    
    def _write_json(self, data: Dict, output_path: Path, check: bool = False) -> int:
        """Write documentation parity JSON for any SDK."""
        # Convert CategoryParity objects to dicts for JSON
        data = data.copy()
        data['documented'] = [{'name': c.name, 'displayName': c.display_name, 'featureCount': c.feature_count, 'docCount': c.doc_count} for c in data['documented']]
        data['undocumented'] = [{'name': c.name, 'displayName': c.display_name, 'featureCount': c.feature_count} for c in data['undocumented']]
        data['extraDocs'] = [{'name': c.name, 'displayName': c.display_name, 'docCount': c.doc_count} for c in data['extraDocs']]
        
        json_output = output_path.with_suffix('.json')
        content = json.dumps(data, indent=2, sort_keys=True)
        
        if check:
            if json_output.exists():
                existing = json_output.read_text()
                existing_data = json.loads(existing)
                existing_data.pop('lastUpdated', None)
                data.pop('lastUpdated', None)
                if json.dumps(existing_data, sort_keys=True) == json.dumps(data, sort_keys=True):
                    print(f"✓ {json_output} is up to date")
                    return 0
                print(f"✗ {json_output} is out of date")
                return 1
            print(f"✗ {json_output} does not exist")
            return 1
        
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(content)
        print(f"✓ Generated {json_output}")
        return 0
    
    def write_python_json(self, check: bool = False) -> int:
        """Write Python documentation parity JSON (optional)."""
        data = self.generate_python_parity()
        return self._write_json(data, self.python_md_output, check)
    
    def write_typescript_json(self, check: bool = False) -> int:
        """Write TypeScript documentation parity JSON (optional)."""
        data = self.generate_typescript_parity()
        return self._write_json(data, self.ts_md_output, check)
    
    def write_rust_json(self, check: bool = False) -> int:
        """Write Rust documentation parity JSON (optional)."""
        data = self.generate_rust_parity()
        return self._write_json(data, self.rust_md_output, check)
    
    def _create_doc_stub(self, category_name: str, display_name: str, docs_dir: Path, sdk_name: str) -> bool:
        """Create a stub documentation file for an undocumented category."""
        # Convert display name to filename (e.g., "Agent-to-Agent (A2A)" -> "a2a.mdx")
        filename = category_name.lower().replace(' ', '-').replace('(', '').replace(')', '') + '.mdx'
        filepath = docs_dir / filename
        
        if filepath.exists():
            return False  # Already exists
        
        # Create stub content
        content = f'''---
title: "{display_name}"
description: "{display_name} features in PraisonAI {sdk_name} SDK"
---

# {display_name}

<Note>
This documentation page is a stub. Please contribute by adding content.
</Note>

## Overview

TODO: Add overview of {display_name} features.

## Usage

```{"typescript" if sdk_name in ("TypeScript", "JavaScript") else "rust" if sdk_name == "Rust" else "python"}
// TODO: Add usage examples
```

## API Reference

TODO: Add API reference.

## Related

- [Getting Started](/docs/{sdk_name.lower()}/quickstart)
'''
        
        # Create directory if needed
        docs_dir.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        print(f"✓ Created {filepath}")
        return True
    
    def scaffold_python_docs(self) -> int:
        """Create stub documentation files for undocumented Python categories."""
        data = self.generate_python_parity()
        docs_dir = self.docs_root / "features"
        
        created = 0
        for cat in data['undocumented']:
            if self._create_doc_stub(cat.name, cat.display_name, docs_dir, "Python"):
                created += 1
        
        if created == 0:
            print("No new documentation stubs needed for Python")
        else:
            print(f"Created {created} documentation stub(s) for Python")
        return 0
    
    def scaffold_typescript_docs(self) -> int:
        """Create stub documentation files for undocumented TypeScript categories."""
        data = self.generate_typescript_parity()
        docs_dir = self.docs_root / "js"
        
        created = 0
        for cat in data['undocumented']:
            if self._create_doc_stub(cat.name, cat.display_name, docs_dir, "TypeScript"):
                created += 1
        
        if created == 0:
            print("No new documentation stubs needed for TypeScript")
        else:
            print(f"Created {created} documentation stub(s) for TypeScript")
        return 0
    
    def scaffold_rust_docs(self) -> int:
        """Create stub documentation files for undocumented Rust categories."""
        data = self.generate_rust_parity()
        docs_dir = self.docs_root / "rust"
        
        created = 0
        for cat in data['undocumented']:
            if self._create_doc_stub(cat.name, cat.display_name, docs_dir, "Rust"):
                created += 1
        
        if created == 0:
            print("No new documentation stubs needed for Rust")
        else:
            print(f"Created {created} documentation stub(s) for Rust")
        return 0


def generate_docs_parity(
    docs_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    target: str = 'all',
    check: bool = False,
    include_json: bool = False,
    scaffold: bool = False,
    copy_docs: bool = False,
    update_nav: bool = False,
) -> int:
    """Generate documentation parity tracker files."""
    generator = DocsParityGenerator(docs_root=docs_root, repo_root=repo_root)
    exit_code = 0
    
    if target in ('python', 'py', 'all'):
        result = generator.write_python_markdown(check=check)
        if result != 0:
            exit_code = result
        if include_json:
            result = generator.write_python_json(check=check)
            if result != 0:
                exit_code = result
    
    if target in ('typescript', 'ts', 'all'):
        result = generator.write_typescript_markdown(check=check)
        if result != 0:
            exit_code = result
        if include_json:
            result = generator.write_typescript_json(check=check)
            if result != 0:
                exit_code = result
        if scaffold:
            generator.scaffold_typescript_docs()
    
    if target in ('rust', 'rs', 'all'):
        result = generator.write_rust_markdown(check=check)
        if result != 0:
            exit_code = result
        if include_json:
            result = generator.write_rust_json(check=check)
            if result != 0:
                exit_code = result
        if scaffold:
            generator.scaffold_rust_docs()
    
    # Copy parity files to docs folder
    if copy_docs and not check:
        import shutil
        copy_map = {
            generator.python_md_output: generator.docs_root / 'features' / 'DOCS_PARITY.md',
            generator.ts_md_output: generator.docs_root / 'js' / 'DOCS_PARITY.md',
            generator.rust_md_output: generator.docs_root / 'rust' / 'DOCS_PARITY.md',
        }
        for src, dst in copy_map.items():
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"✓ Copied {src.name} to {dst.parent.name}/")
    
    # Update docs.json navigation
    if update_nav and not check:
        update_docs_json(generator.docs_root)
    
    return exit_code


def update_docs_json(docs_root: Path) -> bool:
    """Add parity pages to docs.json navigation if not already present.
    
    Uses 'Features' as the group name for automated pages in each SDK tab.
    Safe to run multiple times - only adds if page doesn't exist.
    """
    docs_json_path = docs_root.parent / 'docs.json'
    if not docs_json_path.exists():
        print(f"✗ docs.json not found at {docs_json_path}")
        return False
    
    try:
        data = json.loads(docs_json_path.read_text())
    except json.JSONDecodeError as e:
        print(f"✗ Failed to parse docs.json: {e}")
        return False
    
    # Define parity page entries for each tab
    parity_pages = {
        'Documentation': {
            'page': 'docs/features/DOCS_PARITY',
            'group': 'Features',
        },
        'TypeScript': {
            'page': 'docs/js/DOCS_PARITY',
            'group': 'Features',
        },
        'Rust': {
            'page': 'docs/rust/DOCS_PARITY',
            'group': 'Features',
        },
    }
    
    modified = False
    tabs = data.get('navigation', {}).get('tabs', [])
    
    for tab in tabs:
        tab_name = tab.get('tab', '')
        if tab_name not in parity_pages:
            continue
        
        config = parity_pages[tab_name]
        page_path = config['page']
        group_name = config['group']
        
        # Check if page already exists anywhere in this tab
        tab_json = json.dumps(tab)
        if page_path in tab_json:
            continue  # Already exists
        
        # Find or create the Features group
        groups = tab.get('groups', [])
        features_group = None
        for g in groups:
            if g.get('group') == group_name:
                features_group = g
                break
        
        if features_group is None:
            # Create new Features group at end
            features_group = {
                'group': group_name,
                'icon': 'stars',
                'pages': []
            }
            groups.append(features_group)
        
        # Add page to Features group
        pages = features_group.get('pages', [])
        if page_path not in pages:
            pages.append(page_path)
            features_group['pages'] = pages
            modified = True
            print(f"✓ Added {page_path} to {tab_name} → {group_name}")
    
    if modified:
        docs_json_path.write_text(json.dumps(data, indent=2))
        print(f"✓ Updated {docs_json_path}")
    else:
        print("✓ docs.json already up to date")
    
    return modified


def main():
    """CLI entry point for the docs parity generator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate documentation parity tracker files"
    )
    parser.add_argument(
        "-t", "--target",
        choices=["python", "py", "typescript", "ts", "rust", "rs", "all"],
        default="all",
        help="Target SDK to generate parity for (default: all)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files are up to date (exit 1 if not)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also generate JSON files (default: Markdown only)"
    )
    parser.add_argument(
        "--scaffold",
        action="store_true",
        help="Create stub MDX files for undocumented categories (TypeScript/Rust only)"
    )
    parser.add_argument(
        "--copy-docs",
        action="store_true",
        help="Copy parity files to PraisonAIDocs folder (default: off)"
    )
    parser.add_argument(
        "--update-nav",
        action="store_true",
        help="Update docs.json navigation with parity pages"
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        help="Path to documentation root directory"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Path to repository root directory"
    )
    
    args = parser.parse_args()
    
    exit_code = generate_docs_parity(
        docs_root=args.docs_root,
        repo_root=args.repo_root,
        target=args.target,
        check=args.check,
        include_json=args.json,
        scaffold=args.scaffold,
        copy_docs=args.copy_docs,
        update_nav=args.update_nav,
    )
    
    raise SystemExit(exit_code)


if __name__ == '__main__':
    main()
