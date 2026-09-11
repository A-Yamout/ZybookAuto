from __future__ import annotations

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib import parse

import requests


class ZybooksError(RuntimeError):
    pass


class ZybooksClient:
    API = "https://zyserver.zybooks.com/v1"
    API2 = "https://zyserver2.zybooks.com/v1"

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.auth_token = ""
        self.user_id = ""
        self._build_key: str | None = None

    def _json(self, response: requests.Response):
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise ZybooksError(f"Non-JSON response from ZyBooks ({response.status_code})") from exc
        if isinstance(data, dict) and data.get("success") is False:
            raise ZybooksError(data.get("message") or data.get("error") or str(data))
        return data

    def signin(self):
        data = self._json(self.session.post(
            f"{self.API}/signin",
            json={"email": self.email, "password": self.password},
            timeout=30,
        ))
        self.auth_token = data["session"]["auth_token"]
        self.user_id = str(data["session"]["user_id"])
        self.session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
        return data

    def get_books(self):
        data = self._json(self.session.get(
            f"{self.API}/user/{self.user_id}/items",
            params={"items": '["zybooks"]'},
            timeout=30,
        ))
        return [b for b in data["items"]["zybooks"] if not b.get("autosubscribe")]

    def get_chapters(self, code: str):
        data = self._json(self.session.get(
            f"{self.API}/zybooks",
            params={"zybooks": json.dumps([code])},
            timeout=30,
        ))
        return data["zybooks"][0]["chapters"]

    def get_section(self, code: str, chapter: int, section: int):
        return self._json(self.session.get(
            f"{self.API}/zybook/{code}/chapter/{chapter}/section/{section}",
            timeout=30,
        ))["section"]

    @staticmethod
    def _resource_complete(resource: dict) -> bool:
        if resource.get("complete") is True or resource.get("completed") is True:
            return True
        parts = resource.get("parts")
        if isinstance(parts, list) and parts:
            states = []
            for p in parts:
                if isinstance(p, dict):
                    states.append(bool(p.get("complete") or p.get("completed")))
            if states:
                return all(states)
        progress = resource.get("progress")
        if isinstance(progress, dict):
            if progress.get("complete") is True:
                return True
            completed = progress.get("completed")
            total = progress.get("total")
            if isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
                return completed >= total
        return False

    def get_section_progress(self, code: str, chapter: int, section: int):
        data = self.get_section(code, chapter, section)
        resources = data.get("content_resources", [])
        completable = [r for r in resources if int(r.get("parts", 0) or 0) > 0 or "activity" in str(r.get("type", "")).lower()]
        completed = sum(1 for r in completable if self._resource_complete(r))
        total = len(completable)
        return {
            "complete": total > 0 and completed == total,
            "completed": completed,
            "total": total,
            "resources": resources,
        }

    def get_book_outline_with_progress(self, code: str):
        chapters = self.get_chapters(code)
        output = []
        for chapter in chapters:
            c = {"number": chapter["number"], "title": chapter.get("title", ""), "sections": []}
            for section in chapter.get("sections", []):
                sec_num = section.get("canonical_section_number", section.get("number"))
                try:
                    progress = self.get_section_progress(code, int(chapter["number"]), int(sec_num))
                except Exception as exc:
                    progress = {"complete": False, "completed": 0, "total": 0, "error": str(exc)}
                c["sections"].append({
                    "number": sec_num,
                    "title": section.get("title", ""),
                    "canonical_section_id": section.get("canonical_section_id"),
                    "progress": progress,
                })
            output.append(c)
        return {"book_code": code, "chapters": output}

    def _buildkey(self):
        if self._build_key:
            return self._build_key

        class Parser(HTMLParser):
            value = None
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "meta" and attrs.get("name") == "zybooks-web/config/environment":
                    content = attrs.get("content")
                    if content:
                        self.value = json.loads(parse.unquote(content))["APP"]["BUILDKEY"]

        parser = Parser()
        parser.feed(self.session.get("https://learn.zybooks.com", timeout=30).text)
        if not parser.value:
            raise ZybooksError("Could not determine ZyBooks build key")
        self._build_key = parser.value
        return parser.value

    @staticmethod
    def _timestamp():
        now = datetime.now(timezone.utc)
        return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _checksum(self, activity_id, timestamp, part):
        raw = f"content_resource/{activity_id}/activity{timestamp}{self.auth_token}{activity_id}{part}true{self._buildkey()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _mark_part(self, code: str, section_id: int, activity_id: int, part: int, delay: float):
        time.sleep(max(0.0, delay))
        ts = self._timestamp()
        payload = {
            "part": part,
            "complete": True,
            "metadata": "{}",
            "zybook_code": code,
            "auth_token": self.auth_token,
            "timestamp": ts,
            "__cs__": self._checksum(activity_id, ts, part),
        }
        return self._json(self.session.post(
            f"{self.API}/content_resource/{activity_id}/activity",
            json=payload,
            timeout=30,
        ))

    def complete_section(self, code: str, chapter: int, section: int, *, min_delay=8.0, max_delay=18.0, retries=3):
        data = self.get_section(code, chapter, section)
        section_id = data.get("canonical_section_id")
        if section_id is None:
            raise ZybooksError("Section has no canonical_section_id")

        for resource in data.get("content_resources", []):
            if self._resource_complete(resource):
                continue
            activity_id = resource.get("id")
            raw_parts = resource.get("parts", 0)
            if not activity_id or not isinstance(raw_parts, int) or raw_parts <= 0:
                continue

            for part in range(raw_parts):
                last_error = None
                for attempt in range(max(1, retries)):
                    try:
                        self._mark_part(
                            code,
                            int(section_id),
                            int(activity_id),
                            part,
                            random.uniform(min(min_delay, max_delay), max(min_delay, max_delay)),
                        )
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        time.sleep(min(30, 2 ** attempt + random.random()))
                if last_error:
                    raise ZybooksError(f"Activity {activity_id} part {part + 1} failed: {last_error}")
