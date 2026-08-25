"""Options every Hugging Face push shares, in one place.

Three copies of "push this model to the Hub" existed — `train/llm/trainer.py`,
`train_vision.py` and `upload_vision.py` — and they had drifted:

* **None of them passed `private`.** Every model this tool uploaded became a
  PUBLIC repository, including one fine-tuned on private data. Unsloth accepts
  the flag (`save.py:2654`, `create_huggingface_repo(private=...)`); nothing here
  forwarded it.
* **Only the LLM copy translated a rejected token.** The vision copies had no
  error handling at all, so a 401 surfaced as a raw `HfHubHTTPError` traceback.
* **Only the LLM copy guarded its `rmtree`.** `upload_vision.py` deleted
  `config["hf_model_name"]` if a directory of that name existed, with no check
  that the value is a local path rather than a Hub repo id.

Default is private. Publishing is one click in the Hub UI; unpublishing
something already crawled is not.
"""

import os
import shutil


def hub_push_kwargs(config, flag=None):
    """Keyword arguments common to `push_to_hub_merged` / `push_to_hub_gguf`.

    `flag` coerces a config value to bool; callers that have their own coercion
    pass it so YAML's `"false"` behaves the same everywhere.
    """
    truthy = flag or (lambda v, default=False: default if v is None else bool(v))
    kwargs = {"token": os.getenv("HF_TOKEN")}
    kwargs["private"] = truthy(config.get("hf_private"), default=True)
    for key in ("commit_message", "tags"):
        if config.get(key) is not None:
            kwargs[key] = config[key]
    return kwargs


def clean_local_repo_dir(name):
    """Remove a stale LOCAL output directory before an export.

    Only when `name` is a plain directory name — never a namespaced Hub repo id
    like `user/model`, which must not be read as a path to delete.
    """
    if name and "/" not in str(name).strip("/") and os.path.isdir(name):
        shutil.rmtree(name)


def raise_hf_push_error(exc, repo):
    """Translate a Hub HTTP error into something a user can act on."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 401:
        raise RuntimeError(
            f"Hugging Face rejected the credentials for '{repo}' (401). Run "
            "`huggingface-cli login`, or set HF_TOKEN to a token with write access."
        ) from exc
    if status == 403:
        raise RuntimeError(
            f"Hugging Face refused write access to '{repo}' (403). The repo must be "
            "under your own username or an org you can write to, and the token needs "
            "the write scope."
        ) from exc
    raise RuntimeError(f"Hugging Face upload to '{repo}' failed: {exc}") from exc
