from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .common import new_id
from .data import CoreDataStore


@dataclass(frozen=True)
class CoreSessionSnapshot:
    session_id: str
    current_execution_span_id: str | None
    recent_execution_spans: tuple[dict[str, Any], ...]
    recent_audit_ids: tuple[str, ...]
    pending_approval_requests: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_execution_span_id": self.current_execution_span_id,
            "recent_execution_spans": list(self.recent_execution_spans),
            "recent_audit_ids": list(self.recent_audit_ids),
            "pending_approval_requests": list(self.pending_approval_requests),
        }


class CoreSessionManager:
    def __init__(self, data_store: CoreDataStore) -> None:
        self.data_store = data_store

    def resolve_session_id(self, session_id: str | None = None) -> str:
        return session_id or new_id("session")

    def load_snapshot(
        self,
        session_id: str,
        *,
        current_execution_span_id: str | None = None,
        limit: int = 5,
    ) -> CoreSessionSnapshot:
        spans = tuple(self.data_store.get_execution_spans_for_session(session_id, limit=limit))
        recent_audit_ids = tuple(
            str(span["payload"].get("audit_id"))
            for span in spans
            if span["payload"].get("audit_id")
        )
        pending_approval_requests = tuple(
            self.data_store.get_approval_requests(session_id=session_id, status="pending")
        )
        return CoreSessionSnapshot(
            session_id=session_id,
            current_execution_span_id=current_execution_span_id,
            recent_execution_spans=spans,
            recent_audit_ids=recent_audit_ids,
            pending_approval_requests=pending_approval_requests,
        )

    def build_context(
        self,
        session_id: str,
        *,
        current_execution_span_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        snapshot = self.load_snapshot(
            session_id,
            current_execution_span_id=current_execution_span_id,
            limit=limit,
        )
        previous_execution_spans = [
            span
            for span in snapshot.recent_execution_spans
            if span["execution_span_id"] != current_execution_span_id
        ]
        return {
            "session_id": snapshot.session_id,
            "current_execution_span_id": snapshot.current_execution_span_id,
            "previous_execution_spans": previous_execution_spans,
            "recent_audit_ids": list(snapshot.recent_audit_ids),
            "pending_approval_requests": list(snapshot.pending_approval_requests),
        }