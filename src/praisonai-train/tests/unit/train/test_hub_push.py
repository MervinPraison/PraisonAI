"""Every model this tool uploaded became a public repository.

`private` was never passed to `push_to_hub_merged` / `push_to_hub_gguf` in any
of the three places that push — `train/llm/trainer.py`, `train_vision.py` and
`upload_vision.py`. Unsloth accepts the flag (`save.py:2654`,
`create_huggingface_repo(private=...)`); nothing here forwarded it. A model
fine-tuned on private data was published on completion, silently.

Two more defects came from the same duplication: only the LLM copy translated a
rejected token into an actionable message, and only the LLM copy checked that
the directory it was about to delete was a local path rather than a Hub repo id.
"""

import os

import pytest

from praisonai_train import _hub


# --------------------------------------------------------------------------- #
# private by default
# --------------------------------------------------------------------------- #
def test_a_push_is_private_unless_asked_otherwise():
    # The default matters more than the flag: publishing is one click in the Hub
    # UI, unpublishing something already crawled is not.
    assert _hub.hub_push_kwargs({})["private"] is True


def test_publishing_is_possible_but_deliberate():
    assert _hub.hub_push_kwargs({"hf_private": False})["private"] is False


def test_a_yaml_string_false_still_publishes():
    # YAML gives "false" as a string through some paths; without the trainer's
    # coercion that is truthy and would silently keep the repo private.
    flag = lambda v, default=False: (
        default if v is None else str(v).strip().lower() not in {"false", "no", "0", ""})
    assert _hub.hub_push_kwargs({"hf_private": "false"}, flag=flag)["private"] is False
    assert _hub.hub_push_kwargs({"hf_private": "true"}, flag=flag)["private"] is True


def test_the_token_still_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_abc")
    assert _hub.hub_push_kwargs({})["token"] == "hf_abc"


def test_optional_metadata_is_only_sent_when_set():
    bare = _hub.hub_push_kwargs({})
    assert "commit_message" not in bare and "tags" not in bare
    rich = _hub.hub_push_kwargs({"commit_message": "v2", "tags": ["praisonai"]})
    assert rich["commit_message"] == "v2"
    assert rich["tags"] == ["praisonai"]


# --------------------------------------------------------------------------- #
# every push site actually uses it
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("module", [
    "praisonai_train.train.llm.trainer",
    "praisonai_train.train_vision",
    "praisonai_train.upload_vision",
])
def test_no_push_site_hardcodes_a_bare_token(module):
    # The defect's signature: `token=os.getenv("HF_TOKEN")` as the *only* kwarg,
    # which is what made every repo public.
    import importlib
    import inspect
    src = inspect.getsource(importlib.import_module(module))
    for line in src.splitlines():
        if "push_to_hub" in line:
            continue
    assert 'token=os.getenv("HF_TOKEN")\n        )' not in src, (
        f"{module} still pushes with a bare token and no privacy flag")
    assert "hub_push_kwargs" in src, f"{module} does not use the shared push options"


# --------------------------------------------------------------------------- #
# the rmtree guard, which only one copy had
# --------------------------------------------------------------------------- #
def test_a_hub_repo_id_is_never_treated_as_a_path(tmp_path, monkeypatch):
    # upload_vision deleted config["hf_model_name"] if a directory of that name
    # existed, with no check that the value was a local path.
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "me" / "model"
    victim.mkdir(parents=True)
    (victim / "important.bin").write_text("x")
    _hub.clean_local_repo_dir("me/model")
    assert victim.exists(), "a namespaced Hub repo id was deleted as a path"


def test_a_plain_local_directory_is_still_cleaned(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stale = tmp_path / "outdir"
    stale.mkdir()
    (stale / "old.bin").write_text("x")
    _hub.clean_local_repo_dir("outdir")
    assert not stale.exists(), "the stale output directory was not cleaned"


def test_cleaning_something_that_is_not_there_is_harmless():
    _hub.clean_local_repo_dir("definitely-not-a-directory-anywhere")
    _hub.clean_local_repo_dir("")
    _hub.clean_local_repo_dir(None)


# --------------------------------------------------------------------------- #
# error translation, which only one copy had
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, code):
        self.status_code = code


class _Err(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.response = _Resp(code)


def test_a_rejected_token_says_what_to_do():
    with pytest.raises(RuntimeError) as e:
        _hub.raise_hf_push_error(_Err(401), "me/model")
    msg = str(e.value)
    assert "huggingface-cli login" in msg or "HF_TOKEN" in msg
    assert "me/model" in msg


def test_a_forbidden_repo_is_distinguished_from_a_bad_token():
    # 401 and 403 need opposite responses: get a token, versus you have one but
    # it cannot write here.
    with pytest.raises(RuntimeError) as e:
        _hub.raise_hf_push_error(_Err(403), "someoneelse/model")
    assert "write" in str(e.value)
    assert "login" not in str(e.value)


def test_an_unclassified_failure_still_names_the_repo():
    with pytest.raises(RuntimeError) as e:
        _hub.raise_hf_push_error(_Err(500), "me/model")
    assert "me/model" in str(e.value)
