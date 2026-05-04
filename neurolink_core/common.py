from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass(frozen=True)
class PerceptionEvent:
    event_id: str
    source_kind: str
    event_type: str
    timestamp_wall: str
    source_node: str | None = None
    source_app: str | None = None
    semantic_topic: str | None = None
    timestamp_mono: float | None = None
    priority: int = 50
    dedupe_key: str | None = None
    causality_id: str | None = None
    raw_payload_ref: str | None = None
    policy_tags: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PerceptionEvent":
        return cls(
            event_id=str(payload.get("event_id") or new_id("evt")),
            source_kind=str(payload.get("source_kind") or "core"),
            source_node=payload.get("source_node"),
            source_app=payload.get("source_app"),
            event_type=str(payload.get("event_type") or "unknown"),
            semantic_topic=payload.get("semantic_topic"),
            timestamp_mono=payload.get("timestamp_mono"),
            timestamp_wall=str(payload.get("timestamp_wall") or utc_now_iso()),
            priority=int(payload.get("priority", 50)),
            dedupe_key=payload.get("dedupe_key"),
            causality_id=payload.get("causality_id"),
            raw_payload_ref=payload.get("raw_payload_ref"),
            policy_tags=tuple(payload.get("policy_tags") or ()),
            payload=dict(payload.get("payload") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["policy_tags"] = list(self.policy_tags)
        return data


@dataclass(frozen=True)
class PerceptionFrame:
    frame_id: str
    event_ids: tuple[str, ...]
    highest_priority: int
    topics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "event_ids": list(self.event_ids),
            "highest_priority": self.highest_priority,
            "topics": list(self.topics),
        }


@dataclass(frozen=True)
class WorkflowResult:
    status: str
    execution_span_id: str
    steps: tuple[str, ...]
    events_persisted: int
    delegated: bool
    tool_results: tuple[dict[str, Any], ...]
    audit_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution_span_id": self.execution_span_id,
            "steps": list(self.steps),
            "events_persisted": self.events_persisted,
            "delegated": self.delegated,
            "tool_results": list(self.tool_results),
            "audit_id": self.audit_id,
        }
