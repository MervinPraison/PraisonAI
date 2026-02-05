"""
Feature Parity Tracker for PraisonAI SDKs.

This module provides tools to automatically extract features from Python SDK
and compare them against TypeScript and Rust implementations.

Usage:
    python -m praisonai._dev.parity.generator --write
    python -m praisonai._dev.parity.generator --check
    
Documentation Parity:
    python -m praisonai._dev.parity.docs_generator --write
    python -m praisonai._dev.parity.docs_generator --check
"""

from .python_extractor import PythonFeatureExtractor
from .rust_extractor import RustFeatureExtractor
from .typescript_extractor import TypeScriptFeatureExtractor
from .generator import ParityTrackerGenerator, generate_parity_tracker

# Documentation parity exports
from .docs_extractor import DocsExtractor, DocsFeatures, DocsTopic, BaseDocsExtractor
from .docs_generator import DocsParityGenerator, generate_docs_parity
from .topic_normalizer import normalize_topic, topics_match

__all__ = [
    # Feature parity
    'PythonFeatureExtractor',
    'RustFeatureExtractor',
    'TypeScriptFeatureExtractor',
    'ParityTrackerGenerator',
    'generate_parity_tracker',
    # Documentation parity
    'DocsExtractor',
    'DocsFeatures',
    'DocsTopic',
    'BaseDocsExtractor',
    'DocsParityGenerator',
    'generate_docs_parity',
    'normalize_topic',
    'topics_match',
]
