# ptashka MCP server

Gives AI agents (Claude Code, Claude Desktop, or anything that speaks
[MCP](https://modelcontextprotocol.io)) tools to track and work on tasks in ptashka.

It's a thin client over ptashka's REST API, authenticated with a personal API token. The agent gets
exactly the permissions of that token and of its user's role on each board, and there is
deliberately no tool that deletes anything (archiving, which is reversible, is as far as it goes).

## Tools

| Tool | | What it does |
|---|---|---|
| `whoami` | read | The token's user, and their boards and roles |
| `get_board` | read | Lists and cards, with labels and assignees by name |
| `search_cards` | read | Cross-board search; by default your open tasks |
| `get_card` | read | Description, checklist, recent comments and history, `version` |
| `whats_new` | read | What changed since a cursor, as sentences (for polling) |
| `create_card` | write | Add a card to a list (editor) |
| `update_card` | write | Title, description, due date, complete/reopen, archive (`completed` only for contributors) |
| `move_card` | write | Move or reorder; into the done list completes it |
| `assign_card` | write | Assign/unassign (contributors: only themselves) |
| `label_card` | write | Add/remove a label, by name |
| `add_comment` | write | Comment on a card |
| `add_checklist_item`, `check_item` | write | Checklist |

`PTASHKA_READ_ONLY=1` registers only the read tools.

## Setting up an agent

1. In ptashka, create an account for the agent (or use your own), have an admin approve it, and add
   it to boards as a **contributor**: it can move, complete, tick, comment and take cards, but not
   edit or delete them.
2. Create a token for it: the *API tokens* page, or on the server
   `python -m ptashka.cli.create_token --email agent@example.com --name "Research agent" --scope write`.
3. Register the server with your client:

**Claude Code**
```bash
claude mcp add ptashka \
  -e PTASHKA_URL=https://ptashka.example.com \
  -e PTASHKA_TOKEN=ptk_... \
  -- uv --directory /path/to/ptashka/mcp-server run ptashka-mcp
```
(`--scope user` to have it in every project, instead of only the current one.)

**Claude Desktop** (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "ptashka": {
      "command": "uv",
      "args": ["--directory", "/path/to/ptashka/mcp-server", "run", "ptashka-mcp"],
      "env": { "PTASHKA_URL": "https://ptashka.example.com", "PTASHKA_TOKEN": "ptk_..." }
    }
  }
}
```

`PTASHKA_URL` defaults to `http://localhost:8020` (the development backend). In production it's the
public address (nginx forwards `/api` to the backend).

## Develop

```bash
uv venv && uv pip install -e ../backend -e ".[dev]"   # The backend is needed by the tests only.
.venv/bin/pytest      # Tools end to end against the real backend app, in-process (no server needed)
.venv/bin/pyright
```
