"""Tests for lazy persistence registries and DI-friendly factory (issue #2510).

Covers Gap 2a: importing ``praisonai.persistence.registry`` must not build the
process-default registries as a side effect, and ``get_default_registry`` must
return a stable, per-kind, lazily-created instance. Also verifies the factory
functions accept an injected ``registry=`` for multi-tenant isolation.
"""

import pytest

from praisonai.persistence import registry as registry_module
from praisonai.persistence.registry import (
    StoreRegistry,
    get_default_registry,
)
from praisonai.persistence.factory import (
    create_state_store,
    create_conversation_store,
    create_knowledge_store,
)


def test_import_has_no_module_level_singletons():
    """Import must not bind eager module-level registry constants.

    The legacy names resolve lazily via module ``__getattr__``; they must never
    appear in the module ``__dict__`` as an import-time side effect.
    """
    assert "CONVERSATION_STORES" not in registry_module.__dict__
    assert "KNOWLEDGE_STORES" not in registry_module.__dict__
    assert "STATE_STORES" not in registry_module.__dict__


def test_get_default_registry_is_lazy_and_stable():
    r1 = get_default_registry("state")
    r2 = get_default_registry("state")
    assert r1 is r2
    assert isinstance(r1, StoreRegistry)
    # Different kinds are different instances.
    assert get_default_registry("state") is not get_default_registry("knowledge")


def test_get_default_registry_rejects_unknown_kind():
    with pytest.raises(ValueError):
        get_default_registry("bogus")


def test_backward_compat_module_attrs_resolve():
    """Legacy ``CONVERSATION_STORES`` etc. still resolve to the default registry."""
    assert registry_module.CONVERSATION_STORES is get_default_registry("conversation")
    assert registry_module.KNOWLEDGE_STORES is get_default_registry("knowledge")
    assert registry_module.STATE_STORES is get_default_registry("state")


def test_missing_module_attr_still_raises():
    with pytest.raises(AttributeError):
        registry_module.DOES_NOT_EXIST  # noqa: B018


def test_factory_accepts_injected_registry():
    """A caller-supplied registry is used instead of the process default."""
    tenant = StoreRegistry("state", "praisonai.state_stores")

    created = {}

    def _fake(url=None, **kwargs):
        created["called"] = True
        return object()

    tenant.register("memfake", _fake)
    store = create_state_store("memfake", registry=tenant)
    assert created.get("called") is True
    assert store is not None
    # The default registry is untouched by the tenant registration.
    assert "memfake" not in get_default_registry("state").list_names()


def test_factory_defaults_to_process_registry():
    store = create_state_store("memory")
    assert store is not None
