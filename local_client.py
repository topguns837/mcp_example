"""
local_client.py -- chat with notes_server.py using a LOCAL LLM (via Ollama)
instead of a hosted/paid model.

This is a second, independent MCP *client* implementation (see also
trace_client.py, which speaks raw JSON-RPC by hand). This one uses the
official `mcp` SDK's client-side API (`stdio_client` + `ClientSession`) to
talk to the server, and layers a small agent loop on top that lets a local
model decide when to call the server's tools.

Two protocols are in play here, and it's worth keeping them straight:
  1. MCP itself, between this process and notes_server.py (spawned as a
     subprocess over stdio) -- `session.list_tools()`, `session.call_tool()`,
     `session.get_prompt()`.
  2. Ollama's tool-calling chat protocol, between this process and an Ollama
     server (local, or the `ollama` container over the Docker network) --
     plain HTTP POSTs to `/api/chat`, done here with raw `httpx` calls (no
     `ollama` SDK) so the request/response JSON stays visible, in keeping
     with trace_client.py's "show the wire protocol" spirit.

Run it with:
    uv run python local_client.py

See docs/testing.md and docs/architecture.md for more.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_SCRIPT = Path(__file__).parent / "notes_server.py"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
# Ollama's chat endpoint defaults to temperature 0.8. A lower temperature
# makes a small model like this more consistent at straightforward,
# factual-sounding answers (e.g. "what tools do you have") at some cost to
# response variety -- worth it here since accuracy matters more than
# creativity for a tool-driven assistant.
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.2"))

SYSTEM_PROMPT = (
    "You are a helpful assistant connected to a local notes MCP server. The "
    "tools you may use are exactly the ones provided to you in this "
    "request's tool list -- rely on their live names, descriptions, and "
    "parameters rather than assuming what exists. If the user asks what "
    "tools, functions, or capabilities you have (e.g. 'list your tools', "
    "'list your MCP tools'), that is a question about yourself: answer in "
    "plain text using the tool list you were given, one line per tool. Do "
    "NOT call a tool merely to answer a question about yourself. If a tool "
    "call fails or referenced data doesn't exist, tell the user plainly."
)

HELP_TEXT = """\
Commands:
  <anything else>        chat with the model (it may call create_note / search_notes)
  /summarize <slug>       ask the model to summarize note <slug>
  /reply <slug> [tone]     ask the model to draft a reply based on note <slug>
                          (tone defaults to "friendly")
  /help                   show this message
  /quit, /exit             leave
"""


def mcp_tool_to_ollama_tool(tool: types.Tool) -> dict[str, Any]:
    """Convert an MCP Tool (JSON-Schema input_schema) into the tool-def shape
    Ollama's /api/chat expects in its `tools` list."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


async def call_ollama_chat(
    client: httpx.AsyncClient, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    """POST /api/chat and return the parsed response JSON. Non-streaming, so
    the whole reply (including any tool_calls) arrives in one response body."""
    response = await client.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": OLLAMA_TEMPERATURE},
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()


def mcp_content_to_text(content: list[types.ContentBlock]) -> str:
    """Flatten a list of MCP content blocks (TextContent, etc.) into a
    single string, for handing back to the model as plain-text context."""
    parts = []
    for block in content:
        if isinstance(block, types.TextContent):
            parts.append(block.text)
        elif isinstance(block, types.EmbeddedResource):
            resource = block.resource
            text = getattr(resource, "text", None)
            parts.append(text if text is not None else str(resource))
        else:
            parts.append(str(block))
    return "\n".join(parts)


def mcp_result_to_text(result: types.CallToolResult) -> str:
    text = mcp_content_to_text(result.content)
    if result.is_error:
        return f"Error calling tool: {text}"
    return text


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """Ollama's documented shape has tool_calls[].function.arguments as an
    already-parsed object, but small models sometimes emit it as a JSON
    string instead -- handle both defensively."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


async def run_agent_turn(
    session: ClientSession,
    http_client: httpx.AsyncClient,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tool_hops: int = 6,
) -> str:
    """Drive the tool-calling loop: ask Ollama, resolve any tool_calls via
    MCP, feed results back, repeat until the model answers in plain text (or
    the hop cap is hit, in case a small model loops instead of answering)."""
    for _ in range(max_tool_hops):
        response = await call_ollama_chat(http_client, messages, tools)
        message = response["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            text = message.get("content", "")
            messages.append({"role": "assistant", "content": text})
            return text

        messages.append(message)
        for call in tool_calls:
            function = call["function"]
            name = function["name"]
            arguments = parse_tool_arguments(function.get("arguments"))
            try:
                result = await session.call_tool(name, arguments)
                text = mcp_result_to_text(result)
            except Exception as exc:  # server-raised errors (e.g. bad slug)
                text = f"Error calling tool '{name}': {exc}"
            messages.append({"role": "tool", "content": text})

    return "(gave up after too many tool calls in a row -- try rephrasing)"


async def render_prompt_via_llm(
    session: ClientSession,
    http_client: httpx.AsyncClient,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    name: str,
    arguments: dict[str, str],
) -> str:
    """Handle a slash command: fetch an MCP *prompt* template directly (the
    user is explicitly choosing this, not the model deciding to call a
    tool), then run one plain (non-tool) turn through the LLM so it actually
    produces the summary/reply text, instead of just echoing the template."""
    try:
        prompt_result = await session.get_prompt(name, arguments)
    except Exception as exc:
        return f"Error fetching prompt '{name}': {exc}"

    for prompt_message in prompt_result.messages:
        content = prompt_message.content
        text = mcp_content_to_text(content if isinstance(content, list) else [content])
        messages.append({"role": prompt_message.role, "content": text})

    response = await call_ollama_chat(http_client, messages, tools=[])
    text = response["message"].get("content", "")
    messages.append({"role": "assistant", "content": text})
    return text


def parse_slash_command(line: str) -> tuple[str, list[str]] | None:
    if not line.startswith("/"):
        return None
    parts = line[1:].split()
    if not parts:
        return None
    return parts[0], parts[1:]


async def repl(session: ClientSession, http_client: httpx.AsyncClient, tools: list[dict[str, Any]]) -> None:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Connected to notes-server. Model: {OLLAMA_MODEL} @ {OLLAMA_HOST}")
    print(HELP_TEXT)

    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, input, "> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        line = line.strip()
        if not line:
            continue

        command = parse_slash_command(line)
        if command is not None:
            name, args = command
            if name in ("quit", "exit"):
                return
            if name == "help":
                print(HELP_TEXT)
                continue
            if name == "summarize":
                if not args:
                    print("usage: /summarize <slug>")
                    continue
                answer = await render_prompt_via_llm(
                    session, http_client, tools, messages, "summarize_note", {"slug": args[0]}
                )
                print(answer)
                continue
            if name == "reply":
                if not args:
                    print("usage: /reply <slug> [tone]")
                    continue
                slug = args[0]
                prompt_args = {"slug": slug}
                if len(args) > 1:
                    prompt_args["tone"] = args[1]
                answer = await render_prompt_via_llm(
                    session, http_client, tools, messages, "draft_reply", prompt_args
                )
                print(answer)
                continue
            print(f"Unknown command: /{name}. Try /help.")
            continue

        messages.append({"role": "user", "content": line})
        answer = await run_agent_turn(session, http_client, tools, messages)
        print(answer)


async def main() -> None:
    server_params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
    server_log = open(Path(__file__).parent / "notes_server.log", "w")
    # notes_server.py logs its own errors (e.g. a bad note slug) to stderr
    # with a full traceback; keep those out of the REPL and route them to a
    # file instead, since the REPL already prints a clean one-line error.
    async with stdio_client(server_params, errlog=server_log) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools = [mcp_tool_to_ollama_tool(t) for t in tools_result.tools]
            async with httpx.AsyncClient() as http_client:
                await repl(session, http_client, tools)


if __name__ == "__main__":
    asyncio.run(main())
