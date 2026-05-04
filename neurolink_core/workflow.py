from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from .agents import AffectiveDecision
from .common import PerceptionEvent, PerceptionFrame, WorkflowResult, new_id
from .data import CoreDataStore
from .events import PerceptionEventRouter
from .maf import (
    MafAffectiveAgentAdapter,
    MafRationalAgentAdapter,
    MafRuntimeProfile,
    build_maf_runtime_profile,
)
from .memory import FakeLongTermMemory
from .policy import ReadOnlyToolPolicy
from .tools import FakeUnitToolAdapter, ToolExecutionResult


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


class NoModelCoreWorkflow:
    def __init__(
        self,
        data_store: CoreDataStore | None = None,
        affective_agent: Any | None = None,
        rational_agent: Any | None = None,
        memory: FakeLongTermMemory | None = None,
        tool_adapter: FakeUnitToolAdapter | None = None,
        tool_policy: ReadOnlyToolPolicy | None = None,
        maf_runtime_profile: MafRuntimeProfile | None = None,
        event_router: PerceptionEventRouter | None = None,
    ) -> None:
        self.maf_runtime_profile = maf_runtime_profile or build_maf_runtime_profile()
        self.data_store = data_store or CoreDataStore()
        self.event_router = event_router or PerceptionEventRouter()
        self.affective_agent = affective_agent or MafAffectiveAgentAdapter(
            profile=self.maf_runtime_profile
        )
        self.rational_agent = rational_agent or MafRationalAgentAdapter(
            profile=self.maf_runtime_profile
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
    ) -> WorkflowResult:
        steps: list[str] = []
        execution_span_id = new_id("span")

        steps.append("event_ingress")
        events = self.event_router.route(raw_events)
        self.data_store.persist_execution_span(
            execution_span_id,
            "running",
            {"event_source": "provided", "normalized_event_count": len(events)},
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
        session_context: dict[str, Any] = {
            "execution_span_id": execution_span_id,
            "maf_runtime": self.maf_runtime_metadata(),
        }

        steps.append("long_term_memory_lookup_stub")
        memory_items = self.memory.lookup(frame)
        if hasattr(self.memory, "propose_candidates"):
            for candidate in self.memory.propose_candidates(frame):
                self.data_store.persist_memory_candidate(
                    execution_span_id,
                    str(candidate.get("semantic_topic") or "unknown"),
                    dict(candidate),
                )

        steps.append("affective_arbitration")
        decision = self.affective_agent.decide(frame, memory_items)

        steps.append("rational_delegate_optional")
        plan = self.rational_agent.plan(decision, frame)

        steps.append("tool_and_unit_execution")
        tool_results: list[ToolExecutionResult] = []
        if plan is not None:
            contract = self.tool_adapter.describe_tool(plan.tool_name)
            if contract is None:
                result = self.tool_adapter.execute(plan.tool_name, plan.args)
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
        self.data_store.persist_audit_record(
            audit_id,
            execution_span_id,
            "ok",
            self._build_audit_payload(
                frame,
                decision,
                session_context,
                tool_results,
                self.tool_adapter,
                self.maf_runtime_metadata(),
            ),
        )
        self.data_store.persist_execution_span(
            execution_span_id,
            "ok",
            {
                "steps": steps,
                "events_persisted": len(events),
                "normalized_event_count": len(events),
                "delegated": plan is not None,
                "tool_result_count": len(tool_results),
                "audit_id": audit_id,
            },
        )

        steps.append("notification_dispatch")
        return WorkflowResult(
            status="ok",
            execution_span_id=execution_span_id,
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
            "tool_results": [result.to_dict() for result in tool_results],
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
) -> dict[str, Any]:
    data_store = CoreDataStore(db_path)
    try:
        workflow = NoModelCoreWorkflow(data_store=data_store, tool_adapter=tool_adapter)
        result = workflow.run(
            events if events is not None else sample_events(),
            use_db_events=use_db_events,
            query_limit=query_limit,
            min_priority=min_priority,
            topic=topic,
        )
        payload = result.to_dict()
        payload["maf_runtime"] = workflow.maf_runtime_metadata()
        payload["db_counts"] = {
            "perception_events": data_store.count("perception_events"),
            "execution_spans": data_store.count("execution_spans"),
            "facts": data_store.count("facts"),
            "policy_decisions": data_store.count("policy_decisions"),
            "memory_candidates": data_store.count("memory_candidates"),
            "tool_results": data_store.count("tool_results"),
            "audit_records": data_store.count("audit_records"),
        }
        payload["query"] = {
            "use_db_events": use_db_events,
            "query_limit": query_limit,
            "min_priority": min_priority,
            "topic": topic,
            "recent_topics": data_store.get_recent_topics(limit=min(query_limit, 10)),
        }
        payload["execution_evidence"] = data_store.build_execution_evidence(
            result.execution_span_id,
            result.audit_id,
        )
        payload["event_source"] = "provided" if events is not None else "sample"
        return payload
    finally:
        data_store.close()
