"""The engine must never delete an environment variable it did not set.

`api_key` is documented as "blank uses the environment". Clearing it used to
call `os.environ.pop("OPENAI_API_KEY")` unconditionally, which deleted the key
inherited from the user's shell -- so emptying a field the user had never
filled in turned every subsequent turn into an auth error. Seven lifecycle
tests went red and the cause was three files away from the symptom.

Run: .venv/bin/python -m unittest discover -s engine -p 'test_*.py'
"""
import importlib.util
import os
import pathlib
import sys
import unittest

_SRC = pathlib.Path(__file__).resolve().parents[2] / "praisonai-agents"
if (_SRC / "praisonaiagents" / "__init__.py").is_file():
    sys.path.insert(0, str(_SRC))
_spec = importlib.util.spec_from_file_location(
    "engine_server", pathlib.Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(server)


class ExportOwnership(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)
        server._EXPORTED.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        server._EXPORTED.clear()

    def test_an_inherited_value_survives_clearing(self):
        os.environ["OPENAI_API_KEY"] = "from-the-users-shell"
        server._unset_if_ours("OPENAI_API_KEY")
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "from-the-users-shell")

    def test_our_own_value_is_removed(self):
        server._export("OPENAI_API_KEY", "sk-set-from-settings")
        server._unset_if_ours("OPENAI_API_KEY")
        self.assertIsNone(os.environ.get("OPENAI_API_KEY"))

    def test_a_value_overwritten_after_we_set_it_is_left_alone(self):
        server._export("OPENAI_API_BASE", "http://ours")
        os.environ["OPENAI_API_BASE"] = "http://someone-elses"
        server._unset_if_ours("OPENAI_API_BASE")
        self.assertEqual(os.environ.get("OPENAI_API_BASE"), "http://someone-elses")

    def test_clearing_twice_is_harmless(self):
        server._export("OPENAI_API_KEY", "sk-x")
        server._unset_if_ours("OPENAI_API_KEY")
        server._unset_if_ours("OPENAI_API_KEY")   # must not raise

    def test_blank_settings_do_not_touch_an_inherited_key(self):
        # The end-to-end shape: settings carry no key, the shell does.
        os.environ["OPENAI_API_KEY"] = "inherited"
        server._apply_env({"model": "m", "base_url": "", "api_key": "",
                           "temperature": 0.7})
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "inherited")

    def test_a_too_short_key_is_not_exported_and_does_not_clobber(self):
        os.environ["OPENAI_API_KEY"] = "inherited"
        server._apply_env({"model": "m", "base_url": "", "api_key": "abc",
                           "temperature": 0.7})
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "inherited")


if __name__ == "__main__":
    unittest.main()
