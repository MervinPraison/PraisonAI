"""An OpenAI-style `messages` chat dataset formatted to empty text.

`praisonai-train validate` and `praisonaiagents.eval.export_sft` both use the
`{"messages": [...]}` shape, but `process_dataset` only recognised
`conversations`, so every row fell into the Alpaca branch, formatted to "",
and the run died after the base model had already been loaded.
"""

from praisonai_train.train.llm import trainer as trainer_mod


class _FakeDataset:
    def __init__(self, rows):
        self.rows = rows

    @property
    def column_names(self):
        return list(self.rows[0].keys()) if self.rows else []

    def __len__(self):
        return len(self.rows)

    def rename_column(self, src, dst):
        return _FakeDataset([{(dst if k == src else k): v for k, v in r.items()}
                             for r in self.rows])

    def map(self, func, batched, remove_columns):
        batch = {c: [r[c] for r in self.rows] for c in self.column_names}
        out = func(batch)
        return _FakeDataset([{"text": t} for t in out["text"]])

    def filter(self, pred):
        return _FakeDataset([r for r in self.rows if pred(r)])


class _Tokenizer:
    def apply_chat_template(self, convo, tokenize, add_generation_prompt):
        return "".join(f"<{m['role']}>{m['content']}" for m in convo)


def test_messages_column_is_treated_as_conversations(monkeypatch):
    rows = [{"messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": f"q{i}"},
        {"role": "assistant", "content": f"a{i}"},
    ]} for i in range(3)]
    monkeypatch.setattr(trainer_mod, "load_dataset",
                        lambda *a, **k: _FakeDataset(rows), raising=False)
    monkeypatch.setattr(trainer_mod, "standardize_sharegpt", lambda d: d,
                        raising=False)

    tm = trainer_mod.TrainModel.__new__(trainer_mod.TrainModel)
    tm.config = {"method": "sft"}
    tm.chat_tokenizer = _Tokenizer()

    out = tm.process_dataset({"name": "hub/some-dataset"})
    assert len(out) == 3
    assert out.rows[0]["text"] == "<system>s<user>q0<assistant>a0"
