"""Resolve companies, calculate studies and publish the event documents."""
import asyncio
import re

import requests

from Data_Classes.enums import Direction, InfoTag, Relation
from Data_Classes.event import EventInfo, Impact
from Data_Classes.pipeline import PipelineContext
from Pipeline.event_files import write_event
from Pipeline.event_study import run_event_study
from Pipeline.pipeline_module import PipelineModule


class TickerResolver(PipelineModule):
    label = "Resolving tickers"

    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        from Pipeline.additional_info_collector import get_company_symbol

        for record in ctx.events:
            companies = {}
            for company in record.companies:
                try:
                    ticker = await asyncio.to_thread(get_company_symbol, company.company_name)
                except requests.RequestException:
                    ticker = None
                ticker = ticker.strip().upper() if isinstance(ticker, str) else ""
                if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,31}", ticker):
                    await self.emit_status(ctx, message=f"No ticker for {company.company_name}", tag=InfoTag.WARNING)
                    continue
                company.ticker = ticker
                companies.setdefault(ticker, company)
            record.companies = list(companies.values())
        return None, True


def analyse_companies(event: EventInfo, companies, cache, *, keep_previous=False) -> tuple[list[Impact], list[str]]:
    """
    `companies` is a list of `Company` (first run, no study yet) or
    `Impact` (a refresh, already studied once) — either way each has
    `company_name`, `ticker`, `relation`, `expected_direction`, `reason`.
    """
    impacts: list[Impact] = []
    failures: list[str] = []
    for company in companies:
        ticker = company.ticker
        market_ticker = company.study.market_ticker if isinstance(company, Impact) else None
        try:
            study = run_event_study(ticker, event.event_date, market_ticker=market_ticker, cache=cache)
        except (ValueError, RuntimeError, OSError) as error:
            failures.append(f"{ticker}: {error}")
            if keep_previous and isinstance(company, Impact):
                impacts.append(company)
            continue
        impacts.append(Impact(
            company_name=company.company_name, ticker=ticker, relation=company.relation,
            expected_direction=company.expected_direction, reason=company.reason, study=study,
        ))
    return impacts, failures


def check_predictions(impacts: list[Impact]) -> None:
    for impact in impacts:
        study = impact.study
        direction = impact.expected_direction
        car, t_stat = study.car_pct, study.t_stat
        impact.prediction_match = None
        if study.is_significant:
            moved = "Rose" if car > 0 else "Fell"
            if direction != Direction.UNCLEAR:
                impact.prediction_match = (car > 0) == (direction == Direction.UP)
            study.verdict_text = (
                f"{moved} {abs(car):.2f}% relative to the market-based expectation "
                f"over {study.days_after + 1} trading days (t = {t_stat:.2f})."
            )
        else:
            study.verdict_text = f"Moved roughly in line with the market (t = {t_stat:.2f})."


class EventStudyRunner(PipelineModule):
    label = "Measuring market impact"

    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        for record in ctx.events:
            record.impacts, failures = await asyncio.to_thread(
                analyse_companies, record.event, record.companies, ctx.data_cache
            )
            for message in failures:
                await self.emit_status(ctx, message=message, tag=InfoTag.WARNING)
        return None, True


class PredictionChecker(PipelineModule):
    label = "Checking predictions"

    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        for record in ctx.events:
            check_predictions(record.impacts)
        return None, True


class EventWriter(PipelineModule):
    label = "Saving events"

    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        for record in ctx.events:
            if record.impacts:
                write_event(ctx.data_cache, record.event, record.impacts)
                ctx.event_ids.append(record.event.event_id)
        if not ctx.event_ids:
            ctx.exit_reason = "No events with usable market data were found."
        return None, True
