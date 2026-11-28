"""The ``instructions`` -> ``backstory`` YAML fallback applies to every agent shape (#6714)."""

import pytest

from praisonai.agents_generator import _normalize_yaml_config


@pytest.mark.parametrize(
    "config, bucket, key",
    [
        ({"agents": [{"name": "writer", "instructions": "Write well."}]}, "agents", "writer"),
        ({"agents": {"writer": {"instructions": "Write well."}}}, "agents", "writer"),
        ({"roles": [{"name": "writer", "instructions": "Write well."}]}, "roles", "writer"),
        ({"roles": {"writer": {"instructions": "Write well."}}}, "roles", "writer"),
    ],
)
def test_instructions_fill_backstory(config, bucket, key):
    normalized = _normalize_yaml_config(config, strict=False)
    assert normalized[bucket][key]["backstory"] == "Write well."


def test_explicit_backstory_is_kept_for_roles_list():
    config = {"roles": [{"name": "writer", "instructions": "Write well.", "backstory": "Veteran editor."}]}
    normalized = _normalize_yaml_config(config, strict=False)
    assert normalized["roles"]["writer"]["backstory"] == "Veteran editor."
