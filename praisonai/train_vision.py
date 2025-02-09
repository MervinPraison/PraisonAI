#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script finetunes a vision language model using Unsloth's fast training framework.
It supports vision tasks by converting raw image-caption samples into a conversation format, 
adding vision-specific LoRA adapters, and training using TRL's SFTTrainer with UnslothVisionDataCollator.
"""

import os
import sys
import yaml
import torch
import shutil
import subprocess

from datasets import load_dataset, concatenate_datasets
from unsloth import FastVisionModel, is_bf16_supported
from unsloth.trainer import UnslothVisionDataCollator
from trl import SFTTrainer, SFTConfig


class TrainVisionModel:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.hf_tokenizer = None  # The underlying tokenizer

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
        from psutil import virtual_memory
        ram_gb = virtual_memory().total / 1e9
        print(f"DEBUG: Your runtime has {ram_gb:.1f} gigabytes of available RAM")
        if ram_gb < 20:
            print("DEBUG: Not using a high-RAM runtime")
        else:
            print("DEBUG: You are using a high-RAM runtime!")

    def prepare_model(self):
        print("DEBUG: Preparing vision model and tokenizer...")
        self.model, original_tokenizer = FastVisionModel.from_pretrained(
            model_name=self.config["model_name"],
            load_in_4bit=self.config["load_in_4bit"],
            use_gradient_checkpointing="unsloth"
        )
        print("DEBUG: Vision model and original tokenizer loaded.")
        if original_tokenizer.pad_token is None:
            original_tokenizer.pad_token = original_tokenizer.eos_token
        original_tokenizer.model_max_length = self.config.get("max_seq_length", 2048)
        self.hf_tokenizer = original_tokenizer
        
        # Add vision-specific LoRA adapters
        self.model = FastVisionModel.get_peft_model(
            self.model,
            finetune_vision_layers=self.config.get("finetune_vision_layers", False),
            finetune_language_layers=self.config.get("finetune_language_layers", True),
            finetune_attention_modules=self.config.get("finetune_attention_modules", True),
            finetune_mlp_modules=self.config.get("finetune_mlp_modules", True),
            r=16,
            lora_alpha=16,
            lora_dropout=0,
            bias="none",
            random_state=3407,
            use_rslora=False,
            loftq_config=None
        )
        print("DEBUG: Vision LoRA adapters added.")

    def convert_sample(self, sample):
        # Use a default instruction or one from config
        instr = self.config.get("vision_instruction", "You are an expert radiographer. Describe accurately what you see in this image.")
        conversation = [
            {"role": "user", "content": [
                {"type": "text", "text": instr},
                {"type": "image", "image": sample["image"]}
            ]},
            {"role": "assistant", "content": [
                {"type": "text", "text": sample["caption"]}
            ]}
        ]
        return {"messages": conversation}

    def load_datasets(self):
        datasets = []
        for dataset_info in self.config["dataset"]:
            print("DEBUG: Loading vision dataset:", dataset_info)
            ds = load_dataset(dataset_info["name"], split=dataset_info.get("split_type", "train"))
            print("DEBUG: Converting dataset to vision conversation format...")
            ds = ds.map(self.convert_sample)
            datasets.append(ds)
        combined = concatenate_datasets(datasets)
        print("DEBUG: Combined vision dataset has", len(combined), "examples.")
        return combined

    def train_model(self):
        print("DEBUG: Starting vision training...")
        raw_dataset = self.load_datasets()
        
        # Build training arguments using SFTConfig for vision tasks
        sft_config = SFTConfig(
            per_device_train_batch_size=self.config.get("per_device_train_batch_size", 2),
            gradient_accumulation_steps=self.config.get("gradient_accumulation_steps", 4),
            warmup_steps=self.config.get("warmup_steps", 5),
            max_steps=self.config.get("max_steps", 30),
            learning_rate=self.config.get("learning_rate", 2e-4),
            fp16=self.config.get("fp16", not is_bf16_supported()),
            bf16=self.config.get("bf16", is_bf16_supported()),
            logging_steps=self.config.get("logging_steps", 1),
            optim=self.config.get("optim", "adamw_8bit"),
            weight_decay=self.config.get("weight_decay", 0.01),
            lr_scheduler_type=self.config.get("lr_scheduler_type", "linear"),
            seed=self.config.get("seed", 3407),
            output_dir=self.config.get("output_dir", "outputs"),
            report_to="none" if not os.getenv("PRAISON_WANDB") else "wandb",
            remove_unused_columns=False,
            dataset_text_field="",
            dataset_kwargs={"skip_prepare_dataset": True},
            dataset_num_proc=self.config.get("dataset_num_proc", 4),
            max_seq_length=self.config.get("max_seq_length", 2048)
        )
        
        trainer = SFTTrainer(
            model=self.model,
            tokenizer=self.hf_tokenizer,
            data_collator=UnslothVisionDataCollator(self.model, self.hf_tokenizer),
            train_dataset=raw_dataset,
            args=sft_config
        )
        print("DEBUG: Beginning vision trainer.train() ...")
        trainer.train()
        print("DEBUG: Vision training complete. Saving model and tokenizer locally...")
        self.model.save_pretrained("lora_vision_model")
        self.hf_tokenizer.save_pretrained("lora_vision_model")
        print("DEBUG: Saved vision model and tokenizer to 'lora_vision_model'.")

    def vision_inference(self, instruction, image):
        FastVisionModel.for_inference(self.model)
        messages = [
            {"role": "user", "content": [
                {"type": "image"},
                {"type": "text", "text": instruction}
            ]}
        ]
        input_text = self.hf_tokenizer.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self.hf_tokenizer(
            image,
            input_text,
            add_special_tokens=False,
            return_tensors="pt"
        ).to("cuda")
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=128,
            use_cache=True,
            temperature=1.5,
            min_p=0.1
        )
        print("DEBUG: Vision inference output:", self.hf_tokenizer.batch_decode(outputs))

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
            quantization_method=self.config.get("quantization_method", "q4_k_m"),
            token=os.getenv("HF_TOKEN")
        )

    def save_model_gguf(self):
        self.model.save_pretrained_gguf(
            self.config["hf_model_name"],
            self.hf_tokenizer,
            quantization_method="q4_k_m"
        )

    def run(self):
        self.print_system_info()
        self.check_gpu()
        self.check_ram()
        if self.config.get("train", "true").lower() == "true":
            self.prepare_model()
            self.train_model()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PraisonAI Vision Training Script")
    parser.add_argument("command", choices=["train", "inference"], help="Command to execute")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    args = parser.parse_args()

    trainer_obj = TrainVisionModel(config_path=args.config)
    if args.command == "train":
        trainer_obj.run()
    elif args.command == "inference":
        # For inference, we load a sample image from the first dataset
        instr = trainer_obj.config.get("vision_instruction", "You are an expert radiographer. Describe accurately what you see in this image.")
        ds_info = trainer_obj.config["dataset"][0]
        ds = load_dataset(ds_info["name"], split=ds_info.get("split_type", "train"))
        sample_image = ds[0]["image"]
        if trainer_obj.model is None or trainer_obj.hf_tokenizer is None:
            trainer_obj.prepare_model()
        trainer_obj.vision_inference(instr, sample_image)


if __name__ == "__main__":
    main() 