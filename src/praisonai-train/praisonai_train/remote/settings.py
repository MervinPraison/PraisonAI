"""Where a run executes, declared once.

The same four facts have to be expressible three ways -- a YAML block, CLI
flags, and the desktop form -- and mean the same thing in each. Declaring them
in one table is what stops the three drifting: the flags are generated from it,
the YAML is validated against it, and a parity test asserts that every key has
a flag and every flag has a key.

Nothing here talks to a remote machine. This module is the vocabulary;
``praisonai_train.remote.runner`` is the transport.
"""

from __future__ import annotations

# key, CLI flag, default, help. The default is what the trainer uses when the
# YAML omits the key and the flag is absent.
REMOTE_KEYS = (
    ("host", "--remote-host", None,
     "SSH alias to train on, as in ~/.ssh/config. Omit to train locally."),
    ("python", "--remote-python", "python3",
     "Interpreter on the remote host."),
    ("workdir", "--remote-workdir", "~/.praisonai-train",
     "Directory on the remote host to work in."),
    ("gpus", "--remote-gpus", 1,
     "How many GPUs the run expects to find."),
)

# Anything the user must never put in a config file, because the file is
# written into the run directory, shipped to the remote host, and shown in
# --dry-run. Credentials belong in the ssh agent and the environment.
FORBIDDEN_KEYS = ("password", "passphrase", "token", "key", "secret",
                  "identity_file", "private_key")


class RemoteSettingsError(ValueError):
    """A remote block that cannot be used as written."""


def defaults() -> dict:
    """The remote block as it stands with nothing supplied."""
    return {key: default for key, _flag, default, _help in REMOTE_KEYS}


def flag_for(key: str) -> str:
    for candidate, flag, _default, _help in REMOTE_KEYS:
        if candidate == key:
            return flag
    raise KeyError(key)


def resolve(config: dict, overrides: dict) -> dict:
    """The remote block from the config, with flags on top.

    Same precedence as every other setting: the file is the baseline and a flag
    wins. Returns {} when no host is settled, which is how "train locally" is
    expressed -- there is no separate mode switch to get out of step with it.
    """
    block = config.get("remote") or {}
    if not isinstance(block, dict):
        raise RemoteSettingsError(
            "remote: must be a mapping of key: value, not "
            f"{type(block).__name__}")

    merged = defaults()
    merged.update({k: v for k, v in block.items() if v is not None})
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})

    # Credentials first. They are also unknown keys, so checking that first
    # told the user they had made a typo -- and the remediation for a typo is
    # to correct the spelling, which here would mean trying harder to put a
    # password in a file that gets copied to another machine.
    leaked = sorted(k for k in block if k.lower() in FORBIDDEN_KEYS)
    if leaked:
        raise RemoteSettingsError(
            f"remote: must not carry {', '.join(leaked)}. This file is copied "
            "to the remote host and printed by --dry-run. Use an ssh agent or "
            "an entry in ~/.ssh/config instead.")

    unknown = sorted(set(block) - {k for k, _f, _d, _h in REMOTE_KEYS})
    if unknown:
        known = ", ".join(k for k, _f, _d, _h in REMOTE_KEYS)
        raise RemoteSettingsError(
            f"remote: does not take {', '.join(unknown)}. Known keys: {known}.")

    if not merged.get("host"):
        return {}

    validate(merged)
    return merged


def validate(block: dict) -> None:
    """Reject what would fail far away, or fail dangerously."""
    host = block.get("host")
    if not isinstance(host, str) or not host.strip():
        raise RemoteSettingsError("remote.host must be a non-empty SSH alias.")
    # An alias goes into an ssh command line. Anything outside this set is
    # either a typo or an attempt to smuggle in shell.
    if not all(c.isalnum() or c in "._-@" for c in host):
        raise RemoteSettingsError(
            f"remote.host {host!r} is not a plain SSH alias. Put connection "
            "details in ~/.ssh/config and name the alias here.")

    workdir = block.get("workdir") or ""
    if not isinstance(workdir, str) or not workdir.strip():
        raise RemoteSettingsError("remote.workdir must be a path.")
    # Expanded by the remote shell, so it must survive being passed unquoted.
    if not all(c.isalnum() or c in "._-/~" for c in workdir):
        raise RemoteSettingsError(
            f"remote.workdir {workdir!r} may only contain letters, digits and "
            "._-/~ -- it is expanded by the remote shell.")

    python = block.get("python") or ""
    if not isinstance(python, str) or not python.strip():
        raise RemoteSettingsError("remote.python must be an interpreter name or path.")
    if not all(c.isalnum() or c in "._-/~" for c in python):
        raise RemoteSettingsError(
            f"remote.python {python!r} may only contain letters, digits and ._-/~")

    gpus = block.get("gpus", 1)
    if isinstance(gpus, bool) or not isinstance(gpus, int) or gpus < 1:
        raise RemoteSettingsError(f"remote.gpus must be a positive integer, got {gpus!r}")


def redact(block: dict) -> dict:
    """The block as it is safe to print."""
    return {k: v for k, v in (block or {}).items() if k.lower() not in FORBIDDEN_KEYS}
