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

umask 022
printf 'Normalize VASP cache files under %s\n' "$ROOT"
printf 'Precondition: stop all writers before running this wrapper.\n'

find "$ROOT" -type f -name OUTCAR -print0 |
while IFS= read -r -d '' outcar; do
    calc_dir=${outcar%/*}
    chmod 755 -- "$calc_dir"
    for name in OUTCAR CONTCAR vasprun.xml INCAR POSCAR KPOINTS; do
        path="$calc_dir/$name"
        if [[ -f "$path" && ! -L "$path" ]]; then
            chmod 644 -- "$path"
        fi
    done
done

printf 'Required creation policy: umask 022\n'
printf 'After the whole-home writer exits, run as %s:\n' "$INGEST_USER"
printf 'sudo -u %s env VASP_CACHE_ROOT=%s python3 /home/duguex/vasp_cache/scripts/reingest_tree.py %s --cache-root %s --log %s/logs/reingest_c606.log --errors-json %s/logs/reingest_c606_errors.json\n' \
    "$INGEST_USER" "$CACHE_ROOT" "$ROOT" "$CACHE_ROOT" "$CACHE_ROOT" "$CACHE_ROOT"
