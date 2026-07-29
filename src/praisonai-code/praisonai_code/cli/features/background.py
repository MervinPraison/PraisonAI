"""Bridge: background handler lives in the praisonai wrapper.

Re-exports :class:`BackgroundHandler` and :func:`handle_background_command` from
``praisonai.cli.features.background`` so the code-side feature package can
resolve ``praisonai_code.cli.features.background`` transparently.
"""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.background")
populate_from_module(globals(), _mod)
