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

# Append an export line to a single rc file, idempotently. Returns 0 on success.
_append_path_line() {
  rc="$1"
  line="$2"
  [ -n "${rc}" ] || return 1
  if [ -f "${rc}" ] && grep -Fq "${bindir}" "${rc}" 2>/dev/null; then
    return 0
  fi
  printf '\n# Added by PraisonAI installer\n%s\n' "${line}" >>"${rc}" 2>/dev/null
}

wire_path_dispatch() {
  bindir="$1"
  shell_name="$(basename "${SHELL:-sh}")"
  updated=""

  case "${shell_name}" in
    zsh)
      line="export PATH=\"${bindir}:\$PATH\""
      _append_path_line "${HOME}/.zshrc" "${line}" && updated="${HOME}/.zshrc"
      ;;
    fish)
      mkdir -p "${HOME}/.config/fish" 2>/dev/null || true
      rc="${HOME}/.config/fish/config.fish"
      # `fish_add_path` is unavailable on older fish; guard it and provide a
      # POSIX-safe fallback so PATH is wired regardless of fish version.
      line="if type -q fish_add_path; fish_add_path ${bindir}; else; set -gx PATH ${bindir} \$PATH; end"
      _append_path_line "${rc}" "${line}" && updated="${rc}"
      ;;
    bash)
      # Interactive non-login shells read ~/.bashrc; login shells read the
      # first existing of ~/.bash_profile, ~/.bash_login, ~/.profile. Wire the
      # interactive rc and whichever login profile applies so both work.
      line="export PATH=\"${bindir}:\$PATH\""
      _append_path_line "${HOME}/.bashrc" "${line}" && updated="${HOME}/.bashrc"
      if [ -f "${HOME}/.bash_profile" ]; then
        login_rc="${HOME}/.bash_profile"
      elif [ -f "${HOME}/.bash_login" ]; then
        login_rc="${HOME}/.bash_login"
      else
        login_rc="${HOME}/.profile"
      fi
      _append_path_line "${login_rc}" "${line}" \
        && updated="${updated:+${updated} }${login_rc}"
      ;;
    *)
      line="export PATH=\"${bindir}:\$PATH\""
      _append_path_line "${HOME}/.profile" "${line}" && updated="${HOME}/.profile"
      ;;
  esac

  if [ -n "${updated}" ]; then
    info "Added ${bindir} to PATH in ${updated} (restart your shell to apply)."
  else
    warn "Could not update your shell profile; add ${bindir} to your PATH manually."
  fi
}

# Add a directory to PATH in the user's shell rc file(s), idempotently.
wire_path() {
  bindir="$1"
  case ":${PATH}:" in
    *":${bindir}:"*) return 0 ;;
  esac
  wire_path_dispatch "${bindir}"
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
  # Download the installer to a file first so a failed/empty download (which a
  # piped `curl | sh` can silently swallow) surfaces here with a useful message
  # instead of a later confusing `uv: command not found`.
  tmp_installer="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/uv-install.$$.sh")"
  if ! curl -fsSL https://astral.sh/uv/install.sh -o "${tmp_installer}" \
      || [ ! -s "${tmp_installer}" ]; then
    rm -f "${tmp_installer}" 2>/dev/null || true
    err "Failed to download the uv bootstrap installer (network/DNS issue?)."
    err "Install uv or pipx manually, then re-run this installer:"
    err "  https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
  fi
  sh "${tmp_installer}"
  rm -f "${tmp_installer}" 2>/dev/null || true

  # uv installs to ~/.local/bin or ~/.cargo/bin depending on platform.
  if [ -x "${HOME}/.local/bin/uv" ]; then
    PATH="${HOME}/.local/bin:${PATH}"
  elif [ -x "${HOME}/.cargo/bin/uv" ]; then
    PATH="${HOME}/.cargo/bin:${PATH}"
  fi
  export PATH

  # Verify the bootstrap actually produced a working `uv`; otherwise fail loudly
  # instead of proceeding to `uv tool install` with no uv on PATH.
  if ! has uv; then
    err "uv bootstrap completed but 'uv' is not on PATH."
    err "Open a new shell or install uv/pipx manually, then re-run this installer."
    exit 1
  fi
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
