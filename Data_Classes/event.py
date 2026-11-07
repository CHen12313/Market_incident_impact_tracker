from dataclasses import dataclass

from Data_Classes.enums import Direction, EventStatus, EventType, Relation


@dataclass
class Article:
    title: str
    description: str
    source: str
    published: str  # YYYY-MM-DD
    url: str


@dataclass
class ArticleBucket:
    """NewsCollector's output: one bucket per event_type searched."""
    event_type: EventType
    articles: list[Article]


@dataclass
class Company:
    company_name: str
    relation: Relation
    expected_direction: Direction
    reason: str
    ticker: str | None = None  # filled in by TickerResolver; None until then


@dataclass
class DailyRow:
    day: int
    date: str
    actual_pct: float
    expected_pct: float
    abnormal_pct: float
    cum_actual_pct: float
    cum_expected_pct: float
    car_pct: float | None

    @classmethod
    def from_dict(cls, raw: dict) -> "DailyRow":
        return cls(**raw)


@dataclass
class Study:
    market_ticker: str
    event_day: str
    days_after: int
    beta: float
    raw_return_pct: float
    market_return_pct: float
    expected_return_pct: float
    car_pct: float
    t_stat: float
    is_significant: bool
    daily: list[DailyRow]
    verdict_text: str = ""  # filled in by PredictionChecker; absent from run_event_study()'s result

    @classmethod
    def from_dict(cls, raw: dict) -> "Study":
        return cls(**{**raw, "daily": [DailyRow.from_dict(d) for d in raw["daily"]]})


@dataclass
class Impact:
    company_name: str
    ticker: str
    relation: Relation
    expected_direction: Direction
    reason: str
    study: Study
    prediction_match: bool | None = None  # filled in by PredictionChecker; absent before that

    @classmethod
    def from_dict(cls, raw: dict) -> "Impact":
        return cls(
            company_name=raw["company_name"],
            ticker=raw["ticker"],
            relation=Relation(raw["relation"]),
            expected_direction=Direction(raw["expected_direction"]),
            reason=raw["reason"],
            study=Study.from_dict(raw["study"]),
            prediction_match=raw.get("prediction_match"),
        )


@dataclass
class EventInfo:
    event_id: str
    event_type: EventType
    headline: str
    summary: str
    event_date: str  # YYYY-MM-DD
    source_url: str

    @classmethod
    def from_dict(cls, raw: dict) -> "EventInfo":
        return cls(**{**raw, "event_type": EventType(raw["event_type"])})


@dataclass
class ExtractedEvent:
    """One entry in the pipeline's `events` list. Starts as EventExtractor's
    output ({event, companies}); TickerResolver mutates `companies` in
    place (fills `ticker`, drops ticker-less companies); EventStudyRunner
    then fills `impacts` (companies is no longer read after that point)."""
    event: EventInfo
    companies: list[Company]
    impacts: list[Impact] | None = None


@dataclass
class EventFile:
    """Serializes 1:1 to Data_Cache/events/{event_id}.json — see
    DATA_CONTRACT.md's Event File Contract. Field names and values must
    match that document exactly; it is the authority, this mirrors it."""
    event: EventInfo
    status: EventStatus
    generated_at: str  # ISO-8601 UTC
    impacts: list[Impact]

    @classmethod
    def from_dict(cls, raw: dict) -> "EventFile":
        return cls(
            event=EventInfo.from_dict(raw["event"]),
            status=EventStatus(raw["status"]),
            generated_at=raw["generated_at"],
            impacts=[Impact.from_dict(i) for i in raw["impacts"]],
        )

    def check_invariants(self) -> None:
        """The six invariants DATA_CONTRACT.md lists under "Invariants".
        Diagnostic only — not currently called from the write path (see
        write_event in Pipeline/utils/event_files.py), since cross-exchange
        holiday calendars can legitimately give two companies of the same
        event slightly different realized days_after; raises AssertionError
        naming the first invariant that fails."""
        assert self.impacts, "EventFile.impacts must not be empty"

        days_after_values = {impact.study.days_after for impact in self.impacts}
        assert len(days_after_values) == 1, "every impact must share the same study.days_after"
        days_after = days_after_values.pop()

        expected_status = EventStatus.EARLY if days_after < 5 else EventStatus.COMPLETE
        assert self.status == expected_status, (
            f"status must be {expected_status!r} when days_after={days_after}"
        )

        for impact in self.impacts:
            daily = impact.study.daily
            assert daily[0].day == -10 and daily[-1].day == days_after, (
                f"{impact.ticker}: daily[] must span day -10..{days_after}"
            )

            day_minus_1 = next(d for d in daily if d.day == -1)
            assert day_minus_1.cum_actual_pct == 0 and day_minus_1.cum_expected_pct == 0, (
                f"{impact.ticker}: day -1 must be rebased to 0"
            )

            assert daily[-1].car_pct == impact.study.car_pct, (
                f"{impact.ticker}: daily[-1].car_pct must equal study.car_pct"
            )
            assert abs(impact.study.car_pct - (impact.study.raw_return_pct - impact.study.expected_return_pct)) <= 0.05, (
                f"{impact.ticker}: car_pct must ≈ raw_return_pct - expected_return_pct"
            )

            for d in daily:
                if d.car_pct is not None:
                    assert abs(d.abnormal_pct - (d.actual_pct - d.expected_pct)) <= 0.02, (
                        f"{impact.ticker} day {d.day}: abnormal_pct must ≈ actual_pct - expected_pct"
                    )

            event_day_row = next(d for d in daily if d.day == 0)
            assert event_day_row.date == impact.study.event_day, (
                f"{impact.ticker}: study.event_day must equal the day-0 row's date"
            )
