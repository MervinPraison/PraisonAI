"""C8 bridge: workflow handler lives in the praisonai wrapper."""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.workflow")
populate_from_module(globals(), _mod)
