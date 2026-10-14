#!/bin/sh
set -eu
PATCH_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_DIR=$(mktemp -d "${TMPDIR:-/tmp}/hyprpaper-persistent.XXXXXX")
trap 'rm -rf "$BUILD_DIR"' EXIT HUP INT TERM
git clone --depth 1 --branch v0.8.4 https://github.com/hyprwm/hyprpaper.git "$BUILD_DIR/source"
test "$(git -C "$BUILD_DIR/source" rev-parse HEAD)" = 20fc0fa6c2056c388a4cd69cb394a9f989dd27c0
git -C "$BUILD_DIR/source" apply "$PATCH_DIR/persistent-surface.patch"
cmake -S "$BUILD_DIR/source" -B "$BUILD_DIR/build" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR/build" -j 2
install -Dm755 "$BUILD_DIR/build/hyprpaper" "$HOME/.local/libexec/hyprpaper-persistent"
printf '%s\n' 'Built ~/.local/libexec/hyprpaper-persistent. Restart hyprpaper.service to use it.'
