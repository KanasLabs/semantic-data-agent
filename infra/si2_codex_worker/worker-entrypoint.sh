#!/bin/sh
set -eu

mkdir -p "${CODEX_HOME}" "${HOME}"
exec codex "$@"
