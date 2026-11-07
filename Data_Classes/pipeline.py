from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Literal

from Data_Classes.enums import EventType, InfoTag
from Data_Classes.event import ArticleBucket, ExtractedEvent

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "Data_Cache"


@dataclass
class PipelineParams:
    """Mirrors the POST /api/pipeline/run body (DATA_CONTRACT.md). Not
    wired into run_pipeline's signature — Server/app.py calls it with a
    plain dict (and Server/app.py already validates event_types/days_back
    itself before that) — this exists for direct/typed callers that want
    it instead."""
    event_types: list[EventType] = field(default_factory=EventType.searchable)
    days_back: int = 3


@dataclass(kw_only=True)
class ProgressEvent:
    completed: int
    total: int
    stage: str | None = None
    stage_label: str | None = None
    type: Literal["progress"] = "progress"


@dataclass(kw_only=True)
class InfoEvent:
    message: str
    tag: InfoTag
    type: Literal["info"] = "info"


@dataclass(kw_only=True)
class PipelineResult:
    success: bool
    event_ids: list[str] = field(default_factory=list)
    exit_reason: str | None = None
    error_message: str | None = None
    type: Literal["result"] = "result"


@dataclass
class PipelineContext:
    """Replaces the shared `data` dict. One instance, threaded through every
    stage's `run()`, mutated in place — same role as before, now typed.

    `emit` receives `ProgressEvent`/`InfoEvent` instances; the caller that
    constructs a `PipelineContext` (see Pipeline/main.py's `run_pipeline`)
    is responsible for converting them to the plain-dict wire shape
    Server/app.py and DATA_CONTRACT.md's status-event protocol expect —
    that boundary conversion is not this class's job.
    """
    event_types: list[EventType]
    days_back: int
    emit: Callable[[ProgressEvent | InfoEvent], Awaitable[None]]
    data_cache: Path = DEFAULT_CACHE

    articles: list[ArticleBucket] | None = None          # NewsCollector
    events: list[ExtractedEvent] | None = None           # EventExtractor; mutated by TickerResolver/EventStudyRunner/PredictionChecker
    event_ids: list[str] = field(default_factory=list)   # EventWriter
    exit_reason: str | None = None                       # any stage may set this for a clean early stop
