#!/usr/bin/env bash
# Host side: remove the sandbox and provider created by bring-up.sh.
set -uo pipefail

NAME="${NAME:-praisonai-demo}"
openshell sandbox delete "$NAME" || true
openshell provider delete "$NAME" || true
echo "The gateway's inference route still names provider '$NAME'."
echo "Point it at another provider with 'openshell inference set', or remove the dedicated gateway."
