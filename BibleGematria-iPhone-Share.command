#!/bin/zsh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export BIBLE_GEMATRIA_HOST="0.0.0.0"
export BIBLE_GEMATRIA_PORT="${BIBLE_GEMATRIA_PORT:-8887}"
export BIBLE_GEMATRIA_SHARE="1"

exec "$SCRIPT_DIR/BibleGematria.command"
