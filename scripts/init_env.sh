#!/usr/bin/env bash
# Writes the gitignored .env with freshly generated local secrets. Nothing sensitive is stored
# in the repo: this script holds names and generators, never values.
# An existing .env is left alone, because Postgres keeps the password it was created with.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env already exists; leaving it untouched."
  exit 0
fi

rand() { openssl rand -hex "$1"; }
postgres_password=$(rand 24)
# Hatchet wants a mix of cases, a digit and a symbol; the random part is what makes it strong.
hatchet_password="Hx$(rand 12)9!"

umask 077
cat > .env <<ENV
DEBUG=true
DJANGO_SECRET_KEY=$(rand 32)
POSTGRES_PASSWORD=${postgres_password}
DATABASE_URL=postgres://telejects:${postgres_password}@localhost:5436/telejects
# Written by: make hatchet-token
HATCHET_CLIENT_TOKEN=
HATCHET_CLIENT_TLS_STRATEGY=none
HATCHET_CLIENT_HOST_PORT=localhost:7081
# The Hatchet dashboard sign-in (http://localhost:8892). Hatchet creates this admin the first time
# its data is set up, so changing it later needs a Hatchet reset (see README).
HATCHET_ADMIN_EMAIL=admin@example.com
HATCHET_ADMIN_PASSWORD=${hatchet_password}
# Mail server, e.g. smtp+tls://user:password@host:587. Empty prints mail to the log.
EMAIL_URL=
APP_URL=http://localhost:5184
# The local sign-in that make seed creates.
DEV_ADMIN_EMAIL=admin@example.com
DEV_ADMIN_PASSWORD=$(rand 12)
ENV

echo "Wrote .env with generated local secrets."
echo "Your local sign-in is DEV_ADMIN_EMAIL / DEV_ADMIN_PASSWORD in that file."
