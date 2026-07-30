"""Bridge: ollama handler lives in the praisonai wrapper.

Re-exports :class:`OllamaHandler` and :func:`handle_ollama_command` from
``praisonai.cli.features.ollama`` so the code-side feature package can resolve
``praisonai_code.cli.features.ollama`` transparently.
"""

from praisonai_code.cli._wrapper_reexport import load_wrapper_module, populate_from_module

_mod = load_wrapper_module("praisonai.cli.features.ollama")
populate_from_module(globals(), _mod)
