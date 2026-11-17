#!/usr/bin/env bash
# Stops and removes the daily backup's systemd user timer installed by install-backup-timer.sh. Leaves the backups.
set -euo pipefail

config_home="${XDG_CONFIG_HOME:-${HOME:?HOME is not set}/.config}"
units_dir="$config_home/systemd/user"

systemctl --user disable --now shadowfolio-backup.timer 2>/dev/null || true
# Only these two files, by full name.
rm -f -- "$units_dir/shadowfolio-backup.timer" "$units_dir/shadowfolio-backup.service"
systemctl --user daemon-reload
systemctl --user reset-failed shadowfolio-backup.service 2>/dev/null || true
echo "Removed the shadowfolio-backup timer."
