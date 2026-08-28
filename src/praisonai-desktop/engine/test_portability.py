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
import re
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server                                            # noqa: E402


class DataDirectory(unittest.TestCase):
    """Where the app keeps transcripts and settings, per platform."""

    def test_macos_uses_application_support(self):
        got = server.default_data_dir("darwin", home=pathlib.PurePosixPath("/Users/x"), env={})
        self.assertEqual(got.as_posix(), "/Users/x/Library/Application Support/PraisonAI")

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
        self.assertEqual(got.as_posix(), "/mnt/data/xdg/PraisonAI")

    def test_linux_without_xdg_falls_back_to_the_spec_default(self):
        got = server.default_data_dir("linux", home=pathlib.PurePosixPath("/home/x"), env={})
        self.assertEqual(got.as_posix(), "/home/x/.local/share/PraisonAI")

    def test_the_explicit_override_wins_everywhere(self):
        for platform in ("darwin", "win32", "linux"):
            got = server.default_data_dir(
                platform, home=pathlib.PurePosixPath("/home/x"),
                env={"PRAISONAI_DESKTOP_HOME": "/tmp/chosen"})
            self.assertEqual(got.as_posix(), "/tmp/chosen", platform)


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


class HealthReportsWhereItLives(unittest.TestCase):
    """The UI offers to copy the data folder, so the engine must name it.

    The path can be overridden by PRAISONAI_DESKTOP_HOME, and on Linux by
    XDG_DATA_HOME, so a page that reproduces the default hands the user a
    directory the app is not using.
    """

    def test_the_health_response_names_the_directory_in_use(self):
        import json as _json
        import subprocess as _sp
        import sys as _sys
        import urllib.request as _url

        home = tempfile.mkdtemp(prefix="praison-health-")
        engine = os.path.join(os.path.dirname(os.path.abspath(server.__file__)), "server.py")
        proc = _sp.Popen([_sys.executable, "-u", engine],
                         env=dict(os.environ, PRAISONAI_DESKTOP_HOME=home,
                                  PRAISONAI_DESKTOP_VERSION="4.7.3",
                                  PRAISONAI_KEYCHAIN_SERVICE="ai.praison.desktop.test"),
                         stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True)
        try:
            port = None
            deadline = time.time() + 60
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                if "PRAISONAI_PORT=" in line:
                    port = int(line.split("PRAISONAI_PORT=")[1].strip())
                    break
            self.assertIsNotNone(port, "the engine never announced a port")
            with _url.urlopen(f"http://127.0.0.1:{port}/health", timeout=15) as r:
                health = _json.loads(r.read())
            self.assertEqual(health.get("data_dir"), home,
                             "health does not report the directory actually in use")
            self.assertEqual(health.get("shell_version"), "4.7.3")
            self.assertIn("agents_version", health)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                proc.kill()
            shutil.rmtree(home, ignore_errors=True)


class LeafStoreDeletion(unittest.TestCase):
    """The real stores, not a stand-in.

    FallbackSecretStore was hardened so a delete must succeed everywhere it
    could be read from -- but it was only ever tested against a fake, and the
    real leaves underneath it returned True whatever happened. The write path
    checked its exit status; the delete path did not. A locked keychain, or a
    Linux session with no D-Bus, left the credential intact and reported that
    it had been removed. It then came back on the next launch.

    A fake binary on PATH stands in for `security` / `secret-tool`, so this
    never touches a real keychain.
    """

    def setUp(self):
        # These leaves are the macOS keychain (`security`) and Linux libsecret
        # (`secret-tool`); neither exists on Windows, and the fakes that stand
        # in for them are `#!/bin/sh` scripts a Windows shell cannot execute.
        if os.name == "nt":
            self.skipTest("the keychain and secret-tool stores are POSIX-only")
        self.bin = tempfile.mkdtemp(prefix="praison-fakebin-")
        self.old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = self.bin + os.pathsep + self.old_path

    def tearDown(self):
        # setUp skips before these are set on Windows.
        if getattr(self, "bin", None) is None:
            return
        os.environ["PATH"] = self.old_path
        shutil.rmtree(self.bin, ignore_errors=True)

    def _fake(self, name, script):
        path = pathlib.Path(self.bin) / name
        path.write_text("#!/bin/sh\n" + script, encoding="utf-8")
        path.chmod(0o755)

    def test_a_locked_keychain_does_not_report_a_successful_delete(self):
        # 51 is what `security` returns when the keychain will not unlock.
        self._fake("security", 'if [ "$1" = "delete-generic-password" ]; then exit 51; fi\nexit 0\n')
        self.assertFalse(server.KeychainSecretStore().set("api_key", ""),
                         "a delete that could not happen reported success")

    def test_deleting_something_already_absent_is_a_success(self):
        # 44 is "no such item". The key is gone, which is what was asked for.
        self._fake("security", 'if [ "$1" = "delete-generic-password" ]; then exit 44; fi\nexit 0\n')
        self.assertTrue(server.KeychainSecretStore().set("api_key", ""),
                        "an already-absent key was reported as a failed delete")

    def test_a_keychain_delete_that_works_still_reports_success(self):
        self._fake("security", "exit 0\n")
        self.assertTrue(server.KeychainSecretStore().set("api_key", ""))

    def test_secret_tool_failure_is_not_reported_as_a_delete(self):
        # No D-Bus session: `secret-tool` cannot reach the collection.
        self._fake("secret-tool", 'if [ "$1" = "clear" ]; then exit 1; fi\nexit 0\n')
        self.assertFalse(server.SecretToolSecretStore().set("api_key", ""),
                         "a delete that could not happen reported success")

    def test_secret_tool_success_is_reported(self):
        # `secret-tool clear` exits 0 whether or not it matched anything.
        self._fake("secret-tool", "exit 0\n")
        self.assertTrue(server.SecretToolSecretStore().set("api_key", ""))


class SecretDeletion(unittest.TestCase):
    """Clearing a secret must clear it everywhere it could have landed.

    The fallback exists so a machine with no keyring can still save a key. The
    consequence nobody planned for: once a secret has been written to *both*
    stores -- keyring unavailable, then available again -- a delete that
    short-circuits on the first success leaves the other copy behind, and the
    read path happily serves it. "Remove my API key" then reports success and
    the key keeps working, with the plaintext still on disk.
    """

    class Flaky:
        """A store that can be switched off, like a locked keyring."""

        path = None

        def __init__(self):
            self.values, self.up = {}, True
            self.frozen = False        # readable, but accepts no writes

        def get(self, name):
            return self.values.get(name, "") if self.up else ""

        def set(self, name, value):
            if not self.up or self.frozen:
                return False
            if value:
                self.values[name] = value
            else:
                self.values.pop(name, None)
            return True

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="praison-del-")
        self.primary = self.Flaky()
        self.file = server.FileSecretStore(pathlib.Path(self.home))
        self.store = server.FallbackSecretStore(self.primary, self.file)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_secret_written_to_both_stores_is_deleted_from_both(self):
        self.primary.up = False
        self.store.set("api_key", "sk-old")             # lands in the file
        self.primary.up = True
        self.store.set("api_key", "sk-new")             # lands in the keyring
        self.assertEqual(self.store.get("api_key"), "sk-new")

        self.assertTrue(self.store.set("api_key", ""))  # the user clears it
        self.assertEqual(self.store.get("api_key"), "",
                         "the old key was resurrected from the fallback store")
        self.assertEqual(self.file.get("api_key"), "",
                         "the plaintext copy is still on disk after a delete")

    def test_a_delete_reaches_the_fallback_even_when_the_primary_works(self):
        self.store.set("api_key", "sk-value")
        self.file.set("api_key", "sk-stale-copy")       # however it got there
        self.store.set("api_key", "")
        self.assertEqual(self.file.get("api_key"), "")

    def test_a_delete_that_no_store_can_satisfy_reports_failure(self):
        self.primary.up = False
        # A *file* stands where the store wants a directory, so mkdir fails
        # with NotADirectoryError on every platform -- unlike a made-up
        # absolute path, which a Windows runner may happily create.
        blocker = pathlib.Path(self.home) / "not-a-directory"
        blocker.write_text("", encoding="utf-8")
        broken = server.FileSecretStore(blocker / "store")
        store = server.FallbackSecretStore(self.primary, broken)
        self.assertFalse(store.set("api_key", ""),
                         "a delete nothing could perform reported success")

    def test_a_delete_the_fallback_could_not_perform_is_not_reported_as_success(self):
        # The key is in both stores and the file store cannot be written to.
        # Reporting success here told the user the key was gone while `get`
        # went on serving the plaintext copy.
        if os.name == "nt":
            # The precondition is an unwritable store, established with
            # chmod(0o500). Windows does not honour POSIX mode bits for
            # directory writability, so the delete would succeed and the
            # scenario this guards -- a store that *cannot* perform the delete
            # -- is unreachable here.
            self.skipTest("chmod(0o500) does not make a directory unwritable on Windows")
        self.store.set("api_key", "sk-live")
        # A copy in the fallback that a successful primary write did not clear
        # -- written by an older build, or left by a crash between the two
        # writes. However it got there, `get` can still read it.
        self.file.set("api_key", "sk-live")
        self.file.path.parent.chmod(0o500)          # nothing may be written
        try:
            reported = self.store.set("api_key", "")
            still_readable = self.store.get("api_key")
        finally:
            self.file.path.parent.chmod(0o700)
        self.assertEqual(still_readable, "sk-live",
                         "the fallback copy was cleared after all; rework this test")
        self.assertFalse(reported,
                         "a delete that left a readable secret reported success")

    def test_a_new_key_the_primary_cannot_take_is_the_one_that_gets_used(self):
        # The primary holds an old key and has become unwritable. Saving a new
        # one must not leave the old one shadowing it: the user saves, is told
        # it worked, and the app keeps using the previous key.
        self.store.set("api_key", "sk-old")
        self.primary.frozen = True                  # accepts nothing further
        reported = self.store.set("api_key", "sk-new")
        if reported:
            self.assertEqual(self.store.get("api_key"), "sk-new",
                             "the save reported success but the old key is still in use")

    def test_a_file_that_will_not_parse_does_not_destroy_the_other_secrets(self):
        # One unreadable read used to mean "empty", and the next write laid a
        # fresh file over the top.
        self.file.set("api_key", "sk-keep")
        self.file.set("other_key", "other-keep")
        self.file.path.write_text("{ this is not json", encoding="utf-8")
        self.assertFalse(self.file.set("api_key", "sk-new"),
                         "wrote over a file it could not read")
        self.assertEqual(self.file.get("api_key"), "",
                         "an unreadable store should read as empty, not raise")
        self.file.path.write_text('{"api_key": "sk-keep", "other_key": "other-keep"}',
                                  encoding="utf-8")
        self.assertEqual(self.file.get("other_key"), "other-keep",
                         "the other secret did not survive")

    def test_writing_a_new_secret_does_not_leave_the_old_one_in_the_fallback(self):
        self.primary.up = False
        self.store.set("api_key", "sk-old")
        self.primary.up = True
        self.store.set("api_key", "sk-new")
        self.assertNotEqual(self.file.get("api_key"), "sk-old",
                            "a superseded key is still readable in plaintext")


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
        """Run one statement against the engine with a non-UTF-8 locale.

        The statement goes through a file rather than `-c`. Python decodes the
        `-c` argument with the filesystem encoding, which under LC_ALL=C on
        Linux is ASCII with surrogateescape -- so a non-ASCII character in the
        statement itself arrived as unpaired surrogates and died before
        reaching the code under test. Source *files* are read as UTF-8
        regardless of locale (PEP 3120), so this tests what it means to.
        """
        import subprocess
        engine = os.path.dirname(os.path.abspath(server.__file__))
        code = ("import pathlib, sys\n"
                f"sys.path.insert(0, {engine!r})\n"
                "import server\n"
                f"{statement}\n")
        script = pathlib.Path(self.home) / "_c_locale_case.py"
        script.write_text(code, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(script)],
            env=dict(os.environ, LC_ALL="C", LANG="C",
                     PYTHONCOERCECLOCALE="0", PYTHONUTF8="0"),
            # encoding, not bare text=True: text=True decodes the child's
            # output with the *parent's* default encoding -- cp1252 on a
            # Windows runner -- so a test about UTF-8 handling was reading its
            # own result through a locale codec and failing on the round trip
            # rather than on anything the engine did.
            capture_output=True, text=True, encoding="utf-8", timeout=60)
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


class HashContract(unittest.TestCase):
    """The engine and the Rust shell must fingerprint a process identically.

    The same table is asserted in src-tauri/src/reclaim.rs. If either side's
    hashing drifts, both suites fail rather than the two silently disagreeing
    -- and disagreement here is invisible in the worst way: every live engine
    looks like a recycled pid, so a second one is started beside it on every
    launch, forever, with no error anywhere.
    """

    FIXTURES = [
        (1234, 133_000_000_000_000_000, 8_396_559_443_335_285_342),
        (1, 0, 4_995_674_065_236_331_046),
        (65535, 9_223_372_036_854_775_815, 742_000_315_636_326_002),
    ]

    def test_the_windows_start_key_hashes_as_the_shell_expects(self):
        for pid, stamp, expected in self.FIXTURES:
            self.assertEqual(server._fnv1a64(f"{pid}:{stamp}"), expected,
                             f"pid {pid} stamp {stamp}")

    def test_the_rust_side_asserts_the_identical_table(self):
        # A fixture table that lives in only one language is not a contract.
        rust = pathlib.Path(__file__).resolve().parents[1] / "src-tauri/src/reclaim.rs"
        self.assertTrue(rust.exists(), f"{rust} is missing")
        text = rust.read_text(encoding="utf-8")
        for _, _, expected in self.FIXTURES:
            grouped = f"{expected:_}"          # Rust writes 8_396_559_443_335_285_342
            self.assertTrue(grouped in text or str(expected) in text,
                            f"the shell does not assert the fixture {expected}")

    def test_fnv1a64_stays_a_64_bit_value(self):
        for pid, stamp, _ in self.FIXTURES:
            self.assertLess(server._fnv1a64(f"{pid}:{stamp}"), 2 ** 64)


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


class StreamProtocolVocabulary(unittest.TestCase):
    """The documented stream-protocol events must match the ones emitted.

    A comment cannot fail CI, so the "stream protocol v2" block in server.py
    drifted: it listed nine events while the engine emitted eleven, and the two
    missing ones included approval_request -- the human-in-the-loop tool gate a
    client cannot render if it never hears the event. This test makes the
    comment a checked artifact: every emit(...) call site's name must appear in
    the documented list, and every documented name must be emitted, so either
    direction of drift fails here rather than silently on the wire.
    """

    SOURCE = pathlib.Path(server.__file__).resolve()

    EXPECTED = {
        "start", "reasoning", "delta", "tool_drafting", "tool_call",
        "tool_result", "approval_request", "usage", "cancelled", "error", "end",
    }

    @classmethod
    def setUpClass(cls):
        cls.text = cls.SOURCE.read_text(encoding="utf-8")

    def _documented_events(self):
        """The event names listed under the 'stream protocol v2' comment."""
        marker = "--- stream protocol v2"
        start = self.text.index(marker)
        block = self.text[start:self.text.index("\ndef ", start)]
        events = set()
        for line in block.splitlines():
            m = re.match(r"#\s+([a-z_]+)\s+\{", line)
            if m:
                events.add(m.group(1))
        return events

    def _emitted_events(self):
        """Every literal event name the engine can put on the wire.

        Two dispatch forms reach the socket. Most call sites name the event
        inline -- emit("delta", ...) -- and the first pattern catches those.
        The stream loop also forwards a *variable*: emit(event, frame), where
        event comes from _classify_stream_item. A name added to that classifier
        would drift onto the wire invisibly to a guard that only reads literal
        emit() arguments, so the second pattern reads the classifier's returned
        events as well -- the only place the variable is assigned.
        """
        literal = re.findall(r'(?:_emit_now|emit)\(\s*"([a-z_]+)"', self.text)
        classified = re.findall(
            r'return\s+"([a-z_]+)"\s*,', self._classifier_block())
        return set(literal) | set(classified)

    def _classifier_block(self):
        """The body of _classify_stream_item, source of the forwarded event."""
        start = self.text.index("def _classify_stream_item")
        return self.text[start:self.text.index("\ndef ", start + 1)]

    def test_every_emitted_event_is_documented(self):
        documented = self._documented_events()
        undocumented = self._emitted_events() - documented
        self.assertEqual(
            undocumented, set(),
            f"these events are emitted but not documented in the "
            f"stream-protocol comment: {sorted(undocumented)}")

    def test_every_documented_event_is_emitted(self):
        emitted = self._emitted_events()
        unemitted = self._documented_events() - emitted
        self.assertEqual(
            unemitted, set(),
            f"these events are documented but never emitted -- the comment is "
            f"stale: {sorted(unemitted)}")

    def test_the_two_events_the_drift_hid_are_present(self):
        # The specific regression: approval_request and tool_drafting were live
        # on the wire and absent from the spec.
        documented = self._documented_events()
        for event in ("approval_request", "tool_drafting"):
            self.assertIn(event, documented,
                          f"{event} is emitted but missing from the spec again")

    def test_the_vocabulary_is_the_eleven_events_expected(self):
        # A belt-and-braces check so a matched pair of *both* sides drifting
        # (an event added to the comment and an emitter in the same PR, but
        # neither reviewed) is still measured against a fixed expectation.
        self.assertEqual(self._documented_events(), self.EXPECTED)
        self.assertEqual(self._emitted_events(), self.EXPECTED)


class LaunchAtLogin(unittest.TestCase):
    """The toggle must persist what actually happened, not what was asked.

    Registering a login item only works in the installed macOS .app bundle:
    `set_launch_at_login` returns {"enabled": False} everywhere else -- every
    Windows and Linux user, and any macOS user running from a checkout. The
    handler used to save the *request* and merely attach the honest result to
    the response, which nothing read. So the toggle rendered on, persisted, and
    survived restarts while no login item existed anywhere.
    """

    def setUp(self):
        import io

        self.home = pathlib.Path(tempfile.mkdtemp(prefix="praison-launch-"))
        self._data_dir = server.DATA_DIR
        self._settings_path = server.SETTINGS_PATH
        self._set = server.set_launch_at_login
        server.DATA_DIR = self.home
        server.SETTINGS_PATH = self.home / "settings.json"
        self._io = io

    def tearDown(self):
        server.DATA_DIR = self._data_dir
        server.SETTINGS_PATH = self._settings_path
        server.set_launch_at_login = self._set
        shutil.rmtree(self.home, ignore_errors=True)

    def _post_settings(self, patch):
        """Drive the real /settings POST handler and return its JSON reply."""
        body = json.dumps(patch).encode()

        class FakeHandler(server.Handler):
            def __init__(self):
                self.path = "/settings"
                self.headers = {"Content-Length": str(len(body))}
                self.rfile = self._io_module.BytesIO(body)
                self.wfile = self._io_module.BytesIO()

            def send_response(self, *_a, **_k):
                pass

            def send_header(self, *_a, **_k):
                pass

            def end_headers(self):
                pass

        FakeHandler._io_module = self._io
        handler = FakeHandler()
        handler.do_POST()
        raw = handler.wfile.getvalue()
        return json.loads(raw) if raw else {}

    def test_a_request_that_could_not_register_is_not_persisted_as_on(self):
        # Stub the platform action to the answer every non-bundle host gives.
        server.set_launch_at_login = lambda on: {
            "ok": False, "enabled": False,
            "message": "Only available in the installed app."}

        reply = self._post_settings({"launch_at_login": True})

        self.assertFalse(reply.get("launch_at_login"),
                         "the toggle reported on though nothing was registered")
        self.assertEqual(
            reply.get("launch_at_login_result", {}).get("message"),
            "Only available in the installed app.",
            "the response dropped the explanation for why it did not stick")
        self.assertFalse(
            server.load_settings().get("launch_at_login"),
            "the un-registered login item survived to the next launch")

    def test_a_request_that_registered_is_persisted_as_on(self):
        server.set_launch_at_login = lambda on: {"ok": True, "enabled": bool(on)}

        reply = self._post_settings({"launch_at_login": True})

        self.assertTrue(reply.get("launch_at_login"))
        self.assertTrue(server.load_settings().get("launch_at_login"),
                        "a real registration did not persist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
