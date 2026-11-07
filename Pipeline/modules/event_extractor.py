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
    Reads `context.articles` (NewsCollector's buckets), writes
    `context.events`: one `ExtractedEvent` per distinct incident the LLM
    found newsworthy. Each event includes direct companies and up to
    `max_knock_on_companies` indirect companies. TickerResolver fills in
    `companies[].ticker` later. A bucket that yields no event or fails
    validation is dropped with a warning status event. See DATA_CONTRACT.md.
    """

    label = "Extracting events"

    MODEL = "gpt-5.4-nano-2026-03-17"
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
            f"Title: {article.title}\nDescription: {article.description}\nSource: {article.source}\n"
            f"Published: {article.published}\nURL: {article.url}"
            for article in articles
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
            raw_response = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            logger.warning("EventExtractor: non-JSON response for '%s'", event_type)
            return None

        if not isinstance(raw_response, dict) or not raw_response.get("event_found"):
            return None

        return raw_response

    def _slugify(self, text: str, max_words: int = 6) -> str:
        words = re.findall(r"[a-z0-9]+", text.lower())[:max_words]
        return "-".join(words) or "event"

    def _validate(self, event_type: EventType, raw_response: dict, allowed_urls: set[str]) -> tuple[ExtractedEvent | None, str | None]:
        """Returns (event, None) if valid, or (None, reason) if not."""
        headline = raw_response.get("headline")
        summary = raw_response.get("summary")
        event_date = raw_response.get("event_date")
        source_url = raw_response.get("source_url")
        raw_companies = raw_response.get("companies")

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

        if not isinstance(raw_companies, list) or not raw_companies:
            return None, "no companies"

        cleaned_companies: list[Company] = []
        for raw_company in raw_companies:
            if not isinstance(raw_company, dict):
                continue
            company_name = raw_company.get("company_name")
            reason = raw_company.get("reason")
            if not all(isinstance(value, str) and value.strip() for value in (company_name, reason)):
                continue
            try:
                relation = Relation(raw_company.get("relation"))
                expected_direction = Direction(raw_company.get("expected_direction"))
            except ValueError:
                continue
            cleaned_companies.append(Company(
                company_name=company_name,
                relation=relation,
                expected_direction=expected_direction,
                reason=reason,
            ))

        direct_companies = [company for company in cleaned_companies if company.relation == Relation.DIRECT]
        knock_on_companies = [company for company in cleaned_companies if company.relation != Relation.DIRECT][:self.max_knock_on_companies]
        cleaned_companies = direct_companies + knock_on_companies

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

    async def run(self, context: PipelineContext) -> tuple[str | None, bool]:
        if context.articles is None:
            raise ValueError("EventExtractor: `articles` is missing")

        events: list[ExtractedEvent] = []
        for bucket in context.articles:
            if not bucket.articles:
                continue

            raw_response = await asyncio.to_thread(self._extract_one, bucket.event_type, bucket.articles)
            if raw_response is None:
                continue

            allowed_urls = {article.url for article in bucket.articles}
            event, reason = self._validate(bucket.event_type, raw_response, allowed_urls)
            if event is None:
                await self.emit_status(context, message=f"Dropped invalid '{bucket.event_type}' event: {reason}", tag=InfoTag.WARNING)
                continue

            events.append(event)
            await self.emit_status(context, message=f"Found event: {event.event.headline}", tag=InfoTag.SUB_STAGE_SUCCESS)

        context.events = events
        await self.emit_status(context, message=f"Found {len(events)} events", tag=InfoTag.STAGE_SUCCESS)

        return None, True
