"""Regression test for issue #4314: ``train`` must reach the trainer, not chat.

The legacy dispatcher's ``if args.command:`` chain had no ``train`` case, so
``args.command == 'train'`` fell through to the bare-prompt handler and the
literal word "train" was forwarded to an LLM as a chat prompt — the real
training block was never reached and no trainer subprocess was launched.

This drives the *real* router (unlike the wholesale-``PraisonAI`` stub in
``praisonai-train``) and asserts the dataset config is generated and the trainer
invocation is dispatched, with ``handle_direct_prompt`` never called.
"""

import pytest


def _load_module():
    try:
        import praisonai_code.cli.legacy.praison_ai as pa
    except ImportError as exc:  # pragma: no cover - depends on optional wrapper
        pytest.skip(f"legacy dispatcher unavailable: {exc}")
    return pa


def test_train_command_reaches_trainer_not_direct_prompt(monkeypatch, tmp_path):
    pa = _load_module()

    # parse_args() needs the wrapper's argparse builder; skip if absent.
    try:
        from praisonai_code._wrapper_bridge import import_wrapper_module
        import_wrapper_module("praisonai.cli.legacy.dispatch.argparse_builder")
    except ImportError as exc:  # pragma: no cover - depends on optional wrapper
        pytest.skip(f"wrapper argparse builder unavailable: {exc}")

    calls = {"hdp": [], "train_argv": None, "config": None}

    def fake_hdp(self, *a, **k):
        calls["hdp"].append(a)
        return "PROMPTED"

    def fake_stream(cmd, env=None):
        calls["train_argv"] = list(cmd)

    def fake_gen_config(**kw):
        calls["config"] = kw
        return {"model_name": kw.get("model_name") or ""}

    monkeypatch.setattr(pa, "TRAIN_AVAILABLE", True)
    monkeypatch.setattr(pa.PraisonAI, "handle_direct_prompt", fake_hdp)
    monkeypatch.setattr(pa, "stream_subprocess", fake_stream)
    monkeypatch.setattr(pa, "_get_generate_config", lambda: fake_gen_config)
    # No conda: force the direct-python execution branch deterministically.
    import subprocess as _sp
    monkeypatch.setattr(_sp, "check_output", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))

    dataset = tmp_path / "my_sft.jsonl"
    dataset.write_text('{"instruction": "x"}\n')
    monkeypatch.chdir(tmp_path)

    # parse_args() short-circuits to empty argv under a detected test env
    # (argparse_builder parses ``[]`` when in_test_env). Present a genuine
    # ``praisonai train ...`` argv so the real router parses ``command='train'``.
    import sys as _sys
    monkeypatch.setattr(
        _sys, "argv",
        ["praisonai", "train", "--dataset", str(dataset), "--model", "llama-3.1"],
    )
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    pa.PraisonAI().main()

    # The literal word "train" was never sent to an LLM as a chat prompt.
    assert calls["hdp"] == []
    # The user's dataset drove config generation (not yahma/alpaca-cleaned).
    assert calls["config"] is not None
    assert calls["config"]["dataset"] == [{"name": str(dataset)}]
    assert calls["config"]["model_name"] == "llama-3.1"
    # The trainer subprocess was actually dispatched.
    assert calls["train_argv"] is not None
    assert "praisonai_train.train.llm.trainer" in calls["train_argv"]
    assert "train" in calls["train_argv"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
