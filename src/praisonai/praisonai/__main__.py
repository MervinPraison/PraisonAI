# __main__.py
"""
PraisonAI CLI — Unified Entry Point.

Single entry point for all CLI invocations.
Routes to Typer-based commands for known subcommands,
falls back to legacy argparse for direct prompts and YAML files.

Design:
  - Typer-first: all registered commands auto-discovered via Click
  - Legacy fallback: prompts, .yaml paths, and deprecated --flags
  - No manual command lists needed — adding a Typer command Just Works
"""

import sys
import threading


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_typer_commands_cache = None
_typer_commands_lock = threading.Lock()

# Cache for the legacy dispatcher's implemented-verb set. ``None`` means "not yet
# computed"; a frozenset once derived. Populated lazily from the legacy
# argparse builder's authoritative ``LEGACY_SPECIAL_COMMANDS`` oracle so the
# unified dispatcher never reclassifies an *implemented* verb as free text and
# bills it to an LLM (#4327).
_legacy_verbs_cache = None
_legacy_verbs_lock = threading.Lock()

# Fail-closed fallback for :func:`_get_legacy_verbs`. If importing the
# authoritative ``LEGACY_SPECIAL_COMMANDS`` oracle ever fails, we must NOT return
# an empty set — that would let an *implemented* verb (``thinking status`` etc.)
# fall through to the bare-prompt rule and be billed to an LLM, reintroducing the
# #4327 regression. This static mirror keeps the routing guard functional so such
# verbs still reach the legacy handler even when discovery is degraded. It only
# needs to stay a *superset-safe* copy of the oracle; drift merely means a newly
# added verb isn't recognised until the oracle import recovers, never a bill.
_LEGACY_VERBS_FALLBACK = frozenset({
    'chat', 'code', 'call', 'realtime', 'train', 'ui', 'context', 'research',
    'memory', 'rules', 'workflow', 'hooks', 'knowledge', 'session', 'tools',
    'todo', 'docs', 'mcp', 'commit', 'serve', 'schedule', 'skills', 'profile',
    'eval', 'agents', 'run', 'thinking', 'compaction', 'output', 'deploy',
    'templates', 'recipe', 'endpoints', 'audio', 'embed', 'embedding', 'images',
    'moderate', 'files', 'batches', 'vector-stores', 'rerank', 'ocr',
    'assistants', 'fine-tuning', 'completions', 'messages', 'guardrails', 'rag',
    'videos', 'a2a', 'containers', 'passthrough', 'responses', 'search',
    'realtime-api', 'doctor', 'registry', 'package', 'install', 'uninstall',
    'acp', 'debug', 'lsp', 'diag', 'browser', 'replay', 'bot', 'gateway',
    'sandbox', 'wizard', 'migrate', 'security', 'persistence', 'paths', 'claw',
    'github', 'managed', 'flow', 'dashboard', 'backends', 'audit',
})

# Verbs excluded from the "route implemented verbs to legacy" guard. ``containers``
# and ``vector-stores`` reach a capability that fabricates a success with zero
# network (#4322); restoring their routing would promote that fabrication from
# unreachable to user-visible, so they are held back until #4322 lands. They keep
# their current behaviour rather than being rerouted here.
_LEGACY_VERB_ROUTING_EXCLUSIONS = frozenset({"containers", "vector-stores"})

# Cache for the run command's supported option names. ``None`` means "not yet
# computed"; a tuple ``(all_opts, value_opts)`` once derived; ``False`` marks a
# discovery failure so the conservative legacy fallback is used without retrying
# the (potentially heavy) introspection on every bare-prompt invocation.
_run_option_names_cache = None
_run_option_names_lock = threading.Lock()

# Cache for the *root app* callback's options — the modern engine's GLOBAL flags
# (``--output-format``, ``--json``, ``--quiet`` ...). Click requires them *before*
# the subcommand, so they are tracked separately from ``run``'s own options.
_global_option_names_cache = None
_global_option_names_lock = threading.Lock()

# Short options whose meaning DIFFERS between the legacy argparse surface and the
# modern ``run`` command. Routing an existing YAML/prompt invocation that carries
# one of these to the modern engine would silently change its semantics:
#   -s : legacy ``--save`` (bool) vs modern ``--session`` (takes a value)
#   -f : legacy ``--file`` (input file) vs modern ``--framework``
# To guarantee zero backward-incompatible reinterpretation, their presence keeps
# the invocation on legacy (which owns them). Long forms are unambiguous and are
# unaffected — ``--session``/``--framework`` still reach the modern engine.
_LEGACY_COLLIDING_SHORT_OPTS = frozenset({"-s", "-f"})


def _introspect_option_names(command):
    """Derive ``(all_opts, value_opts)`` from a Click command's parameters.

    Single owner for the parse loop shared by :func:`_get_run_option_names` and
    :func:`_get_global_option_names`; ``all_opts`` is every long/short option
    string and ``value_opts`` is the non-flag subset that consumes a value.
    """
    all_opts = set()
    value_opts = set()
    for param in command.params:
        is_flag = getattr(param, "is_flag", False) or getattr(
            param, "is_bool_flag", False
        )
        for opt in getattr(param, "opts", []):
            if opt.startswith("-"):
                all_opts.add(opt)
                if not is_flag:
                    value_opts.add(opt)
        # Secondary opts are the negated forms of bool flags
        # (e.g. ``--no-stream``); never value-consuming.
        for opt in getattr(param, "secondary_opts", []):
            if opt.startswith("-"):
                all_opts.add(opt)
    return all_opts, value_opts


def _get_run_option_names():
    """Return the option names accepted by the Typer ``run`` command.

    Derived once, at dispatch time, by introspecting the ``run`` command's Click
    parameters — so routing never drifts from the flags ``run`` actually
    implements. Returns a tuple ``(all_opts, value_opts)`` where ``all_opts`` is
    the set of every long/short option string (e.g. ``{"--model", "-m", ...}``)
    and ``value_opts`` is the subset that consumes a following value (non-flag
    options). Returns ``None`` if introspection fails, so callers fall back to
    the conservative legacy path rather than mis-route.
    """
    global _run_option_names_cache

    if _run_option_names_cache is not None:
        return None if _run_option_names_cache is False else _run_option_names_cache

    with _run_option_names_lock:
        if _run_option_names_cache is not None:
            return None if _run_option_names_cache is False else _run_option_names_cache

        try:
            from praisonai.cli.commands.run import app as run_app
            from typer.main import get_command as _get_command

            command = _get_command(run_app)
            all_opts, value_opts = _introspect_option_names(command)
        except Exception:
            # Introspection depends only on the static command definition, so a
            # failure here is structural — cache it (as ``False``) to avoid
            # re-importing heavy modules on every bare-prompt dispatch. Callers
            # fall back to the conservative any-flag→legacy rule.
            _run_option_names_cache = False
            return None

        _run_option_names_cache = (all_opts, value_opts)
        return _run_option_names_cache


def _get_global_option_names():
    """The modern engine's *global* flags, declared on ``@app.callback`` rather
    than on any subcommand. Same ``(all_opts, value_opts)`` contract and
    ``None``-on-failure convention as :func:`_get_run_option_names`.
    """
    global _global_option_names_cache

    if _global_option_names_cache is not None:
        return None if _global_option_names_cache is False else _global_option_names_cache

    with _global_option_names_lock:
        if _global_option_names_cache is not None:
            return None if _global_option_names_cache is False else _global_option_names_cache

        try:
            from praisonai.cli.app import app as root_app
            from typer.main import get_command as _get_command

            command = _get_command(root_app)
            all_opts, value_opts = _introspect_option_names(command)
        except Exception:
            _global_option_names_cache = False
            return None

        _global_option_names_cache = (all_opts, value_opts)
        return _global_option_names_cache


def _get_dispatch_option_names():
    """Union of ``run``'s and the root callback's option names.

    Tokenising argv needs *every* value-consuming option the modern engine knows;
    without the global half, ``praisonai --output-format json version`` treats
    ``json`` as the first positional and mis-routes. ``None`` only when ``run``
    introspection failed; a global-half failure degrades to ``run``'s sets.
    """
    run_opts = _get_run_option_names()
    if run_opts is None:
        return None
    global_opts = _get_global_option_names()
    if global_opts is None:
        return run_opts
    return (run_opts[0] | global_opts[0], run_opts[1] | global_opts[1])


def _global_only_option_names():
    """Option names on the root callback but NOT on ``run``. Click accepts a
    group-level option only *before* the subcommand. Options on both (``-o``,
    ``-v``) stay with ``run``: ``praisonai "hi" -o json`` has always meant
    ``run --output json``.
    """
    run_opts = _get_run_option_names()
    global_opts = _get_global_option_names()
    if run_opts is None or global_opts is None:
        return frozenset()
    return frozenset(global_opts[0] - run_opts[0])


def _mistyped_command_suggestions(argv, first_cmd):
    """Close command matches when ``first_cmd`` is a typo'd subcommand.

    ``praisonai deploi`` is a mistyped verb, not a prompt, but the bare-prompt
    rule cannot tell them apart by shape — so it forwards it to ``run`` and the
    word is billed to an LLM. Disambiguated by the signal every CLI uses for
    "did you mean": lexical proximity to a *registered* command name. Non-empty
    only when ALL hold, so one-word prompts (``praisonai hello``) keep working:
    exactly one positional; no whitespace, path separator, ``.yaml``/``.yml``
    suffix or existing file; not itself a command; discovery succeeded; and
    difflib ratio >= 0.8 to some command.

    A high difflib ratio is necessary but not sufficient: a legitimate plural or
    extension of a command word (``tests`` for ``test``, ``runs`` for ``run``,
    ``server`` for ``serve``) also scores >= 0.8, yet is a valid prompt, not a
    typo. An extension *contains the full command as a prefix* and is therefore
    dropped so real prompts reach ``run`` untouched. A *truncation* (``deplo``
    for ``deploy``, ``versio`` for ``version``) is the opposite — a typo — so it
    is kept and suggested rather than forwarded to (and billed by) the model.
    """
    import os

    if not first_cmd or first_cmd.startswith("-"):
        return []
    if any(ch.isspace() for ch in first_cmd):
        return []
    if "/" in first_cmd or os.sep in first_cmd:
        return []
    if first_cmd.lower().endswith((".yaml", ".yml")):
        return []
    if os.path.exists(first_cmd):
        return []

    commands = _get_typer_commands()
    if not commands or first_cmd in commands:
        return []

    # Exactly one positional token — otherwise it reads as free text.
    positionals = [
        arg
        for arg, _name, kind in _iter_argv_tokens(argv, _dispatch_value_opts())
        if kind == "pos"
    ]
    if len(positionals) != 1:
        return []

    import difflib

    matches = difflib.get_close_matches(first_cmd, sorted(commands), n=3, cutoff=0.8)
    # Spare only EXTENSIONS of a command: a plural/extension (``tests`` for
    # ``test``, ``server`` for ``serve``) contains the command as a prefix and
    # is a legitimate prompt, not a typo. A TRUNCATION (``deplo`` for ``deploy``,
    # ``versio`` for ``version``) is a typo — keeping it here means it is
    # suggested, not forwarded to the model and billed as a mistaken prompt.
    matches = [cmd for cmd in matches if not first_cmd.startswith(cmd)]
    return matches


def _dispatch_value_opts():
    """Value-consuming option names for tokenisation, or the static fallback."""
    opts = _get_dispatch_option_names()
    return opts[1] if opts is not None else {"--output-format", "-o"}


def _get_typer_commands():
    """Auto-discover registered Typer commands via Click introspection."""
    global _typer_commands_cache

    # Fast path
    if _typer_commands_cache is not None:
        return _typer_commands_cache

    with _typer_commands_lock:
        if _typer_commands_cache is not None:  # Double-check
            return _typer_commands_cache

        try:
            from praisonai.cli.app import get_command_names
            commands = get_command_names()
        except Exception:
            # Do NOT poison the cache on failure — let the next caller retry.
            import logging
            logging.getLogger("praisonai.__main__").warning(
                "Typer command discovery failed; falling back to legacy dispatch.",
                exc_info=True,
            )
            return set()

        _typer_commands_cache = commands
        return _typer_commands_cache


def _get_legacy_verbs():
    """Auto-discover the legacy dispatcher's implemented-verb set.

    Sourced from the legacy argparse builder's authoritative
    ``LEGACY_SPECIAL_COMMANDS`` oracle so this stays in lockstep with the verbs
    legacy actually handles.

    Fails *closed*: if the oracle import raises, return the static
    :data:`_LEGACY_VERBS_FALLBACK` mirror rather than an empty set. An empty set
    would let an implemented verb fall through to the bare-prompt rule and be
    billed to an LLM — the #4327 regression this guard exists to prevent. The
    fallback is *not* cached so a later caller can still pick up the authoritative
    oracle once the transient import failure clears.
    """
    global _legacy_verbs_cache

    if _legacy_verbs_cache is not None:
        return _legacy_verbs_cache

    with _legacy_verbs_lock:
        if _legacy_verbs_cache is not None:  # Double-check
            return _legacy_verbs_cache

        try:
            from praisonai.cli.legacy.dispatch.argparse_builder import (
                LEGACY_SPECIAL_COMMANDS,
            )
            verbs = frozenset(LEGACY_SPECIAL_COMMANDS)
        except Exception:
            import logging
            logging.getLogger("praisonai.__main__").warning(
                "Legacy verb discovery failed; using static fallback registry so "
                "implemented verbs still route to their handler (not the LLM).",
                exc_info=True,
            )
            # Fail closed: recognise implemented verbs from the static mirror.
            # Do NOT poison the cache — a later caller can still load the oracle.
            return _LEGACY_VERBS_FALLBACK

        _legacy_verbs_cache = verbs
        return _legacy_verbs_cache


def _is_implemented_legacy_verb(first_cmd):
    """True when ``first_cmd`` is a verb the legacy dispatcher implements.

    Such a token is an *implemented command*, not free text — it must reach its
    handler on the legacy path, never be joined/quoted and billed to an LLM by
    the modern ``run`` forwarder (#4327). A small exclusion set
    (:data:`_LEGACY_VERB_ROUTING_EXCLUSIONS`) is withheld pending #4322.
    """
    if not first_cmd:
        return False
    if first_cmd in _LEGACY_VERB_ROUTING_EXCLUSIONS:
        return False
    return first_cmd in _get_legacy_verbs()


def _iter_argv_tokens(argv, value_opts=None):
    """Classify each ``argv`` token, yielding ``(arg, name, kind)``.

    Single source of truth for "which tokens are flags, and which following
    token is consumed as a flag's value". ``kind`` is one of:

      - ``"flag"``    — a dash-prefixed option token. ``name`` is its option
                        name (``--foo=bar`` → ``--foo``, otherwise ``arg``).
      - ``"value"``   — a token consumed as the *preceding* option's value.
                        ``name`` is ``None``.
      - ``"pos"``     — a plain positional token. ``name`` is ``None``.

    ``value_opts`` is the set of option names that consume a following value
    (e.g. ``--model gpt-4o``). When supplied, the token following such an option
    is classified ``"value"`` so a value beginning with a dash (``--session
    -abc``, ``--output -json``) is not mis-classified as a separate flag.
    ``--opt=value`` forms carry their value inline and need no lookahead.
    Without ``value_opts`` every dash-prefixed token is a ``"flag"`` and no
    token is consumed as a value (the original conservative behaviour).
    """
    value_opts = value_opts or set()
    expect_value = False
    for arg in argv:
        if expect_value:
            expect_value = False
            yield arg, None, "value"
            continue
        if arg.startswith("-"):
            name = arg.split("=", 1)[0]
            if "=" not in arg and name in value_opts:
                expect_value = True
            yield arg, name, "flag"
        else:
            yield arg, None, "pos"


def _find_first_command(argv, value_opts=None):
    """Find the first non-flag argument in argv.

    Skips global flags (--json, --verbose, etc.) and their values.
    Returns the first positional arg, or None if only flags are present.

    ``value_opts`` (the set of value-consuming option names) is shared with the
    other routing walks via :func:`_iter_argv_tokens` so value-consumption
    semantics stay in lockstep. When omitted it falls back to the minimal
    static set of value flags historically recognised here.
    """
    if value_opts is None:
        value_opts = {"--output-format", "-o"}
    for arg, _name, kind in _iter_argv_tokens(argv, value_opts):
        if kind == "pos":
            return arg  # First non-flag arg
    return None


def _flag_names(argv, value_opts=None):
    """Return the option *names* present in ``argv`` (``--foo=bar`` → ``--foo``).

    ``value_opts`` is the set of option names that consume a following value
    (e.g. ``--model gpt-4o``). When supplied, the token following such an option
    is treated as that option's *value* and skipped, so a value beginning with a
    dash (``--session -abc``, ``--output -json``) is not mis-classified as a
    separate flag. ``--opt=value`` forms carry their value inline and need no
    lookahead. Without ``value_opts`` the original conservative behaviour holds:
    every dash-prefixed token is reported as an option name.
    """
    return [
        name
        for _arg, name, kind in _iter_argv_tokens(argv, value_opts)
        if kind == "flag"
    ]


def _looks_like_bare_prompt(argv, first_cmd):
    """Return True when argv is a bare free-text prompt for the modern `run` path.

    A *bare prompt* is a first positional token that is neither a Typer command
    (already handled upstream) nor a ``.yaml``/``.yml`` file token. Such an
    invocation expresses the same intent as ``praisonai run "<prompt>"`` and
    should reach the modern Typer ``run`` engine (session continuity,
    ``--output`` modes, credential gate, permissions).

    Flags are allowed *iff* every flag present is one that ``run`` itself
    accepts — derived from ``run``'s own parameter definitions via
    :func:`_get_run_option_names`. So ``praisonai "fix the bug" --model gpt-4o``,
    ``--continue``, ``--session …``, ``--output …`` all reach the modern engine,
    behaving identically to ``praisonai run "…" <flag>``.

    A single genuinely legacy-only flag (``--auto``, ``--serve``, ...) keeps the
    whole invocation on the legacy argparse dispatcher, which owns that large
    deprecated flag surface. ``.yaml``/``.yml`` workflows also stay on legacy.

    If ``run`` option discovery fails, the rule falls back to its original
    conservative behaviour: any flag present routes to legacy.
    """
    if not first_cmd:
        return False
    # YAML workflow files are handled by :func:`_looks_like_yaml_run_target`,
    # which forwards them to the same modern ``run`` engine; keep them out of
    # the bare-prompt classifier so they aren't joined/quoted as free text.
    if first_cmd.lower().endswith((".yaml", ".yml")):
        return False

    # A quick, value-unaware scan first: if there are no dash-prefixed tokens at
    # all, this is a plain prompt and we can skip the (potentially heavy) run
    # option introspection entirely.
    if not any(arg.startswith("-") for arg in argv):
        return True

    dispatch_opts = _get_dispatch_option_names()
    if dispatch_opts is None:
        # Discovery failed → conservative: any flag means legacy owns it.
        return False
    supported, value_opts = dispatch_opts
    # Classify flags value-aware so a value-taking option's dash-prefixed value
    # (``--session -abc``, ``--output -json``) is not mistaken for a flag.
    flags = _flag_names(argv, value_opts)
    # A short option whose meaning differs between legacy and modern (``-s``,
    # ``-f``) keeps the invocation on legacy to avoid silent reinterpretation.
    if any(flag in _LEGACY_COLLIDING_SHORT_OPTS for flag in flags):
        return False
    # All flags must be run-supported; a single unrecognised flag → legacy.
    return all(flag in supported for flag in flags)


def _looks_like_yaml_run_target(argv, first_cmd):
    """Return True when argv is a workflow-YAML invocation for the modern engine.

    A workflow file (``praisonai agents.yaml``) expresses the same intent as
    ``praisonai run agents.yaml`` and must reach the modern Typer ``run`` engine
    so YAML is behaviourally identical to the ``run`` surface: session
    continuity (``--continue`` / ``--session`` / ``--fork``), ``--output`` modes,
    the first-run credential gate and the permission flags all apply.

    True iff ``first_cmd`` is a ``.yaml``/``.yml`` token and every flag present
    is one the modern ``run`` command accepts (derived from ``run``'s own
    parameter definitions via :func:`_get_run_option_names`). ``run`` accepts
    ``--framework``, so multi-framework YAML (``--framework crewai``) is carried
    into the modern envelope too and dispatched via the existing YAML executors.

    A single genuinely legacy-only flag keeps the whole invocation on the legacy
    argparse dispatcher, which owns that deprecated flag surface. If ``run``
    option discovery fails, the rule falls back to the conservative behaviour:
    any flag present routes to legacy.
    """
    if not first_cmd:
        return False
    if not first_cmd.lower().endswith((".yaml", ".yml")):
        return False

    # A flagless YAML target is unambiguously a modern ``run`` file target.
    if not any(arg.startswith("-") for arg in argv):
        return True

    dispatch_opts = _get_dispatch_option_names()
    if dispatch_opts is None:
        # Discovery failed → conservative: any flag means legacy owns it.
        return False
    supported, value_opts = dispatch_opts
    flags = _flag_names(argv, value_opts)
    # A short option whose meaning differs between legacy and modern (``-s``,
    # ``-f``) keeps the YAML invocation on legacy to avoid silent
    # reinterpretation of a previously-valid legacy flag.
    if any(flag in _LEGACY_COLLIDING_SHORT_OPTS for flag in flags):
        return False
    # All flags must be run-supported; a single unrecognised flag → legacy.
    return all(flag in supported for flag in flags)


def _build_run_argv(argv, value_opts):
    """Rewrite a bare-prompt ``argv`` into a ``run`` invocation.

    ``run`` takes a single positional ``target`` plus its options. An unquoted
    prompt (``praisonai fix the auth bug --model gpt-4o``) arrives as multiple
    positional tokens interleaved with flags. This joins the positional tokens
    into one ``target`` string and appends the flags (and their values) after
    it, yielding ``["run", "<prompt>", *flags]`` — exactly what the user would
    have typed as ``praisonai run "<prompt>" <flags>``.

    ``value_opts`` is the set of option names that consume a following value
    (e.g. ``--model gpt-4o``); their value token is kept with the flag rather
    than mistaken for part of the prompt. ``--opt=value`` forms are self-
    contained and need no lookahead.
    """
    global_flags, rest = _split_global_flags(argv, value_opts)
    positionals = []
    flags = []
    for arg, _name, kind in _iter_argv_tokens(rest, value_opts):
        if kind == "pos":
            positionals.append(arg)
        else:
            flags.append(arg)
    prompt = " ".join(positionals)
    return [*global_flags, "run", prompt, *flags]


def _split_global_flags(argv, value_opts):
    """Partition ``argv`` into ``(global_flag_tokens, remaining_tokens)``.

    ``--output-format json`` must be emitted as ``praisonai --output-format json
    run <target>``; appended after ``run``, Click rejects it with "No such
    option". Options ``run`` also declares stay in ``rest``.
    """
    global_only = _global_only_option_names()
    if not global_only:
        return [], list(argv)
    global_flags = []
    rest = []
    target = rest
    for arg, name, kind in _iter_argv_tokens(argv, value_opts):
        if kind == "flag":
            target = global_flags if name in global_only else rest
        elif kind == "pos":
            target = rest
        target.append(arg)
    return global_flags, rest


def _run_typer(argv):
    """Dispatch to the Typer CLI app."""
    import os
    
    # Set up safer encoding for Windows legacy terminals
    if sys.platform == "win32" and hasattr(sys.stdout, 'encoding'):
        encoding = getattr(sys.stdout, 'encoding', '').lower()
        if encoding in ('cp1252', 'cp1251', 'cp850', 'ascii') or ('cp' in encoding and encoding != 'cp65001'):
            # Force UTF-8 mode for subprocess safety
            if 'PYTHONIOENCODING' not in os.environ:
                os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    # Serialize Typer registration through the discovery lock so this path
    # cannot race with ``_get_typer_commands`` mid-registration on another
    # thread. ``register_commands()`` is idempotent on success; we hold the
    # lock around it (and not just call it) so that a concurrent
    # discoverer cannot observe a partially-registered command tree.
    # Crucially we do NOT wrap this in try/except: registration errors
    # (e.g. ``ImportError`` from a missing optional dep) must propagate
    # from ``main()`` rather than be silently downgraded to an empty
    # command set, otherwise the user just sees Typer's "no command" path
    # instead of a real diagnostic.
    from praisonai.cli.app import app, register_commands
    with _typer_commands_lock:
        register_commands()

    original = sys.argv
    sys.argv = ["praisonai"] + list(argv)
    try:
        app()
    except UnicodeEncodeError as e:
        # Handle Unicode encoding errors gracefully
        print("Error: Unable to display help due to terminal encoding limitations.", file=sys.stderr)
        print("Try setting: $env:PYTHONIOENCODING='utf-8' (PowerShell) or set PYTHONIOENCODING=utf-8 (cmd)", file=sys.stderr)
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code if isinstance(e.code, int) else 0)
    finally:
        sys.argv = original


def _run_legacy(argv):
    """Dispatch to the legacy argparse CLI (prompts, YAML, deprecated flags).

    Wrapper-enhanced: multi-framework YAML and ``--framework crewai`` paths load
    framework adapters via ``praisonai_code._wrapper_bridge`` (requires
    ``pip install praisonai``). Typer hot path remains in ``_run_typer``.
    """
    from praisonai.cli.main import PraisonAI

    original = sys.argv
    sys.argv = ["praisonai"] + list(argv)
    try:
        praison = PraisonAI()
        result = praison.main()
        code = 0 if result is None else (1 if result is False else 0)
        sys.exit(code)
    except SystemExit as e:
        sys.exit(e.code if isinstance(e.code, int) else 0)
    finally:
        sys.argv = original


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Unified CLI entry point — Typer-first, legacy fallback.

    Routing rules (in order):
      1. --version / -V          → print version and exit
      2. --help / -h             → Typer help (global or command-level)
      3. No arguments            → Typer interactive TUI
      4. First arg is a Typer cmd→ Typer (auto-discovered from app.py)
      5. Bare free-text prompt   → Typer `run` (modern engine), including when
                                   accompanied only by ``run``-supported flags
                                   (``--model``, ``--continue``, ``--output`` …)
      6. Workflow YAML file      → Typer `run <file>` (modern engine), when
                                   accompanied only by ``run``-supported flags,
                                   so ``.yaml``/``.yml`` runs gain the same
                                   session continuity, ``--output`` modes,
                                   credential gate and permissions as prompts
      7. Everything else         → Legacy (legacy-only flags), with a one-line
                                   notice on legacy-only-flag fallback
    """
    argv = sys.argv[1:]

    # 1. Quick version check (minimal imports)
    if "--version" in argv or "-V" in argv:
        from praisonai.version import __version__
        print(f"PraisonAI version {__version__}")
        return

    # 2. Help flags → always Typer (global help or command help)
    if "--help" in argv or "-h" in argv:
        _run_typer(argv)
        return

    # 3. No arguments → Typer (interactive TUI)
    if not argv:
        _run_typer(argv)
        return

    # 4. Find first non-flag argument and check if it's a Typer command.
    #    Classify value-aware when flags are present: a leading value-taking
    #    ``run`` option (e.g. ``--session abc123 agents.yaml``) must consume its
    #    following token as a *value* rather than mistake it for the first
    #    positional — otherwise the YAML/prompt target after it would be
    #    misidentified. Discovery is skipped (and the conservative static set
    #    used) when there are no dash-prefixed tokens or when introspection
    #    fails, so the fast/flagless path stays light and mis-routing is avoided.
    value_opts = None
    if any(arg.startswith("-") for arg in argv):
        dispatch_opts = _get_dispatch_option_names()
        if dispatch_opts is not None:
            value_opts = dispatch_opts[1]
    first_cmd = _find_first_command(argv, value_opts)

    if first_cmd is None:
        # Only flags, no command → Typer handles global flags
        _run_typer(argv)
        return

    if first_cmd in _get_typer_commands():
        # Known Typer command → Typer
        _run_typer(argv)
        return

    # A verb the legacy dispatcher implements is a *command*, not free text.
    # Without this guard it falls through to the bare-prompt rule below and is
    # joined/quoted into a modern ``run`` prompt and billed to an LLM (#4327):
    # ``praisonai thinking status`` costs ~2.5k tokens and exits 0 instead of
    # reaching its handler. Route it to legacy, which owns the handler.
    if _is_implemented_legacy_verb(first_cmd):
        _run_legacy(argv)
        return

    # A lone token that is a near-miss for a registered command is a mistyped
    # verb, not a prompt. Without this guard it falls through to the bare-prompt
    # rule below and is billed to an LLM: ``praisonai deploi`` costs money and
    # exits 1, where the sibling praisonai-* binaries exit 2 without running.
    suggestions = _mistyped_command_suggestions(argv, first_cmd)
    if suggestions:
        print("Error: No such command '{}'.".format(first_cmd), file=sys.stderr)
        print(
            "Did you mean: {}?".format(", ".join(suggestions)),
            file=sys.stderr,
        )
        print(
            'To run it as a prompt instead: praisonai run "{}"'.format(first_cmd),
            file=sys.stderr,
        )
        sys.exit(2)

    if _looks_like_bare_prompt(argv, first_cmd):
        # Bare free-text prompt → modern Typer `run` engine (same as
        # `praisonai run "<prompt>"`), inheriting session continuity,
        # --output modes, the credential gate and permissions.
        #
        # ``run`` takes a single positional ``target`` plus its options. An
        # unquoted prompt (``praisonai build a weather agent --model x``)
        # arrives as multiple positional tokens possibly interleaved with
        # run-supported flags; ``_build_run_argv`` joins the positionals into
        # one ``target`` and appends the flags so the whole invocation reaches
        # ``run`` intact instead of Typer rejecting the extra positionals.
        # ``value_opts`` was already derived above (value-aware first-token
        # classification), so reuse it rather than re-introspecting ``run``.
        _run_typer(_build_run_argv(argv, value_opts or set()))
    elif _looks_like_yaml_run_target(argv, first_cmd):
        # Workflow YAML file → modern Typer `run <file>` engine (same as
        # `praisonai run agents.yaml`), inheriting session continuity,
        # --output modes, the credential gate and permissions. The YAML target
        # is already a single positional token, so the argv is forwarded intact
        # after the `run` command — the existing YAML executors run *inside* the
        # modern session/output/credential/permission envelope.
        yaml_globals, yaml_rest = _split_global_flags(argv, value_opts or set())
        _run_typer([*yaml_globals, "run", *yaml_rest])
    else:
        # Legacy/deprecated-flag invocation → legacy. This is reached only when
        # a YAML workflow or prompt carries a flag the modern engine does not
        # implement. Surface a one-line notice so the fallback is never silent —
        # the modern `praisonai run` owns session continuity, --output modes,
        # the credential gate and permissions that legacy lacks.
        if _flag_names(argv):
            print(
                "Note: '{}' contains a flag not supported by the modern engine; "
                "using the legacy engine. For session continuity, --output modes "
                "and permissions, try: praisonai run \"{}\" ...".format(
                    first_cmd, first_cmd
                ),
                file=sys.stderr,
            )
        _run_legacy(argv)


if __name__ == "__main__":
    main()