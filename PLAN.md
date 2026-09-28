# Learn MCP by Building a Local Notes Server

## Context

The user is studying the Model Context Protocol (MCP) specification (2025-11-25),
starting from the `server/prompts` page, and wants a hands-on project to internalize
the architecture rather than just reading docs. They want three things delivered:
(1) a survey of example projects worth building, (2) a breakdown of what's needed to
implement them, and (3) a concrete implementation plan for one of them.

An empty `mcp_example/` directory already exists in the workspace
(`/home/mediapipe/workspaces/mcp_example`) and will be the project root.

Confirmed choices from the user:
- **Language/SDK**: Python (official `mcp` SDK, FastMCP-style decorators)
- **Project**: Local notes / knowledge base server — deliberately chosen because it
  exercises all three server-side primitives (Resources, Tools, Prompts) with zero
  external APIs or credentials, so nothing can fail due to network/auth issues while
  learning.
- **Test client**: Claude Code itself, via `claude mcp add`

Environment check done: Python 3.10.12 and pip are present; `uv` is not installed
(will install it, since it's the tool the official MCP Python SDK docs and
`mcp[cli]` scaffolding assume — falls back to plain `venv`+`pip` if install is
declined/unavailable); `claude mcp` CLI is available for registering the server.

---

## Part 1 — Example Projects (survey, for context)

These are the four candidate projects considered, in order of how completely they
cover the MCP primitives (Resources / Tools / Prompts / Sampling):

| # | Project | Resources | Tools | Prompts | Notes |
|---|---|---|---|---|---|
| 1 | **Notes / knowledge base server** (chosen) | Notes as `note://<id>` resources | `create_note`, `search_notes` | `summarize_note`, `draft_reply` | No external deps; purely local files |
| 2 | SQLite database explorer | Table schemas as resources | `run_query` (read-only) | `draft_sql_from_request` | Mirrors the official MCP quickstart; adds DB setup |
| 3 | Public weather/API tool server | — | `get_forecast`, `get_alerts` (open-meteo, no key) | — | Simplest possible server, but skips Resources/Prompts |
| 4 | Git repo assistant | File tree / diff as resources | `git_log`, `git_diff` | `draft_commit_message` | Realistic dev-tool feel; needs a real git repo target |

Project 1 is the one being implemented below. Projects 2–4 are natural "next steps"
once the first one is understood — the plan notes at the end how to extend toward
them.

---

## Part 2 — Resource Breakdown

**Runtime / tooling**
- Python 3.10.12 (already present)
- `uv` (package/env manager recommended by the official MCP Python SDK) — install via
  the official installer script; fallback is `python3 -m venv` + `pip`
- `mcp` Python package with the `cli` extra (`mcp[cli]`), which provides `FastMCP`
  and the `mcp dev` / `mcp install` helper commands
- Claude Code CLI (already available) as the test client via `claude mcp add`

**Project structure** (inside `/home/mediapipe/workspaces/mcp_example`)
```
mcp_example/
├── pyproject.toml          # uv-managed project + mcp dependency
├── notes_server.py         # the FastMCP server: resources, tools, prompts
├── notes/                  # local data dir — the "database" of the example
│   ├── welcome.md
│   └── mcp-cheatsheet.md
└── README.md               # how to run + what each primitive demonstrates
```

**Conceptual pieces to implement** (mapped to the spec pages already reviewed)
- **Resources** — `list_resources` / `read_resource` equivalents via `@mcp.resource(...)`:
  expose each `notes/*.md` file as a `note://<slug>` resource, plus one dynamic
  resource template `note://{slug}` for on-demand reads.
- **Tools** — `@mcp.tool()`: `create_note(title, body)` writes a new markdown file;
  `search_notes(query)` greps note contents and returns matches. These are the
  model-invoked, side-effecting primitive (contrast with Resources, which are
  read-only context).
- **Prompts** — `@mcp.prompt()`: `summarize_note(slug)` returns a `PromptMessage`
  list asking the model to summarize a given note's content (embedding the note as
  an embedded resource, per the `EmbeddedResource` content type from the docs page
  the user was reading); `draft_reply(slug, tone)` returns a templated message with
  an argument.
- **Capability negotiation** — FastMCP handles this automatically, but the README
  will point out where `capabilities.resources`, `capabilities.tools`, and
  `capabilities.prompts` (with `listChanged`) show up in the `initialize` handshake,
  since that's the mechanism the spec page describes.

---

## Part 3 — Implementation Plan

**Delivery style**: this plan itself gets copied into
`mcp_example/PLAN.md` as step 0, so it persists as a reference in the project. Then
each step below is executed one at a time, in order, with a short explanation before
each tool call of *what* is being done and *why* it maps to the MCP concept it
demonstrates (resource vs. tool vs. prompt, capability negotiation, transport, etc.)
so the user builds understanding alongside the code rather than receiving a finished
project all at once.

0. **Write `mcp_example/PLAN.md`** containing this plan (Parts 1–3), so the
   project folder is self-documenting from the start.

1. **Install `uv`** (or confirm fallback) and scaffold the project
   - `curl -LsSf https://astral.sh/uv/install.sh | sh` (or note the pip/venv fallback
     if the user prefers not to install uv globally)
   - `uv init mcp_example` / `uv add "mcp[cli]"` inside the existing empty directory

2. **Seed sample data**
   - Create `notes/welcome.md` and `notes/mcp-cheatsheet.md` with a few paragraphs
     each, so Resources/Tools/Prompts have real content to operate on from the start.

3. **Write `notes_server.py`**
   - Instantiate `FastMCP("notes")`
   - Add the two resources (static list + templated single-note read)
   - Add the two tools (`create_note`, `search_notes`) with input validation and
     clear docstrings (docstrings become the descriptions shown to the model/client)
   - Add the two prompts (`summarize_note`, `draft_reply`), constructing
     `PromptMessage` objects, one of which embeds the note as a resource per the
     spec's `EmbeddedResource` content type
   - Add `if __name__ == "__main__": mcp.run()` for stdio transport

4. **Write `README.md`**
   - Short "what is this" + how each primitive maps to a spec section, so the
     project doubles as a reference while re-reading the docs

5. **Local smoke test with the MCP dev inspector-free path**
   - `uv run mcp dev notes_server.py` to sanity check the server boots and lists
     its primitives before wiring it into Claude Code

6. **Register with Claude Code**
   - `claude mcp add notes-server -- uv run --directory /home/mediapipe/workspaces/mcp_example python notes_server.py`
   - Verify with `claude mcp list` / `claude mcp get notes-server`

7. **End-to-end verification**
   - In a Claude Code session, confirm the server's resources appear (list notes),
     invoke `create_note` and `search_notes` as tools, and invoke `summarize_note`
     as a slash-command-style prompt — confirming all three primitives round-trip
     through the real JSON-RPC exchange (`prompts/list`, `prompts/get`,
     `resources/list`, `resources/read`, `tools/list`, `tools/call`)

8. **Note next steps in the README** for extending toward the SQLite or Git-assistant
   variants from Part 1, once this one is understood.

### Verification
- `uv run mcp dev notes_server.py` starts without error and reports 2 resources
  (or 1 static + 1 template), 2 tools, 2 prompts.
- `claude mcp list` shows `notes-server` as connected.
- From within Claude Code: listing resources shows the two seed notes; calling
  `create_note` creates a new file under `notes/` and it becomes visible as a new
  resource; calling `search_notes` finds it; invoking `summarize_note` returns a
  templated prompt referencing the note's embedded content.

---

## Part 4 — Phase 2: Docs, a Local-LLM Client, and Dockerization

Once the notes-server above was working, the goal shifted to pushing this as a
public code sample: restructured docs, a way for colleagues without a Claude
subscription to try it, and a single-command way to run the whole thing.

**Docs restructure** -- `README.md` stayed the quickstart hub; deep content moved
into `docs/`: `architecture.md` (protocol flows, plus the "two protocols meeting"
point below), `testing.md` (all four ways to exercise the server), `docker.md`
(the Docker/tmux setup).

**`local_client.py`** -- a second MCP client (alongside `trace_client.py`),
driven by a local LLM via [Ollama](https://ollama.com) instead of a hosted
model, so colleagues without API access can still try the server. Key
decisions, in the order they came up:
- **Ollama over llama-cpp-python/vLLM** -- best tool-calling support and
  Docker distribution story for a teaching project.
- **`qwen2.5:1.5b` as the default model**, not a typical 7-8B default --
  this server only has two trivial tools, so a compact (~1GB) model was
  explicitly requested and is sufficient.
- **`httpx` as an explicit dependency**, not the `ollama` PyPI package --
  keeps the raw request/response JSON visible (same "show the wire
  protocol" spirit as `trace_client.py`), and this SDK version's `mcp[cli]`
  no longer pulls in plain `httpx` transitively (it vendors a renamed
  `httpx2`/`httpcore2`), so relying on it transitively would have broken
  outright.
- **A real, verified agent loop**: `session.list_tools()` -> convert each
  `Tool.input_schema` to Ollama's `{"type": "function", "function": {...}}`
  shape -> `POST /api/chat` -> resolve any `tool_calls` via
  `session.call_tool(...)` -> feed results back -> repeat. The two MCP
  *prompts* are deliberately not exposed as tools (prompts are
  user-triggered, not model-decided); `/summarize` and `/reply` fetch them
  directly via `session.get_prompt(...)`.
- **A reliability finding worth recording**: asking the model *about
  itself* ("list your current MCP tools") turned out to be unreliable in a
  different direction than expected -- rather than answering in plain text,
  it would sometimes call `create_note`/`search_notes` anyway (with
  made-up arguments, occasionally leaving stray notes behind), because
  merely having a non-empty `tools` list in the request measurably biases
  small models toward calling *something*. Verified this wasn't fixable by
  prompt-tuning or a lower temperature alone, and held at `qwen2.5:3b` too.
  Fixed by adding `/tools`, a REPL command that reads the answer straight
  from the same live `list_tools()` result already used to build the
  tool-calling payload -- deterministic, and still fully dynamic (no tool
  names hardcoded anywhere), unlike the first attempt at a fix (a system
  prompt enumerating tool names by hand), which was correctly rejected
  during review for hardcoding what MCP already provides dynamically.

**Dockerization** -- `Dockerfile` (`python:3.10-slim-bookworm` + `uv` +
`tmux`), `docker-compose.yml` (an `ollama` service and an `app` service),
`docker/entrypoint.sh` (a detached `tmux` session with a `chat` window
running `local_client.py` and a plain `shell` window), and `startScript.sh`
as the single command that builds, waits for Ollama's healthcheck, pulls
the model, and attaches. Two notable fixes along the way:
- The `app` service bind-mounts the repo at `/app` for live edits, which
  would otherwise shadow the image's baked `.venv` with an empty host
  directory (`.venv` is gitignored) -- fixed with a second, named volume
  nested at `/app/.venv`, which Docker resolves as authoritative over the
  parent bind mount.
- The Ollama model cache started as an opaque named Docker volume, then was
  changed to a bind-mounted `ollama-data/` folder in the repo (tracked via
  `ollama-data/.gitkeep`, contents gitignored) so the ~1GB+ of downloaded
  model data is visible/inspectable on the host rather than hidden inside
  Docker's volume store.

### Verification
Tested live end-to-end, not just read through: `local_client.py` standalone
against a bare `ollama` container (tool calls fire correctly, `create_note`
writes real files, `/summarize`/`/reply` produce real generated text, a bad
slug fails gracefully); the full `docker compose` stack (the `.venv`-shadow
fix, `app`-to-`ollama` service-name networking, the `ollama-data` bind mount
actually receiving the downloaded model); and `./startScript.sh` itself
end-to-end from a clean state, including the `/tools` fix inside the real
running container.
