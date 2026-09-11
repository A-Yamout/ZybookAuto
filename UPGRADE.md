# ZybookAuto dashboard upgrade

This branch adds a local web dashboard and a persistent background queue around the original ZyBooks automation concept.

## Features

- Signs in using the current Bearer-token authentication flow.
- Lists subscribed ZyBooks.
- Reads each chapter/section and attempts to infer its current completion state from the section resource payload.
- Disables already-complete sections in the selector.
- Lets the user select individual incomplete sections or all incomplete sections.
- Stores queued jobs and settings in SQLite.
- Runs one section at a time in a background worker.
- Supports pause, resume, cancelling queued work, retries, exponential backoff, and configurable pacing.
- Re-reads section progress before execution so work that became complete is skipped.
- Re-reads section progress after execution and reports accepted-but-unverified submissions separately from hard failures.
- Includes a local MCP server for AI-agent control of queueing, start/pause/stop, and progress inspection.
- Keeps the original `ZybookAuto.py` untouched for comparison.

## Run dashboard

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ZYBOOKS_EMAIL='you@example.com'
export ZYBOOKS_PASSWORD='your-password'
export ZYBOOKAUTO_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

Open `http://127.0.0.1:8765`.

Credentials may alternatively be entered in the dashboard. Environment variables are preferable because dashboard-entered credentials are stored locally in `zybookauto.db`.

## Run MCP server

In a second terminal, using the same virtual environment and environment variables:

```bash
source .venv/bin/activate
python mcp_server.py
```

The MCP server uses Streamable HTTP and binds to `127.0.0.1:8766` by default. It has no application-level authentication, so keep it bound to localhost unless you add a trusted network/authentication layer yourself.

Available MCP tools:

- `list_books()`
- `queue_chapter(book_code, chapter_number, skip_complete=true)`
- `queue_sections(book_code, sections)` where sections look like `["1.1", "1.3"]`
- `start_queue()`
- `pause_queue()`
- `stop_queued_work()`
- `get_progress(limit=50)`

Example agent workflow:

1. Call `list_books` to identify the ZyBook code.
2. Call `queue_chapter` with chapter `1`.
3. Call `start_queue`.
4. Call `get_progress` whenever you want current queue status.

You can override the local MCP host/port with:

```bash
export ZYBOOKAUTO_MCP_HOST=127.0.0.1
export ZYBOOKAUTO_MCP_PORT=8766
```

For stdio-based MCP clients, set:

```bash
export ZYBOOKAUTO_MCP_TRANSPORT=stdio
python mcp_server.py
```

## Important compatibility note

ZyBooks' API is private and can change without notice. The progress parser deliberately accepts several common completion shapes (`complete`, `completed`, `progress`, and part-level state), but a live account is needed to verify the exact response shape for the user's current books. If a section shows `0/0` or `sync error`, inspect the returned section payload and extend `_resource_complete()` rather than assuming it is incomplete.

The executor only attempts resources that expose a positive integer `parts` count. Unsupported resource types are skipped rather than guessed.
