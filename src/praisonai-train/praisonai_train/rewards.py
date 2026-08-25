"""Resolving reward functions named in a config.

GRPO scores generated completions with one or more reward functions. They are
Python callables, and a YAML config can only carry a string — so the string has
to name the callable.

**The convention here is a dotted import path**, `module:function`, the same
form `console_scripts` and gunicorn use:

    method: grpo
    reward_funcs:
      - myproject.rewards:length_penalty
      - myproject.rewards:contains_answer

Two alternatives were possible and were not chosen. A registry populated by
decorator would mean the config can only name functions from a module something
else already imported, which is a worse failure to debug. Inline Python in YAML
is a code-execution surface in a file people paste from the internet.

An import path is inspectable before anything runs: `praisonai-train llm
--dry-run` resolves every one and reports the ones that do not exist, before
the GPU time. That is the property the other two lack.

TRL calls each with `(prompts, completions, **kwargs)` and expects a list of
floats, one per completion.
"""

from __future__ import annotations

import importlib
import inspect


class RewardError(ValueError):
    """A reward function that cannot be resolved or is the wrong shape."""


def resolve(spec):
    """Import `module:function` and return the callable.

    Raises RewardError naming the part that failed, because "no module named
    x" and "module x has no attribute y" need different fixes and the bare
    ImportError does not say which happened.
    """
    if callable(spec):
        return spec
    if not isinstance(spec, str) or ":" not in spec:
        raise RewardError(
            f"reward function {spec!r} is not a 'module:function' path. "
            "Example: myproject.rewards:length_penalty")
    module_name, _, attr = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise RewardError(
            f"cannot import '{module_name}' for reward function '{spec}': {exc}. "
            "Is it on PYTHONPATH?") from exc
    try:
        fn = getattr(module, attr)
    except AttributeError as exc:
        available = [n for n in dir(module) if not n.startswith("_") and callable(
            getattr(module, n, None))]
        raise RewardError(
            f"'{module_name}' has no '{attr}'. Callables there: "
            f"{', '.join(sorted(available)[:8]) or 'none'}") from exc
    if not callable(fn):
        raise RewardError(f"'{spec}' is a {type(fn).__name__}, not a function")
    return fn


def check_signature(fn, spec=""):
    """Warn-level check that `fn` looks like a TRL reward function.

    TRL calls (prompts, completions, **kwargs). A function that cannot accept
    that fails deep inside the training loop, after the model is loaded --
    catching it here costs nothing.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None      # builtins and C callables; let TRL decide
    params = list(sig.parameters.values())
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        positional = [p for p in params
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if len(positional) >= 2:
            return None
    names = [p.name for p in params]
    if "completions" in names:
        return None
    return (f"{spec or getattr(fn, '__name__', 'reward function')} does not take "
            "'completions'; TRL calls reward functions as "
            "(prompts, completions, **kwargs)")


def resolve_all(specs):
    """Resolve a list, or a single spec, into callables.

    Every failure is collected rather than raised on the first, so someone with
    three broken paths fixes all three in one pass instead of three runs.
    """
    if specs is None:
        return []
    if isinstance(specs, (str,)) or callable(specs):
        specs = [specs]
    resolved, problems, warnings = [], [], []
    for spec in specs:
        try:
            fn = resolve(spec)
        except RewardError as exc:
            problems.append(str(exc))
            continue
        resolved.append(fn)
        note = check_signature(fn, spec if isinstance(spec, str) else "")
        if note:
            warnings.append(note)
    if problems:
        raise RewardError("\n".join(problems))
    for note in warnings:
        print(f"WARNING: {note}")
    return resolved


MISSING_REWARDS = (
    "method '{method}' needs reward_funcs: a list of 'module:function' import "
    "paths that score completions. Example:\n"
    "  reward_funcs:\n"
    "    - myproject.rewards:length_penalty"
)


def require(method, resolved):
    """Raise unless `method` has the reward functions it cannot run without.

    Separate from the trainer so it can be tested by calling it. A test that
    greps train_model's source for the message passes with the branch disabled,
    which is how this kind of guard goes missing.
    """
    if not resolved:
        raise RewardError(MISSING_REWARDS.format(method=method))
    return resolved
