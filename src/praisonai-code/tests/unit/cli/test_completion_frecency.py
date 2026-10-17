"""Frecency (usage-history) ranking for interactive ``@`` / ``/`` completion."""

from praisonai_code.cli.features.at_mentions import FileSearchService
from praisonai_code.cli.utils.frecency import MAX_BOOST, FrecencyStore


def _project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    for name in ("account_service.py", "accounts.py", "app.py"):
        (root / name).write_text("")
    return root


def test_empty_store_keeps_pure_fuzzy_order(tmp_path):
    root = _project(tmp_path)
    store = FrecencyStore(tmp_path / "frecency.json")
    svc = FileSearchService(str(root), frecency=store)
    assert [s.path for s in svc.search("acc")] == ["account_service.py", "accounts.py"]
    assert not (tmp_path / "frecency.json").exists()


def test_selection_promotes_file_and_persists(tmp_path):
    root = _project(tmp_path)
    path = tmp_path / "frecency.json"
    svc = FileSearchService(str(root), frecency=FrecencyStore(path))
    svc.search("")  # warm the result cache; recording must invalidate it
    for _ in range(3):
        svc.record_selection("app.py")
    assert svc.search("")[0].path == "app.py"
    assert all(s.score <= 100 for s in svc.search(""))

    # Survives a restart (fresh store reading the same file).
    fresh = FileSearchService(str(root), frecency=FrecencyStore(path))
    assert fresh.search("")[0].path == "app.py"


def test_boost_is_bounded_and_decays(tmp_path):
    store = FrecencyStore(tmp_path / "f.json")
    for _ in range(3):
        store.record("commands", "help", now=0)
    recent = store.boost("commands", "help", now=60)
    assert 0 < store.boost("commands", "help", now=60 * 86400) < recent
    for _ in range(100):
        store.record("commands", "help", now=0)
    assert store.boost("commands", "help", now=60) == MAX_BOOST
    assert store.boost("commands", "unseen", now=60) == 0


def test_much_better_fuzzy_match_still_wins(tmp_path):
    root = _project(tmp_path)
    (root / "a_x_c_c.py").write_text("")
    store = FrecencyStore(tmp_path / "f.json")
    for _ in range(50):
        store.record("files", "a_x_c_c.py")
    svc = FileSearchService(str(root), frecency=store)
    # A heavily used weak subsequence match (~59 + 20) stays below unused
    # "starts with" matches (90): history reorders, it doesn't override.
    assert [s.path for s in svc.search("acc")][-1] == "a_x_c_c.py"


def test_corrupt_store_is_ignored(tmp_path):
    path = tmp_path / "f.json"
    path.write_text("{not json")
    store = FrecencyStore(path)
    assert store.boost("files", "x") == 0
    store.record("files", "x")
    assert store.boost("files", "x") > 0
