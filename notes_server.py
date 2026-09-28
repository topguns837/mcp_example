"""
notes_server.py -- a minimal MCP server for learning Resources, Tools, and Prompts.

Run it directly as a stdio MCP server (a client/host launches this as a
subprocess and talks JSON-RPC 2.0 over stdin/stdout):

    uv run python notes_server.py

Or poke at it interactively with the official MCP Inspector dev UI:

    uv run mcp dev notes_server.py

See notes/mcp-cheatsheet.md and PLAN.md for how each piece below maps back to
the MCP specification (https://modelcontextprotocol.io/specification).
"""

import re
from pathlib import Path

from mcp.server.mcpserver import Message, MCPServer
from mcp.server.mcpserver.resources import DirectoryResource, FileResource

NOTES_DIR = Path(__file__).parent / "notes"
NOTES_DIR.mkdir(exist_ok=True)

server = MCPServer(
    "notes-server",
    instructions=(
        "Exposes local markdown notes as Resources, lets the model create and "
        "search notes as Tools, and offers Prompts to summarize a note or draft "
        "a reply based on one."
    ),
)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "note"


def _note_path(slug: str) -> Path:
    return NOTES_DIR / f"{slug}.md"


def _register_note_resource(slug: str, path: Path) -> None:
    """Register one markdown file as a concrete MCP resource (note://<slug>)
    so it shows up in a `resources/list` response."""
    server.add_resource(
        FileResource(
            uri=f"note://{slug}",
            name=slug,
            title=slug.replace("-", " ").title(),
            description=f"Markdown note '{slug}.md'",
            mime_type="text/markdown",
            path=path,
        )
    )


# --- Resources ---------------------------------------------------------
# Resources are read-only context that the client/user pulls in -- the model
# does not "call" a resource the way it calls a tool.

# One concrete resource per note file that already exists on disk, so they
# appear immediately in `resources/list`.
for note_path in sorted(NOTES_DIR.glob("*.md")):
    _register_note_resource(note_path.stem, note_path)

# A different *kind* of resource: a directory listing (JSON), to show that a
# resource doesn't have to be "one file's contents" -- it's just anything
# addressable by a URI.
server.add_resource(
    DirectoryResource(
        uri="note://directory",
        name="notes-directory",
        title="All notes (directory listing)",
        description="JSON listing of every file under notes/",
        path=NOTES_DIR,
    )
)


@server.resource("note://{slug}")
def read_note(slug: str) -> str:
    """Read a single note by slug.

    This is a *template* resource (the URI has a `{slug}` placeholder), so
    unlike the concrete resources registered above, it is evaluated fresh on
    every read -- which means it can serve notes created after startup (e.g.
    via the create_note tool below) even before they're separately
    registered as concrete resources.
    """
    path = _note_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"No such note: {slug}")
    return path.read_text(encoding="utf-8")


# --- Tools ---------------------------------------------------------------
# Tools are invoked BY THE MODEL to take actions or fetch on-demand data, and
# unlike resources they can have side effects.

@server.tool()
def create_note(title: str, body: str) -> str:
    """Create a new markdown note and register it as an MCP resource.

    Args:
        title: Short title for the note; used to derive its slug/filename.
        body: Markdown body content for the note.
    """
    slug = _slugify(title)
    path = _note_path(slug)
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    _register_note_resource(slug, path)
    return f"Created note '{slug}' at note://{slug}"


@server.tool()
def search_notes(query: str) -> list[str]:
    """Search every note for a case-insensitive substring match.

    Args:
        query: Text to search for across all notes' contents.

    Returns:
        A list of "slug: matching line" strings, one per line that matched.
    """
    query_lower = query.lower()
    hits: list[str] = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if query_lower in line.lower():
                hits.append(f"{path.stem}: {line.strip()}")
    return hits


# --- Prompts ---------------------------------------------------------------
# Prompts are user-triggered templates (often surfaced by a host as slash
# commands) that return a list of messages to seed a conversation.

@server.prompt()
def summarize_note(slug: str) -> list[Message]:
    """Ask the model to summarize a note.

    Demonstrates the `EmbeddedResource` content type from the spec: the
    note's content is inlined directly into the prompt as a resource block,
    rather than just pasted as plain text.
    """
    path = _note_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"No such note: {slug}")
    return [
        {
            "role": "user",
            "content": (
                f"Please summarize the following note (note://{slug}) "
                "in 2-3 sentences."
            ),
        },
        {
            "role": "user",
            "content": {
                "type": "resource",
                "resource": {
                    "uri": f"note://{slug}",
                    "mimeType": "text/markdown",
                    "text": path.read_text(encoding="utf-8"),
                },
            },
        },
    ]


@server.prompt()
def draft_reply(slug: str, tone: str = "friendly") -> str:
    """Draft a reply based on a note's content, in a requested tone.

    Args:
        slug: The note to base the reply on.
        tone: Desired tone, e.g. "friendly", "formal", "brief".
    """
    path = _note_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"No such note: {slug}")
    content = path.read_text(encoding="utf-8")
    return f"Draft a {tone} reply based on this note:\n\n{content}"


if __name__ == "__main__":
    # stdio transport: this process is meant to be launched as a subprocess by
    # an MCP client (Claude Code, Claude Desktop, MCP Inspector) which speaks
    # JSON-RPC 2.0 over stdin/stdout. Running it directly in a plain terminal
    # will look like it "hangs" -- it's just waiting for a client to connect.
    server.run()
