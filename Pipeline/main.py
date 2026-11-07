import asyncio
import logging
from typing import List

from Pipeline.config import ALL_EVENT_TYPES, DEFAULT_DAYS_BACK
from Pipeline.pipeline_module import PipelineModule

logger = logging.getLogger(__name__)


def _build_steps(params: dict) -> tuple[List[PipelineModule], dict, dict]:
    """
    Build the ordered module list for one run, plus the backtrack
    instructions `execute_pipeline` needs and a {class name: index} map for
    resolving them.

    Not implemented yet — the modules it will wire in (NewsCollector,
    EventExtractor, TickerResolver, EventStudyRunner, PredictionChecker,
    EventWriter) don't exist yet. See todo_chen.md section 2.
    """
    raise NotImplementedError("Pipeline modules aren't built yet (todo_chen.md section 2)")


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
    """
    Run one event-extraction / impact-analysis pass end to end.

    `params` must carry `event_types` and `days_back` (see todo_chen.md
    section 5), plus whatever `emit` status-event sink the caller wants
    status events sent to. `run_id` is minted by the server (Ding), not here.
    """
    emit = params.get("emit")
    if emit is None:
        raise ValueError("Unable to establish status stream, emit() is None")

    data = {
        "run_id": params.get("run_id"),
        "event_types": params.get("event_types") or ALL_EVENT_TYPES,
        "days_back": params.get("days_back") or DEFAULT_DAYS_BACK,
        "output": {},
        "emit": emit,
    }

    try:
        pipeline_steps, loop_instructions, step_index_map = _build_steps(params)
    except NotImplementedError:
        raise
    except ValueError:
        logger.exception("Failed to build pipeline for run_id %s", data["run_id"])
        raise

    try:
        success, data = await execute_pipeline(
            data=data,
            pipeline_steps=pipeline_steps,
            loop_instructions=loop_instructions,
            step_index_map=step_index_map,
        )
        exit_reason = data.get("exit_reason")
        if success and exit_reason is None:
            return success, {"output": data["output"]}
        elif success and exit_reason is not None:
            return success, {"exit_reason": exit_reason}
    except ValueError as e:
        logger.exception(e)
        return False, {"error_message": str(e)}
    except Exception as e:
        logger.exception(e)
        return False, {"error_message": str(e)}


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
    params["emit"] = emit

    async def _run():
        try:
            return await run_pipeline(params)
        finally:
            await status_queue.put(_SENTINEL)

    task = asyncio.create_task(_run())
    while True:
        event = await status_queue.get()
        if event is _SENTINEL:
            break
        yield event

    success, payload = await task
    yield {"type": "result", "success": success, **payload}
