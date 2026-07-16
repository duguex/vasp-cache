#!/usr/bin/env bash
set -euo pipefail

ROOT=${1:-/mnt/shared/home/c606}
INGEST_USER=${2:-duguex}
CACHE_ROOT=${3:-/mnt/shared/vasp_cache}

if [[ ! -d "$ROOT" ]]; then
    printf 'not a directory: %s\n' "$ROOT" >&2
    exit 2
fi
if (( $# > 3 )); then
    printf 'usage: %s [ROOT] [INGEST_USER] [CACHE_ROOT]\n' "$0" >&2
    exit 2
fi
ROOT=$(realpath -e -- "$ROOT")
chmod 755 -- "$ROOT"

umask 022
printf 'Normalize shared-data permissions under %s\n' "$ROOT"
printf 'Protected: hidden paths, credentials, tokens, keys, and PEM files.\n'
printf 'Precondition: stop all writers before running this wrapper.\n'

PROTECTED=(
    ! -path "$ROOT"
    \(
    -name '.*'
    -o -name 'credentials'
    -o -name 'credential'
    -o -name '*token*'
    -o -name '*.pem'
    -o -name '*.key'
    -o -name 'id_rsa*'
    \)
)
find "$ROOT" \( "${PROTECTED[@]}" \) -prune -o \
    -type d -exec chmod 755 -- {} \;
find "$ROOT" \( "${PROTECTED[@]}" \) -prune -o \
    -type f ! -perm /111 -print0 |
    xargs -0 -r chmod 644 --
find "$ROOT" \( "${PROTECTED[@]}" \) -prune -o \
    -type f -perm /111 -print0 |
    xargs -0 -r chmod 755 --
if ! remaining=$(find "$ROOT" \( "${PROTECTED[@]}" \) -prune -o \
    \( -type d ! -perm 755 \
    -o -type f ! -perm /111 ! -perm 644 \
    -o -type f -perm /111 ! -perm 755 \) \
    -print -quit); then
    printf 'permission verification scan failed\n' >&2
    exit 1
fi
if [[ -n "$remaining" ]]; then
    printf 'permission verification failed: %s\n' "$remaining" >&2
    exit 1
fi

printf 'Required creation policy: umask 022\n'
printf 'After the whole-home writer exits, run as %q:\n' "$INGEST_USER"
printf 'sudo -u '
printf '%q' "$INGEST_USER"
printf ' env VASP_CACHE_ROOT='
printf '%q' "$CACHE_ROOT"
printf ' python3 /home/duguex/vasp_cache/scripts/reingest_tree.py '
printf '%q' "$ROOT"
printf ' --cache-root '
printf '%q' "$CACHE_ROOT"
printf ' --log '
printf '%q' "$CACHE_ROOT/logs/reingest_c606.log"
printf ' --errors-json '
printf '%q' "$CACHE_ROOT/logs/reingest_c606_errors.json"
printf '\n'
