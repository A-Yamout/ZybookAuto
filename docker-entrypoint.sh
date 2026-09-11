#!/bin/sh
set -eu

python app.py &
WEB_PID=$!

python mcp_server.py &
MCP_PID=$!

cleanup() {
  kill "$WEB_PID" "$MCP_PID" 2>/dev/null || true
  wait "$WEB_PID" "$MCP_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

while kill -0 "$WEB_PID" 2>/dev/null && kill -0 "$MCP_PID" 2>/dev/null; do
  sleep 1
done

# If either service exits, stop the other and fail the container so Docker can restart it.
cleanup
exit 1
