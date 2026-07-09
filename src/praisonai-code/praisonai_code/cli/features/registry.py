"""Bridge: registry handler lives in the praisonai wrapper.

Re-exports :class:`RegistryHandler` and :func:`handle_registry_command` from
``praisonai.cli.features.registry`` so the legacy CLI dispatcher, the Typer
``registry`` command group and ``serve registry`` can resolve
``praisonai_code.cli.features.registry`` transparently.
"""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.registry")
populate_from_module(globals(), _mod)
