"""
LLM Fine-tuning Module.

This module provides LLM fine-tuning using Unsloth's fast training framework.
Supports ShareGPT and Alpaca-style datasets.

Usage:
    praisonai train dataset.json
    praisonai train --model llama-3.1 dataset.json

Note: This module requires heavy dependencies (torch, unsloth, transformers).
They are only loaded when this module is explicitly imported.
"""

__all__ = ["TrainModel"]


def __getattr__(name: str):
    """Lazy load to avoid heavy imports."""
    if name == "TrainModel":
        from .trainer import TrainModel
        return TrainModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
