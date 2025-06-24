def generate_config(
    ollama_save=None,
    huggingface_save=None,
    train=None,
    model_name=None,
    hf_model_name=None,
    ollama_model_name=None,
    model_parameters=None,
    max_seq_length=None,
    load_in_4bit=None,
    lora_r=None,
    lora_target_modules=None,
    lora_alpha=None,
    lora_dropout=None,
    lora_bias=None,
    use_gradient_checkpointing=None,
    random_state=None,
    use_rslora=None,
    loftq_config=None,
    dataset=None,
    dataset_text_field=None,
    dataset_num_proc=None,
    packing=None,
    per_device_train_batch_size=None,
    gradient_accumulation_steps=None,
    warmup_steps=None,
    num_train_epochs=None,
    max_steps=None,
    learning_rate=None,
    logging_steps=None,
    optim=None,
    weight_decay=None,
    lr_scheduler_type=None,
    seed=None,
    output_dir=None,
    quantization_method=None
):
    """Generates the configuration for PraisonAI with dynamic overrides."""

    config = {
        "ollama_save": ollama_save or "true",
        "huggingface_save": huggingface_save or "true",
        "train": train or "true",

        "model_name": model_name or "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
        "hf_model_name": hf_model_name or "mervinpraison/llama-3.1-tamilan-8B-test",
        "ollama_model": ollama_model_name or "mervinpraison/llama3.1-tamilan-test",
        "model_parameters": model_parameters or "8b",

        "dataset": dataset or [
            {
                "name": "yahma/alpaca-cleaned",
                "split_type": "train",
                "processing_func": "format_prompts",
                "rename": {"input": "input", "output": "output", "instruction": "instruction"},
                "filter_data": False,
                "filter_column_value": "id",
                "filter_value": "alpaca",
                "num_samples": 20000
            }
        ],

        "dataset_text_field": dataset_text_field or "text",
        "dataset_num_proc": dataset_num_proc or 2,
        "packing": packing or False,

        "max_seq_length": max_seq_length or 2048,
        "load_in_4bit": load_in_4bit or True,
        "lora_r": lora_r or 16,
        "lora_target_modules": lora_target_modules or [
            "q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"
        ],
        "lora_alpha": lora_alpha or 16,
        "lora_dropout": lora_dropout or 0,
        "lora_bias": lora_bias or "none",
        "use_gradient_checkpointing": use_gradient_checkpointing or "unsloth",
        "random_state": random_state or 3407,
        "use_rslora": use_rslora or False,
        "loftq_config": loftq_config or None,

        "per_device_train_batch_size": per_device_train_batch_size or 2,
        "gradient_accumulation_steps": gradient_accumulation_steps or 2,
        "warmup_steps": warmup_steps or 5,
        "num_train_epochs": num_train_epochs or 1,
        "max_steps": max_steps or 10,
        "learning_rate": learning_rate or 2.0e-4,
        "logging_steps": logging_steps or 1,
        "optim": optim or "adamw_8bit",
        "weight_decay": weight_decay or 0.01,
        "lr_scheduler_type": lr_scheduler_type or "linear",
        "seed": seed or 3407,
        "output_dir": output_dir or "outputs",

        "quantization_method": quantization_method or ["q4_k_m"]
    }
    return config