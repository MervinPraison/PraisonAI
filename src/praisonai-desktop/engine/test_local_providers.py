"""The Base URL setting must reach whichever provider the model names.

The desktop has two credential settings, Base URL and API key, and sent both
to OPENAI_API_BASE / OPENAI_API_KEY only. litellm reads a different variable
per provider, so for every local runtime the setting was inert:

    model                        api_base litellm used
    ollama/llama3.2              http://localhost:11434   <- the default, not the setting
    lm_studio/qwen2.5-7b         None
    hosted_vllm/meta-llama/...   None

A user pointing the app at Ollama on another host, or at LM Studio or vLLM at
all, was silently ignored -- the request went somewhere else or nowhere.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import importlib.util
import os
import pathlib
import tempfile
import unittest

_HOME = tempfile.mkdtemp(prefix="praison-providers-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test.prov." + str(os.getpid())

_spec = importlib.util.spec_from_file_location(
    "engine_server_providers", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

assert server.KEYCHAIN_SERVICE != "ai.praison.desktop", "refusing to touch the real keychain"

BASE = "http://192.168.1.50:11434"
KEY = "sk-a-real-looking-key-123456"


def _clear():
    for name in list(os.environ):
        if name.endswith("_API_BASE") or name.endswith("_API_KEY"):
            os.environ.pop(name, None)


class ProviderPrefix(unittest.TestCase):

    def test_a_slashed_id_yields_its_provider(self):
        self.assertEqual(server.model_provider("ollama/llama3.2"), "ollama")
        self.assertEqual(server.model_provider("lm_studio/qwen"), "lm_studio")
        self.assertEqual(server.model_provider("hosted_vllm/m"), "hosted_vllm")

    def test_a_bare_name_has_no_provider(self):
        self.assertEqual(server.model_provider("gpt-4o-mini"), "")

    def test_a_bare_name_maps_to_the_openai_vars(self):
        self.assertEqual(server.provider_env_names(""),
                         ("OPENAI_API_BASE", "OPENAI_API_KEY"))

    def test_known_local_runtimes_map_to_their_own_vars(self):
        self.assertEqual(server.provider_env_names("ollama")[0], "OLLAMA_API_BASE")
        self.assertEqual(server.provider_env_names("lm_studio")[0], "LM_STUDIO_API_BASE")
        self.assertEqual(server.provider_env_names("hosted_vllm")[0], "HOSTED_VLLM_API_BASE")

    def test_an_unlisted_provider_follows_the_convention(self):
        """A provider litellm gains later must not need a code change here."""
        self.assertEqual(server.provider_env_names("groq"),
                         ("GROQ_API_BASE", "GROQ_API_KEY"))

    def test_ollama_needs_no_key(self):
        self.assertIsNone(server.provider_env_names("ollama")[1])


class BaseUrlReachesTheProvider(unittest.TestCase):

    def setUp(self):
        _clear()
        self.addCleanup(_clear)

    def _apply(self, model, base_url=BASE, api_key=KEY):
        server._apply_env({"model": model, "base_url": base_url, "api_key": api_key})

    def test_ollama_gets_the_configured_host(self):
        self._apply("ollama/llama3.2")
        self.assertEqual(os.environ.get("OLLAMA_API_BASE"), BASE,
                         "Ollama would have gone to litellm's localhost default")

    def test_lm_studio_gets_a_base_url_at_all(self):
        self._apply("lm_studio/qwen2.5-7b")
        self.assertEqual(os.environ.get("LM_STUDIO_API_BASE"), BASE)

    def test_vllm_gets_a_base_url_at_all(self):
        self._apply("hosted_vllm/meta-llama/Llama-3-8B")
        self.assertEqual(os.environ.get("HOSTED_VLLM_API_BASE"), BASE)

    def test_openai_still_works_for_a_bare_name(self):
        self._apply("gpt-4o-mini")
        self.assertEqual(os.environ.get("OPENAI_API_BASE"), BASE)
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), KEY)

    def test_the_openai_pair_is_kept_in_step(self):
        """Switching back to a bare id must not leave a stale endpoint."""
        self._apply("ollama/llama3.2")
        self.assertEqual(os.environ.get("OPENAI_API_BASE"), BASE)

    def test_the_key_reaches_the_provider_that_needs_one(self):
        self._apply("lm_studio/qwen2.5-7b")
        self.assertEqual(os.environ.get("LM_STUDIO_API_KEY"), KEY)

    def test_clearing_the_base_url_clears_the_provider_var(self):
        self._apply("ollama/llama3.2")
        self._apply("ollama/llama3.2", base_url="")
        self.assertIsNone(os.environ.get("OLLAMA_API_BASE"))

    def test_a_short_key_is_still_refused(self):
        """The existing backstop must survive the rerouting."""
        self._apply("lm_studio/q", api_key="abc")
        self.assertIsNone(os.environ.get("LM_STUDIO_API_KEY"))


class LitellmAgrees(unittest.TestCase):
    """Assert against litellm itself, not just our own env vars."""

    def setUp(self):
        _clear()
        self.addCleanup(_clear)

    def test_litellm_resolves_each_runtime_to_the_configured_host(self):
        try:
            from litellm.utils import get_llm_provider
        except ImportError:
            self.skipTest("litellm not installed in this environment")
        for model in ("ollama/llama3.2", "lm_studio/qwen2.5-7b",
                      "hosted_vllm/meta-llama/Llama-3-8B"):
            with self.subTest(model=model):
                _clear()
                server._apply_env({"model": model, "base_url": BASE, "api_key": KEY})
                _, _, _, api_base = get_llm_provider(model=model)
                self.assertEqual(api_base, BASE)


if __name__ == "__main__":
    unittest.main()
