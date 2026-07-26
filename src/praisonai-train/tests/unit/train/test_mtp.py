"""Unit tests for MTP (Multi-Token Prediction) fast-inference support.

All heavy deps (huggingface_hub download, llama.cpp subprocess, network, GPU) are
stubbed via monkeypatch — these run offline with no GPU, mirroring the style of
``test_robustness.py``.
"""
import sys
import types

import pytest

import praisonai_train.train._mtp as mtp
import praisonai_train.train._llamacpp as llamacpp


# --------------------------------------------------------------------------- #
# resolve_drafter / is_mtp_supported
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", [
    "gemma-4-E4B-it",
    "gemma-4-e4b-it",
    "unsloth/gemma-4-E4B-it-GGUF",
    "GEMMA-4-E4B",
    "mervinpraison/praisonai-gemma-4-E4B-tamil",
])
def test_resolve_drafter_e4b(name):
    resolved = mtp.resolve_drafter(name)
    assert resolved == (
        "unsloth/gemma-4-E4B-it-GGUF",
        "MTP/mtp-gemma-4-E4B-it-Q8_0.gguf",
    )
    assert mtp.is_mtp_supported(name) is True


@pytest.mark.parametrize("name", [
    "qwen2.5-7b-instruct",
    "meta-llama/Llama-3.1-8B",
    "google/gemma-2-2b-it",  # gemma-2, not gemma-4
    "mistralai/Mistral-7B",
])
def test_resolve_drafter_unsupported(name):
    assert mtp.resolve_drafter(name) is None
    assert mtp.is_mtp_supported(name) is False


def test_resolve_drafter_precision():
    repo, fname = mtp.resolve_drafter("gemma-4-E4B-it", precision="bf16")
    assert fname == "MTP/mtp-gemma-4-E4B-it-BF16.gguf"
    repo, fname = mtp.resolve_drafter("gemma-4-E4B-it", precision="f16")
    assert fname == "MTP/mtp-gemma-4-E4B-it-F16.gguf"


def test_resolve_drafter_other_sizes():
    assert mtp.resolve_drafter("gemma-4-E2B-it")[1] == "MTP/mtp-gemma-4-E2B-it-Q8_0.gguf"
    assert mtp.resolve_drafter("gemma-4-12b-it")[1] == "MTP/mtp-gemma-4-12b-it-Q8_0.gguf"
    # No stock MTP drafter is published for 27B/31B — resolver must return None.
    assert mtp.resolve_drafter("gemma-4-27b-it") is None


def test_resolve_drafter_bad_precision():
    with pytest.raises(ValueError, match="precision"):
        mtp.resolve_drafter("gemma-4-E4B-it", precision="q4_k_m")


# --------------------------------------------------------------------------- #
# fetch_drafter
# --------------------------------------------------------------------------- #
def test_fetch_drafter_downloads(monkeypatch, tmp_path):
    seen = {}

    def _fake_download(repo_id, filename, local_dir, token=None, **_k):
        seen["repo_id"] = repo_id
        seen["filename"] = filename
        seen["local_dir"] = local_dir
        seen["token"] = token
        return str(tmp_path / "mtp-gemma-4-E4B-it-Q8_0.gguf")

    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.hf_hub_download = _fake_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    monkeypatch.setenv("HF_TOKEN", "hf_fake")

    result = mtp.fetch_drafter("gemma-4-E4B-it", tmp_path)
    assert str(result).endswith("mtp-gemma-4-E4B-it-Q8_0.gguf")
    assert seen["repo_id"] == "unsloth/gemma-4-E4B-it-GGUF"
    assert seen["filename"] == "MTP/mtp-gemma-4-E4B-it-Q8_0.gguf"
    assert seen["token"] == "hf_fake"


def test_fetch_drafter_unsupported_family(monkeypatch, tmp_path):
    # Must fail BEFORE trying to import/download.
    with pytest.raises(ValueError, match="Gemma-4"):
        mtp.fetch_drafter("qwen2.5-7b", tmp_path)


# --------------------------------------------------------------------------- #
# build_mtp_cmd
# --------------------------------------------------------------------------- #
def test_build_mtp_cmd_with_draft():
    cmd = llamacpp.build_mtp_cmd(
        "llama-server", "target.gguf", draft_gguf="draft.gguf",
        spec_draft_n_max=2, server=True, port=8080, ngl=99,
    )
    assert "--model" in cmd
    assert "target.gguf" in cmd
    assert "--model-draft" in cmd
    assert "draft.gguf" in cmd
    assert "--spec-type" in cmd
    assert "draft-mtp" in cmd
    assert "--spec-draft-n-max" in cmd
    assert "2" in cmd
    assert "-ngl" in cmd
    assert "99" in cmd
    assert "--port" in cmd
    assert "8080" in cmd


def test_build_mtp_cmd_no_draft():
    cmd = llamacpp.build_mtp_cmd("llama-cli", "target.gguf", draft_gguf=None, server=False)
    assert "--model" in cmd
    assert "-ngl" in cmd
    # Draft/MTP flags must be absent.
    assert "--model-draft" not in cmd
    assert "--spec-type" not in cmd
    assert "draft-mtp" not in cmd
    assert "--spec-draft-n-max" not in cmd
    # server=False -> no --port
    assert "--port" not in cmd


def test_build_mtp_cmd_extra_appended():
    cmd = llamacpp.build_mtp_cmd(
        "llama-cli", "t.gguf", server=False, extra=["--prompt", "hi", "-n", "16"])
    assert cmd[-4:] == ["--prompt", "hi", "-n", "16"]


# --------------------------------------------------------------------------- #
# find_llama_binary
# --------------------------------------------------------------------------- #
def test_find_llama_binary_missing_raises(monkeypatch):
    monkeypatch.delenv("LLAMA_CPP_BIN", raising=False)
    monkeypatch.setattr(llamacpp.shutil, "which", lambda _n: None)
    with pytest.raises(RuntimeError, match="LLAMA_CPP_BIN"):
        llamacpp.find_llama_binary("llama-server")


def test_find_llama_binary_from_path(monkeypatch):
    monkeypatch.delenv("LLAMA_CPP_BIN", raising=False)
    monkeypatch.setattr(llamacpp.shutil, "which", lambda _n: "/usr/local/bin/llama-server")
    assert llamacpp.find_llama_binary("llama-server") == "/usr/local/bin/llama-server"


# --------------------------------------------------------------------------- #
# parse_llama_timings
# --------------------------------------------------------------------------- #
_SAMPLE_TIMINGS = """
llama_perf_sampler_print:    sampling time =       9.12 ms /   257 runs
llama_perf_context_print: prompt eval time =     120.00 ms /    12 tokens (   10.00 ms per token,   100.00 tokens per second)
llama_perf_context_print:        eval time =    1234.56 ms /   256 runs   (    4.82 ms per token,   207.45 tokens per second)
llama_perf_context_print:       total time =    1500.00 ms /   268 tokens
"""

_SAMPLE_SPEC = _SAMPLE_TIMINGS + """
draft acceptance rate = 78.4 %
n_accept =  201 / n_drafted =  256
"""


def test_parse_llama_timings_tps():
    parsed = llamacpp.parse_llama_timings(_SAMPLE_TIMINGS)
    # Takes the LAST tokens-per-second (generation eval), not prompt eval.
    assert parsed["tokens_per_sec"] == 207.45
    assert parsed["n_predict"] == 256
    assert parsed["accept_rate"] is None


def test_parse_llama_timings_accept_rate():
    parsed = llamacpp.parse_llama_timings(_SAMPLE_SPEC)
    assert parsed["tokens_per_sec"] == 207.45
    assert parsed["accept_rate"] == pytest.approx(0.784)


def test_parse_llama_timings_n_accept_fraction():
    text = "eval time = 1000 ms / 100 runs ( 10 ms per token, 100.0 tokens per second)\n" \
           "n_accept = 80\nn_drafted = 100\n"
    parsed = llamacpp.parse_llama_timings(text)
    assert parsed["accept_rate"] == pytest.approx(0.80)
