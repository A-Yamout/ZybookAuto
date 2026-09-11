# ZybookAuto

ZybookAuto automates ZyBooks activity processing and now exposes a queue-based workflow that can be controlled from ChatGPT through the connected ZyBooks tool.

> **Note:** This project interacts with ZyBooks on your behalf. Use it only on accounts and coursework you are authorized to access, and make sure your use complies with your school and ZyBooks policies.

---

## What it can do

The current ChatGPT integration supports:

- List the ZyBooks available to the configured account
- Queue an entire chapter
- Queue specific sections such as `1.1`, `1.3`, and `2.4`
- Start or resume queued work
- Pause the worker before it begins the next queued job
- Cancel jobs that have not started yet
- Check queue state, running jobs, recent jobs, and counts
- Attempt to skip sections that are already complete when a chapter is queued

The queue runs separately from the ChatGPT conversation, so ChatGPT can submit work, inspect its state, and control the worker through the tool interface.

---

## Example ChatGPT workflow

Once the ZyBooks tool is connected, you can use normal language in ChatGPT.

Examples:

```text
What ZyBooks do I have?
```

```text
Do the entire first chapter.
```

```text
Queue sections 2.1, 2.3, and 2.5.
```

```text
Start the queue.
```

```text
Check my ZyBooks progress.
```

```text
Pause after the current section.
```

```text
Cancel everything that has not started yet.
```

For a full chapter, ChatGPT first queues the chapter and then starts the worker. By default, the chapter queue is configured to skip sections that the backend reports as already complete.

---

## Queue behavior

A queued job generally moves through these states:

```text
queued -> running -> finished
```

The progress tool can report:

- Whether the worker is paused
- The currently running job
- Number of queued jobs
- Number of running jobs
- Recent job information
- Errors returned by jobs

### Pause

Pausing does not interrupt the job that is already running. It prevents the worker from beginning another queued job after the current one finishes.

### Stop / cancel queued work

Stopping queued work removes jobs that have **not started yet** and pauses the worker.

A job that is already running cannot currently be selectively removed through the ChatGPT tool interface.

---

## Known issue: completed-section detection

The current `skip_complete` behavior is **not fully reliable**.

During testing, sections `1.6` and `1.7` were already complete in ZyBooks but were still queued when Chapter 1 was submitted with completed sections set to be skipped.

Until this is fixed, do not treat the automatic completion check as authoritative. If you know which sections are already complete, the safest approach is to queue only the specific sections that still need work.

Tracking issue: **#3 - Completed ZyBooks sections are not reliably detected before queueing**.

A future fix should refresh completion information immediately before queue creation, avoid stale cached state, and verify section completion more directly.

---

## Current tool operations

The ChatGPT-facing integration currently exposes operations equivalent to:

| Operation | Purpose |
| --- | --- |
| `list_books` | List ZyBooks available to the configured account |
| `queue_chapter` | Queue every section in a chapter, optionally skipping completed sections |
| `queue_sections` | Queue specific section numbers |
| `start_queue` | Start or resume processing |
| `pause_queue` | Pause before the next queued job begins |
| `stop_queued_work` | Cancel jobs that have not started and pause the worker |
| `get_progress` | Return worker state, counts, running job details, and recent jobs |

---

## Installation / legacy script

The original Python script requires the `requests` package:

```bash
pip install requests
```

The repository originally operated as a direct Python automation script. The current setup adds a service/tool layer around that functionality so it can be controlled remotely from ChatGPT rather than requiring every action to be started manually from the command line.

---

## Authentication update

ZyBooks authentication was updated to address the `Ill-formatted request` error caused by changes to how the ZyBooks API accepts authentication.

Current behavior includes:

- The sign-in flow retrieves the `auth_token`
- The session uses an `Authorization: Bearer <token>` header
- GET requests no longer rely on the deprecated token query parameter
- POST requests retain legacy token handling where required

---

## Development notes

When changing the queue or ChatGPT integration, verify at minimum:

1. A book can be listed successfully.
2. Individual sections can be queued.
3. A full chapter can be queued.
4. Starting, pausing, and stopping the queue behave correctly.
5. Progress accurately reflects queued and running jobs.
6. Already-completed sections are detected against fresh ZyBooks state rather than stale cached data.

If you encounter a bug, open a GitHub issue with the affected book/chapter/section, the queue state, and the expected versus observed behavior.
