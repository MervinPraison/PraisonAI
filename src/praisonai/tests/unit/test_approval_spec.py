from praisonai._approval_spec import ApprovalSpec


def test_from_yaml_prefers_primary_keys_over_legacy_aliases():
    spec = ApprovalSpec.from_yaml(
        {
            "enabled": True,
            "backend": "console",
            "approve_all_tools": False,
            "all_tools": True,
            "timeout": 0,
            "approval_timeout": 30,
        }
    )

    assert spec.approve_all_tools is False
    assert spec.timeout == 0
