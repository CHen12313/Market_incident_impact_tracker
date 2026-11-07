import asyncio
import json
import logging
import re
from datetime import datetime

import openai

from Data_Classes.enums import Direction, EventType, InfoTag, Relation
from Data_Classes.event import Company, EventInfo, ExtractedEvent
from Data_Classes.pipeline import PipelineContext
from Pipeline.config import OPENAI_API_KEY
from Pipeline.parameters.prompts import event_extractor_system_message, event_extractor_user_message
from Pipeline.pipeline_module import PipelineModule

logger = logging.getLogger(__name__)


class EventExtractor(PipelineModule):
    """
    Reads `ctx.articles` (NewsCollector's buckets), writes `ctx.events`: one
    `ExtractedEvent` per distinct incident the LLM found newsworthy.
    `companies[].ticker` is filled in later by TickerResolver. A bucket
    that yields no event, or an LLM response that fails validation, is
    dropped (with a `warning` status event) rather than raising — see
    DATA_CONTRACT.md.
    """

    label = "Extracting events"

    MODEL = "gpt-4o-mini"
    MAX_KNOCK_ON_COMPANIES = 4

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 max_knock_on_companies: int | None = None):
        self.api_key = api_key if api_key is not None else OPENAI_API_KEY
        self.model = model if model is not None else self.MODEL
        self.max_knock_on_companies = max_knock_on_companies if max_knock_on_companies is not None else self.MAX_KNOCK_ON_COMPANIES
        if not self.api_key:
            raise ValueError("Set OPENAI_API_KEY before scanning news.")
        self.client = openai.Client(api_key=self.api_key, timeout=30)

    def _build_messages(self, event_type: EventType, articles: list) -> list[dict]:
        article_block = "\n\n".join(
            f"Title: {a.title}\nDescription: {a.description}\nSource: {a.source}\n"
            f"Published: {a.published}\nURL: {a.url}"
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

    def _extract_one(self, event_type: EventType, articles: list) -> dict | None:
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

        if not isinstance(raw, dict) or not raw.get("event_found"):
            return None

        return raw

    def _slugify(self, text: str, max_words: int = 6) -> str:
        words = re.findall(r"[a-z0-9]+", text.lower())[:max_words]
        return "-".join(words) or "event"

    def _validate(self, event_type: EventType, raw: dict, allowed_urls: set[str]) -> tuple[ExtractedEvent | None, str | None]:
        """Returns (event, None) if valid, or (None, reason) if not."""
        headline = raw.get("headline")
        summary = raw.get("summary")
        event_date = raw.get("event_date")
        source_url = raw.get("source_url")
        companies_raw = raw.get("companies")

        if not headline or not isinstance(headline, str):
            return None, "missing headline"
        if not summary or not isinstance(summary, str):
            return None, "missing summary"

        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            return None, f"invalid event_date {event_date!r}"

        if not isinstance(source_url, str) or source_url not in allowed_urls:  # never trust a URL the model didn't copy verbatim
            return None, "source_url not among the provided articles"

        if not isinstance(companies_raw, list) or not companies_raw:
            return None, "no companies"

        cleaned_companies: list[Company] = []
        for c in companies_raw:
            if not isinstance(c, dict):
                continue
            company_name = c.get("company_name")
            reason = c.get("reason")
            if not all(isinstance(value, str) and value.strip() for value in (company_name, reason)):
                continue
            try:
                relation = Relation(c.get("relation"))
                expected_direction = Direction(c.get("expected_direction"))
            except ValueError:
                continue
            cleaned_companies.append(Company(
                company_name=company_name,
                relation=relation,
                expected_direction=expected_direction,
                reason=reason,
            ))

        direct = [c for c in cleaned_companies if c.relation == Relation.DIRECT]
        knock_on = [c for c in cleaned_companies if c.relation != Relation.DIRECT][:self.max_knock_on_companies]
        cleaned_companies = direct + knock_on

        if not cleaned_companies:
            return None, "no valid companies survived validation"

        event = ExtractedEvent(
            event=EventInfo(
                event_id=f"{event_date}-{self._slugify(headline)}",
                event_type=event_type,
                headline=headline,
                summary=summary,
                event_date=event_date,
                source_url=source_url,
            ),
            companies=cleaned_companies,
        )
        return event, None

    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        if ctx.articles is None:
            raise ValueError("EventExtractor: `articles` is missing")

        events: list[ExtractedEvent] = []
        for bucket in ctx.articles:
            if not bucket.articles:
                continue

            raw = await asyncio.to_thread(self._extract_one, bucket.event_type, bucket.articles)
            if raw is None:
                continue

            allowed_urls = {a.url for a in bucket.articles}
            event, reason = self._validate(bucket.event_type, raw, allowed_urls)
            if event is None:
                await self.emit_status(ctx, message=f"Dropped invalid '{bucket.event_type}' event: {reason}", tag=InfoTag.WARNING)
                continue

            events.append(event)
            await self.emit_status(ctx, message=f"Found event: {event.event.headline}", tag=InfoTag.SUB_STAGE_SUCCESS)

        ctx.events = events
        await self.emit_status(ctx, message=f"Found {len(events)} events", tag=InfoTag.STAGE_SUCCESS)

        return None, True
