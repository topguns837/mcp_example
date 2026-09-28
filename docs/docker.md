# Docker + tmux setup

The single-command way to run this whole project -- server, local LLM, and
an interactive chat client -- with nothing installed on your machine except
Docker. This is the recommended path if you don't have a Claude
subscription and don't want to set up Python/`uv`/Ollama by hand.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2
  (`docker compose version` should work)

## Run it

```bash
git clone <this repo>
cd mcp_example
./startScript.sh
```

That's it. `startScript.sh`:
1. Checks `docker` and `docker compose` are available.
2. Builds and starts two containers: `ollama` (the local LLM runtime) and
   `app` (this project, with `tmux` installed).
3. Waits for `ollama`'s healthcheck to pass.
4. Pulls the configured model (`qwen2.5:1.5b` by default) into it -- this is
   a one-time ~1GB download per machine, cached under `ollama-data/` in the
   repo (bind-mounted, gitignored -- see "How it's wired" below), so
   subsequent runs are a fast no-op.
5. Attaches you to a `tmux` session already running inside the `app`
   container, with `local_client.py` (see `docs/testing.md`) started and
   waiting for input.

## What's in the tmux session

Two windows, created by `docker/entrypoint.sh`:
- **`chat`** (the one you land on) -- running `local_client.py`, ready to
  chat.
- **`shell`** -- a plain shell in the same container, for poking around:
  editing files under `notes/`, running `trace_client.py`, etc.

## tmux, the 4 keys you actually need

You don't need to know tmux beyond this:

| Keys | Effect |
|---|---|
| `Ctrl-b` then `0` / `1` | Switch to the `chat` / `shell` window |
| `Ctrl-b` then `d` | Detach -- everything keeps running in the background |
| `docker compose exec app tmux attach -t mcp` | Re-attach later (from the repo directory) |
| `Ctrl-b` then `[`, then `q` to exit | Enter scroll-back mode to read output that's scrolled off (arrow keys alone don't scroll a tmux pane) |

Stopping everything: `docker compose down` (add `-v` to also delete the
cached venv; delete `ollama-data/`'s *contents* separately, with `sudo` if
needed -- see the ownership note below -- to also drop the downloaded model
and get a fully clean slate).

## Configuration

Copy `.env.example` to `.env` to override defaults:

```bash
cp .env.example .env
```

- `OLLAMA_MODEL` -- which model to pull and use (default `qwen2.5:1.5b`; try
  `llama3.2:1b` for something even lighter, or size up if you want more
  reliable tool-calling -- see `docs/testing.md`).
- `OLLAMA_TEMPERATURE` -- sampling temperature for `local_client.py`
  (default `0.2`, lower than Ollama's own default of `0.8`, for more
  consistent answers -- see `docs/testing.md`).
- `OLLAMA_PORT` -- host port Ollama's API is exposed on, for
  curl/debugging outside the containers (default `11434`).

## GPU acceleration (optional)

The default setup is CPU-only, so it works on any machine regardless of
hardware. If you have an NVIDIA GPU and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
installed, uncomment the `deploy.resources.reservations.devices` block under
the `ollama` service in `docker-compose.yml`.

## Things that are deliberately host-only

The MCP **Inspector** (`uv run mcp dev notes_server.py`) needs Node.js
>= 22, which this image doesn't include (kept slim on purpose). Use it on
your host if you want it, or use `trace_client.py`/`local_client.py` from
the `shell` window instead -- both work fully inside the container.

## How it's wired (for the curious)

- `Dockerfile` -- `python:3.10-slim-bookworm` + `uv` + `tmux`, then `uv sync`
  to install this project's dependencies.
- `docker-compose.yml` -- the `ollama` service (official image, healthcheck,
  and `./ollama-data:/root/.ollama` bind-mounted for the model cache -- see
  below) and the `app` service (built from the `Dockerfile`, waits for
  `ollama` to be healthy, gets `OLLAMA_HOST=http://ollama:11434` so
  `local_client.py` reaches Ollama by its Compose service name over the
  Docker network).
- `ollama-data/` -- where the `ollama` service actually stores everything it
  downloads (models, its own keypair, etc.), bind-mounted into the container
  rather than hidden in an opaque Docker-managed volume, so you can inspect
  or `du -sh` it from the host. The folder itself is tracked in git (via
  `ollama-data/.gitkeep`, so it exists after a fresh clone) but everything
  Ollama writes into it is gitignored. Ollama runs as root inside its
  container, so those files end up root-owned on the host -- harmless for
  normal use, just means deleting them by hand later may need `sudo`.
- The `app` service bind-mounts the repo at `/app` for live edits, **plus**
  a separate named volume at the nested path `/app/.venv` -- otherwise the
  bind mount would shadow the image's already-built virtualenv with an
  empty directory (`.venv` is gitignored, so a fresh clone has none on the
  host). The nested volume mount wins over the parent bind mount, so the
  container's own `.venv` survives.
