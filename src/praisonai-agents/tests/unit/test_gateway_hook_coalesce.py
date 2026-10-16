"""Tests for the hook burst-coalescing contract (Issue #5867)."""

import pytest

from praisonaiagents.gateway import CoalesceConfig, HookConfig


PR = {"repository": {"full_name": "o/r"}, "pull_request": {"number": 7}}


def test_default_hook_does_not_coalesce():
    hook = HookConfig(path="github")
    assert hook.coalesce is None
    assert hook.resolve_coalesce_key(PR) is None
    assert hook.to_dict()["coalesce"] is None


def test_group_key_renders_and_is_scoped_by_path():
    cfg = CoalesceConfig(group_key="{repository.full_name}#{pull_request.number}")
    a = HookConfig(path="github", coalesce=cfg).resolve_coalesce_key(PR)
    b = HookConfig(path="other", coalesce=cfg).resolve_coalesce_key(PR)
    assert a.endswith("o/r#7")
    assert a != b


def test_empty_group_key_is_not_coalesced():
    hook = HookConfig(path="g", coalesce=CoalesceConfig(group_key="{missing}"))
    assert hook.resolve_coalesce_key(PR) is None


def test_from_dict_yaml_parity():
    hook = HookConfig.from_dict({
        "path": "github",
        "coalesce": {"group_key": "{pull_request.number}", "window_seconds": 5,
                     "max_wait_seconds": 60},
    })
    assert isinstance(hook.coalesce, CoalesceConfig)
    assert hook.coalesce.window_seconds == 5.0
    assert "coalesce" not in hook.metadata
    assert hook.to_dict()["coalesce"]["max_wait_seconds"] == 60.0


def test_deadline_debounces_and_caps():
    cfg = CoalesceConfig(group_key="{x}", window_seconds=30, max_wait_seconds=100)
    assert cfg.deadline(0, 0) == 30
    assert cfg.deadline(0, 50) == 80
    assert cfg.deadline(0, 90) == 100  # max_wait caps a steady stream


@pytest.mark.parametrize("kwargs", [
    {"group_key": ""},
    {"group_key": "{x}", "window_seconds": 0},
    {"group_key": "{x}", "window_seconds": 10, "max_wait_seconds": 5},
])
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValueError):
        CoalesceConfig(**kwargs)


def test_non_finite_durations_rejected():
    import pytest
    from praisonaiagents.gateway import CoalesceConfig

    for kw in ({"window_seconds": float("inf"), "max_wait_seconds": float("inf")},
               {"window_seconds": float("nan")}):
        with pytest.raises(ValueError):
            CoalesceConfig(group_key="{pr}", **kw)
