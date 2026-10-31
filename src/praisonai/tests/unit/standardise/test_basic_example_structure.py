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
    assert "ast.Add: operator.add" in code
    assert 'f"Unsupported operation: {type(node)}"' in code
    assert 'f"Error: {e}"' in code

    # The rendered example must be valid Python with the calculator intact.
    tree = ast.parse(code)
    functions = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert {"calculator", "_eval_node"} <= functions
    agent_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Agent"
    ]
    assert any(
        keyword.arg == "tools"
        and isinstance(keyword.value, ast.List)
        and [elt.id for elt in keyword.value.elts if isinstance(elt, ast.Name)] == ["calculator"]
        for call in agent_calls
        for keyword in call.keywords
    )


def test_tools_calculator_rejects_non_numeric_constants():
    structure = _generator()._get_feature_basic_structure("tools", "Tools")
    code = structure.split("```python\n", 1)[1].rsplit("```", 1)[0]
    calculator_def = next(
        node for node in ast.parse(code).body
        if isinstance(node, ast.FunctionDef) and node.name == "calculator"
    )
    namespace = {}
    exec(compile(ast.Module(body=[calculator_def], type_ignores=[]), "<example>", "exec"), namespace)
    calculator = namespace["calculator"]

    assert calculator("2 + 3 * 4") == "14"
    assert calculator("'x' * 3").startswith("Error:")
    assert calculator("True + 1").startswith("Error:")
    assert calculator("2 ** 10") == "1024"
    assert calculator("9 ** 100000000").startswith("Error:")
    assert calculator("2 ** 3000") == str(2 ** 3000)
    assert calculator("1 ** 5000") == "1"
    assert calculator("3 ** 5000").startswith("Error:")
    assert calculator("2 ** 4096").startswith("Error:")
    assert calculator("1e308 ** 2").startswith("Error:")


def test_basic_example_prompt_includes_feature_structure(tmp_path):
    generator = AIGenerator(sdk_root=tmp_path, use_fast_context=False)
    prompt = generator._build_basic_example_prompt("tools", "Tools", {})
    assert "def calculator(expression: str) -> str:" in prompt
