#!/usr/bin/env bash
# Stops and removes the daily sync's systemd user timer installed by install-sync-timer.sh. Safe to run more than once.
set -euo pipefail

config_home="${XDG_CONFIG_HOME:-${HOME:?HOME is not set}/.config}"
units_dir="$config_home/systemd/user"

systemctl --user disable --now shadowfolio-sync.timer 2>/dev/null || true
# Only these two files, by full name.
rm -f -- "$units_dir/shadowfolio-sync.timer" "$units_dir/shadowfolio-sync.service"
systemctl --user daemon-reload
systemctl --user reset-failed shadowfolio-sync.service 2>/dev/null || true
echo "Removed the shadowfolio-sync timer."
