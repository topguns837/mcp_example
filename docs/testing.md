# Testing: every way to exercise this server

`notes_server.py` speaks JSON-RPC 2.0 over stdio -- it's meant to be
launched by a client/host, not run standalone in a terminal (it will look
like it "hangs" waiting for a client). Four ways to actually exercise it,
from most to least hand-holding:

## 1. MCP Inspector (interactive web UI)

```bash
uv run mcp dev notes_server.py
```

Opens a local web UI where you can browse resources, call tools, and get
prompts one at a time, and see the raw JSON-RPC requests/responses.

**Node version requirement:** the Inspector package needs Node >= 22 (it
uses `node:util`'s `styleText`, added in Node 20.12+, and its own
`package.json` pins `engines.node: ">=22.19.0"`). If your default Node is
older, install one with [`nvm`](https://github.com/nvm-sh/nvm) *without*
touching the system Node:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
export NVM_DIR="$HOME/.nvm" && \. "$NVM_DIR/nvm.sh"
nvm install 22   # then, in every new shell: nvm use 22
```

If a previous attempt with the wrong Node already cached a broken install,
you'll see `Error running MCP Inspector: Cannot find native binding` --
clear npx's cache and retry: `rm -rf ~/.npm/_npx`.

This is a **host-only** workflow -- see `docs/docker.md` for why it doesn't
run inside the Docker setup.

## 2. `trace_client.py` (see the exact wire protocol)

```bash
uv run python trace_client.py
```

Spawns the server itself (no SDK abstraction in between) and prints every
JSON-RPC 2.0 message exactly as it crosses the pipe: the `initialize`
handshake, `resources/list`, a `tools/call`, and a `prompts/get`. Useful for
seeing literally what "the exact communication between host, client, and
server" looks like -- MCP over stdio is just one JSON object per line, no
extra framing. See `docs/architecture.md` for what each step means.

## 3. Claude Code

Register the server:

```bash
claude mcp add notes-server -- uv run --directory /home/mediapipe/workspaces/mcp_example python notes_server.py
```

Verify it's registered:

```bash
claude mcp list
claude mcp get notes-server
```

**Note:** an already-running Claude Code session loads its MCP servers at
startup, so a server added with `claude mcp add` while a session is open
won't appear in that session's tools until you start a new session (or use
your client's reload mechanism, if it has one).

Once connected, from within a session you can:
- List resources -> see `note://welcome`, `note://mcp-cheatsheet`, `note://directory`
- Call the `create_note` tool -> creates a new file under `notes/` and
  registers it as a new resource immediately
- Call the `search_notes` tool -> greps all notes
- Invoke the `summarize_note` or `draft_reply` prompts against any note slug

## 4. `local_client.py` -- no Claude subscription needed

A local-LLM-driven client, for anyone without hosted-model access. Uses
[Ollama](https://ollama.com) to run a small model locally, and drives this
server's tools/prompts the same way a real host would. See
`docs/architecture.md`'s "local-LLM agent loop" section for how it's wired.

**Standalone** (you already have Ollama running locally):
```bash
ollama pull qwen2.5:1.5b   # or your own OLLAMA_MODEL
uv run python local_client.py
```
Configurable via env vars: `OLLAMA_HOST` (default `http://localhost:11434`),
`OLLAMA_MODEL` (default `qwen2.5:1.5b`), `OLLAMA_TEMPERATURE` (default `0.2`
-- see the reliability note below for why it's lower than Ollama's own
default of `0.8`).

**Via Docker** (Ollama and everything else runs in containers for you):
```bash
./startScript.sh
```
See `docs/docker.md` for what this does.

### REPL commands

| Command | Effect |
|---|---|
| *(anything else)* | Chat with the model. It may decide to call `create_note` or `search_notes` on its own. |
| `/tools` | List the tools available right now, read directly from the live MCP `list_tools()` result -- no model involved, so it's always correct (see the reliability note below for why this exists). |
| `/summarize <slug>` | Fetch the `summarize_note` prompt for that note and have the model produce the summary. |
| `/reply <slug> [tone]` | Fetch the `draft_reply` prompt (tone defaults to `friendly`) and have the model draft it. |
| `/help` | Show the command list. |
| `/quit`, `/exit` | Leave. |

### Example transcript

```
> search_notes for the word MCP please
I found a note titled "MCP Cheatsheet" that matches your search query. Here's what it contains:

- MCP (Model Context Protocol) standardizes how an LLM application (the
  **host**), interacts with an LLM client.
- Welcome: This is a seed note for the MCP notes server example.
```

Behind the scenes: the model received `search_notes`'s schema as an
available tool, decided to call it with `{"query": "MCP"}`, `local_client.py`
ran that through `session.call_tool(...)` against the real server, and fed
the matching lines back to the model to phrase into an answer.

**A note on the default model's reliability**: `qwen2.5:1.5b` is small
(~1GB) on purpose -- this server only has two trivial tools, so it doesn't
need a large model. That said, small models occasionally answer in plain
text instead of calling a tool on the first try; if that happens, rephrase
more directly ("call search_notes for X") or size up via `OLLAMA_MODEL`
(e.g. `qwen2.5:3b` or `llama3.1:8b`) if you want more consistent tool-calling.

**A sharper version of that problem**: asking the model *about itself* --
"what tools do you have", "list your MCP tools" -- is unreliable in the
other direction. Rather than answering in plain text, it will sometimes
call `create_note` or `search_notes` anyway (even with made-up arguments,
which can leave a stray note behind), because merely having a non-empty
`tools` list in the request measurably biases small models toward calling
*something*. This isn't fixable by prompt-tuning alone -- it was tested
against both `qwen2.5:1.5b` and `qwen2.5:3b` with no reliable improvement.
Use `/tools` for a guaranteed-correct answer to that specific question.
