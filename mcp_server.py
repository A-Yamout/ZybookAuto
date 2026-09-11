from __future__ import annotations

import os
from typing import Any

from pydantic import AnyHttpUrl
from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings

from app import build_client, ensure_worker, store, worker_pause

HOST = os.getenv("ZYBOOKAUTO_MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("ZYBOOKAUTO_MCP_PORT", "20030"))
TOKEN = os.getenv("ZYBOOKAUTO_MCP_TOKEN", "")
PUBLIC_URL = os.getenv("ZYBOOKAUTO_MCP_PUBLIC_URL", f"http://localhost:{PORT}/mcp")

if not TOKEN:
    raise RuntimeError(
        "ZYBOOKAUTO_MCP_TOKEN is required when the network MCP server is enabled"
    )


class StaticTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token != TOKEN:
            return None
        return AccessToken(
            token=token,
            client_id="zybookauto-agent",
            scopes=["zybookauto:control"],
        )


mcp = MCPServer(
    "ZybookAuto",
    token_verifier=StaticTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(os.getenv("ZYBOOKAUTO_MCP_ISSUER", f"http://localhost:{PORT}/")),
        resource_server_url=AnyHttpUrl(PUBLIC_URL),
        required_scopes=["zybookauto:control"],
    ),
)


@mcp.tool()
def list_books() -> list[dict[str, Any]]:
    """List ZyBooks available to the configured account."""
    client = build_client()
    return client.get_books()


@mcp.tool()
def queue_chapter(book_code: str, chapter_number: int, skip_complete: bool = True) -> dict[str, Any]:
    """Queue all sections in one chapter. By default, sections already complete are skipped."""
    client = build_client()
    chapters = client.get_chapters(book_code)
    chapter = next((c for c in chapters if int(c.get("number", -1)) == int(chapter_number)), None)
    if chapter is None:
        raise ValueError(f"Chapter {chapter_number} was not found in {book_code}")

    queued = []
    skipped = []
    for section in chapter.get("sections", []):
        section_number = int(section.get("canonical_section_number", section.get("number")))
        title = section.get("title", "")

        if skip_complete:
            try:
                progress = client.get_section_progress(book_code, int(chapter_number), section_number)
                if progress.get("complete"):
                    skipped.append({"section": section_number, "title": title, "reason": "already complete"})
                    continue
            except Exception as exc:
                skipped.append({"section": section_number, "title": title, "reason": f"progress check failed: {exc}"})
                continue

        job_id = store.enqueue(book_code, int(chapter_number), section_number, title)
        queued.append({"job_id": job_id, "section": section_number, "title": title})

    ensure_worker()
    return {
        "book_code": book_code,
        "chapter": int(chapter_number),
        "queued_count": len(queued),
        "skipped_count": len(skipped),
        "queued": queued,
        "skipped": skipped,
        "worker_paused": not worker_pause.is_set(),
    }


@mcp.tool()
def queue_sections(book_code: str, sections: list[str]) -> dict[str, Any]:
    """Queue specific sections written like ['1.1', '1.3', '2.4']."""
    client = build_client()
    chapters = {int(c["number"]): c for c in client.get_chapters(book_code)}
    queued = []

    for selector in sections:
        try:
            chapter_text, section_text = selector.split(".", 1)
            chapter_number = int(chapter_text)
            section_number = int(section_text)
        except Exception as exc:
            raise ValueError(f"Invalid section selector: {selector}") from exc

        chapter = chapters.get(chapter_number)
        if chapter is None:
            raise ValueError(f"Chapter {chapter_number} was not found")

        section = next(
            (
                s for s in chapter.get("sections", [])
                if int(s.get("canonical_section_number", s.get("number"))) == section_number
            ),
            None,
        )
        if section is None:
            raise ValueError(f"Section {selector} was not found")

        title = section.get("title", "")
        job_id = store.enqueue(book_code, chapter_number, section_number, title)
        queued.append({"job_id": job_id, "section": selector, "title": title})

    ensure_worker()
    return {"queued_count": len(queued), "queued": queued, "worker_paused": not worker_pause.is_set()}


@mcp.tool()
def start_queue() -> dict[str, Any]:
    """Start or resume background processing of queued work."""
    ensure_worker()
    worker_pause.set()
    return {"started": True, "worker_paused": False}


@mcp.tool()
def pause_queue() -> dict[str, Any]:
    """Pause the worker before it begins another queued job."""
    worker_pause.clear()
    return {"paused": True}


@mcp.tool()
def stop_queued_work() -> dict[str, Any]:
    """Cancel all jobs that have not started yet and pause the worker."""
    worker_pause.clear()
    with store.lock, store._conn() as conn:
        cur = conn.execute("UPDATE jobs SET status='cancelled' WHERE status='queued'")
        cancelled = cur.rowcount
    return {"cancelled": cancelled, "worker_paused": True}


@mcp.tool()
def get_progress(limit: int = 50) -> dict[str, Any]:
    """Return queue state, counts, running job details, and recent jobs."""
    jobs = store.jobs()[: max(1, min(int(limit), 200))]
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job["status"]] = counts.get(job["status"], 0) + 1

    running = next((job for job in jobs if job["status"] == "running"), None)
    total = sum(counts.values())
    finished = (
        counts.get("done", 0)
        + counts.get("submitted", 0)
        + counts.get("accepted", 0)
        + counts.get("failed", 0)
        + counts.get("cancelled", 0)
    )

    return {
        "worker_paused": not worker_pause.is_set(),
        "running": running,
        "counts": counts,
        "finished_jobs": finished,
        "total_jobs_returned": total,
        "jobs": jobs,
    }


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path="/mcp",
    )
