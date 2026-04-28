"""Unit tests for the unified CLI dispatcher in `praisonai.__main__`.

The dispatcher is Typer-first with a legacy fallback for bare prompts and
YAML invocations. It must:

  - Short-circuit on ``--version`` / ``-V`` before importing any heavy
    Typer or legacy modules (so version reporting stays fast even with
    broken optional deps).
  - Route ``--help`` / ``-h`` to Typer (so help text auto-discovers
    subcommands).
  - Route bare argv (no positional) to Typer.
  - Auto-discover registered Typer commands via Click introspection,
    cached behind a thread-safe lock that does not poison on failure.
  - Route the first non-flag positional through the discovered command
    set: known commands → Typer; everything else (prompts, YAML paths,
    legacy flags) → legacy.
  - Always restore ``sys.argv`` after dispatch — Typer mutates argv and
    legacy invocations also rewrite it.
  - Skip global flags (``--verbose``, ``-o`` + value, etc.) when looking
    for the first positional command.
"""

import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

import praisonai.__main__ as dispatcher


class TestFindFirstCommand(unittest.TestCase):
    """``_find_first_command`` skips global flags + value-flag values."""

    def test_returns_first_positional(self):
        self.assertEqual(dispatcher._find_first_command(["chat", "hello"]), "chat")

    def test_skips_leading_flags(self):
        self.assertEqual(dispatcher._find_first_command(["--verbose", "ui"]), "ui")
        self.assertEqual(dispatcher._find_first_command(["--debug", "--json", "chat"]), "chat")

    def test_skips_value_flags_and_their_values(self):
        # --output-format json should not be treated as the command.
        self.assertEqual(
            dispatcher._find_first_command(["--output-format", "json", "chat"]),
            "chat",
        )
        self.assertEqual(
            dispatcher._find_first_command(["-o", "yaml", "ui"]),
            "ui",
        )

    def test_only_flags_returns_none(self):
        self.assertIsNone(dispatcher._find_first_command(["--verbose", "--debug"]))

    def test_empty_argv_returns_none(self):
        self.assertIsNone(dispatcher._find_first_command([]))

    def test_yaml_path_returned_as_first(self):
        self.assertEqual(
            dispatcher._find_first_command(["agents.yaml"]),
            "agents.yaml",
        )

    def test_freetext_prompt_returned_as_first(self):
        # Whole token returned, including the embedded space.
        self.assertEqual(
            dispatcher._find_first_command(["Build a weather agent"]),
            "Build a weather agent",
        )


class TestGetTyperCommandsCache(unittest.TestCase):
    """``_get_typer_commands`` caches its result under a lock and does
    not poison the cache on failure."""

    def setUp(self):
        # Reset module-level cache between tests.
        dispatcher._typer_commands_cache = None

    def tearDown(self):
        dispatcher._typer_commands_cache = None

    def test_returns_set_on_success(self):
        result = dispatcher._get_typer_commands()
        self.assertIsInstance(result, set)
        # Cache is populated after a successful call.
        self.assertIsNotNone(dispatcher._typer_commands_cache)

    def test_cache_is_reused_on_second_call(self):
        first = dispatcher._get_typer_commands()
        second = dispatcher._get_typer_commands()
        self.assertIs(first, second)

    def test_failure_does_not_poison_cache(self):
        """If discovery fails, the next caller must be allowed to retry."""
        with mock.patch(
            "praisonai.cli.app.register_commands",
            side_effect=ImportError("simulated optional dep missing"),
        ):
            result = dispatcher._get_typer_commands()
        # Failed discovery returns an empty set ...
        self.assertEqual(result, set())
        # ... but the cache stays None so a subsequent call can retry.
        self.assertIsNone(dispatcher._typer_commands_cache)

    def test_concurrent_callers_get_same_result(self):
        """No double-initialization under contention."""
        results = []
        errors = []

        def worker():
            try:
                results.append(dispatcher._get_typer_commands())
            except Exception as e:  # pragma: no cover - unexpected
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # All threads must observe the same cached set object.
        first = results[0]
        for r in results[1:]:
            self.assertIs(r, first)


class TestVersionShortCircuit(unittest.TestCase):
    """``--version`` / ``-V`` must print and return without importing
    Typer or legacy modules."""

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

    def test_version_does_not_import_typer_or_legacy(self):
        """The version path is on the hot import path; it must stay light.

        We deliberately avoid ``mock.patch("praisonai.cli.app.register_commands")``
        and friends here: ``mock.patch`` with a dotted target imports the
        target module when the patch context is entered, which would
        defeat the invariant under test. Instead, evict any cached
        ``praisonai.cli.*`` modules from ``sys.modules`` before invoking
        ``main()`` and assert they remain absent afterwards.
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


class TestMainRouting(unittest.TestCase):
    """``main()`` routes argv to version / Typer / legacy according to
    routing rules 1-5 from the module docstring."""

    def setUp(self):
        self._saved_argv = sys.argv
        dispatcher._typer_commands_cache = None

    def tearDown(self):
        sys.argv = self._saved_argv
        dispatcher._typer_commands_cache = None

    def test_help_flag_routes_to_typer(self):
        sys.argv = ["praisonai", "--help"]
        with mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_short_help_flag_routes_to_typer(self):
        sys.argv = ["praisonai", "-h"]
        with mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_no_args_routes_to_typer(self):
        sys.argv = ["praisonai"]
        with mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_only_global_flags_routes_to_typer(self):
        """Argv with only flags (no positional command) → Typer for global flag handling."""
        sys.argv = ["praisonai", "--verbose"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_known_typer_command_routes_to_typer(self):
        sys.argv = ["praisonai", "fake-cmd", "--opt"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"fake-cmd"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_freetext_prompt_routes_to_legacy(self):
        sys.argv = ["praisonai", "Create a weather app"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_legacy.assert_called_once()
        run_typer.assert_not_called()

    def test_yaml_path_routes_to_legacy(self):
        # Routing decision is by command-set membership, NOT by file
        # existence — the original auto-discovery dispatcher does not
        # touch the filesystem.
        sys.argv = ["praisonai", "agents.yaml"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_legacy.assert_called_once()
        run_typer.assert_not_called()

    def test_unknown_command_routes_to_legacy(self):
        sys.argv = ["praisonai", "totally-unknown"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_legacy.assert_called_once()
        run_typer.assert_not_called()


class TestRunLegacyArgvRestoration(unittest.TestCase):
    """``_run_legacy`` must always restore ``sys.argv``, even on
    SystemExit, AND that restoration must have discriminating power."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_argv_restored_after_normal_exit(self):
        # NOTE: argv[0] differs from the dispatcher's rewrite ("praisonai")
        # so the assertion has discriminating power: if the ``finally``
        # clause were missing, ``sys.argv[0]`` would still be "praisonai"
        # after dispatch, and the equality check would fail.
        original = ["/usr/local/bin/some-launcher", "agents.yaml"]
        sys.argv = list(original)

        fake = mock.MagicMock()
        fake.main.return_value = None

        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher._run_legacy(["agents.yaml"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")  # invariant pin

    def test_argv_restored_after_systemexit(self):
        original = ["/usr/local/bin/some-launcher", "topic"]
        sys.argv = list(original)

        fake = mock.MagicMock()
        fake.main.side_effect = SystemExit(2)

        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher._run_legacy(["topic"])

        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")

    def test_main_returning_false_translates_to_exit_code_1(self):
        sys.argv = ["/usr/local/bin/some-launcher", "topic"]
        fake = mock.MagicMock()
        fake.main.return_value = False
        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher._run_legacy(["topic"])
        self.assertEqual(cm.exception.code, 1)


class TestRunTyperArgvRestoration(unittest.TestCase):
    """``_run_typer`` must restore argv even if the Typer app raises."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_argv_restored_after_systemexit(self):
        original = ["/usr/local/bin/some-launcher", "chat"]
        sys.argv = list(original)
        with mock.patch("praisonai.cli.app.register_commands"), \
             mock.patch("praisonai.cli.app.app", side_effect=SystemExit(0)), \
             self.assertRaises(SystemExit):
            dispatcher._run_typer(["chat"])
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")


class TestTyperRegistrationFailureFailsLoud(unittest.TestCase):
    """``_run_typer`` must NOT swallow ``register_commands()`` exceptions.

    A registration failure (e.g. ``ImportError`` from a missing optional
    dependency) is a real misconfiguration: the user should see the
    underlying error rather than a silent fallback to "no commands
    registered". A future refactor that wraps ``register_commands()`` in a
    defensive try/except inside ``_run_typer`` would silently downgrade
    that to Typer's empty-app behaviour, so this test pins the invariant.
    """

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_register_commands_importerror_propagates(self):
        sys.argv = ["praisonai", "chat"]
        with mock.patch(
            "praisonai.cli.app.register_commands",
            side_effect=ImportError("missing optional dep 'fakemod'"),
        ), self.assertRaises(ImportError) as cm:
            dispatcher._run_typer(["chat"])
        self.assertIn("fakemod", str(cm.exception))

    def test_register_commands_runtimeerror_propagates(self):
        sys.argv = ["praisonai", "chat"]
        with mock.patch(
            "praisonai.cli.app.register_commands",
            side_effect=RuntimeError("registration broke"),
        ), self.assertRaises(RuntimeError) as cm:
            dispatcher._run_typer(["chat"])
        self.assertIn("registration broke", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
