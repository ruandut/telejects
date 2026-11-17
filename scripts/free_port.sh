#!/usr/bin/env bash
# Stops whatever is listening on a local port, so a dev server can always start on its own port
# instead of failing or drifting to the next free one. Usually that is an earlier run of the same
# server, left open in another terminal.
# Usage: scripts/free_port.sh 8000
set -euo pipefail

port="${1:?usage: free_port.sh <port>}"

listeners() { lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true; }

pids=$(listeners)
[ -n "$pids" ] || exit 0

echo "Port ${port} is taken; stopping what holds it (pid $(echo $pids))."
kill $pids 2>/dev/null || true

# Give it three seconds to let go, then insist.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -z "$(listeners)" ] && exit 0
  sleep 0.3
done
pids=$(listeners)
[ -z "$pids" ] || kill -9 $pids 2>/dev/null || true
