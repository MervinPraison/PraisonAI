#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script finetunes a model using Unsloth's fast training framework.
It supports both ShareGPT and Alpaca‑style datasets by converting raw conversation
data into plain-text prompts using a chat template, then pre‑tokenizing the prompts.
Extra debug logging is added to help trace the root cause of errors.
"""

import os
import sys
import yaml
import shutil
import difflib
import textwrap
import contextlib
import subprocess
from functools import partial

# Preference-tuning methods. Unsloth patches TRL's DPO, ORPO and KTO trainers
# alongside SFT (unsloth/__init__.py lists them in the trainers it rewrites), but
# this module could only ever run SFT -- so a dataset of chosen/rejected pairs had
# nowhere to go and the whole preference-tuning half of the library was
# unreachable from PraisonAI.
#
# Each entry names the TRL trainer and config class, the columns the dataset must
# provide, and whether the method needs a frozen reference model. Adding a method
# is one entry plus its import.
TRAINING_METHODS = {
    "sft": {
        "trainer": "SFTTrainer", "config": "SFTConfig",
        "columns": (), "needs_ref_model": False,
        "summary": "supervised fine-tuning on completions",
    },
    "dpo": {
        "trainer": "DPOTrainer", "config": "DPOConfig",
        "columns": ("prompt", "chosen", "rejected"), "needs_ref_model": True,
        "summary": "direct preference optimisation on chosen/rejected pairs",
    },
    "orpo": {
        "trainer": "ORPOTrainer", "config": "ORPOConfig",
        # ORPO folds the reference model into its loss, so there is none to hold.
        "columns": ("prompt", "chosen", "rejected"), "needs_ref_model": False,
        "summary": "odds-ratio preference optimisation, no reference model",
    },
    "kto": {
        "trainer": "KTOTrainer", "config": "KTOConfig",
        "columns": ("prompt", "completion", "label"), "needs_ref_model": True,
        "summary": "Kahneman-Tversky optimisation on thumbs-up/down labels",
    },
}

# Turn markers for masking the prompt out of the loss.
#
# TRL's `assistant_only_loss` needs `{% generation %}` in the chat template, and
# NONE of unsloth's 43 templates contain it (verified: grep -c "generation %}"
# unsloth/chat_templates.py -> 0). So `assistant_only_loss: auto` resolved to
# False for every template a user can actually select, and every instruction
# run trained on the prompt as well as the answer -- a quality loss with no
# error, announced only by a summary line reading "Loss mask: full sequence".
#
# Unsloth's own answer is `train_on_responses_only(trainer, instruction_part,
# response_part)` (unsloth/chat_templates.py:58-87), which masks by locating
# literal marker strings and works on any template. It needs the two markers,
# which vary by family -- hence this table.
RESPONSE_MARKERS = {
    "llama-3": ("<|start_header_id|>user<|end_header_id|>\n\n",
                "<|start_header_id|>assistant<|end_header_id|>\n\n"),
    "chatml": ("<|im_start|>user\n", "<|im_start|>assistant\n"),
    "gemma": ("<start_of_turn>user\n", "<start_of_turn>model\n"),
    "mistral": ("[INST]", "[/INST]"),
    "phi": ("<|user|>\n", "<|assistant|>\n"),
    "zephyr": ("<|user|>\n", "<|assistant|>\n"),
}

# Which markers a chat_template name uses. Matched longest-first so "llama-3.1"
# does not fall through to a shorter, wrong prefix.
TEMPLATE_TO_MARKERS = {
    "llama-3": "llama-3", "llama3": "llama-3", "llama-3.1": "llama-3",
    "llama-31": "llama-3", "llama": "llama-3",
    "chatml": "chatml", "qwen-2.5": "chatml", "qwen25": "chatml",
    "qwen2.5": "chatml", "qwen-25": "chatml", "qwen-3": "chatml",
    "qwen3": "chatml", "qwen3-instruct": "chatml", "qwen3-thinking": "chatml",
    "phi-4": "chatml", "gptoss": "chatml", "gpt-oss": "chatml",
    "yi-chat": "chatml", "unsloth": "chatml",
    "gemma": "gemma", "gemma2": "gemma", "gemma-3": "gemma", "gemma3": "gemma",
    "gemma-3n": "gemma", "gemma3n": "gemma", "gemma-4": "gemma", "gemma4": "gemma",
    "gemma_chatml": "chatml", "gemma2_chatml": "chatml",
    "mistral": "mistral",
    "phi-3": "phi", "phi-35": "phi", "phi-3.5": "phi",
    "zephyr": "zephyr",
}


# The summary line has to name *which* route masked, because the two have very
# different coverage and "assistant replies only" hid that distinction.
_MASK_LABELS = {
    False: "full sequence (training on prompts too)",
    "assistant_only_loss": "assistant replies only (TRL assistant_only_loss)",
    "train_on_responses_only": "assistant replies only (unsloth turn markers)",
}


# Phrasings the four runtimes use for the same condition. `torch.cuda.OutOfMemoryError`
# subclasses RuntimeError, so the CLI's catch-all swallowed it into a single ERROR
# line carrying torch's raw allocator dump -- the most common fine-tuning failure,
# and the one where a first-time user has no idea which number to change.
_OOM_MARKERS = (
    "out of memory",
    "cuda out of memory",
    "hip out of memory",
    "outofmemoryerror",
)

# Ordered cheapest-first: sequence length is usually the biggest lever and the
# least destructive to change. Same ordering unsloth validated in its studio
# backend (studio/backend/core/training/worker.py:4834-4845).
OOM_REMEDIATION = (
    "The GPU ran out of memory. In order of what usually helps most:\n"
    "  1. Lower max_seq_length (try 2048, or 4096 if you were higher)\n"
    "  2. Set use_gradient_checkpointing: unsloth (if it is off)\n"
    "  3. Lower per_device_train_batch_size, raising gradient_accumulation_steps\n"
    "     by the same factor to keep the effective batch size\n"
    "  4. Use a smaller model, or a 4-bit one (load_in_4bit: true)"
)


def is_out_of_memory(exc):
    """True when this exception is a GPU OOM, whatever runtime raised it.

    The class name is folded into the searched text rather than checked
    separately: `torch.cuda.OutOfMemoryError` is matched by the
    "outofmemoryerror" marker, so a separate `type(exc).__name__` branch was
    code no test could distinguish from its absence.
    """
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _OOM_MARKERS)


def decide_masking(use_mask, supports_mask, markers):
    """Which masking route to take: False, or the name of the mechanism.

    Separate from the trainer so the decision can be tested directly. A test
    that reads `train_model`'s source for the string "train_on_responses_only"
    passes even when the branch that calls it is disabled -- which is how this
    defect survived in the first place.
    """
    if not use_mask:
        return False
    if supports_mask:
        return "assistant_only_loss"
    if markers:
        return "train_on_responses_only"
    return None      # asked for, and neither route available


def resolve_response_markers(chat_template, model_name=""):
    """(instruction_part, response_part) for a template, or None if unknown.

    Falls back to the model name when no explicit chat_template is configured,
    because the model's own template is then in use. Returns None rather than
    guessing: masking on the wrong markers silently trains on nothing, which is
    worse than not masking at all.
    """
    for source, is_model in ((chat_template, False), (model_name, True)):
        if not source:
            continue
        key = str(source).strip().lower()
        if is_model:
            # Match the repo name, not the org. Every unsloth model is
            # "unsloth/<name>", and "unsloth" is itself a template key -- so
            # scanning the full id sent every one of them to the chatml markers,
            # including Gemma and Llama models whose real markers are different.
            key = key.rsplit("/", 1)[-1]
        if key in TEMPLATE_TO_MARKERS:
            return RESPONSE_MARKERS[TEMPLATE_TO_MARKERS[key]]
        for name in sorted(TEMPLATE_TO_MARKERS, key=len, reverse=True):
            # Longest-first so "llama-3.1" beats "llama". Hyphens and dots are
            # written both ways in the wild ("gemma-2" vs "gemma2").
            if name in key or name.replace("-", "") in key.replace("-", ""):
                return RESPONSE_MARKERS[TEMPLATE_TO_MARKERS[name]]
    return None


# GGUF / Ollama quantization methods supported by Unsloth's exporter. Validated up
# front so a typo (e.g. "q4km") fails fast with a clear message instead of after a
# long training run when the export step finally rejects it.
VALID_QUANTIZATION_METHODS = frozenset({
    "q4_k_m", "q5_k_m", "q8_0", "q4_0", "q4_1", "q5_0", "q5_1",
    "q3_k_m", "q6_k", "f16", "bf16", "q2_k",
})


def _lazy_import_training_deps():
    """Import heavy training dependencies only when needed."""
    try:
        import torch
        from transformers import TextStreamer, TrainingArguments
        from unsloth import FastLanguageModel, is_bfloat16_supported
        from unsloth.chat_templates import standardize_sharegpt, get_chat_template
        from trl import SFTTrainer, SFTConfig
        # Imported lazily and individually: a TRL old enough to lack one of these
        # should still be able to run the others rather than failing at import.
        _pref = {}
        for _name in ("DPOTrainer", "DPOConfig", "ORPOTrainer", "ORPOConfig",
                      "KTOTrainer", "KTOConfig"):
            try:
                _pref[_name] = getattr(__import__("trl", fromlist=[_name]), _name)
            except (ImportError, AttributeError):
                pass
        from datasets import load_dataset, concatenate_datasets
        from psutil import virtual_memory
        # Make available in global scope for the rest of the module
        globals().update({
            'torch': torch,
            'TextStreamer': TextStreamer,
            'FastLanguageModel': FastLanguageModel,
            'is_bfloat16_supported': is_bfloat16_supported,
            'SFTTrainer': SFTTrainer,
            'SFTConfig': SFTConfig,
            **_pref,
            'TrainingArguments': TrainingArguments,
            'load_dataset': load_dataset,
            'concatenate_datasets': concatenate_datasets,
            'virtual_memory': virtual_memory,
            'standardize_sharegpt': standardize_sharegpt,
            'get_chat_template': get_chat_template,
        })
    except ImportError as e:
        raise ImportError(
            f"Training dependencies not available. Install with: "
            f"pip install torch transformers unsloth datasets trl psutil. Error: {e}"
        ) from e

#####################################
# Step 1: Formatting Raw Conversations
#####################################
def formatting_prompts_func(examples, tokenizer):
    """
    Converts each example's conversation into a single plain-text prompt.
    If the example has a "conversations" field, process it as ShareGPT-style.
    Otherwise, assume Alpaca-style data with "instruction", "input", and "output" fields.
    """
    # Per-batch prints fire on every mapped batch and drown the log; gate them behind
    # PRAISON_DEBUG so normal runs stay readable (the run summary still prints).
    # Parse as a boolean so PRAISON_DEBUG=0/false/no disable it (not just "unset").
    _dbg = os.environ.get("PRAISON_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    if _dbg:
        print("DEBUG: formatting_prompts_func() received batch with keys:", list(examples.keys()))
    texts = []
    # Check if the example has a "conversations" field.
    if "conversations" in examples:
        for convo in examples["conversations"]:
            try:
                formatted = tokenizer.apply_chat_template(
                    convo,
                    tokenize=False,  # Return a plain string
                    add_generation_prompt=False
                )
            except Exception as e:
                print(f"ERROR in apply_chat_template (conversations): {e}")
                formatted = ""
            # Flatten list if necessary
            if isinstance(formatted, list):
                formatted = formatted[0] if len(formatted) == 1 else "\n".join(formatted)
            texts.append(formatted)
    else:
        # Assume Alpaca format: use "instruction", "input", and "output" keys.
        instructions = examples.get("instruction", [])
        inputs_list = examples.get("input", [])
        outputs_list = examples.get("output", [])
        # If any field is missing, replace with empty string.
        for ins, inp, out in zip(instructions, inputs_list, outputs_list):
            # Create a conversation-like structure.
            convo = [
                {"role": "user", "content": ins + (f"\nInput: {inp}" if inp.strip() != "" else "")},
                {"role": "assistant", "content": out}
            ]
            try:
                formatted = tokenizer.apply_chat_template(
                    convo,
                    tokenize=False,
                    add_generation_prompt=False
                )
            except Exception as e:
                print(f"ERROR in apply_chat_template (alpaca): {e}")
                formatted = ""
            if isinstance(formatted, list):
                formatted = formatted[0] if len(formatted) == 1 else "\n".join(formatted)
            texts.append(formatted)
    if texts and _dbg:
        print("DEBUG: Raw texts sample (first 200 chars):", texts[0][:200])
    return {"text": texts}

#####################################
# Step 2: Tokenizing the Prompts
#####################################
def tokenize_function(examples, hf_tokenizer, max_length):
    """
    Tokenizes a batch of text prompts with padding and truncation enabled.

    Kept as a public helper (re-exported by ``praisonai.train``) even though the
    training path no longer calls it (modern TRL tokenizes internally).
    """
    flat_texts = []
    for t in examples["text"]:
        if isinstance(t, list):
            t = t[0] if len(t) == 1 else " ".join(t)
        flat_texts.append(t)
    tokenized = hf_tokenizer(
        flat_texts,
        padding="max_length",
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    return {key: value.tolist() for key, value in tokenized.items()}

#####################################
# Main Training Class
#####################################
class TrainModel:
    def __init__(self, config_path="config.yaml"):
        # Under DDP the flag that routes Unsloth through its non-reentrant
        # (DDP-safe) checkpointing path must be set BEFORE `unsloth` is imported —
        # the legacy path is selected at import/load time, so setting it later
        # (after from_pretrained) leaves a torchrun launch on the reentrant path
        # and it still crashes in backward with "parameter marked as ready twice".
        if int(os.environ.get("WORLD_SIZE", 1)) > 1:
            os.environ.setdefault("UNSLOTH_USE_NEW_MODEL", "1")
        _lazy_import_training_deps()
        self.load_config(config_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.hf_tokenizer = None   # The underlying HF tokenizer
        self.chat_tokenizer = None # Chat wrapper for formatting

    @classmethod
    def for_export(cls, config):
        """Build a trainer for EXPORT ONLY (push an already-trained model) from a
        config dict, skipping the training-only validation (no dataset required).

        Used by the standalone `export` command so a non-developer can publish a
        model that was trained earlier without re-running training. The caller loads
        the model via load_model() and assigns self.model / self.hf_tokenizer.
        """
        obj = cls.__new__(cls)
        _lazy_import_training_deps()
        obj.config = dict(config or {})
        if "model" in obj.config and "model_name" not in obj.config:
            obj.config["model_name"] = obj.config["model"]
        # Validate quantization up front here too — for_export skips the full
        # training validate_config, so an invalid --quant would otherwise only
        # fail deep inside Unsloth / `ollama create`.
        q = obj.config.get("quantization_method")
        # Configs written against older templates carry the single-element
        # list form. Accepting it costs one line and avoids failing a run for a
        # shape the project itself shipped. Normalize back into config so the
        # GGUF exporter (which re-reads self.config) receives the method string,
        # not the list.
        if isinstance(q, (list, tuple)) and len(q) == 1:
            q = q[0]
            obj.config["quantization_method"] = q
        if q is not None and str(q).lower() not in VALID_QUANTIZATION_METHODS:
            raise ValueError(
                f"quantization_method '{q}' is not valid. Choose one of: "
                f"{', '.join(sorted(VALID_QUANTIZATION_METHODS))}."
            )
        obj.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        obj.model = None
        obj.hf_tokenizer = None
        obj.chat_tokenizer = None
        return obj

    def load_config(self, path):
        with open(path, "r") as file:
            self.config = yaml.safe_load(file) or {}
        # `model` is an accepted alias for `model_name` (matches the --model CLI flag).
        if "model" in self.config and "model_name" not in self.config:
            self.config["model_name"] = self.config["model"]
        self.validate_config()
        print("DEBUG: Loaded config:", self.config)

    # Known config keys — anything else is flagged so typos/unsupported keys are not
    # silently ignored (important for people and agents writing configs by hand).
    KNOWN_KEYS = frozenset({
        "model", "model_name", "model_parameters", "max_seq_length", "load_in_4bit",
        "chat_template", "lora_r", "lora_alpha", "lora_dropout", "lora_bias",
        "lora_target_modules", "use_gradient_checkpointing", "use_rslora", "loftq_config",
        "random_state", "dataset", "dataset_text_field", "dataset_num_proc", "packing",
        "per_device_train_batch_size", "gradient_accumulation_steps", "warmup_steps",
        "max_steps", "num_train_epochs", "learning_rate", "fp16", "bf16", "logging_steps",
        "optim", "weight_decay", "lr_scheduler_type", "seed", "output_dir",
        "assistant_only_loss", "train_on_responses_only", "save_steps",
        "train", "huggingface_save", "huggingface_save_gguf", "ollama_save",
        "method", "beta", "max_prompt_length", "desirable_weight", "undesirable_weight",
        "hf_private", "save_method", "commit_message", "tags",
        "hf_model_name", "ollama_model", "quantization_method", "remove_unused_columns",
        # quantization / precision
        "dtype", "load_in_8bit", "full_finetuning",
        # advanced LoRA
        "modules_to_save", "rank_pattern", "alpha_pattern", "use_dora",
        # checkpointing / resume
        "save_strategy", "save_total_limit", "save_safetensors",
        "resume_from_checkpoint", "final_model_dir",
        # evaluation / best-checkpoint / early stopping
        "val_split_ratio", "eval_strategy", "eval_steps", "per_device_eval_batch_size",
        "load_best_model_at_end", "metric_for_best_model", "greater_is_better",
        "early_stopping_patience", "early_stopping_threshold",
        # extra training knobs
        "max_grad_norm", "warmup_ratio", "lr_scheduler_kwargs", "adam_beta1",
        "adam_beta2", "adam_epsilon", "group_by_length", "neftune_noise_alpha",
        "dataloader_num_workers", "logging_first_step", "data_seed",
        "ddp_find_unused_parameters", "push_to_hub", "hub_model_id", "hub_strategy",
        "report_to", "run_name", "training_arguments",
        # MTP (Multi-Token Prediction) fast-inference drafter
        "mtp_draft", "mtp_draft_repo", "mtp_draft_file", "spec_draft_n_max",
    })

    @staticmethod
    def resolve_method(config):
        """Normalise and check `method`, returning it. Kept separate from
        `validate_config` so it can be exercised without a CUDA import."""
        method = str(config.get("method", "sft")).lower()
        if method not in TRAINING_METHODS:
            raise ValueError(
                f"method '{method}' is not supported. Choose one of: "
                + ", ".join(f"{k} ({v['summary']})" for k, v in TRAINING_METHODS.items()))
        config["method"] = method
        return method

    def validate_config(self):
        self.resolve_method(self.config)

        required = ["model_name", "max_seq_length", "dataset"]
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(
                f"Config is missing required keys: {missing}. Minimal example:\n"
                f"  model_name: unsloth/gemma-2-2b-it-bnb-4bit\n"
                f"  max_seq_length: 2048\n"
                f"  dataset:\n    - name: yahma/alpaca-cleaned"
            )
        # Fail fast (before training) when a publish target is requested but its
        # destination name is missing, instead of silently skipping the upload the
        # user asked for after a long run.
        if self._flag(self.config.get("huggingface_save")) or self._flag(
            self.config.get("huggingface_save_gguf")
        ):
            if not self.config.get("hf_model_name"):
                raise ValueError(
                    "hf_model_name is required when huggingface_save or "
                    "huggingface_save_gguf is enabled."
                )
        if self._flag(self.config.get("ollama_save")) and not self.config.get("ollama_model"):
            raise ValueError("ollama_model is required when ollama_save is enabled.")

        # --- Preflight: fail FAST with friendly messages BEFORE any model/GPU load,
        # so a non-developer gets a clear, actionable error in seconds instead of a
        # traceback after minutes of downloads. ---

        # GPU: fine-tuning cannot run on CPU. Catch it before Unsloth tries.
        # Only enforced when training is enabled — publish/export-only runs
        # (train: false) are valid on CPU.
        if self._flag(self.config.get("train"), default=True) and not torch.cuda.is_available():
            raise ValueError(
                "No CUDA GPU detected. Fine-tuning needs a GPU. On a rented box "
                "check the driver; on CPU it cannot run."
            )

        # Hugging Face token: required to publish. Checked up front so a long run
        # doesn't finish only to fail at the upload step. A cached login via
        # `huggingface-cli login` is also accepted (downstream Hub calls use it),
        # so only fail when NEITHER an env token NOR a cached token is present.
        publishing = (
            self._flag(self.config.get("huggingface_save"))
            or self._flag(self.config.get("huggingface_save_gguf"))
            or self._flag(self.config.get("push_to_hub"))
        )
        if publishing and not self._has_hf_credentials():
            raise ValueError(
                "Publishing to Hugging Face is enabled but no credentials were found. "
                "Run `huggingface-cli login` or `export HF_TOKEN=hf_...`. To train "
                "without publishing, set huggingface_save: false."
            )

        # Disk: model downloads + checkpoints + merged export need headroom. A 10GB
        # floor catches the common "no space left on device" mid-run failure early.
        try:
            free_gb = shutil.disk_usage(self.config.get("output_dir") or ".").free / 2 ** 30
        except OSError:
            free_gb = None
        if free_gb is not None and free_gb < 10:
            raise ValueError(
                f"Low disk: only {free_gb:.1f} GB free on the training disk "
                f"(need ~10 GB minimum). Free up space or set output_dir to a "
                f"larger disk."
            )

        # Quantization method: only relevant when a GGUF/Ollama export is requested.
        if self._flag(self.config.get("huggingface_save_gguf")) or self._flag(
            self.config.get("ollama_save")
        ):
            q = self.config.get("quantization_method")
            # Configs written against older templates carry the single-element
            # list form. Accepting it costs one line and avoids failing a run
            # for a shape the project itself shipped. Normalize back into config
            # so the GGUF exporter (which re-reads self.config) receives the
            # method string, not the list.
            if isinstance(q, (list, tuple)) and len(q) == 1:
                q = q[0]
                self.config["quantization_method"] = q
            if q is not None and str(q).lower() not in VALID_QUANTIZATION_METHODS:
                raise ValueError(
                    f"quantization_method '{q}' is not valid. Choose one of: "
                    f"{', '.join(sorted(VALID_QUANTIZATION_METHODS))}."
                )

        # --- Unknown keys: collect ALL, suggest the closest known key, print once. ---
        unknown = [k for k in self.config if k not in self.KNOWN_KEYS]
        if unknown:
            lines = ["WARNING: unrecognized config key(s) — these will be ignored:"]
            for key in unknown:
                match = difflib.get_close_matches(str(key), self.KNOWN_KEYS, n=1)
                suggestion = f"  (did you mean '{match[0]}'?)" if match else ""
                lines.append(f"  - {key}{suggestion}")
            print("\n".join(lines))

    @staticmethod
    def _require_columns(dataset, columns, method):
        """Fail before the run starts, naming the columns that are missing.

        TRL's own error for a wrongly-shaped preference dataset surfaces deep in
        the collator -- minutes in, after the model is loaded and quantised, and
        worded in terms of tensors rather than the file the user pointed at.
        """
        if not columns:
            return
        have = set(getattr(dataset, "column_names", None) or [])
        missing = [c for c in columns if c not in have]
        if missing:
            raise ValueError(
                f"method '{method}' needs the column(s) {missing} and the dataset has "
                f"{sorted(have) or 'none'}. A {method} dataset needs "
                f"{list(columns)} per row.")

    @staticmethod
    def _flag(value, default=False):
        """Coerce a config flag to bool. Accepts real YAML booleans and the string
        forms ('true'/'false') that older configs use, so `train: true` and
        `train: "true"` both work instead of crashing on `.lower()`."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    @staticmethod
    def _has_hf_credentials():
        """True if a Hugging Face token is available via env OR a cached
        `huggingface-cli login`. The Hub client accepts a cached token when
        ``token=None``, so preflight must not reject a valid cached login."""
        if os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN"):
            return True
        with contextlib.suppress(Exception):
            from huggingface_hub import get_token
            if get_token():
                return True
        return False

    def _supports_assistant_mask(self):
        """True iff assistant-only loss will actually produce a usable mask for this
        tokenizer (mirrors TRL's runtime check), so we can auto-enable it without
        risking TRL's "no assistant tokens" RuntimeError on templates that lack the
        `{% generation %}` markers (most stock templates do)."""
        tok = self.hf_tokenizer
        if not getattr(tok, "chat_template", None):
            return False
        dummy = [{"role": "user", "content": "ping"},
                 {"role": "assistant", "content": "pong"}]
        try:
            out = tok.apply_chat_template(
                dummy, tokenize=True, return_dict=True,
                return_assistant_tokens_mask=True, add_generation_prompt=False,
            )
        except Exception:
            return False
        mask = out.get("assistant_masks")
        if not mask:
            return False
        if isinstance(mask[0], (list, tuple)):
            return any(1 in row for row in mask)
        return 1 in mask

    def print_system_info(self):
        print("DEBUG: PyTorch version:", torch.__version__)
        print("DEBUG: CUDA version:", torch.version.cuda)
        if torch.cuda.is_available():
            print("DEBUG: CUDA Device Capability:", torch.cuda.get_device_capability())
        else:
            print("DEBUG: CUDA is not available")
        print("DEBUG: Python Version:", sys.version)
        print("DEBUG: Python Path:", sys.executable)

    def check_gpu(self):
        # Guard the CUDA query: get_device_properties(0) raises a raw error on a
        # CPU-only box. validate_config already fails fast for training, but this
        # keeps other entry points (e.g. export) from crashing here.
        if not torch.cuda.is_available():
            print("DEBUG: No CUDA GPU available.")
            return
        gpu_stats = torch.cuda.get_device_properties(0)
        print(f"DEBUG: GPU = {gpu_stats.name}. Max memory = {round(gpu_stats.total_memory/(1024**3),3)} GB.")

    def check_ram(self):
        ram_gb = virtual_memory().total / 1e9
        print(f"DEBUG: Your runtime has {ram_gb:.1f} gigabytes of available RAM")
        if ram_gb < 20:
            print("DEBUG: Not using a high-RAM runtime")
        else:
            print("DEBUG: You are using a high-RAM runtime!")

    def prepare_model(self):
        print("DEBUG: Preparing model and tokenizer...")
        # --- Multi-GPU / DDP detection (torchrun sets LOCAL_RANK/WORLD_SIZE) ---
        local_rank = int(os.environ.get("LOCAL_RANK", os.environ.get("RANK", 0)))
        world_size = int(os.environ.get("WORLD_SIZE", 1))
        self._distributed = world_size > 1
        # --- Quantization / precision flexibility ---
        dtype_cfg = self.config.get("dtype")  # None | "float16" | "bfloat16"
        dtype = getattr(torch, dtype_cfg) if isinstance(dtype_cfg, str) else None
        load_kwargs = dict(
            model_name=self.config["model_name"],
            max_seq_length=self.config["max_seq_length"],
            dtype=dtype,
            load_in_4bit=self._flag(self.config.get("load_in_4bit"), default=True),
        )
        if self.config.get("load_in_8bit") is not None:
            load_kwargs["load_in_8bit"] = self._flag(self.config["load_in_8bit"])
        if self.config.get("full_finetuning") is not None:
            load_kwargs["full_finetuning"] = self._flag(self.config["full_finetuning"])
        if load_kwargs.get("load_in_4bit") and load_kwargs.get("load_in_8bit"):
            raise ValueError("Set only one of load_in_4bit / load_in_8bit, not both.")
        if self._distributed:
            # Under DDP each rank loads the FULL model on its own GPU. Do NOT use
            # "auto"/"balanced" (that is single-process model-parallel and conflicts).
            load_kwargs["device_map"] = {"": local_rank}
            print(f"DEBUG: DDP rank {local_rank}/{world_size} -> device_map {{'':{local_rank}}}")
        self.model, original_tokenizer = FastLanguageModel.from_pretrained(**load_kwargs)
        print("DEBUG: Model and original tokenizer loaded.")
        if original_tokenizer.pad_token is None:
            original_tokenizer.pad_token = original_tokenizer.eos_token
        original_tokenizer.model_max_length = self.config["max_seq_length"]
        # Only override the tokenizer's built-in chat template when the config asks
        # for a specific one. Forcing "llama-3.1" onto every model corrupted the
        # prompt formatting for Gemma / Qwen / any non-Llama model.
        chat_template = self.config.get("chat_template")
        if chat_template:
            self.chat_tokenizer = get_chat_template(original_tokenizer, chat_template=chat_template)
        else:
            self.chat_tokenizer = original_tokenizer
        # Fail fast if we have no usable chat template. Without one,
        # apply_chat_template() errors are swallowed downstream and silently
        # produce empty training text, which corrupts the run rather than
        # reporting the real cause.
        if getattr(self.chat_tokenizer, "chat_template", None) is None:
            raise ValueError(
                "Tokenizer for model '{}' has no chat template and none was "
                "provided via config 'chat_template'. Set 'chat_template' (e.g. "
                "'gemma', 'qwen-2.5', 'llama-3.1') so conversations format "
                "correctly.".format(self.config["model_name"])
            )
        self.hf_tokenizer = self.chat_tokenizer
        print("DEBUG: Chat tokenizer ready; HF tokenizer saved.")
        # NOTE: UNSLOTH_USE_NEW_MODEL is set in __init__ BEFORE unsloth is imported
        # (the DDP-safe non-reentrant checkpointing path is chosen at import/load
        # time). We re-assert it here as a harmless safety net.
        if self._distributed:
            os.environ.setdefault("UNSLOTH_USE_NEW_MODEL", "1")
        # --- Full fine-tuning: train the base weights directly, skip LoRA ---
        if self._flag(self.config.get("full_finetuning"), default=False):
            print("DEBUG: full_finetuning enabled — training base model, skipping LoRA adapters.")
            return
        peft_kwargs = dict(
            r=self.config.get("lora_r", 16),
            target_modules=self.config.get("lora_target_modules", [
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]),
            lora_alpha=self.config.get("lora_alpha", 16),
            lora_dropout=self.config.get("lora_dropout", 0),
            bias=self.config.get("lora_bias", "none"),
            use_gradient_checkpointing=self.config.get("use_gradient_checkpointing", "unsloth"),
            random_state=self.config.get("random_state", 3407),
            use_rslora=self._flag(self.config.get("use_rslora"), default=False),
            loftq_config=self.config.get("loftq_config", None),
        )
        # Optional advanced LoRA knobs (only passed when set).
        for opt in ("modules_to_save", "rank_pattern", "alpha_pattern", "use_dora"):
            if self.config.get(opt) is not None:
                peft_kwargs[opt] = self.config[opt]
        self.model = FastLanguageModel.get_peft_model(self.model, **peft_kwargs)
        print("DEBUG: LoRA adapters added.")

    def process_dataset(self, dataset_info):
        dataset_name = dataset_info["name"]
        split_type = dataset_info.get("split_type", "train")
        print(f"DEBUG: Loading dataset '{dataset_name}' split '{split_type}'...")
        # Support HF hub datasets, explicit data_files, or a local file path.
        data_files = dataset_info.get("data_files")
        if data_files:
            fmt = dataset_info.get("format", "json")
            dataset = load_dataset(fmt, data_files=data_files, split=split_type)
        elif os.path.exists(dataset_name):
            ext = dataset_name.rsplit(".", 1)[-1]
            fmt = dataset_info.get("format", {"jsonl": "json"}.get(ext, ext))
            dataset = load_dataset(fmt, data_files=dataset_name, split=split_type)
        else:
            dataset = load_dataset(dataset_name, split=split_type)
        # Column rename (advertised in the default config; previously ignored).
        rename = dataset_info.get("rename")
        if isinstance(rename, dict):
            rename = {s: d for s, d in rename.items()
                      if s in dataset.column_names and s != d}
            if rename:
                dataset = dataset.rename_columns(rename)
        # Row filter (advertised in the default config; previously ignored).
        if self._flag(dataset_info.get("filter_data"), default=False):
            col = dataset_info.get("filter_column_value")
            val = dataset_info.get("filter_value")
            if col:
                dataset = dataset.filter(lambda ex: ex.get(col) == val)
        # Honor num_samples (train on a subset) — previously advertised but ignored.
        # Validate as a positive integer so 0/negatives/booleans/typos fail fast with
        # a clear message instead of silently training on the full set or crashing mid-run.
        num_samples = dataset_info.get("num_samples")
        if num_samples is not None:
            if isinstance(num_samples, bool) or not isinstance(num_samples, int):
                try:
                    num_samples = int(num_samples)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"dataset[].num_samples must be a positive integer, got "
                        f"{num_samples!r}."
                    ) from exc
            if num_samples < 1:
                raise ValueError(
                    f"dataset[].num_samples must be a positive integer, got "
                    f"{num_samples!r}."
                )
            dataset = dataset.select(range(min(num_samples, len(dataset))))
            print(f"DEBUG: Using {len(dataset)} samples (num_samples={num_samples}).")
            # num_samples takes a head slice, which runs BEFORE the shuffle below —
            # so without shuffle you always train on the first N rows (often sorted
            # by source/topic and unrepresentative). Say so once, clearly.
            if not self._flag(dataset_info.get("shuffle"), default=False):
                print("NOTE: num_samples takes the FIRST N rows before shuffle; "
                      "add shuffle: true to sample randomly.")
        print("DEBUG: Dataset columns:", dataset.column_names)

        # SFT flattens every row to a single `text` column. A preference dataset
        # must keep prompt/chosen/rejected (or prompt/completion/label) — the
        # trainer reads those columns by name, and flattening them destroyed the
        # dataset before the method ever saw it.
        if self.config.get("method", "sft") != "sft":
            method = self.config["method"]
            if self._flag(dataset_info.get("shuffle"), default=False):
                dataset = dataset.shuffle(
                    seed=int(dataset_info.get("seed", self.config.get("seed", 3407))))
            print(f"DEBUG: method={method}; keeping preference columns "
                  f"{dataset.column_names} as-is.")
            return dataset

        if self._flag(dataset_info.get("shuffle"), default=False):
            dataset = dataset.shuffle(
                seed=int(dataset_info.get("seed", self.config.get("seed", 3407))))
        if "conversations" in dataset.column_names:
            print("DEBUG: Standardizing dataset (ShareGPT style)...")
            dataset = standardize_sharegpt(dataset)
        else:
            print("DEBUG: Dataset does not have 'conversations'; assuming Alpaca format.")
        print("DEBUG: Applying formatting function to dataset...")
        format_func = partial(formatting_prompts_func, tokenizer=self.chat_tokenizer)
        dataset = dataset.map(format_func, batched=True, remove_columns=dataset.column_names)
        # Drop rows that formatted to empty text (chat-template failure / empty convo)
        # instead of silently training on blank examples.
        before = len(dataset)
        dataset = dataset.filter(lambda ex: bool((ex.get("text") or "").strip()))
        if before - len(dataset):
            print(f"WARNING: dropped {before - len(dataset)}/{before} examples that "
                  f"formatted to empty text.")
        if len(dataset) == 0:
            raise ValueError(
                "All examples formatted to empty text — check dataset schema / chat_template.")
        return dataset

    def load_datasets(self):
        datasets = []
        for dataset_info in self.config["dataset"]:
            # Advertised in the shipped templates but never read. Saying so beats
            # silently discarding a formatter the user believed was running.
            if dataset_info.get("processing_func"):
                print(
                    f"WARNING: dataset.processing_func "
                    f"({dataset_info['processing_func']}) is not supported and will "
                    f"be ignored; formatting is chosen automatically from the "
                    f"dataset's columns."
                )
            print("DEBUG: Processing dataset info:", dataset_info)
            # A validation/test split loaded here is CONCATENATED into training, not
            # held out — an easy way to contaminate eval without noticing. Warn, and
            # point at the real held-out mechanism (val_split_ratio).
            split_type = str(dataset_info.get("split_type", "train")).strip().lower()
            if split_type in {"validation", "valid", "test", "eval"}:
                print(f"WARNING: dataset split_type '{split_type}' is ADDED to the "
                      f"TRAINING data (not held out). Use val_split_ratio for a "
                      f"held-out eval set.")
            datasets.append(self.process_dataset(dataset_info))
        combined = concatenate_datasets(datasets)
        print("DEBUG: Combined dataset has", len(combined), "examples.")
        return combined

    def train_model(self):
        print("DEBUG: Starting training...")
        # The dataset carries a "text" column (from formatting_prompts_func). Modern
        # TRL tokenizes internally, so we no longer pre-tokenize + pass a dummy field.
        raw_dataset = self.load_datasets()
        print("DEBUG: Dataset ready with", len(raw_dataset), "examples.")

        # Optional held-out eval split so overfitting can be monitored and the best
        # checkpoint kept (val_split_ratio carves it from the training data).
        eval_dataset = None
        val_ratio = self.config.get("val_split_ratio")
        if val_ratio:
            split = raw_dataset.train_test_split(
                test_size=float(val_ratio), seed=int(self.config.get("seed", 3407)))
            raw_dataset, eval_dataset = split["train"], split["test"]
            print(f"DEBUG: eval split -> train={len(raw_dataset)} eval={len(eval_dataset)}")

        default_report = "wandb" if os.getenv("PRAISON_WANDB") else "none"
        # SFT-specific fields (dataset_text_field, max_length, packing, ...) live on
        # SFTConfig in modern TRL, not on TrainingArguments / the SFTTrainer kwargs.
        sft_params = {
            "per_device_train_batch_size": self.config.get("per_device_train_batch_size", 2),
            "gradient_accumulation_steps": self.config.get("gradient_accumulation_steps", 2),
            "warmup_steps": self.config.get("warmup_steps", 50),
            "learning_rate": self.config.get("learning_rate", 2e-4),
            "fp16": self.config.get("fp16", not is_bfloat16_supported()),
            "bf16": self.config.get("bf16", is_bfloat16_supported()),
            "logging_steps": self.config.get("logging_steps", 15),
            "logging_first_step": self._flag(self.config.get("logging_first_step"), default=True),
            "optim": self.config.get("optim", "adamw_8bit"),
            "weight_decay": self.config.get("weight_decay", 0.01),
            "lr_scheduler_type": self.config.get("lr_scheduler_type", "linear"),
            "seed": self.config.get("seed", 3407),
            "output_dir": self.config.get("output_dir", "outputs"),
            "report_to": self.config.get("report_to", default_report),
            "dataset_text_field": self.config.get("dataset_text_field", "text"),
            "max_length": self.config["max_seq_length"],
            "dataset_num_proc": self.config.get("dataset_num_proc", 1),
            "packing": self._flag(self.config.get("packing"), default=False),
        }
        if self.config.get("run_name") or os.getenv("PRAISON_WANDB_RUN_NAME"):
            sft_params["run_name"] = self.config.get(
                "run_name", os.getenv("PRAISON_WANDB_RUN_NAME", "praisonai-train"))
        # Prefer max_steps if given; otherwise fall back to epochs (default 2800 steps
        # preserves the previous behaviour when neither is configured).
        if self.config.get("num_train_epochs") and not self.config.get("max_steps"):
            sft_params["num_train_epochs"] = self.config["num_train_epochs"]
        else:
            if not self.config.get("num_train_epochs") and not self.config.get("max_steps"):
                # Neither was set — the run silently defaults to 2800 steps, which is
                # rarely what a first-time user wants. Tell them how to control it.
                print("NOTE: neither num_train_epochs nor max_steps set; defaulting to "
                      "max_steps: 2800. Set num_train_epochs: 1-3 (or max_steps) to "
                      "control training length.")
            sft_params["max_steps"] = self.config.get("max_steps", 2800)
        # When both epochs and max_steps are set, max_steps silently wins — say so.
        if self.config.get("num_train_epochs") and self.config.get("max_steps"):
            print(f"DEBUG: both num_train_epochs and max_steps set; using "
                  f"max_steps={sft_params['max_steps']} (num_train_epochs ignored).")

        # --- Checkpointing (mid-run saves so a long/interrupted run isn't lost) ---
        save_strategy = self.config.get(
            "save_strategy", "steps" if self.config.get("save_steps") else "no")
        sft_params["save_strategy"] = save_strategy
        if save_strategy == "steps":
            sft_params["save_steps"] = int(self.config.get("save_steps", 100))
        if self.config.get("save_total_limit") is not None:
            sft_params["save_total_limit"] = int(self.config["save_total_limit"])
        sft_params["save_safetensors"] = self._flag(
            self.config.get("save_safetensors"), default=True)

        # --- Evaluation + best-checkpoint selection (only when an eval set exists) ---
        if eval_dataset is not None:
            eval_strategy = self.config.get(
                "eval_strategy", "steps" if self.config.get("eval_steps") else "epoch")
            sft_params["eval_strategy"] = eval_strategy
            if eval_strategy == "steps":
                sft_params["eval_steps"] = int(self.config.get("eval_steps", 100))
            sft_params["per_device_eval_batch_size"] = int(self.config.get(
                "per_device_eval_batch_size",
                self.config.get("per_device_train_batch_size", 2)))
            if self._flag(self.config.get("load_best_model_at_end"), default=False):
                sft_params["load_best_model_at_end"] = True
                sft_params["metric_for_best_model"] = self.config.get(
                    "metric_for_best_model", "eval_loss")
                sft_params["greater_is_better"] = self._flag(
                    self.config.get("greater_is_better"), default=False)
                # load_best_model_at_end requires save_strategy == eval_strategy AND
                # (for steps) save_steps to be a multiple of eval_steps. Reconcile
                # both so a valid-looking config can't crash the trainer.
                if sft_params.get("save_strategy", "no") != eval_strategy:
                    sft_params["save_strategy"] = eval_strategy
                    if eval_strategy == "steps":
                        sft_params["save_steps"] = sft_params["eval_steps"]
                if eval_strategy == "steps" and sft_params.get("save_steps"):
                    ss, es = int(sft_params["save_steps"]), int(sft_params["eval_steps"])
                    if ss % es != 0:
                        # Align eval to the checkpoint cadence (preserves the user's
                        # checkpoint frequency, which matters most for crash recovery).
                        print(f"WARNING: load_best_model_at_end needs save_steps a multiple "
                              f"of eval_steps; setting eval_steps={ss} to match save_steps.")
                        sft_params["eval_steps"] = ss

        # --- Extra optimization / DDP / hub knobs (only when set) ---
        if self.config.get("max_grad_norm") is not None:
            sft_params["max_grad_norm"] = float(self.config["max_grad_norm"])
        if self.config.get("warmup_ratio") is not None:
            sft_params["warmup_ratio"] = float(self.config["warmup_ratio"])
            sft_params.pop("warmup_steps", None)  # mutually exclusive with warmup_steps
        for k, cast in [("adam_beta1", float), ("adam_beta2", float),
                        ("adam_epsilon", float), ("neftune_noise_alpha", float),
                        ("dataloader_num_workers", int), ("data_seed", int)]:
            if self.config.get(k) is not None:
                sft_params[k] = cast(self.config[k])
        if self.config.get("group_by_length") is not None:
            sft_params["group_by_length"] = self._flag(self.config["group_by_length"])
        if self.config.get("lr_scheduler_kwargs") is not None:
            sft_params["lr_scheduler_kwargs"] = self.config["lr_scheduler_kwargs"]
        # DDP unused-parameter detection. Default True so multimodal / MoE / elastic
        # models (e.g. Gemma 4 E4B, whose vision/audio adapters don't fire in text-only
        # training) don't crash with "Expected to have finished reduction...". Set
        # false for a small speedup on pure dense-text models where all LoRA params
        # are used every step.
        if getattr(self, "_distributed", False):
            sft_params["ddp_find_unused_parameters"] = self._flag(
                self.config.get("ddp_find_unused_parameters"), default=True)
        # Push checkpoints to the Hub during training (optional).
        if self._flag(self.config.get("push_to_hub"), default=False):
            sft_params["push_to_hub"] = True
            sft_params["hub_model_id"] = self.config.get(
                "hub_model_id", self.config.get("hf_model_name"))
            sft_params["hub_strategy"] = self.config.get("hub_strategy", "every_save")
            if os.getenv("HF_TOKEN"):
                sft_params["hub_token"] = os.getenv("HF_TOKEN")
        # Response-only loss: compute loss only on the assistant's replies (better
        # instruction tuning). Default "auto" enables it whenever a masking route is
        # available -- TRL's assistant_only_loss when the template supports it, else
        # unsloth's turn-marker masking -- so beginners get the quality win with zero
        # risk of TRL's "no assistant tokens" crash. true/false force it.
        # `train_on_responses_only` is accepted as a familiar alias.
        # Two ways to mask, and the second is why this is not a one-liner.
        #
        # TRL's assistant_only_loss needs `{% generation %}` in the template.
        # None of unsloth's 43 templates have it, so on its own that setting
        # resolves to False for every template a user can pick -- and the run
        # trains on the prompt with no error. Unsloth's own
        # train_on_responses_only() masks by locating literal turn markers
        # instead and works on any template; it is applied to the built trainer
        # rather than through the config.
        self._response_markers = None
        self._masking_on = False

        # Response-only masking is an SFT-only mechanism: it rewrites the label
        # tensors of a completion-tokenised dataset. Preference trainers (DPO,
        # ORPO, KTO) build their own labels from chosen/rejected pairs, so both
        # masking routes are meaningless there and `train_on_responses_only`
        # would corrupt the run. Skip the whole decision for those methods.
        method = self.config.get("method", "sft")
        if method == "sft":
            markers = resolve_response_markers(
                self.config.get("chat_template"), self.config.get("model_name", ""))

            mask_setting = self.config.get(
                "assistant_only_loss", self.config.get("train_on_responses_only", "auto"))
            supports_mask = self._supports_assistant_mask()
            # `auto` means "mask if we can". Keying it off `supports_mask` alone sent
            # every unsloth template (which lacks {% generation %}) down the unmasked
            # path even when valid turn markers were available -- defeating the whole
            # fallback. Enable it when EITHER route is usable, and let decide_masking
            # pick which one.
            if isinstance(mask_setting, str) and mask_setting.strip().lower() == "auto":
                use_mask = supports_mask or bool(markers)
            else:
                use_mask = self._flag(mask_setting)
            route = decide_masking(use_mask, supports_mask, markers)
            if route == "assistant_only_loss":
                sft_params["assistant_only_loss"] = True
                self._masking_on = route
            elif route == "train_on_responses_only":
                self._response_markers = markers
                self._masking_on = route
            elif route is None:
                raise ValueError(
                    f"assistant_only_loss is enabled but neither masking route is "
                    f"available for '{self.config['model_name']}': the chat template has "
                    f"no {{% generation %}} markers, and no turn markers are known for it. "
                    f"Set assistant_only_loss: false to train on the full sequence, or "
                    f"choose a chat_template from: "
                    f"{', '.join(sorted(set(TEMPLATE_TO_MARKERS)))}."
                )

        # --- Early stopping (optional; needs an eval set) ---
        callbacks = []
        patience = self.config.get("early_stopping_patience")
        if patience:
            if eval_dataset is None:
                raise ValueError(
                    "early_stopping_patience requires an eval set — set val_split_ratio.")
            from transformers import EarlyStoppingCallback
            callbacks.append(EarlyStoppingCallback(
                early_stopping_patience=int(patience),
                early_stopping_threshold=float(self.config.get("early_stopping_threshold", 0.0))))
            sft_params.setdefault("load_best_model_at_end", True)
            sft_params.setdefault("metric_for_best_model", "eval_loss")
            # Early stopping turns on load_best_model_at_end AFTER the eval block above
            # ran, so the save/eval-strategy alignment may not have happened yet. The
            # Trainer requires save_strategy == eval_strategy when loading the best
            # model, so re-align here (default eval "epoch"; force matching saves).
            if sft_params.get("load_best_model_at_end"):
                eval_strategy = sft_params.get("eval_strategy", "epoch")
                sft_params["eval_strategy"] = eval_strategy
                if sft_params.get("save_strategy", "no") != eval_strategy:
                    sft_params["save_strategy"] = eval_strategy
                    if eval_strategy == "steps":
                        sft_params["save_steps"] = sft_params.get(
                            "eval_steps", int(self.config.get("eval_steps", 100)))

        # --- Advanced escape hatch: pass any raw SFTConfig field through verbatim ---
        passthrough = self.config.get("training_arguments") or {}
        if not isinstance(passthrough, dict):
            raise ValueError("config 'training_arguments' must be a mapping of SFTConfig fields.")
        sft_params.update(passthrough)  # user-supplied wins

        # Final safety net: the passthrough escape hatch can enable/override
        # load_best_model_at_end (or the step cadence) after the blocks above ran, so
        # re-check the Trainer's invariant here — save_strategy must equal eval_strategy
        # and (for steps) save_steps must be a multiple of eval_steps — no matter which
        # path turned load_best_model_at_end on.
        if sft_params.get("load_best_model_at_end"):
            eval_strategy = sft_params.get("eval_strategy", "epoch")
            sft_params["eval_strategy"] = eval_strategy
            if sft_params.get("save_strategy", "no") != eval_strategy:
                sft_params["save_strategy"] = eval_strategy
            if eval_strategy == "steps":
                es = int(sft_params.get("eval_steps", 100))
                ss = int(sft_params.get("save_steps", es))
                if ss % es != 0:
                    # Align eval to the checkpoint cadence (preserves the user's
                    # checkpoint frequency, which matters most for crash recovery).
                    print(f"WARNING: load_best_model_at_end needs save_steps a multiple "
                          f"of eval_steps; setting eval_steps={ss} to match save_steps.")
                    es = ss
                sft_params["save_steps"] = ss
                sft_params["eval_steps"] = es

        # Drop any field the installed TRL/Transformers SFTConfig doesn't accept, so
        # version differences (e.g. save_safetensors/group_by_length come and go) warn
        # instead of crashing the run.
        import dataclasses
        valid_fields = {f.name for f in dataclasses.fields(SFTConfig)}
        dropped = sorted(k for k in sft_params if k not in valid_fields)
        if dropped:
            print(f"WARNING: SFTConfig (this TRL version) does not accept {dropped}; ignoring.")
            sft_params = {k: v for k, v in sft_params.items() if k in valid_fields}

        spec = TRAINING_METHODS[method]

        if method != "sft":
            # SFT-only fields are not on a preference config and would be
            # rejected; the shared TrainingArguments fields are.
            for only_sft in ("dataset_text_field", "packing", "dataset_num_proc"):
                sft_params.pop(only_sft, None)
            sft_params["max_length"] = self.config["max_seq_length"]
            sft_params["max_prompt_length"] = int(self.config.get(
                "max_prompt_length", self.config["max_seq_length"] // 2))
            if self.config.get("beta") is not None:
                sft_params["beta"] = float(self.config["beta"])
            if method == "kto":
                for w in ("desirable_weight", "undesirable_weight"):
                    if self.config.get(w) is not None:
                        sft_params[w] = float(self.config[w])
            self._require_columns(raw_dataset, spec["columns"], method)

        cfg_cls = globals().get(spec["config"])
        trainer_cls = globals().get(spec["trainer"])
        if cfg_cls is None or trainer_cls is None:
            raise RuntimeError(
                f"method '{method}' needs {spec['trainer']} and {spec['config']} from TRL, "
                f"which this TRL version does not provide. Upgrade trl, or use method: sft.")

        # The same drop-unknown-fields guard the SFT path uses: a preference
        # config is a different class with a different field set.
        valid = getattr(cfg_cls, "__dataclass_fields__", None)
        if valid:
            dropped = [k for k in sft_params if k not in valid]
            if dropped:
                print(f"WARNING: {spec['config']} does not accept "
                      f"{sorted(dropped)}; ignoring.")
                sft_params = {k: v for k, v in sft_params.items() if k in valid}

        training_args = cfg_cls(**sft_params)
        trainer_kwargs = {
            "model": self.model,
            "processing_class": self.hf_tokenizer,
            "train_dataset": raw_dataset,
            "eval_dataset": eval_dataset,
            "args": training_args,
            "callbacks": callbacks or None,
        }
        if spec["needs_ref_model"]:
            # None means "use the frozen base weights". With a PEFT adapter that
            # is exactly right, and it avoids a second full model in VRAM.
            trainer_kwargs["ref_model"] = None
        trainer = trainer_cls(**trainer_kwargs)

        if self._response_markers:
            # Applied to the trainer, not the config: this rewrites the label
            # tensors on the already-tokenised dataset.
            from unsloth.chat_templates import train_on_responses_only
            instruction_part, response_part = self._response_markers
            trainer = train_on_responses_only(
                trainer, instruction_part=instruction_part, response_part=response_part)
            print(f"DEBUG: masking prompt tokens via train_on_responses_only "
                  f"(instruction={instruction_part!r}, response={response_part!r})")
        final_dir = self.config.get("final_model_dir", "lora_model")
        # One clear summary of what will run — so people and agents can confirm the
        # config resolved as intended without reading the DEBUG noise.
        steps = sft_params.get("max_steps", f"{sft_params.get('num_train_epochs', 1)} epoch(s)")
        gpus = int(os.environ.get("WORLD_SIZE", 1))
        gpu_str = f" × {gpus} GPUs" if gpus > 1 else ""
        eval_str = f"  (+{len(eval_dataset)} eval)" if eval_dataset is not None else ""
        ckpt_str = sft_params["save_strategy"]
        if sft_params["save_strategy"] == "steps":
            ckpt_str += f" @ {sft_params.get('save_steps')} steps"
        print(
            "\n──────────── PraisonAI Train ────────────\n"
            f"  Model:       {self.config['model_name']}\n"
            f"  Examples:    {len(raw_dataset)}{eval_str}\n"
            f"  Loss mask:   {_MASK_LABELS[self._masking_on]}\n"
            f"  Steps:       {steps}  ·  batch {sft_params['per_device_train_batch_size']}"
            f" × accum {sft_params['gradient_accumulation_steps']}{gpu_str}\n"
            f"  Checkpoints: {ckpt_str}  ·  Output: {final_dir}/\n"
            "─────────────────────────────────────────\n"
        )
        # Resume from a checkpoint. Accepts:
        #   true  -> auto-resume from the latest checkpoint in output_dir (crash-safe:
        #            if none exists yet, start fresh instead of erroring)
        #   a path -> resume from that specific checkpoint
        #   false -> fresh run
        # This makes recovery trivial: after any crash (OOM, GPU reclaim), just relaunch
        # the SAME command and training continues from the last saved step.
        resume = self.config.get("resume_from_checkpoint", False)
        # Normalize every boolean spelling _flag accepts (true/false/1/0/yes/no/on/off)
        # BEFORE treating a string as an explicit checkpoint path — so "1"/"yes" mean
        # "auto-resume", not a literal directory named "1".
        if isinstance(resume, str) and resume.strip().lower() in (
            "true", "false", "1", "0", "yes", "no", "on", "off"
        ):
            resume = self._flag(resume)
        if resume is True:
            import glob
            # Only real checkpoint dirs with a numeric suffix qualify — stray files or
            # dirs like "checkpoint-backup"/"checkpoint-incomplete" must not make the
            # auto-resume path fire (or crash the int() parse below).
            ckpts = [
                p for p in glob.glob(os.path.join(sft_params["output_dir"], "checkpoint-*"))
                if os.path.isdir(p) and p.rsplit("-", 1)[-1].isdigit()
            ]
            if ckpts:
                latest = max(ckpts, key=lambda p: int(p.rsplit("-", 1)[-1]))
                # Pass the validated path directly rather than leaving resume=True and
                # letting the trainer redo (and possibly mis-parse) its own discovery.
                resume = latest
                print(f"DEBUG: auto-resume from latest checkpoint: {latest}")
            else:
                print("DEBUG: resume_from_checkpoint=true but no checkpoint yet; starting fresh.")
                resume = False
        print("DEBUG: Beginning trainer.train() ...")
        trainer.train(resume_from_checkpoint=resume if resume else None)
        # Under DDP only rank 0 writes the final adapter (avoid a write race).
        if int(os.environ.get("RANK", os.environ.get("LOCAL_RANK", 0))) == 0:
            print("DEBUG: Training complete. Saving model and tokenizer locally...")
            self.model.save_pretrained(final_dir)
            self.hf_tokenizer.save_pretrained(final_dir)
            print(f"DEBUG: Saved model and tokenizer to '{final_dir}'.")

    def inference(self, instruction, input_text):
        FastLanguageModel.for_inference(self.model)
        messages = [{"role": "user", "content": f"{instruction}\n\nInput: {input_text}"}]
        inputs = self.hf_tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(self.device)
        outputs = self.model.generate(
            input_ids=inputs,
            max_new_tokens=64,
            use_cache=True,
            temperature=1.5,
            min_p=0.1
        )
        print("DEBUG: Inference output:", self.hf_tokenizer.batch_decode(outputs))

    def load_model(self):
        from unsloth import FastLanguageModel
        # Reload with the SAME precision/quantization the model was trained under,
        # otherwise an 8-bit (or full-precision) model gets reloaded in 4-bit — a
        # different memory footprint that can OOM or silently change behaviour.
        dtype_cfg = self.config.get("dtype")
        load_kwargs = dict(
            model_name=self.config.get("final_model_dir", "lora_model"),
            max_seq_length=self.config.get("max_seq_length", 2048),
            dtype=getattr(torch, dtype_cfg) if isinstance(dtype_cfg, str) else None,
            load_in_4bit=self._flag(self.config.get("load_in_4bit"), default=True),
        )
        if self.config.get("load_in_8bit") is not None:
            load_kwargs["load_in_8bit"] = self._flag(self.config["load_in_8bit"])
            if load_kwargs["load_in_8bit"]:
                load_kwargs["load_in_4bit"] = False
        if self.config.get("full_finetuning") is not None:
            load_kwargs["full_finetuning"] = self._flag(self.config["full_finetuning"])
        model, tokenizer = FastLanguageModel.from_pretrained(**load_kwargs)
        return model, tokenizer

    @staticmethod
    def _raise_hf_push_error(exc, repo):
        """Translate a Hugging Face Hub HTTP error into an actionable message."""
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 401:
            raise RuntimeError(
                "Hugging Face rejected the token (401). It is invalid or expired — "
                "run `huggingface-cli login` or `export HF_TOKEN=hf_...` with a valid "
                "write token."
            ) from exc
        if status == 403:
            raise RuntimeError(
                f"No write access to '{repo}' (403). The repo must be under your own "
                f"username and the token must have write scope. Set hf_model_name to "
                f"'<your-username>/<name>'."
            ) from exc
        raise RuntimeError(f"Hugging Face upload to '{repo}' failed: {exc}") from exc

    def _clean_local_repo_dir(self):
        """Remove a stale LOCAL output dir before an export — but only when
        hf_model_name is a plain local directory name, never a namespaced Hub repo
        id like 'user/model' (which must not be interpreted as a path to delete)."""
        name = self.config["hf_model_name"]
        if "/" not in name.strip("/") and os.path.isdir(name):
            shutil.rmtree(name)

    def hub_push_kwargs(self):
        """Options shared by every Hub push. See praisonai_train/_hub.py."""
        from praisonai_train._hub import hub_push_kwargs
        return hub_push_kwargs(self.config, flag=self._flag)

    def save_model_merged(self):
        from huggingface_hub.utils import HfHubHTTPError
        repo = self.config["hf_model_name"]
        self._clean_local_repo_dir()
        try:
            self.model.push_to_hub_merged(
                repo,
                self.hf_tokenizer,
                save_method=self.config.get("save_method", "merged_16bit"),
                **self.hub_push_kwargs()
            )
        except HfHubHTTPError as exc:
            self._raise_hf_push_error(exc, repo)

    def push_model_gguf(self):
        from huggingface_hub.utils import HfHubHTTPError
        repo = self.config["hf_model_name"]
        try:
            self.model.push_to_hub_gguf(
                repo,
                self.hf_tokenizer,
                quantization_method=self.config.get("quantization_method", "q4_k_m"),
                **self.hub_push_kwargs()
            )
        except HfHubHTTPError as exc:
            self._raise_hf_push_error(exc, repo)

    def save_model_gguf(self):
        self.model.save_pretrained_gguf(
            self.config["hf_model_name"],
            self.hf_tokenizer,
            quantization_method=self.config.get("quantization_method", "q4_k_m"),
        )

    def prepare_modelfile_content(self):
        output_model = self.config["hf_model_name"]
        model_name = self.config["model_name"].lower()
        # Mapping from model name keywords to their default TEMPLATE and stop tokens (and optional SYSTEM/num_ctx)
        mapping = {
            "llama": {
                "template": """<|start_header_id|>system<|end_header_id|>
    Cutting Knowledge Date: December 2023
    {{ if .System }}{{ .System }}
    {{- end }}
    {{- if .Tools }}When you receive a tool call response, use the output to format an answer to the original user question.
    You are a helpful assistant with tool calling capabilities.
    {{- end }}<|eot_id|>
    {{- range $i, $_ := .Messages }}
    {{- $last := eq (len (slice $.Messages $i)) 1 }}
    {{- if eq .Role "user" }}<|start_header_id|>user<|end_header_id|>
    {{- if and $.Tools $last }}
    Given the following functions, please respond with a JSON for a function call with its proper arguments that best answers the given prompt.
    Respond in the format {"name": function name, "parameters": dictionary of argument name and its value}. Do not use variables.
    {{ range $.Tools }}
    {{- . }}
    {{ end }}
    {{ .Content }}<|eot_id|>
    {{- else }}
    {{ .Content }}<|eot_id|>
    {{- end }}{{ if $last }}<|start_header_id|>assistant<|end_header_id|>
    {{ end }}
    {{- else if eq .Role "assistant" }}<|start_header_id|>assistant<|end_header_id|>
    {{- if .ToolCalls }}
    {{ range .ToolCalls }}
    {"name": "{{ .Function.Name }}", "parameters": {{ .Function.Arguments }}}{{ end }}
    {{- else }}
    {{ .Content }}
    {{- end }}{{ if not $last }}<|eot_id|>{{ end }}
    {{- else if eq .Role "tool" }}<|start_header_id|>ipython<|end_header_id|>
    {{ .Content }}<|eot_id|>{{ if $last }}<|start_header_id|>assistant<|end_header_id|>
    {{ end }}
    {{- end }}
    {{- end }}""",
                "stop_tokens": ["<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>"]
            },
            "qwen": {
                "template": """{{- if .Suffix }}<|fim_prefix|>{{ .Prompt }}<|fim_suffix|>{{ .Suffix }}<|fim_middle|>
    {{- else if .Messages }}
    {{- if or .System .Tools }}<|im_start|>system
    {{- if .System }}
    {{ .System }}
    {{- end }}
    {{- if .Tools }}
    # Tools
    You may call one or more functions to assist with the user query.
    You are provided with function signatures within <tools></tools> XML tags:
    <tools>
    {{- range .Tools }}
    {"type": "function", "function": {{ .Function }}}
    {{- end }}
    </tools>
    For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
    <tool_call>
    {"name": <function-name>, "arguments": <args-json-object>}
    </tool_call>
    {{- end }}<|im_end|>
    {{ end }}
    {{- range $i, $_ := .Messages }}
    {{- $last := eq (len (slice $.Messages $i)) 1 -}}
    {{- if eq .Role "user" }}<|im_start|>user
    {{ .Content }}<|im_end|>
    {{ else if eq .Role "assistant" }}<|im_start|>assistant
    {{ if .Content }}{{ .Content }}
    {{- else if .ToolCalls }}<tool_call>
    {{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
    {{ end }}</tool_call>
    {{- end }}{{ if not $last }}<|im_end|>
    {{ end }}
    {{- else if eq .Role "tool" }}<|im_start|>user
    <tool_response>
    {{ .Content }}
    </tool_response><|im_end|>
    {{ end }}
    {{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
    {{ end }}
    {{- end }}
    {{- else }}
    {{- if .System }}<|im_start|>system
    {{ .System }}<|im_end|>
    {{ end }}{{ if .Prompt }}<|im_start|>user
    {{ .Prompt }}<|im_end|>
    {{ end }}<|im_start|>assistant
    {{ end }}{{ .Response }}{{ if .Response }}<|im_end|>{{ end }}""",
                "system": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.",
                "num_ctx": 32768,
                "stop_tokens": ["<|endoftext|>"]
            },
            "mistral": {
                "template": "[INST] {{ if .System }}{{ .System }} {{ end }}{{ .Prompt }} [/INST]",
                "stop_tokens": ["[INST]", "[/INST]"]
            },
            "phi": {
                "template": """{{- range $i, $_ := .Messages }}
    {{- $last := eq (len (slice $.Messages $i)) 1 -}}
    <|im_start|>{{ .Role }}<|im_sep|>
    {{ .Content }}{{ if not $last }}<|im_end|>
    {{ end }}
    {{- if and (ne .Role "assistant") $last }}<|im_end|>
    <|im_start|>assistant<|im_sep|>
    {{ end }}
    {{- end }}""",
                "stop_tokens": ["<|im_start|>", "<|im_end|>", "<|im_sep|>"]
            },
            "deepseek": {
                "template": """{{- if .System }}{{ .System }}{{ end }}
    {{- range $i, $_ := .Messages }}
    {{- $last := eq (len (slice $.Messages $i)) 1}}
    {{- if eq .Role "user" }}
    {{ .Content }}
    {{- else if eq .Role "assistant" }}
    {{ .Content }}{{- if not $last }}
    {{- end }}
    {{- end }}
    {{- if and $last (ne .Role "assistant") }}
    {{ end }}
    {{- end }}""",
                # DeepSeek's end-of-sequence marker. Previously this was four empty
                # strings, which emitted broken `PARAMETER stop` lines (no value).
                "stop_tokens": ["<｜end▁of▁sentence｜>"]
            },
            "llava": {
                "template": """{{- if .Suffix }}<|fim_prefix|>{{ .Prompt }}<|fim_suffix|>{{ .Suffix }}<|fim_middle|>
    {{- else if .Messages }}
    {{- if or .System .Tools }}<|im_start|>system
    {{- if .System }}
    {{ .System }}
    {{- end }}
    {{- if .Tools }}
    # Tools
    You may call one or more functions to assist with the user query.
    You are provided with function signatures within <tools></tools> XML tags:
    <tools>
    {{- range .Tools }}
    {"type": "function", "function": {{ .Function }}}
    {{- end }}
    </tools>
    For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
    <tool_call>
    {"name": <function-name>, "arguments": <args-json-object>}
    </tool_call>
    {{- end }}<|im_end|>
    {{ end }}
    {{- range $i, $_ := .Messages }}
    {{- $last := eq (len (slice $.Messages $i)) 1 -}}
    {{- if eq .Role "user" }}<|im_start|>user
    {{ .Content }}<|im_end|>
    {{ else if eq .Role "assistant" }}<|im_start|>assistant
    {{ if .Content }}{{ .Content }}
    {{- else if .ToolCalls }}<tool_call>
    {{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
    {{ end }}</tool_call>
    {{- end }}{{ if not $last }}<|im_end|>
    {{ end }}
    {{- else if eq .Role "tool" }}<|im_start|>user
    <tool_response>
    {{ .Content }}
    </tool_response><|im_end|>
    {{ end }}
    {{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
    {{ end }}
    {{- end }}
    {{- else }}
    {{- if .System }}<|im_start|>system
    {{ .System }}<|im_end|>
    {{ end }}{{ if .Prompt }}<|im_start|>user
    {{ .Prompt }}<|im_end|>
    {{ end }}<|im_start|>assistant
    {{ end }}{{ .Response }}{{ if .Response }}<|im_end|>{{ end }}""",
                "stop_tokens": ["</s>", "USER:", "ASSSISTANT:"]
            },
            "gemma": {
                # Gemma uses <start_of_turn>/<end_of_turn> and has no system role;
                # the system prompt is folded into the first user turn (per the
                # Gemma chat template spec) rather than emitted as a separate turn.
                "template": """<start_of_turn>user
    {{ if .System }}{{ .System }}
    {{ end }}{{ .Prompt }}<end_of_turn>
    <start_of_turn>model
    {{ .Response }}<end_of_turn>
    """,
                "stop_tokens": ["<end_of_turn>", "<start_of_turn>"]
            }
        }
        # Select mapping by checking if any key is in the model_name.
        chosen = None
        for key, settings in mapping.items():
            if key in model_name:
                chosen = settings
                break
        if chosen is None:
            # No known family matched the model name — the generic Llama-style
            # template below may format prompts or stop tokens incorrectly for this
            # model. Warn so a garbled Ollama model isn't a silent surprise.
            print(f"WARNING: no known chat template matched model '{model_name}'; "
                  f"using a generic template — stop tokens may be wrong. Verify the "
                  f"Ollama output, or set model_name to a recognized family "
                  f"(llama/qwen/gemma/mistral/phi/deepseek).")
            # Fallback default
            chosen = {
                "template": """{{ if .System }}<|start_header_id|>system<|end_header_id|>
    {{ .System }}<|eot_id|>{{ end }}{{ if .Prompt }}<|start_header_id|>user<|end_header_id|>
    {{ .Prompt }}<|eot_id|>{{ end }}<|start_header_id|>assistant<|end_header_id|>
    {{ .Response }}<|eot_id|>""",
                "stop_tokens": ["<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>"]
            }
        # Build the stop parameter lines. Skip empty/whitespace tokens so we never
        # emit a broken `PARAMETER stop` line with no value.
        stop_params = "\n".join(
            f"PARAMETER stop {token}"
            for token in chosen["stop_tokens"]
            if str(token).strip()
        )
        # Optionally include a SYSTEM line and num_ctx if defined in the mapping.
        system_line = ""
        if "system" in chosen:
            system_line = f"SYSTEM {chosen['system']}\n"
        num_ctx_line = ""
        if "num_ctx" in chosen:
            num_ctx_line = f"PARAMETER num_ctx {chosen['num_ctx']}\n"
        # The template literals above are written at source indentation, so every
        # continuation line carries a leading four spaces that would otherwise be
        # baked into the served TEMPLATE (e.g. "\n    <start_of_turn>model"). That
        # tokenizes differently from training and degrades a correct fine-tune, so
        # strip the common leading indent from the template before embedding it.
        # `dedent` needs a uniform indent, but the first line (right after `"""`)
        # has none — normalise by indenting the first line, dedenting, then
        # restoring it.
        template = textwrap.dedent("    " + chosen["template"])
        # Assemble and return the modelfile content at column 0.
        return (
            f"FROM {output_model}\n"
            f'TEMPLATE """{template}"""\n'
            f"{system_line}{num_ctx_line}{stop_params}\n"
        )

    def create_and_push_ollama_model(self):
        from .._ollama import create_and_push_ollama_model
        modelfile_content = self.prepare_modelfile_content()
        # Pass the configured quantization so `ollama create` quantizes on the way in
        # (an unquantized f16 model can be many GB larger). None -> no --quantize.
        create_and_push_ollama_model(
            self.config['ollama_model'],
            self.config.get('model_parameters', 'latest'),
            modelfile_content,
            quantization=self.config.get('quantization_method'),
        )

    def run(self):
        self.print_system_info()
        self.check_gpu()
        self.check_ram()
        if self._flag(self.config.get("train"), default=True):
            self.prepare_model()
            self.train_model()
        if self.model is None:
            # Training was disabled (train: false) so no model was loaded. Skip
            # publishing rather than crashing with an AttributeError on None.
            print("DEBUG: Training skipped (train: false); no model to publish.")
            return
        # Under DDP only the main process (rank 0) should merge/push — otherwise every
        # rank races to write the same HF/Ollama repo.
        if int(os.environ.get("RANK", os.environ.get("LOCAL_RANK", 0))) != 0:
            print("DEBUG: non-main rank; skipping publish.")
            return
        # Publishing defaults OFF and is skipped unless a target is set — so a plain
        # "train locally" config finishes with the LoRA saved to lora_model/ instead
        # of crashing on a missing repo name or pushing to someone else's account.
        if self._flag(self.config.get("huggingface_save")) and self.config.get("hf_model_name"):
            self.save_model_merged()
        if self._flag(self.config.get("huggingface_save_gguf")) and self.config.get("hf_model_name"):
            self.push_model_gguf()
        if self._flag(self.config.get("ollama_save")) and self.config.get("ollama_model"):
            self.create_and_push_ollama_model()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PraisonAI Training Script")
    parser.add_argument("command", choices=["train"], help="Command to execute")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    parser.add_argument("--model", type=str, help="Model name")
    parser.add_argument("--hf", type=str, help="Hugging Face model name")
    parser.add_argument("--ollama", type=str, help="Ollama model name")
    parser.add_argument("--dataset", type=str, help="Dataset name for training")
    args = parser.parse_args()

    if args.command == "train":
        # Wrap construction + run so config/preflight/runtime errors reach a
        # non-developer as a single clean line, not a scary traceback. ValueError /
        # RuntimeError are the "expected, actionable" failures we raise deliberately;
        # anything else (a real bug) re-raises with its full traceback.
        try:
            trainer_obj = TrainModel(config_path=args.config)
            trainer_obj.run()
        except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
            # OutOfMemoryError is a RuntimeError, so without this the user got
            # torch's allocator dump as one ERROR line and no idea what to change.
            if is_out_of_memory(exc):
                print(f"\nERROR: {exc}\n\n{OOM_REMEDIATION}\n", file=sys.stderr)
            else:
                print(f"\nERROR: {exc}\n", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            sys.exit(130)

if __name__ == "__main__":
    main()
