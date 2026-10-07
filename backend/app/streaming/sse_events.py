from typing import Any, TypedDict


class QueueItem(TypedDict):
    event: str
    data: dict[str, Any]


def make_event(event: str, data: dict[str, Any]) -> QueueItem:
    return {"event": event, "data": data}
