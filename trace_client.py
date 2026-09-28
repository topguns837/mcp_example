"""
trace_client.py -- prints the EXACT JSON-RPC 2.0 messages exchanged with
notes_server.py over stdio, with no SDK abstraction hiding the wire format.

This plays the role of the "client" side of MCP by hand: it spawns the server
as a subprocess (same as Claude Code does), writes one JSON object per line to
its stdin, and reads one JSON object per line back from its stdout -- which is
literally the whole MCP stdio transport. Every message actually sent/received
is printed before/after it crosses the pipe.

Run it with:
    uv run python trace_client.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SERVER_SCRIPT = Path(__file__).parent / "notes_server.py"
PYTHON = sys.executable  # the venv's python that uv set up


def send(proc: subprocess.Popen, message: dict) -> None:
    """Write one JSON-RPC message as a single line to the server's stdin."""
    line = json.dumps(message)
    label = "REQUEST" if "id" in message else "NOTIFICATION"
    print(f"\n>>> CLIENT -> SERVER  ({label})")
    print(json.dumps(message, indent=2))
    assert proc.stdin is not None
    proc.stdin.write(line + "\n")
    proc.stdin.flush()


def recv(proc: subprocess.Popen) -> dict:
    """Read exactly one JSON-RPC message line back from the server's stdout."""
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"Server closed stdout unexpectedly. stderr:\n{stderr}")
    message = json.loads(line)
    print("<<< SERVER -> CLIENT  (RESPONSE)")
    print(json.dumps(message, indent=2))
    return message


def main() -> None:
    proc = subprocess.Popen(
        [PYTHON, str(SERVER_SCRIPT)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )

    try:
        # 1. The `initialize` handshake -- every MCP connection starts here.
        # The client declares its own capabilities; the server responds with
        # its name/version and which capabilities (resources/tools/prompts)
        # it supports.
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "trace-client", "version": "0.1.0"},
                },
            },
        )
        recv(proc)

        # 2. `initialized` notification -- note: no "id" field. Notifications
        # get no response; this just tells the server the handshake is done.
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3. List resources -- see the seed notes come back as Resource objects.
        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}})
        recv(proc)

        # 4. Call a tool -- ask the model-facing `create_note` tool to act.
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "create_note",
                    "arguments": {
                        "title": "Traced Note",
                        "body": "Created via a hand-written JSON-RPC request.",
                    },
                },
            },
        )
        recv(proc)

        # 5. Get a prompt -- see the EmbeddedResource content type in the
        # response, exactly as described on the spec's prompts page.
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "prompts/get",
                "params": {"name": "summarize_note", "arguments": {"slug": "traced-note"}},
            },
        )
        recv(proc)

    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
