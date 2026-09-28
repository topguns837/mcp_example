#!/usr/bin/env bash
# Entrypoint for the `app` container: creates a detached tmux session with
# two windows (chat / shell) on first start, then keeps the container alive.
# start.sh attaches to this session from the host.
set -euo pipefail

SESSION=mcp

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" -n chat "uv run python local_client.py; exec bash"
  tmux new-window -t "$SESSION" -n shell
  tmux select-window -t "$SESSION:chat"
fi

exec sleep infinity
