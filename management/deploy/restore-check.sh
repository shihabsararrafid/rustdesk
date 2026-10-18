#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then
  printf '%s\n' 'Usage: sh restore-check.sh BACKUP_DIRECTORY NEW_TEST_DIRECTORY' >&2
  exit 2
fi
exec python3 "$(dirname "$0")/recovery.py" verify "$1" "$2"
