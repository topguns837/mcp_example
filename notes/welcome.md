# Welcome

This is a seed note for the MCP notes server example.

MCP (Model Context Protocol) standardizes how an LLM application (the **host**),
through a **client** it embeds, talks to a **server** that exposes context and
capabilities. This project *is* one such server.

Three things a server can offer:

- **Resources** — read-only context (this very file, exposed as `note://welcome`)
- **Tools** — actions the model can invoke (`create_note`, `search_notes` here)
- **Prompts** — reusable, user-triggered message templates (`summarize_note`, `draft_reply`)

Edit this file, or better, create a new note with the `create_note` tool once the
server is running, and watch it show up as a new resource.
