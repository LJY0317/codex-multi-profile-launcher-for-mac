#!/bin/sh
set -eu
exec python3 "$(dirname "$0")/../src/codex_profile.py" install "$@"
