#!/usr/bin/env bash
# PraisonAI Installer
# Works on macOS, Linux, and Windows (WSL)
# Usage: curl -fsSL https://praison.ai/install.sh | bash
#
# Environment variables:
#   PRAISONAI_VERSION       - Specific version to install (default: latest)
#   PRAISONAI_EXTRAS        - Comma-separated extras (e.g., "ui,chat,code")
#   PRAISONAI_NO_PROMPT     - Skip interactive prompts (1 to enable)
#   PRAISONAI_DRY_RUN       - Print what would happen without making changes
#   PRAISONAI_PYTHON        - Path to Python executable
#   PRAISONAI_SKIP_VENV     - Skip virtual environment creation (1 to enable)
#   PRAISONAI_INSTALL_DIR   - Base dir for the fallback venv (default: ~/.praisonai)
#   PRAISONAI_BACKEND       - Force isolation backend: uv | pipx | venv (default: auto)
#   PRAISONAI_NO_MODIFY_PATH - Do not append a PATH block to the shell rc (1 to enable)
#
# Isolation backend preference order (auto): uv tool -> pipx -> venv fallback.
# All paths keep the CLI isolated from the user's active/global Python env and
# expose a `praisonai` shim on PATH via ~/.local/bin.

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
NO_ONBOARD="${PRAISONAI_NO_ONBOARD:-0}"
INSTALL_DIR="${PRAISONAI_INSTALL_DIR:-$HOME/.praisonai}"
BACKEND="${PRAISONAI_BACKEND:-auto}"
NO_MODIFY_PATH="${PRAISONAI_NO_MODIFY_PATH:-0}"
SHIM_DIR="$HOME/.local/bin"
MIN_PYTHON_VERSION="3.10"

# Set by the isolation backends so onboarding/verification can find the
# isolated `praisonai` executable without relying on PATH being refreshed.
PRAISONAI_BIN=""

# Set to 1 inside maybe_offer_bot_onboarding() when the bot wizard
# succeeds. The wizard already prints a complete "✅ Done" panel with
# the dashboard URL, bot-start command, gateway endpoints and doctor
# hints — so we suppress the installer's own next-steps block to avoid
# showing a second, partially duplicated summary after it.
BOT_ONBOARDED=0

# Logging functions - all output to stderr to avoid capturing in $()
log_info() {
    echo -e "${BLUE}==>${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}✓${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1" >&2
}

log_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

log_step() {
    echo -e "${CYAN}→${NC} $1" >&2
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
            # Download and verify Homebrew installer
            HOMEBREW_INSTALLER="/tmp/homebrew-install.sh"
            curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$HOMEBREW_INSTALLER"
            if [[ -f "$HOMEBREW_INSTALLER" ]]; then
                /bin/bash "$HOMEBREW_INSTALLER"
                rm -f "$HOMEBREW_INSTALLER"
            else
                log_error "Failed to download Homebrew installer"
                exit 1
            fi
            
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

# Build the pip/uv/pipx package spec (e.g. "praisonai[all]==1.2.3").
build_package_spec() {
    local pkg="praisonai"

    if [[ -n "$EXTRAS" ]]; then
        pkg="praisonai[$EXTRAS]"
    else
        # Default to the full experience for curl|bash installs.
        pkg="praisonai[all]"
    fi

    if [[ "$VERSION" != "latest" ]]; then
        pkg="${pkg}==${VERSION}"
    fi

    echo "$pkg"
}

# Decide which isolation backend to use. Honour PRAISONAI_BACKEND when set,
# otherwise prefer `uv tool` -> `pipx` -> venv fallback.
detect_backend() {
    if [[ "$SKIP_VENV" == "1" ]]; then
        echo "system"
        return 0
    fi

    case "$BACKEND" in
        uv|pipx|venv|system)
            echo "$BACKEND"
            return 0
            ;;
        auto)
            ;;
        *)
            log_error "Unknown backend '$BACKEND'. Valid values: uv, pipx, venv, system, auto."
            exit 1
            ;;
    esac

    if command_exists uv; then
        echo "uv"
    elif command_exists pipx; then
        echo "pipx"
    else
        echo "venv"
    fi
}

# Install via `uv tool install` (fully isolated, fast). uv manages its own
# bin dir and PATH; we still surface the resolved shim for verification.
install_with_uv() {
    local pkg="$1"

    log_info "Installing PraisonAI with uv (isolated tool)..."

    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would run: uv tool install --force $pkg"
        return 0
    fi

    uv tool install --force "$pkg"
    uv tool update-shell 2>/dev/null || true

    local bin=""
    bin="$(command -v praisonai 2>/dev/null || true)"
    if [[ -z "$bin" && -x "$HOME/.local/bin/praisonai" ]]; then
        bin="$HOME/.local/bin/praisonai"
    fi
    PRAISONAI_BIN="$bin"
    log_success "PraisonAI installed via uv"
}

# Install via `pipx install` (isolated persistent venv managed by pipx).
install_with_pipx() {
    local pkg="$1"

    log_info "Installing PraisonAI with pipx (isolated)..."

    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would run: pipx install --force $pkg"
        return 0
    fi

    pipx install --force "$pkg"
    pipx ensurepath 2>/dev/null || true

    local bin=""
    bin="$(command -v praisonai 2>/dev/null || true)"
    if [[ -z "$bin" && -x "$HOME/.local/bin/praisonai" ]]; then
        bin="$HOME/.local/bin/praisonai"
    fi
    PRAISONAI_BIN="$bin"
    log_success "PraisonAI installed via pipx"
}

# Create a non-destructive shim in ~/.local/bin pointing at an isolated
# `praisonai` executable (used by the venv fallback). uv/pipx manage their
# own shims, so this only runs for the venv backend.
create_shim() {
    local target="$1"

    if [[ -z "$target" ]]; then
        return 0
    fi

    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would link shim: $SHIM_DIR/praisonai -> $target"
        return 0
    fi

    mkdir -p "$SHIM_DIR"
    ln -sf "$target" "$SHIM_DIR/praisonai"
    PRAISONAI_BIN="$SHIM_DIR/praisonai"
    log_success "Linked praisonai shim into $SHIM_DIR"
}

# Create virtual environment
create_venv() {
    local python_cmd="$1"
    local venv_dir="${2:-$INSTALL_DIR/venv}"
    
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
    
    # Build install command - default is praisonai[all] for full experience
    local install_pkg="praisonai[all]"
    if [[ "$VERSION" != "latest" ]]; then
        install_pkg="praisonai[all]==$VERSION"
    fi
    
    # Override extras if specified
    if [[ -n "$EXTRAS" ]]; then
        install_pkg="praisonai[$EXTRAS]"
        if [[ "$VERSION" != "latest" ]]; then
            install_pkg="praisonai[$EXTRAS]==$VERSION"
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

# Detect the shell rc file to modify for PATH.
detect_shell_rc() {
    case "$SHELL" in
        */zsh)
            echo "$HOME/.zshrc"
            ;;
        */bash)
            if [[ -f "$HOME/.bash_profile" ]]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        */fish)
            echo "$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "$HOME/.profile"
            ;;
    esac
}

# Ensure a directory is on PATH for the current session and, unless
# --no-modify-path is set, appended non-destructively to the shell rc
# inside a clearly-marked PraisonAI block.
ensure_path_dir() {
    local bin_dir="$1"

    if [[ -z "$bin_dir" ]]; then
        return 0
    fi

    # Export for current session regardless of rc modification.
    export PATH="$bin_dir:$PATH"

    if [[ "$NO_MODIFY_PATH" == "1" ]]; then
        log_info "Skipping PATH modification (--no-modify-path). Add to PATH: $bin_dir"
        return 0
    fi

    local shell_rc
    shell_rc="$(detect_shell_rc)"

    local path_line="export PATH=\"$bin_dir:\$PATH\""
    if [[ "$SHELL" == */fish ]]; then
        path_line="set -gx PATH $bin_dir \$PATH"
    fi

    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would add to $shell_rc: $path_line"
        return 0
    fi

    if grep -q "$bin_dir" "$shell_rc" 2>/dev/null; then
        log_step "PATH already configured in $shell_rc"
    else
        mkdir -p "$(dirname "$shell_rc")"
        {
            echo ""
            echo "# >>> PraisonAI PATH >>>"
            echo "$path_line"
            echo "# <<< PraisonAI PATH <<<"
        } >> "$shell_rc"
        log_success "Added PraisonAI to PATH in $shell_rc"
    fi
}

# Setup shell PATH (venv backend). uv/pipx already place their shims under
# ~/.local/bin, which we also ensure is on PATH for all backends in main().
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

    ensure_path_dir "$bin_dir"
}

# Resolve a usable `praisonai` invocation: prefer the backend-recorded bin,
# then PATH, then the venv python module fallback.
resolve_praisonai_cmd() {
    local venv_dir="$1"

    if [[ -n "$PRAISONAI_BIN" && -x "$PRAISONAI_BIN" ]]; then
        echo "$PRAISONAI_BIN"
        return 0
    fi

    if command_exists praisonai; then
        command -v praisonai
        return 0
    fi

    if [[ -n "$venv_dir" && -x "$venv_dir/bin/praisonai" ]]; then
        echo "$venv_dir/bin/praisonai"
        return 0
    fi

    return 1
}

# Offer to install shell completions using `praisonai completion <shell>`.
maybe_install_completions() {
    local venv_dir="$1"

    if [[ "$NO_ONBOARD" == "1" || "$NO_PROMPT" == "1" || "$DRY_RUN" == "1" ]]; then
        return 0
    fi

    local praisonai_cmd
    if ! praisonai_cmd="$(resolve_praisonai_cmd "$venv_dir")"; then
        return 0
    fi

    local shell_name="${SHELL##*/}"
    case "$shell_name" in
        bash|zsh|fish) ;;
        *)
            return 0
            ;;
    esac

    local target=""
    case "$shell_name" in
        bash)
            target="$HOME/.bashrc"
            ;;
        zsh)
            target="$HOME/.zshrc"
            ;;
        fish)
            target="$HOME/.config/fish/completions/praisonai.fish"
            ;;
    esac

    if [ -e /dev/tty ] && [ -t 1 ]; then
        echo ""
        echo -ne "${CYAN}Install ${shell_name} shell completions for praisonai? [Y/n] ${NC}"
        local yn=""
        read -r yn < /dev/tty || yn=""
        case "$yn" in
            [nN]*)
                log_info "Skipped — run 'praisonai completion ${shell_name}' anytime."
                return 0
                ;;
        esac
    else
        # Non-interactive but prompts allowed: skip silently.
        return 0
    fi

    if [[ "$shell_name" == "fish" ]]; then
        mkdir -p "$(dirname "$target")"
        if "$praisonai_cmd" completion fish > "$target" 2>/dev/null; then
            log_success "Installed fish completions to $target"
        else
            log_warn "Could not install fish completions — run 'praisonai completion fish' manually."
        fi
    else
        if grep -q "_praisonai_completion\|#compdef praisonai" "$target" 2>/dev/null; then
            log_step "Completions already present in $target"
            return 0
        fi
        if "$praisonai_cmd" completion "$shell_name" >> "$target" 2>/dev/null; then
            log_success "Installed ${shell_name} completions to $target"
        else
            log_warn "Could not install completions — run 'praisonai completion ${shell_name}' manually."
        fi
    fi
}

# Verify installation
verify_installation() {
    local venv_dir="$1"
    
    log_info "Verifying installation..."
    
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "[DRY RUN] Would verify installation"
        return 0
    fi
    
    # Resolve the interpreter that owns the installed package. For the venv
    # fallback this is the venv python; for uv/pipx the package lives in an
    # isolated environment, NOT the system python3, so importing with the
    # system interpreter would always fail. In that case verify via the
    # resolved `praisonai` CLI instead.
    local python_cmd=""
    if [[ -n "$venv_dir" && -f "$venv_dir/bin/python" ]]; then
        python_cmd="$venv_dir/bin/python"
    elif [[ -n "$venv_dir" && -f "$venv_dir/Scripts/python.exe" ]]; then
        python_cmd="$venv_dir/Scripts/python.exe"
    fi

    # Resolve a usable CLI for both verification fallback and version output.
    local praisonai_cmd=""
    praisonai_cmd="$(resolve_praisonai_cmd "$venv_dir" 2>/dev/null || true)"

    if [[ -n "$python_cmd" ]]; then
        # venv backend: check the import directly against the venv python.
        if $python_cmd -c "from praisonaiagents import Agent; print('Import successful')" 2>/dev/null; then
            log_success "PraisonAI agents package verified"
        else
            log_error "Failed to import praisonaiagents"
            return 1
        fi
    elif [[ -n "$praisonai_cmd" && -x "$praisonai_cmd" ]]; then
        # uv/pipx backend (isolated env): a working CLI is sufficient proof.
        log_success "PraisonAI CLI verified ($praisonai_cmd)"
    else
        log_error "Could not verify installation: praisonai CLI not found"
        return 1
    fi

    # Check CLI version if available.
    if [[ -n "$praisonai_cmd" && -x "$praisonai_cmd" ]]; then
        local cli_version
        cli_version=$("$praisonai_cmd" --version 2>/dev/null | head -n1 || echo "unknown")
        log_success "CLI available: praisonai $cli_version"
    elif command_exists praisonai; then
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
    
    echo "  Set up a messaging bot (Telegram / Discord / Slack / WhatsApp):"
    echo -e "     ${CYAN}praisonai onboard${NC}"
    echo ""
    echo "  Open the dashboard UI (localhost only):"
    echo -e "     ${CYAN}praisonai claw${NC}    ${BOLD}→${NC} http://127.0.0.1:8082"
    echo ""
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
    echo "  --backend BACKEND    Force isolation backend: uv, pipx, or venv (default: auto)"
    echo "  --install-dir DIR    Base dir for the venv fallback (default: ~/.praisonai)"
    echo "  --no-modify-path     Do not append a PATH block to your shell rc"
    echo "  --no-venv            Skip isolation; install into the active environment"
    echo "  --no-onboard         Skip interactive onboarding after install"
    echo "  --python PATH        Use specific Python executable"
    echo "  --dry-run            Print what would happen without making changes"
    echo "  --no-prompt          Skip interactive prompts"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  PRAISONAI_VERSION     Specific version to install"
    echo "  PRAISONAI_EXTRAS      Comma-separated extras"
    echo "  PRAISONAI_NO_ONBOARD  Skip interactive onboarding (1 to enable)"
    echo "  PRAISONAI_NO_PROMPT  Skip interactive prompts (1 to enable)"
    echo "  PRAISONAI_DRY_RUN    Print what would happen (1 to enable)"
    echo "  PRAISONAI_PYTHON     Path to Python executable"
    echo "  PRAISONAI_SKIP_VENV  Skip virtual environment (1 to enable)"
    echo "  PRAISONAI_INSTALL_DIR    Base dir for the venv fallback"
    echo "  PRAISONAI_BACKEND        Force backend: uv, pipx, venv"
    echo "  PRAISONAI_NO_MODIFY_PATH Skip shell rc PATH modification (1 to enable)"
    echo ""
    echo "Examples:"
    echo "  # Basic install (isolated: uv tool -> pipx -> venv)"
    echo "  curl -fsSL https://praison.ai/install.sh | bash"
    echo ""
    echo "  # Install with UI extras"
    echo "  curl -fsSL https://praison.ai/install.sh | bash -s -- --extras ui,chat"
    echo ""
    echo "  # Force pipx and don't touch PATH"
    echo "  curl -fsSL https://praison.ai/install.sh | bash -s -- --backend pipx --no-modify-path"
    echo ""
    echo "  # Dry run"
    echo "  curl -fsSL https://praison.ai/install.sh | bash -s -- --dry-run"
    echo ""
    echo "Power-user alternatives (no installer needed):"
    echo "  uvx praisonai \"2+2\"        # zero-install one-shot via uv"
    echo "  pipx install praisonai      # isolated persistent install"
    echo "  pip install praisonai       # install into the active environment"
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
            --backend)
                BACKEND="$2"
                shift 2
                ;;
            --install-dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --no-modify-path)
                NO_MODIFY_PATH="1"
                shift
                ;;
            --no-onboard)
                NO_ONBOARD="1"
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

# Run onboarding after successful installation
run_onboarding() {
    local venv_dir="$1"
    
    # Skip onboarding if requested
    if [[ "$NO_ONBOARD" == "1" ]]; then
        log_info "Skipping onboarding (--no-onboard)"
        return 0
    fi
    
    # Skip onboarding in non-interactive environments
    if [[ "$NO_PROMPT" == "1" ]]; then
        log_info "Skipping onboarding (non-interactive mode)"
        return 0
    fi
    
    # Check if TTY is available (required for interactive setup)
    if ! [ -e /dev/tty ] || ! [ -t 1 ]; then
        log_info "No TTY available — skipping onboarding. Run 'praisonai setup' later."
        return 0
    fi
    
    # Skip onboarding in dry run mode
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "Dry run mode — skipping onboarding"
        return 0
    fi
    
    log_step "Starting interactive setup wizard..."
    
    # Prefer venv python, then user-specified, then system python3
    local py=""
    if [[ -n "$venv_dir" && "$SKIP_VENV" != "1" && -x "$venv_dir/bin/python" ]]; then
        py="$venv_dir/bin/python"
    elif [[ -n "$PYTHON_CMD" ]] && command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        py="$PYTHON_CMD"
    else
        py="python3"
    fi
    
    # Run the setup wizard
    if "$py" -m praisonai setup < /dev/tty > /dev/tty 2> /dev/tty; then
        log_success "Setup wizard completed successfully!"
        echo ""
        echo -e "${BOLD}${GREEN}You're all set! 🎉${NC}"
        echo ""
    else
        log_warn "Setup wizard failed or was cancelled."
        echo ""
        echo -e "${YELLOW}Don't worry! You can run the setup wizard anytime with:${NC}"
        echo -e "  ${CYAN}praisonai setup${NC}"
        echo ""
    fi
}

# Offer bot onboarding after setup (always prompts when a TTY is available;
# default answer is Yes so curl|bash installs finish with a working bot).
maybe_offer_bot_onboarding() {
    local venv_dir="$1"

    if [[ "$NO_ONBOARD" == "1" ]]; then
        log_info "Skipping bot onboarding (--no-onboard)"
        return 0
    fi
    if [[ "$NO_PROMPT" == "1" ]]; then
        log_info "Skipping bot onboarding (non-interactive mode) — run 'praisonai onboard' later"
        return 0
    fi
    if [[ "$DRY_RUN" == "1" ]]; then
        log_info "Dry run — skipping bot onboarding"
        return 0
    fi
    if ! [ -e /dev/tty ]; then
        log_info "No TTY available — skipping bot onboarding. Run 'praisonai onboard' later."
        return 0
    fi

    # Prefer venv python, then user-specified, then system python3
    local py=""
    if [[ -n "$venv_dir" && "$SKIP_VENV" != "1" && -x "$venv_dir/bin/python" ]]; then
        py="$venv_dir/bin/python"
    elif [[ -n "$PYTHON_CMD" ]] && command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        py="$PYTHON_CMD"
    else
        py="python3"
    fi

    # Always prompt so fresh installs discover the onboard wizard too.
    # Default is Yes — users running the curl|bash installer usually want
    # to finish end-to-end. They can answer N to skip or pass --no-onboard.
    echo ""
    echo -ne "${CYAN}Set up a messaging bot (Telegram / Discord / Slack / WhatsApp) now? [Y/n] ${NC}"
    local yn=""
    read -r yn < /dev/tty || yn=""
    case "$yn" in
        [nN]*)
            log_info "Skipped — run 'praisonai onboard' anytime to set up a bot."
            ;;
        *)
            if "$py" -m praisonai onboard < /dev/tty > /dev/tty 2> /dev/tty; then
                log_success "Bot onboarding completed!"
                BOT_ONBOARDED=1
            else
                log_warn "Bot onboarding skipped or failed — you can retry with 'praisonai onboard'."
            fi
            ;;
    esac
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

    # Choose an isolation backend: uv tool -> pipx -> venv fallback.
    local backend
    backend=$(detect_backend)
    log_info "Isolation backend: $backend"

    local venv_dir=""

    case "$backend" in
        uv)
            install_with_uv "$(build_package_spec)"
            ensure_path_dir "$SHIM_DIR"
            ;;
        pipx)
            install_with_pipx "$(build_package_spec)"
            ensure_path_dir "$SHIM_DIR"
            ;;
        system)
            # No isolation requested (--no-venv): install into active env.
            local python_cmd
            python_cmd=$(ensure_python)
            ensure_pip "$python_cmd"
            install_praisonai "$python_cmd" ""
            ;;
        venv|*)
            # Fallback: isolated venv under $INSTALL_DIR, shimmed to ~/.local/bin.
            local python_cmd
            python_cmd=$(ensure_python)
            ensure_pip "$python_cmd"
            venv_dir=$(create_venv "$python_cmd")
            install_praisonai "$python_cmd" "$venv_dir"
            if [[ "$DRY_RUN" != "1" && -n "$venv_dir" && -x "$venv_dir/bin/praisonai" ]]; then
                # Shim into ~/.local/bin covers PATH; no need to also add venv/bin.
                create_shim "$venv_dir/bin/praisonai"
                ensure_path_dir "$SHIM_DIR"
            else
                # No shim (dry-run or missing binary): fall back to venv bin on PATH.
                setup_shell_path "$venv_dir"
                ensure_path_dir "$SHIM_DIR"
            fi
            ;;
    esac

    # Verify installation
    verify_installation "$venv_dir"

    # Offer to install shell completions
    maybe_install_completions "$venv_dir"
    
    # Run interactive onboarding
    run_onboarding "$venv_dir"
    
    # Offer bot onboarding
    maybe_offer_bot_onboarding "$venv_dir"

    # Print next steps only when the bot wizard did NOT run to completion.
    # When it did, its "✅ Done" panel is the final and most useful summary,
    # and appending another next-steps block creates a confusing duplicate.
    if [[ "$BOT_ONBOARDED" != "1" ]]; then
        print_next_steps "$venv_dir"
    fi
}

# Run main
main "$@"
