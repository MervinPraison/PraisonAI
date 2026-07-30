"""Bridge: eval handler lives in the praisonai wrapper.

Re-exports :class:`EvalHandler` and :func:`handle_eval_command` from
``praisonai.cli.features.eval`` so the legacy CLI dispatcher and the Typer
``eval`` command can resolve ``praisonai_code.cli.features.eval`` transparently.
"""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.eval")
populate_from_module(globals(), _mod)
