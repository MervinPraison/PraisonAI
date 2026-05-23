import ast
from pathlib import Path


def _chat_mixin_path() -> Path:
    for candidate in Path(__file__).resolve().parents:
        chat_mixin = candidate / "praisonaiagents" / "agent" / "chat_mixin.py"
        if chat_mixin.exists():
            return chat_mixin
    raise FileNotFoundError("Could not locate praisonaiagents/agent/chat_mixin.py")


def get_chat_mixin_stream_parameter_default(function_name: str):
    chat_mixin = _chat_mixin_path()
    tree = ast.parse(chat_mixin.read_text(encoding="utf-8"))

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ChatMixin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == function_name:
                    args = item.args.args
                    defaults = item.args.defaults
                    first_default_index = len(args) - len(defaults)
                    for idx, arg in enumerate(args):
                        if arg.arg == "stream":
                            default_idx = idx - first_default_index
                            if default_idx < 0:
                                raise AssertionError(
                                    f"Function '{function_name}' has no default for stream"
                                )
                            default = defaults[default_idx]
                            if isinstance(default, ast.Constant):
                                return default.value
                            raise AssertionError(
                                f"Function '{function_name}' stream default is non-constant"
                            )
    raise AssertionError(f"Function '{function_name}' or stream parameter not found")


def test_chat_completion_stream_default_is_false():
    assert get_chat_mixin_stream_parameter_default("_chat_completion") is False


def test_execute_unified_chat_completion_stream_default_is_false():
    assert (
        get_chat_mixin_stream_parameter_default("_execute_unified_chat_completion")
        is False
    )
