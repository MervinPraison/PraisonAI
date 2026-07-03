#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Backward-compatible shim for the LLM fine-tuning entry point.

The canonical fine-tuning implementation lives in
:mod:`praisonai.train.llm.trainer` (served by the ``praisonai.train`` package).
This top-level module is retained only as a thin re-export so that any legacy
reference to ``praisonai/train.py`` (e.g. ``python path/to/train.py train``)
keeps working. There is a single owner: ``praisonai.train.llm.trainer``.

Note: because ``praisonai.train`` resolves to the package, this file is only
reachable when executed directly as a script, not via ``import``.
"""

from praisonai.train.llm.trainer import (  # noqa: F401
    TrainModel,
    formatting_prompts_func,
    tokenize_function,
    main,
)

__all__ = ["TrainModel", "formatting_prompts_func", "tokenize_function", "main"]

if __name__ == "__main__":
    main()
