import subprocess
import os
import sys
import yaml
import torch
import shutil
from transformers import TextStreamer
from unsloth import FastLanguageModel, is_bfloat16_supported
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset, concatenate_datasets, Dataset
from psutil import virtual_memory

class train:
    def __init__(self, config_path="config.yaml"):
        self.load_config(config_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model, self.tokenizer = None, None

    def load_config(self, path):
        with open(path, "r") as file:
            self.config = yaml.safe_load(file)

    def print_system_info(self):
        print(f"PyTorch version: {torch.__version__}")
        print(f"CUDA version: {torch.version.cuda}")
        if torch.cuda.is_available():
            device_capability = torch.cuda.get_device_capability()
            print(f"CUDA Device Capability: {device_capability}")
        else:
            print("CUDA is not available")

        python_version = sys.version
        pip_version = subprocess.check_output(['pip', '--version']).decode().strip()
        python_path = sys.executable
        pip_path = subprocess.check_output(['which', 'pip']).decode().strip()
        print(f"Python Version: {python_version}")
        print(f"Pip Version: {pip_version}")
        print(f"Python Path: {python_path}")
        print(f"Pip Path: {pip_path}")

    def check_gpu(self):
        gpu_stats = torch.cuda.get_device_properties(0)
        print(f"GPU = {gpu_stats.name}. Max memory = {round(gpu_stats.total_memory / 1024 / 1024 / 1024, 3)} GB.")

    def check_ram(self):
        ram_gb = virtual_memory().total / 1e9
        print('Your runtime has {:.1f} gigabytes of available RAM\n'.format(ram_gb))
        if ram_gb < 20:
            print('Not using a high-RAM runtime')
        else:
            print('You are using a high-RAM runtime!')

    # def install_packages(self):
    #     subprocess.run(["pip", "install", "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git@4e570be9ae4ced8cdc64e498125708e34942befc"])
    #     subprocess.run(["pip", "install", "--no-deps", "trl<0.9.0", "peft==0.12.0", "accelerate==0.33.0", "bitsandbytes==0.43.3"])

    def prepare_model(self):
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.config["model_name"],
            max_seq_length=self.config["max_seq_length"],
            dtype=None,
            load_in_4bit=self.config["load_in_4bit"]
        )
        self.model = FastLanguageModel.get_peft_model(
            self.model,
            r=self.config["lora_r"],
            target_modules=self.config["lora_target_modules"],
            lora_alpha=self.config["lora_alpha"],
            lora_dropout=self.config["lora_dropout"],
            bias=self.config["lora_bias"],
            use_gradient_checkpointing=self.config["use_gradient_checkpointing"],
            random_state=self.config["random_state"],
            use_rslora=self.config["use_rslora"],
            loftq_config=self.config["loftq_config"],
        )

    def process_dataset(self, dataset_info):
        dataset_name = dataset_info["name"]
        split_type = dataset_info.get("split_type", "train")
        processing_func = getattr(self, dataset_info.get("processing_func", "format_prompts"))
        rename = dataset_info.get("rename", {})
        filter_data = dataset_info.get("filter_data", False)
        filter_column_value = dataset_info.get("filter_column_value", "id")
        filter_value = dataset_info.get("filter_value", "alpaca")
        num_samples = dataset_info.get("num_samples", 20000)

        dataset = load_dataset(dataset_name, split=split_type)

        if rename:
            dataset = dataset.rename_columns(rename)
        if filter_data:
            dataset = dataset.filter(lambda example: filter_value in example[filter_column_value]).shuffle(seed=42).select(range(num_samples))
        dataset = dataset.map(processing_func, batched=True)
        return dataset

    def format_prompts(self, examples):
        alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

        ### Instruction:
        {}

        ### Input:
        {}

        ### Response:
        {}"""
        texts = [alpaca_prompt.format(ins, inp, out) + self.tokenizer.eos_token for ins, inp, out in zip(examples["instruction"], examples["input"], examples["output"])]
        return {"text": texts}

    def load_datasets(self):
        datasets = []
        for dataset_info in self.config["dataset"]:
            datasets.append(self.process_dataset(dataset_info))
        return concatenate_datasets(datasets)

    def train_model(self):
        dataset = self.load_datasets()
        trainer = SFTTrainer(
            model=self.model,
            tokenizer=self.tokenizer,
            train_dataset=dataset,
            dataset_text_field=self.config["dataset_text_field"],
            max_seq_length=self.config["max_seq_length"],
            dataset_num_proc=self.config["dataset_num_proc"],
            packing=self.config["packing"],
            args=TrainingArguments(
                per_device_train_batch_size=self.config["per_device_train_batch_size"],
                gradient_accumulation_steps=self.config["gradient_accumulation_steps"],
                warmup_steps=self.config["warmup_steps"],
                num_train_epochs=self.config["num_train_epochs"],
                max_steps=self.config["max_steps"],
                learning_rate=self.config["learning_rate"],
                fp16=not is_bfloat16_supported(),
                bf16=is_bfloat16_supported(),
                logging_steps=self.config["logging_steps"],
                optim=self.config["optim"],
                weight_decay=self.config["weight_decay"],
                lr_scheduler_type=self.config["lr_scheduler_type"],
                seed=self.config["seed"],
                output_dir=self.config["output_dir"],
            ),
        )
        trainer.train()
        self.model.save_pretrained("lora_model") # Local saving
        self.tokenizer.save_pretrained("lora_model")

    def inference(self, instruction, input_text):
        FastLanguageModel.for_inference(self.model)
        alpaca_prompt = """Below is an instruction that describes a task, paired with an input that provides further context. Write a response that appropriately completes the request.

        ### Instruction:
        {}

        ### Input:
        {}

        ### Response:
        {}"""
        inputs = self.tokenizer([alpaca_prompt.format(instruction, input_text, "")], return_tensors="pt").to("cuda")
        outputs = self.model.generate(**inputs, max_new_tokens=64, use_cache=True)
        print(self.tokenizer.batch_decode(outputs))
        
    def load_model(self):
        """Loads the model and tokenizer using the FastLanguageModel library."""
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
            self.tokenizer,
            save_method="merged_16bit",
            token=os.getenv('HF_TOKEN')
        )

    def push_model_gguf(self):
        self.model.push_to_hub_gguf(
            self.config["hf_model_name"],
            self.tokenizer,
            quantization_method=self.config["quantization_method"],
            token=os.getenv('HF_TOKEN')
        )
    
    def save_model_gguf(self):
        self.model.save_pretrained_gguf(
            self.config["hf_model_name"],
            self.tokenizer,
            quantization_method="q4_k_m"
        )

    def prepare_modelfile_content(self):
        output_model = self.config["hf_model_name"]
        gguf_path = f"{output_model}/unsloth.Q4_K_M.gguf"

        # Check if the GGUF file exists. If not, generate it ## TODO Multiple Quantisation other than Q4_K_M.gguf
        if not os.path.exists(gguf_path):
            self.model, self.tokenizer = self.load_model()
            self.save_model_gguf()
        return f"""FROM {output_model}/unsloth.Q4_K_M.gguf

TEMPLATE \"\"\"Below are some instructions that describe some tasks. Write responses that appropriately complete each request.{{{{ if .Prompt }}}}

### Instruction:
{{{{ .Prompt }}}}

{{{{ end }}}}### Response:
{{{{ .Response }}}}\"\"\"

PARAMETER stop ""
PARAMETER stop ""
PARAMETER stop ""
PARAMETER stop ""
PARAMETER stop "<|reserved_special_token_"
"""

    def create_and_push_ollama_model(self):
        modelfile_content = self.prepare_modelfile_content()
        with open('Modelfile', 'w') as file:
            file.write(modelfile_content)

        subprocess.run(["ollama", "serve"])
        subprocess.run(["ollama", "create", f"{self.config['ollama_model']}:{self.config['model_parameters']}", "-f", "Modelfile"])
        subprocess.run(["ollama", "push", f"{self.config['ollama_model']}:{self.config['model_parameters']}"])

    def run(self):
        self.print_system_info()
        self.check_gpu()
        self.check_ram()
        # self.install_packages()
        if self.config.get("train", "true").lower() == "true":
            self.prepare_model()
            self.train_model()

        if self.config.get("huggingface_save", "true").lower() == "true":
            # self.model, self.tokenizer = self.load_model()
            self.save_model_merged()

        if self.config.get("huggingface_save_gguf", "true").lower() == "true":
            # self.model, self.tokenizer = self.load_model()
            self.push_model_gguf()
            
        # if self.config.get("save_gguf", "true").lower() == "true": ## TODO
        #     self.model, self.tokenizer = self.load_model()
        #     self.save_model_gguf()
        
        # if self.config.get("save_merged", "true").lower() == "true": ## TODO
        #     self.model, self.tokenizer = self.load_model()
        #     self.save_model_merged()

        if self.config.get("ollama_save", "true").lower() == "true":
            self.create_and_push_ollama_model()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='PraisonAI Training Script')
    parser.add_argument('command', choices=['train'], help='Command to execute')
    parser.add_argument('--config', default='config.yaml', help='Path to configuration file')
    args = parser.parse_args()

    if args.command == 'train':
        ai = train(config_path=args.config)
        ai.run()


if __name__ == '__main__':
    main()
