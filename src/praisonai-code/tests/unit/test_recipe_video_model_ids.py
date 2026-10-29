"""Recipe prompt text must not recommend deprecated video model IDs (#5180)."""

from pathlib import Path

import pytest

FEATURES = Path(__file__).resolve().parents[2] / "praisonai_code" / "cli" / "features"
DEPRECATED = ("veo-3.0-generate-preview", "runway/gen-3")


@pytest.mark.parametrize("name", ["recipe_creator.py", "recipe_prompts.py"])
def test_recipe_prompts_use_current_video_ids(name):
    text = (FEATURES / name).read_text(encoding="utf-8")
    for stale in DEPRECATED:
        assert stale not in text
    assert "gemini/veo-3.1-generate-preview" in text
