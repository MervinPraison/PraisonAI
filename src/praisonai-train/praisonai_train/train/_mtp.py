"""Multi-Token Prediction (MTP) drafter resolution and download.

Gemma-4 supports *lossless* fast inference via self-speculative decoding using a
SEPARATE, stock drafter model — you do NOT retrain it, even for a fine-tuned
target. This module maps a (fine-tuned or base) Gemma-4 model name to the matching
stock MTP drafter on the Hugging Face Hub and downloads it on demand.

Heavy deps (``huggingface_hub``) are imported lazily inside the functions so that
importing this module never requires the Hub client to be installed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple

# --------------------------------------------------------------------------- #
# Drafter table
# --------------------------------------------------------------------------- #
# Each Gemma-4 size ships a stock MTP drafter under `MTP/` in its unsloth GGUF
# repo. The precision selects which quantized drafter file to pull.
_PRECISIONS = {
    "q8_0": "Q8_0",
    "bf16": "BF16",
    "f16": "F16",
}

# size-key -> (repo_id, drafter basename stem). The drafter file is
# `MTP/mtp-gemma-4-<SIZE>-it-<PRECISION>.gguf` inside `<repo_id>`.
# Only sizes with a stock MTP drafter actually published (verified on the Hub).
MTP_DRAFTERS = {
    "e2b": "unsloth/gemma-4-E2B-it-GGUF",
    "e4b": "unsloth/gemma-4-E4B-it-GGUF",
    "12b": "unsloth/gemma-4-12b-it-GGUF",
}

# Display size (used to build the file/repo names) keyed by the lowercase size key.
_SIZE_DISPLAY = {
    "e2b": "E2B",
    "e4b": "E4B",
    "12b": "12b",
}


def _detect_size(model_name: str) -> Optional[str]:
    """Return the lowercase MTP size key (e.g. ``"e4b"``) for a Gemma-4 model name.

    Matches any name that mentions ``gemma-4`` (or ``gemma4``) followed by a known
    size token, in any casing and regardless of an org prefix or fine-tune suffix,
    e.g. ``mervinpraison/praisonai-gemma-4-E4B-tamil``. Returns None for non
    Gemma-4 families.
    """
    lowered = model_name.lower()
    # Must be the Gemma-4 family; reject qwen/llama/gemma-2/etc.
    if "gemma-4" not in lowered and "gemma4" not in lowered:
        return None
    for key in MTP_DRAFTERS:
        # size token bounded by non-alphanumerics (or string edges) so "e4b" does
        # not accidentally match inside another token.
        if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", lowered):
            return key
    return None


def is_mtp_supported(model_name: str) -> bool:
    """True if a stock MTP drafter exists for this model's family+size."""
    return _detect_size(model_name) is not None


def resolve_drafter(model_name: str, precision: str = "q8_0") -> Optional[Tuple[str, str]]:
    """Resolve a Gemma-4 model name to its stock MTP drafter ``(repo_id, filename)``.

    Args:
        model_name: Target model name/id (base or fine-tuned). May include an org
            prefix and a fine-tune suffix — only the family + size matter.
        precision: One of ``q8_0`` (default), ``bf16``, ``f16``.

    Returns:
        ``(repo_id, filename)`` where ``filename`` is the path within the repo
        (e.g. ``MTP/mtp-gemma-4-E4B-it-Q8_0.gguf``), or ``None`` if the family is
        unsupported (non Gemma-4).
    """
    size = _detect_size(model_name)
    if size is None:
        return None
    repo_id = MTP_DRAFTERS[size]
    prec = _PRECISIONS.get(precision.lower())
    if prec is None:
        valid = ", ".join(sorted(_PRECISIONS))
        raise ValueError(
            f"Unknown MTP drafter precision {precision!r}. Choose one of: {valid}."
        )
    display = _SIZE_DISPLAY[size]
    filename = f"MTP/mtp-gemma-4-{display}-it-{prec}.gguf"
    return repo_id, filename


def fetch_drafter(
    model_name: str,
    dest_dir: str | Path,
    precision: str = "q8_0",
) -> Path:
    """Download the stock MTP drafter for ``model_name`` into ``dest_dir``.

    Args:
        model_name: Target model name/id (base or fine-tuned).
        dest_dir: Local directory to place the downloaded drafter GGUF in.
        precision: Drafter precision (``q8_0`` | ``bf16`` | ``f16``).

    Returns:
        Local ``Path`` to the downloaded drafter GGUF.

    Raises:
        ValueError: If the model family has no stock MTP drafter (with actionable
            guidance).
    """
    resolved = resolve_drafter(model_name, precision=precision)
    if resolved is None:
        raise ValueError(
            f"No stock MTP drafter is available for '{model_name}'. MTP fast inference "
            "is currently supported only for the Gemma-4 family (E2B, E4B, 12B). "
            "Serve without a drafter, or pick a Gemma-4 target."
        )
    repo_id, filename = resolved

    # Lazy import: importing this module must not require huggingface_hub.
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - exercised via friendly message
        raise ValueError(
            "huggingface_hub is required to download the MTP drafter. "
            'Install it with: pip install "praisonai-train[llm]" (or pip install huggingface_hub).'
        ) from exc

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(dest_dir),
        token=os.environ.get("HF_TOKEN"),
    )
    return Path(local_path)
