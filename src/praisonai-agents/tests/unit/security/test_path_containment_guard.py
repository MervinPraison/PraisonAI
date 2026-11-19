"""Guard: every file-touching tool keeps paths inside its root.

Each tool that takes a filesystem path is called with six escape forms
(absolute path outside the root, ``..``, a sibling directory whose name
starts with the root's name, ``~``, an in-root symlink to an outside
directory, and ``..`` taken through that symlink). None may read, list, write or delete outside the root.

``test_every_path_tool_is_probed`` scans the tool registry so that a new
tool with a path parameter fails here until it is probed or exempted with
a reason.
"""

from __future__ import annotations

import importlib
import inspect
import os
import re
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink fixtures need POSIX"
)

SECRET = "CANARY-7f3a91c2"
SEARCH_RE = "CANARY-7f3a[0-9a-f]+"  # matches SECRET without containing it
MARKER = "hidden_marker_q9"
VECTORS = ("absolute", "dotdot", "sibling", "tilde", "symlink", "linkup")


@pytest.fixture
def box(tmp_path, monkeypatch):
    """Root ``ws`` (the cwd) plus four places outside it that hold a secret."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "inside.txt").write_text("inside\n")
    outside, sibling, home = tmp_path / "outside", tmp_path / "ws-sib", tmp_path / "home"
    for d in (outside, sibling, home):
        (d / "scripts").mkdir(parents=True)
        (d / "canary.txt").write_text(SECRET + "\n")
        (d / f"{MARKER}.txt").write_text("x\n")
        (d / "scripts" / f"{MARKER}.py").write_text("print('x')\n")
        (d / "scripts" / "run.py").write_text(f"print('{SECRET}')\n")
    os.symlink(outside, ws / "link")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "praisonai_home"))
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    monkeypatch.delenv("PRAISONAI_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(ws)
    dirs = {
        "absolute": str(outside),
        "dotdot": "../outside",
        "sibling": str(sibling),
        "tilde": "~",
        "symlink": "link",
        "linkup": "link/../outside",  # ".." taken through the symlink
    }
    return {"ws": ws, "dirs": dirs, "outsides": (outside, sibling, home)}


def _file(box, vector, name="canary.txt"):
    return f"{box['dirs'][vector]}/{name}"


def _call(fn, *args, **kwargs):
    """Run a tool; a ValueError/PermissionError is a refusal, so return it."""
    try:
        return fn(*args, **kwargs)
    except (ValueError, PermissionError) as exc:
        return exc


def _stat_leak(result):
    """Metadata of an outside file counts as a leak."""
    return SECRET if isinstance(result, dict) and "size" in result else result


def _assert_no_leak(result):
    text = repr(result)
    assert SECRET not in text, f"secret read from outside the root: {text[:300]}"
    assert MARKER not in text, f"outside directory listed: {text[:300]}"


def _assert_outside_untouched(box):
    for d in box["outsides"]:
        names = sorted(p.name for p in d.iterdir())
        assert names == ["canary.txt", f"{MARKER}.txt", "scripts"], f"{d} changed: {names}"
        assert len(list((d / "scripts").iterdir())) == 2, f"{d}/scripts changed"
        assert (d / "canary.txt").read_text() == SECRET + "\n", f"{d}/canary.txt changed"


# --- probes: one per tool; each gets (box, vector) ------------------------


def _file_tools():
    from praisonaiagents.tools.file_tools import FileTools
    return FileTools()


def _edit_tools(box):
    from praisonaiagents.tools.edit_tools import EditTools
    return EditTools(root=str(box["ws"]))


def _skill_tools(box):
    from praisonaiagents.tools.skill_tools import SkillTools
    return SkillTools(working_directory=str(box["ws"]))


def _fast(name):
    return getattr(importlib.import_module("praisonaiagents.context.fast.search_tools"), name)


def _fast_agent(box):
    from praisonaiagents.context.fast.fast_context_agent import FastContextAgent
    return FastContextAgent(workspace_path=str(box["ws"]))


def _search(name):
    return getattr(importlib.import_module("praisonaiagents.tools.search_tools"), name)


def _lsp(name):
    return getattr(importlib.import_module("praisonaiagents.tools.lsp_tools"), name)


def _ast(name):
    return getattr(importlib.import_module("praisonaiagents.tools.ast_grep_tool"), name)


def _patch(box, v):
    target = _file(box, v, "new.txt")
    return _edit_tools(box).apply_patch(f"*** Begin Patch\n*** Add File: {target}\n+pwned\n*** End Patch\n")


PROBES = {
    # file_tools
    "read_file": lambda b, v: _call(_file_tools().read_file, _file(b, v)),
    "write_file": lambda b, v: _call(_file_tools().write_file, _file(b, v, "new.txt"), "pwned"),
    "list_files": lambda b, v: _call(_file_tools().list_files, b["dirs"][v]),
    "get_file_info": lambda b, v: _stat_leak(_call(_file_tools().get_file_info, _file(b, v))),
    "copy_file": lambda b, v: (
        _call(_file_tools().copy_file, _file(b, v), "copied.txt"),
        (b["ws"] / "copied.txt").read_text() if (b["ws"] / "copied.txt").exists() else "",
        _call(_file_tools().copy_file, "inside.txt", _file(b, v, "new.txt")),
    ),
    "move_file": lambda b, v: (
        _call(_file_tools().move_file, _file(b, v), "moved.txt"),
        _call(_file_tools().move_file, "inside.txt", _file(b, v, "new.txt")),
    ),
    "delete_file": lambda b, v: _call(_file_tools().delete_file, _file(b, v)),
    # edit_tools
    "edit_file": lambda b, v: _call(_edit_tools(b).edit_file, _file(b, v), SECRET, "pwned"),
    "edit_tools.read_file": lambda b, v: _call(_edit_tools(b).read_file, _file(b, v)),
    "search_files": lambda b, v: (
        _call(_edit_tools(b).search_files, b["dirs"][v], "CANARY-7f3a"),
        _call(_edit_tools(b).search_files, ".", "CANARY-7f3a", _file(b, v)),
    ),
    "apply_patch": lambda b, v: _call(_patch, b, v),
    # search_tools
    "grep": lambda b, v: _call(_search("grep"), SEARCH_RE, b["dirs"][v]),
    "glob": lambda b, v: _call(_search("glob"), "**/*", b["dirs"][v]),
    # skill_tools
    "read_skill_file": lambda b, v: _call(_skill_tools(b).read_skill_file, b["dirs"][v], "canary.txt"),
    "list_skill_scripts": lambda b, v: _call(_skill_tools(b).list_skill_scripts, b["dirs"][v]),
    "run_skill_script": lambda b, v: _call(
        _skill_tools(b).run_skill_script, _file(b, v, "scripts/run.py")
    ),
    # FastContext search tools
    "fast.grep_search": lambda b, v: _call(_fast("grep_search"), b["dirs"][v], SEARCH_RE, is_regex=True),
    "fast.glob_search": lambda b, v: _call(_fast("glob_search"), b["dirs"][v], "**/*"),
    "fast.list_directory": lambda b, v: _call(_fast("list_directory"), b["dirs"][v], recursive=True),
    "fast.read_file": lambda b, v: _call(_fast("read_file"), _file(b, v)),
    "fast.glob_pattern": lambda b, v: _call(_fast("glob_search"), ".", f"{b['dirs'][v]}/*"),
    # the model-facing dispatcher pins the root even if the model names one
    "fast.agent_execute_tool": lambda b, v: _call(
        _fast_agent(b).execute_tool, "grep_search", search_path=b["dirs"][v],
        pattern=SEARCH_RE, is_regex=True, workspace_root="/",
    ),
}
for _name in (
    "lsp_definition", "lsp_references", "lsp_document_symbols",
    "lsp_implementations", "lsp_incoming_calls", "lsp_outgoing_calls",
):
    PROBES[_name] = (lambda n: lambda b, v: _call(_lsp(n), file_path=_file(b, v)))(_name)
PROBES["lsp_workspace_symbols"] = lambda b, v: _call(
    _lsp("lsp_workspace_symbols"), "x", file_path=_file(b, v)
)
PROBES["lsp_hover"] = lambda b, v: _call(_lsp("lsp_hover"), _file(b, v), 1, 1)
PROBES["ast_grep_search"] = lambda b, v: _call(_ast("ast_grep_search"), "$X", "python", path=b["dirs"][v])
PROBES["ast_grep_rewrite"] = lambda b, v: _call(_ast("ast_grep_rewrite"), "$X", "y", "python", path=b["dirs"][v])
PROBES["ast_grep_scan"] = lambda b, v: _call(_ast("ast_grep_scan"), path=b["dirs"][v])

class _FakeImage:
    size = (1, 1)

    def save(self, path):
        with open(path, "w") as f:
            f.write("png")


def _screenshot(b, v):
    import praisonaiagents.tools.computer_tools as ct
    saved = ct._get_backend
    ct._get_backend = lambda: type("B", (), {"screenshot": staticmethod(_FakeImage)})()
    try:
        return _call(ct.computer_screenshot, _file(b, v, "shot.png"))
    finally:
        ct._get_backend = saved


def _crawl(b, v):
    from praisonaiagents.tools.spider_tools import SpiderTools
    spider = SpiderTools()
    spider.scrape_page = lambda url, **kw: {"url": url, "links": []}
    return _call(spider.crawl, "https://example.com/", max_pages=1, output_dir=b["dirs"][v])


def _cot():
    from praisonaiagents.tools.train.data.generatecot import GenerateCOT
    gen = GenerateCOT(qa_pairs={"q": "a"})
    gen.solutions = {"q": {"thought_process": "t"}}
    gen.cot_run_dict = lambda question: {"thought_process": "t"}
    return gen


def _cot_write(name, **kwargs):
    return lambda b, v: _call(getattr(_cot(), name), filepath=_file(b, v, "new.csv"), **kwargs)


PROBES["computer_screenshot"] = _screenshot
PROBES["crawl"] = _crawl
PROBES["cot_load_answers"] = lambda b, v: (_call(_cot().cot_load_answers, _file(b, v)), "read checked in test_path_containment_cot")
PROBES["cot_upload_to_huggingface"] = lambda b, v: _call(_cot().cot_upload_to_huggingface, "u", "d", _file(b, v, "x.csv"))
for _name in (
    "cot_save_solutions_with_qa_pairs", "cot_append_solutions_with_qa_pairs",
    "cot_export_json_with_qa_pairs", "cot_export_csv_with_qa_pairs", "cot_append_csv_with_qa_pairs",
):
    PROBES[_name] = _cot_write(_name)
PROBES["cot_save"] = _cot_write("cot_save", question="q", answer="a")

# Tools with a path parameter that are not a containment sink, with the reason.
EXEMPT = {
    "create_edit_tools": "factory; root is operator configuration",
    "create_file_tools": "factory; workspace is operator configuration",
    "create_skill_tools": "factory; working_directory is operator configuration",
    "smtp_read_inbox": "IMAP folder name, not a filesystem path",
    "execute_command": "shell tool; spill_dir is minor next to running commands (shell class)",
    "github_create_branch": "approval-gated git on repo_path (approval class)",
    "github_commit_and_push": "approval-gated git on repo_path (approval class)",
    "github_create_pull_request": "approval-gated git on repo_path (approval class)",
}

# Tools whose root walk must not follow an in-root symlink out of the root.
WALKS = {
    "list_files": lambda b: _call(_file_tools().list_files, ".", "**/*"),
    "list_files.pattern": lambda b: _call(_file_tools().list_files, ".", "link/*"),
    "search_files": lambda b: _call(_edit_tools(b).search_files, ".", "CANARY-7f3a"),
    "grep": lambda b: _call(_search("grep"), SEARCH_RE, "."),
    "glob": lambda b: _call(_search("glob"), "**/*", "."),
    "fast.grep_search": lambda b: _call(_fast("grep_search"), ".", SEARCH_RE, is_regex=True),
    "fast.glob_search": lambda b: _call(_fast("glob_search"), ".", "**/*"),
    "fast.list_directory": lambda b: _call(_fast("list_directory"), ".", recursive=True),
    "ast_grep_search": lambda b: _call(_ast("ast_grep_search"), "$X", "python", path="."),
}

# Path sinks not yet routed through resolve_inside. Shrink this, never grow it.
PENDING: dict = {}

_PATH_PARAM = re.compile(
    r"(^|_)(path|paths|file|filepath|filename|dir|directory|folder|src|dst|root)$"
)
_EXTRA_MODULES = ("praisonaiagents.context.fast.search_tools",)


def _path_tools():
    """Names of registry tools (and module tool functions) taking a path."""
    import praisonaiagents.tools as tools_pkg

    found = set()

    def visit(name, obj):
        if not callable(obj):
            return
        try:
            params = inspect.signature(obj).parameters
        except (TypeError, ValueError):
            return
        if any(_PATH_PARAM.search(p) for p in params):
            found.add(name)

    modules = set()
    for name, (module, _cls) in tools_pkg.TOOL_MAPPINGS.items():
        try:
            visit(name, getattr(tools_pkg, name))
        except (AttributeError, ImportError, TypeError):
            continue
        modules.add(module)
    for module in sorted(modules):
        try:
            mod = importlib.import_module(module, "praisonaiagents.tools")
        except ImportError:
            continue
        for fname, fn in vars(mod).items():
            if inspect.isfunction(fn) and fn.__module__ == mod.__name__ and not fname.startswith("_"):
                visit(fname, fn)
    for module in _EXTRA_MODULES:
        mod = importlib.import_module(module)
        for fname, fn in vars(mod).items():
            if inspect.isfunction(fn) and fn.__module__ == module and not fname.startswith("_"):
                visit(f"fast.{fname}", fn)
    return found


def test_every_path_tool_is_probed():
    found = _path_tools()
    # Control: the scan must reach the registry, its modules and FastContext.
    assert {"read_file", "search_files", "run_skill_script", "fast.grep_search"} <= found
    unknown = found - set(PROBES) - set(EXEMPT) - set(PENDING)
    assert not unknown, (
        f"New tool(s) take a filesystem path: {sorted(unknown)}. Route the path "
        "through praisonaiagents.tools.path_safety.resolve_inside and add a probe "
        "to PROBES (or a reasoned entry to EXEMPT)."
    )


@pytest.mark.parametrize("vector", VECTORS)
@pytest.mark.parametrize("tool", sorted(PROBES))
def test_tool_refuses_escape(box, tool, vector):
    result = PROBES[tool](box, vector)
    _assert_no_leak(result)
    _assert_outside_untouched(box)


@pytest.mark.parametrize("tool", sorted(WALKS))
def test_walk_does_not_follow_symlink_out(box, tool):
    _assert_no_leak(WALKS[tool](box))
