"""Output controller for the praisonai-train CLI.

Reuses ``praisonai_code``'s richer OutputController when co-installed (via the
lazy ``_code_bridge``), otherwise falls back to a self-contained controller so
``pip install praisonai-train`` works standalone with only ``rich``/``typer``.
"""

from praisonai_train.cli.output.console import (
    OutputController,
    get_output_controller,
    set_output_controller,
)

__all__ = [
    "OutputController",
    "get_output_controller",
    "set_output_controller",
]
