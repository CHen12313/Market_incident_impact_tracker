from enum import StrEnum


class EventType(StrEnum):
    MERGER = "merger"
    BREACH = "breach"
    RECALL = "recall"
    OUTAGE = "outage"
    LAWSUIT = "lawsuit"
    REGULATION = "regulation"
    OTHER = "other"

    @classmethod
    def searchable(cls) -> list["EventType"]:
        """Every type except OTHER — what NewsCollector searches for by default."""
        return [t for t in cls if t is not cls.OTHER]


class Relation(StrEnum):
    DIRECT = "direct"
    COMPETITOR = "competitor"
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    OTHER = "other"


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    UNCLEAR = "unclear"


class EventStatus(StrEnum):
    COMPLETE = "complete"
    EARLY = "early"


class InfoTag(StrEnum):
    START = "start"
    INFO = "info"
    SUB_STAGE_SUCCESS = "sub_stage_success"
    STAGE_SUCCESS = "stage_success"
    SUB_STAGE_FAIL = "sub_stage_fail"
    WARNING = "warning"


class RunState(StrEnum):
    """Server-side (Ding's `runs[run_id]["state"]`) — listed here since it's
    part of the same shared vocabulary, even though the pipeline itself
    never constructs one."""
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
