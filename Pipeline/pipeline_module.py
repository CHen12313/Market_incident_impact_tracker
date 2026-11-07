from abc import ABC, abstractmethod


class PipelineModule(ABC):
    """
    Base class for all pipeline modules.

    Every module is one stage in the pipeline, run in sequence over one
    shared `data` dict. `data` is the only channel for domain data: a stage
    reads its inputs from it by key and writes its outputs back into it, in
    place. `run`'s return value is a separate control channel — see below.

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
    async def run(self, data: dict) -> tuple[str | None, bool]:
        """
        Run this stage: mutate `data` in place, then return a control tuple.

        Returns:
            (signal_name, satisfied): `signal_name` names the condition being
            reported on, or None if there's nothing to report. `satisfied` is
            False only when a named condition isn't met — the pipeline
            controller may then re-run a declared retry region.

        Raises:
            ValueError: a required input key is missing or invalid — failure
            is never encoded in the return tuple.

        See each subclass docstring for its data contract.
        """
        ...

    async def emit_status(self, data: dict, **fields) -> None:
        emit = data.get("emit", None)
        if emit is None:
            return
        await emit({"type": "info", **fields})
