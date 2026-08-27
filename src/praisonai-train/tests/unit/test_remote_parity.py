"""The same instruction, three ways.

Where a run executes has to be expressible as a YAML block, as CLI flags, and
by the desktop form -- and mean the same thing in each. Three surfaces over one
set of facts is exactly the arrangement that drifts, so the parity is asserted
rather than described.

Nothing here contacts a remote machine.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from praisonai_train.remote import settings  # noqa: E402


class TestParity:
    def test_every_key_has_a_flag_and_every_flag_is_distinct(self):
        keys = [k for k, _f, _d, _h in settings.REMOTE_KEYS]
        flags = [f for _k, f, _d, _h in settings.REMOTE_KEYS]
        assert len(set(keys)) == len(keys), f"duplicate keys: {keys}"
        assert len(set(flags)) == len(flags), f"duplicate flags: {flags}"
        for key, flag, _d, _h in settings.REMOTE_KEYS:
            assert flag == "--remote-" + key.replace("_", "-"), (
                f"{key} and {flag} do not name the same thing")

    def test_the_cli_declares_exactly_those_flags(self):
        """The llm command must accept every key, and invent none."""
        from praisonai_train.cli.commands import train as train_cmd

        import inspect
        params = inspect.signature(train_cmd.train_llm).parameters
        for key, flag, _d, _h in settings.REMOTE_KEYS:
            name = f"remote_{key}"
            assert name in params, f"{flag} is declared in the table but not on the CLI"
        declared = {p for p in params if p.startswith("remote_")}
        expected = {f"remote_{k}" for k, _f, _d, _h in settings.REMOTE_KEYS}
        assert declared == expected, (
            f"the CLI and the table disagree: {declared ^ expected}")

    def test_every_key_is_documented(self):
        for key, _flag, _default, help_text in settings.REMOTE_KEYS:
            assert help_text and help_text.strip(), f"{key} has no help"


class TestResolution:
    def test_no_remote_block_means_train_here(self):
        assert settings.resolve({}, {}) == {}
        assert settings.resolve({"model_name": "x"}, {}) == {}

    def test_a_host_in_yaml_is_enough(self):
        got = settings.resolve({"remote": {"host": "gpubox"}}, {})
        assert got["host"] == "gpubox"
        assert got["python"] == "python3"
        assert got["workdir"] == "~/.praisonai-train"

    def test_a_flag_beats_the_file(self):
        got = settings.resolve({"remote": {"host": "from-yaml", "gpus": 1}},
                               {"host": "from-flag", "gpus": 4})
        assert got["host"] == "from-flag"
        assert got["gpus"] == 4

    def test_a_flag_alone_is_enough(self):
        got = settings.resolve({}, {"host": "gpubox"})
        assert got["host"] == "gpubox"

    def test_an_absent_flag_does_not_erase_the_file(self):
        got = settings.resolve({"remote": {"host": "gpubox", "python": "/opt/py"}},
                               {"host": None, "python": None})
        assert got["python"] == "/opt/py"


class TestRefusals:
    def test_an_unknown_key_is_named(self):
        with pytest.raises(settings.RemoteSettingsError) as caught:
            settings.resolve({"remote": {"host": "h", "hostname": "typo"}}, {})
        assert "hostname" in str(caught.value)

    def test_a_credential_in_the_config_is_refused(self):
        # The file is shipped to the remote host and printed by --dry-run.
        for bad in ("password", "token", "private_key"):
            with pytest.raises(settings.RemoteSettingsError) as caught:
                settings.resolve({"remote": {"host": "h", bad: "hunter2"}}, {})
            message = str(caught.value)
            assert bad in message
            # Refused *as a credential*, not as a typo -- these are also
            # unknown keys, and "you misspelled it" is the wrong advice.
            assert "must not carry" in message, message
            assert "ssh agent" in message, message
            assert "hunter2" not in message, "the value was echoed back"

    def test_shell_metacharacters_in_a_host_are_refused(self):
        for bad in ("gpu; rm -rf /", "gpu$(whoami)", "gpu`id`", "gpu box", "gpu&x"):
            with pytest.raises(settings.RemoteSettingsError):
                settings.resolve({"remote": {"host": bad}}, {})

    def test_shell_metacharacters_in_a_workdir_are_refused(self):
        for bad in ("~/dir; rm -rf /", "$(pwd)", "a b"):
            with pytest.raises(settings.RemoteSettingsError):
                settings.resolve({"remote": {"host": "h", "workdir": bad}}, {})

    def test_a_tilde_workdir_is_allowed(self):
        # It has to survive being passed unquoted so the remote shell expands it.
        got = settings.resolve({"remote": {"host": "h", "workdir": "~/runs"}}, {})
        assert got["workdir"] == "~/runs"

    def test_gpus_must_be_a_positive_integer(self):
        for bad in (0, -1, "two", 1.5, True):
            with pytest.raises(settings.RemoteSettingsError):
                settings.resolve({"remote": {"host": "h", "gpus": bad}}, {})

    def test_a_non_mapping_remote_block_is_refused(self):
        with pytest.raises(settings.RemoteSettingsError):
            settings.resolve({"remote": "gpubox"}, {})

    def test_a_falsey_non_mapping_remote_block_is_refused(self):
        # [], "" and false are present but malformed. `remote: or {}` would
        # have swallowed them into local training instead of flagging the
        # mistake -- only an omitted or null value means "train here".
        for bad in ([], "", False):
            with pytest.raises(settings.RemoteSettingsError):
                settings.resolve({"remote": bad}, {})

    def test_an_omitted_or_null_remote_block_trains_here(self):
        assert settings.resolve({}, {}) == {}
        assert settings.resolve({"remote": None}, {}) == {}
