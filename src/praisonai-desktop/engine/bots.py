"""Manage Telegram/Slack channel bots and the multi-bot gateway from Desktop.

Subprocess lifecycle mirrors training.py: one supervisor, persisted state,
ring-buffer logs, start_new_session so stop() can reach the process group.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid

SUPPORTED_PLATFORMS = frozenset({"telegram", "slack"})
MAX_LOG_LINES = 400
RUNNING = "running"
STOPPED = "stopped"
ERROR = "error"


def _quiet_spawn_kwargs() -> dict:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return {"creationflags": flags} if flags else {}


def load_dotenv_file(path: pathlib.Path) -> None:
    """Load KEY=VALUE lines into os.environ without overwriting existing keys."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_token_ref(ref: str) -> str:
    """Resolve env:VAR references used in channel configs."""
    ref = (ref or "").strip()
    if ref.startswith("env:"):
        return os.environ.get(ref[4:].strip(), "")
    return ref


def _default_agent_block(model: str = "gpt-4o-mini") -> dict:
    return {
        "name": "Desktop Assistant",
        "instructions": "You are a helpful assistant. Reply briefly and clearly.",
        "llm": model or "gpt-4o-mini",
    }


class _ProcessHandle:
    def __init__(self, name: str, log_path: pathlib.Path):
        self.name = name
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self.log_lines: collections.deque = collections.deque(maxlen=MAX_LOG_LINES)
        self.error: str | None = None
        self.started_at: float | None = None
        self._reader: threading.Thread | None = None

    def _read_loop(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        try:
            for line in self.proc.stdout:
                text = line.rstrip("\n")
                self.log_lines.append(text)
                try:
                    with self.log_path.open("a", encoding="utf-8") as fh:
                        fh.write(line)
                except OSError:
                    pass
        except Exception:  # noqa: BLE001
            pass

    def start(self, argv: list[str], env: dict[str, str], cwd: pathlib.Path) -> None:
        self.stop()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.log_path.write_text("", encoding="utf-8")
        except OSError:
            pass
        try:
            self.proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
                **_quiet_spawn_kwargs(),
            )
        except OSError as exc:
            self.error = str(exc)
            self.proc = None
            return
        self.error = None
        self.started_at = time.time()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> bool:
        if not self.alive():
            self.proc = None
            return False
        proc = self.proc
        assert proc is not None
        try:
            if sys.platform.startswith("win"):
                proc.terminate()
            else:
                os.killpg(os.getpgid(proc.pid), subprocess.signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
        self.proc = None
        return True

    def summary(self) -> dict:
        alive = self.alive()
        state = RUNNING if alive else (ERROR if self.error else STOPPED)
        return {
            "name": self.name,
            "state": state,
            "pid": self.proc.pid if alive and self.proc else None,
            "error": self.error,
            "started_at": self.started_at,
            "log_tail": list(self.log_lines)[-80:],
        }


class BotSupervisor:
    """Channel bots + optional gateway, persisted under the desktop data dir."""

    def __init__(self, home: pathlib.Path, python: str, *, model: str = "gpt-4o-mini"):
        self.home = home
        self.python = python
        self.model = model
        self.root = home / "bots"
        self.config_dir = self.root / "configs"
        self.channels_path = self.root / "channels.json"
        self.gateway_config = self.root / "gateway.yaml"
        self.gateway_log = self.root / "gateway.log"
        # RLock: delete_channel -> stop_channel and start_gateway -> gateway_status
        # re-enter the same supervisor while holding the lock.
        self._lock = threading.RLock()
        self._channels: list[dict] = []
        self._gateway = _ProcessHandle("gateway", self.gateway_log)
        self._bots: dict[str, _ProcessHandle] = {}
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        load_dotenv_file(pathlib.Path.home() / ".praisonai" / ".env")
        self._load_channels()
        self._reconcile()

    def _load_channels(self) -> None:
        try:
            data = json.loads(self.channels_path.read_text(encoding="utf-8"))
            self._channels = data if isinstance(data, list) else []
        except (OSError, ValueError, json.JSONDecodeError):
            self._channels = []

    def _save_channels(self) -> None:
        self.channels_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.channels_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._channels, indent=2), encoding="utf-8")
        os.replace(tmp, self.channels_path)

    def _find(self, channel_id: str) -> dict | None:
        for ch in self._channels:
            if ch.get("id") == channel_id:
                return ch
        return None

    def _bot_handle(self, channel_id: str) -> _ProcessHandle:
        if channel_id not in self._bots:
            log_path = self.root / f"channel-{channel_id}.log"
            self._bots[channel_id] = _ProcessHandle(channel_id, log_path)
        return self._bots[channel_id]

    def _channel_status(self, ch: dict) -> dict:
        handle = self._bots.get(ch["id"])
        running = handle.alive() if handle else False
        state = RUNNING if running else ch.get("state", STOPPED)
        out = dict(ch)
        out["state"] = state
        out["pid"] = handle.proc.pid if running and handle and handle.proc else None
        if handle and handle.error and not running:
            out["error"] = handle.error
        token_ref = ch.get("token_ref") or ""
        out["token_set"] = bool(resolve_token_ref(token_ref))
        if ch.get("platform") == "slack":
            app_ref = ch.get("app_token_ref") or "env:SLACK_APP_TOKEN"
            out["app_token_set"] = bool(resolve_token_ref(app_ref))
        return out

    def list_channels(self) -> list[dict]:
        with self._lock:
            return [self._channel_status(ch) for ch in self._channels]

    def add_channel(self, payload: dict) -> dict:
        platform = str(payload.get("platform") or "").strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"platform must be one of: {', '.join(sorted(SUPPORTED_PLATFORMS))}")
        name = str(payload.get("name") or platform.title()).strip()
        token_ref = str(payload.get("token_ref") or "").strip()
        if not token_ref:
            token_ref = f"env:{platform.upper()}_BOT_TOKEN" if platform != "slack" else "env:SLACK_BOT_TOKEN"
        entry = {
            "id": uuid.uuid4().hex[:12],
            "platform": platform,
            "name": name,
            "token_ref": token_ref,
            "unknown_user_policy": payload.get("unknown_user_policy") or "allow",
            "state": STOPPED,
        }
        if platform == "slack":
            entry["app_token_ref"] = str(payload.get("app_token_ref") or "env:SLACK_APP_TOKEN").strip()
        with self._lock:
            self._channels.append(entry)
            self._save_channels()
            return self._channel_status(entry)

    def update_channel(self, channel_id: str, updates: dict) -> dict:
        with self._lock:
            ch = self._find(channel_id)
            if not ch:
                raise ValueError("no such channel")
            handle = self._bots.get(channel_id)
            if handle and handle.alive():
                raise RuntimeError("stop the channel before editing")
            for key in ("name", "token_ref", "app_token_ref", "unknown_user_policy"):
                if key in updates and updates[key] is not None:
                    ch[key] = str(updates[key]).strip()
            self._save_channels()
            return self._channel_status(ch)

    def delete_channel(self, channel_id: str) -> bool:
        with self._lock:
            self.stop_channel(channel_id)
            before = len(self._channels)
            self._channels = [c for c in self._channels if c.get("id") != channel_id]
            self._save_channels()
            cfg = self.config_dir / f"{channel_id}.yaml"
            try:
                cfg.unlink(missing_ok=True)
            except OSError:
                pass
            return len(self._channels) < before

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        return env

    def _write_bot_yaml(self, ch: dict) -> pathlib.Path:
        platform = ch["platform"]
        token_ref = ch.get("token_ref") or ""
        token = resolve_token_ref(token_ref)
        if not token:
            var = token_ref[4:] if token_ref.startswith("env:") else token_ref
            raise ValueError(f"token not set ({var or 'missing'})")
        lines = [
            f"platform: {platform}",
            f'token: "${{{token_ref[4:].strip() if token_ref.startswith("env:") else "TOKEN"}}}"',
            f"unknown_user_policy: {ch.get('unknown_user_policy') or 'allow'}",
            "agent:",
            f"  name: \"{ _default_agent_block(self.model)['name'] }\"",
            f"  instructions: \"{ _default_agent_block(self.model)['instructions'] }\"",
            f"  llm: \"{self.model}\"",
        ]
        if platform == "slack":
            app_ref = ch.get("app_token_ref") or "env:SLACK_APP_TOKEN"
            var = app_ref[4:].strip() if app_ref.startswith("env:") else "SLACK_APP_TOKEN"
            if not resolve_token_ref(app_ref):
                raise ValueError(f"app token not set ({var})")
            lines.insert(3, f'app_token: "${{{var}}}"')
        path = self.config_dir / f"{ch['id']}.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def start_channel(self, channel_id: str) -> dict:
        with self._lock:
            ch = self._find(channel_id)
            if not ch:
                raise ValueError("no such channel")
            if self._gateway.alive():
                raise RuntimeError("stop the gateway before starting an individual bot (one poller per token)")
            handle = self._bot_handle(channel_id)
            if handle.alive():
                return self._channel_status(ch)
            yaml_path = self._write_bot_yaml(ch)
            argv = [self.python, "-m", "praisonai", "bot", "start", "--config", str(yaml_path)]
            handle.start(argv, self._build_env(), self.config_dir)
            if not handle.alive():
                ch["state"] = ERROR
                ch["error"] = handle.error or "bot failed to start"
                self._save_channels()
                raise RuntimeError(ch["error"])
            ch["state"] = RUNNING
            ch.pop("error", None)
            self._save_channels()
            return self._channel_status(ch)

    def stop_channel(self, channel_id: str) -> dict:
        with self._lock:
            ch = self._find(channel_id)
            if not ch:
                raise ValueError("no such channel")
            handle = self._bot_handle(channel_id)
            handle.stop()
            ch["state"] = STOPPED
            ch.pop("error", None)
            self._save_channels()
            return self._channel_status(ch)

    def _write_gateway_yaml(self, port: int = 8765) -> None:
        agents = {
            "default": _default_agent_block(self.model),
        }
        channels_block: dict = {}
        for ch in self._channels:
            plat = ch["platform"]
            if plat == "telegram":
                channels_block["telegram"] = {
                    "token": f"${{{(ch.get('token_ref') or 'env:TELEGRAM_BOT_TOKEN')[4:].strip() if (ch.get('token_ref') or '').startswith('env:') else 'TELEGRAM_BOT_TOKEN'}}}",
                    "unknown_user_policy": ch.get("unknown_user_policy") or "allow",
                    "routing": {"dm": "default", "default": "default"},
                }
            elif plat == "slack":
                token_var = (ch.get("token_ref") or "env:SLACK_BOT_TOKEN")
                app_var = (ch.get("app_token_ref") or "env:SLACK_APP_TOKEN")
                t_name = token_var[4:].strip() if token_var.startswith("env:") else "SLACK_BOT_TOKEN"
                a_name = app_var[4:].strip() if app_var.startswith("env:") else "SLACK_APP_TOKEN"
                channels_block["slack"] = {
                    "token": f"${{{t_name}}}",
                    "app_token": f"${{{a_name}}}",
                    "routing": {"dm": "default", "channel": "default", "default": "default"},
                }
        text = (
            "# Generated by PraisonAI Desktop\n"
            "gateway:\n"
            f'  host: "127.0.0.1"\n'
            f"  port: {port}\n\n"
            "agents:\n"
            "  default:\n"
            f"    name: \"Desktop Assistant\"\n"
            f"    instructions: \"You are a helpful assistant. Reply briefly.\"\n"
            f"    llm: \"{self.model}\"\n\n"
            "channels:\n"
        )
        for plat, cfg in channels_block.items():
            text += f"  {plat}:\n"
            for k, v in cfg.items():
                if isinstance(v, dict):
                    text += f"    {k}:\n"
                    for sk, sv in v.items():
                        text += f"      {sk}: \"{sv}\"\n"
                else:
                    text += f"    {k}: \"{v}\"\n"
        self.gateway_config.write_text(text, encoding="utf-8")

    def gateway_status(self) -> dict:
        with self._lock:
            alive = self._gateway.alive()
            return {
                "state": RUNNING if alive else STOPPED,
                "pid": self._gateway.proc.pid if alive and self._gateway.proc else None,
                "port": 8765,
                "config_path": str(self.gateway_config),
                "log_tail": list(self._gateway.log_lines)[-80:],
                "channels_configured": len(self._channels),
            }

    def start_gateway(self, port: int = 8765) -> dict:
        with self._lock:
            for ch in self._channels:
                handle = self._bots.get(ch["id"])
                if handle and handle.alive():
                    raise RuntimeError("stop individual channel bots before starting the gateway")
            if not self._channels:
                raise ValueError("add at least one channel before starting the gateway")
            for ch in self._channels:
                if ch["platform"] == "telegram" and not resolve_token_ref(ch.get("token_ref") or ""):
                    raise ValueError("TELEGRAM_BOT_TOKEN is not set")
                if ch["platform"] == "slack":
                    if not resolve_token_ref(ch.get("token_ref") or ""):
                        raise ValueError("SLACK_BOT_TOKEN is not set")
                    if not resolve_token_ref(ch.get("app_token_ref") or "env:SLACK_APP_TOKEN"):
                        raise ValueError("SLACK_APP_TOKEN is not set")
            if self._gateway.alive():
                return self.gateway_status()
            self._write_gateway_yaml(port)
            argv = [
                self.python,
                "-m",
                "praisonai",
                "gateway",
                "start",
                "--config",
                str(self.gateway_config),
            ]
            self._gateway.start(argv, self._build_env(), self.root)
            if not self._gateway.alive():
                err = self._gateway.error or "gateway failed to start"
                raise RuntimeError(err)
            return self.gateway_status()

    def stop_gateway(self) -> dict:
        with self._lock:
            self._gateway.stop()
            return self.gateway_status()

    def logs(self, target: str) -> dict:
        with self._lock:
            if target == "gateway":
                return {"target": "gateway", "lines": list(self._gateway.log_lines)}
            handle = self._bots.get(target)
            if not handle:
                raise ValueError("no such target")
            return {"target": target, "lines": list(handle.log_lines)}

    def _reconcile(self) -> None:
        """Mark stale running states stopped after engine restart."""
        changed = False
        for ch in self._channels:
            if ch.get("state") == RUNNING:
                ch["state"] = STOPPED
                changed = True
        if changed:
            self._save_channels()
