#!/usr/bin/env bash
# Stops this checkout's Hatchet workers, so there is only ever one and it runs the current code.
# Workers are matched by their working directory, so another project's worker is left alone.
set -euo pipefail

backend="$(cd "$(dirname "$0")/../backend" && pwd -P)"

for pid in $(pgrep -f "manage.py hatchet_worker" 2>/dev/null || true); do
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  if [ "$cwd" = "$backend" ]; then
    echo "Stopping an earlier worker (pid ${pid})."
    kill "$pid" 2>/dev/null || true
  fi
done
