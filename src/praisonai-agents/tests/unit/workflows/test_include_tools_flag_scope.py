"""PRAISONAI_ALLOW_LOCAL_TOOLS covers the working directory only.

An included recipe's ``tools.py`` outside the working directory (a registry
recipe or any other path) needs PRAISONAI_ALLOW_TEMPLATE_TOOLS, the flag for
recipe and template code. The local-tools flag no longer opens it.
"""

def _include_recipe(tmp_path, monkeypatch, recipe_dir, **env):
    for name in ("PRAISONAI_ALLOW_LOCAL_TOOLS", "PRAISONAI_ALLOW_TEMPLATE_TOOLS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    recipe_dir.mkdir(parents=True)
    marker = tmp_path / f"ran-{recipe_dir.name}"
    (recipe_dir / "tools.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    (recipe_dir / "workflow.yaml").write_text("name: child\nsteps: []\n")
    from praisonaiagents.workflows.workflows import Workflow, include
    Workflow(steps=[include(str(recipe_dir))]).run(input="", llm="dummy/local", stream=False)
    return marker.exists()


def test_local_tools_flag_does_not_cover_recipe_outside_cwd(tmp_path, monkeypatch):
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    flag = {"PRAISONAI_ALLOW_LOCAL_TOOLS": "true"}
    assert _include_recipe(tmp_path, monkeypatch, tmp_path / "outside", **flag) is False
    assert _include_recipe(tmp_path, monkeypatch, tmp_path / "work" / "inside", **flag) is True
    assert _include_recipe(tmp_path, monkeypatch, tmp_path / "other",
                           PRAISONAI_ALLOW_TEMPLATE_TOOLS="true") is True
