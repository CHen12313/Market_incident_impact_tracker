import asyncio
import logging

from Pipeline.additional_info_collector import get_company_symbol
from Pipeline.config import DEMO_TICKER_OVERRIDES
from Pipeline.pipeline_module import PipelineModule

logger = logging.getLogger(__name__)


class TickerResolver(PipelineModule):
    """
    Mutates `data["events"]` in place: fills `ticker` on every company,
    checking `overrides` first, then falling back to `get_company_symbol()`.
    A company with no resolvable ticker is dropped; an event left with no
    companies at all is dropped too (EventStudyRunner/EventWriter have
    nothing to do with it, and EventWriter never writes a file with no
    impacts). See DATA_CONTRACT.md.
    """

    label = "Matching companies to tickers"

    OVERRIDES = DEMO_TICKER_OVERRIDES

    def __init__(self, overrides: dict[str, str] | None = None):
        self.overrides = overrides if overrides is not None else self.OVERRIDES

    def _resolve_one(self, company_name: str) -> str | None:
        override = self.overrides.get(company_name.strip().lower())
        if override:
            return override
        try:
            return get_company_symbol(company_name)
        except Exception:
            # a lookup failure (a flaky 422 from Finnhub, a network hiccup) is
            # operationally the same as "no ticker found" from here — drop the
            # company rather than letting one bad lookup fail the whole run
            logger.warning("get_company_symbol raised for %r", company_name, exc_info=True)
            return None

    async def run(self, data: dict) -> tuple[str | None, bool]:
        events = data.get("events")
        if events is None:
            raise ValueError("TickerResolver: `events` is missing")

        resolved_events = []
        for extracted in events:
            kept_companies = []
            for company in extracted["companies"]:
                ticker = await asyncio.to_thread(self._resolve_one, company["company_name"])
                if ticker is None:
                    await self.emit_status(data, message=f"No ticker found for '{company['company_name']}', skipped", tag="warning")
                    continue
                company["ticker"] = ticker
                kept_companies.append(company)

            if not kept_companies:
                await self.emit_status(data, message=f"Dropped event '{extracted['event']['headline']}': no company had a resolvable ticker", tag="warning")
                continue

            extracted["companies"] = kept_companies
            resolved_events.append(extracted)

        data["events"] = resolved_events

        total_companies = sum(len(e["companies"]) for e in resolved_events)
        await self.emit_status(
            data,
            message=f"Resolved tickers for {total_companies} companies across {len(resolved_events)} events",
            tag="stage_success",
        )

        return None, True
