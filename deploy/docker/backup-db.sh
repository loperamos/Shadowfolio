#!/usr/bin/env bash
# Backs up the Docker app's database to a folder on this machine, keeping the last KEEP_DAYS days.
# Uses SQLite's online backup inside the running container, so the copy is consistent while the app is in use.
# Run from anywhere: ./deploy/docker/backup-db.sh   (or daily, with install-backup-timer.sh)
# Where: SHADOWFOLIO_BACKUP_DIR, default ~/shadowfolio-backups. It is on the same disk as the volume: it guards
# against mistakes and a damaged database, not a failed disk; copy the folder off this machine for that.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$here/../.." && pwd)"
backup_dir="${SHADOWFOLIO_BACKUP_DIR:-${HOME:?HOME is not set}/shadowfolio-backups}"
keep_days=14
stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
inside="/data/backup-$stamp.db"  # the copy, made inside the container's volume first

mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
cd "$repo_dir"

docker compose exec -T app python - "$inside" <<'PY'
import sqlite3
import sys

source, copy = sqlite3.connect("file:/data/shadowfolio.db?mode=ro", uri=True), sqlite3.connect(sys.argv[1])
source.backup(copy)
copy.close()
source.close()
PY
docker compose cp "app:$inside" "$backup_dir/shadowfolio-$stamp.db"
docker compose exec -T app python -c "import os, sys; os.remove(sys.argv[1])" "$inside"
chmod 600 "$backup_dir/shadowfolio-$stamp.db"

# Only this script's own backups, by name, older than keep_days.
find "$backup_dir" -maxdepth 1 -type f -name 'shadowfolio-*.db' -mtime "+$keep_days" -delete
echo "Backed up to $backup_dir/shadowfolio-$stamp.db"
