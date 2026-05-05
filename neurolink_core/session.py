from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from .common import PerceptionFrame
from .common import new_id
from .data import CoreDataStore


PROMPT_SAFE_CONTEXT_SCHEMA_VERSION = "1.2.2-prompt-safe-context-v1"


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


def build_prompt_safe_context(
    session_context: dict[str, Any],
    *,
    frame: PerceptionFrame,
    memory_items: list[dict[str, Any]],
    available_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    previous_spans = cast(
        list[Any],
        session_context.get("previous_execution_spans") or [],
    )
    pending_approvals = cast(
        list[Any],
        session_context.get("pending_approval_requests") or [],
    )
    return {
        "schema_version": PROMPT_SAFE_CONTEXT_SCHEMA_VERSION,
        "session_id": str(session_context.get("session_id") or ""),
        "execution_span_id": str(session_context.get("execution_span_id") or ""),
        "target_app_id": str(session_context.get("target_app_id") or ""),
        "frame": {
            "frame_id": frame.frame_id,
            "event_ids": list(frame.event_ids),
            "topics": list(frame.topics),
            "highest_priority": frame.highest_priority,
        },
        "history": {
            "previous_execution_count": len(previous_spans),
            "recent_audit_ids": list(session_context.get("recent_audit_ids") or [])[:5],
            "previous_executions": [
                _summarize_execution_span(span)
                for span in previous_spans[:5]
                if isinstance(span, dict)
            ],
        },
        "pending_approvals": [
            _summarize_pending_approval(approval)
            for approval in pending_approvals[:5]
            if isinstance(approval, dict)
        ],
        "memory": {
            "lookup_count": len(memory_items),
            "items": [_summarize_memory_item(item) for item in memory_items[:5]],
            "runtime": _summarize_runtime_metadata(
                cast(dict[str, Any], session_context.get("memory_runtime") or {})
            ),
        },
        "runtime": {
            "maf": _summarize_maf_runtime(
                cast(dict[str, Any], session_context.get("maf_runtime") or {})
            ),
            "memory": _summarize_runtime_metadata(
                cast(dict[str, Any], session_context.get("memory_runtime") or {})
            ),
        },
        "available_tools": [
            _summarize_tool_contract(tool)
            for tool in available_tools[:20]
            if isinstance(tool, dict)
        ],
        "safety_boundaries": {
            "model_context_only": True,
            "can_execute_tools_directly": False,
            "tool_execution_requires_core_policy": True,
            "approval_and_lease_gates_authoritative": True,
        },
    }


def _summarize_execution_span(span: dict[str, Any]) -> dict[str, Any]:
    payload = cast(dict[str, Any], span.get("payload") or {})
    return {
        "execution_span_id": str(span.get("execution_span_id") or ""),
        "status": str(span.get("status") or ""),
        "steps": list(payload.get("steps") or [])[:12],
        "delegated": bool(payload.get("delegated", False)),
        "tool_result_count": int(payload.get("tool_result_count") or 0),
        "audit_id": str(payload.get("audit_id") or ""),
    }


def _summarize_pending_approval(approval: dict[str, Any]) -> dict[str, Any]:
    payload = cast(dict[str, Any], approval.get("payload") or {})
    contract = cast(dict[str, Any], payload.get("contract") or {})
    return {
        "approval_request_id": str(approval.get("approval_request_id") or ""),
        "tool_name": str(approval.get("tool_name") or payload.get("tool_name") or ""),
        "status": str(approval.get("status") or payload.get("status") or ""),
        "side_effect_level": str(
            payload.get("side_effect_level") or contract.get("side_effect_level") or ""
        ),
        "required_resources": list(
            payload.get("required_resources") or contract.get("required_resources") or []
        ),
        "target_app_id": str(payload.get("target_app_id") or ""),
    }


def _summarize_memory_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = cast(dict[str, Any], item.get("payload") or {})
    return {
        "memory_id": str(item.get("memory_id") or item.get("id") or ""),
        "semantic_topic": str(
            item.get("semantic_topic")
            or payload.get("semantic_topic")
            or item.get("topic")
            or ""
        ),
        "source": str(item.get("source") or payload.get("source") or ""),
        "source_execution_span_id": str(item.get("source_execution_span_id") or ""),
        "created_at": str(item.get("created_at") or ""),
        "event_ids": list(payload.get("event_ids") or item.get("event_ids") or [])[:10],
        "priority": payload.get("priority", item.get("priority")),
    }


def _summarize_runtime_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "backend_kind",
        "backend_runtime",
        "requires_external_service",
        "fallback_active",
        "fallback_backend",
        "package_available",
        "sidecar_configured",
        "last_lookup_status",
        "last_commit_status",
        "can_execute_tools_directly",
    }
    return {key: metadata[key] for key in allowed_keys if key in metadata}


def _summarize_maf_runtime(metadata: dict[str, Any]) -> dict[str, Any]:
    provider_config = cast(dict[str, Any], metadata.get("provider_config") or {})
    return {
        "provider_mode": str(metadata.get("provider_mode") or ""),
        "real_provider_enabled": bool(metadata.get("real_provider_enabled", False)),
        "provider_ready_for_model_call": bool(
            metadata.get("provider_ready_for_model_call", False)
        ),
        "provider_kind": str(provider_config.get("provider_kind") or "unknown"),
        "agent_roles": list(metadata.get("agent_roles") or []),
    }


def _summarize_tool_contract(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(tool.get("name") or tool.get("tool_name") or ""),
        "side_effect_level": str(tool.get("side_effect_level") or ""),
        "required_resources": list(tool.get("required_resources") or []),
        "approval_required": bool(tool.get("approval_required", False)),
    }