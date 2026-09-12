#!/bin/bash
# Run from the frontend directory: Tailwind resolves its content globs here.
# launchd and terminal sessions may otherwise start in different directories.
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir/frontend/nextjs"
node_bin="${ASTERIA_NODE_BIN:-/opt/homebrew/opt/node@22/bin/node}"
if [[ ! -x "$node_bin" ]]; then
  echo "Node 22 not found; set ASTERIA_NODE_BIN to its executable." >&2
  exit 1
fi
if [[ "$("$node_bin" -p 'process.versions.node.split(".")[0]')" != "22" ]]; then
  echo "The workspace frontend requires Node 22." >&2
  exit 1
fi
# Polling avoids low watcher limits on some machines, but on macOS cloud-backed
# Documents it can deadlock reads from node_modules. Prefer native watching;
# callers can opt into polling explicitly when they hit EMFILE.
export WATCHPACK_POLLING="${WATCHPACK_POLLING:-false}"
export NEXT_PUBLIC_ASTERIA_API_URL="${NEXT_PUBLIC_ASTERIA_API_URL:-http://127.0.0.1:8018}"
export NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-$NEXT_PUBLIC_ASTERIA_API_URL}"
# Authentication is configured by the caller/.env.local, never disabled here.
"$node_bin" ../../scripts/check-frontend-files.cjs
exec "$node_bin" node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port "${ASTERIA_FRONTEND_PORT:-3023}"
