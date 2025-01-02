#!/bin/bash

# Exit on any error
set -e

# Function to print messages
print_message() {
    echo "==> $1"
}

# Function to print usage
print_usage() {
    echo "Usage: $0 [-u|--ui] [-c|--chat] [-d|--code] [-r|--realtime] [-a|--all] [--run] [--quick] [--model MODEL] [--base URL]"
    echo "Options:"
    echo "  -u, --ui       Install UI dependencies for Multi Agents (CrewAI/AutoGen)"
    echo "  -c, --chat     Install Chat interface for single AI Agent"
    echo "  -d, --code     Install Code interface for codebase interaction"
    echo "  -r, --realtime Install Realtime voice interaction interface"
    echo "  -a, --all      Install all interfaces"
    echo "  --run          Run the interface after installation"
    echo "  --quick        Quick start the UI interface with chainlit"
    echo "  --model        Set custom model name (e.g., mistral-large)"
    echo "  --base         Set custom API base URL (e.g., https://api.mistral.ai/v1)"
    echo "  --cicd         Run in CI/CD mode (skip repository cloning)"
    echo "  -h, --help     Show this help message"
}

# Function to prompt for OpenAI API key if not set
check_openai_key() {
    if [ -z "$OPENAI_API_KEY" ]; then
        print_message "OpenAI API key not found"
        read -p "Enter your API key: " api_key
        export OPENAI_API_KEY="$api_key"
    fi
}

# Function to setup model configuration
setup_model_config() {
    if [ ! -z "$MODEL_NAME" ]; then
        print_message "Setting custom model: $MODEL_NAME"
        export OPENAI_MODEL_NAME="$MODEL_NAME"
    fi
    
    if [ ! -z "$API_BASE" ]; then
        print_message "Setting custom API base: $API_BASE"
        # Set both variables for compatibility
        export OPENAI_API_BASE="$API_BASE"
        export OPENAI_API_BASE_URL="$API_BASE"
    fi
}

# Function to setup chainlit authentication
setup_chainlit() {
    print_message "Setting up chainlit authentication..."
    
    # Check if .env file exists
    if [ ! -f .env ]; then
        print_message "Creating new chainlit secret..."
        touch .env
        # Generate a secure random secret
        SECRET=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
        echo "CHAINLIT_AUTH_SECRET=\"$SECRET\"" > .env
    fi
    
    # Source the secret from .env
    if [ -f .env ]; then
        source .env
        if [ -z "$CHAINLIT_AUTH_SECRET" ]; then
            print_message "Error: CHAINLIT_AUTH_SECRET not found in .env file"
            exit 1
        else
            print_message "Chainlit authentication configured successfully"
            export CHAINLIT_AUTH_SECRET
        fi
    else
        print_message "Error: Failed to create .env file"
        exit 1
    fi
}

# Function to run UI interface
run_ui_interface() {
    check_openai_key
    setup_model_config
    if [[ $QUICK == true ]]; then
        print_message "Quick starting UI interface with chainlit..."
        setup_chainlit
        praisonai ui
    else
        print_message "Starting UI interface..."
        read -p "Use chainlit interface? (y/N): " use_chainlit
        if [[ $use_chainlit =~ ^[Yy]$ ]]; then
            setup_chainlit
            praisonai ui
        else
            read -p "Enter your initial prompt (or press enter for default): " prompt
            if [ -z "$prompt" ]; then
                prompt="create a movie script about dog in moon"
            fi
            read -p "Use AutoGen framework? (y/N): " use_autogen
            if [[ $use_autogen =~ ^[Yy]$ ]]; then
                praisonai --framework autogen --init "$prompt"
            else
                praisonai --init "$prompt"
            fi
        fi
    fi
}

# Function to run Chat interface
run_chat_interface() {
    check_openai_key
    setup_model_config
    print_message "Starting Chat interface..."
    python3 -m praisonai chat
}

# Function to run Code interface
run_code_interface() {
    check_openai_key
    setup_model_config
    print_message "Starting Code interface..."
    praisonai code
}

# Function to run Realtime interface
run_realtime_interface() {
    check_openai_key
    setup_model_config
    print_message "Starting Realtime voice interaction..."
    python3 -m praisonai realtime
}

# Function to check system dependencies
check_system_deps() {
    print_message "Checking system dependencies..."
    
    # Check RHEL version
    if [ -f /etc/redhat-release ]; then
        RHEL_VERSION=$(cat /etc/redhat-release)
        print_message "Detected Red Hat Enterprise Linux: $RHEL_VERSION"
        
        # Extract major version number
        RHEL_MAJOR=$(echo "$RHEL_VERSION" | grep -oP '(?<=release )\d+')
        if [ -z "$RHEL_MAJOR" ] || [ "$RHEL_MAJOR" -lt 9 ]; then
            print_message "Warning: This script is tested on RHEL 9.x. Your version: $RHEL_VERSION"
            read -p "Do you want to continue? (y/N): " continue_install
            if [[ ! $continue_install =~ ^[Yy]$ ]]; then
                print_message "Installation aborted by user"
                exit 1
            fi
        fi
    fi
    
    # Detect package manager
    if command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"
    elif command -v apt-get &> /dev/null; then
        PKG_MANAGER="apt"
    else
        print_message "Unsupported package manager. This script supports Fedora (dnf) and Debian/Ubuntu (apt)."
        exit 1
    fi
    
    # Install  specifically
    if [ "$PKG_MANAGER" = "dnf" ]; then
        print_message "Installing Python 3.11 and pip..."
        
        # For RHEL systems
        if [ -f /etc/redhat-release ]; then
            # Enable EPEL repository for RHEL 9
            sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
            sudo dnf install -y https://dl.fedoraproject.org/pub/epel/epel-next-release-latest-9.noarch.rpm
            
            # Update package list
            sudo dnf update -y
            
            # Install Python 3.11
            if ! sudo dnf install -y python3.11; then
                print_message "Python 3.11 not found in default repositories. Trying alternative installation..."
                # Try installing from EPEL
                sudo dnf install -y python3.11 || {
                    print_message "Failed to install Python 3.11. Please install manually."
                    exit 1
                }
            fi
        else
            # For other dnf-based systems (Fedora)
            sudo dnf update -y
            sudo dnf install -y python3.11
        fi
        
        # Install pip
        sudo dnf install -y python3-pip
        
        # Try to set Python 3.11 as default if it exists
        if [ -f "/usr/bin/python3.11" ]; then
            sudo alternatives --set python3 /usr/bin/python3.11 || true
        fi
    else
        print_message "Installing Python 3.11 and pip..."
        
        # Install Python 3.11 without using add-apt-repository
        echo "deb http://ppa.launchpad.net/deadsnakes/ppa/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa.list
        sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys F23C5A6CF475977595C89F51BA6932366A755776
        
        sudo apt-get update || true  # Continue even if there are some update errors
        
        # Install required packages
        sudo apt-get install -y python3.11 python3.11-venv python3.11-distutils
        # Set Python 3.11 as the default python3
        sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
        sudo update-alternatives --set python3 /usr/bin/python3.11
    fi
    
    # Verify Python version is exactly 3.11
    PYTHON_VERSION=$(python3 --version)
    if [[ ! $PYTHON_VERSION =~ "Python 3.11" ]]; then
        print_message "Error: Python version must be 3.11. Current version: $PYTHON_VERSION"
        exit 1
    fi
    
    # Check for poetry and add to PATH if needed
    if ! command -v poetry &> /dev/null; then
        print_message "Poetry not found. Installing with Python 3.11..."
        curl -sSL https://install.python-poetry.org | python3.11 -
        export PATH="$HOME/.local/bin:$PATH"
        source $HOME/.profile
    fi
    
    # Verify poetry installation
    if ! command -v poetry &> /dev/null; then
        print_message "Failed to install Poetry. Please install it manually."
        exit 1
    fi
}

# Function to setup virtual environment
setup_venv() {
    print_message "Setting up virtual environment..."
    
    # Skip venv setup if running in CI/CD mode
    if [[ "$CICD" == "true" ]]; then
        print_message "Running in CI/CD mode, skipping venv setup..."
        return 0
    fi
    
    # Only run these steps for local development
    poetry config virtualenvs.in-project true
    
    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        poetry install --no-root
    fi
    
    # Activate virtual environment
    source .venv/bin/activate
}

# Function to check and install interface dependencies
install_interface_deps() {
    # Skip if poetry.lock exists (dependencies already installed)
    if [ -f "poetry.lock" ]; then
        print_message "Dependencies for $1 interface already installed. Skipping..."
        return
    fi

    if [[ $1 == "ui" ]]; then
        print_message "Installing UI interface dependencies..."
        poetry install -E ui -E crewai -E autogen
    elif [[ $1 == "chat" ]]; then
        print_message "Installing Chat interface dependencies..."
        poetry install -E chat
    elif [[ $1 == "code" ]]; then
        print_message "Installing Code interface dependencies..."
        poetry install -E code
    elif [[ $1 == "realtime" ]]; then
        print_message "Installing Realtime interface dependencies..."
        poetry install -E realtime
    fi
}

# Parse command line arguments
UI=false
CHAT=false
CODE=false
REALTIME=false
RUN=false
QUICK=false
CICD=false
TAG="v2.0.16"
MODEL_NAME=""
API_BASE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cicd)
            CICD=true
            shift
            ;;
        -u|--ui)
            UI=true
            shift
            ;;
        -c|--chat)
            CHAT=true
            shift
            ;;
        -d|--code)
            CODE=true
            shift
            ;;
        -r|--realtime)
            REALTIME=true
            shift
            ;;
        -a|--all)
            UI=true
            CHAT=true
            CODE=true
            REALTIME=true
            shift
            ;;
        --run)
            RUN=true
            shift
            ;;
        --quick)
            QUICK=true
            UI=true
            RUN=true
            shift
            ;;
        --model)
            shift
            MODEL_NAME="$1"
            shift
            ;;
        --base)
            shift
            API_BASE="$1"
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            print_message "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Clone repository and checkout tag if not in CICD mode
if [[ $CICD == false ]]; then
    print_message "Cloning PraisonAI repository and checking out ${TAG}..."
    if [ ! -d "PraisonAI" ]; then
        git clone https://github.com/MervinPraison/PraisonAI.git
        cd PraisonAI
        git checkout ${TAG}
    else
        cd PraisonAI
        git checkout ${TAG}
    fi
fi

# If no options specified, show usage
if [[ $UI == false && $CHAT == false && $CODE == false && $REALTIME == false ]]; then
    print_message "No interface selected"
    print_usage
    exit 1
fi

# Detect OS and check dependencies only if installation is needed
if [[ $UI == true || $CHAT == true || $CODE == true || $REALTIME == true ]]; then
    check_system_deps
    setup_venv

    # Install interface-specific dependencies only if needed
    if [[ $UI == true ]]; then
        install_interface_deps "ui"
    fi

    if [[ $CHAT == true ]]; then
        install_interface_deps "chat"
    fi

    if [[ $CODE == true ]]; then
        install_interface_deps "code"
    fi

    if [[ $REALTIME == true ]]; then
        install_interface_deps "realtime"
    fi

    # Check if praisonai is already installed
    if ! pip show praisonai &> /dev/null; then
        print_message "Installing PraisonAI components..."
        pip install praisonai
        pip install praisonaiagents
        
        # Install only the required components based on selected interfaces
        components=()
        [[ $UI == true ]] && components+=("ui" "crewai" "autogen")
        [[ $CHAT == true ]] && components+=("chat")
        [[ $CODE == true ]] && components+=("code")
        [[ $REALTIME == true ]] && components+=("realtime")
        
        # Install selected components
        for component in "${components[@]}"; do
            pip install "praisonai[$component]"
        done
    else
        print_message "PraisonAI is already installed. Skipping installation."
    fi

    print_message "Setup completed successfully!"
fi

# Run interfaces if requested
if [[ $RUN == true ]]; then
    # Check for OPENAI_API_KEY
    if [ -z "$OPENAI_API_KEY" ]; then
        print_message "OpenAI API key not found. Please set it before running interfaces."
        print_message "You can set it by running: export OPENAI_API_KEY='your-api-key'"
        exit 1
    fi
    
    if [[ $UI == true ]]; then
        run_ui_interface
    fi
    if [[ $CHAT == true ]]; then
        run_chat_interface
    fi
    if [[ $CODE == true ]]; then
        run_code_interface
    fi
    if [[ $REALTIME == true ]]; then
        run_realtime_interface
    fi
else
    # Display next steps and current configuration
    print_message "Configuration:"
    if [ ! -z "$OPENAI_API_KEY" ]; then
        echo "API Key: [Set]"
    fi
    if [ ! -z "$MODEL_NAME" ]; then
        echo "Model: $MODEL_NAME"
    fi
    if [ ! -z "$API_BASE" ]; then
        echo "API Base: $API_BASE"
    fi
    
    print_message "Next steps:"
    if [[ $UI == true ]]; then
        echo "- To start the UI interface:"
        echo "  Quick start: ./setup.sh --quick"
        echo "  Interactive: ./setup.sh -u --run"
        echo "  With custom model: ./setup.sh --quick --model mistral-large --base https://api.mistral.ai/v1"
        echo "  Or visit: https://docs.praison.ai/ui/ui"
    fi
    if [[ $CHAT == true ]]; then
        echo "- To start the Chat interface: ./setup.sh -c --run"
        echo "  Or visit: https://docs.praison.ai/ui/chat"
    fi
    if [[ $CODE == true ]]; then
        echo "- To start the Code interface: ./setup.sh -d --run"
        echo "  Or visit: https://docs.praison.ai/ui/code"
    fi
    if [[ $REALTIME == true ]]; then
        echo "- To start the Realtime interface: ./setup.sh -r --run"
        echo "  Or visit: https://docs.praison.ai/ui/realtime"
    fi
fi
