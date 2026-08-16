"""Importable gateway administration API (Issue #3985).

Gateway self-healing (``doctor --fix``) and provisioning (``onboard``) previously
existed only as private helpers inside the Typer command modules, so a program
embedding the gateway, provisioning it from CI/CD, or asserting "my gateway
repaired itself" in a test had to shell out to the CLI or reach into unsupported
``cli/`` internals (which also require the CLI-only ``typer`` dependency).

This module owns the typer-free repair machinery (config-version migration and
auth-token minting, driven through the shared core health registry) and exposes
it as importable, non-interactive functions returning a small typed result. The
Typer commands in ``cli/commands/gateway.py`` re-import these helpers so there is
one canonical flow (DRY).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from praisonai_bot.gateway.preflight import resolve_env_token as _resolve_env_token

PathLike = Union[str, "os.PathLike[str]"]


def _check_gateway_secret_strength(config_path: str):
    """Inspect the gateway's own auth_token for known-weak/placeholder values.

    Returns an actionable error string when the gateway is on an EXTERNAL bind
    and its resolved ``auth_token`` is either missing or a known-weak/
    placeholder value (caller should fail closed, mirroring startup). On a
    loopback bind a warning is printed for a weak token and ``None`` is returned
    (consistent with the permissive-loopback posture). Returns ``None`` when the
    token is strong, absent on a loopback bind, or the config cannot be read.
    """
    import yaml

    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:  # pragma: no cover — defensive
        return None

    gw = cfg.get("gateway", cfg) or {}
    raw_token = gw.get("auth_token") or os.environ.get("GATEWAY_AUTH_TOKEN", "")
    token = _resolve_env_token(raw_token) if raw_token else ""

    from praisonaiagents.gateway.protocols import (
        is_weak_secret,
        resolve_auth_mode,
        WeakGatewaySecretError,
    )

    # A strong, present token needs no further checks.
    if token and not is_weak_secret(token):
        return None

    bind_host = gw.get("bind_host") or gw.get("host") or "127.0.0.1"
    is_local = resolve_auth_mode(str(bind_host)) == "local"

    # Absent token: only a concern on an external bind, where startup fails
    # closed for a missing required secret. Doctor must agree (#3259).
    if not token:
        if is_local:
            return None
        return (
            f"Refusing to start: gateway.auth_token is required for external "
            f"bind {bind_host} but is missing.\n"
            f"Fix:  praisonai onboard         (30 seconds, 3 prompts)\n"
            f'Or:   export GATEWAY_AUTH_TOKEN="$(openssl rand -hex 16)"'
        )

    # Present-but-weak token: warn on loopback, fail closed externally.
    if is_local:
        # Advisory only — must go to stderr so callers rendering a
        # machine-readable JSON document to stdout stay parseable.
        print(
            f"⚠  gateway.auth_token is a known-weak/placeholder value "
            f"(loopback bind {bind_host}). Rotate before exposing externally.",
            file=sys.stderr,
        )
        return None

    return str(WeakGatewaySecretError(field="gateway.auth_token"))


def _config_has_explicit_weak_token(config_path: str) -> bool:
    """True when gateway.yaml pins an explicit (non-``${ENV}``) weak auth_token.

    Such a value is read verbatim at startup (``GatewayConfig.auth_token``) and
    by :func:`_check_gateway_secret_strength`, so it takes precedence over the
    ``GATEWAY_AUTH_TOKEN`` env var. Minting only into the env would leave the
    weak YAML value active — the repair must rewrite the YAML too (#3554).
    A ``${ENV}`` reference is NOT rewritten: it resolves from the env store the
    env-var repair already fixes, so overwriting it would clobber operator
    indirection.
    """
    import yaml

    if not os.path.exists(config_path):
        return False
    try:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:  # pragma: no cover — defensive
        return False

    gw = cfg.get("gateway", cfg) or {}
    raw_token = gw.get("auth_token")
    if not raw_token or not isinstance(raw_token, str):
        return False
    if raw_token.startswith("${") and raw_token.endswith("}"):
        return False

    from praisonaiagents.gateway.protocols import is_weak_secret

    return is_weak_secret(raw_token)


def _persist_yaml_auth_token(config_path: str, new_token: str) -> None:
    """Rewrite the ``gateway.auth_token`` in gateway.yaml in place (#3554)."""
    import yaml

    with open(config_path) as fh:
        cfg = yaml.safe_load(fh) or {}

    if isinstance(cfg.get("gateway"), dict):
        cfg["gateway"]["auth_token"] = new_token
    else:
        cfg["auth_token"] = new_token

    with open(config_path, "w") as fh:
        yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)


def _check_config_version(config_path: str):
    """Return applied-migration reasons if gateway.yaml is out of date (#3841).

    Reads the raw YAML and asks the canonical core migrator whether any
    declarative rule fires or the ``config_version`` stamp is missing/stale.
    Returns ``(reasons, from_version, to_version)`` when a migration would run,
    else ``None`` — so ``doctor`` can surface "your config is out of date, run
    --fix" without writing anything. A single ``str`` error is returned when the
    config was written by a newer build or carries a malformed stamp, so doctor
    can warn without attempting a (downgrading) migration.

    Older core installs that predate the migration API (praisonaiagents without
    ``migrate_config_with_doctor``) make this a graceful no-op rather than
    crashing ``doctor`` with an ``ImportError``.
    """
    import yaml

    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception:  # pragma: no cover — defensive
        return None
    if not isinstance(cfg, dict):
        return None

    try:
        from praisonaiagents.gateway.config import (
            GATEWAY_CONFIG_VERSION,
            ConfigVersionError,
            is_config_current,
            migrate_config_with_doctor,
        )
    except ImportError:
        # Core too old to know about config versioning; nothing to migrate.
        return None

    try:
        current = is_config_current(cfg)
        _, reasons = migrate_config_with_doctor(cfg)
    except ConfigVersionError as exc:
        return str(exc)
    if current and not reasons:
        return None
    from_version = cfg.get("config_version", "unstamped")
    return reasons, from_version, GATEWAY_CONFIG_VERSION


def _repair_config_version(config_path: str):
    """Migrate gateway.yaml forward once and stamp ``config_version`` (#3841).

    Applies the canonical declarative migration rules via the core executor and
    rewrites the YAML, preserving key order. Returns the list of operator-facing
    reasons for the applied rules (may be empty when only the version stamp
    needed writing).

    The rewrite is atomic: the migrated YAML is serialised to a temporary file
    in the same directory and ``os.replace``'d over the live ``gateway.yaml``, so
    an interruption, full disk, or I/O error during ``doctor --fix`` can never
    leave the config truncated or half-written.
    """
    import tempfile
    import yaml

    with open(config_path) as fh:
        cfg = yaml.safe_load(fh) or {}

    from praisonaiagents.gateway.config import migrate_config_with_doctor

    migrated, reasons = migrate_config_with_doctor(cfg)

    directory = os.path.dirname(os.path.abspath(config_path))
    fd, tmp_path = tempfile.mkstemp(
        prefix=".gateway.", suffix=".yaml.tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w") as fh:
            yaml.safe_dump(
                migrated, fh, default_flow_style=False, sort_keys=False
            )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, config_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return reasons


def _repair_gateway_secret(dry_run: bool = False, config_path: str = ""):
    """Mint a strong gateway auth token to repair a weak/missing one.

    The safe, idempotent repair behind ``gateway doctor --fix``: the caller has
    already detected a weak/absent ``gateway.auth_token`` (via
    :func:`_check_gateway_secret_strength`); this generates a fresh
    ``secrets.token_hex(16)`` value and persists it to ``~/.praisonai/.env`` (the
    same store ``praisonai onboard`` uses) so it survives daemon restarts. The
    new token is also exported into this process's environment so the caller can
    immediately **re-validate** that the finding cleared.

    When gateway.yaml pins an explicit (non-``${ENV}``) weak ``auth_token``, that
    value wins over the env var at both startup and re-validation, so the same
    strong token is ALSO written back into the YAML — otherwise ``--fix`` would
    report success while the weak YAML value stays active (#3554). When
    ``dry_run`` is True no token is minted or written.

    Returns ``"would-repair"`` (dry-run preview) or ``"repaired"`` so the
    ``doctor`` command can render a detect → repair → re-validate line.
    """
    if dry_run:
        return "would-repair"

    import secrets as _secrets
    from praisonai_bot.cli.features.onboard import _save_env_vars

    new_token = _secrets.token_hex(16)
    _save_env_vars({"GATEWAY_AUTH_TOKEN": new_token})
    os.environ["GATEWAY_AUTH_TOKEN"] = new_token
    if config_path and _config_has_explicit_weak_token(config_path):
        _persist_yaml_auth_token(config_path, new_token)
    return "repaired"


class _GatewaySecretHealthCheck:
    """Adapter that exposes the gateway auth-token check to the registry."""

    check_id = "core/gateway/auth-token"

    def detect(self, context):
        from praisonaiagents.runtime.doctor_protocol import Finding

        config_path = context.get("config_path")
        if not config_path:
            return []
        message = _check_gateway_secret_strength(str(config_path))
        if not message:
            return []
        return [Finding(
            rule_id=self.check_id,
            severity="error",
            message=message,
            fix_description="Mint and persist a strong gateway auth token",
        )]

    def repair(self, context, findings):
        from praisonaiagents.runtime.health_check import HealthRepairResult

        config_path = context.get("config_path")
        if not config_path:
            return HealthRepairResult(
                changed=False, message="gateway config path not provided; no action taken"
            )
        action = _repair_gateway_secret(
            dry_run=bool(context.get("dry_run")),
            config_path=str(config_path),
        )
        if action == "would-repair":
            return HealthRepairResult(
                changed=False,
                message=(
                    "gateway_auth_token: weak -> would mint a strong token "
                    "(--dry-run)"
                ),
            )
        return HealthRepairResult(changed=True, message="gateway auth token repaired")


class _GatewayConfigVersionHealthCheck:
    """Adapter that exposes config migration through the health registry."""

    check_id = "core/gateway/config-version"

    def detect(self, context):
        from praisonaiagents.runtime.doctor_protocol import Finding

        config_path = context.get("config_path")
        if not config_path:
            return []
        migration = _check_config_version(str(config_path))
        if migration is None:
            return []
        if isinstance(migration, str):
            return [Finding(
                rule_id=self.check_id,
                severity="error",
                message=migration,
                fix_description=None,
                context={"unsupported": True},
            )]
        reasons, from_version, to_version = migration
        return [Finding(
            rule_id=self.check_id,
            severity="warning",
            message=(
                "gateway config is out of date "
                f"(config_version {from_version} -> {to_version})"
            ),
            fix_description="Apply safe migrations and stamp config_version",
            context={
                "reasons": list(reasons),
                "from_version": from_version,
                "to_version": to_version,
            },
        )]

    def repair(self, context, findings):
        from praisonaiagents.runtime.health_check import HealthRepairResult

        config_path = context.get("config_path")
        if not config_path:
            return HealthRepairResult(
                changed=False, message="gateway config path not provided; no action taken"
            )
        details = findings[0].context or {}
        if details.get("unsupported"):
            return HealthRepairResult(
                changed=False,
                message=(
                    "config: written by a newer build; left untouched to avoid "
                    "a downgrade"
                ),
            )
        reasons = list(details.get("reasons", []))
        from_version = details.get("from_version", "unstamped")
        to_version = details.get("to_version", "current")
        if context.get("dry_run"):
            lines = [f"config: would {reason}" for reason in reasons]
            lines.append(
                "config: would stamp config_version "
                f"{from_version} -> {to_version} (--dry-run)"
            )
            return HealthRepairResult(changed=False, message="\n".join(lines))

        applied = _repair_config_version(str(config_path))
        lines = [f"config: {reason}" for reason in applied]
        lines.append(f"config: config_version {from_version} -> {to_version}")
        return HealthRepairResult(changed=True, message="\n".join(lines))


def _run_gateway_health_checks(config_path: str, *, fix: bool, dry_run: bool):
    """Run built-in and third-party checks through one shared lifecycle."""
    from praisonaiagents.runtime.health_registry import get_health_check_registry

    registry = get_health_check_registry()
    # Register the mandatory gateway checks as protected BEFORE plugin
    # discovery so an installed extension cannot shadow the required
    # auth-token/config-version validation and repair.
    for check in (_GatewaySecretHealthCheck(), _GatewayConfigVersionHealthCheck()):
        if check.check_id not in registry.protected_ids():
            registry.register_check(check, protected=True)
    return registry.run(
        {"config_path": config_path, "dry_run": dry_run},
        fix=fix,
    )


@dataclass(frozen=True)
class GatewayRepairResult:
    """Closed result shape for :func:`repair_gateway_config`.

    Mirrors the degraded-owner vocabulary in
    ``praisonaiagents.gateway.degraded_state`` so a programmatic caller can act
    on what changed and what remains degraded.

    Attributes:
        auth_token_minted: A strong ``gateway.auth_token`` was minted/persisted.
        config_version_migrated: ``config_version`` was forward-migrated.
        changes: Operator-facing lines describing what was repaired.
        remaining_degraded_owners: Redacted ``{owner_kind, owner_id, state,
            reason, retry_hint}`` dicts for findings that are still unresolved
            after the run (empty on a clean verify).
    """

    auth_token_minted: bool = False
    config_version_migrated: bool = False
    changes: List[str] = field(default_factory=list)
    remaining_degraded_owners: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "auth_token_minted": self.auth_token_minted,
            "config_version_migrated": self.config_version_migrated,
            "changes": list(self.changes),
            "remaining_degraded_owners": list(self.remaining_degraded_owners),
        }


def _finding_to_degraded_owner(check_id: str, finding) -> Dict[str, str]:
    """Map a residual health :class:`Finding` to the degraded-owner shape.

    Reuses the closed ``owner_kind`` vocabulary from ``degraded_state`` and
    names the canonical remediation command in ``retry_hint`` so a caller sees
    the same operator-safe record the runtime surfaces via ``health()``.
    """
    return {
        "owner_kind": "gateway",
        "owner_id": check_id,
        "state": "cold",
        "reason": getattr(finding, "message", "") or "",
        "retry_hint": "praisonai gateway doctor --fix",
    }


def repair_gateway_config(
    config_path: PathLike,
    *,
    fix: bool = False,
    dry_run: bool = False,
) -> GatewayRepairResult:
    """Self-heal a gateway config, programmatically (Issue #3985).

    Runs the same detect → repair → re-validate lifecycle behind
    ``praisonai gateway doctor --fix``: forward-migrate an out-of-date
    ``config_version`` and mint/persist a strong ``gateway.auth_token`` when the
    configured one is weak or missing.

    Args:
        config_path: Path to the gateway ``bot.yaml`` / ``gateway.yaml``.
        fix: When ``True`` apply safe repairs; when ``False`` (default) only
            detect, leaving findings in ``remaining_degraded_owners``.
        dry_run: With ``fix=True``, preview repairs without writing anything.

    Returns:
        A :class:`GatewayRepairResult` describing what changed and what remains
        degraded. On a clean verify ``remaining_degraded_owners`` is empty.
    """
    path = os.path.expanduser(os.fspath(config_path))

    results = _run_gateway_health_checks(path, fix=fix, dry_run=dry_run)

    auth_token_minted = False
    config_version_migrated = False
    changes: List[str] = []
    remaining: List[Dict[str, str]] = []

    for result in results:
        if result.repaired and not dry_run:
            if result.check_id == "core/gateway/auth-token":
                auth_token_minted = True
            elif result.check_id == "core/gateway/config-version":
                config_version_migrated = True
        repair = getattr(result, "repair", None)
        if repair is not None and getattr(repair, "message", None):
            changes.extend(
                line for line in str(repair.message).splitlines() if line.strip()
            )
        for finding in result.residual_findings:
            remaining.append(_finding_to_degraded_owner(result.check_id, finding))

    return GatewayRepairResult(
        auth_token_minted=auth_token_minted,
        config_version_migrated=config_version_migrated,
        changes=changes,
        remaining_degraded_owners=remaining,
    )


def provision_gateway_config(
    *,
    platform: str,
    token: str,
    agents: Optional[List[str]] = None,
    config_path: Optional[PathLike] = None,
) -> Path:
    """Provision a working ``bot.yaml`` + ``.env`` non-interactively (Issue #3985).

    The argument-driven library entry the interactive ``onboard`` wizard never
    exposed: produces the same gateway-compatible config the wizard writes,
    persisting the channel token to ``~/.praisonai/.env`` (via env-var
    reference) so secrets stay out of the YAML.

    Args:
        platform: Channel platform to configure, e.g. ``"telegram"``. Must be a
            known built-in or ``pip``-installed channel; an unsupported value
            raises :class:`ValueError` rather than writing a config the gateway
            would reject at startup (Issue #3985).
        token: The channel token to persist to ``~/.praisonai/.env``. Must be a
            non-empty string; an empty credential raises :class:`ValueError`
            rather than writing a channel the gateway would boot degraded.
        agents: Agent names to declare (defaults to ``["assistant"]``). Every
            name is declared in the ``agents:`` block; the first is used as the
            channel's default route.
        config_path: Where to write the config (defaults to the onboarded
            ``~/.praisonai/bot.yaml``).

    Returns:
        The path the config was written to.

    Raises:
        ValueError: If ``platform`` is not a supported channel or ``token`` is
            empty — fail-closed so provisioning never reports success for a
            configuration the gateway cannot serve.
    """
    from praisonai_bot.cli.features.onboard import (
        _available_platforms,
        _generate_bot_yaml,
        _praison_home,
        _save_env_vars,
    )

    if not token or not str(token).strip():
        raise ValueError(
            f"provision_gateway_config: a non-empty token is required for "
            f"channel {platform!r}; the gateway would boot this channel "
            f"degraded without a credential."
        )

    available = _available_platforms()
    info = available.get(platform)
    if info is None:
        supported = ", ".join(sorted(available)) or "(none)"
        raise ValueError(
            f"provision_gateway_config: unsupported platform {platform!r}. "
            f"Supported channels: {supported}."
        )

    agent_names = list(dict.fromkeys(agents)) if agents else ["assistant"]
    agent_name = agent_names[0]

    env_var = info.get("token_env", f"{platform.upper()}_BOT_TOKEN")
    _save_env_vars({env_var: token})

    yaml_content = _generate_bot_yaml(
        [platform], agent_name=agent_name, agent_names=agent_names
    )

    if config_path is not None:
        target = Path(os.path.expanduser(os.fspath(config_path)))
    else:
        target = _praison_home() / "bot.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml_content)
    return target
