"""Continued pretraining was impossible, in two separate ways.

**A raw-text corpus could not load.** A dataset with only a `text` column fell
through to the Alpaca branch, where `examples.get("instruction", [])` returns
`[]`, every row formatted to `""`, and the run died with "All examples formatted
to empty text — check dataset schema / chat_template". That message blames the
dataset for a shape the formatter simply did not handle.

**And the embeddings got the wrong learning rate.** `modules_to_save` was
exposed, so a user could make `embed_tokens`/`lm_head` trainable — but the
trainer was plain `SFTTrainer`, which has no `embedding_learning_rate`. The
embeddings therefore trained at the adapters' rate, which is the known-bad
recipe: unsloth ships `UnslothTrainer` specifically to give them a separate,
much lower one (`unsloth/trainer.py:445-524`).
"""

import pytest

from praisonai_train.train.llm import trainer as trainer_mod

fmt = trainer_mod.formatting_prompts_func


# --------------------------------------------------------------------------- #
# A raw-text corpus loads
# --------------------------------------------------------------------------- #
def test_a_text_only_corpus_passes_through_unchanged():
    out = fmt({"text": ["the first paragraph", "the second"]}, tokenizer=None)
    assert out["text"] == ["the first paragraph", "the second"]


def test_raw_text_needs_no_tokenizer():
    # The Alpaca and ShareGPT branches both call apply_chat_template; a raw
    # corpus must not, or CPT would depend on a chat template it has no use for.
    fmt({"text": ["x"]}, tokenizer=None)


def test_a_row_that_is_not_a_string_becomes_empty_rather_than_crashing():
    # The empty-row filter downstream then drops it and says how many went.
    out = fmt({"text": ["ok", None, 42]}, tokenizer=None)
    assert out["text"] == ["ok", "", ""]


def test_sharegpt_still_wins_over_a_text_column():
    # Many ShareGPT dumps also carry a stray `text` column; the conversation is
    # the real content and must not be shadowed.
    class _Tok:
        def apply_chat_template(self, convo, **kw):
            return f"<formatted {len(convo)} turns>"

    out = fmt({"conversations": [[{"role": "user", "content": "hi"}]],
               "text": ["ignore me"]}, tokenizer=_Tok())
    assert out["text"] == ["<formatted 1 turns>"]


def test_alpaca_still_wins_over_a_text_column():
    class _Tok:
        def apply_chat_template(self, convo, **kw):
            return "<alpaca>"

    out = fmt({"instruction": ["do it"], "input": [""], "output": ["done"],
               "text": ["ignore me"]}, tokenizer=_Tok())
    assert out["text"] == ["<alpaca>"]


def test_the_empty_dataset_error_names_the_shapes_it_understands():
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.process_dataset)
    message = src[src.index("All examples formatted to empty text"):]
    for shape in ("conversations", "instruction", "text"):
        assert shape in message, f"the error does not mention {shape}"
    assert "columns_before" in message, "the error does not say what the dataset has"


# --------------------------------------------------------------------------- #
# The embeddings get their own learning rate
# --------------------------------------------------------------------------- #
def test_cpt_is_a_method():
    assert "cpt" in trainer_mod.TRAINING_METHODS
    assert trainer_mod.TrainModel.resolve_method({"method": "cpt"}) == "cpt"


def test_cpt_uses_the_trainer_that_has_an_embedding_lr():
    # SFTTrainer has no embedding_learning_rate; UnslothTrainer exists for it.
    spec = trainer_mod.TRAINING_METHODS["cpt"]
    assert spec["trainer"] == "UnslothTrainer"
    assert spec["config"] == "UnslothTrainingArguments"


def test_cpt_requires_a_text_column():
    assert trainer_mod.TRAINING_METHODS["cpt"]["columns"] == ("text",)
    with pytest.raises(ValueError) as e:
        trainer_mod.TrainModel._require_columns(
            type("D", (), {"column_names": ["instruction", "output"]})(),
            trainer_mod.TRAINING_METHODS["cpt"]["columns"], "cpt")
    assert "text" in str(e.value)


def test_the_embedding_rate_defaults_below_the_adapter_rate():
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.train_model)
    block = src[src.index('if method == "cpt":'):]
    assert "embedding_learning_rate" in block
    assert "lr / 10" in block, (
        "the embedding LR does not default below the adapter LR, which is the "
        "recipe unsloth's UnslothTrainer exists to avoid")


def test_cpt_keeps_its_text_column_through_process_dataset():
    # CPT is formatted like SFT (raw text in, text out), so unlike the
    # preference methods it must NOT take the passthrough branch.
    import inspect

    src = inspect.getsource(trainer_mod.TrainModel.process_dataset)
    guard = src[src.index('self.config.get("method", "sft") not in'):]
    assert '("sft", "cpt")' in guard[:80], (
        "cpt takes the preference passthrough and is never formatted")
