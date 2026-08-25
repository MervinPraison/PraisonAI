"""`model_name` was a free-text string with no validation anywhere.

A typo was caught by Hugging Face — after the CLI accepted it, after the
environment was built, sometimes after a partial download. And nothing told a
new user which models work: `config.yaml` offers exactly one example, from the
Llama-3.1 era.

Unsloth already maintains the list (`unsloth/models/mapper.py`, 246 distinct
4-bit repos, updated every release), so this reads it at runtime rather than
vendoring a copy that would be stale the day it was written.
"""

import pytest
from typer.testing import CliRunner

from praisonai_train import models as cat
from praisonai_train.cli import app as app_mod

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clear_cache():
    cat.known_models.cache_clear()
    yield
    cat.known_models.cache_clear()


# --------------------------------------------------------------------------- #
# The catalog
# --------------------------------------------------------------------------- #
def test_the_catalog_is_never_empty():
    # Even with unsloth absent there must be something to suggest, or the
    # error message degrades to "that's wrong" with no way forward.
    assert len(cat.known_models()) > 0


def test_it_reads_unsloths_mapper_when_available(monkeypatch):
    """The whole design: not a vendored copy.

    A hand-written catalog is stale the day it ships. unsloth updates its
    mapper every release, and it is already a dependency.
    """
    import sys
    import types

    fake = types.ModuleType("unsloth.models.mapper")
    # The 16-bit mirror appears ONLY as a value, so a catalog built from keys
    # alone would miss it -- and a user who names the 16-bit repo would be
    # warned their perfectly valid model is unknown.
    fake.INT_TO_FLOAT_MAPPER = {"unsloth/fake-4bit": "unsloth/fake-16bit-mirror"}
    fake.FLOAT_TO_INT_MAPPER = {"unsloth/fake": "unsloth/fake-4bit"}
    monkeypatch.setitem(sys.modules, "unsloth.models.mapper", fake)
    cat.known_models.cache_clear()
    assert "unsloth/fake-4bit" in cat.known_models()
    assert "unsloth/fake" in cat.known_models()
    assert "unsloth/fake-16bit-mirror" in cat.known_models(), (
        "a model that appears only as a mapper value is reported as unknown")


def test_a_missing_unsloth_falls_back_rather_than_raising(monkeypatch):
    # The CLI is importable without the training extra; `models` and config
    # validation must still work there.
    import builtins

    real = builtins.__import__

    def _no_unsloth(name, *a, **k):
        if name.startswith("unsloth"):
            raise ImportError("no unsloth here")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_unsloth)
    cat.known_models.cache_clear()
    assert cat.known_models() == tuple(cat.CURATED)


def test_the_curated_set_is_a_real_starting_point():
    # One current model per major family, so "I have not chosen yet" has an
    # answer that is not just the first alphabetically.
    families = {"llama", "qwen", "gemma", "mistral", "phi"}
    joined = " ".join(cat.CURATED).lower()
    for family in families:
        assert family in joined, f"nothing curated for {family}"


# --------------------------------------------------------------------------- #
# Suggestions
# --------------------------------------------------------------------------- #
def test_a_typo_suggests_the_model_meant():
    hits = cat.suggest("unsloth/Meta-Llama-3.1-8B-Instrct-bnb-4bit")
    assert "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit" in hits


def test_the_right_model_under_the_wrong_org_is_found(monkeypatch):
    """Matched on the repo name, not the full id.

    The org prefix has to be discarded before comparing, or a long enough one
    drowns the part that identifies the model. `meta-llama/...` is short enough
    that difflib finds it either way, so this uses an org long enough that
    full-id matching demonstrably fails.
    """
    import sys
    import types

    fake = types.ModuleType("unsloth.models.mapper")
    fake.INT_TO_FLOAT_MAPPER = {"unsloth/gemma-2-9b-it-bnb-4bit": "unsloth/gemma-2-9b-it"}
    fake.FLOAT_TO_INT_MAPPER = {}
    monkeypatch.setitem(sys.modules, "unsloth.models.mapper", fake)
    cat.known_models.cache_clear()

    wrong_org = "some-very-long-organisation-name-here/gemma-2-9b-it-bnb-4bit"
    hits = cat.suggest(wrong_org)
    # The 16-bit mirror is in the catalog too and is a near match, so assert on
    # the ordering: the exact repo name has to lead.
    assert hits and hits[0] == "unsloth/gemma-2-9b-it-bnb-4bit", hits


def test_something_unrelated_suggests_nothing_rather_than_anything():
    # A confident wrong suggestion is worse than none.
    assert cat.suggest("completely-unrelated/xyzzy-9000") == []


def test_an_empty_name_is_handled():
    assert cat.suggest("") == []
    assert cat.is_known("") is False


# --------------------------------------------------------------------------- #
# The message
# --------------------------------------------------------------------------- #
def test_an_unknown_model_warns_without_refusing():
    # unsloth loads plenty of models it does not map, so refusing would block
    # working configurations.
    msg = cat.describe_unknown("some-org/brand-new-model")
    assert "may not load" in msg
    assert "praisonai-train models" in msg, "no way to find the right name"


def test_a_near_miss_leads_with_the_correction():
    msg = cat.describe_unknown("unsloth/Meta-Llama-3.1-8B-Instrct-bnb-4bit")
    assert "Did you mean" in msg
    assert "Instruct" in msg


def test_a_wild_miss_offers_a_starting_point_instead():
    msg = cat.describe_unknown("completely-unrelated/xyzzy-9000")
    assert "Did you mean" not in msg
    assert "starting points" in msg


def test_validation_warns_but_does_not_raise():
    import inspect

    from praisonai_train.train.llm.trainer import TrainModel

    src = inspect.getsource(TrainModel.validate_config)
    block = src[src.index("describe_unknown") - 200:src.index("required = [")]
    assert "print(" in block, "the unknown-model path does not warn"
    assert "raise" not in block, "an unmapped model is refused, blocking valid configs"


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #
def test_models_is_registered():
    names = {c.name or c.callback.__name__ for c in app_mod.app.registered_commands}
    assert "models" in names


def test_models_filters(monkeypatch):
    result = runner.invoke(app_mod.app, ["models", "gemma"])
    assert result.exit_code == 0
    assert "gemma" in result.output.lower()
    assert "qwen" not in result.output.lower(), "the filter did not filter"


def test_a_filter_matching_nothing_exits_non_zero():
    result = runner.invoke(app_mod.app, ["models", "definitely-not-a-family"])
    assert result.exit_code == 1
    assert "Try a family name" in result.output


def test_json_output_is_a_list():
    import json

    result = runner.invoke(app_mod.app, ["models", "--json"])
    assert isinstance(json.loads(result.output), list)
