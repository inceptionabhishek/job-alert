from __future__ import annotations

import logging
from urllib.parse import urlencode, urljoin

from job_alert.models import Job
from .base import SourceAdapter
from .utils import plain_text

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.amazon.jobs/en/search.json"
SITE_URL = "https://www.amazon.jobs"


class AmazonAdapter(SourceAdapter):
    """Read the public Amazon Jobs search response, optionally country-filtered."""

    def fetch(self) -> list[Job]:
        queries = self.config.get("search_queries", ["software development engineer ii", "backend engineer"])
        if not isinstance(queries, list) or not queries or not all(isinstance(q, str) and q.strip() for q in queries):
            raise ValueError(f"{self.name}: search_queries must be a non-empty list of strings")
        page_size = int(self.config.get("page_size", 50))
        max_pages = int(self.config.get("max_pages", 10))
        if not 1 <= page_size <= 50 or not 1 <= max_pages <= 20:
            raise ValueError(f"{self.name}: page_size must be 1-50 and max_pages must be 1-20")

        jobs: dict[str, Job] = {}
        country = str(self.config.get("country", "IND")).upper().strip()
        for query in queries:
            offset = 0
            for page in range(max_pages):
                parameters = {
                    "base_query": query,
                    "sort": "recent",
                    "offset": offset,
                    "result_limit": page_size,
                }
                if country:
                    parameters["country"] = country
                payload = self.http.get_json(f"{SEARCH_URL}?{urlencode(parameters)}")
                if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                    raise ValueError(f"{self.name}: Amazon search response did not contain a jobs list")
                if payload.get("error"):
                    raise ValueError(f"{self.name}: Amazon search returned an error: {payload['error']}")
                results = payload["jobs"]
                for item in results:
                    if not isinstance(item, dict) or (country and item.get("country_code") != country):
                        continue
                    external_id = str(item.get("id_icims") or item.get("id") or "")
                    path = str(item.get("job_path") or "")
                    if not external_id or not path.startswith("/en/jobs/") or not item.get("title"):
                        logger.warning("Skipping Amazon result without a usable ID, title, or job path")
                        continue
                    location = str(item.get("location") or "").strip()
                    if item.get("country_code") == "IND":
                        if location.startswith("IN, "):
                            location = location[4:].strip()
                        if not location:
                            location = "India"
                        elif "india" not in location.casefold():
                            location = f"{location}, India"
                    description = "\n\n".join(filter(None, [
                        plain_text(item.get("description")),
                        plain_text(item.get("basic_qualifications")),
                        plain_text(item.get("preferred_qualifications")),
                    ]))
                    jobs[external_id] = Job(
                        source=self.name,
                        external_id=external_id,
                        title=str(item["title"]),
                        company="Amazon",
                        location=location,
                        url=urljoin(SITE_URL, path),
                        description=description,
                        posted_date=item.get("posted_date"),
                    )
                offset += len(results)
                total = int(payload.get("hits") or 0)
                if not results or offset >= total:
                    break
                if page == max_pages - 1:
                    if self.config.get("allow_truncated", False):
                        logger.warning("%s: checked newest %d of %d results for %r; older results omitted",
                                       self.name, offset, total, query)
                        break
                    raise ValueError(
                        f"{self.name}: search for {query!r} has {total} results, but max_pages={max_pages} "
                        "would truncate them; increase max_pages"
                    )
        return list(jobs.values())
