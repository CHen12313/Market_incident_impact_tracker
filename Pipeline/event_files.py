"""Persist event documents and price caches without exposing partial writes."""
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from datetime import datetime, timezone


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
    impacts.sort(key=lambda item: (item["relation"] != "direct", -abs(item["study"]["car_pct"])))
    document = dict(
        event=event, impacts=impacts,
        status="early" if min(item["study"]["days_after"] for item in impacts) < 5 else "complete",
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
    path = Path(cache) / "events" / f"{event['event_id']}.json"
    with event_lock:
        atomic_write(path, lambda file: json.dump(document, file, ensure_ascii=False, allow_nan=False, indent=2))
    return document
