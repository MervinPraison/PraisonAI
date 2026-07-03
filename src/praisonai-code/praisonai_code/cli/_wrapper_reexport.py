"""Re-export a wrapper submodule into a praisonai-code bridge module."""

from __future__ import annotations

from types import ModuleType


def load_wrapper_module(wrapper_name: str) -> ModuleType:
    from praisonai_code._wrapper_bridge import import_wrapper_module

    return import_wrapper_module(wrapper_name)


def populate_from_module(target_globals: dict, source: ModuleType) -> None:
    """Re-export ``source``'s public attributes into ``target_globals``.

    A snapshot of current attributes is copied so ``from bridge import Name``
    keeps working, and a live PEP 562 ``__getattr__`` proxy is installed so
    later reassignments on ``source`` (e.g. test monkeypatching) stay visible
    through the bridge.
    """
    for name, value in vars(source).items():
        if name.startswith("__"):
            continue
        target_globals[name] = value

    def __getattr__(name: str):
        try:
            return getattr(source, name)
        except AttributeError as exc:  # pragma: no cover - defensive
            raise AttributeError(
                f"module {target_globals.get('__name__', '?')!r} "
                f"has no attribute {name!r}"
            ) from exc

    target_globals["__getattr__"] = __getattr__
