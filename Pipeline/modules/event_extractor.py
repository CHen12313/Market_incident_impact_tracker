import asyncio
import json
import logging
import re
from datetime import datetime

import openai

from Pipeline.config import OPENAI_API_KEY
from Pipeline.parameters.prompts import event_extractor_system_message, event_extractor_user_message
from Pipeline.pipeline_module import PipelineModule

logger = logging.getLogger(__name__)


class EventExtractor(PipelineModule):
    """
    Reads `data["articles"]` (NewsCollector's buckets), writes `data["events"]`:
    one entry per distinct incident the LLM found newsworthy, each

        {
            "event": {event_id, event_type, headline, summary, event_date, source_url},
            "companies": [{company_name, relation, expected_direction, reason}, ...],
        }

    `companies` is the direct company (if any) plus up to `max_knock_on_companies`
    knock-on companies; `ticker` is filled in later by TickerResolver. A bucket
    that yields no event, or an LLM response that fails validation, is dropped
    (with a `warning` status event) rather than raising — see DATA_CONTRACT.md.
    """

    label = "Extracting events"

    MODEL = "gpt-4o-mini"
    MAX_KNOCK_ON_COMPANIES = 4
    VALID_RELATIONS = {"direct", "competitor", "supplier", "customer", "other"}
    VALID_DIRECTIONS = {"up", "down", "unclear"}

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 max_knock_on_companies: int | None = None):
        self.api_key = api_key if api_key is not None else OPENAI_API_KEY
        self.model = model if model is not None else self.MODEL
        self.max_knock_on_companies = max_knock_on_companies if max_knock_on_companies is not None else self.MAX_KNOCK_ON_COMPANIES
        self.client = openai.Client(api_key=self.api_key)

    def _build_messages(self, event_type: str, articles: list[dict]) -> list[dict]:
        article_block = "\n\n".join(
            f"Title: {a['title']}\nDescription: {a['description']}\nSource: {a['source']}\n"
            f"Published: {a['published']}\nURL: {a['url']}"
            for a in articles
        )
        user_message = event_extractor_user_message.format(
            event_type=event_type,
            max_knock_on_companies=self.max_knock_on_companies,
            article_block=article_block,
        )
        return [
            {"role": "system", "content": event_extractor_system_message},
            {"role": "user", "content": user_message},
        ]

    def _extract_one(self, event_type: str, articles: list[dict]) -> dict | None:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(event_type, articles),
            response_format={"type": "json_object"},
            temperature=0.2,
        ).choices[0].message.content

        try:
            raw = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            logger.warning("EventExtractor: non-JSON response for '%s'", event_type)
            return None

        if not raw.get("event_found"):
            return None

        return raw

    def _slugify(self, text: str, max_words: int = 6) -> str:
        words = re.findall(r"[a-z0-9]+", text.lower())[:max_words]
        return "-".join(words) or "event"

    def _validate(self, event_type: str, raw: dict, allowed_urls: set[str]) -> tuple[dict | None, str | None]:
        """Returns (event, None) if valid, or (None, reason) if not."""
        headline = raw.get("headline")
        summary = raw.get("summary")
        event_date = raw.get("event_date")
        source_url = raw.get("source_url")
        companies = raw.get("companies")

        if not headline or not isinstance(headline, str):
            return None, "missing headline"
        if not summary or not isinstance(summary, str):
            return None, "missing summary"

        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            return None, f"invalid event_date {event_date!r}"

        if source_url not in allowed_urls:  # never trust a URL the model didn't copy verbatim
            return None, "source_url not among the provided articles"

        if not isinstance(companies, list) or not companies:
            return None, "no companies"

        cleaned_companies = []
        for c in companies:
            if not isinstance(c, dict):
                continue
            company_name = c.get("company_name")
            relation = c.get("relation")
            expected_direction = c.get("expected_direction")
            reason = c.get("reason")
            if not company_name or relation not in self.VALID_RELATIONS or expected_direction not in self.VALID_DIRECTIONS or not reason:
                continue
            cleaned_companies.append({
                "company_name": company_name,
                "relation": relation,
                "expected_direction": expected_direction,
                "reason": reason,
            })

        direct = [c for c in cleaned_companies if c["relation"] == "direct"]
        knock_on = [c for c in cleaned_companies if c["relation"] != "direct"][:self.max_knock_on_companies]
        cleaned_companies = direct + knock_on

        if not cleaned_companies:
            return None, "no valid companies survived validation"

        event = {
            "event": {
                "event_id": f"{event_date}-{self._slugify(headline)}",
                "event_type": event_type,
                "headline": headline,
                "summary": summary,
                "event_date": event_date,
                "source_url": source_url,
            },
            "companies": cleaned_companies,
        }
        return event, None

    async def run(self, data: dict) -> tuple[str | None, bool]:
        buckets = data.get("articles")
        if buckets is None:
            raise ValueError("EventExtractor: `articles` is missing")

        events = []
        for bucket in buckets:
            event_type, articles = bucket["event_type"], bucket["articles"]
            if not articles:
                continue

            raw = await asyncio.to_thread(self._extract_one, event_type, articles)
            if raw is None:
                continue

            allowed_urls = {a["url"] for a in articles}
            event, reason = self._validate(event_type, raw, allowed_urls)
            if event is None:
                await self.emit_status(data, message=f"Dropped invalid '{event_type}' event: {reason}", tag="warning")
                continue

            events.append(event)
            await self.emit_status(data, message=f"Found event: {event['event']['headline']}", tag="sub_stage_success")

        data["events"] = events
        await self.emit_status(data, message=f"Found {len(events)} events", tag="stage_success")

        return None, True
