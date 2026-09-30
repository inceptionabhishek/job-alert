from __future__ import annotations

from html import escape
import json
from typing import Iterable
from urllib.parse import quote

from .http import HttpClient
from .models import Job, MatchResult


def format_message(job: Job, match: MatchResult) -> str:
    description = job.description.strip()
    if len(description) > 1200:
        description = description[:1197].rstrip() + "..."
    lines = [
        "🚨 <b>New matching job</b>",
        "",
        f"<b>{escape(job.title)}</b>",
        escape(job.company),
        f"📍 {escape(job.location or 'Location not listed')}",
        f"Match score: {match.score}",
    ]
    if job.posted_date:
        lines.append(f"Posted: {escape(str(job.posted_date))}")
    if match.reasons:
        lines.append(f"Why: {escape('; '.join(match.reasons))}")
    if description:
        lines.extend(["", escape(description)])
    if job.url:
        lines.extend(["", f'<a href="{escape(job.url, quote=True)}">View and apply</a>'])
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, http: HttpClient):
        self.token = token
        self.chat_id = chat_id
        self.http = http

    def send(self, job: Job, match: MatchResult) -> None:
        url = f"https://api.telegram.org/bot{quote(self.token, safe='')}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id,
            "text": format_message(job, match),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        self.http.request(url, data=payload, headers={"Content-Type": "application/json"})

