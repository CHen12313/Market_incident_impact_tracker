"""Run the market-model event study for each resolved company."""
import asyncio

from Data_Classes.enums import InfoTag
from Data_Classes.event import EventInfo, Impact
from Data_Classes.pipeline import PipelineContext
from Pipeline.event_study import run_event_study
from Pipeline.pipeline_module import PipelineModule


class EventStudyRunner(PipelineModule):
    """
    Reads `context.events[].companies` (TickerResolver's output), runs the
    market-model event study for each resolved ticker, and writes
    `context.events[].impacts`. A company whose price history can't be
    fetched is dropped (with a `warning` status event) rather than failing
    the run — see DATA_CONTRACT.md.
    """

    label = "Measuring market impact"

    async def run(self, context: PipelineContext) -> tuple[str | None, bool]:
        for record in context.events:
            record.impacts, failures = await asyncio.to_thread(
                self.analyse_companies, record.event, record.companies, context.data_cache
            )
            for message in failures:
                await self.emit_status(context, message=message, tag=InfoTag.WARNING)
        return None, True

    @staticmethod
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
