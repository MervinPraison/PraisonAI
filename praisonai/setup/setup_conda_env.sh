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
ENV_NAME="praison_env"
if conda info --envs | grep -q $ENV_NAME; then
    echo "Environment $ENV_NAME already exists. Recreating..."
    conda env remove -y -n $ENV_NAME  # Remove existing environment
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS (both Intel and M1/M2)
        conda create --name $ENV_NAME python=3.10 pytorch=2.3.0 -c pytorch -y
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        conda create --name $ENV_NAME python=3.10 pytorch=2.3.0 cudatoolkit=11.8 -c pytorch -c nvidia -y
    fi
    # conda activate $ENV_NAME
else
    echo "Creating new environment $ENV_NAME..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS (both Intel and M1/M2)
        conda create --name $ENV_NAME python=3.10 pytorch=2.3.0 -c pytorch -y
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        conda create --name $ENV_NAME python=3.10 pytorch=2.3.0 cudatoolkit=11.8 -c pytorch -c nvidia -y
    fi
    # conda activate $ENV_NAME
fi

# source $HOME/miniconda/bin/activate $ENV_NAME

# Get full path of pip
PIP_FULL_PATH=$(conda run -n $ENV_NAME which pip)

# Install other packages within the activated environment
# Use PIP_FULL_PATH to run pip commands
$PIP_FULL_PATH install --upgrade pip 
$PIP_FULL_PATH install "xformers==0.0.26.post1"
$PIP_FULL_PATH install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git@4e570be9ae4ced8cdc64e498125708e34942befc"
$PIP_FULL_PATH install --no-deps "trl<0.9.0" peft accelerate bitsandbytes 

echo "Setup completed successfully!"
