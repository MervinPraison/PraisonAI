import ast
from pathlib import Path


def _get_stream_default(function_name: str):
    chat_mixin = (
        Path(__file__).resolve().parents[3]
        / "praisonaiagents"
        / "agent"
        / "chat_mixin.py"
    )
    tree = ast.parse(chat_mixin.read_text(encoding="utf-8"))

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ChatMixin":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == function_name:
                    args = item.args.args
                    defaults = item.args.defaults
                    defaults_start = len(args) - len(defaults)
                    for idx, arg in enumerate(args):
                        if arg.arg == "stream":
                            default_idx = idx - defaults_start
                            if default_idx < 0:
                                return None
                            default = defaults[default_idx]
                            if isinstance(default, ast.Constant):
                                return default.value
                            return None
    return None


def test_chat_completion_sync_stream_default_is_false():
    assert _get_stream_default("_chat_completion") is False


def test_unified_chat_completion_sync_stream_default_is_false():
    assert _get_stream_default("_execute_unified_chat_completion") is False
