# ZybookAuto

ZybookAuto automates ZyBooks activity processing through a persistent queue, a local web dashboard, and an MCP interface that can be controlled by an AI agent.

> **Note:** Use this only on ZyBooks accounts and coursework you are authorized to access, and make sure your use complies with your course and ZyBooks policies.

---

## Current architecture

The Docker deployment runs two services inside one container:

- `app.py` — Flask dashboard **and the only background job executor**
- `mcp_server.py` — Streamable HTTP MCP control interface

Both processes share the same SQLite database. MCP never starts its own execution thread. It only adds jobs and changes shared queue control state in SQLite.

This is important because older builds could accidentally create one worker in `app.py` and another in `mcp_server.py`, which allowed two jobs to appear as `running` at the same time.

The worker now enforces:

```text
at most one running job
```

Job claiming uses an atomic SQLite transaction, so even an accidental second claimant cannot start another job while one is already running.

---

## Queue states

Jobs can appear as:

```text
queued
running
done
submitted
failed
cancelled
```

Typical flow:

```text
queued -> running -> done
```

`submitted` means the activity POST was accepted by ZyBooks, but the read-back response did not expose enough completion information to prove the whole section was complete. It is not the same as a failed submission.

### Restart recovery

If the container or worker process restarts while a job is marked `running`, that job is automatically changed back to `queued` when the sole worker starts again.

Before redoing work, the worker refreshes the current ZyBooks section state. If ZyBooks already reports the section complete, the recovered job is marked `done` without resubmitting it.

---

## Shared worker controls

Pause/resume state is stored in SQLite rather than in a process-local Python event. This means the dashboard and MCP server now control the same worker state.

- **Resume / start** sets `worker_enabled=1`
- **Pause** sets `worker_enabled=0`
- **Stop queued work** pauses the worker and marks all not-yet-started jobs `cancelled`

Pausing does not interrupt a section that is already executing. It prevents the next queued job from starting.

---

## What it can do

The current integration supports:

- List ZyBooks available to the configured account
- Read chapter and section completion state
- Queue an entire chapter
- Skip sections already reported complete
- Queue specific sections such as `1.1`, `1.3`, and `2.4`
- Start or resume queued work
- Pause before the next job
- Cancel work that has not started
- Report current queue state and recent jobs
- Run continuously in Docker
- Expose an authenticated Streamable HTTP MCP endpoint

---

## Completion detection

Completion checks are refreshed directly from ZyBooks before chapter queue decisions are made.

The client recognizes multiple completion representations used by ZyBooks, including:

- `complete` / `completed` flags
- completed/total counters
- percentage values
- nested progress objects
- part-level completion state
- section-level completion fallback data

The MCP `queue_chapter` response includes `completion_checks` so an agent can inspect why a section was queued or skipped.

Issue #3 covered the older stale/incomplete completion detection behavior and has been resolved.

---

## Dashboard

By default the dashboard is available at:

```text
http://localhost:8765
```

When accessed from another machine, replace `localhost` with the Docker host's IP address.

The dashboard provides:

- Book selection
- Chapter/section selection
- Collapsed chapters with chapter-level select-all
- Queue controls
- Worker status
- Live execution telemetry
- Recent job history

---

## MCP server

The MCP server uses **Streamable HTTP**.

Default endpoint:

```text
http://localhost:20030/mcp
```

For a public deployment behind Cloudflare Tunnel, set:

```text
ZYBOOKAUTO_MCP_PUBLIC_URL=https://mcp.example.com/mcp
```

The MCP server requires a bearer token:

```text
Authorization: Bearer <ZYBOOKAUTO_MCP_TOKEN>
```

Current MCP tools:

| Tool | Purpose |
| --- | --- |
| `list_books` | List configured ZyBooks |
| `queue_chapter` | Queue a chapter and optionally skip completed sections |
| `queue_sections` | Queue selected sections |
| `start_queue` | Enable/resume the shared worker |
| `pause_queue` | Pause before the next job starts |
| `stop_queued_work` | Pause and cancel queued jobs |
| `get_progress` | Return counts, current running job, and recent jobs |

Because `mcp_server.py` is a separate process, it intentionally does **not** call `ensure_worker()`. `app.py` owns execution for the lifetime of the service.

---

## Docker Compose

Build and start in the background:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
```

Watch logs:

```bash
docker compose logs -f zybookauto
```

Stop the service:

```bash
docker compose down
```

The SQLite database is stored in the persistent `zybookauto-data` Docker volume, so rebuilding the image does not erase queue state or saved settings.

### Environment variables

A typical `.env` file can contain:

```text
ZYBOOKS_EMAIL=student@example.com
ZYBOOKS_PASSWORD=replace-me
ZYBOOKAUTO_SECRET=replace-with-a-random-secret
ZYBOOKAUTO_MCP_TOKEN=replace-with-a-long-random-token
ZYBOOKAUTO_MCP_PUBLIC_URL=https://mcp.example.com/mcp
```

Generate a random MCP token with:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

---

## Example agent workflow

Once the MCP server is connected to an AI agent, normal requests can map to the MCP tools.

```text
What ZyBooks do I have?
```

```text
Queue chapter 1, skipping anything already complete.
```

```text
Start the queue.
```

```text
How far along is it?
```

```text
Pause after the current section.
```

The AI agent can inspect `get_progress` later without interrupting the worker.

---

## ZyBooks authentication

The project includes the newer ZyBooks authentication behavior required after the API change that caused `Ill-formatted request` errors in older builds.

Current behavior:

- Sign-in retrieves the `auth_token`
- The requests session sets `Authorization: Bearer <token>`
- GET requests do not send the deprecated token query parameter
- Activity POST requests retain the token in the request body where required for compatibility

---

## Tests

Run the unit tests with:

```bash
python -m unittest discover -s tests
```

Regression coverage includes:

- Completion-state parsing
- Fresh completed/incomplete section handling
- Only one job being claimable as `running`
- Recovery of stale `running` jobs after restart
- Shared persisted worker pause/resume state

---

## Development checklist

When changing queue behavior, verify at minimum:

1. Books can be listed successfully.
2. Individual sections can be queued.
3. A whole chapter can be queued.
4. Already-completed sections are skipped using fresh ZyBooks state.
5. Only one job can be `running` at a time.
6. Dashboard and MCP pause/resume controls affect the same worker.
7. Restarting the service recovers stale `running` jobs safely.
8. MCP `get_progress` accurately reflects the database queue state.
9. Docker starts both the dashboard and MCP processes successfully.

If you encounter a bug, open a GitHub issue with the affected book/chapter/section, current queue state, expected behavior, and observed behavior.
