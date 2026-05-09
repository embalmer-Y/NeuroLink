from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from .common import PerceptionFrame
from .common import new_id
from .data import CoreDataStore


PROMPT_SAFE_CONTEXT_SCHEMA_VERSION = "1.2.5-prompt-safe-context-v2"
MEMORY_RECALL_POLICY_SCHEMA_VERSION = "1.2.5-memory-recall-policy-v1"


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
    skills = cast(
        list[Any],
        session_context.get("skill_descriptors") or [],
    )
    mcp_descriptors = cast(
        list[Any],
        session_context.get("mcp_descriptors") or [],
    )
    affective_runtime_context = cast(
        dict[str, Any],
        session_context.get("affective_runtime_context") or {},
    )
    memory_runtime = cast(dict[str, Any], session_context.get("memory_runtime") or {})
    memory_recall = _build_memory_recall_context(memory_items, memory_runtime)
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
            "items": list(memory_recall["rational_recall"]["items"]),
            "affective_items": list(memory_recall["affective_recall"]["items"]),
            "rational_items": list(memory_recall["rational_recall"]["items"]),
            "recall_policy": memory_recall,
            "runtime": _summarize_runtime_metadata(memory_runtime),
        },
        "runtime": {
            "maf": _summarize_maf_runtime(
                cast(dict[str, Any], session_context.get("maf_runtime") or {})
            ),
            "memory": _summarize_runtime_metadata(memory_runtime),
        },
        "available_tools": [
            _summarize_tool_contract(tool)
            for tool in available_tools[:20]
            if isinstance(tool, dict)
        ],
        "skills": [
            _summarize_skill_descriptor(skill)
            for skill in skills[:5]
            if isinstance(skill, dict)
        ],
        "mcp_bridges": [
            _summarize_mcp_descriptor(mcp)
            for mcp in mcp_descriptors[:5]
            if isinstance(mcp, dict)
        ],
        "affective_runtime": _summarize_affective_runtime_context(
            affective_runtime_context
        ),
        "safety_boundaries": {
            "model_context_only": True,
            "can_execute_tools_directly": False,
            "tool_execution_requires_core_policy": True,
            "approval_and_lease_gates_authoritative": True,
            "prompt_safe_multimodal_summary_only": True,
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
    governance = cast(dict[str, Any], payload.get("memory_governance") or {})
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
        "source_fact_refs": list(governance.get("source_fact_refs") or [])[:10],
        "retention_class": str(governance.get("retention_class") or ""),
        "lifecycle_state": str(governance.get("lifecycle_state") or ""),
        "commit_backend": str(governance.get("commit_backend") or ""),
    }


def _build_memory_recall_context(
    memory_items: list[dict[str, Any]],
    memory_runtime: dict[str, Any],
) -> dict[str, Any]:
    affective_items: list[dict[str, Any]] = []
    rational_items: list[dict[str, Any]] = []
    filtered_out_categories: dict[str, int] = {}

    def _increment(category: str) -> None:
        filtered_out_categories[category] = filtered_out_categories.get(category, 0) + 1

    for item in memory_items:
        classification = _classify_memory_recall_item(item)
        summary = _summarize_memory_item(item)
        if classification == "affective_long_term":
            affective_items.append(summary)
            continue
        if classification == "rational_operational":
            rational_items.append(summary)
            continue
        _increment(classification)

    affective_source_refs = sorted(
        {
            str(item.get("memory_id") or "")
            for item in affective_items
            if str(item.get("memory_id") or "")
        }
    )
    rational_source_refs = sorted(
        {
            str(item.get("memory_id") or "")
            for item in rational_items
            if str(item.get("memory_id") or "")
        }
    )
    runtime_summary = _summarize_runtime_metadata(memory_runtime)
    return {
        "schema_version": MEMORY_RECALL_POLICY_SCHEMA_VERSION,
        "lookup_count": len(memory_items),
        "backend_kind": str(memory_runtime.get("backend_kind") or ""),
        "fallback_backend": str(memory_runtime.get("fallback_backend") or ""),
        "fallback_active": bool(memory_runtime.get("fallback_active", False)),
        "last_lookup_status": str(memory_runtime.get("last_lookup_status") or ""),
        "affective_recall": {
            "policy_mode": "affective_long_term_context",
            "selected_count": len(affective_items),
            "items": affective_items[:5],
            "source_refs": affective_source_refs[:10],
            "filtered_out_categories": dict(filtered_out_categories),
        },
        "rational_recall": {
            "policy_mode": "rational_operational_context",
            "selected_count": len(rational_items),
            "items": rational_items[:5],
            "source_refs": rational_source_refs[:10],
            "filtered_out_categories": dict(filtered_out_categories),
        },
        "filtered_out_categories": dict(filtered_out_categories),
        "runtime": runtime_summary,
    }


def _classify_memory_recall_item(item: dict[str, Any]) -> str:
    payload = cast(dict[str, Any], item.get("payload") or {})
    governance = cast(dict[str, Any], payload.get("memory_governance") or {})
    lifecycle_state = str(governance.get("lifecycle_state") or "")
    retention_class = str(governance.get("retention_class") or "")
    if not governance:
        return "ungoverned_memory_result"
    if lifecycle_state != "committed":
        return f"lifecycle_{lifecycle_state or 'unknown'}"
    if retention_class == "user_context":
        return "affective_long_term"
    if retention_class in {"operational_lesson", "operational_context"}:
        return "rational_operational"
    return f"retention_{retention_class or 'unknown'}"


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


def _summarize_skill_descriptor(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(skill.get("name") or ""),
        "schema_version": str(skill.get("schema_version") or ""),
        "workflow_plan_required": bool(skill.get("workflow_plan_required", False)),
        "json_output_required": bool(skill.get("json_output_required", False)),
        "release_target_promotion_blocked": bool(
            skill.get("release_target_promotion_blocked", False)
        ),
        "callback_audit_required": bool(skill.get("callback_audit_required", False)),
    }


def _summarize_mcp_descriptor(mcp: dict[str, Any]) -> dict[str, Any]:
    safety_boundaries = cast(dict[str, Any], mcp.get("safety_boundaries") or {})
    return {
        "bridge_name": str(mcp.get("bridge_name") or ""),
        "schema_version": str(mcp.get("schema_version") or ""),
        "bridge_mode": str(mcp.get("bridge_mode") or ""),
        "transport": str(mcp.get("transport") or ""),
        "read_only_tool_count": len(mcp.get("read_only_tools") or []),
        "blocked_tool_count": len(mcp.get("blocked_tools") or []),
        "tool_execution_via_mcp_forbidden": bool(
            mcp.get("tool_execution_via_mcp_forbidden")
            if "tool_execution_via_mcp_forbidden" in mcp
            else safety_boundaries.get("tool_execution_via_mcp_forbidden", False)
        ),
        "external_mcp_connection_enabled": bool(
            mcp.get("external_mcp_connection_enabled")
            if "external_mcp_connection_enabled" in mcp
            else safety_boundaries.get("external_mcp_connection_enabled", False)
        ),
    }


def _summarize_affective_runtime_context(context: dict[str, Any]) -> dict[str, Any]:
    multimodal_summary = cast(dict[str, Any], context.get("multimodal_summary") or {})
    profile_route = cast(dict[str, Any], context.get("profile_route") or {})
    presentation_policy = cast(dict[str, Any], context.get("presentation_policy") or {})
    return {
        "schema_version": str(context.get("schema_version") or ""),
        "multimodal_summary": {
            "request_id": str(multimodal_summary.get("request_id") or ""),
            "input_modes": list(multimodal_summary.get("input_modes") or []),
            "response_modes": list(multimodal_summary.get("response_modes") or []),
            "profile_hint": str(multimodal_summary.get("profile_hint") or "auto"),
            "latency_class": str(multimodal_summary.get("latency_class") or ""),
            "text_count": int(multimodal_summary.get("text_count") or 0),
            "text_preview": list(multimodal_summary.get("text_preview") or []),
            "image_ref_count": int(multimodal_summary.get("image_ref_count") or 0),
            "audio_ref_count": int(multimodal_summary.get("audio_ref_count") or 0),
            "video_ref_count": int(multimodal_summary.get("video_ref_count") or 0),
            "provenance": str(multimodal_summary.get("provenance") or ""),
        },
        "profile_route": {
            "requested_profile": str(profile_route.get("requested_profile") or "auto"),
            "selected_profile": str(profile_route.get("selected_profile") or ""),
            "route_status": str(profile_route.get("route_status") or "unknown"),
            "route_reason": str(profile_route.get("route_reason") or ""),
            "failure_status": str(profile_route.get("failure_status") or ""),
            "fallback_used": bool(profile_route.get("fallback_used", False)),
            "candidate_rejection_count": int(
                profile_route.get("candidate_rejection_count") or 0
            ),
            "requires_live_backend": bool(
                profile_route.get("requires_live_backend", False)
            ),
            "route_ready": bool(profile_route.get("route_ready", False)),
        },
        "presentation_policy": {
            "prompt_safe_multimodal_summary_only": bool(
                presentation_policy.get("prompt_safe_multimodal_summary_only", False)
            ),
            "internal_facts_remain_core_owned": bool(
                presentation_policy.get("internal_facts_remain_core_owned", False)
            ),
            "model_may_not_execute_tools_directly": bool(
                presentation_policy.get("model_may_not_execute_tools_directly", False)
            ),
            "user_visible_output_separated_from_internal_facts": bool(
                presentation_policy.get(
                    "user_visible_output_separated_from_internal_facts",
                    False,
                )
            ),
        },
    }