"""Job event frames over Redis pub/sub (LLD §5.7).

Workers publish JSON progress frames to the channel ``job:{job_id}``; the SSE
endpoint subscribes and relays them. Terminal frames (``step`` in
:data:`TERMINAL_STEPS`) tell the stream it may close.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

_CHANNEL_PREFIX = "job:"
TERMINAL_STEPS = frozenset({"done", "failed"})


def channel(job_id: uuid.UUID | str) -> str:
    return f"{_CHANNEL_PREFIX}{job_id}"


def is_terminal(frame: dict[str, Any]) -> bool:
    return frame.get("step") in TERMINAL_STEPS


async def publish(redis: Any, job_id: uuid.UUID | str, frame: dict[str, Any]) -> None:
    """Publish one JSON frame to the job's channel. Best-effort — a missing
    subscriber is fine (late subscribers get the replay frame from the DB)."""
    if redis is None:
        return
    await redis.publish(channel(job_id), json.dumps(frame))
