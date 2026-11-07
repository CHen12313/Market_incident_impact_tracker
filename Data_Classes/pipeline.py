from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

from Data_Classes.enums import EventType, InfoTag
from Data_Classes.event import ArticleBucket, ExtractedEvent, Impact


@dataclass
class PipelineParams:
    """Constructed from the POST /api/pipeline/run body, which is unchanged;
    an invalid event_type in that body now fails here as a ValueError (via
    EventType(raw)) instead of silently passing through."""
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
    stage's `run()`, mutated in place — same role as before, now typed."""
    event_types: list[EventType]
    days_back: int
    emit: Callable[[ProgressEvent | InfoEvent], Awaitable[None]]

    articles: list[ArticleBucket] | None = None          # NewsCollector
    events: list[ExtractedEvent] | None = None           # EventExtractor; mutated by TickerResolver
    impacts: list[Impact] | None = None                  # EventStudyRunner; mutated by PredictionChecker
    event_ids: list[str] = field(default_factory=list)   # EventWriter
    exit_reason: str | None = None                       # any stage may set this for a clean early stop
