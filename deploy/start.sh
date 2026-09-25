#!/usr/bin/env bash
# Run from WSL2/Linux: bash deploy/start.sh --gpu (or omit --gpu for CPU).
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ $# -gt 1 || ($# -eq 1 && "$1" != "--gpu") ]]; then
  echo "Usage: bash deploy/start.sh [--gpu]" >&2
  exit 2
fi

for tool in docker openssl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $tool; install it before continuing." >&2
    exit 1
  fi
done

env_file="$repo_dir/deploy/.env"
first_start=0
if [[ ! -f "$env_file" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Administrator email: " admin_email
  else
    admin_email="${ASTERIA_ADMIN_EMAIL:-}"
  fi
  if [[ ! "$admin_email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
    echo "Provide a valid administrator email (or set ASTERIA_ADMIN_EMAIL)." >&2
    exit 1
  fi
  cp deploy/.env.example "$env_file"
  chmod 600 "$env_file"
  sed -i "s/REPLACE_WITH_HEX_ONLY_PASSWORD/$(openssl rand -hex 32)/" "$env_file"
  sed -i "s/REPLACE_WITH_AT_LEAST_64_HEX_CHARACTERS/$(openssl rand -hex 32)/" "$env_file"
  sed -i "s/REPLACE_WITH_ANOTHER_64_HEX_CHARACTERS/$(openssl rand -hex 32)/" "$env_file"
  sed -i "s/ASTERIA_ADMIN_EMAILS=admin@example.com/ASTERIA_ADMIN_EMAILS=$admin_email/" "$env_file"
  first_start=1
  echo "Created deploy/.env with random local secrets. Keep this file and back it up securely."
fi

get_value() { sed -n "s/^$1=//p" "$env_file" | tail -n 1; }
db_password="$(get_value DB_PASSWORD)"
jwt_secret="$(get_value JWT_SECRET)"
settings_secret="$(get_value ASTERIA_MODEL_SETTINGS_SECRET)"
admin_email="$(get_value ASTERIA_ADMIN_EMAILS)"
if [[ ! "$db_password" =~ ^[a-f0-9]{64}$ || ${#jwt_secret} -lt 32 || ${#settings_secret} -lt 32 || "$admin_email" == "admin@example.com" || -z "$admin_email" ]]; then
  echo "deploy/.env is incomplete; set DB_PASSWORD, JWT_SECRET, ASTERIA_MODEL_SETTINGS_SECRET and ASTERIA_ADMIN_EMAILS." >&2
  exit 1
fi

compose=(docker compose -f compose.yaml)
if [[ ${1:-} == "--gpu" ]]; then
  compose+=(-f deploy/compose.gpu.yaml)
fi
compose+=(--env-file "$env_file")
export ASTERIA_BUILD_REVISION="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
"${compose[@]}" ps
if [[ $first_start -eq 1 && -t 0 ]]; then
  echo "Set the first administrator password when prompted (12+ characters)."
  "${compose[@]}" exec api python scripts/manage-lab.py account --email "$admin_email"
elif [[ $first_start -eq 1 ]]; then
  echo "Create the administrator account with: docker compose --env-file deploy/.env exec -it api python scripts/manage-lab.py account --email $admin_email"
fi
echo "Open http://127.0.0.1:3023/login, then configure the model API Key in Agent → 模型."
