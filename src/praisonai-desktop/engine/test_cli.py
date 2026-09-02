"""The headless CLI must drive the engine the app does, and only that.

These tests exercise the parts that can be checked without a live engine or a
network: the doctor's version comparison (the command that answers a version
report), the required-floor read from provision.rs (which must not drift from
the Rust source of truth), the lockfile parser, and the SSE stream reader that
turns a turn's frames back into text and tool counts.
"""

import io
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
DESKTOP = HERE.parent
sys.path.insert(0, str(DESKTOP))
import cli  # noqa: E402


class Args:
    """A stand-in for the argparse namespace the command functions take."""

    def __init__(self, **kw):
        self.home = None
        self.__dict__.update(kw)


class RequiredFloor(unittest.TestCase):
    """The floor doctor checks against comes from provision.rs, not a constant."""

    def test_reads_the_provisioned_floor(self):
        floor = cli._required_floor()
        self.assertIsNotNone(floor, "provision.rs no longer states a praisonaiagents floor")
        # A version, not a range fragment: it must be usable with _vtuple.
        self.assertRegex(floor, r"^\d+\.\d+")

    def test_floor_is_the_one_the_shell_provisions(self):
        # The value here is not asserted verbatim -- that would just duplicate
        # the constant -- but it must parse to a tuple, which is all doctor
        # needs to compare installed against required.
        floor = cli._required_floor()
        self.assertGreaterEqual(len(cli.server._vtuple(floor)), 2)


class LockfileParsing(unittest.TestCase):
    def test_absent_lock_is_none_not_an_error(self):
        self.assertIsNone(cli._lockfile_fields(home="/definitely/not/a/dir"))

    def test_fields_are_parsed_key_by_key(self, ):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "engine.lock").write_text(
                "format_version=2\nport=54321\npid=999\n", encoding="utf-8")
            fields = cli._lockfile_fields(home=d)
        self.assertEqual(fields["port"], "54321")
        self.assertEqual(fields["pid"], "999")


class SseReader(unittest.TestCase):
    """The stream reader must recover text and tool counts from raw frames."""

    def _frames(self, blob):
        return list(cli._iter_sse(io.BytesIO(blob.encode())))

    def test_delta_frames_yield_text(self):
        events = self._frames(
            'event: delta\ndata: {"text": "Hi "}\n\n'
            'event: delta\ndata: {"text": "there"}\n\n')
        text = "".join(p["text"] for e, p in events if e == "delta")
        self.assertEqual(text, "Hi there")

    def test_a_non_json_data_line_is_skipped_not_fatal(self):
        events = self._frames(
            'event: delta\ndata: not json\n\n'
            'event: delta\ndata: {"text": "ok"}\n\n')
        self.assertEqual([p["text"] for e, p in events if e == "delta"], ["ok"])


class Doctor(unittest.TestCase):
    """doctor exits non-zero exactly when the installed engine is too old."""

    def _run(self, installed, floor):
        real_installed = cli.server._installed_version
        real_floor = cli._required_floor
        real_port = cli._live_port
        cli.server._installed_version = lambda: installed
        cli._required_floor = lambda: floor
        cli._live_port = lambda home=None: None
        buf = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = buf
        try:
            code = cli.cmd_doctor(Args())
        finally:
            sys.stdout = real_stdout
            cli.server._installed_version = real_installed
            cli._required_floor = real_floor
            cli._live_port = real_port
        return code, buf.getvalue()

    def test_below_floor_is_a_problem(self):
        code, out = self._run("1.7.1", "1.7.2")
        self.assertEqual(code, 1)
        self.assertIn("below the required floor", out)

    def test_at_or_above_floor_passes(self):
        code, out = self._run("1.7.3", "1.7.2")
        self.assertEqual(code, 0)
        self.assertIn("All checks passed", out)

    def test_missing_install_is_a_problem(self):
        code, out = self._run("unknown", "1.7.2")
        self.assertEqual(code, 1)
        self.assertIn("not installed", out)


class ParserWiring(unittest.TestCase):
    """Every subcommand parses and binds to a handler."""

    def test_subcommands_bind_to_functions(self):
        parser = cli.build_parser()
        for argv, func in (
            (["engine", "start"], cli.cmd_engine_start),
            (["engine", "health"], cli.cmd_engine_health),
            (["chat", "hello"], cli.cmd_chat),
            (["doctor"], cli.cmd_doctor),
        ):
            args = parser.parse_args(argv)
            self.assertIs(args.func, func)

    def test_chat_defaults_deny_approval(self):
        args = cli.build_parser().parse_args(["chat", "hi"])
        self.assertFalse(args.approve)

    def test_chat_approve_flag(self):
        args = cli.build_parser().parse_args(["chat", "hi", "--approve"])
        self.assertTrue(args.approve)


class LivePort(unittest.TestCase):
    """Only *our* engine is adopted: ok plus the right protocol version."""

    def _run(self, fields, health):
        real_fields = cli._lockfile_fields
        real_http = cli._http_json
        cli._lockfile_fields = lambda home=None: fields
        cli._http_json = lambda url, timeout=4.0: health
        try:
            return cli._live_port()
        finally:
            cli._lockfile_fields = real_fields
            cli._http_json = real_http

    def test_matching_protocol_is_adopted(self):
        port = self._run({"port": "5000"},
                         {"ok": True, "version": cli.server.PROTOCOL_VERSION})
        self.assertEqual(port, "5000")

    def test_wrong_protocol_is_rejected(self):
        # A recycled port answered by an unrelated loopback service.
        port = self._run({"port": "5000"},
                         {"ok": True, "version": cli.server.PROTOCOL_VERSION + 99})
        self.assertIsNone(port)

    def test_not_ok_is_rejected(self):
        port = self._run({"port": "5000"}, {"ok": False})
        self.assertIsNone(port)


class ApprovalAnswer(unittest.TestCase):
    """A headless turn answers the approval gate rather than blocking on it."""

    def test_posts_choice_to_approve_route(self):
        sent = {}

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _fake_urlopen(req, timeout=None):
            sent["url"] = req.full_url
            sent["body"] = req.data
            return _FakeResp()

        real = cli.urllib.request.urlopen
        cli.urllib.request.urlopen = _fake_urlopen
        try:
            cli._answer_approval("5000", {"approval_id": "ap_1"}, "deny")
        finally:
            cli.urllib.request.urlopen = real
        self.assertIn("/approve/ap_1", sent["url"])
        self.assertIn(b"deny", sent["body"])

    def test_missing_id_is_a_noop(self):
        called = []
        real = cli.urllib.request.urlopen
        cli.urllib.request.urlopen = lambda *a, **k: called.append(1)
        try:
            cli._answer_approval("5000", {}, "deny")
        finally:
            cli.urllib.request.urlopen = real
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
