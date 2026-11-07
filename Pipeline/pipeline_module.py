from abc import ABC, abstractmethod

from Data_Classes.enums import InfoTag
from Data_Classes.pipeline import InfoEvent, PipelineContext


class PipelineModule(ABC):
    """
    Base class for all pipeline modules.

    Every module is one stage in the pipeline, run in sequence over one
    shared `PipelineContext`. `ctx` is the only channel for domain data: a
    stage reads its inputs from its fields and writes its outputs back into
    them, in place. `run`'s return value is a separate control channel —
    see below.

    Modules that want to report progress call `self.emit_status(...)` from
    inside `run`; it's a no-op when nothing is listening.

    Sync I/O inside `run` (requests, yfinance, a sync OpenAI client, ...)
    must go through `await asyncio.to_thread(...)` so the pipeline never
    blocks the event loop.

    `label` is the human-readable caption `execute_pipeline` sends as
    `stage_label` alongside `progress` events (DATA_CONTRACT.md's Pipeline
    Status Event Protocol) — the frontend's progress-bar caption. Subclasses
    set it as a class attribute, e.g. `label = "Collecting news"`.
    """

    label: str | None = None

    @abstractmethod
    async def run(self, ctx: PipelineContext) -> tuple[str | None, bool]:
        """
        Run this stage: mutate `ctx` in place, then return a control tuple.

        Returns:
            (signal_name, satisfied): reserved for a future retry/backtrack
            controller — the current `execute_pipeline` doesn't act on
            either value, and ends a run early only via `ctx.exit_reason`.

        Raises:
            ValueError: a required input field is missing or invalid —
            failure is never encoded in the return tuple.

        See each subclass docstring for its data contract.
        """
        ...

    async def emit_status(self, ctx: PipelineContext, message: str, tag: InfoTag) -> None:
        if ctx.emit is None:
            return
        await ctx.emit(InfoEvent(message=message, tag=tag))
