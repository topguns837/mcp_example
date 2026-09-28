#!/usr/bin/env bash
# Single-command entry point: builds and starts the Docker stack (an Ollama
# service + this project's app container), waits for Ollama to be ready,
# pulls the local LLM (cached after the first run), and drops you straight
# into an interactive tmux session chatting with notes_server.py.
#
# Usage: ./startScript.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

command -v docker >/dev/null 2>&1 || {
  echo "error: docker is required but not found. See https://docs.docker.com/get-docker/" >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  echo "error: 'docker compose' (v2) is required but not found." >&2
  exit 1
}

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"

echo "==> Building and starting containers..."
docker compose up -d --build

echo "==> Waiting for ollama to become healthy..."
ollama_container="$(docker compose ps -q ollama)"
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$ollama_container" 2>/dev/null)" = "healthy" ]; do
  sleep 2
done

echo "==> Pulling $OLLAMA_MODEL (already-cached models are a fast no-op)..."
docker compose exec ollama ollama pull "$OLLAMA_MODEL"

cat <<'EOF'

==> Ready. Attaching to the chat session.
    Ctrl-b then d   -- detach (containers keep running; re-attach any time
                       with: docker compose exec app tmux attach -t mcp)
    Ctrl-b then 0/1 -- switch between the "chat" and "shell" windows
    Ctrl-b then [    -- scroll back (press q to exit scroll mode)

EOF
docker compose exec -it app tmux attach -t mcp
