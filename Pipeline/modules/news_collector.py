import asyncio
import logging
from datetime import datetime, timedelta, timezone

import requests

from Data_Classes.enums import EventType, InfoTag
from Data_Classes.event import Article, ArticleBucket
from Data_Classes.pipeline import PipelineContext
from Pipeline.config import (
    INCIDENT_TERMS,
    NEWS_API_KEY,
    NEWS_API_BACKUP,
    NEWS_API_BACKUP2,
    NEWS_API_BACKUP3,
    NEWS_API_BACKUP4,
    NEWS_API_BACKUP5,
    NEWS_API_BACKUP6,
)
from Pipeline.pipeline_module import PipelineModule

logger = logging.getLogger(__name__)


class NewsCollector(PipelineModule):
    """
    Reads `ctx.event_types` and `ctx.days_back`, writes `ctx.articles`: one
    `ArticleBucket` per requested event_type. See DATA_CONTRACT.md.
    """

    label = "Collecting news"

    API_KEYS = [NEWS_API_KEY, NEWS_API_BACKUP, NEWS_API_BACKUP2, NEWS_API_BACKUP3, NEWS_API_BACKUP4, NEWS_API_BACKUP5, NEWS_API_BACKUP6]
    MAX_PAGES = 2
    PAGE_SIZE = 10
    MAX_HITS_PER_TYPE = 40
    INCIDENT_TERMS = INCIDENT_TERMS

    def __init__(self, api_keys: list[str] | None = None, max_pages: int | None = None,
                 page_size: int | None = None, max_hits_per_type: int | None = None,
                 incident_terms: dict | None = None):
        self.api_keys = list(dict.fromkeys(key for key in (api_keys if api_keys is not None else self.API_KEYS) if key))
        self.max_pages = max_pages if max_pages is not None else self.MAX_PAGES
        self.page_size = page_size if page_size is not None else self.PAGE_SIZE
        self.max_hits_per_type = max_hits_per_type if max_hits_per_type is not None else self.MAX_HITS_PER_TYPE
        self.incident_terms = incident_terms if incident_terms is not None else self.INCIDENT_TERMS

    def _terms_for(self, event_type: EventType) -> str:
        """Return a NewsAPI-ready OR string, e.g. "(recall OR defect OR ...)"."""
        raw_terms = self.incident_terms.get(event_type.lower(), self.incident_terms["_default"])
        or_block = " OR ".join({t.lower() for t in raw_terms})
        return f"({or_block})"

    def _fetch(self, query: str, start_cutoff, use_title_filter: bool) -> list[dict]:
        hits: list[dict] = []
        succeeded = False
        for current_key in self.api_keys:  # main key first, then fallback
            headers = {"x-api-key": current_key}
            for page in range(1, self.max_pages + 1):
                params = {
                    "from": start_cutoff.isoformat(),
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": self.page_size,
                    "page": page,
                }
                params["qInTitle" if use_title_filter else "q"] = query

                r = requests.get("https://newsapi.org/v2/everything", params=params, headers=headers, timeout=15)

                if r.status_code == 429:
                    logger.warning("[NewsAPI 429] Rate limit hit")
                    break  # try next API key

                if r.status_code != 200:
                    logger.warning("[NewsAPI %s] %s", r.status_code, r.json().get("message"))
                    break

                succeeded = True
                for a in r.json().get("articles", []):
                    pub_date = a.get("publishedAt", "")[:10]
                    try:
                        pub_date = datetime.strptime(pub_date, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if pub_date < start_cutoff:
                        continue

                    hits.append({
                        "title": a.get("title", ""),
                        "description": a.get("description", "") or "",
                        "source": a.get("source", {}).get("name", "N/A"),
                        "published": pub_date.isoformat(),
                        "url": a.get("url", ""),
                    })

                if len(hits) >= self.max_hits_per_type:
                    break  # avoid unnecessary pages
            if hits:
                break  # stop retrying once successful
        if not succeeded:
            raise ValueError("NewsAPI rejected the request. Check the API key and quota.")
        return hits

    def _collect(self, event_types: list[EventType], days_back: int) -> list[ArticleBucket]:
        """
        Return one ArticleBucket per entry in `event_types`. First try
        qInTitle; if empty, fall back to q= (full-text).
        """
        start_cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).date()

        buckets = []
        for event_type in event_types:
            query = self._terms_for(event_type)
            raw = self._fetch(query, start_cutoff, use_title_filter=True) or self._fetch(query, start_cutoff, use_title_filter=False)
            articles = [Article(**a) for a in raw]
            logger.info("Collected %d article(s) for '%s'.", len(articles), event_type)
            buckets.append(ArticleBucket(event_type=event_type, articles=articles))

        return buckets

    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        if not ctx.event_types:
            raise ValueError("NewsCollector: `event_types` is missing or empty")
        if ctx.days_back is None:
            raise ValueError("NewsCollector: `days_back` is missing")

        await self.emit_status(ctx, message=f"Searching news for {', '.join(ctx.event_types)}...", tag=InfoTag.START)

        buckets = await asyncio.to_thread(self._collect, ctx.event_types, ctx.days_back)

        for bucket in buckets:
            if not bucket.articles:
                await self.emit_status(ctx, message=f"No articles found for '{bucket.event_type}'", tag=InfoTag.WARNING)

        ctx.articles = buckets

        total = sum(len(bucket.articles) for bucket in buckets)
        await self.emit_status(ctx, message=f"Found {total} articles", tag=InfoTag.STAGE_SUCCESS)

        return None, True
