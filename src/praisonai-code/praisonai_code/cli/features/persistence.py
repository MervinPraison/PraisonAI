"""Bridge: persistence handler lives in the praisonai wrapper.

Re-exports :func:`handle_persistence_command` from
``praisonai.cli.features.persistence`` so the legacy CLI dispatcher can resolve
``praisonai_code.cli.features.persistence`` transparently.
"""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.persistence")
populate_from_module(globals(), _mod)
