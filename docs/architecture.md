# Architecture: what this server does, and how the pieces talk to each other

For MCP *concepts* (host/client/server roles, capability negotiation,
transports, prompt content types), see `notes/mcp-cheatsheet.md` -- this doc
doesn't repeat that, it's about the concrete flows in *this* project.

## What `notes_server.py` exposes

| Primitive | This server's example | Who invokes it |
|---|---|---|
| **Resources** | `note://<slug>` (one per file under `notes/`), `note://directory` (JSON listing) | The client/user, as read-only context |
| **Tools** | `create_note(title, body)`, `search_notes(query)` | The model, to take action or fetch data |
| **Prompts** | `summarize_note(slug)`, `draft_reply(slug, tone)` | The user, explicitly (e.g. a slash command) |

All of it runs over the **stdio transport**: a client spawns
`notes_server.py` as a subprocess and exchanges one JSON-RPC 2.0 object per
line over its stdin/stdout. There's no network involved.

## The protocol flow, end to end

This is exactly what `trace_client.py` does by hand, with no SDK
abstraction -- run it (`uv run python trace_client.py`) to see the real JSON
for each of these steps:

1. **`initialize`** -- the client sends its `protocolVersion` and
   capabilities; the server responds with its own name/version and which
   capabilities (resources/tools/prompts) it supports.
2. **`notifications/initialized`** -- a client->server notification (no
   `id`, no response) marking the handshake done.
3. **`resources/list`** / **`tools/list`** / **`prompts/list`** -- the
   client asks what's available. Each tool/prompt's `description` and
   argument schema come straight from the corresponding Python function's
   docstring and type hints (see `notes_server.py`) -- the SDK generates the
   wire-level metadata for you.
4. **`tools/call`** -- e.g. calling `create_note` with `{"title": ..., "body":
   ...}`. The server runs the actual Python function and returns its result
   as a list of content blocks.
5. **`prompts/get`** -- e.g. `summarize_note` with `{"slug": "welcome"}`. The
   server returns a list of `PromptMessage`s, one of which embeds the note's
   full content inline as an `EmbeddedResource` content block (rather than
   just referencing it by URI) -- see `notes_server.py`'s `summarize_note`.

## A second protocol, layered on top: the local-LLM agent loop

`local_client.py` (see `docs/testing.md`) adds a different, unrelated
protocol on top of MCP: Ollama's tool-calling chat API. It's worth being
explicit that these are two separate things meeting at one Python process:

```
   Ollama tool-calling protocol              MCP protocol
   (HTTP, /api/chat)                          (stdio, JSON-RPC)
┌──────────┐  tools=[...]   ┌──────────────┐  tools/call   ┌───────────────┐
│  Ollama  │◄──────────────►│ local_client │◄─────────────►│ notes_server  │
│ (model)  │  tool_calls    │    .py       │  result        │    .py       │
└──────────┘                └──────────────┘                └───────────────┘
```

Concretely, `local_client.py`:
1. Calls `session.list_tools()` over MCP to get each `Tool`'s
   `input_schema` (a JSON Schema).
2. Wraps each one as `{"type": "function", "function": {"name",
   "description", "parameters": input_schema}}` -- the shape Ollama's
   `/api/chat` expects in its `tools` list. MCP tool schemas are already
   JSON Schema, so this is a near-direct pass-through, not a translation.
3. Sends the conversation + `tools` to Ollama. If the model's response
   includes `tool_calls`, it resolves each one via MCP's
   `session.call_tool(name, arguments)`, flattens the result's content
   blocks into text, and appends it back into the conversation as a
   `tool`-role message.
4. Repeats until the model replies with plain text instead of a tool call.

The two MCP *prompts* (`summarize_note`, `draft_reply`) are intentionally
**not** exposed to the model as tools -- prompts are meant to be
user-triggered, not model-decided. `local_client.py`'s `/summarize <slug>`
and `/reply <slug> [tone]` slash commands call `session.get_prompt(...)`
directly, then run the returned template through the model once to produce
actual prose.

## Where to look next

- `docs/testing.md` -- every way to run and exercise this server.
- `docs/docker.md` -- the Docker/tmux setup that packages all of the above.
