#!/bin/sh
set -eu
if [ "$#" -eq 0 ]; then
    set -- install
fi
exec python3 "$(dirname "$0")/../src/codex_profile.py" "$@"
