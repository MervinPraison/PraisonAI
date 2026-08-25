"""The generator must only advertise memory backends that actually resolve.

Regression for #4229: the capability list handed to the model was a literal
that still named removed backends (redis/postgres/qdrant), so generated code
raised before reaching the API. Derive it from the live resolver instead, and
prove every advertised preset and URL scheme resolves.
"""
from praisonaiagents.config.feature_configs import MemoryConfig
from praisonaiagents.config.param_resolver import resolve, ArrayMode
from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
from praisonai.standardise.ai_generator import AIGenerator


def _memory_caps():
    gen = AIGenerator.__new__(AIGenerator)
    return AIGenerator._detect_feature_capabilities(gen, "memory", {})


def _resolve_memory(value):
    """Resolve a memory preset/URL the same way Agent.__init__ does."""
    return resolve(
        value=value,
        param_name="memory",
        config_class=MemoryConfig,
        presets=MEMORY_PRESETS,
        url_schemes=MEMORY_URL_SCHEMES,
        array_mode=ArrayMode.SINGLE_OR_LIST,
        default=None,
    )


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
    """Each preset the generator teaches must resolve via the unified resolver."""
    for preset in _memory_caps()["supports_presets"]:
        cfg = _resolve_memory(preset)
        assert cfg is not None, f"preset {preset!r} did not resolve"
        assert isinstance(cfg, MemoryConfig), f"preset {preset!r} -> {type(cfg)}"
        backend = cfg.backend.value if hasattr(cfg.backend, "value") else cfg.backend
        assert backend is not None, f"preset {preset!r} has no backend"


def test_every_advertised_url_scheme_resolves():
    """Each URL scheme the generator teaches must resolve via the unified resolver."""
    for scheme in _memory_caps()["supports_url_schemes"]:
        cfg = _resolve_memory(f"{scheme}://localhost/db")
        assert isinstance(cfg, MemoryConfig), f"scheme {scheme!r} did not resolve to MemoryConfig"
        backend = cfg.backend.value if hasattr(cfg.backend, "value") else cfg.backend
        assert backend is not None
