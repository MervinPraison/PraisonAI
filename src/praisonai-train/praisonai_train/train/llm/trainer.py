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
import subprocess
from functools import partial


def _lazy_import_training_deps():
    """Import heavy training dependencies only when needed."""
    try:
        import torch
        from transformers import TextStreamer, TrainingArguments
        from unsloth import FastLanguageModel, is_bfloat16_supported
        from unsloth.chat_templates import standardize_sharegpt, get_chat_template
        from trl import SFTTrainer, SFTConfig
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
    _dbg = os.environ.get("PRAISON_DEBUG")
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
    })

    def validate_config(self):
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
        for key in self.config:
            if key not in self.KNOWN_KEYS:
                print(f"WARNING: ignoring unknown config key '{key}' (typo, or not supported).")

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
        print("DEBUG: Dataset columns:", dataset.column_names)
        if "conversations" in dataset.column_names:
            print("DEBUG: Standardizing dataset (ShareGPT style)...")
            dataset = standardize_sharegpt(dataset)
        else:
            print("DEBUG: Dataset does not have 'conversations'; assuming Alpaca format.")
        if self._flag(dataset_info.get("shuffle"), default=False):
            dataset = dataset.shuffle(
                seed=int(dataset_info.get("seed", self.config.get("seed", 3407))))
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
            print("DEBUG: Processing dataset info:", dataset_info)
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
            sft_params["max_steps"] = self.config.get("max_steps", 2800)

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
        # instruction tuning). Default "auto" enables it only when the model's chat
        # template actually supports masking, so beginners get the quality win with
        # zero risk of TRL's "no assistant tokens" crash. true/false force it.
        # `train_on_responses_only` is accepted as a familiar alias.
        mask_setting = self.config.get(
            "assistant_only_loss", self.config.get("train_on_responses_only", "auto"))
        supports_mask = self._supports_assistant_mask()
        if isinstance(mask_setting, str) and mask_setting.strip().lower() == "auto":
            use_mask = supports_mask
        else:
            use_mask = self._flag(mask_setting)
        if use_mask and not supports_mask:
            raise ValueError(
                f"assistant_only_loss is enabled but the chat template for "
                f"'{self.config['model_name']}' has no assistant-turn markers "
                f"({{% generation %}}). Set assistant_only_loss: auto (recommended) or "
                f"false, or use a chat_template that supports masking."
            )
        if use_mask:
            sft_params["assistant_only_loss"] = True
        self._masking_on = use_mask

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

        # Drop any field the installed TRL/Transformers SFTConfig doesn't accept, so
        # version differences (e.g. save_safetensors/group_by_length come and go) warn
        # instead of crashing the run.
        import dataclasses
        valid_fields = {f.name for f in dataclasses.fields(SFTConfig)}
        dropped = sorted(k for k in sft_params if k not in valid_fields)
        if dropped:
            print(f"WARNING: SFTConfig (this TRL version) does not accept {dropped}; ignoring.")
            sft_params = {k: v for k, v in sft_params.items() if k in valid_fields}

        training_args = SFTConfig(**sft_params)
        trainer = SFTTrainer(
            model=self.model,
            processing_class=self.hf_tokenizer,
            train_dataset=raw_dataset,
            eval_dataset=eval_dataset,
            args=training_args,
            callbacks=callbacks or None,
        )
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
            f"  Loss mask:   {'assistant replies only' if self._masking_on else 'full sequence'}\n"
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
        if isinstance(resume, str) and resume.strip().lower() in ("true", "false"):
            resume = self._flag(resume)
        if resume is True:
            import glob
            ckpts = glob.glob(os.path.join(sft_params["output_dir"], "checkpoint-*"))
            if ckpts:
                latest = max(ckpts, key=lambda p: int(p.rsplit("-", 1)[-1])
                             if p.rsplit("-", 1)[-1].isdigit() else -1)
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

    def save_model_merged(self):
        if os.path.exists(self.config["hf_model_name"]):
            shutil.rmtree(self.config["hf_model_name"])
        self.model.push_to_hub_merged(
            self.config["hf_model_name"],
            self.hf_tokenizer,
            save_method="merged_16bit",
            token=os.getenv("HF_TOKEN")
        )

    def push_model_gguf(self):
        self.model.push_to_hub_gguf(
            self.config["hf_model_name"],
            self.hf_tokenizer,
            quantization_method=self.config["quantization_method"],
            token=os.getenv("HF_TOKEN")
        )

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
                "stop_tokens": ["", "", "", ""]
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
            # Fallback default
            chosen = {
                "template": """{{ if .System }}<|start_header_id|>system<|end_header_id|>
    {{ .System }}<|eot_id|>{{ end }}{{ if .Prompt }}<|start_header_id|>user<|end_header_id|>
    {{ .Prompt }}<|eot_id|>{{ end }}<|start_header_id|>assistant<|end_header_id|>
    {{ .Response }}<|eot_id|>""",
                "stop_tokens": ["<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>"]
            }
        # Build the stop parameter lines.
        stop_params = "\n".join([f"PARAMETER stop {token}" for token in chosen["stop_tokens"]])
        # Optionally include a SYSTEM line and num_ctx if defined in the mapping.
        system_line = ""
        if "system" in chosen:
            system_line = f"SYSTEM {chosen['system']}\n"
        num_ctx_line = ""
        if "num_ctx" in chosen:
            num_ctx_line = f"PARAMETER num_ctx {chosen['num_ctx']}\n"
        # Assemble and return the modelfile content.
        return f"""FROM {output_model}
    TEMPLATE \"\"\"{chosen['template']}\"\"\"
    {system_line}{num_ctx_line}{stop_params}
    """

    def create_and_push_ollama_model(self):
        from .._ollama import create_and_push_ollama_model
        modelfile_content = self.prepare_modelfile_content()
        create_and_push_ollama_model(
            self.config['ollama_model'], 
            self.config['model_parameters'], 
            modelfile_content
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
        trainer_obj = TrainModel(config_path=args.config)
        trainer_obj.run()

if __name__ == "__main__":
    main()
