"""The desktop must be able to run agent frameworks other than PraisonAI.

The app had no framework concept at all -- a grep for "framework" across the
engine, the settings registry and the UI returned nothing, and every turn was
a single hardcoded praisonaiagents.Agent.

praisonai's FrameworkAdapterRegistry discovers adapters through the
`praisonai.framework_adapters` entry-point group, so installing
praisonai-frameworks registers CrewAI, AutoGen, LangGraph, Agno, Google ADK,
OpenAI Agents SDK and Pydantic AI without a change here. The desktop already
provisions the praisonai wrapper, so the registry is reachable.

The rule these tests pin: a framework that is not installed is REFUSED with
its install command, never silently swapped for the default. A silent
fallback is what makes a setting look effective while changing nothing --
the defect this codebase ships most often.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import importlib.util
import os
import pathlib
import tempfile
import unittest

_HOME = tempfile.mkdtemp(prefix="praison-frameworks-")
os.environ["PRAISONAI_DESKTOP_HOME"] = _HOME
os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test.fw." + str(os.getpid())

_spec = importlib.util.spec_from_file_location(
    "engine_server_frameworks", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)

assert server.KEYCHAIN_SERVICE != "ai.praison.desktop", "refusing to touch the real keychain"


class Discovery(unittest.TestCase):

    def test_the_builtin_is_always_available(self):
        self.assertIn("praisonai", server.list_frameworks()["available"])

    def test_the_report_has_the_shape_the_ui_needs(self):
        info = server.list_frameworks()
        for key in ("available", "known", "hints", "default"):
            self.assertIn(key, info, key)

    def test_available_is_a_subset_of_known(self):
        info = server.list_frameworks()
        self.assertTrue(set(info["available"]) <= set(info["known"]))

    def test_every_unavailable_framework_carries_a_hint(self):
        """A name with no way to obtain it is a dead end."""
        info = server.list_frameworks()
        for name in info["known"]:
            if name not in info["available"]:
                self.assertTrue(info["hints"].get(name), name)

    def test_a_missing_wrapper_degrades_to_the_builtin(self, ):
        """An engine predating the wrapper must still answer, not raise."""
        original = server.framework_registry
        server.framework_registry = lambda: None
        try:
            info = server.list_frameworks()
            self.assertEqual(info["available"], ["praisonai"])
            self.assertIsNotNone(info["error"])
        finally:
            server.framework_registry = original


class RefusalIsExplicit(unittest.TestCase):

    def test_the_default_is_accepted(self):
        self.assertIsNone(server.framework_error("praisonai"))

    def test_blank_means_the_default(self):
        self.assertIsNone(server.framework_error(""))

    def test_an_uninstalled_framework_is_refused(self):
        self.assertIsNotNone(server.framework_error("crewai"))

    def test_the_refusal_names_how_to_get_it(self):
        """The message must be a next step, not a dead end."""
        message = server.framework_error("crewai")
        self.assertIn("praisonai-frameworks", message)

    def test_an_unknown_name_is_refused_too(self):
        self.assertIsNotNone(server.framework_error("not_a_real_framework"))

    def test_running_an_uninstalled_framework_raises(self):
        """It must not quietly fall back to the built-in agent."""
        with self.assertRaises(RuntimeError) as caught:
            server.run_with_framework("hello", {"framework": "crewai",
                                                "model": "gpt-4o-mini"})
        self.assertIn("praisonai-frameworks", str(caught.exception))


class TurnConfig(unittest.TestCase):

    def test_the_turn_becomes_a_one_agent_config(self):
        doc = server._framework_yaml("What is 2+2?", {"framework": "crewai",
                                                      "system_prompt": ""})
        self.assertIn("framework: crewai", doc)
        self.assertIn("roles:", doc)
        self.assertIn("What is 2+2?", doc)

    def test_the_system_prompt_reaches_the_config(self):
        doc = server._framework_yaml("hi", {"framework": "crewai",
                                            "system_prompt": "Be terse."})
        self.assertIn("Be terse.", doc)

    def test_a_prompt_with_quotes_is_encoded_not_interpolated(self):
        """The prompt is user input; it must not be able to corrupt the YAML.

        Asserted without PyYAML: the desktop engine is stdlib-only by design
        (see this module's header) and its CI installs nothing else, so a test
        importing yaml fails there while passing locally -- which is how this
        first went red.
        """
        import json

        raw = 'He said "hello": now what?'
        doc = server._framework_yaml(raw, {"framework": "crewai",
                                           "system_prompt": ""})
        self.assertIn(json.dumps(raw), doc,
                      "the prompt was interpolated raw instead of encoded")
        self.assertNotIn("\n" + raw, doc)

    def test_the_document_parses_when_a_yaml_reader_is_present(self):
        """The real check, run only where PyYAML exists (it is a praisonai dep)."""
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML absent: the engine venv is stdlib-only")
        parsed = yaml.safe_load(server._framework_yaml(
            'He said "hello": now what?',
            {"framework": "crewai", "system_prompt": 'A "quoted" persona'}))
        self.assertIn("assistant", parsed["roles"])
        self.assertEqual(
            parsed["roles"]["assistant"]["tasks"]["reply"]["description"],
            'He said "hello": now what?')

    def test_the_setting_has_a_default(self):
        self.assertEqual(server.DEFAULT_SETTINGS.get("framework"), "praisonai")


if __name__ == "__main__":
    unittest.main()
