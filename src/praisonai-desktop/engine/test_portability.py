"""The engine must behave the same on macOS, Windows and Linux.

Every test here runs on whatever platform the suite runs on, but asserts the
behaviour a *different* platform would otherwise get wrong -- so the regression
is caught on a laptop rather than in a bug report from a Windows user who can
only say "it doesn't work".

Where a defect is only reachable on another OS, the platform-dependent piece is
isolated behind a function taking the platform as an argument, so the branch is
exercised rather than merely written.
"""

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server                                            # noqa: E402


class DataDirectory(unittest.TestCase):
    """Where the app keeps transcripts and settings, per platform."""

    def test_macos_uses_application_support(self):
        got = server.default_data_dir("darwin", home=pathlib.PurePosixPath("/Users/x"), env={})
        self.assertEqual(str(got), "/Users/x/Library/Application Support/PraisonAI")

    def test_windows_uses_appdata_not_a_library_folder(self):
        got = server.default_data_dir(
            "win32", home=pathlib.PureWindowsPath(r"C:\Users\x"),
            env={"APPDATA": r"C:\Users\x\AppData\Roaming"})
        self.assertIn("AppData", str(got))
        self.assertNotIn("Library", str(got),
                         "a Library folder on Windows is excluded from roaming and backup")

    def test_windows_without_appdata_still_lands_somewhere_sensible(self):
        got = server.default_data_dir("win32", home=pathlib.PureWindowsPath(r"C:\Users\x"), env={})
        self.assertIn("x", str(got))
        self.assertNotIn("Library", str(got))

    def test_linux_honours_xdg_data_home(self):
        # Deliberately NOT ~/.local/share: the first version of this test used
        # the same path the fallback produces, so it passed whether or not the
        # variable was read at all. A value must differ from the default to
        # prove anything.
        got = server.default_data_dir(
            "linux", home=pathlib.PurePosixPath("/home/x"),
            env={"XDG_DATA_HOME": "/mnt/data/xdg"})
        self.assertEqual(str(got), "/mnt/data/xdg/PraisonAI")

    def test_linux_without_xdg_falls_back_to_the_spec_default(self):
        got = server.default_data_dir("linux", home=pathlib.PurePosixPath("/home/x"), env={})
        self.assertEqual(str(got), "/home/x/.local/share/PraisonAI")

    def test_the_explicit_override_wins_everywhere(self):
        for platform in ("darwin", "win32", "linux"):
            got = server.default_data_dir(
                platform, home=pathlib.PurePosixPath("/home/x"),
                env={"PRAISONAI_DESKTOP_HOME": "/tmp/chosen"})
            self.assertEqual(str(got), "/tmp/chosen", platform)


class SignalRegistration(unittest.TestCase):
    """The engine must not die registering a signal that does not exist."""

    def test_registering_signals_survives_a_platform_without_sighup(self):
        # Windows has no SIGHUP. Building the tuple `(SIGTERM, SIGINT, SIGHUP)`
        # dereferences it *before* any try block, so an AttributeError escapes
        # -- and it escapes AFTER the port is announced and the lockfile
        # written, so the shell adopts an engine that is already dead and every
        # request looks like a network fault.
        registered = []

        class FakeSignalModule:
            SIGTERM, SIGINT = 15, 2       # deliberately no SIGHUP
            @staticmethod
            def signal(sig, handler):
                registered.append(sig)

        server.register_exit_signals(lambda *_: None, module=FakeSignalModule)
        self.assertEqual(registered, [15, 2])

    def test_a_signal_the_platform_rejects_is_skipped_not_fatal(self):
        class Rejecting:
            SIGTERM, SIGINT, SIGHUP = 15, 2, 1
            @staticmethod
            def signal(sig, handler):
                if sig == 1:
                    raise OSError("cannot register SIGHUP here")

        server.register_exit_signals(lambda *_: None, module=Rejecting)   # must not raise

    def test_the_real_platform_registers_at_least_terminate_and_interrupt(self):
        import signal as real
        registered = []
        original = real.signal
        try:
            real.signal = lambda sig, handler: registered.append(sig)
            server.register_exit_signals(lambda *_: None)
        finally:
            real.signal = original
        self.assertIn(real.SIGTERM, registered)
        self.assertIn(real.SIGINT, registered)


class SecretStore(unittest.TestCase):
    """API keys must be storable on all three platforms, not just macOS."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-secret-")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_secret_round_trips_through_the_fallback_store(self):
        store = server.FileSecretStore(pathlib.Path(self.home))
        self.assertTrue(store.set("api_key", "sk-secret"))
        self.assertEqual(store.get("api_key"), "sk-secret")

    def test_clearing_a_secret_removes_it(self):
        store = server.FileSecretStore(pathlib.Path(self.home))
        store.set("api_key", "sk-secret")
        store.set("api_key", "")
        self.assertEqual(store.get("api_key"), "")

    def test_an_unset_secret_reads_as_empty_not_an_error(self):
        store = server.FileSecretStore(pathlib.Path(self.home))
        self.assertEqual(store.get("never_set"), "")

    def test_the_secret_is_never_briefly_world_readable(self):
        """The temp file must be 0600 from creation, not from a later chmod.

        Asserting only on the final mode passes even if the file is created
        0644 and chmodded afterwards -- which leaves a window where any local
        process can read the key. This inspects the file at the moment it is
        about to be renamed.
        """
        if os.name == "nt":
            self.skipTest("POSIX permission bits do not apply on Windows")
        store = server.FileSecretStore(pathlib.Path(self.home))
        seen = {}
        original = server._replace_with_retry
        try:
            def spy(tmp, target, attempts=4):
                seen["mode"] = tmp.stat().st_mode & 0o777
                return original(tmp, target, attempts)
            server._replace_with_retry = spy
            store.set("api_key", "sk-secret")
        finally:
            server._replace_with_retry = original
        self.assertEqual(seen.get("mode"), 0o600,
                         f"the secret was world-readable before the rename ({oct(seen.get('mode', 0))})")

    def test_the_secret_file_is_not_readable_by_other_users(self):
        store = server.FileSecretStore(pathlib.Path(self.home))
        store.set("api_key", "sk-secret")
        if os.name == "nt":
            self.skipTest("POSIX permission bits do not apply on Windows")
        mode = store.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, f"secrets are world-readable at {oct(mode)}")

    def test_secrets_never_land_in_settings_json(self):
        store = server.FileSecretStore(pathlib.Path(self.home))
        store.set("api_key", "sk-secret")
        settings = pathlib.Path(self.home) / "settings.json"
        if settings.exists():
            self.assertNotIn("sk-secret", settings.read_text())

    def test_a_store_is_chosen_for_every_platform(self):
        for platform in ("darwin", "win32", "linux", "freebsd"):
            store = server.secret_store_for(platform, pathlib.Path(self.home))
            self.assertTrue(hasattr(store, "get") and hasattr(store, "set"),
                            f"{platform} got no usable secret store")

    def test_a_failing_primary_store_falls_back_rather_than_losing_the_key(self):
        class Broken:
            path = pathlib.Path("/nonexistent")
            def get(self, key): return ""
            def set(self, key, value): return False

        store = server.FallbackSecretStore(Broken(), server.FileSecretStore(pathlib.Path(self.home)))
        self.assertTrue(store.set("api_key", "sk-secret"),
                        "a failing keychain must not make the app permanently unauthenticated")
        self.assertEqual(store.get("api_key"), "sk-secret")


class TestIsolation(unittest.TestCase):
    """Asking for an isolated home must isolate the secrets too."""

    def test_the_keychain_service_can_be_pointed_somewhere_harmless(self):
        # The system keyring is shared per user, so a test run against the
        # default service overwrites whatever key the developer actually uses
        # -- and the old value cannot be recovered. This happened once; the
        # override exists so it cannot happen again.
        self.assertTrue(
            os.environ.get("PRAISONAI_KEYCHAIN_SERVICE") or True)
        import importlib
        os.environ["PRAISONAI_KEYCHAIN_SERVICE"] = "ai.praison.desktop.test"
        try:
            reloaded = importlib.reload(server)
            self.assertEqual(reloaded.KEYCHAIN_SERVICE, "ai.praison.desktop.test")
        finally:
            os.environ.pop("PRAISONAI_KEYCHAIN_SERVICE", None)
            importlib.reload(server)


class Encoding(unittest.TestCase):
    """Files are UTF-8 everywhere, not whatever the machine's locale says."""

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="praison-enc-"))

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_non_ascii_path_in_the_lockfile_is_written_as_utf8(self):
        # Run under LC_ALL=C, where the default encoding is US-ASCII. On a Mac
        # the locale is already UTF-8, so an unencoded write_text looks correct
        # here and fails only on the user's machine -- the defect has to be
        # reproduced in a child process to be visible at all.
        #
        # The Rust side reads this file as strict UTF-8 and maps invalid bytes
        # to "absent", and absent means spawn: a user whose home directory is
        # not ASCII would get a second engine beside the live one every launch.
        target = self.home / "engine.lock"
        self._in_c_locale(
            f"server.write_lock_text(pathlib.Path({str(target)!r}), "
            f"'interpreter=C:\\\\Users\\\\\u7530\u4e2d\\\\python.exe\\n')")
        self.assertEqual(target.read_bytes().decode("utf-8"),
                         "interpreter=C:\\Users\\\u7530\u4e2d\\python.exe\n")

    def _in_c_locale(self, statement):
        """Run one statement against the engine with a non-UTF-8 locale."""
        import subprocess
        engine = os.path.dirname(os.path.abspath(server.__file__))
        code = ("import pathlib, sys\n"
                f"sys.path.insert(0, {engine!r})\n"
                "import server\n"
                f"{statement}\n")
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=dict(os.environ, LC_ALL="C", LANG="C",
                     PYTHONCOERCECLOCALE="0", PYTHONUTF8="0"),
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0,
                         f"failed under a C locale:\n{result.stderr[-800:]}")
        return result.stdout

    def test_a_utf8_text_file_is_read_as_utf8(self):
        source = self.home / "note.txt"
        source.write_text("caf\u00e9 \u2014 \u03b1\u03b2\u03b3", encoding="utf-8")
        self.assertEqual(server.read_text_file(source), "caf\u00e9 \u2014 \u03b1\u03b2\u03b3")

    def test_a_utf8_text_file_is_read_as_utf8_under_a_c_locale(self):
        # Without an explicit encoding this decodes as ASCII/cp1252 and, because
        # errors are replaced rather than raised, hands the model plausible
        # mojibake it will reason over confidently.
        source = self.home / "note.txt"
        source.write_text("caf\u00e9 \u2014 \u03b1\u03b2\u03b3", encoding="utf-8")
        out = self._in_c_locale(
            f"sys.stdout.buffer.write(server.read_text_file(pathlib.Path({str(source)!r}))"
            ".encode('utf-8'))")
        self.assertEqual(out, "caf\u00e9 \u2014 \u03b1\u03b2\u03b3")

    def test_an_undecodable_file_degrades_rather_than_raising(self):
        source = self.home / "binary.bin"
        source.write_bytes(b"ok \xff\xfe then")
        got = server.read_text_file(source)
        self.assertIn("ok", got)
        self.assertIn("then", got)


class SocketReuse(unittest.TestCase):
    """SO_REUSEADDR means different things on Windows and POSIX."""

    def test_address_reuse_is_off_on_windows(self):
        # On POSIX it means "reuse a TIME_WAIT address" and is right. On
        # Windows it means "another process may bind this exact address while
        # I am still listening" -- and this server carries API keys and
        # transcripts on unauthenticated loopback.
        self.assertFalse(server.allow_address_reuse("win32"))

    def test_address_reuse_is_on_elsewhere(self):
        self.assertTrue(server.allow_address_reuse("darwin"))
        self.assertTrue(server.allow_address_reuse("linux"))


class ProcessStartTime(unittest.TestCase):
    """The recycled-PID guard needs a real fingerprint on every platform."""

    def test_our_own_start_time_is_not_zero(self):
        # Zero is the "I could not tell" value. If it is returned on a platform,
        # every lockfile carries zero, every recycled pid compares equal, and
        # an unrelated process gets adopted as the engine.
        self.assertNotEqual(server._start_time(), 0,
                            "no start-time fingerprint on this platform")

    def test_the_same_process_fingerprints_the_same_way_twice(self):
        self.assertEqual(server._start_time(), server._start_time())

    def test_a_pid_that_does_not_exist_reports_zero(self):
        self.assertEqual(server._start_time(2 ** 22), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
