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
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
    echo "Windows detected. Please run this script in Git Bash or WSL."
    exit 1
else
    echo "Unsupported operating system: $OSTYPE"
    exit 1
fi

# Check if conda is already installed
if ! command -v conda &> /dev/null; then
    echo "Conda is not installed. Installing Miniconda..."
    wget $MINICONDA_URL -O ~/miniconda.sh
    bash ~/miniconda.sh -b -p $HOME/miniconda
    source $HOME/miniconda/bin/activate
    conda init
else
    echo "Conda is already installed."
fi

# Create and activate the Conda environment
ENV_NAME="unsloth_env"
if conda info --envs | grep -q $ENV_NAME; then
    echo "Environment $ENV_NAME already exists. Activating..."
    conda activate $ENV_NAME
else
    echo "Creating new environment $ENV_NAME..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS (both Intel and M1/M2)
        conda create --name $ENV_NAME python=3.10 pytorch=2.3.0 -c pytorch -y
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        conda create --name $ENV_NAME python=3.10 pytorch=2.3.0 cudatoolkit=11.8 -c pytorch -c nvidia -y
        conda activate $ENV_NAME
        pip install xformers==0.0.26.post1
    fi
fi

source $HOME/miniconda/bin/activate $ENV_NAME

# Install other packages
pip install --upgrade pip
pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git@4e570be9ae4ced8cdc64e498125708e34942befc"
pip install --no-deps "trl<0.9.0" peft accelerate bitsandbytes

echo "Setup completed successfully!"