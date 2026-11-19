"""The dashboard's mark is the eagle; the lobster from the claw era is gone."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_wrapper_and_docker_use_the_eagle_mark():
    files = [*(ROOT / "src/praisonai/praisonai").rglob("*.py"), *(ROOT / "docker").iterdir()]
    hits = [str(f.relative_to(ROOT)) for f in files
            if f.is_file() and "\U0001F99E" in f.read_text(encoding="utf-8", errors="ignore")]
    assert hits == []
