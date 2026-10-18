#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then
  printf '%s\n' 'Usage: sh backup.sh SOURCE_DB NEW_BACKUP_DIRECTORY' >&2
  exit 2
fi
exec python3 "$(dirname "$0")/recovery.py" backup "$1" "$2"
