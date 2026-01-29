#!/usr/bin/env bash
# PraisonAI Installer
# Works on macOS, Linux, and Windows (WSL)
# Usage: curl -fsSL https://praison.ai/install.sh | bash
#
# Environment variables:
#   PRAISONAI_VERSION     - Specific version to install (default: latest)
#   PRAISONAI_EXTRAS      - Comma-separated extras (e.g., "ui,chat,code")
#   PRAISONAI_NO_PROMPT   - Skip interactive prompts (1 to enable)
#   PRAISONAI_DRY_RUN     - Print what would happen without making changes
#   PRAISONAI_PYTHON      - Path to Python executable
#   PRAISONAI_SKIP_VENV   - Skip virtual environment creation (1 to enable)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
VERSION="${PRAISONAI_VERSION:-latest}"
EXTRAS="${PRAISONAI_EXTRAS:-}"
NO_PROMPT="${PRAISONAI_NO_PROMPT:-0}"
DRY_RUN="${PRAISONAI_DRY_RUN:-0}"
PYTHON_CMD="${PRAISONAI_PYTHON:-}"
SKIP_VENV="${PRAISONAI_SKIP_VENV:-0}"
MIN_PYTHON_VERSION="3.10"

# Logging functions
log_info() {
    echo -e "${BLUE}==>${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

log_step() {
    echo -e "${CYAN}→${NC} $1"
}

# Print banner
print_banner() {
    echo -e "${BOLD}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║                                                           ║"
    echo "║   ${CYAN}PraisonAI${NC}${BOLD} - AI Agents Made Simple                      ║"
    echo "║                                                           ║"
    echo "║   Works everywhere. Installs everything. You're welcome.  ║"
    echo "║                                                           ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Darwin*)
            OS="macos"
            ;;
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                OS="wsl"
            else
                OS="linux"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            OS="windows"
            ;;
        *)
            OS="unknown"
            ;;
    esac
    echo "$OS"
}

# Detect package manager
detect_package_manager() {
    if command -v brew &>/dev/null; then
        echo "brew"
    elif command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v yum &>/dev/null; then
        echo "yum"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    elif command -v apk &>/dev/null; then
        echo "apk"
    else
        echo "unknown"
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" &>/dev/null
}

# Compare Python versions
version_gte() {
    # Returns 0 if $1 >= $2
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# Find suitable Python
find_python() {
    local python_cmd=""
    
    # Check user-specified Python first
    if [[ -n "$PYTHON_CMD" ]]; then
        if command_exists "$PYTHON_CMD"; then
            python_cmd="$PYTHON_CMD"
        else
            log_error "Specified Python not found: $PYTHON_CMD"
            return 1
        fi
    else
        # Try common Python commands
        for cmd in python3.12 python3.11 python3.10 python3 python; do
            if command_exists "$cmd"; then
                python_cmd="$cmd"
                break
            fi
        done
    fi
    
    if [[ -z "$python_cmd" ]]; then
        return 1
    fi
    
    # Verify version
    local version
    version=$("$python_cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    
    if version_gte "$version" "$MIN_PYTHON_VERSION"; then
        echo "$python_cmd"
        return 0
    fi
    
    return 1
}

# Install Python on macOS
install_python_macos() {
    log_step "Installing Python via Homebrew..."
    
    if ! command_exists brew; then
        log_step "Installing Homebrew first..."
        if [[ "$DRY_RUN" == "1" ]]; then
            log_info "[DRY RUN] Would install Homebrew"
        else
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            
            # Add Homebrew to PATH for this session
            if [[ -f "/opt/homebrew/bin/brew" ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -f "/usr/local/bin/brew" ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
        fi
    fi
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would run: brew install python@3.12"
    else
        brew install python@3.12 || brew upgrade python@3.12 || true
    fi
}

# Install Python on Linux
install_python_linux() {
    local pkg_manager
    pkg_manager=$(detect_package_manager)
    
    log_step "Installing Python via $pkg_manager..."
    
    case "$pkg_manager" in
        apt)
            if [[ "$DRY_RUN" == "1" ]]; then
                log_info "[DRY RUN] Would run: apt-get update && apt-get install -y python3 python3-pip python3-venv"
            else
                sudo apt-get update
                sudo apt-get install -y python3 python3-pip python3-venv
            fi
            ;;
        dnf)
            if [[ "$DRY_RUN" == "1" ]]; then
                log_info "[DRY RUN] Would run: dnf install -y python3 python3-pip"
            else
                sudo dnf install -y python3 python3-pip
            fi
            ;;
        yum)
            if [[ "$DRY_RUN" == "1" ]]; then
                log_info "[DRY RUN] Would run: yum install -y python3 python3-pip"
            else
                sudo yum install -y python3 python3-pip
            fi
            ;;
        pacman)
            if [[ "$DRY_RUN" == "1" ]]; then
                log_info "[DRY RUN] Would run: pacman -Sy --noconfirm python python-pip"
            else
                sudo pacman -Sy --noconfirm python python-pip
            fi
            ;;
        apk)
            if [[ "$DRY_RUN" == "1" ]]; then
                log_info "[DRY RUN] Would run: apk add python3 py3-pip"
            else
                sudo apk add python3 py3-pip
            fi
            ;;
        *)
            log_error "Unsupported package manager. Please install Python $MIN_PYTHON_VERSION+ manually."
            return 1
            ;;
    esac
}

# Ensure Python is installed
ensure_python() {
    log_info "Checking Python installation..."
    
    local python_cmd
    if python_cmd=$(find_python); then
        local version
        version=$("$python_cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
        log_success "Python $version found: $python_cmd"
        echo "$python_cmd"
        return 0
    fi
    
    log_warn "Python $MIN_PYTHON_VERSION+ not found. Installing..."
    
    local os
    os=$(detect_os)
    
    case "$os" in
        macos)
            install_python_macos
            ;;
        linux|wsl)
            install_python_linux
            ;;
        *)
            log_error "Cannot auto-install Python on this OS. Please install Python $MIN_PYTHON_VERSION+ manually."
            return 1
            ;;
    esac
    
    # Try to find Python again
    if python_cmd=$(find_python); then
        log_success "Python installed successfully"
        echo "$python_cmd"
        return 0
    fi
    
    log_error "Failed to install Python. Please install Python $MIN_PYTHON_VERSION+ manually."
    return 1
}

# Ensure pip is available
ensure_pip() {
    local python_cmd="$1"
    
    log_info "Checking pip..."
    
    if "$python_cmd" -m pip --version &>/dev/null; then
        log_success "pip is available"
        return 0
    fi
    
    log_step "Installing pip..."
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would install pip"
        return 0
    fi
    
    # Try ensurepip first
    if "$python_cmd" -m ensurepip --upgrade &>/dev/null; then
        log_success "pip installed via ensurepip"
        return 0
    fi
    
    # Fall back to get-pip.py
    curl -fsSL https://bootstrap.pypa.io/get-pip.py | "$python_cmd"
    log_success "pip installed via get-pip.py"
}

# Create virtual environment
create_venv() {
    local python_cmd="$1"
    local venv_dir="${2:-$HOME/.praisonai/venv}"
    
    if [[ "$SKIP_VENV" == "1" ]]; then
        log_info "Skipping virtual environment (PRAISONAI_SKIP_VENV=1)"
        return 0
    fi
    
    log_info "Creating virtual environment..."
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would create venv at: $venv_dir"
        return 0
    fi
    
    mkdir -p "$(dirname "$venv_dir")"
    
    if [[ -d "$venv_dir" ]]; then
        log_step "Virtual environment already exists at $venv_dir"
    else
        "$python_cmd" -m venv "$venv_dir"
        log_success "Virtual environment created at $venv_dir"
    fi
    
    echo "$venv_dir"
}

# Install PraisonAI
install_praisonai() {
    local python_cmd="$1"
    local venv_dir="$2"
    
    log_info "Installing PraisonAI..."
    
    local pip_cmd="$python_cmd -m pip"
    
    # Use venv pip if available
    if [[ -n "$venv_dir" && -f "$venv_dir/bin/pip" ]]; then
        pip_cmd="$venv_dir/bin/pip"
    elif [[ -n "$venv_dir" && -f "$venv_dir/Scripts/pip.exe" ]]; then
        pip_cmd="$venv_dir/Scripts/pip.exe"
    fi
    
    # Build install command
    local install_pkg="praisonaiagents"
    if [[ "$VERSION" != "latest" ]]; then
        install_pkg="praisonaiagents==$VERSION"
    fi
    
    # Add extras if specified
    if [[ -n "$EXTRAS" ]]; then
        install_pkg="praisonaiagents[$EXTRAS]"
        if [[ "$VERSION" != "latest" ]]; then
            install_pkg="praisonaiagents[$EXTRAS]==$VERSION"
        fi
    fi
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would run: $pip_cmd install --upgrade $install_pkg"
        return 0
    fi
    
    # Upgrade pip first
    $pip_cmd install --upgrade pip
    
    # Install PraisonAI
    $pip_cmd install --upgrade "$install_pkg"
    
    # Also install the wrapper if extras include ui/chat/code
    if [[ "$EXTRAS" == *"ui"* ]] || [[ "$EXTRAS" == *"chat"* ]] || [[ "$EXTRAS" == *"code"* ]]; then
        local wrapper_pkg="praisonai[$EXTRAS]"
        if [[ "$VERSION" != "latest" ]]; then
            wrapper_pkg="praisonai[$EXTRAS]==$VERSION"
        fi
        $pip_cmd install --upgrade "$wrapper_pkg"
    fi
    
    log_success "PraisonAI installed successfully!"
}

# Setup shell PATH
setup_shell_path() {
    local venv_dir="$1"
    
    if [[ "$SKIP_VENV" == "1" ]] || [[ -z "$venv_dir" ]]; then
        return 0
    fi
    
    log_info "Setting up shell PATH..."
    
    local bin_dir="$venv_dir/bin"
    if [[ ! -d "$bin_dir" ]]; then
        bin_dir="$venv_dir/Scripts"
    fi
    
    local shell_rc=""
    case "$SHELL" in
        */zsh)
            shell_rc="$HOME/.zshrc"
            ;;
        */bash)
            if [[ -f "$HOME/.bash_profile" ]]; then
                shell_rc="$HOME/.bash_profile"
            else
                shell_rc="$HOME/.bashrc"
            fi
            ;;
        */fish)
            shell_rc="$HOME/.config/fish/config.fish"
            ;;
        *)
            shell_rc="$HOME/.profile"
            ;;
    esac
    
    local path_line="export PATH=\"$bin_dir:\$PATH\""
    if [[ "$SHELL" == */fish ]]; then
        path_line="set -gx PATH $bin_dir \$PATH"
    fi
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would add to $shell_rc: $path_line"
        return 0
    fi
    
    # Check if already in rc file
    if grep -q "$bin_dir" "$shell_rc" 2>/dev/null; then
        log_step "PATH already configured in $shell_rc"
    else
        echo "" >> "$shell_rc"
        echo "# PraisonAI" >> "$shell_rc"
        echo "$path_line" >> "$shell_rc"
        log_success "Added PraisonAI to PATH in $shell_rc"
    fi
    
    # Export for current session
    export PATH="$bin_dir:$PATH"
}

# Verify installation
verify_installation() {
    local venv_dir="$1"
    
    log_info "Verifying installation..."
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would verify installation"
        return 0
    fi
    
    local python_cmd="python3"
    if [[ -n "$venv_dir" && -f "$venv_dir/bin/python" ]]; then
        python_cmd="$venv_dir/bin/python"
    elif [[ -n "$venv_dir" && -f "$venv_dir/Scripts/python.exe" ]]; then
        python_cmd="$venv_dir/Scripts/python.exe"
    fi
    
    # Check import
    if $python_cmd -c "import praisonaiagents; print(f'Version: {praisonaiagents.__version__}')" 2>/dev/null; then
        log_success "PraisonAI agents package verified"
    else
        log_error "Failed to import praisonaiagents"
        return 1
    fi
    
    # Check CLI if wrapper installed
    if command_exists praisonai; then
        local cli_version
        cli_version=$(praisonai --version 2>/dev/null | head -n1 || echo "unknown")
        log_success "CLI available: praisonai $cli_version"
    fi
}

# Print next steps
print_next_steps() {
    local venv_dir="$1"
    
    echo ""
    echo -e "${BOLD}${GREEN}Installation complete!${NC}"
    echo ""
    echo -e "${BOLD}Next steps:${NC}"
    echo ""
    
    if [[ -n "$venv_dir" ]] && [[ "$SKIP_VENV" != "1" ]]; then
        echo "  1. Activate the virtual environment:"
        if [[ "$SHELL" == */fish ]]; then
            echo -e "     ${CYAN}source $venv_dir/bin/activate.fish${NC}"
        else
            echo -e "     ${CYAN}source $venv_dir/bin/activate${NC}"
        fi
        echo ""
        echo "  2. Or restart your terminal to use PraisonAI globally"
        echo ""
    fi
    
    echo "  Quick start:"
    echo -e "     ${CYAN}python -c \"from praisonaiagents import Agent; Agent(name='test').start('Hello!')\"${NC}"
    echo ""
    echo "  Documentation:"
    echo -e "     ${CYAN}https://docs.praison.ai${NC}"
    echo ""
    echo "  Set your API key:"
    echo -e "     ${CYAN}export OPENAI_API_KEY=your_key${NC}"
    echo ""
}

# Print help
print_help() {
    echo "PraisonAI Installer"
    echo ""
    echo "Usage: curl -fsSL https://praison.ai/install.sh | bash"
    echo "       curl -fsSL https://praison.ai/install.sh | bash -s -- [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --version VERSION    Install specific version (default: latest)"
    echo "  --extras EXTRAS      Install with extras (e.g., ui,chat,code)"
    echo "  --no-venv            Skip virtual environment creation"
    echo "  --python PATH        Use specific Python executable"
    echo "  --dry-run            Print what would happen without making changes"
    echo "  --no-prompt          Skip interactive prompts"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  PRAISONAI_VERSION    Specific version to install"
    echo "  PRAISONAI_EXTRAS     Comma-separated extras"
    echo "  PRAISONAI_NO_PROMPT  Skip interactive prompts (1 to enable)"
    echo "  PRAISONAI_DRY_RUN    Print what would happen (1 to enable)"
    echo "  PRAISONAI_PYTHON     Path to Python executable"
    echo "  PRAISONAI_SKIP_VENV  Skip virtual environment (1 to enable)"
    echo ""
    echo "Examples:"
    echo "  # Basic install"
    echo "  curl -fsSL https://praison.ai/install.sh | bash"
    echo ""
    echo "  # Install with UI extras"
    echo "  curl -fsSL https://praison.ai/install.sh | bash -s -- --extras ui,chat"
    echo ""
    echo "  # Install specific version"
    echo "  curl -fsSL https://praison.ai/install.sh | bash -s -- --version 0.14.0"
    echo ""
    echo "  # Dry run"
    echo "  curl -fsSL https://praison.ai/install.sh | bash -s -- --dry-run"
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version)
                VERSION="$2"
                shift 2
                ;;
            --extras)
                EXTRAS="$2"
                shift 2
                ;;
            --no-venv)
                SKIP_VENV="1"
                shift
                ;;
            --python)
                PYTHON_CMD="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="1"
                shift
                ;;
            --no-prompt)
                NO_PROMPT="1"
                shift
                ;;
            -h|--help)
                print_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                print_help
                exit 1
                ;;
        esac
    done
}

# Main installation function
main() {
    parse_args "$@"
    
    print_banner
    
    local os
    os=$(detect_os)
    log_info "Detected OS: $os"
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_warn "Running in DRY RUN mode - no changes will be made"
    fi
    
    # Ensure Python
    local python_cmd
    python_cmd=$(ensure_python)
    
    # Ensure pip
    ensure_pip "$python_cmd"
    
    # Create virtual environment
    local venv_dir=""
    if [[ "$SKIP_VENV" != "1" ]]; then
        venv_dir=$(create_venv "$python_cmd")
    fi
    
    # Install PraisonAI
    install_praisonai "$python_cmd" "$venv_dir"
    
    # Setup PATH
    setup_shell_path "$venv_dir"
    
    # Verify installation
    verify_installation "$venv_dir"
    
    # Print next steps
    print_next_steps "$venv_dir"
}

# Run main
main "$@"
