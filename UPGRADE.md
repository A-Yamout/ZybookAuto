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
- Re-reads section progress after execution and marks a job done only if ZyBooks reports it complete.
- Keeps the original `ZybookAuto.py` untouched for comparison.

## Run

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

## Important compatibility note

ZyBooks' API is private and can change without notice. The progress parser deliberately accepts several common completion shapes (`complete`, `completed`, `progress`, and part-level state), but a live account is needed to verify the exact response shape for the user's current books. If a section shows `0/0` or `sync error`, inspect the returned section payload and extend `_resource_complete()` rather than assuming it is incomplete.

The executor only attempts resources that expose a positive integer `parts` count. Unsupported resource types are skipped rather than guessed.
