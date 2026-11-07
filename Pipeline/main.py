import argparse
import asyncio
import dataclasses
import json
import logging
from pathlib import Path
import re
from typing import List

from Data_Classes.enums import EventType
from Data_Classes.event import EventInfo, Impact
from Data_Classes.pipeline import DEFAULT_CACHE, PipelineContext, ProgressEvent
from Pipeline.config import ALL_EVENT_TYPES, DEFAULT_DAYS_BACK
from Pipeline.pipeline_module import PipelineModule
from Pipeline.utils.event_files import event_lock, write_event

from Pipeline.modules.event_extractor import EventExtractor
from Pipeline.modules.event_study_runner import EventStudyRunner
from Pipeline.modules.event_writer import EventWriter
from Pipeline.modules.news_collector import NewsCollector
from Pipeline.modules.prediction_checker import PredictionChecker
from Pipeline.modules.ticker_resolver import TickerResolver

logger = logging.getLogger(__name__)


def _build_steps(parameters: dict) -> tuple[List[PipelineModule], dict, dict]:
    news = NewsCollector()
    if not news.api_keys:
        raise ValueError("Set NEWS_API_KEY before scanning news.")
    steps = [news, EventExtractor(), TickerResolver(), EventStudyRunner(), PredictionChecker(), EventWriter()]
    return steps, {}, {step.__class__.__name__: index for index, step in enumerate(steps)}


async def execute_pipeline(context: PipelineContext, pipeline_steps: List[PipelineModule], loop_instructions: dict[str, dict], step_index_map: dict) -> PipelineContext:
    """
    Run `pipeline_steps` in order, backtracking over a declared region when
    its `end` step reports `satisfied=False`. `loop_instructions` maps a
    signal name to {"start", "end", "max_attempts"}, naming the segment
    (by step class name, via `step_index_map`) to re-run.
    """
    async def _retry_pipeline_segment(instruction: dict, retry_segment: list[PipelineModule], context: PipelineContext) -> bool:
        """Re-run `retry_segment` up to `instruction['max_attempts']` times,
        stopping as soon as the last step reports satisfied. Returns whether
        it succeeded; the caller doesn't currently act on this."""
        attempts: int = instruction.get("max_attempts")
        while attempts > 0:
            logger.info("Attempts left: [%s]", attempts)
            for step in retry_segment:
                signal, satisfied = await step.run(context)
            if satisfied:  # we only check the signal of the last step, so this has to be out of the for loop
                return True
            attempts -= 1
        logger.warning("Retry attempts exhausted - module still not satisfied. Continuing...")
        return False

    await context.emit(ProgressEvent(completed=0, total=len(pipeline_steps), stage=None, stage_label=None))
    cursor = 0
    while cursor < len(pipeline_steps):
        current_step = pipeline_steps[cursor]
        signal_name, satisfied = await current_step.run(context)
        await context.emit(ProgressEvent(
            completed=cursor + 1,
            total=len(pipeline_steps),
            stage=current_step.__class__.__name__,
            stage_label=current_step.label,
        ))

        if signal_name == "end_pipeline":
            logger.info("Pipeline exited early. Reason: %s", context.exit_reason)
            return context  # early stop is only used when nothing is broken; if something broke, the
            # module should have raised instead, so getting here is still a success
        elif signal_name in loop_instructions and not satisfied:
            instruction = loop_instructions[signal_name]  # we checked it exists above, so raw access is fine
            start_index = step_index_map[instruction["start"]]
            end_index = step_index_map[instruction["end"]]
            retry_segment = pipeline_steps[start_index:end_index + 1]
            logger.warning("Retry triggered. Re-running segment [%s] - [%s]", instruction["start"], instruction["end"])
            await _retry_pipeline_segment(instruction=instruction, retry_segment=retry_segment, context=context)
            logger.info("Finished re-running segment [%s] - [%s]", instruction["start"], instruction["end"])
        cursor += 1

    return context


async def run_pipeline(parameters: dict) -> tuple[bool, dict]:
    """
    Run the scan and return the terminal result described by the data
    contract. `parameters` and the return value are plain dicts — that's
    the wire shape Server/app.py and DATA_CONTRACT.md's status-event
    protocol expect; `PipelineContext` and the typed status events are
    internal to this module and never cross that boundary.
    """
    raw_emit = parameters["emit"]

    async def emit(event) -> None:
        await raw_emit(dataclasses.asdict(event))

    try:
        event_types = [EventType(t) for t in (parameters.get("event_types") or ALL_EVENT_TYPES)]
    except ValueError as error:
        logger.warning("Pipeline could not complete: %s", error)
        return False, {"error_message": str(error)}

    context = PipelineContext(
        event_types=event_types,
        days_back=parameters.get("days_back") or DEFAULT_DAYS_BACK,
        data_cache=Path(parameters.get("data_cache", DEFAULT_CACHE)),
        emit=emit,
    )
    try:
        steps, loops, indexes = _build_steps(parameters)
        context = await execute_pipeline(context, steps, loops, indexes)
        return True, {"event_ids": list(dict.fromkeys(context.event_ids)), "exit_reason": context.exit_reason}
    except ValueError as error:
        logger.warning("Pipeline could not complete: %s", error)
        return False, {"error_message": str(error)}
    except Exception:
        logger.exception("Pipeline failed")
        return False, {"error_message": "Pipeline failed while contacting a provider or processing data."}


def refresh_event(event_id, *, data_cache=DEFAULT_CACHE):
    """Recalculate the cached event and keep prior studies for unavailable tickers."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", event_id):
        raise ValueError("Invalid event ID")
    path = Path(data_cache) / "events" / f"{event_id}.json"
    with event_lock:
        document = json.loads(path.read_text(encoding="utf-8"))
        event = EventInfo.from_dict(document["event"])
        previous_impacts = [Impact.from_dict(i) for i in document["impacts"]]
        impacts, failures = EventStudyRunner.analyse_companies(event, previous_impacts, data_cache, keep_previous=True)
        if len(failures) == len(impacts):
            raise ValueError("No updated market data was available for this event.")
        PredictionChecker.check_predictions(impacts)
        return write_event(data_cache, event, impacts)


async def stream_pipeline(parameters: dict):
    """
    Runs `run_pipeline` in the background and yields its status events as
    they arrive, ending with one {"type": "result", ...} event carrying the
    same (success, payload) pair `run_pipeline` returns.
    """
    status_queue = asyncio.Queue()
    _SENTINEL = object()

    async def emit(event):
        await status_queue.put(event)
    parameters = dict(parameters, emit=emit)

    async def _run():
        try:
            return await run_pipeline(parameters)
        finally:
            await status_queue.put(_SENTINEL)

    task = asyncio.create_task(_run())
    try:
        while True:
            event = await status_queue.get()
            if event is _SENTINEL:
                break
            yield event

        success, payload = await task
        yield {"type": "result", "success": success, **payload}
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def regenerate_demo_events(*, data_cache=DEFAULT_CACHE) -> None:
    """
    Re-run the event study for every event already in `data_cache/events`,
    straight from the price cache — no NewsCollector/EventExtractor/
    TickerResolver, so this needs no API keys and doesn't depend on live
    yfinance. Used by `--demo` to refresh the demo files before a run.
    """
    events_directory = Path(data_cache) / "events"
    event_ids = sorted(path.stem for path in events_directory.glob("*.json"))
    if not event_ids:
        print(f"No cached event files found in {events_directory}")
        return

    for event_id in event_ids:
        try:
            refresh_event(event_id, data_cache=data_cache)
            print(f"Regenerated {event_id}")
        except Exception as error:
            print(f"Skipped {event_id}: {error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline CLI")
    parser.add_argument("--demo", action="store_true",
                         help="Regenerate every cached event file's study from Data_Cache/prices, offline")
    arguments = parser.parse_args()

    if arguments.demo:
        regenerate_demo_events()
    else:
        parser.print_help()
