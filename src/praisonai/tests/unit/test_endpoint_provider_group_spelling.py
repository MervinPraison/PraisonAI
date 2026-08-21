"""Both endpoint-provider readers must scan the same entry-point group.

``praisonai/endpoints/registry.py`` read ``praisonai.endpoint_providers`` while
``praisonai_code/cli/features/_endpoint_registry.py`` read
``praisonai.endpoints.providers``. Neither was declared anywhere, so a plugin
author guessed - and the wrong guess made ``endpoints invoke --type <plugin>``
silently run the *recipe* provider and report success.
"""

import pathlib
import warnings
from importlib.metadata import EntryPoint

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

import praisonai_code._registry as base_registry
from praisonai.endpoints import registry as endpoints_registry
from praisonai.endpoints.discovery import EndpointInfo, ProviderInfo
from praisonai.endpoints.providers.base import BaseProvider, HealthResult, InvokeResult
from praisonai_code.cli.features import _endpoint_registry as cli_registry

CANONICAL = "praisonai.endpoint_providers"
LEGACY = "praisonai.endpoints.providers"


class AcmeProvider(BaseProvider):
    provider_type = "acme"

    def get_provider_info(self):
        return ProviderInfo(provider_type="acme", name="acme", base_url=self.base_url)

    def list_endpoints(self, tags=None):
        return [EndpointInfo(name="acme-echo", provider_type="acme")]

    def describe_endpoint(self, name):
        return EndpointInfo(name=name, provider_type="acme")

    def invoke(self, name, input_data=None, config=None, stream=False):
        if stream:
            raise AssertionError("streaming must route through invoke_stream")
        return InvokeResult(ok=True, data={"acme": True, "endpoint": name})

    def invoke_stream(self, name, input_data=None, config=None):
        yield {"event": "data", "data": {"chunk": 1}}
        yield {"event": "done", "data": "[DONE]"}

    def health(self):
        return HealthResult(healthy=True, provider_type="acme")


def _reset_cli_registry_default(monkeypatch):
    """``EndpointProviderRegistry.default()`` caches a process-wide singleton in
    the subclass ``__dict__``. Any earlier test in the full suite warms it, after
    which the monkeypatched ``entry_points`` below is never re-scanned - the CLI
    then resolves ``acme`` against a stale cache, falls through to the recipe
    path and posts to ``/v1/recipes/run`` (the ``assert 2 == 0`` failure seen
    only in the full CI run, not in isolation).

    Crucially there are *two* class objects: ``cmd_invoke`` imports the registry
    as ``praisonai.cli.features._endpoint_registry`` (the compatibility shim
    re-exports ``praisonai_code``'s module under the ``praisonai`` namespace via
    ``__path__``), while this test imports it as
    ``praisonai_code.cli.features._endpoint_registry``. They are distinct classes
    with *independent* ``default()`` caches, so resetting only the one this test
    imports leaves the handler's stale. Drop the cached instance on every such
    class so the next ``default()`` rediscovers under the patched entry points;
    ``monkeypatch`` restores the originals on teardown, keeping other tests
    unaffected.
    """
    registry_classes = {cli_registry.EndpointProviderRegistry}
    try:  # the exact class ``cmd_invoke`` resolves through the shim namespace
        from praisonai.cli.features._endpoint_registry import (
            EndpointProviderRegistry as _handler_registry,
        )

        registry_classes.add(_handler_registry)
    except Exception:  # pragma: no cover - shim always importable in this suite
        pass

    for registry_cls in registry_classes:
        if "_default_instance" in registry_cls.__dict__:
            monkeypatch.delattr(registry_cls, "_default_instance", raising=False)


def _publish(monkeypatch, group, name="acme"):
    ep = EntryPoint(name=name, value="x:y", group=group)
    monkeypatch.setattr(ep.__class__, "load", lambda self: AcmeProvider, raising=False)
    monkeypatch.setattr(
        base_registry, "entry_points", lambda *, group: [ep] if group == _publish.group else []
    )
    _publish.group = group
    _reset_cli_registry_default(monkeypatch)


_SINGLETON_REGISTRIES = (
    cli_registry.EndpointProviderRegistry,
    endpoints_registry.ProviderRegistry,
)


def _evict_default_registries():
    """Drop the per-class ``.default()`` singletons.

    ``EndpointProviderRegistry.default()`` caches a per-class instance whose
    entry-point discovery runs once at construction. ``cmd_invoke`` resolves
    providers through that cache, so a singleton built by an earlier test on the
    same xdist worker — before this file publishes ``acme`` — never sees the
    plugin and the CLI silently falls back to the recipe HTTP path
    (``assert http == [] ⇒ assert 2 == 0``). Evicting before and after each case
    forces rediscovery against the freshly published plugin and prevents a
    poisoned instance from leaking to later tests.
    """
    for registry_cls in _SINGLETON_REGISTRIES:
        if "_default_instance" in registry_cls.__dict__:
            delattr(registry_cls, "_default_instance")


@pytest.fixture(params=[CANONICAL, LEGACY], ids=["canonical", "legacy"])
def published(request, monkeypatch):
    _publish(monkeypatch, request.param)
    _evict_default_registries()
    yield request.param
    _evict_default_registries()


def test_both_readers_see_the_plugin(published):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert "acme" in endpoints_registry.ProviderRegistry().list_names()
        assert "acme" in cli_registry.EndpointProviderRegistry().list_names()


def test_only_the_legacy_group_warns(monkeypatch):
    _publish(monkeypatch, CANONICAL)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        endpoints_registry.ProviderRegistry()
    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)]

    _publish(monkeypatch, LEGACY)
    with pytest.warns(DeprecationWarning, match=r"praisonai\.endpoints\.providers"):
        endpoints_registry.ProviderRegistry()


def test_builtin_cannot_be_hijacked_by_a_plugin(monkeypatch):
    _publish(monkeypatch, CANONICAL, name="recipe")
    resolved = cli_registry.EndpointProviderRegistry().resolve("recipe")
    assert resolved.__name__ == "invoke_recipe"


def test_openai_compat_is_registered():
    assert "openai-compat" in endpoints_registry.ProviderRegistry().list_names()
    assert "openai-compat" in cli_registry.EndpointProviderRegistry().list_names()


def _handler():
    from praisonai.cli.features.endpoints import EndpointsHandler

    handler = EndpointsHandler()
    handler._try_unified_discovery = lambda url=None: None
    http = []
    handler._make_request = lambda method, path, **kw: (
        http.append((method, path)) or {"status": 200, "data": {"ok": True}}
    )
    return handler, http


def test_invoke_routes_to_the_plugin(published):
    handler, http = _handler()
    seen = []
    original = handler._handle_invoke_result
    handler._handle_invoke_result = lambda result, name, parsed: (
        seen.append(result) or original(result, name, parsed)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        rc = handler.cmd_invoke(["acme-echo", "--type", "acme"])
    assert rc == 0
    assert http == []  # NOT posted to /v1/recipes/run
    assert seen[0]["data"] == {"acme": True, "endpoint": "acme-echo"}


def test_unknown_type_errors_instead_of_running_a_recipe():
    handler, http = _handler()
    assert handler.cmd_invoke(["x", "--type", "bogus"]) == handler.EXIT_VALIDATION_ERROR
    assert http == []


def test_stream_routes_through_provider_invoke_stream(published):
    """``--stream`` must consume ``BaseProvider.invoke_stream`` rather than
    calling ``invoke(stream=True)`` (whose result the CLI cannot render)."""
    handler, http = _handler()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        rc = handler.cmd_invoke(["acme-echo", "--type", "acme", "--stream"])
    # AcmeProvider.invoke raises if reached with stream=True; reaching here with
    # a success code proves invoke_stream drove the output instead.
    assert rc == handler.EXIT_SUCCESS
    assert http == []


def test_canonical_group_is_declared_in_pyproject():
    root = pathlib.Path(endpoints_registry.__file__).resolve().parents[2]
    groups = tomllib.loads((root / "pyproject.toml").read_text())["project"]["entry-points"]
    assert CANONICAL in groups
    assert set(groups[CANONICAL]) >= {"recipe", "agents-api", "mcp", "a2a", "a2u"}
