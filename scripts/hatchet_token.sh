#!/usr/bin/env bash
# Creates a Hatchet API token and stores it in the gitignored .env. The token is never printed.
set -euo pipefail

cd "$(dirname "$0")/.."

# hatchet-lite's built-in default tenant (a fixed public id, not a secret).
tenant=707d0855-80ab-4e1f-a156-f1c4546cbf52

token=$(docker compose exec -T hatchet /hatchet-admin token create --config /config --tenant-id "$tenant" | tail -1)
if [ -z "$token" ]; then
  echo "Hatchet returned no token. Is it running? (make up)" >&2
  exit 1
fi

umask 077
updated=$(mktemp .env.XXXXXX)
awk -v token="$token" '
  /^HATCHET_CLIENT_TOKEN=/ { print "HATCHET_CLIENT_TOKEN=" token; next }
  { print }
' .env > "$updated"
mv "$updated" .env

echo "HATCHET_CLIENT_TOKEN written to .env"
