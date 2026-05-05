from __future__ import annotations

from typing import Protocol
from typing import Any

from .common import PerceptionFrame
from .data import CoreDataStore


class LongTermMemory(Protocol):
    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        ...

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        ...


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


class LocalCandidateBackedMemory:
    def __init__(self, data_store: CoreDataStore) -> None:
        self.data_store = data_store

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        memory_items: list[dict[str, Any]] = []
        for topic in frame.topics:
            memory_items.extend(
                self.data_store.get_long_term_memories(
                    semantic_topic=topic,
                    limit=5,
                )
            )
        return memory_items

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            {
                "semantic_topic": topic,
                "source": "local_candidate_backed_memory",
                "event_ids": list(frame.event_ids),
                "priority": frame.highest_priority,
            }
            for topic in frame.topics
        ]

    def commit_candidates(
        self,
        execution_span_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        memory_ids: list[str] = []
        for candidate in candidates:
            memory_ids.append(
                self.data_store.persist_long_term_memory(
                    execution_span_id,
                    str(candidate.get("semantic_topic") or "unknown"),
                    dict(candidate),
                )
            )
        return memory_ids
