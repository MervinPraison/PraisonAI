"""Wrapper file tools and stores keep caller paths inside their root.

Covers ``code_list_files``, ``multiedit``'s model-visible ``workspace_root``
and the template cache ``package:`` source; pins the ACP session id and Jobs
``agent_file`` checks that are already on main.
"""

import os
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="symlink fixture needs POSIX")

MARKER = "hidden_marker_q9"


@pytest.fixture
def box(tmp_path, monkeypatch):
    ws, outside, sibling = tmp_path / "ws", tmp_path / "outside", tmp_path / "ws-sib"
    for d in (ws, outside, sibling):
        d.mkdir()
    for d in (outside, sibling):
        (d / f"{MARKER}.py").write_text("x = 1\n")
    (ws / "inside.py").write_text("x = 1\n")
    os.symlink(outside, ws / "link")
    monkeypatch.chdir(ws)
    monkeypatch.delenv("PRAISONAI_JOBS_AGENT_ROOT", raising=False)
    return {"ws": ws, "outside": outside, "dirs": {
        "absolute": str(outside), "dotdot": "../outside", "sibling": str(sibling), "symlink": "link",
    }}


VECTORS = ("absolute", "dotdot", "sibling", "symlink")


@pytest.mark.parametrize("vector", VECTORS)
def test_code_list_files_stays_in_workspace(box, vector):
    from praisonai.code import agent_tools

    agent_tools.set_workspace(str(box["ws"]))
    try:
        assert MARKER not in agent_tools.code_list_files(box["dirs"][vector], recursive=True)
        assert "inside.py" in agent_tools.code_list_files(".")
    finally:
        agent_tools._workspace_root = None


@pytest.mark.parametrize("vector", VECTORS)
def test_list_files_without_workspace_uses_cwd(box, vector):
    from praisonai.code.tools.list_files import list_files

    result = list_files(box["dirs"][vector], recursive=True)
    assert MARKER not in repr(result) and result["success"] is False


@pytest.mark.parametrize("root", ["outside", "sibling", "filesystem"])
def test_multiedit_workspace_root_cannot_widen(box, root):
    from praisonai.tools.multiedit import multiedit

    target = box["outside"] / f"{MARKER}.py"
    wide = {"outside": box["outside"], "sibling": box["ws"].parent / "ws-sib", "filesystem": "/"}[root]
    path = target if root != "sibling" else wide / f"{MARKER}.py"
    result = multiedit(str(path), [{"old": "x = 1", "new": "x = 2"}], workspace_root=str(wide))
    assert result["success"] is False
    assert path.read_text() == "x = 1\n"


def test_multiedit_narrower_root_still_works(box):
    from praisonai.tools.multiedit import multiedit

    (box["ws"] / "sub").mkdir()
    (box["ws"] / "sub" / "a.py").write_text("x = 1\n")
    result = multiedit("a.py", [{"old": "x = 1", "new": "x = 2"}], workspace_root=str(box["ws"] / "sub"))
    assert result["success"] is True and (box["ws"] / "sub" / "a.py").read_text() == "x = 2\n"


@pytest.mark.parametrize("path", ["praisonai/../../../../escape", "../x", "praisonai/..", "a/b/../../.."])
def test_template_cache_package_path_stays_in_cache(tmp_path, path):
    from praisonai.templates.cache import TemplateCache
    from praisonai.templates.resolver import ResolvedTemplate, TemplateSource

    cache = TemplateCache(cache_dir=tmp_path / "cache")
    with pytest.raises(ValueError):
        cache._get_cache_path(ResolvedTemplate(source=TemplateSource.PACKAGE, path=path))
    ok = cache._get_cache_path(ResolvedTemplate(source=TemplateSource.PACKAGE, path="praisonai/tmpl"))
    assert ok == tmp_path / "cache" / "package" / "praisonai" / "tmpl"


@pytest.mark.parametrize("sid", ["../outside_read", "/etc/passwd", "a/../../b"])
def test_acp_session_id_cannot_leave_store(tmp_path, sid):
    from praisonai.acp.session import SessionStore

    with pytest.raises(ValueError):
        SessionStore(storage_dir=tmp_path / "s")._session_path(sid)


def test_jobs_agent_file_defaults_to_cwd(box):
    from praisonai.jobs.path_validation import validate_agent_file_path

    with pytest.raises(ValueError):
        validate_agent_file_path(str(box["outside"] / f"{MARKER}.py"))
    with pytest.raises(ValueError):
        validate_agent_file_path("link/x.yaml")
    assert validate_agent_file_path("inside.py") == "inside.py"


# --- grep / glob tools: the cwd is the default root ------------------------


@pytest.fixture
def tools_box(box, monkeypatch):
    monkeypatch.delenv("PRAISONAI_WORKSPACE", raising=False)
    (box["ws"] / "file_link.py").symlink_to(box["outside"] / f"{MARKER}.py")
    return box


@pytest.mark.parametrize("kind", ["absolute", "dotdot", "sibling", "symlink"])
def test_grep_and_glob_stay_in_the_cwd_by_default(tools_box, kind):
    from praisonai.tools.glob_tool import glob_directories, glob_files
    from praisonai.tools.grep_tool import grep_search

    where = tools_box["dirs"][kind]
    assert MARKER not in str(glob_files("*.py", directory=where))
    assert MARKER not in str(grep_search("x = 1", directory=where))
    assert not glob_directories("*", directory=where).get("directories")


def test_grep_and_glob_skip_matches_that_leave_the_cwd(tools_box):
    from praisonai.tools.glob_tool import glob_files
    from praisonai.tools.grep_tool import grep_search

    assert MARKER not in str(glob_files("*.py"))
    assert MARKER not in str(glob_files("../outside/*.py", recursive=False))
    assert MARKER not in str(grep_search("x = 1"))
    assert "inside.py" in str(glob_files("*.py"))  # control: the cwd itself still works
    assert "inside.py" in str(grep_search("x = 1"))


def test_praisonai_workspace_still_sets_the_root(tools_box, monkeypatch):
    from praisonai.tools.glob_tool import glob_files

    monkeypatch.setenv("PRAISONAI_WORKSPACE", str(tools_box["outside"]))
    assert MARKER in str(glob_files("*.py", directory=str(tools_box["outside"])))
