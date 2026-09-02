"""
Signature-level parity checker: praisonaiagents (Python) vs praisonai-ts.

The name-level tracker (``praisonai._dev.parity.generator``) answers "does the
export exist?". This package answers "does it take the same parameters, with
the same required-ness and defaults?" for a curated list of surfaces
(``surface.yaml``), using normalisation rules (``rules.yaml``) and an explicit,
reviewed waiver list (``waivers.yaml``).

Usage::

    python -m praisonai._dev.parity.signatures --write      # regenerate outputs
    python -m praisonai._dev.parity.signatures --check      # CI gate
    python -m praisonai._dev.parity.signatures --diff Agent.__init__
    python -m praisonai._dev.parity.signatures --baseline   # waive current gaps
"""

from .schema import Param, SurfaceSignature, snake_to_camel
from .py_extract import extract_python_surface, python_type_class, PythonSurfaceNotFound
from .compare import (
    Rules,
    Waiver,
    SurfaceComparison,
    Evaluation,
    ToolingError,
    compare_surface,
    compare_all,
    evaluate,
    render_markdown,
    render_json,
    load_rules,
    load_surfaces,
    load_waivers,
    main,
)

__all__ = [
    'Param',
    'SurfaceSignature',
    'snake_to_camel',
    'extract_python_surface',
    'python_type_class',
    'PythonSurfaceNotFound',
    'Rules',
    'Waiver',
    'SurfaceComparison',
    'Evaluation',
    'ToolingError',
    'compare_surface',
    'compare_all',
    'evaluate',
    'render_markdown',
    'render_json',
    'load_rules',
    'load_surfaces',
    'load_waivers',
    'main',
]
