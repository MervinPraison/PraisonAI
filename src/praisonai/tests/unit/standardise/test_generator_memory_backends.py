"""The generator must only advertise memory backends that actually resolve.

Regression for #4229: the capability list handed to the model was a literal
that still named removed backends (redis/postgres/qdrant), so generated code
raised before reaching the API. Derive it from the live resolver instead, and
prove every advertised preset and URL scheme resolves.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
from praisonai.standardise.ai_generator import AIGenerator


def _memory_caps():
    gen = AIGenerator.__new__(AIGenerator)
    return AIGenerator._detect_feature_capabilities(gen, "memory", {})


def test_generator_presets_match_the_live_resolver():
    caps = _memory_caps()
    assert caps["supports_presets"] == sorted(MEMORY_PRESETS)
    assert caps["supports_url_schemes"] == sorted(MEMORY_URL_SCHEMES)


def test_generator_never_advertises_a_removed_backend():
    caps = _memory_caps()
    blob = repr(caps)
    for dead in ("redis", "postgres", "postgresql", "qdrant"):
        assert dead not in blob, f"generator still advertises dead backend {dead!r}"


def test_every_advertised_preset_resolves():
    """Each preset the generator teaches must resolve to a live backend.

    A preset "resolves" when the resolver routes it to a real backend. Some
    backends (e.g. mem0's managed client) additionally require credentials at
    construction time; a missing-credential error still proves the preset is
    live, so it is treated as resolved. What must never happen is the resolver
    itself rejecting the preset as unknown/removed.
    """
    for preset in _memory_caps()["supports_presets"]:
        try:
            Agent(instructions="t", memory=preset)
        except ValueError as exc:
            if "api key" not in str(exc).lower():
                raise


def test_every_advertised_url_scheme_resolves():
    for scheme in _memory_caps()["supports_url_schemes"]:
        Agent(instructions="t", memory=f"{scheme}://localhost/db")
