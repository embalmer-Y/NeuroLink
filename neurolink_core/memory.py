from __future__ import annotations

from typing import Any

from .common import PerceptionFrame


class FakeLongTermMemory:
    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        del frame
        return []

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            {
                "semantic_topic": topic,
                "source": "no_model_perception_frame",
                "event_ids": list(frame.event_ids),
                "priority": frame.highest_priority,
            }
            for topic in frame.topics
        ]
