#!/bin/bash

# Detect OS and architecture
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if [[ $(uname -m) == 'arm64' ]]; then
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
    else
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    
    # Install libcurl development package if not present (Debian based)
    if command -v dpkg &> /dev/null; then
        if ! dpkg -s libcurl4-openssl-dev &> /dev/null; then
            echo "libcurl4-openssl-dev is not installed. Installing..."
            sudo apt-get update
            sudo apt-get install -y libcurl4-openssl-dev
        else
            echo "libcurl4-openssl-dev is already installed."
        fi
    else
        echo "Non-Debian based Linux detected. Please ensure libcurl development libraries are installed."
    fi

    # Check if ollama is installed and executable; if not, install it
    if ! command -v ollama &> /dev/null; then
        echo "Ollama is not installed. Installing Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        
        # Generate SSH key non-interactively only if it doesn't already exist
        if [ ! -f ~/.ssh/id_ed25519 ]; then
            echo "Generating SSH key for Ollama..."
            ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -q
        else
            echo "SSH key ~/.ssh/id_ed25519 already exists. Skipping generation."
        fi
        echo "Copying SSH key to /usr/share/ollama/.ollama..."
        sudo cp ~/.ssh/id_ed25519 /usr/share/ollama/.ollama
    else
        echo "Ollama is already installed."
    fi

elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
    echo "Windows detected. Please run this script in Git Bash or WSL."
    exit 1
else
    echo "Unsupported operating system: $OSTYPE"
    exit 1
fi

# --- What GPU is actually here? --------------------------------------------
#
# Every Linux host got `pytorch-cuda=12.4` regardless of hardware. On an AMD
# box or a Blackwell card that produces a working-LOOKING environment which
# fails at the first kernel; on a CPU-only host it installs a CUDA build that
# can never run. Probe before pinning.
detect_accelerator() {
    if command -v nvidia-smi &> /dev/null && nvidia-smi -L 2>/dev/null | grep -q GPU; then
        echo "cuda"; return
    fi
    # nvidia-smi can be absent on a machine that does have the driver.
    if [ -d /proc/driver/nvidia/gpus ] && [ -n "$(ls -A /proc/driver/nvidia/gpus 2>/dev/null)" ]; then
        echo "cuda"; return
    fi
    if command -v rocminfo &> /dev/null || command -v amd-smi &> /dev/null; then
        echo "rocm"; return
    fi
    echo "cpu"
}

ACCELERATOR="$(detect_accelerator)"
echo "Detected accelerator: $ACCELERATOR"

# The pytorch-cuda pin, or nothing at all. Kept in one place so the two
# create-environment branches below cannot disagree.
TORCH_SPEC="pytorch=2.6.0"
TORCH_CHANNELS="-c pytorch"
case "$ACCELERATOR" in
    cuda)
        TORCH_SPEC="pytorch=2.6.0 pytorch-cuda=12.4"
        TORCH_CHANNELS="-c pytorch -c nvidia"
        ;;
    rocm)
        echo "WARNING: an AMD GPU was detected. This installer only knows the CUDA"
        echo "         and CPU builds, so it will install the CPU one. Follow"
        echo "         https://pytorch.org/get-started/locally/ for a ROCm build,"
        echo "         then re-run this script."
        ;;
    cpu)
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            echo "WARNING: no GPU detected. Fine-tuning needs one -- praisonai-train"
            echo "         llm refuses to run on CPU. The environment will still be"
            echo "         usable for dataset work and exports."
        fi
        ;;
esac

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    echo "Conda is not installed. Installing Miniconda..."
    wget "$MINICONDA_URL" -O ~/miniconda.sh
    bash ~/miniconda.sh -b -p "$HOME/miniconda"
    source "$HOME/miniconda/bin/activate"
    conda init
else
    echo "Conda is already installed."
fi

# Create and activate the Conda environment
ENV_NAME="praison_env"
if conda info --envs | grep -q "$ENV_NAME"; then
    echo "Environment $ENV_NAME already exists. Recreating..."
    conda env remove -y -n "$ENV_NAME"
    conda create --name "$ENV_NAME" python=3.11 $TORCH_SPEC $TORCH_CHANNELS -y
else
    echo "Creating new environment $ENV_NAME..."
    conda create --name "$ENV_NAME" python=3.11 $TORCH_SPEC $TORCH_CHANNELS -y
fi

# Activate the environment
source "$HOME/miniconda/bin/activate" "$ENV_NAME"

# Install cmake via conda
echo "Installing cmake..."
conda install -y cmake

# Get full path of pip within the activated environment
PIP_FULL_PATH=$(conda run -n "$ENV_NAME" which pip)

# Install other packages using pip
$PIP_FULL_PATH install --upgrade pip
# Latest Unsloth pulls a compatible xformers/trl/transformers set itself; pinning an
# ancient unsloth commit + trl<0.9.0 broke new-model support (Gemma 4, Qwen3, ...).
$PIP_FULL_PATH install "unsloth>=2025.9.1" unsloth_zoo
$PIP_FULL_PATH install "trl>=0.18.2" "peft>=0.13.0" "accelerate>=0.34.0" "bitsandbytes>=0.45.0"
$PIP_FULL_PATH install sentencepiece protobuf datasets huggingface_hub hf_transfer wandb

echo "Setup completed successfully!"
