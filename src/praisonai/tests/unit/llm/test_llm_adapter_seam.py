"""Anti-regression: the provider adapter must stay load-bearing.

Measured on origin/main: DefaultAdapter declares 17 methods and 11 of them have
zero call sites anywhere in praisonaiagents, while llm/llm.py carries 145 lines
of hand-written Ollama dispatch doing some of the same jobs. Nothing failed.
This file is what makes that state fail.

An adapter method that nothing calls is a lie about the extension point: someone
adding a provider implements it in good faith and their code is never reached.
"""

import ast
import pathlib

import pytest

# Empty: every DefaultAdapter method now has a live call site. Eleven were dead
# when this file was written; nine were deleted as speculative API and two were
# wired into llm.py.
#
# The allowlist mechanism is deliberately kept rather than removed, so a future
# addition has an obvious, reviewable place to be justified. It may only ever
# SHRINK: an adapter method with no consumer is the exact defect this file
# exists to prevent (root AGENTS.md: no exports without a live consumer).
KNOWN_DEAD = frozenset()

# Attribute-call receivers that denote a provider adapter. Restricting to these
# is what stops OpenAIClient.format_tools -- an unrelated method with the same
# name -- from counting as a call site for DefaultAdapter.format_tools.
ADAPTER_RECEIVERS = frozenset({"_provider_adapter", "adapter", "provider_adapter"})

# The factory that returns a provider adapter. A direct call on its result --
# get_provider_adapter(provider).foo() -- is a genuine adapter call site, so it
# is recognised via this marker rather than being mistaken for a bare receiver.
ADAPTER_FACTORIES = frozenset({"get_provider_adapter"})
ADAPTER_FACTORY_RECEIVER = "<adapter-factory>"


def _llm_package_root() -> pathlib.Path:
    import praisonaiagents.llm as llm_pkg
    return pathlib.Path(llm_pkg.__file__).parent


def _adapter_methods() -> frozenset:
    from praisonaiagents.llm.adapters import DefaultAdapter
    return frozenset(
        name for name, value in vars(DefaultAdapter).items()
        if callable(value) and not name.startswith("_")
    )


def _receiver_name(func: ast.Attribute):
    """Best-effort name of the object a method is called on."""
    value = func.value
    if isinstance(value, ast.Name):            # adapter.foo()
        return value.id
    if isinstance(value, ast.Attribute):       # self._provider_adapter.foo()
        return value.attr
    if isinstance(value, ast.Call):            # get_provider_adapter(p).foo()
        inner = value.func
        if isinstance(inner, ast.Name):
            return ADAPTER_FACTORY_RECEIVER if inner.id in ADAPTER_FACTORIES else inner.id
        if isinstance(inner, ast.Attribute):
            return ADAPTER_FACTORY_RECEIVER if inner.attr in ADAPTER_FACTORIES else inner.attr
    return None


def _call_sites() -> dict:
    """Map adapter method name -> ['relative/path.py:lineno', ...].

    Scans every module under praisonaiagents/llm/ except the adapter module
    itself, where these names are definitions rather than calls.
    """
    root = _llm_package_root()
    adapters_file = (root / "adapters" / "__init__.py").resolve()
    methods = _adapter_methods()
    found = {}
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == adapters_file:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:   # pragma: no cover
            pytest.fail(f"could not parse {path}: {exc}")
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            name = node.func.attr
            if name in methods and _receiver_name(node.func) in (
                ADAPTER_RECEIVERS | {ADAPTER_FACTORY_RECEIVER}
            ):
                found.setdefault(name, []).append(
                    f"{path.relative_to(root)}:{node.lineno}")
    return found


def test_every_adapter_method_has_a_call_site():
    """Every DefaultAdapter method is invoked on an adapter instance somewhere."""
    methods = _adapter_methods()
    called = _call_sites()
    dead = sorted(methods - set(called) - KNOWN_DEAD)
    assert not dead, (
        f"Adapter method(s) with no call site and no entry in KNOWN_DEAD: {dead}. "
        "Either wire them into llm/llm.py, delete them, or add them to KNOWN_DEAD "
        "with a justification. An adapter method that nothing calls is a lie "
        "about the extension point."
    )


def test_no_dead_name_is_actually_live():
    """KNOWN_DEAD may not name a method that now has a call site.

    Without this, KNOWN_DEAD rots into a permanent blanket exemption: a method
    gets wired, nobody removes it from the set, and the next dead method added
    beside it is never noticed.
    """
    called = _call_sites()
    stale = sorted(name for name in KNOWN_DEAD if name in called)
    assert not stale, (
        f"KNOWN_DEAD lists live method(s) {stale} -- called at "
        f"{ {n: called[n] for n in stale} }. Remove them from KNOWN_DEAD."
    )


def test_known_dead_names_all_exist():
    """KNOWN_DEAD may not name a method that no longer exists.

    Keeps the set honest after a deletion: a stale entry would silently widen
    the exemption for a future method that happens to reuse the name.
    """
    missing = sorted(KNOWN_DEAD - _adapter_methods())
    assert not missing, (
        f"KNOWN_DEAD names non-existent method(s) {missing}. Remove them from "
        "KNOWN_DEAD in the same commit as the deletion."
    )


def test_protocol_and_default_adapter_agree():
    """Every method the protocol declares exists on DefaultAdapter.

    LLMProviderAdapterProtocol is @runtime_checkable, so isinstance() only checks
    name presence -- it cannot notice a protocol method no adapter implements.
    """
    from praisonaiagents.llm.protocols import LLMProviderAdapterProtocol
    declared = frozenset(
        name for name in getattr(LLMProviderAdapterProtocol, "__protocol_attrs__", ())
        if not name.startswith("_")
    ) or frozenset(
        name for name, value in vars(LLMProviderAdapterProtocol).items()
        if callable(value) and not name.startswith("_")
    )
    missing = sorted(declared - _adapter_methods())
    assert not missing, (
        f"Protocol declares {missing} but DefaultAdapter does not implement it."
    )
