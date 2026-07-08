"""Bridge: endpoints handler lives in the praisonai wrapper.

Re-exports :class:`EndpointsHandler` and :func:`handle_endpoints_command` from
``praisonai.cli.features.endpoints`` so the legacy CLI dispatcher and doctor
checks can resolve ``praisonai_code.cli.features.endpoints`` transparently.
"""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.endpoints")
populate_from_module(globals(), _mod)
