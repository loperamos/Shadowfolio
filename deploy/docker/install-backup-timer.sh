#!/usr/bin/env bash
# Installs the daily backup of the Docker app's database as a systemd user timer (no root needed).
# Run from anywhere: ./deploy/docker/install-backup-timer.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$here/../.." && pwd)"
units_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$units_dir"
sed "s|@REPO_DIR@|$repo_dir|g" "$here/shadowfolio-backup.service" > "$units_dir/shadowfolio-backup.service"
cp "$here/shadowfolio-backup.timer" "$units_dir/shadowfolio-backup.timer"
systemctl --user daemon-reload
systemctl --user enable --now shadowfolio-backup.timer
systemctl --user list-timers shadowfolio-backup.timer --no-pager
