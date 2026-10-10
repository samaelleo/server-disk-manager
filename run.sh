#!/usr/bin/env bash
# Server Disk Manager - Zero-Trace Temporary Runner
# Automatically downloads to a temporary directory, runs with python3, and cleans up on exit.

set -e

TMP_DIR=$(mktemp -d /tmp/sdm.XXXXXX)
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

SCRIPT_URL="https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py"

if command -v curl >/dev/null 2>&1; then
    curl -sSL "$SCRIPT_URL" -o "$TMP_DIR/dm.py"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_DIR/dm.py" "$SCRIPT_URL"
else
    echo "[ERROR] Neither curl nor wget is installed." >&2
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    python3 "$TMP_DIR/dm.py" "$@"
elif command -v python >/dev/null 2>&1; then
    python "$TMP_DIR/dm.py" "$@"
else
    echo "[ERROR] Python 3 is not installed on this server." >&2
    exit 1
fi
