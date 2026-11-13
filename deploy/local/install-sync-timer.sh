#!/usr/bin/env bash
# Installs the daily sync as a systemd user timer (no root needed). Run from anywhere: ./deploy/local/install-sync-timer.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$here/../.." && pwd)"
units_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$units_dir"
sed "s|@REPO_DIR@|$repo_dir|g" "$here/shadowfolio-sync.service" > "$units_dir/shadowfolio-sync.service"
cp "$here/shadowfolio-sync.timer" "$units_dir/shadowfolio-sync.timer"
systemctl --user daemon-reload
systemctl --user enable --now shadowfolio-sync.timer
systemctl --user list-timers shadowfolio-sync.timer --no-pager
