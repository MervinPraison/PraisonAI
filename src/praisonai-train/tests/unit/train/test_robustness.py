"""Robustness tests for the LLM trainer — clean errors, preflight validation, and
export robustness. All heavy deps (torch CUDA, HF push, ollama subprocess) are
stubbed so these run with no GPU and no network.
"""
import sys
import types

import pytest

import praisonai_train.train.llm.trainer as trainer_mod
import praisonai_train.train._ollama as ollama_mod


# --------------------------------------------------------------------------- #
# Helpers / fakes
# --------------------------------------------------------------------------- #
class _FakeCuda:
    def __init__(self, available):
        self._available = available

    def is_available(self):
        return self._available


class _FakeTorch:
    def __init__(self, available):
        self.cuda = _FakeCuda(available)


class _FreeDisk:
    def __init__(self, free_gb):
        self.free = int(free_gb * 2 ** 30)


def _make_trainer(config, monkeypatch, gpu=True, free_gb=500):
    """Build a bare TrainModel with a controllable GPU/disk environment."""
    monkeypatch.setattr(trainer_mod, "torch", _FakeTorch(gpu), raising=False)
    monkeypatch.setattr(trainer_mod.shutil, "disk_usage", lambda *_a, **_k: _FreeDisk(free_gb))
    obj = trainer_mod.TrainModel.__new__(trainer_mod.TrainModel)
    obj.config = config
    return obj


def _valid_config(**extra):
    cfg = {
        "model_name": "unsloth/gemma-2-2b-it-bnb-4bit",
        "max_seq_length": 2048,
        "dataset": [{"name": "yahma/alpaca-cleaned"}],
    }
    cfg.update(extra)
    return cfg


# --------------------------------------------------------------------------- #
# 1. main() clean-error wrapper
# --------------------------------------------------------------------------- #
def test_main_wrapper_prints_clean_error_no_traceback(monkeypatch, capsys):
    class _Boom:
        def __init__(self, config_path=None):
            pass

        def run(self):
            raise ValueError("something friendly went wrong")

    monkeypatch.setattr(trainer_mod, "TrainModel", _Boom)
    monkeypatch.setattr(sys, "argv", ["praisonai-train", "train", "--config", "x.yaml"])

    with pytest.raises(SystemExit) as exc:
        trainer_mod.main()
    assert exc.value.code == 1

    captured = capsys.readouterr()
    assert "ERROR: something friendly went wrong" in captured.err
    assert "Traceback" not in captured.err
    assert "ValueError" not in captured.err


def test_main_wrapper_keyboardinterrupt_clean(monkeypatch, capsys):
    class _Interrupt:
        def __init__(self, config_path=None):
            pass

        def run(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(trainer_mod, "TrainModel", _Interrupt)
    monkeypatch.setattr(sys, "argv", ["praisonai-train", "train"])

    with pytest.raises(SystemExit) as exc:
        trainer_mod.main()
    assert exc.value.code == 130
    assert "Interrupted." in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# 2. Preflight validations
# --------------------------------------------------------------------------- #
def test_no_gpu_raises_friendly(monkeypatch):
    obj = _make_trainer(_valid_config(), monkeypatch, gpu=False)
    with pytest.raises(ValueError, match="No CUDA GPU detected"):
        obj.validate_config()


def test_missing_hf_token_raises_friendly(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    obj = _make_trainer(
        _valid_config(huggingface_save=True, hf_model_name="me/model"),
        monkeypatch,
    )
    with pytest.raises(ValueError, match="HF_TOKEN is not set"):
        obj.validate_config()


def test_bad_quantization_raises_friendly(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    obj = _make_trainer(
        _valid_config(
            huggingface_save_gguf=True, hf_model_name="me/model",
            quantization_method="q4km",
        ),
        monkeypatch,
    )
    with pytest.raises(ValueError, match="quantization_method 'q4km' is not valid"):
        obj.validate_config()


def test_valid_quantization_passes(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_fake")
    obj = _make_trainer(
        _valid_config(
            huggingface_save_gguf=True, hf_model_name="me/model",
            quantization_method="q4_k_m",
        ),
        monkeypatch,
    )
    obj.validate_config()  # must not raise


def test_low_disk_raises_friendly(monkeypatch):
    obj = _make_trainer(_valid_config(), monkeypatch, free_gb=3)
    with pytest.raises(ValueError, match="free space or set output_dir"):
        obj.validate_config()


def test_check_gpu_no_crash_on_cpu(monkeypatch, capsys):
    monkeypatch.setattr(trainer_mod, "torch", _FakeTorch(False), raising=False)
    obj = trainer_mod.TrainModel.__new__(trainer_mod.TrainModel)
    obj.check_gpu()  # must not raise on CPU-only
    assert "No CUDA GPU" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 3. Unknown-key warning with suggestion
# --------------------------------------------------------------------------- #
def test_unknown_key_suggestion(monkeypatch, capsys):
    obj = _make_trainer(_valid_config(learnign_rate=1e-4), monkeypatch)
    obj.validate_config()  # warns, does not raise
    out = capsys.readouterr().out
    assert "learnign_rate" in out
    assert "did you mean 'learning_rate'" in out


# --------------------------------------------------------------------------- #
# 5. Ollama export robustness
# --------------------------------------------------------------------------- #
def test_ollama_push_401_translates(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ollama_mod, "_check_ollama_disk", lambda *_a, **_k: None)
    monkeypatch.setattr(ollama_mod, "ensure_ollama_running", lambda *_a, **_k: None)

    def _fake_run(cmd, *a, **k):
        if "create" in cmd:
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        return types.SimpleNamespace(
            returncode=1, stdout="", stderr="Error: 401 unauthorized: invalid key")

    monkeypatch.setattr(ollama_mod.subprocess, "run", _fake_run)

    with pytest.raises(RuntimeError, match="settings/keys"):
        ollama_mod.create_and_push_ollama_model("me/model", "latest", "FROM ./model\n")


def test_ollama_push_passes_quantize_flag(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ollama_mod, "_check_ollama_disk", lambda *_a, **_k: None)
    monkeypatch.setattr(ollama_mod, "ensure_ollama_running", lambda *_a, **_k: None)
    seen = {}

    def _fake_run(cmd, *a, **k):
        if "create" in cmd:
            seen["create"] = cmd
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ollama_mod.subprocess, "run", _fake_run)
    ollama_mod.create_and_push_ollama_model(
        "me/model", "latest", "FROM ./model\n", quantization="q4_k_m")
    assert "--quantize" in seen["create"]
    assert "q4_k_m" in seen["create"]


def test_ollama_disk_precheck_triggers(monkeypatch, tmp_path):
    # A LOCAL FROM path gives a known source size, so the 1.5x requirement is
    # enforced and a nearly-full volume is rejected.
    src = tmp_path / "model.gguf"
    src.write_bytes(b"x")  # existence is enough; size is stubbed below
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    monkeypatch.setattr(ollama_mod, "_dir_size_bytes", lambda _p: 4 * 2 ** 30)
    monkeypatch.setattr(ollama_mod.shutil, "disk_usage", lambda *_a, **_k: _FreeDisk(1))
    with pytest.raises(RuntimeError, match="OLLAMA_MODELS"):
        ollama_mod._check_ollama_disk(f"FROM {src}\n")


def test_ollama_disk_precheck_skips_unknown_source(monkeypatch, tmp_path):
    # A Hub-id FROM has unknown source size; we can't estimate the requirement so
    # the check is skipped rather than blocking a viable small-model export.
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    monkeypatch.setattr(ollama_mod.shutil, "disk_usage", lambda *_a, **_k: _FreeDisk(1))
    ollama_mod._check_ollama_disk("FROM some-hub-id\n")  # must not raise


# --------------------------------------------------------------------------- #
# 8. Standalone export command dispatch
# --------------------------------------------------------------------------- #
def test_export_command_dispatches_hf(monkeypatch, tmp_path):
    import praisonai_train.cli.commands.train as cli

    called = {}

    class _FakeTrainer:
        @classmethod
        def for_export(cls, cfg):
            obj = cls()
            obj.config = cfg
            obj.model = None
            obj.hf_tokenizer = None
            return obj

        def load_model(self):
            return ("MODEL", "TOK")

        def save_model_merged(self):
            called["target"] = "hf"

        def save_model_gguf(self):
            called.setdefault("calls", []).append("save_gguf")
            called["target"] = "gguf"

        def push_model_gguf(self):
            called.setdefault("calls", []).append("push_gguf")

        def create_and_push_ollama_model(self):
            called["target"] = "ollama"

    monkeypatch.setattr(trainer_mod, "TrainModel", _FakeTrainer)

    cli.train_export(
        target="hf",
        model_dir=str(tmp_path),
        config=None,
        ollama=None,
        hf="me/model",
        quant=None,
        base_model="unsloth/gemma-2-2b",
    )
    assert called["target"] == "hf"


def test_export_gguf_saves_local_without_hf(monkeypatch, tmp_path):
    """`export gguf` without --hf must produce a LOCAL gguf (no Hub push)."""
    import praisonai_train.cli.commands.train as cli

    called = {}

    class _FakeTrainer:
        @classmethod
        def for_export(cls, cfg):
            obj = cls()
            obj.config = cfg
            obj.model = None
            obj.hf_tokenizer = None
            return obj

        def load_model(self):
            return ("MODEL", "TOK")

        def save_model_gguf(self):
            called.setdefault("calls", []).append("save_gguf")

        def push_model_gguf(self):
            called.setdefault("calls", []).append("push_gguf")

    monkeypatch.setattr(trainer_mod, "TrainModel", _FakeTrainer)

    cli.train_export(
        target="gguf",
        model_dir=str(tmp_path),
        config=None,
        ollama=None,
        hf=None,
        quant="q4_k_m",
        base_model="unsloth/gemma-2-2b",
    )
    # Saved locally, and did NOT push to the Hub.
    assert called.get("calls") == ["save_gguf"]


def test_export_gguf_saves_local_and_pushes_with_hf(monkeypatch, tmp_path):
    """`export gguf --hf` must save locally AND push to the Hub."""
    import praisonai_train.cli.commands.train as cli

    called = {}

    class _FakeTrainer:
        @classmethod
        def for_export(cls, cfg):
            obj = cls()
            obj.config = cfg
            obj.model = None
            obj.hf_tokenizer = None
            return obj

        def load_model(self):
            return ("MODEL", "TOK")

        def save_model_gguf(self):
            called.setdefault("calls", []).append("save_gguf")

        def push_model_gguf(self):
            called.setdefault("calls", []).append("push_gguf")

    monkeypatch.setattr(trainer_mod, "TrainModel", _FakeTrainer)

    cli.train_export(
        target="gguf",
        model_dir=str(tmp_path),
        config=None,
        ollama=None,
        hf="me/model",
        quant="q4_k_m",
        base_model="unsloth/gemma-2-2b",
    )
    assert called.get("calls") == ["save_gguf", "push_gguf"]


def test_export_command_bad_target_exits(monkeypatch, tmp_path):
    import typer
    import praisonai_train.cli.commands.train as cli

    with pytest.raises(typer.Exit):
        cli.train_export(
            target="bogus",
            model_dir=str(tmp_path),
            config=None,
            ollama=None,
            hf=None,
            quant=None,
            base_model=None,
        )
