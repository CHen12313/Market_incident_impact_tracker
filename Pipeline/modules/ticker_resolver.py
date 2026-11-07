"""Resolve each extracted company's name to a stock ticker."""
import asyncio
import re

import requests

from Data_Classes.enums import InfoTag
from Data_Classes.pipeline import PipelineContext
from Pipeline.pipeline_module import PipelineModule


class TickerResolver(PipelineModule):
    """
    Reads `context.events[].companies` (EventExtractor's output), fills in
    each `Company.ticker` via a Finnhub symbol lookup, and drops companies
    whose name doesn't resolve to a valid ticker (with a `warning` status
    event) rather than failing the run — see DATA_CONTRACT.md.
    """

    label = "Resolving tickers"

    async def run(self, context: PipelineContext) -> tuple[str | None, bool]:
        from Pipeline.utils.additional_info_collector import get_company_symbol

        for record in context.events:
            companies = {}
            for company in record.companies:
                ticker = await self.resolve_ticker(company.company_name, get_company_symbol)
                if ticker is None:
                    await self.emit_status(context, message=f"No ticker for {company.company_name}", tag=InfoTag.WARNING)
                    continue
                company.ticker = ticker
                companies.setdefault(ticker, company)
            record.companies = list(companies.values())
        return None, True

    @staticmethod
    async def resolve_ticker(company_name: str, lookup) -> str | None:
        try:
            ticker = await asyncio.to_thread(lookup, company_name)
        except requests.RequestException:
            return None
        ticker = ticker.strip().upper() if isinstance(ticker, str) else ""
        return ticker if re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,31}", ticker) else None
