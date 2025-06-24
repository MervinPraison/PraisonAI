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
    if [[ "$OSTYPE" == "darwin"* ]]; then
        conda create --name "$ENV_NAME" python=3.10 pytorch=2.3.0 -c pytorch -y
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        conda create --name "$ENV_NAME" python=3.10 pytorch=2.3.0 cudatoolkit=11.8 -c pytorch -c nvidia -y
    fi
else
    echo "Creating new environment $ENV_NAME..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        conda create --name "$ENV_NAME" python=3.10 pytorch=2.3.0 -c pytorch -y
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        conda create --name "$ENV_NAME" python=3.10 pytorch=2.3.0 cudatoolkit=11.8 -c pytorch -c nvidia -y
    fi
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
$PIP_FULL_PATH install "xformers==0.0.26.post1"
$PIP_FULL_PATH install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git@53a773e4fbc53a1d96c7ba107e5fe75dab07027b"
$PIP_FULL_PATH install --no-deps "trl<0.9.0" peft accelerate bitsandbytes 
$PIP_FULL_PATH install unsloth_zoo
$PIP_FULL_PATH install cut_cross_entropy
$PIP_FULL_PATH install sentencepiece protobuf datasets huggingface_hub hf_transfer wandb

echo "Setup completed successfully!"
