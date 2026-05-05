from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any, Callable, cast

from .agents import AffectiveDecision
from .common import PerceptionEvent, PerceptionFrame, WorkflowResult, new_id
from .data import CoreDataStore
from .events import PerceptionEventRouter
from .maf import (
    MafProviderMode,
    MafRuntimeProfile,
    build_affective_agent_adapter,
    build_default_maf_provider_client,
    build_maf_runtime_profile,
    build_rational_agent_adapter,
)
from .memory import FakeLongTermMemory, LongTermMemory, build_memory_backend
from .policy import ReadOnlyToolPolicy
from .session import CoreSessionManager, build_prompt_safe_context
from .tools import FakeUnitToolAdapter, ToolContract, ToolExecutionResult


AGENT_RUN_EVIDENCE_SCHEMA_VERSION = "1.2.2-agent-run-evidence-v1"


def _extract_observed_resource_names(leases: list[Any]) -> list[str]:
    observed_resources: list[str] = []
    for lease in leases:
        if not isinstance(lease, dict):
            continue
        lease_dict = cast(dict[str, Any], lease)
        for key in ("resource", "resource_name", "lease_name", "name"):
            value = lease_dict.get(key)
            if isinstance(value, str) and value:
                observed_resources.append(value)
                break
    return sorted(set(observed_resources))


def _extract_observed_lease_rows(lease_observation: dict[str, Any]) -> list[dict[str, Any]]:
    if lease_observation.get("status") != "ok":
        return []
    payload = cast(dict[str, Any] | None, lease_observation.get("payload"))
    if not isinstance(payload, dict):
        return []
    result_payload = cast(dict[str, Any] | None, payload.get("result"))
    if not isinstance(result_payload, dict):
        return []
    replies = cast(list[Any] | None, result_payload.get("replies"))
    if not isinstance(replies, list) or not replies:
        return []
    first_reply = cast(dict[str, Any], replies[0])
    reply_payload = cast(dict[str, Any] | None, first_reply.get("payload"))
    if not isinstance(reply_payload, dict):
        return []
    leases = cast(list[Any] | None, reply_payload.get("leases"))
    if not isinstance(leases, list):
        return []
    rows: list[dict[str, Any]] = []
    for lease in leases:
        if isinstance(lease, dict):
            rows.append(cast(dict[str, Any], lease))
    return rows


def _extract_observed_app_rows(apps_observation: dict[str, Any]) -> list[dict[str, Any]]:
    if apps_observation.get("status") != "ok":
        return []
    payload = cast(dict[str, Any] | None, apps_observation.get("payload"))
    if not isinstance(payload, dict):
        return []
    result_payload = cast(dict[str, Any] | None, payload.get("result"))
    if not isinstance(result_payload, dict):
        return []
    replies = cast(list[Any] | None, result_payload.get("replies"))
    if not isinstance(replies, list) or not replies:
        return []
    first_reply = cast(dict[str, Any], replies[0])
    reply_payload = cast(dict[str, Any] | None, first_reply.get("payload"))
    if not isinstance(reply_payload, dict):
        return []
    apps = cast(list[Any] | None, reply_payload.get("apps"))
    if not isinstance(apps, list):
        return []
    rows: list[dict[str, Any]] = []
    for app in apps:
        if isinstance(app, dict):
            rows.append(cast(dict[str, Any], app))
    return rows


def _build_operator_requirements(
    approval_request: dict[str, Any],
    *,
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    adapter = tool_adapter or FakeUnitToolAdapter()
    request_payload = cast(dict[str, Any], approval_request["payload"])
    raw_required_resources = request_payload.get("required_resources")
    required_resources: list[str] = []
    if isinstance(raw_required_resources, (list, tuple)):
        required_resources = [
            str(item) for item in cast(list[Any] | tuple[Any, ...], raw_required_resources)
        ]
    contract_payload = cast(dict[str, Any], request_payload.get("contract") or {})

    lease_observation = adapter.execute(
        "system_query_leases",
        {"reason": "approval_operator_inspect"},
    ).to_dict()
    apps_observation = adapter.execute(
        "system_query_apps",
        {"reason": "approval_operator_inspect"},
    ).to_dict()
    state_sync_observation = adapter.execute(
        "system_state_sync",
        {"reason": "approval_operator_inspect"},
    ).to_dict()

    observed_leases = _extract_observed_lease_rows(lease_observation)
    observed_apps = _extract_observed_app_rows(apps_observation)

    requested_args = cast(dict[str, Any], request_payload.get("requested_args") or {})
    target_app_id = str(
        requested_args.get("app_id")
        or requested_args.get("app")
        or request_payload.get("target_app_id")
        or ""
    )
    if not target_app_id and len(observed_apps) == 1:
        observed_app = observed_apps[0]
        target_app_id = str(
            observed_app.get("app_id")
            or observed_app.get("name")
            or observed_app.get("app")
            or ""
        )

    observed_resources = _extract_observed_resource_names(observed_leases)
    resolved_required_resources: list[str] = []
    unresolved_required_resources: list[str] = []
    for resource in required_resources:
        if resource == "app_control_lease":
            if target_app_id:
                resolved_required_resources.append(f"app/{target_app_id}/control")
            else:
                unresolved_required_resources.append(resource)
            continue
        resolved_required_resources.append(resource)

    matching_lease_ids: list[str] = []
    for lease in observed_leases:
        resource = str(lease.get("resource") or "")
        if resource not in resolved_required_resources:
            continue
        lease_id = str(lease.get("lease_id") or "")
        if lease_id:
            matching_lease_ids.append(lease_id)

    missing_required_resources = [
        resource
        for resource in resolved_required_resources
        if resource not in observed_resources
    ]
    missing_required_resources.extend(unresolved_required_resources)

    return {
        "resource": str(contract_payload.get("resource") or request_payload.get("tool_name") or ""),
        "required_resources": required_resources,
        "resolved_required_resources": resolved_required_resources,
        "unresolved_required_resources": unresolved_required_resources,
        "observed_resources": observed_resources,
        "missing_required_resources": missing_required_resources,
        "resource_requirements_satisfied": not missing_required_resources,
        "cleanup_hint": request_payload.get("cleanup_hint"),
        "target_app_id": target_app_id,
        "matching_lease_ids": matching_lease_ids,
        "lease_observation": lease_observation,
        "apps_observation": apps_observation,
        "state_sync_observation": state_sync_observation,
    }


def build_approval_context(
    data_store: CoreDataStore,
    approval_request: dict[str, Any],
    *,
    tool_adapter: Any | None = None,
    resumed_execution: dict[str, Any] | None = None,
    operator_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_execution_span_id = str(approval_request["source_execution_span_id"])
    source_execution_span = data_store.get_execution_span(source_execution_span_id)
    source_audit_id = None
    if source_execution_span is not None:
        source_audit_id = source_execution_span["payload"].get("audit_id")

    resumed_execution_evidence: dict[str, Any] | None = None
    if resumed_execution is not None:
        resumed_execution_evidence = data_store.build_execution_evidence(
            str(resumed_execution["execution_span_id"]),
            str(resumed_execution["audit_id"]),
        )
    else:
        resumed_execution_span_id = approval_request["payload"].get(
            "resumed_execution_span_id"
        )
        if resumed_execution_span_id is not None:
            resumed_execution_span = data_store.get_execution_span(
                str(resumed_execution_span_id)
            )
            if resumed_execution_span is not None:
                resumed_audit_id = resumed_execution_span["payload"].get("audit_id")
                if resumed_audit_id is not None:
                    resumed_execution_evidence = data_store.build_execution_evidence(
                        str(resumed_execution_span_id),
                        str(resumed_audit_id),
                    )

    return {
        "source_execution_span": source_execution_span,
        "source_execution_evidence": (
            data_store.build_execution_evidence(
                source_execution_span_id,
                str(source_audit_id),
            )
            if source_audit_id is not None
            else None
        ),
        "resumed_execution_evidence": resumed_execution_evidence,
        "operator_requirements": operator_requirements
        if operator_requirements is not None
        else _build_operator_requirements(
            approval_request,
            tool_adapter=tool_adapter,
        ),
    }


def sample_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "evt-demo-callback-001",
            "source_kind": "unit_app",
            "source_node": "unit-01",
            "source_app": "neuro_demo_gpio",
            "event_type": "callback",
            "semantic_topic": "unit.callback",
            "timestamp_wall": "2026-05-04T00:00:00Z",
            "priority": 80,
            "dedupe_key": "demo-callback-001",
            "policy_tags": ["demo", "no_model"],
            "payload": {"callback_enabled": True},
        },
        {
            "event_id": "evt-time-tick-001",
            "source_kind": "clock",
            "event_type": "time.tick",
            "semantic_topic": "time.tick",
            "timestamp_wall": "2026-05-04T00:00:01Z",
            "priority": 10,
            "dedupe_key": "tick-001",
            "policy_tags": ["clock"],
            "payload": {"period_ms": 1000},
        },
    ]


def build_user_prompt_event(input_text: str) -> list[dict[str, Any]]:
    lowered = input_text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    semantic_topic = "user.input"
    has_app_target = "app" in tokens or "apps" in tokens or "application" in tokens
    target_app_id = _extract_explicit_app_id(input_text)
    if "restart" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.restart"
    elif "start" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.start"
    elif "stop" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.stop"
    elif "unload" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.unload"
    elif "lease" in tokens or "leases" in tokens:
        semantic_topic = "user.input.query.leases"
    elif has_app_target:
        semantic_topic = "user.input.query.apps"
    elif "device" in tokens or "network" in tokens or "status" in tokens:
        semantic_topic = "user.input.query.device"
    elif "capability" in tokens or "capabilities" in tokens:
        semantic_topic = "user.input.capabilities"
    return [
        {
            "event_id": new_id("evt"),
            "source_kind": "user",
            "source_app": target_app_id,
            "event_type": "user.input",
            "semantic_topic": semantic_topic,
            "timestamp_wall": "2026-05-04T00:00:02Z",
            "priority": 70,
            "policy_tags": ["user_input", "agent_run"],
            "payload": {
                "text": input_text,
                **({"target_app_id": target_app_id} if target_app_id else {}),
            },
        }
    ]


def _extract_explicit_app_id(input_text: str) -> str | None:
    candidate_pattern = re.compile(r"[a-z0-9][a-z0-9_-]{2,}")
    stopwords = {
        "restart",
        "start",
        "stop",
        "unload",
        "app",
        "apps",
        "application",
        "please",
        "the",
        "now",
        "current",
        "show",
        "query",
        "device",
        "status",
        "lease",
        "leases",
        "unit",
    }
    lowered = input_text.lower()
    for match in candidate_pattern.finditer(lowered):
        candidate = match.group(0)
        if candidate in stopwords:
            continue
        if candidate.startswith("neuro") or "_" in candidate or "-" in candidate:
            return candidate
    return None


def _extract_target_app_id_from_events(events: list[PerceptionEvent]) -> str | None:
    for event in events:
        if event.source_kind != "user":
            continue
        payload_target_app_id = str(event.payload.get("target_app_id") or "")
        if payload_target_app_id:
            return payload_target_app_id
        if event.source_app:
            return str(event.source_app)
    return None


class NoModelCoreWorkflow:
    def __init__(
        self,
        data_store: CoreDataStore | None = None,
        affective_agent: Any | None = None,
        rational_agent: Any | None = None,
        memory: LongTermMemory | None = None,
        tool_adapter: Any | None = None,
        tool_policy: ReadOnlyToolPolicy | None = None,
        maf_runtime_profile: MafRuntimeProfile | None = None,
        provider_client: Any | None = None,
        rational_backend: str = "auto",
        allow_model_call: bool = False,
        copilot_agent_factory: Any | None = None,
        event_router: PerceptionEventRouter | None = None,
        session_manager: CoreSessionManager | None = None,
    ) -> None:
        self.maf_runtime_profile = maf_runtime_profile or build_maf_runtime_profile()
        self.data_store = data_store or CoreDataStore()
        self.event_router = event_router or PerceptionEventRouter()
        self.session_manager = session_manager or CoreSessionManager(self.data_store)
        self.affective_agent = affective_agent or build_affective_agent_adapter(
            self.maf_runtime_profile,
            provider_client=provider_client,
        )
        self.rational_agent = rational_agent or build_rational_agent_adapter(
            self.maf_runtime_profile,
            provider_client=provider_client,
            rational_backend=rational_backend,
            allow_model_call=allow_model_call,
            copilot_agent_factory=copilot_agent_factory,
        )
        self.memory = memory or FakeLongTermMemory()
        self.tool_adapter = tool_adapter or FakeUnitToolAdapter()
        self.tool_policy = tool_policy or ReadOnlyToolPolicy()

    def run(
        self,
        raw_events: Iterable[dict[str, Any]],
        use_db_events: bool = False,
        query_limit: int = 100,
        min_priority: int = 0,
        topic: str | None = None,
        session_id: str | None = None,
    ) -> WorkflowResult:
        steps: list[str] = []
        execution_span_id = new_id("span")
        resolved_session_id = self.session_manager.resolve_session_id(session_id)
        initial_session_context = self.session_manager.build_context(
            resolved_session_id,
            limit=5,
        )

        steps.append("event_ingress")
        events = self.event_router.route(raw_events)
        self.data_store.persist_execution_span(
            execution_span_id,
            "running",
            {
                "event_source": "provided",
                "normalized_event_count": len(events),
                "session_id": resolved_session_id,
            },
            session_id=resolved_session_id,
        )

        steps.append("database_persistence")
        for event in events:
            self.data_store.persist_event(event)

        steps.append("perception_frame_build")
        frame = self._build_frame(events)

        if use_db_events:
            steps.append("database_query")
            db_events = self.data_store.query_events(
                limit=query_limit,
                min_priority=min_priority,
                topic=topic,
            )
            if db_events:
                steps.append("frame_build_from_db")
                frame_data = self.data_store.build_frame(db_events)
                frame = PerceptionFrame(**frame_data)

        self._persist_frame_facts(execution_span_id, frame, events)

        steps.append("session_context_load")
        target_app_id = _extract_target_app_id_from_events(events)
        session_context: dict[str, Any] = {
            "execution_span_id": execution_span_id,
            **initial_session_context,
            "maf_runtime": self.maf_runtime_metadata(),
            "memory_runtime": self.memory_runtime_metadata(),
            **({"target_app_id": target_app_id} if target_app_id else {}),
        }

        steps.append("long_term_memory_lookup_stub")
        memory_items = self.memory.lookup(frame)
        session_context["memory_lookup_count"] = len(memory_items)
        session_context["memory_runtime"] = self.memory_runtime_metadata()
        candidate_payloads: list[dict[str, Any]] = []
        if hasattr(self.memory, "propose_candidates"):
            for candidate in self.memory.propose_candidates(frame):
                candidate_payload = dict(candidate)
                candidate_payloads.append(candidate_payload)
                self.data_store.persist_memory_candidate(
                    execution_span_id,
                    str(candidate.get("semantic_topic") or "unknown"),
                    candidate_payload,
                )
        commit_candidates = getattr(self.memory, "commit_candidates", None)
        if callable(commit_candidates):
            commit_candidates_fn = cast(
                Callable[[str, list[dict[str, Any]]], list[str]],
                commit_candidates,
            )
            committed_memory_ids = commit_candidates_fn(
                execution_span_id,
                candidate_payloads,
            )
            session_context["committed_memory_count"] = len(committed_memory_ids)
            session_context["committed_memory_ids"] = committed_memory_ids
            session_context["memory_runtime"] = self.memory_runtime_metadata()

        available_tools = self._available_tool_context()
        session_context["available_tools"] = available_tools
        prompt_safe_context = build_prompt_safe_context(
            session_context,
            frame=frame,
            memory_items=memory_items,
            available_tools=available_tools,
        )
        session_context["prompt_safe_context"] = prompt_safe_context

        affective_step = (
            "affective_model_call"
            if self.maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
            else "affective_arbitration"
        )
        steps.append(affective_step)
        safe_memory_items = cast(
            list[dict[str, Any]],
            prompt_safe_context["memory"]["items"],
        )
        decision = self.affective_agent.decide(frame, safe_memory_items)
        model_call_evidence = self._build_model_call_evidence(
            frame,
            decision,
            self.maf_runtime_metadata(),
        )
        session_context["model_call_evidence"] = model_call_evidence

        steps.append("rational_delegate_optional")
        plan = self.rational_agent.plan(
            decision,
            frame,
            available_tools=available_tools,
            session_context=prompt_safe_context,
        )

        steps.append("tool_and_unit_execution")
        tool_results: list[ToolExecutionResult] = []
        if plan is not None:
            contract = self.tool_adapter.describe_tool(plan.tool_name)
            if contract is None:
                result = ToolExecutionResult(
                    tool_result_id=new_id("tool"),
                    tool_name=plan.tool_name,
                    status="error",
                    payload={
                        "failure_status": "unknown_tool",
                        "failure_class": "manifest_lookup_failed",
                        "requested_plan": plan.to_dict(),
                        "available_tools": available_tools,
                    },
                )
            else:
                policy_decision = self.tool_policy.evaluate_contract(contract)
                policy_payload = policy_decision.to_dict()
                self.data_store.persist_policy_decision(
                    execution_span_id,
                    plan.tool_name,
                    policy_payload,
                )
                if policy_decision.allowed:
                    result = self.tool_adapter.execute(plan.tool_name, plan.args)
                    result.payload["policy_decision"] = policy_payload
                else:
                    if policy_decision.approval_required:
                        approval_request_id = new_id("approval")
                        approval_request_payload: dict[str, Any] = {
                            "approval_request_id": approval_request_id,
                            "tool_name": plan.tool_name,
                            "reason": "operator_approval_required_before_execution",
                            "requested_args": dict(plan.args),
                            "required_resources": list(contract.required_resources),
                            "cleanup_hint": contract.cleanup_hint,
                            "side_effect_level": contract.side_effect_level.value,
                            "policy_decision": policy_payload,
                            "contract": contract.to_dict(),
                            "status": "pending",
                        }
                        self.data_store.persist_approval_request(
                            resolved_session_id,
                            execution_span_id,
                            plan.tool_name,
                            "pending",
                            approval_request_payload,
                            approval_request_id=approval_request_id,
                        )
                        result = ToolExecutionResult(
                            tool_result_id=new_id("tool"),
                            tool_name=plan.tool_name,
                            status="pending_approval",
                            payload={
                                "failure_status": "approval_required",
                                "failure_class": "approval_gate_pending",
                                "policy_decision": policy_payload,
                                "approval_request": approval_request_payload,
                            },
                        )
                        session_context["pending_approval_request_ids"] = list(
                            {
                                *cast(
                                    list[str],
                                    session_context.get(
                                        "pending_approval_request_ids",
                                        [],
                                    ),
                                ),
                                approval_request_id,
                            }
                        )
                    else:
                        result = ToolExecutionResult(
                            tool_result_id=new_id("tool"),
                            tool_name=plan.tool_name,
                            status="blocked",
                            payload={
                                "failure_status": "policy_blocked",
                                "failure_class": "tool_policy_denied",
                                "policy_decision": policy_payload,
                            },
                        )
            self.data_store.persist_tool_result(
                result.tool_result_id,
                execution_span_id,
                result.tool_name,
                result.status,
                result.payload,
            )
            tool_results.append(result)

        steps.append("audit_record")
        audit_id = new_id("audit")
        final_response = self._build_final_response(frame, decision, tool_results)
        self.data_store.persist_audit_record(
            audit_id,
            execution_span_id,
            "ok",
            self._build_audit_payload(
                frame,
                decision,
                session_context,
                tool_results,
                final_response,
                self.tool_adapter,
                self.maf_runtime_metadata(),
            ),
            session_id=resolved_session_id,
        )
        self.data_store.persist_execution_span(
            execution_span_id,
            "ok",
            {
                "session_id": resolved_session_id,
                "steps": steps,
                "events_persisted": len(events),
                "normalized_event_count": len(events),
                "delegated": plan is not None,
                "tool_result_count": len(tool_results),
                "audit_id": audit_id,
            },
            session_id=resolved_session_id,
        )

        steps.append("notification_dispatch")
        return WorkflowResult(
            status="ok",
            execution_span_id=execution_span_id,
            session_id=resolved_session_id,
            final_response=final_response,
            steps=tuple(steps),
            events_persisted=len(events),
            delegated=plan is not None,
            tool_results=tuple(result.to_dict() for result in tool_results),
            audit_id=audit_id,
        )

    @staticmethod
    def _build_frame(events: list[PerceptionEvent]) -> PerceptionFrame:
        event_ids = tuple(event.event_id for event in events)
        topics = tuple(
            sorted(
                {
                    event.semantic_topic or event.event_type
                    for event in events
                    if event.semantic_topic or event.event_type
                }
            )
        )
        highest_priority = max((event.priority for event in events), default=0)
        return PerceptionFrame(
            frame_id=new_id("frame"),
            event_ids=event_ids,
            highest_priority=highest_priority,
            topics=topics,
        )

    def maf_runtime_metadata(self) -> dict[str, Any]:
        agent_adapters: list[dict[str, Any]] = []
        for agent in (self.affective_agent, self.rational_agent):
            runtime_metadata = getattr(agent, "runtime_metadata", None)
            if callable(runtime_metadata):
                agent_adapters.append(cast(dict[str, Any], runtime_metadata()))
        return {
            **self.maf_runtime_profile.to_dict(),
            "agent_adapters": agent_adapters,
        }

    def memory_runtime_metadata(self) -> dict[str, Any]:
        runtime_metadata = getattr(self.memory, "runtime_metadata", None)
        if callable(runtime_metadata):
            return cast(dict[str, Any], runtime_metadata())
        return {
            "backend_kind": "unknown",
            "backend_runtime": "unknown",
            "requires_external_service": False,
            "fallback_active": False,
            "can_execute_tools_directly": False,
        }

    def _available_tool_context(self) -> list[dict[str, Any]]:
        tool_manifest = getattr(self.tool_adapter, "tool_manifest", None)
        if not callable(tool_manifest):
            return []
        manifest = cast(tuple[ToolContract, ...], tool_manifest())
        available_tools: list[dict[str, Any]] = []
        for contract in manifest:
            available_tools.append(contract.to_dict())
        return available_tools

    def _persist_frame_facts(
        self,
        execution_span_id: str,
        frame: PerceptionFrame,
        events: list[PerceptionEvent],
    ) -> None:
        self.data_store.persist_fact(
            execution_span_id,
            "perception_frame",
            frame.frame_id,
            frame.to_dict(),
        )
        for event in events:
            self.data_store.persist_fact(
                execution_span_id,
                "perception_event_topic",
                event.semantic_topic or event.event_type,
                {
                    "event_id": event.event_id,
                    "source_kind": event.source_kind,
                    "source_node": event.source_node,
                    "source_app": event.source_app,
                    "priority": event.priority,
                },
            )

    @staticmethod
    def _build_audit_payload(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        session_context: dict[str, Any],
        tool_results: list[ToolExecutionResult],
        final_response: dict[str, Any],
        tool_adapter: Any,
        maf_runtime: dict[str, Any],
    ) -> dict[str, Any]:
        adapter_runtime = {}
        if hasattr(tool_adapter, "runtime_metadata"):
            adapter_runtime = dict(tool_adapter.runtime_metadata())

        state_sync_summary: dict[str, Any] | None = None
        for result in tool_results:
            if result.tool_name != "system_state_sync":
                continue
            payload = result.payload
            if result.status == "ok":
                snapshot = dict(payload.get("state_sync") or {})
                state_sync_summary = {
                    "tool_status": result.status,
                    "snapshot_status": snapshot.get("status", "unknown"),
                    "recommended_next_actions": list(
                        snapshot.get("recommended_next_actions") or []
                    ),
                    "failure_class": "",
                    "failure_status": "",
                }
            else:
                raw_nested_payload = payload.get("payload")
                nested_payload: dict[str, Any] = (
                    cast(dict[str, Any], raw_nested_payload)
                    if isinstance(raw_nested_payload, dict)
                    else {}
                )
                recommended_next_actions: list[Any] = []
                if nested_payload:
                    recommended_next_actions = list(
                        nested_payload.get("recommended_next_actions") or []
                    )
                state_sync_summary = {
                    "tool_status": result.status,
                    "snapshot_status": str((nested_payload or {}).get("status") or "error"),
                    "recommended_next_actions": recommended_next_actions,
                    "failure_class": str(payload.get("failure_class") or ""),
                    "failure_status": str(payload.get("failure_status") or ""),
                }
            break

        return {
            "frame": frame.to_dict(),
            "decision": decision.to_dict(),
            "session_context": dict(session_context),
            "maf_runtime": dict(maf_runtime),
            "adapter_runtime": adapter_runtime,
            "state_sync_summary": state_sync_summary,
            "final_response": dict(final_response),
            "tool_results": [result.to_dict() for result in tool_results],
        }

    @staticmethod
    def _build_model_call_evidence(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        maf_runtime: dict[str, Any],
    ) -> dict[str, Any]:
        provider_config = cast(dict[str, Any], maf_runtime.get("provider_config") or {})
        agent_adapters = cast(list[Any], maf_runtime.get("agent_adapters") or [])
        affective_adapter: dict[str, Any] = {}
        for adapter in agent_adapters:
            if not isinstance(adapter, dict):
                continue
            adapter_payload = cast(dict[str, Any], adapter)
            if adapter_payload.get("agent_role") == "affective":
                affective_adapter = adapter_payload
                break
        real_provider_enabled = bool(maf_runtime.get("real_provider_enabled", False))
        provider_call_supported = bool(
            affective_adapter.get("provider_call_supported", False)
        )
        return {
            "agent_role": "affective",
            "call_status": (
                "model_call_succeeded"
                if real_provider_enabled and provider_call_supported
                else "deterministic_fake"
            ),
            "executes_model_call": real_provider_enabled and provider_call_supported,
            "frame_id": frame.frame_id,
            "event_ids": list(frame.event_ids),
            "provider_kind": str(provider_config.get("provider_kind") or "unknown"),
            "provider_client_kind": str(
                affective_adapter.get("provider_client_kind") or "deterministic_fake"
            ),
            "response_schema": "AffectiveDecision",
            "decision": decision.to_dict(),
        }

    @staticmethod
    def _build_final_response(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        tool_results: list[ToolExecutionResult],
    ) -> dict[str, Any]:
        topics = ", ".join(frame.topics) if frame.topics else "unknown"
        if not decision.delegated:
            text = f"Recorded perception topics {topics}; no delegated action was required."
        elif not tool_results:
            text = f"Observed {topics} and opened a reasoning window, but no tool execution was required."
        else:
            result = tool_results[0]
            tool_label = result.tool_name.replace("system_", "").replace("_", " ")
            if result.status == "ok":
                text = f"Observed {topics} and completed a read-only {tool_label} before responding."
            elif result.status == "pending_approval":
                text = f"Observed {topics} and prepared delegated {tool_label}, but execution is waiting for explicit approval."
            elif result.status == "blocked":
                text = f"Observed {topics} but blocked delegated {tool_label} due to policy constraints."
            else:
                text = f"Observed {topics} and attempted delegated {tool_label}, but the tool path reported an error."
        return {
            "speaker": "affective",
            "delegated": decision.delegated,
            "text": text,
            "salience": decision.salience,
        }


def run_no_model_dry_run(
    db_path: str = ":memory:",
    *,
    use_db_events: bool = False,
    query_limit: int = 100,
    min_priority: int = 0,
    topic: str | None = None,
    tool_adapter: Any | None = None,
    events: Iterable[dict[str, Any]] | None = None,
    session_id: str | None = None,
    maf_provider_mode: str = "deterministic_fake",
    allow_model_call: bool = False,
    memory: Any | None = None,
    memory_backend: str = "fake",
    mem0_client: Any | None = None,
    provider_client: Any | None = None,
    rational_backend: str = "auto",
    copilot_agent_factory: Any | None = None,
    require_real_tool_adapter: bool = False,
) -> dict[str, Any]:
    data_store = CoreDataStore(db_path)
    try:
        maf_runtime_profile = build_maf_runtime_profile(provider_mode=maf_provider_mode)
        resolved_provider_client = provider_client
        if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value:
            if not allow_model_call:
                raise ValueError("real_provider_mode_requires_allow_model_call")
            if resolved_provider_client is None:
                resolved_provider_client = build_default_maf_provider_client(
                    maf_runtime_profile
                )
        if rational_backend == "copilot" and not allow_model_call:
            raise ValueError("copilot_rational_backend_requires_allow_model_call")
        resolved_memory = memory or build_memory_backend(
            memory_backend,
            data_store,
            mem0_client=mem0_client,
        )
        workflow = NoModelCoreWorkflow(
            data_store=data_store,
            memory=resolved_memory,
            tool_adapter=tool_adapter,
            maf_runtime_profile=maf_runtime_profile,
            provider_client=resolved_provider_client,
            rational_backend=rational_backend,
            allow_model_call=allow_model_call,
            copilot_agent_factory=copilot_agent_factory,
        )
        result = workflow.run(
            events if events is not None else sample_events(),
            use_db_events=use_db_events,
            query_limit=query_limit,
            min_priority=min_priority,
            topic=topic,
            session_id=session_id,
        )
        payload = result.to_dict()
        payload["maf_runtime"] = workflow.maf_runtime_metadata()
        payload["memory_runtime"] = workflow.memory_runtime_metadata()
        payload["release_gate_require_real_tool_adapter"] = require_real_tool_adapter
        execution_evidence = data_store.build_execution_evidence(
            result.execution_span_id,
            result.audit_id,
        )
        payload["runtime_mode"] = (
            "real_llm"
            if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
            else "deterministic"
        )
        audit_payload = cast(dict[str, Any], execution_evidence["audit_record"]["payload"])
        session_context = cast(dict[str, Any], audit_payload.get("session_context") or {})
        payload["model_call_evidence"] = session_context.get("model_call_evidence")
        payload["db_counts"] = {
            "perception_events": data_store.count("perception_events"),
            "execution_spans": data_store.count("execution_spans"),
            "facts": data_store.count("facts"),
            "policy_decisions": data_store.count("policy_decisions"),
            "memory_candidates": data_store.count("memory_candidates"),
            "long_term_memories": data_store.count("long_term_memories"),
            "tool_results": data_store.count("tool_results"),
            "approval_requests": data_store.count("approval_requests"),
            "approval_decisions": data_store.count("approval_decisions"),
            "audit_records": data_store.count("audit_records"),
        }
        payload["query"] = {
            "use_db_events": use_db_events,
            "query_limit": query_limit,
            "min_priority": min_priority,
            "topic": topic,
            "recent_topics": data_store.get_recent_topics(limit=min(query_limit, 10)),
        }
        payload["execution_evidence"] = execution_evidence
        payload["event_source"] = "provided" if events is not None else "sample"
        payload["session"] = {
            **workflow.session_manager.load_snapshot(
                result.session_id,
                current_execution_span_id=result.execution_span_id,
                limit=5,
            ).to_dict()
        }
        payload["agent_run_evidence"] = _build_agent_run_evidence(payload)
        return payload
    finally:
        data_store.close()


def _build_agent_run_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    maf_runtime = cast(dict[str, Any], payload.get("maf_runtime") or {})
    memory_runtime = cast(dict[str, Any], payload.get("memory_runtime") or {})
    model_call_evidence = cast(dict[str, Any] | None, payload.get("model_call_evidence"))
    execution_evidence = cast(dict[str, Any], payload.get("execution_evidence") or {})
    audit_record = cast(dict[str, Any] | None, execution_evidence.get("audit_record"))
    audit_payload = cast(dict[str, Any], (audit_record or {}).get("payload") or {})
    tool_adapter_runtime = cast(dict[str, Any], audit_payload.get("adapter_runtime") or {})
    session_context = cast(dict[str, Any], audit_payload.get("session_context") or {})
    prompt_safe_context = cast(dict[str, Any], session_context.get("prompt_safe_context") or {})
    db_counts = cast(dict[str, Any], payload.get("db_counts") or {})
    tool_results = cast(list[Any], payload.get("tool_results") or [])
    policy_decisions = cast(list[Any], execution_evidence.get("policy_decisions") or [])
    approval_requests = cast(list[Any], execution_evidence.get("approval_requests") or [])
    rational_backend = _extract_rational_backend_metadata(maf_runtime)
    prompt_safety_boundaries = cast(
        dict[str, Any],
        prompt_safe_context.get("safety_boundaries") or {},
    )
    prompt_memory = cast(dict[str, Any], prompt_safe_context.get("memory") or {})
    real_tool_adapter_required = bool(payload.get("release_gate_require_real_tool_adapter", False))
    real_tool_adapter_present = tool_adapter_runtime.get("adapter_kind") == "neuro-cli"
    real_tool_execution_succeeded = False
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        result_payload = cast(dict[str, Any], result)
        if result_payload.get("status") == "ok":
            real_tool_execution_succeeded = True
            break
    closure_gates: dict[str, bool] = {
        "provider_runtime_metadata_present": bool(maf_runtime),
        "rational_backend_metadata_present": bool(rational_backend),
        "memory_runtime_metadata_present": bool(memory_runtime),
        "model_call_evidence_present": model_call_evidence is not None,
        "prompt_safe_context_present": bool(prompt_safe_context),
        "db_counts_present": bool(db_counts),
        "execution_evidence_present": bool(execution_evidence),
        "policy_or_pending_evidence_present": bool(policy_decisions or approval_requests),
        "tool_result_or_pending_approval_present": bool(tool_results or approval_requests),
        "audit_record_present": audit_record is not None,
        "final_response_present": bool(payload.get("final_response")),
        "provider_context_is_prompt_safe": (
            prompt_safe_context.get("schema_version") == "1.2.2-prompt-safe-context-v1"
        ),
        "direct_tool_execution_by_model_disabled": bool(
            prompt_safety_boundaries.get("can_execute_tools_directly") is False
        ),
    }
    if real_tool_adapter_required:
        closure_gates["real_tool_adapter_present"] = real_tool_adapter_present
        closure_gates["real_tool_execution_succeeded"] = real_tool_execution_succeeded
    return {
        "schema_version": AGENT_RUN_EVIDENCE_SCHEMA_VERSION,
        "workflow": "agent-run",
        "runtime_mode": payload.get("runtime_mode"),
        "provider_runtime": {
            "provider_mode": maf_runtime.get("provider_mode"),
            "real_provider_enabled": maf_runtime.get("real_provider_enabled"),
            "provider_ready_for_model_call": maf_runtime.get(
                "provider_ready_for_model_call"
            ),
            "agent_adapter_count": len(maf_runtime.get("agent_adapters") or []),
        },
        "rational_backend": rational_backend,
        "memory_runtime": memory_runtime,
        "tool_adapter_runtime": tool_adapter_runtime,
        "release_gate_require_real_tool_adapter": real_tool_adapter_required,
        "real_tool_adapter_present": real_tool_adapter_present,
        "real_tool_execution_succeeded": real_tool_execution_succeeded,
        "model_call_evidence": model_call_evidence,
        "prompt_safe_context": {
            "schema_version": prompt_safe_context.get("schema_version"),
            "memory_lookup_count": prompt_memory.get("lookup_count"),
            "available_tool_count": len(prompt_safe_context.get("available_tools") or []),
            "pending_approval_count": len(prompt_safe_context.get("pending_approvals") or []),
            "safety_boundaries": prompt_safety_boundaries,
        },
        "db_counts": db_counts,
        "evidence_counts": {
            "facts": len(execution_evidence.get("facts") or []),
            "policy_decisions": len(policy_decisions),
            "memory_candidates": len(execution_evidence.get("memory_candidates") or []),
            "long_term_memories": len(execution_evidence.get("long_term_memories") or []),
            "approval_requests": len(approval_requests),
            "tool_results": len(tool_results),
        },
        "audit": {
            "audit_id": payload.get("audit_id"),
            "audit_record_present": audit_record is not None,
            "session_id": payload.get("session_id"),
        },
        "final_response": payload.get("final_response"),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _extract_rational_backend_metadata(maf_runtime: dict[str, Any]) -> dict[str, Any]:
    for adapter in cast(list[Any], maf_runtime.get("agent_adapters") or []):
        if not isinstance(adapter, dict):
            continue
        adapter_payload = cast(dict[str, Any], adapter)
        if adapter_payload.get("agent_role") != "rational":
            continue
        rational_backend = adapter_payload.get("rational_backend")
        if isinstance(rational_backend, dict):
            return cast(dict[str, Any], rational_backend)
    return {}


def apply_approval_decision(
    db_path: str,
    *,
    approval_request_id: str,
    decision: str,
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    if decision not in {"approve", "deny", "expire"}:
        raise ValueError("approval_decision_must_be_approve_deny_or_expire")

    data_store = CoreDataStore(db_path)
    try:
        approval_request = data_store.get_approval_request(approval_request_id)
        if approval_request is None:
            raise ValueError("approval_request_not_found")
        if approval_request["status"] != "pending":
            raise ValueError(
                f"approval_request_not_pending_{approval_request['status']}"
            )

        session_id = str(approval_request["session_id"])
        request_payload = cast(dict[str, Any], approval_request["payload"])
        decision_payload: dict[str, Any] = {
            "decision": decision,
            "tool_name": approval_request["tool_name"],
            "source_execution_span_id": approval_request["source_execution_span_id"],
        }
        resumed_execution: dict[str, Any] | None = None
        updated_status = "denied"

        if decision == "approve":
            adapter = tool_adapter or FakeUnitToolAdapter()
            operator_requirements = _build_operator_requirements(
                approval_request,
                tool_adapter=adapter,
            )
            decision_payload["operator_requirements"] = operator_requirements
            if not operator_requirements["resource_requirements_satisfied"]:
                decision_payload.update(
                    {
                        "decision_outcome": "blocked_resource_gate",
                        "failure_class": "approval_resource_gate_unsatisfied",
                        "failure_status": "missing_required_resources",
                        "missing_required_resources": list(
                            operator_requirements["missing_required_resources"]
                        ),
                    }
                )
                data_store.persist_approval_decision(
                    approval_request_id,
                    session_id,
                    decision,
                    decision_payload,
                )
                updated_request_payload: dict[str, Any] = {
                    **request_payload,
                    "status": "pending",
                    "last_decision_attempt": decision,
                    "last_decision_outcome": "blocked_resource_gate",
                    "last_missing_required_resources": list(
                        operator_requirements["missing_required_resources"]
                    ),
                }
                data_store.persist_approval_request(
                    session_id,
                    str(approval_request["source_execution_span_id"]),
                    str(approval_request["tool_name"]),
                    "pending",
                    updated_request_payload,
                    approval_request_id=approval_request_id,
                )

                updated_request = data_store.get_approval_request(approval_request_id)
                assert updated_request is not None
                return {
                    "ok": False,
                    "status": "blocked_resource_gate",
                    "failure_class": "approval_resource_gate_unsatisfied",
                    "failure_status": "missing_required_resources",
                    "approval_request": updated_request,
                    "approval_decisions": data_store.get_approval_decisions(
                        approval_request_id
                    ),
                    "resumed_execution": None,
                    "approval_context": build_approval_context(
                        data_store,
                        updated_request,
                        tool_adapter=adapter,
                        operator_requirements=operator_requirements,
                    ),
                    "session": CoreSessionManager(data_store).load_snapshot(
                        session_id, limit=5
                    ).to_dict(),
                }

            execution_span_id = new_id("span")
            tool_name = str(approval_request["tool_name"])
            requested_args = cast(dict[str, Any], request_payload.get("requested_args") or {})
            resolved_args = dict(requested_args)
            target_app_id = str(operator_requirements.get("target_app_id") or "")
            if target_app_id:
                resolved_args.setdefault("app_id", target_app_id)
                resolved_args.setdefault("app", target_app_id)
            matching_lease_ids = cast(
                list[Any],
                operator_requirements.get("matching_lease_ids") or [],
            )
            if matching_lease_ids:
                first_lease_id = str(matching_lease_ids[0] or "")
                if first_lease_id:
                    resolved_args.setdefault("lease_id", first_lease_id)
            result = adapter.execute(tool_name, resolved_args)
            result.payload["approval_request_id"] = approval_request_id
            result.payload["approval_decision"] = "approve"
            final_response: dict[str, Any] = {
                "speaker": "affective",
                "delegated": True,
                "text": f"Approved delegated {tool_name.replace('system_', '').replace('_', ' ')} and resumed execution.",
                "salience": 80,
            }
            audit_id = new_id("audit")

            data_store.persist_execution_span(
                execution_span_id,
                "running",
                {
                    "session_id": session_id,
                    "approval_request_id": approval_request_id,
                    "resumed_from_execution_span_id": approval_request["source_execution_span_id"],
                    "decision": decision,
                },
                session_id=session_id,
            )
            data_store.persist_tool_result(
                result.tool_result_id,
                execution_span_id,
                result.tool_name,
                result.status,
                result.payload,
            )
            data_store.persist_audit_record(
                audit_id,
                execution_span_id,
                "ok",
                {
                    "approval_request_id": approval_request_id,
                    "approval_decision": decision,
                    "resumed_execution": result.to_dict(),
                    "final_response": final_response,
                },
                session_id=session_id,
            )
            data_store.persist_execution_span(
                execution_span_id,
                "ok",
                {
                    "session_id": session_id,
                    "approval_request_id": approval_request_id,
                    "decision": decision,
                    "tool_result_id": result.tool_result_id,
                    "audit_id": audit_id,
                },
                session_id=session_id,
            )
            resumed_execution = {
                "execution_span_id": execution_span_id,
                "tool_result": result.to_dict(),
                "audit_id": audit_id,
                "final_response": final_response,
            }
            decision_payload["resumed_execution_span_id"] = execution_span_id
            updated_status = "approved"
        elif decision == "expire":
            updated_status = "expired"

        data_store.persist_approval_decision(
            approval_request_id,
            session_id,
            decision,
            decision_payload,
        )
        updated_request_payload: dict[str, Any] = {
            **request_payload,
            "status": updated_status,
            "last_decision": decision,
        }
        if resumed_execution is not None:
            updated_request_payload["resumed_execution_span_id"] = resumed_execution[
                "execution_span_id"
            ]
        data_store.persist_approval_request(
            session_id,
            str(approval_request["source_execution_span_id"]),
            str(approval_request["tool_name"]),
            updated_status,
            updated_request_payload,
            approval_request_id=approval_request_id,
        )

        updated_request = data_store.get_approval_request(approval_request_id)
        assert updated_request is not None

        return {
            "ok": True,
            "status": updated_status,
            "approval_request": updated_request,
            "approval_decisions": data_store.get_approval_decisions(approval_request_id),
            "resumed_execution": resumed_execution,
            "approval_context": build_approval_context(
                data_store,
                updated_request,
                tool_adapter=tool_adapter,
                resumed_execution=resumed_execution,
                operator_requirements=(
                    decision_payload.get("operator_requirements")
                    if isinstance(decision_payload.get("operator_requirements"), dict)
                    else None
                ),
            ),
            "session": CoreSessionManager(data_store).load_snapshot(session_id, limit=5).to_dict(),
        }
    finally:
        data_store.close()
