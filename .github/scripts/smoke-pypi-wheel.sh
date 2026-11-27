#!/usr/bin/env bash
set -euo pipefail

package="${1:?expected a PyPI distribution name}"
version="${2:?expected a candidate version}"
module="${package//-/_}"

shopt -s nullglob
wheels=("$PWD/dist/$module-$version"-*.whl)
if (( ${#wheels[@]} != 1 )); then
  printf 'Expected one wheel for %s==%s, found %s\n' "$package" "$version" "${#wheels[@]}" >&2
  exit 1
fi
wheel="${wheels[0]}"

smoke_dir=$(mktemp -d)
trap 'rm -rf "$smoke_dir"' EXIT
cd "$smoke_dir"

# Package code and build dependencies run without the release credentials.
clean() {
  env -i PATH="$PATH" PRAISONAI_HOME="$smoke_dir/praisonai" \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    XDG_CONFIG_HOME="$smoke_dir/config" XDG_DATA_HOME="$smoke_dir/data" "$@"
}

smoke_install() {
  local venv="$1"
  local python="$venv/bin/python"
  clean uv --no-config venv --python 3.11 "$venv"
  if [[ $# == 2 ]]; then
    clean uv --no-config pip install --python "$python" "$2"
  fi
  clean uv --no-config pip install --python "$python" "$wheel"
  clean uv --no-config pip check --python "$python"
  clean "$python" -I -c '
import sys
from importlib import import_module, metadata

distribution, module, expected = sys.argv[1:]
installed = metadata.version(distribution)
assert installed == expected, f"{distribution}: installed {installed}, expected {expected}"
import_module(module)
' "$package" "$module" "$version"
  if [[ "$package" != praisonaiagents ]]; then
    clean "$venv/bin/$package" --help > /dev/null
  fi
}

smoke_install "$smoke_dir/fresh"
if [[ "$package" == praisonai ]]; then
  smoke_install "$smoke_dir/upgrade" "praisonai<$version"
fi
