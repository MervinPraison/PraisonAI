#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script handles uploading trained vision models to Hugging Face and Ollama.
It reads configuration from config.yaml and provides options to upload in different formats.
"""

import os
import yaml
import torch
import shutil
import subprocess
from unsloth import FastVisionModel

class UploadVisionModel:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.hf_tokenizer = None

    def load_config(self, path):
        """Load configuration from yaml file."""
        with open(path, "r") as file:
            self.config = yaml.safe_load(file)
        print("DEBUG: Loaded config:", self.config)

    def prepare_model(self):
        """Load the trained model for uploading."""
        print("DEBUG: Loading trained model and tokenizer...")
        self.model, original_tokenizer = FastVisionModel.from_pretrained(
            model_name=self.config.get("output_dir", "lora_model"),
            load_in_4bit=self.config.get("load_in_4bit", True)
        )
        self.hf_tokenizer = original_tokenizer
        print("DEBUG: Model and tokenizer loaded successfully.")

    def save_model_merged(self):
        """Save merged model to Hugging Face Hub."""
        print(f"DEBUG: Saving merged model to Hugging Face Hub: {self.config['hf_model_name']}")
        if os.path.exists(self.config["hf_model_name"]):
            shutil.rmtree(self.config["hf_model_name"])
        self.model.push_to_hub_merged(
            self.config["hf_model_name"],
            self.hf_tokenizer,
            save_method="merged_16bit",
            token=os.getenv("HF_TOKEN")
        )
        print("DEBUG: Model saved to Hugging Face Hub successfully.")

    def push_model_gguf(self):
        """Push model in GGUF format to Hugging Face Hub."""
        print(f"DEBUG: Pushing GGUF model to Hugging Face Hub: {self.config['hf_model_name']}")
        self.model.push_to_hub_gguf(
            self.config["hf_model_name"],
            self.hf_tokenizer,
            quantization_method=self.config.get("quantization_method", "q4_k_m"),
            token=os.getenv("HF_TOKEN")
        )
        print("DEBUG: GGUF model pushed to Hugging Face Hub successfully.")

    def prepare_modelfile_content(self):
        """Prepare Ollama modelfile content using Llama 3.2 vision template."""
        output_model = self.config["hf_model_name"]
        
        # Using Llama 3.2 vision template format
        template = """{{- range $index, $_ := .Messages }}<|start_header_id|>{{ .Role }}<|end_header_id|>

{{ .Content }}
{{- if gt (len (slice $.Messages $index)) 1 }}<|eot_id|>
{{- else if ne .Role "assistant" }}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

{{ end }}
{{- end }}"""
        
        # Assemble the modelfile content with Llama 3.2 vision parameters
        modelfile = f"FROM {output_model}\n"
        modelfile += "TEMPLATE \"""" + template + "\"""\n"
        modelfile += "PARAMETER temperature 0.6\n"
        modelfile += "PARAMETER top_p 0.9\n"
        return modelfile

    def create_and_push_ollama_model(self):
        """Create and push model to Ollama."""
        print(f"DEBUG: Creating Ollama model: {self.config['ollama_model']}:{self.config['model_parameters']}")
        modelfile_content = self.prepare_modelfile_content()
        with open("Modelfile", "w") as file:
            file.write(modelfile_content)
        
        print("DEBUG: Starting Ollama server...")
        subprocess.run(["ollama", "serve"])
        
        print("DEBUG: Creating Ollama model...")
        subprocess.run([
            "ollama", "create", 
            f"{self.config['ollama_model']}:{self.config['model_parameters']}", 
            "-f", "Modelfile"
        ])
        
        print("DEBUG: Pushing model to Ollama...")
        subprocess.run([
            "ollama", "push", 
            f"{self.config['ollama_model']}:{self.config['model_parameters']}"
        ])
        print("DEBUG: Model pushed to Ollama successfully.")

    def upload(self, target="all"):
        """
        Upload the model to specified targets.
        Args:
            target (str): One of 'all', 'huggingface', 'huggingface_gguf', or 'ollama'
        """
        self.prepare_model()
        
        if target in ["all", "huggingface"]:
            self.save_model_merged()
        
        if target in ["all", "huggingface_gguf"]:
            self.push_model_gguf()
            
        if target in ["all", "ollama"]:
            self.create_and_push_ollama_model()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Upload Vision Model to Various Platforms")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    parser.add_argument(
        "--target", 
        choices=["all", "huggingface", "huggingface_gguf", "ollama"],
        default="all",
        help="Target platform to upload to"
    )
    args = parser.parse_args()

    uploader = UploadVisionModel(config_path=args.config)
    uploader.upload(target=args.target)

if __name__ == "__main__":
    main()
