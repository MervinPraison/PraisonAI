"""What models this actually supports.

`model_name` was a free-text string with no validation anywhere. A typo was
caught by Hugging Face — after the CLI had accepted it, after the environment
was built, sometimes after a partial download. And nothing told a new user
which models work: `config.yaml` offers exactly one example, from the
Llama-3.1 era.

Unsloth already maintains the list — `unsloth/models/mapper.py` has 246
distinct 4-bit repos and is updated with every release. So this reads that at
runtime rather than vendoring a copy, because a hand-written catalog is stale
the day it is written. `CURATED` is the fallback for when unsloth is not
installed (the CLI is importable without the training extra) and the starting
point for `praisonai-train models` with no filter.
"""

from __future__ import annotations

import difflib
import functools

# A small, deliberately opinionated starting set: one current model per family,
# sized to fit a single 24 GB card in 4-bit. Not a substitute for the mapper --
# a signpost for someone who has not chosen yet.
CURATED = (
    "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
    "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    "unsloth/gemma-2-9b-it-bnb-4bit",
    "unsloth/mistral-7b-instruct-v0.3-bnb-4bit",
    "unsloth/Phi-3.5-mini-instruct-bnb-4bit",
    "unsloth/Qwen2.5-3B-Instruct-bnb-4bit",
    "unsloth/gemma-2-2b-it-bnb-4bit",
)


@functools.lru_cache(maxsize=1)
def known_models() -> tuple:
    """Every model unsloth maps, or the curated set if it is not installed.

    Cached: the mapper is a large module-level dict and this is consulted on
    every config validation.
    """
    try:
        from unsloth.models.mapper import INT_TO_FLOAT_MAPPER, FLOAT_TO_INT_MAPPER
    except ImportError:
        return tuple(CURATED)
    names = set(INT_TO_FLOAT_MAPPER) | set(FLOAT_TO_INT_MAPPER)
    names.update(v for v in INT_TO_FLOAT_MAPPER.values() if isinstance(v, str))
    return tuple(sorted(n for n in names if isinstance(n, str) and "/" in n))


def is_known(name: str) -> bool:
    return bool(name) and name in known_models()


def suggest(name: str, n: int = 3) -> list:
    """Close matches for a name that is not in the catalog.

    Matched on the repo name rather than the full id, so a right model under
    the wrong org still surfaces -- `meta-llama/...` should suggest the unsloth
    mirror of the same thing.
    """
    if not name:
        return []
    target = name.rsplit("/", 1)[-1].lower()
    catalog = known_models()
    by_repo = {n.rsplit("/", 1)[-1].lower(): n for n in catalog}
    hits = difflib.get_close_matches(target, list(by_repo), n=n, cutoff=0.6)
    return [by_repo[h] for h in hits]


def describe_unknown(name: str) -> str:
    """The message for a model we cannot vouch for.

    Deliberately a warning rather than a refusal: unsloth loads plenty of
    models it does not map (loader.py falls through to the generic path), so
    refusing would block working configurations. It says what it does not know
    and offers the nearest thing.
    """
    lines = [f"'{name}' is not in unsloth's model list, so it may not load."]
    close = suggest(name)
    if close:
        lines.append("Did you mean: " + ", ".join(close) + "?")
    else:
        lines.append("Known-good starting points: " + ", ".join(CURATED[:3]) + ".")
    lines.append("Run `praisonai-train models` to see the full list.")
    return " ".join(lines)
