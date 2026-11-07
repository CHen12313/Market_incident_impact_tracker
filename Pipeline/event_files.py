"""Persist event documents and price caches without exposing partial writes."""
import dataclasses
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from datetime import datetime, timezone

from Data_Classes.enums import EventStatus, Relation
from Data_Classes.event import EventFile

event_lock = RLock()


def atomic_write(path, write):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            write(file)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_event(cache, event, impacts):
    """`event` is an `EventInfo`, `impacts` a list of `Impact` (see
    Data_Classes/event.py). Returns the plain dict actually written, since
    that's what crosses back out to the HTTP/JSON boundary (Server/app.py's
    `jsonify`, refresh_event's caller) — the dataclasses stay internal."""
    impacts = sorted(impacts, key=lambda item: (item.relation != Relation.DIRECT, -abs(item.study.car_pct)))
    document = EventFile(
        event=event, impacts=impacts,
        status=EventStatus.EARLY if min(item.study.days_after for item in impacts) < 5 else EventStatus.COMPLETE,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    path = Path(cache) / "events" / f"{event.event_id}.json"
    payload = dataclasses.asdict(document)
    with event_lock:
        atomic_write(path, lambda file: json.dump(payload, file, ensure_ascii=False, allow_nan=False, indent=2))
    return payload
