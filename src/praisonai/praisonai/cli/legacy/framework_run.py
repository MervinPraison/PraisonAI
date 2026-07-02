"""Framework adapter lazy imports for legacy YAML / multi-framework runs."""

from __future__ import annotations


def fw_registry_module():
    from praisonai.framework_adapters import registry
    return registry


def fw_validators_module():
    from praisonai.framework_adapters import validators
    return validators


def fw_workflow_module():
    from praisonai.framework_adapters import workflow_framework
    return workflow_framework
