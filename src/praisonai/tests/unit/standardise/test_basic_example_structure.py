"""Basic example structures must render without evaluating the embedded code.

Regression: the ``tools`` template is an f-string whose example code contains
literal braces (the ``ops`` dict, ``{type(node)}`` and ``{e}``). They were not
escaped, so building the structures dict raised ``TypeError`` (and would hit
``NameError`` for ``node``/``e``) for every feature, breaking basic example
prompt generation.
"""
import ast

import pytest

from praisonai.standardise.ai_generator import AIGenerator


def _generator():
    return AIGenerator(use_fast_context=False)


@pytest.mark.parametrize(
    "slug",
    ["guardrails", "memory", "tools", "knowledge", "streaming", "handoffs"],
)
def test_basic_structure_renders_for_every_feature(slug):
    structure = _generator()._get_feature_basic_structure(slug, "Demo")
    assert structure.startswith("```python\n")
    assert '"""Demo - Basic Example"""' in structure


def test_tools_structure_contains_runnable_calculator():
    structure = _generator()._get_feature_basic_structure("tools", "Tools")
    code = structure.split("```python\n", 1)[1].rsplit("```", 1)[0]
    assert "{{" not in code and "}}" not in code
    assert "ops = {" in code
    assert 'f"Unsupported operation: {type(node)}"' in code
    assert 'f"Error: {e}"' in code

    # The rendered example must be valid Python with the calculator intact.
    tree = ast.parse(code)
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert {"calculator", "_eval_node"} <= functions


def test_basic_example_prompt_includes_feature_structure(tmp_path):
    generator = AIGenerator(sdk_root=tmp_path, use_fast_context=False)
    prompt = generator._build_basic_example_prompt("tools", "Tools", {})
    assert "def calculator(expression: str) -> str:" in prompt
