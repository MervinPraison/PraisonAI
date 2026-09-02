"""A headless driver for the PraisonAI desktop engine.

The engine (engine/server.py) is an HTTP server the Tauri shell spawns and then
talks to over loopback. There has never been a supported way to reach it without
the window, so reproducing a desktop bug meant installing the app, opening it,
and typing -- impossible on a headless machine, over SSH, or in CI.

This is that supported way. It speaks to the same routes the app does and adds
no engine code: it starts the engine, reads its announced port, and drives it.

    praisonai-desktop engine start [--home DIR]   provision-free: run and print the port
    praisonai-desktop engine health               versions, data dir, port (from the lockfile)
    praisonai-desktop chat "prompt" [--no-tools]  one turn, streamed to stdout
    praisonai-desktop doctor                       what is installed vs what the app requires

`doctor` is the one that answers a version report immediately: it prints the
installed praisonaiagents against the floor the app actually provisions, so a
"tool calling returns nothing" report resolves to "1.7.1 installed, >=1.7.2
required" in one command rather than a screen recording.

Stdlib only, exactly like the engine it drives -- so it runs in the same venv
the app builds and adds nothing to it.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE / "engine"
# Reuse the engine's own logic rather than reimplementing the data dir, the
# lockfile format or the version lookup -- a second copy is a second thing to
# drift out of agreement with the Rust shell.
sys.path.insert(0, str(ENGINE))
import server  # noqa: E402


def _required_floor():
    """The praisonaiagents floor the app provisions, read from provision.rs.

    The Rust shell is the source of truth for what the engine needs
    (ENGINE_PACKAGES in src-tauri/src/provision.rs). Hardcoding the version
    here would be a second place to update, and the one most likely to be
    forgotten -- so doctor reads the real floor and cannot disagree with what
    the app actually installs.
    """
    provision = HERE / "src-tauri" / "src" / "provision.rs"
    try:
        text = provision.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'praisonaiagents\s*>=\s*([0-9][0-9A-Za-z.\-]*)', text)
    return match.group(1) if match else None


def _lockfile_fields(home=None):
    """The engine lockfile parsed into a dict, or None if there is no lock.

    The same file, in the same format, that src-tauri/src/lockfile.rs parses --
    this is how the running engine is found without matching a process name
    that would also match the finder itself.
    """
    data_dir = pathlib.Path(home) if home else server.default_data_dir()
    lock = data_dir / "engine.lock"
    try:
        text = lock.read_text(encoding="utf-8")
    except OSError:
        return None
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
    return fields or None


def _http_json(url, timeout=4.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _live_port(home=None):
    """The port of a healthy engine, verified via /health, or None.

    A lockfile alone is not proof: a crashed engine leaves one behind, and a
    recycled pid can look live. The /health probe confirms the port really is
    our engine before anything is sent to it -- and it must be *our* engine, so
    the protocol version is checked too, not just `ok`. A recycled port that
    another loopback service happens to answer with `{"ok": true}` would
    otherwise be handed the user's prompt; the engine stamps every /health with
    server.PROTOCOL_VERSION, which an unrelated service will not.
    """
    fields = _lockfile_fields(home)
    if not fields or not fields.get("port"):
        return None
    port = fields["port"]
    try:
        health = _http_json(f"http://127.0.0.1:{port}/health", timeout=1.5)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if health.get("ok") is not True:
        return None
    if health.get("version") != server.PROTOCOL_VERSION:
        return None
    return port


def cmd_engine_start(args):
    """Run the engine in the foreground and print its port once it is listening.

    This does not provision a venv -- it runs the engine with the current
    interpreter, which is what makes it usable from a checkout or an existing
    app environment. The port is printed to stdout the moment the socket is
    bound (the engine announces it), so a caller can read one line and connect.
    """
    env = dict(os.environ)
    if args.home:
        env["PRAISONAI_DESKTOP_HOME"] = str(pathlib.Path(args.home).expanduser())
    proc = subprocess.Popen(
        [sys.executable, str(ENGINE / "server.py")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True,
    )
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return proc.wait()


def cmd_engine_health(args):
    """Print the running engine's health, or say plainly that none is running."""
    port = _live_port(args.home)
    if port is None:
        print("No running engine found (no live lockfile under the data dir).")
        print("Start one with:  praisonai-desktop engine start")
        return 1
    health = _http_json(f"http://127.0.0.1:{port}/health")
    fields = _lockfile_fields(args.home) or {}
    print(f"port           {port}")
    print(f"pid            {fields.get('pid', '?')}")
    print(f"protocol       {health.get('version', '?')}")
    print(f"agents_version {health.get('agents_version', '?')}")
    print(f"data_dir       {health.get('data_dir', '?')}")
    return 0


def cmd_chat(args):
    """Drive one turn against a running engine and stream the answer to stdout.

    This is the reproduction primitive the issue asks for: a tool-calling
    failure that took a GUI and several screenshots to show becomes one command
    whose output is the answer. It parses the engine's SSE stream so a turn that
    ran tools but returned no text -- the exact 1.7.1 failure -- is reported as
    such rather than as a blank success.
    """
    port = _live_port(args.home)
    if port is None:
        print("No running engine found. Start one first with:  "
              "praisonai-desktop engine start", file=sys.stderr)
        return 1

    # session, not just chat_id: the engine caches one agent per `session`
    # (default "default") and only loads history per chat_id, so without this
    # every --chat-id would share one agent and inherit the others' history.
    body = json.dumps({
        "prompt": args.prompt,
        "session": args.chat_id,
        "chat_id": args.chat_id,
        "run_id": args.chat_id,
        "tools": not args.no_tools,
    }).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/chat", data=body,
        headers={"content-type": "application/json"})

    text_chars = 0
    tools_ran = 0
    error = None
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            for event, payload in _iter_sse(resp):
                if event == "delta":
                    chunk = payload.get("text", "")
                    text_chars += len(chunk)
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                elif event == "tool_result":
                    tools_ran += 1
                elif event == "approval_request":
                    # A tool-enabled turn can hit the approval gate (the engine
                    # defaults approval_mode to "ask"), which blocks the run for
                    # up to its 300s timeout waiting on /approve. There is no
                    # human on a headless turn, so answer it here rather than
                    # hang: --approve to allow, otherwise deny. A denied tool is
                    # recoverable; a frozen turn is not.
                    _answer_approval(port, payload,
                                     "allow" if args.approve else "deny")
                elif event == "error":
                    error = payload.get("message", "unknown error")
    except (urllib.error.URLError, OSError) as exc:
        print(f"\nRequest failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if text_chars:
        sys.stdout.write("\n")
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if not text_chars:
        # The 1.7.1 signature, named rather than shown as an empty answer.
        note = (f"{tools_ran} tool call(s) ran, but the model returned no text."
                if tools_ran else "the engine produced no output.")
        print(f"error: {note}", file=sys.stderr)
        return 1
    return 0


def _iter_sse(resp):
    """Yield (event, data-dict) pairs from a text/event-stream response.

    Frames are blank-line separated; each carries an `event:` and a `data:`
    line. A data line that is not JSON is skipped rather than crashing the
    stream, since a partial frame is recoverable and a dropped connection is
    not.
    """
    event = "message"
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\n")
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            try:
                yield event, json.loads(line[len("data:"):].strip())
            except ValueError:
                pass
        elif line == "":
            event = "message"


def _answer_approval(port, payload, choice):
    """Answer an approval_request so a headless turn does not block on the gate.

    Posts the decision to /approve/{id}; failure is swallowed because the turn
    will fall back to the engine's own approval timeout, and a broken answer
    must not itself crash the stream we are still reading.
    """
    aid = payload.get("approval_id")
    if not aid:
        return
    body = json.dumps({"choice": choice}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/approve/{aid}", data=body,
        headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=4.0):
            pass
    except (urllib.error.URLError, OSError):
        pass


def cmd_doctor(args):
    """Report what is installed against what the app requires.

    The command that would have answered the original report on its own: it
    prints the installed praisonaiagents and the floor the app provisions, and
    exits non-zero when the installed version is below that floor -- so it works
    as a check in a script, not only as something to read.
    """
    installed = server._installed_version()
    floor = _required_floor()
    print(f"python            {sys.version.split()[0]} ({sys.executable})")
    print(f"praisonaiagents   {installed}")
    if floor:
        print(f"required          >={floor}")

    problems = []
    if installed == "unknown":
        problems.append("praisonaiagents is not installed in this environment.")
    elif floor and server._vtuple(installed) < server._vtuple(floor):
        problems.append(
            f"praisonaiagents {installed} is below the required floor >={floor}. "
            "A tool-using turn can end without the model being asked for its "
            "answer; upgrade with:  pip install -U 'praisonaiagents'")

    port = _live_port(args.home)
    print(f"engine            {'running on port ' + port if port else 'not running'}")

    if problems:
        print()
        for line in problems:
            print(f"PROBLEM: {line}")
        return 1
    print("\nAll checks passed.")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="praisonai-desktop",
        description="Drive the PraisonAI desktop engine without the GUI.")
    sub = parser.add_subparsers(dest="command", required=True)

    engine = sub.add_parser("engine", help="start or inspect the engine")
    engine_sub = engine.add_subparsers(dest="engine_command", required=True)

    start = engine_sub.add_parser("start", help="run the engine and print its port")
    start.add_argument("--home", help="data directory (sets PRAISONAI_DESKTOP_HOME)")
    start.set_defaults(func=cmd_engine_start)

    health = engine_sub.add_parser("health", help="show a running engine's health")
    health.add_argument("--home", help="data directory to look for the lockfile in")
    health.set_defaults(func=cmd_engine_health)

    chat = sub.add_parser("chat", help="run one turn against a running engine")
    chat.add_argument("prompt", help="the message to send")
    chat.add_argument("--no-tools", action="store_true", help="disable built-in tools")
    chat.add_argument("--approve", action="store_true",
                      help="auto-allow tool approval prompts (default: deny)")
    chat.add_argument("--chat-id", default="cli", help="conversation id to use")
    chat.add_argument("--home", help="data directory to look for the lockfile in")
    chat.add_argument("--timeout", type=float, default=120.0, help="seconds to wait")
    chat.set_defaults(func=cmd_chat)

    doctor = sub.add_parser("doctor", help="what is installed vs required")
    doctor.add_argument("--home", help="data directory to look for the lockfile in")
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
