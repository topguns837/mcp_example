# MCP Cheatsheet

Quick reference while implementing this server, tied to the spec pages:

## Core roles
- **Host**: the LLM application (e.g. Claude Code, Claude Desktop)
- **Client**: the connector inside the host, one per server connection
- **Server**: this program — exposes Resources/Tools/Prompts over JSON-RPC 2.0

## Capability negotiation
On connect, client and server exchange an `initialize` request/response declaring
which capabilities each side supports, e.g.:

```json
{ "capabilities": { "prompts": { "listChanged": true } } }
```

## The three server primitives
| Primitive | Who invokes it | Read or act | Example method |
|---|---|---|---|
| Resource  | Client/user (context) | Read-only  | `resources/list`, `resources/read` |
| Tool      | The model              | Can have side effects | `tools/list`, `tools/call` |
| Prompt    | The user (explicitly)  | Returns message templates | `prompts/list`, `prompts/get` |

## Transports
- **stdio** — server is a subprocess, talks JSON-RPC over stdin/stdout (what this
  project uses; simplest, no networking)
- **Streamable HTTP** — server is a long-running HTTP endpoint, for remote/shared
  servers

## Prompt content types
A `PromptMessage.content` can be `text`, `image`, `audio`, or an embedded `resource`
(a resource's contents inlined directly into the conversation).
