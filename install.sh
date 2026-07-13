#!/bin/sh
# PraisonAI one-line standalone installer.
#
#   curl -fsSL https://raw.githubusercontent.com/MervinPraison/PraisonAI/main/install.sh | sh
#
# Installs PraisonAI into a dedicated, isolated environment (via `uv tool` or
# `pipx`, auto-detecting/bootstrapping the runtime) and exposes a global
# `praisonai` command on PATH. Idempotent and safe to re-run.
#
# Options (environment variables):
#   PRAISONAI_VERSION=x.y.z   Pin a specific version (default: latest).
#   PRAISONAI_INSTALLER=uv|pipx  Force a specific tool manager.
#   PRAISONAI_NONINTERACTIVE=1   Never prompt; suitable for CI.
#
# `pip install praisonai` remains fully supported for library/embedded use;
# this installer only manages the standalone CLI binary.

set -eu

PACKAGE="praisonai"
VERSION="${PRAISONAI_VERSION:-}"
FORCED_INSTALLER="${PRAISONAI_INSTALLER:-}"
NONINTERACTIVE="${PRAISONAI_NONINTERACTIVE:-}"

info() { printf '\033[0;36m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[0;33mwarning:\033[0m %s\n' "$1" >&2; }
err() { printf '\033[0;31merror:\033[0m %s\n' "$1" >&2; }

has() { command -v "$1" >/dev/null 2>&1; }

detect_platform() {
  os="$(uname -s 2>/dev/null || echo unknown)"
  arch="$(uname -m 2>/dev/null || echo unknown)"
  info "Detected platform: ${os} ${arch}"
}

# Add a directory to PATH in the user's shell rc file, idempotently.
wire_path() {
  bindir="$1"
  case ":${PATH}:" in
    *":${bindir}:"*) return 0 ;;
  esac

  shell_name="$(basename "${SHELL:-sh}")"
  case "${shell_name}" in
    zsh) rc="${HOME}/.zshrc"; line="export PATH=\"${bindir}:\$PATH\"" ;;
    fish)
      rc="${HOME}/.config/fish/config.fish"
      line="fish_add_path ${bindir}"
      mkdir -p "${HOME}/.config/fish" 2>/dev/null || true
      ;;
    bash) rc="${HOME}/.bashrc"; line="export PATH=\"${bindir}:\$PATH\"" ;;
    *) rc="${HOME}/.profile"; line="export PATH=\"${bindir}:\$PATH\"" ;;
  esac

  if [ -f "${rc}" ] && grep -Fq "${bindir}" "${rc}" 2>/dev/null; then
    return 0
  fi
  printf '\n# Added by PraisonAI installer\n%s\n' "${line}" >>"${rc}" 2>/dev/null \
    && info "Added ${bindir} to PATH in ${rc} (restart your shell or 'source ${rc}')." \
    || warn "Could not update ${rc}; add ${bindir} to your PATH manually."
}

spec() {
  if [ -n "${VERSION}" ]; then
    printf '%s==%s' "${PACKAGE}" "${VERSION}"
  else
    printf '%s' "${PACKAGE}"
  fi
}

install_with_uv() {
  info "Installing ${PACKAGE} with 'uv tool'..."
  uv tool install --force "$(spec)"
  wire_path "${HOME}/.local/bin"
}

install_with_pipx() {
  info "Installing ${PACKAGE} with pipx..."
  pipx install --force "$(spec)"
  pipx ensurepath >/dev/null 2>&1 || true
  wire_path "${HOME}/.local/bin"
}

bootstrap_uv() {
  if [ -n "${NONINTERACTIVE}" ] || [ ! -t 0 ]; then
    info "Bootstrapping uv (isolated Python tool manager)..."
  else
    info "No uv/pipx found; bootstrapping uv..."
  fi
  curl -fsSL https://astral.sh/uv/install.sh | sh
  # uv installs to ~/.local/bin or ~/.cargo/bin depending on platform.
  if [ -x "${HOME}/.local/bin/uv" ]; then
    PATH="${HOME}/.local/bin:${PATH}"
  elif [ -x "${HOME}/.cargo/bin/uv" ]; then
    PATH="${HOME}/.cargo/bin:${PATH}"
  fi
  export PATH
}

main() {
  detect_platform

  if ! has curl; then
    err "curl is required to run this installer."
    exit 1
  fi

  case "${FORCED_INSTALLER}" in
    uv)   has uv || bootstrap_uv; install_with_uv ;;
    pipx) if has pipx; then install_with_pipx; else err "pipx requested but not installed."; exit 1; fi ;;
    "")
      if has uv; then
        install_with_uv
      elif has pipx; then
        install_with_pipx
      else
        bootstrap_uv
        install_with_uv
      fi
      ;;
    *) err "Unknown PRAISONAI_INSTALLER='${FORCED_INSTALLER}' (use uv or pipx)."; exit 1 ;;
  esac

  echo
  info "PraisonAI installed. Get started with:"
  echo "    praisonai setup"
  echo
  info "Manage it later with:"
  echo "    praisonai upgrade      # update in place"
  echo "    praisonai upgrade --check"
  echo "    praisonai uninstall    # remove cleanly"
}

main "$@"
