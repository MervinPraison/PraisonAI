"""Unit tests for the unified CLI dispatcher in `praisonai.__main__`.

The dispatcher is the single entry point for all CLI invocations. It must:
  - Short-circuit on ``--version`` / ``-V`` before importing any heavy modules
    (so version reporting stays fast even with broken optional deps).
  - Treat free-text prompts and bare ``.yaml``/``.yml`` paths (existing on
    disk) as legacy invocations and route them to ``PraisonAI()``.
  - Hand every other invocation, including ``--help``, to Typer so registered
    subcommands and global flags work.
  - Always restore ``sys.argv`` after dispatch — Typer mutates ``argv`` and
    legacy invocations also rewrite it.
  - Fail loud on Typer command-registration errors (no silent degradation).
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

import praisonai.__main__ as dispatcher


class TestIsLegacyInvocation(unittest.TestCase):
    """``_is_legacy_invocation`` only matches bare prompts and existing YAML files.

    It must NOT match:
      - empty argv
      - argv whose first token is a flag
      - YAML-looking arguments that don't exist on disk (could be a typo or
        a Typer subcommand name that happens to end in ``.yml``).
    """

    def test_empty_argv_is_not_legacy(self):
        self.assertFalse(dispatcher._is_legacy_invocation([]))

    def test_leading_flag_is_not_legacy(self):
        self.assertFalse(dispatcher._is_legacy_invocation(["--verbose", "agents.yaml"]))
        self.assertFalse(dispatcher._is_legacy_invocation(["-V"]))

    def test_freetext_prompt_is_legacy(self):
        self.assertTrue(dispatcher._is_legacy_invocation(["Create a weather app"]))

    def test_existing_yaml_file_is_legacy(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as fh:
            fh.write(b"agents: []\n")
            path = fh.name
        try:
            self.assertTrue(dispatcher._is_legacy_invocation([path]))
        finally:
            os.unlink(path)

    def test_existing_yml_file_is_legacy(self):
        with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as fh:
            fh.write(b"agents: []\n")
            path = fh.name
        try:
            self.assertTrue(dispatcher._is_legacy_invocation([path]))
        finally:
            os.unlink(path)

    def test_nonexistent_yaml_path_is_not_legacy(self):
        # If the file doesn't exist, fall through to Typer so it can show a
        # proper command-not-found error instead of silently routing to legacy.
        self.assertFalse(
            dispatcher._is_legacy_invocation(["/nonexistent/agents.yaml"])
        )

    def test_typer_subcommand_is_not_legacy(self):
        self.assertFalse(dispatcher._is_legacy_invocation(["chat"]))
        self.assertFalse(dispatcher._is_legacy_invocation(["ui", "--port", "8080"]))


class TestVersionShortCircuit(unittest.TestCase):
    """``--version`` / ``-V`` must print and return without importing Typer."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_long_flag_prints_version(self):
        sys.argv = ["praisonai", "--version"]
        with mock.patch("builtins.print") as mock_print:
            dispatcher.main()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("PraisonAI version", printed)

    def test_short_flag_prints_version(self):
        sys.argv = ["praisonai", "-V"]
        with mock.patch("builtins.print") as mock_print:
            dispatcher.main()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("PraisonAI version", printed)

    def test_version_does_not_import_typer_app(self):
        """The version path is on the hot import path; it must stay light.

        We deliberately avoid ``mock.patch("praisonai.cli.app.register_commands")``
        here: ``mock.patch`` with a dotted target imports the target module
        when the patch context is entered, which would itself defeat the
        invariant we are trying to verify. Instead, evict any cached
        ``praisonai.cli.*`` modules from ``sys.modules`` before invoking
        ``main()``, then assert they are still absent afterwards.
        """
        sys.argv = ["praisonai", "--version"]
        cli_mods = [m for m in list(sys.modules) if m.startswith("praisonai.cli")]
        saved = {m: sys.modules.pop(m) for m in cli_mods}
        try:
            with mock.patch("builtins.print"):
                dispatcher.main()
            still_loaded = [m for m in sys.modules if m.startswith("praisonai.cli")]
            self.assertEqual(
                still_loaded, [],
                f"--version must not import praisonai.cli.*, but loaded: {still_loaded}",
            )
        finally:
            sys.modules.update(saved)


class TestLegacyRouting(unittest.TestCase):
    """Bare prompts and existing YAML paths must reach the legacy ``PraisonAI()``."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_freetext_prompt_routes_to_legacy(self):
        sys.argv = ["praisonai", "Build a weather agent"]
        fake = mock.MagicMock()
        fake.main.return_value = None
        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake) as PraisonAI, \
             mock.patch("praisonai.cli.app.register_commands") as reg, \
             self.assertRaises(SystemExit):
            dispatcher.main()
        PraisonAI.assert_called_once()
        fake.main.assert_called_once()
        reg.assert_not_called()

    def test_existing_yaml_routes_to_legacy(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as fh:
            fh.write(b"agents: []\n")
            path = fh.name
        try:
            sys.argv = ["praisonai", path]
            fake = mock.MagicMock()
            fake.main.return_value = None
            with mock.patch(
                "praisonai.cli.main.PraisonAI", return_value=fake
            ) as PraisonAI, self.assertRaises(SystemExit):
                dispatcher.main()
            PraisonAI.assert_called_once()
            fake.main.assert_called_once()
        finally:
            os.unlink(path)

    def test_legacy_translates_bool_false_to_exit_code_1(self):
        """Legacy ``main()`` returning ``False`` must propagate as exit code 1."""
        sys.argv = ["praisonai", "Topic prompt"]
        fake = mock.MagicMock()
        fake.main.return_value = False
        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher.main()
        self.assertEqual(cm.exception.code, 1)

    def test_legacy_path_restores_argv(self):
        # NOTE: argv[0] differs from the dispatcher's rewrite ("praisonai"),
        # so the restoration assertion has real discriminating power.
        # If the ``finally`` clause were removed, ``sys.argv[0]`` would
        # remain "praisonai" after dispatch, and ``assertEqual`` would fail.
        # (Claude's earlier '--extra-arg' variant did not catch this because
        # the dispatcher rewrites to ``["praisonai"] + sys.argv[1:]`` —
        # identical to the original when ``argv[0] == "praisonai"``.)
        original = ["/usr/local/bin/some-launcher", "Build weather app", "--extra-arg"]
        sys.argv = list(original)
        fake = mock.MagicMock()
        fake.main.return_value = None
        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit):
            dispatcher.main()
        self.assertEqual(sys.argv, original)


class TestTyperRouting(unittest.TestCase):
    """Anything that is not version/legacy must reach the Typer app."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_no_args_routes_to_typer(self):
        sys.argv = ["praisonai"]
        with mock.patch("praisonai.cli.app.app") as app, \
             mock.patch("praisonai.cli.app.register_commands") as reg, \
             mock.patch("praisonai.cli.main.PraisonAI") as legacy:
            dispatcher.main()
        reg.assert_called_once()
        app.assert_called_once()
        legacy.assert_not_called()

    def test_help_flag_routes_to_typer(self):
        sys.argv = ["praisonai", "--help"]
        with mock.patch("praisonai.cli.app.app") as app, \
             mock.patch("praisonai.cli.app.register_commands"), \
             mock.patch("praisonai.cli.main.PraisonAI") as legacy:
            dispatcher.main()
        app.assert_called_once()
        legacy.assert_not_called()

    def test_subcommand_routes_to_typer(self):
        sys.argv = ["praisonai", "chat", "--model", "gpt-4o"]
        with mock.patch("praisonai.cli.app.app") as app, \
             mock.patch("praisonai.cli.app.register_commands") as reg, \
             mock.patch("praisonai.cli.main.PraisonAI") as legacy:
            dispatcher.main()
        reg.assert_called_once()
        app.assert_called_once()
        legacy.assert_not_called()

    def test_typer_path_restores_argv(self):
        # See note in test_legacy_path_restores_argv — differing argv[0]
        # is what gives this assertion discriminating power.
        original = ["/usr/local/bin/some-launcher", "chat", "--model", "gpt-4"]
        sys.argv = list(original)
        with mock.patch("praisonai.cli.app.app"), \
             mock.patch("praisonai.cli.app.register_commands"):
            dispatcher.main()
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")

    def test_typer_registration_failure_propagates(self):
        """``register_commands()`` errors must NOT be swallowed (fail-loud design)."""
        sys.argv = ["praisonai", "chat"]
        with mock.patch(
            "praisonai.cli.app.register_commands",
            side_effect=ImportError("missing optional dep"),
        ), self.assertRaises(ImportError):
            dispatcher.main()

    def test_systemexit_from_typer_propagates_code(self):
        sys.argv = ["praisonai", "chat"]
        fake_app = mock.MagicMock(side_effect=SystemExit(2))
        with mock.patch("praisonai.cli.app.app", fake_app), \
             mock.patch("praisonai.cli.app.register_commands"), \
             self.assertRaises(SystemExit) as cm:
            dispatcher.main()
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
