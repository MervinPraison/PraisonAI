"""A documented global flag, and a typo'd verb, must not become billed LLM calls."""

import sys
import unittest
from unittest import mock

import praisonai.__main__ as dispatcher


class TestDispatcherRouting(unittest.TestCase):
    def setUp(self):
        self._argv = sys.argv
        dispatcher._global_option_names_cache = None
        dispatcher._run_option_names_cache = None

    def tearDown(self):
        sys.argv = self._argv
        dispatcher._global_option_names_cache = None
        dispatcher._run_option_names_cache = None

    def route(self, argv):
        """Return ('typer'|'legacy', argv) or ('exit', (code, stderr))."""
        sys.argv = ["praisonai", *argv]
        with mock.patch.object(dispatcher, "_run_typer") as typer, \
             mock.patch.object(dispatcher, "_run_legacy") as legacy, \
             mock.patch("builtins.print") as printed:
            try:
                dispatcher.main()
            except SystemExit as exc:
                text = " ".join(str(c.args[0]) for c in printed.call_args_list if c.args)
                return "exit", (exc.code, text)
        if typer.called:
            return "typer", typer.call_args.args[0]
        return ("legacy", legacy.call_args.args[0]) if legacy.called else ("none", None)

    def test_output_format_long_and_short_form_reach_typer(self):
        # THE BUG: the long form used to be ('legacy', [...]) — `version`
        # dropped, `json` billed to an LLM, exit 0.
        self.assertEqual(self.route(["--output-format", "json", "version"]),
                         ("typer", ["--output-format", "json", "version"]))
        self.assertEqual(self.route(["-o", "json", "version"]),
                         ("typer", ["-o", "json", "version"]))

    def test_global_flag_is_hoisted_ahead_of_run(self):
        # Click accepts a group option only before the subcommand.
        self.assertEqual(self.route(["--output-format", "json", "hello"]),
                         ("typer", ["--output-format", "json", "run", "hello"]))
        self.assertEqual(self.route(["--output-format", "json", "agents.yaml"]),
                         ("typer", ["--output-format", "json", "run", "agents.yaml"]))

    def test_shared_short_opt_stays_with_run(self):
        # ``-o`` is declared by BOTH run and the root callback; never hoisted.
        self.assertNotIn("-o", dispatcher._global_only_option_names())
        self.assertEqual(self.route(["hello", "-o", "json"]),
                         ("typer", ["run", "hello", "-o", "json"]))

    def test_legacy_escape_hatch_survives(self):
        self.assertEqual(self.route(["agents.yaml", "--serve"]),
                         ("legacy", ["agents.yaml", "--serve"]))

    def test_typoed_verb_exits_2_without_llm_call(self):
        # THE BUG: used to reach `run` as the prompt "deploi", spend an LLM
        # call, create a session, and exit 1 after a wall of auth errors.
        for typo, expected in (("deploi", "deploy"), ("versoin", "version"),
                               ("cofig", "config"), ("memry", "memory")):
            kind, (code, text) = self.route([typo])
            self.assertEqual((kind, code), ("exit", 2), f"{typo!r}")
            self.assertIn(f"No such command '{typo}'", text)
            self.assertIn(expected, text, f"{typo!r} should suggest {expected!r}")

    def test_truncation_typo_exits_2_without_llm_call(self):
        # REGRESSION: a truncation of a command (``deplo`` for ``deploy``) is a
        # typo. It used to be spared by the ``cmd.startswith(first_cmd)`` half of
        # the prefix filter and forwarded to ``run``, spending a billed LLM call
        # per invocation. It must be caught and suggested, not billed.
        for typo, expected in (("deplo", "deploy"), ("versio", "version"),
                               ("serv", "serve"), ("tes", "test")):
            kind, (code, text) = self.route([typo])
            self.assertEqual((kind, code), ("exit", 2), f"{typo!r}")
            self.assertIn(f"No such command '{typo}'", text)
            self.assertIn(expected, text, f"{typo!r} should suggest {expected!r}")

    def test_genuine_prompts_are_untouched(self):
        self.assertEqual(self.route(["hello"]), ("typer", ["run", "hello"]))
        self.assertEqual(self.route(["deploi", "the", "app"]),
                         ("typer", ["run", "deploi the app"]))

    def test_plural_of_command_is_a_prompt_not_a_typo(self):
        # A plural/extension of a command word scores >= 0.8 on difflib but is a
        # legitimate one-word prompt, not a typo — it must reach ``run``, never
        # ``exit 2``. (``tests`` for ``test``, ``server`` for ``serve``, ...)
        for word in ("tests", "runs", "apps", "codes", "server"):
            self.assertEqual(
                self.route([word]),
                ("typer", ["run", word]),
                f"{word!r} is a valid prompt, must not be blocked as a typo",
            )
            self.assertEqual(
                dispatcher._mistyped_command_suggestions([word], word),
                [],
                f"{word!r} shares a command prefix; no suggestion",
            )

    def test_yaml_exact_command_and_failed_discovery_disable_the_guard(self):
        m = dispatcher._mistyped_command_suggestions
        self.assertEqual(m(["deploi.yaml"], "deploi.yaml"), [])
        self.assertEqual(m(["deploy"], "deploy"), [])
        with mock.patch.object(dispatcher, "_get_typer_commands", return_value=set()):
            self.assertEqual(m(["deploi"], "deploi"), [])


if __name__ == "__main__":
    unittest.main()
