#!/bin/sh
# Renders the SVG sources beside this script to the 1024x1024 PNGs that
# `npx tauri icon icon/icon.json` consumes. Needs rsvg-convert (librsvg):
# `brew install librsvg` / `apt install librsvg2-bin`.
set -eu
cd "$(dirname "$0")"
for name in app-icon android-fg android-monochrome; do
  rsvg-convert -w 1024 -h 1024 "$name.svg" -o "$name.png"
done
# The adaptive-icon background is the flat brand colour, so it needs no art.
rsvg-convert -w 1024 -h 1024 -o android-bg.png <<SVG
<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024"><rect width="1024" height="1024" fill="#312E81"/></svg>
SVG
