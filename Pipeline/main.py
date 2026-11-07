import asyncio
import json
import logging
from pathlib import Path
import re
from typing import List

from Pipeline.config import ALL_EVENT_TYPES, DEFAULT_DAYS_BACK
from Pipeline.pipeline_module import PipelineModule

logger = logging.getLogger(__name__)
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "Data_Cache"


def _build_steps(params: dict) -> tuple[List[PipelineModule], dict, dict]:
    from Pipeline.modules.analysis import EventStudyRunner, EventWriter, PredictionChecker, TickerResolver
    from Pipeline.modules.event_extractor import EventExtractor
    from Pipeline.modules.news_collector import NewsCollector

    news = NewsCollector()
    if not news.api_keys:
        raise ValueError("Set NEWS_API_KEY before scanning news.")
    steps = [news, EventExtractor(), TickerResolver(), EventStudyRunner(), PredictionChecker(), EventWriter()]
    return steps, {}, {step.__class__.__name__: index for index, step in enumerate(steps)}


async def execute_pipeline(data: dict, pipeline_steps: List[PipelineModule], loop_instructions: dict[str, dict], step_index_map: dict) -> tuple[bool, dict]:
    """
    Run `pipeline_steps` in order, backtracking over a declared region when
    its `end` step reports `satisfied=False`. `loop_instructions` maps a
    signal name to {"start", "end", "max_attempts"}, naming the segment
    (by step class name, via `step_index_map`) to re-run.
    """
    async def _retry_pipeline_segment(instruction: dict, retry_segment: list[PipelineModule], data: dict) -> bool:
        """Re-run `retry_segment` up to `instruction['max_attempts']` times,
        stopping as soon as the last step reports satisfied. Returns whether
        it succeeded; the caller doesn't currently act on this."""
        attempts: int = instruction.get("max_attempts")
        while attempts > 0:
            logger.info("Attempts left: [%s]", attempts)
            for step in retry_segment:
                signal, satisfied = await step.run(data)
            if satisfied:  # we only check the signal of the last step, so this has to be out of the for loop
                return True
            attempts -= 1
        logger.warning("Retry attempts exhausted - module still not satisfied. Continuing...")
        return False

    await data["emit"]({"type": "progress", "completed": 0, "total": len(pipeline_steps), "stage": None, "stage_label": None})
    cursor = 0
    while cursor < len(pipeline_steps):
        current_step = pipeline_steps[cursor]
        signal_name, satisfied = await current_step.run(data)
        await data["emit"]({
            "type": "progress",
            "completed": cursor + 1,
            "total": len(pipeline_steps),
            "stage": current_step.__class__.__name__,
            "stage_label": current_step.label,
        })

        if signal_name == "end_pipeline":
            logger.info("Pipeline exited early. Reason: %s", data.get("exit_reason"))
            return True, data  # early stop is only used when nothing is broken; if something broke, the
            # module should have raised instead, so getting here is still a success
        elif signal_name in loop_instructions and not satisfied:
            instruction = loop_instructions[signal_name]  # we checked it exists above, so raw access is fine
            start_index = step_index_map[instruction["start"]]
            end_index = step_index_map[instruction["end"]]
            retry_segment = pipeline_steps[start_index:end_index + 1]
            logger.warning("Retry triggered. Re-running segment [%s] - [%s]", instruction["start"], instruction["end"])
            await _retry_pipeline_segment(instruction=instruction, retry_segment=retry_segment, data=data)
            logger.info("Finished re-running segment [%s] - [%s]", instruction["start"], instruction["end"])
        cursor += 1

    return True, data


async def run_pipeline(params: dict) -> tuple[bool, dict]:
    """Run the scan and return the terminal result described by the data contract."""
    data = {
        "event_types": params.get("event_types") or ALL_EVENT_TYPES,
        "days_back": params.get("days_back") or DEFAULT_DAYS_BACK,
        "data_cache": Path(params.get("data_cache", DEFAULT_CACHE)),
        "event_ids": [],
        "emit": params["emit"],
    }
    try:
        steps, loops, indexes = _build_steps(params)
        success, data = await execute_pipeline(data, steps, loops, indexes)
        return success, {"event_ids": list(dict.fromkeys(data["event_ids"])), "exit_reason": data.get("exit_reason")}
    except ValueError as error:
        logger.warning("Pipeline could not complete: %s", error)
        return False, {"error_message": str(error)}
    except Exception:
        logger.exception("Pipeline failed")
        return False, {"error_message": "Pipeline failed while contacting a provider or processing data."}


def refresh_event(event_id, *, data_cache=DEFAULT_CACHE):
    """Recalculate the cached event and keep prior studies for unavailable tickers."""
    from Pipeline.event_files import event_lock, write_event
    from Pipeline.modules.analysis import analyse_companies, check_predictions

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", event_id):
        raise ValueError("Invalid event ID")
    path = Path(data_cache) / "events" / f"{event_id}.json"
    with event_lock:
        document = json.loads(path.read_text(encoding="utf-8"))
        impacts, failures = analyse_companies(document["event"], document["impacts"], data_cache, keep_previous=True)
        if len(failures) == len(impacts):
            raise ValueError("No updated market data was available for this event.")
        check_predictions(impacts)
        return write_event(data_cache, document["event"], impacts)


async def stream_pipeline(params: dict):
    """
    Runs `run_pipeline` in the background and yields its status events as
    they arrive, ending with one {"type": "result", ...} event carrying the
    same (success, payload) pair `run_pipeline` returns.
    """
    status_queue = asyncio.Queue()
    _SENTINEL = object()

    async def emit(event):
        await status_queue.put(event)
    params = dict(params, emit=emit)

    async def _run():
        try:
            return await run_pipeline(params)
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
