"""Regression tests for #6355: every auto generator shares one dangerous-tool gate.

``execute_bash`` is deliberately NOT in the static
``TOOL_CATEGORIES['code_execution']`` list; it must be caught by the
live-registry name-shape check in ``_dangerous_tool_names``. Before #6355 the
workflow/job generators only consulted the static list, so it slipped through.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

LIVE_TOOLS = ["read_file", "execute_bash"]
BENIGN = "summarise this article"
OPT_IN = "write a python script and run the command"


def _workflow_yaml(topic):
    from praisonai.auto import WorkflowAutoGenerator

    adapter = MagicMock()
    adapter.name = "praisonai"
    adapter.is_available.return_value = True
    adapter.SUPPORTS_WORKFLOW = True
    registry = MagicMock()
    registry.create.return_value = adapter
    registry.pick_default.return_value = "praisonai"
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
        gen = WorkflowAutoGenerator(topic=topic, adapter_registry=registry)
    data = {
        "name": "wf",
        "agents": {"a1": {"name": "A", "role": "R", "goal": "G",
                          "instructions": "I", "tools": list(LIVE_TOOLS)}},
        "steps": [],
    }
    with patch.object(type(gen), "_available_tools", return_value=LIVE_TOOLS), \
            tempfile.TemporaryDirectory() as tmp:
        gen.workflow_file = f"{tmp}/wf.yaml"
        return Path(gen._save_workflow(data, "sequential")).read_text()


def _job_yaml(topic):
    from praisonai.auto import JobWorkflowAutoGenerator

    gen = JobWorkflowAutoGenerator(topic=topic)
    step = Mock()
    step.name, step.step_type = "gen", "agent"
    step.config = {"role": "R", "instructions": "I", "tools": list(LIVE_TOOLS)}
    data = Mock()
    data.name, data.description, data.steps = "wf", "desc", [step]
    with patch.object(type(gen), "_available_tools", return_value=LIVE_TOOLS), \
            tempfile.TemporaryDirectory() as tmp:
        gen.workflow_file = f"{tmp}/wf.yaml"
        return Path(gen._save_workflow(data)).read_text()


@pytest.mark.parametrize("render", [_workflow_yaml, _job_yaml])
def test_live_registry_exec_tool_stripped_on_benign_topic(render):
    text = render(BENIGN)
    assert "execute_bash" not in text
    assert "read_file" in text


@pytest.mark.parametrize("render", [_workflow_yaml, _job_yaml])
def test_live_registry_exec_tool_kept_when_topic_opts_in(render):
    text = render(OPT_IN)
    assert "execute_bash" in text
    assert "read_file" in text
