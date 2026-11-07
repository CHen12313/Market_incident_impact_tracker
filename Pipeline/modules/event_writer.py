"""Persist each event and its impacts to the event cache."""
from Data_Classes.pipeline import PipelineContext
from Pipeline.event_files import write_event
from Pipeline.pipeline_module import PipelineModule


class EventWriter(PipelineModule):
    """
    Reads `context.events` (PredictionChecker's output), writes each event
    with usable impacts to `context.data_cache` via `write_event()`, and
    collects the written IDs into `context.event_ids` — see
    DATA_CONTRACT.md.
    """

    label = "Saving events"

    async def run(self, context: PipelineContext) -> tuple[str | None, bool]:
        for record in context.events:
            if record.impacts:
                write_event(context.data_cache, record.event, record.impacts)
                context.event_ids.append(record.event.event_id)
        if not context.event_ids:
            context.exit_reason = "No events with usable market data were found."
        return None, True
