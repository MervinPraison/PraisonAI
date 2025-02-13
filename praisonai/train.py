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
import torch
import shutil
import subprocess
from transformers import TextStreamer
from unsloth import FastLanguageModel, is_bfloat16_supported
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset, concatenate_datasets
from psutil import virtual_memory
from unsloth.chat_templates import standardize_sharegpt, get_chat_template
from functools import partial

#####################################
# Step 1: Formatting Raw Conversations
#####################################
def formatting_prompts_func(examples, tokenizer):
    """
    Converts each example's conversation into a single plain-text prompt.
    If the example has a "conversations" field, process it as ShareGPT-style.
    Otherwise, assume Alpaca-style data with "instruction", "input", and "output" fields.
    """
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
    if texts:
        print("DEBUG: Raw texts sample (first 200 chars):", texts[0][:200])
    return {"text": texts}

#####################################
# Step 2: Tokenizing the Prompts
#####################################
def tokenize_function(examples, hf_tokenizer, max_length):
    """
    Tokenizes a batch of text prompts with padding and truncation enabled.
    """
    flat_texts = []
    for t in examples["text"]:
        if isinstance(t, list):
            t = t[0] if len(t) == 1 else " ".join(t)
        flat_texts.append(t)
    print("DEBUG: Tokenizing a batch of size:", len(flat_texts))
    tokenized = hf_tokenizer(
        flat_texts,
        padding="max_length",
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    tokenized = {key: value.tolist() for key, value in tokenized.items()}
    sample_key = list(tokenized.keys())[0]
    print("DEBUG: Tokenized sample (first 10 tokens of", sample_key, "):", tokenized[sample_key][0][:10])
    return tokenized

#####################################
# Main Training Class
#####################################
class TrainModel:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.hf_tokenizer = None   # The underlying HF tokenizer
        self.chat_tokenizer = None # Chat wrapper for formatting

    def load_config(self, path):
        with open(path, "r") as file:
            self.config = yaml.safe_load(file)
        print("DEBUG: Loaded config:", self.config)

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
        self.model, original_tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.config["model_name"],
            max_seq_length=self.config["max_seq_length"],
            dtype=None,
            load_in_4bit=self.config["load_in_4bit"],
        )
        print("DEBUG: Model and original tokenizer loaded.")
        if original_tokenizer.pad_token is None:
            original_tokenizer.pad_token = original_tokenizer.eos_token
        original_tokenizer.model_max_length = self.config["max_seq_length"]
        self.chat_tokenizer = get_chat_template(original_tokenizer, chat_template="llama-3.1")
        self.hf_tokenizer = original_tokenizer
        print("DEBUG: Chat tokenizer created; HF tokenizer saved.")
        self.model = FastLanguageModel.get_peft_model(
            self.model,
            r=16,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            lora_alpha=16,
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=3407,
            use_rslora=False,
            loftq_config=None,
        )
        print("DEBUG: LoRA adapters added.")

    def process_dataset(self, dataset_info):
        dataset_name = dataset_info["name"]
        split_type = dataset_info.get("split_type", "train")
        print(f"DEBUG: Loading dataset '{dataset_name}' split '{split_type}'...")
        dataset = load_dataset(dataset_name, split=split_type)
        print("DEBUG: Dataset columns:", dataset.column_names)
        if "conversations" in dataset.column_names:
            print("DEBUG: Standardizing dataset (ShareGPT style)...")
            dataset = standardize_sharegpt(dataset)
        else:
            print("DEBUG: Dataset does not have 'conversations'; assuming Alpaca format.")
        print("DEBUG: Applying formatting function to dataset...")
        format_func = partial(formatting_prompts_func, tokenizer=self.chat_tokenizer)
        dataset = dataset.map(format_func, batched=True, remove_columns=dataset.column_names)
        sample = dataset[0]
        print("DEBUG: Sample processed example keys:", list(sample.keys()))
        if "text" in sample:
            print("DEBUG: Sample processed 'text' type:", type(sample["text"]))
            print("DEBUG: Sample processed 'text' content (first 200 chars):", sample["text"][:200])
        else:
            print("DEBUG: Processed sample does not contain 'text'.")
        return dataset

    def tokenize_dataset(self, dataset):
        print("DEBUG: Tokenizing the entire dataset...")
        tokenized_dataset = dataset.map(
            lambda examples: tokenize_function(examples, self.hf_tokenizer, self.config["max_seq_length"]),
            batched=True
        )
        tokenized_dataset = tokenized_dataset.remove_columns(["text"])
        print("DEBUG: Tokenized dataset sample keys:", tokenized_dataset[0].keys())
        return tokenized_dataset

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
        raw_dataset = self.load_datasets()
        tokenized_dataset = self.tokenize_dataset(raw_dataset)
        print("DEBUG: Dataset tokenization complete.")
        # Build the training arguments parameters dynamically
        ta_params = {
            "per_device_train_batch_size": self.config.get("per_device_train_batch_size", 2),
            "gradient_accumulation_steps": self.config.get("gradient_accumulation_steps", 2),
            "warmup_steps": self.config.get("warmup_steps", 50),
            "max_steps": self.config.get("max_steps", 2800),
            "learning_rate": self.config.get("learning_rate", 2e-4),
            "fp16": self.config.get("fp16", not is_bfloat16_supported()),
            "bf16": self.config.get("bf16", is_bfloat16_supported()),
            "logging_steps": self.config.get("logging_steps", 15),
            "optim": self.config.get("optim", "adamw_8bit"),
            "weight_decay": self.config.get("weight_decay", 0.01),
            "lr_scheduler_type": self.config.get("lr_scheduler_type", "linear"),
            "seed": self.config.get("seed", 3407),
            "output_dir": self.config.get("output_dir", "outputs"),
            "report_to": "none" if not os.getenv("PRAISON_WANDB") else "wandb",
            "remove_unused_columns": self.config.get("remove_unused_columns", False)
        }
        if os.getenv("PRAISON_WANDB"):
            ta_params["save_steps"] = self.config.get("save_steps", 100)
            ta_params["run_name"] = os.getenv("PRAISON_WANDB_RUN_NAME", "praisonai-train")

        training_args = TrainingArguments(**ta_params)
        # Since the dataset is pre-tokenized, we supply a dummy dataset_text_field.
        trainer = SFTTrainer(
            model=self.model,
            tokenizer=self.hf_tokenizer,
            train_dataset=tokenized_dataset,
            dataset_text_field="input_ids",  # Dummy field since data is numeric
            max_seq_length=self.config["max_seq_length"],
            dataset_num_proc=1,  # Use a single process to avoid pickling issues
            packing=False,
            args=training_args,
        )
        from unsloth.chat_templates import train_on_responses_only
        trainer = train_on_responses_only(
            trainer,
            instruction_part="<|start_header_id|>user<|end_header_id|>\n\n",
            response_part="<|start_header_id|>assistant<|end_header_id|>\n\n",
        )
        print("DEBUG: Beginning trainer.train() ...")
        trainer.train()
        print("DEBUG: Training complete. Saving model and tokenizer locally...")
        self.model.save_pretrained("lora_model")
        self.hf_tokenizer.save_pretrained("lora_model")
        print("DEBUG: Saved model and tokenizer to 'lora_model'.")

    def inference(self, instruction, input_text):
        FastLanguageModel.for_inference(self.model)
        messages = [{"role": "user", "content": f"{instruction}\n\nInput: {input_text}"}]
        inputs = self.hf_tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to("cuda")
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
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.config["output_dir"],
            max_seq_length=2048,
            dtype=None,
            load_in_4bit=self.config["load_in_4bit"],
        )
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
            quantization_method="q4_k_m"
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
    {{- if .Tools }}When you receive a tool call response, use the output to format an answer to the orginal user question.
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
        modelfile_content = self.prepare_modelfile_content()
        with open("Modelfile", "w") as file:
            file.write(modelfile_content)
        subprocess.run(["ollama", "serve"])
        subprocess.run(["ollama", "create", f"{self.config['ollama_model']}:{self.config['model_parameters']}", "-f", "Modelfile"])
        subprocess.run(["ollama", "push", f"{self.config['ollama_model']}:{self.config['model_parameters']}"])

    def run(self):
        self.print_system_info()
        self.check_gpu()
        self.check_ram()
        if self.config.get("train", "true").lower() == "true":
            self.prepare_model()
            self.train_model()
        if self.config.get("huggingface_save", "true").lower() == "true":
            self.save_model_merged()
        if self.config.get("huggingface_save_gguf", "true").lower() == "true":
            self.push_model_gguf()
        if self.config.get("ollama_save", "true").lower() == "true":
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
