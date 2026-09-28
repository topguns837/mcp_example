# notes-server: a minimal MCP server for learning the protocol

A local markdown-notes server built with the official Python `mcp` SDK, to learn
the Model Context Protocol (MCP) by exercising all three server-side primitives:

| Primitive | This project's example | Spec page |
|---|---|---|
| **Resources** | `note://{slug}` (each markdown file), `note://directory` (JSON listing) | `/specification/.../server/resources` |
| **Tools** | `create_note`, `search_notes` | `/specification/.../server/tools` |
| **Prompts** | `summarize_note`, `draft_reply` | `/specification/.../server/prompts` |

See `PLAN.md` for the full project plan, `notes/mcp-cheatsheet.md` for a
quick conceptual reference (hosts/clients/servers, capability negotiation,
transports), and `docs/architecture.md` for how this specific server's
protocol flows work.

## Requirements

- Python >= 3.10
- [`uv`](https://docs.astral.sh/uv/) (already set up in this project)
- ...or just [Docker](https://docs.docker.com/get-docker/) -- see method 4
  below, no local Python/uv setup needed at all.

## Run it

The server speaks JSON-RPC 2.0 over stdio -- it's meant to be launched by a
client/host, not run standalone in a terminal (it will look like it "hangs"
waiting for a client). Four ways to try it (full details in `docs/testing.md`):

### 1. MCP Inspector (interactive web UI)

```bash
uv run mcp dev notes_server.py
```
Browse resources, call tools, get prompts, and see the raw JSON-RPC in a
local web UI. Needs Node >= 22 -- see `docs/testing.md` for the version gotcha.

### 2. `trace_client.py` (see the exact wire protocol)

```bash
uv run python trace_client.py
```
Spawns the server and prints every JSON-RPC message exactly as it crosses
the pipe -- the `initialize` handshake, `resources/list`, a `tools/call`,
a `prompts/get`. No SDK abstraction in the way.

### 3. Claude Code

```bash
claude mcp add notes-server -- uv run --directory /home/mediapipe/workspaces/mcp_example python notes_server.py
```
Then, from within a Claude Code session: list resources, call `create_note`/
`search_notes`, invoke the `summarize_note`/`draft_reply` prompts. See
`docs/testing.md` for verification commands and a Claude-Code-session gotcha.

### 4. Docker + a local LLM (no Claude subscription needed)

```bash
./startScript.sh
```
One command: builds a container with this project + `tmux`, another running
[Ollama](https://ollama.com) with a small local model, and drops you into an
interactive chat session that drives this server's tools the same way a
real host would -- useful for colleagues without hosted-model access. See
`docs/docker.md` for what it does and `docs/testing.md` for the client's
usage/commands.

## What each file is doing

- **`notes_server.py`** -- the whole server. Read top to bottom: Resources
  section, then Tools, then Prompts. Each primitive is a Python function with
  a decorator (`@server.resource(...)`, `@server.tool()`, `@server.prompt()`);
  the SDK turns the function's docstring and type hints into the
  `description`/`arguments` metadata a client sees via `resources/list`,
  `tools/list`, and `prompts/list`.
- **`trace_client.py`** -- a hand-written MCP client showing the raw wire
  protocol (see method 2 above).
- **`local_client.py`** -- an MCP client driven by a local LLM via Ollama,
  for testing without a hosted model (see method 4 above and
  `docs/architecture.md`'s "local-LLM agent loop" section).
- **`notes/*.md`** -- the seed data. Also the "database" this whole example
  operates on; feel free to add/edit files directly, or use the tools.
- **`docs/`** -- `architecture.md` (protocol flows), `testing.md` (every way
  to run/exercise the server), `docker.md` (the Docker/tmux setup).
- **`PLAN.md`** -- the original project plan (example-project survey,
  resource breakdown, implementation steps).

## Gotcha: don't use `from __future__ import annotations` here

Early versions of this file had that import at the top (a common habit for
"modern" type hints). It breaks under `uv run mcp dev notes_server.py`
specifically: the `mcp` CLI loads the script via
`importlib.util.module_from_spec(...)` + `exec_module(...)` but never
registers the resulting module in `sys.modules`. With postponed evaluation
active, a return type like `list[Message]` is stored as the *string*
`"list[Message]"` and only resolved later, when pydantic builds the
validator -- and pydantic looks up the defining module via
`sys.modules[func.__module__]` to get the namespace to resolve it in. Since
that module was never registered, the lookup misses, `Message` looks
undefined, and you get `NameError: name 'Message' is not defined` even
though the import is right there at the top of the file.

Without `from __future__ import annotations`, annotations are evaluated
immediately at function-definition time, in the module's real, live
namespace -- so this whole failure mode doesn't apply. (Python 3.9+ allows
plain `list[Message]`/`list[str]` at runtime anyway, so nothing is lost by
leaving it out here.) This is a `mcp` CLI loader bug, not a protocol issue --
worth knowing since it'll bite any MCP server that mixes postponed
annotations with a dev-tool that loads scripts this way.

## SDK version note

This project pins `mcp[cli]>=2.2.0`. In `mcp` 2.x, the class that older
tutorials call `FastMCP` was renamed to `MCPServer`
(`from mcp.server.mcpserver import MCPServer`) -- same decorator-based API,
just a different import path and class name. If you see older example code
using `from mcp.server.fastmcp import FastMCP`, substitute accordingly.

## Extending this

Natural next steps, once this example makes sense (see `PLAN.md` Part 1 for
the other example projects considered):

- Add a `resources/list_changed` notification when `create_note` registers a
  new resource, so a connected client updates its list live instead of only
  seeing new notes on its next `resources/list` call.
- Swap the markdown-file backend for SQLite (schemas as resources, a
  read-only query tool, a prompt that drafts SQL) -- closer to the official
  MCP quickstart server.
- Add a `roots` or `sampling` example to see a **client**-side capability
  (as opposed to everything here, which is server-side).
