from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .motivation import VitalityState
from .persona import PersonaState


INTERNAL_AUTONOMY_TOPICS = {"time.tick", "core.maintenance.tick"}


@dataclass(frozen=True)
class AutonomousDaemonPolicy:
    maintenance_interval_cycles: int = 3
    time_tick_priority: int = 10
    maintenance_tick_priority: int = 25
    wake_priority_threshold: int = 50
    time_tick_period_ms: int = 1000


@dataclass(frozen=True)
class AutonomousCyclePlan:
    cycle_index: int
    cycle_kind: str
    wake_decision: str
    reasons: tuple[str, ...]
    raw_event_count: int
    planned_events: tuple[dict[str, Any], ...]
    synthetic_event_count: int
    should_run_workflow: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_index": self.cycle_index,
            "cycle_kind": self.cycle_kind,
            "wake_decision": self.wake_decision,
            "reasons": list(self.reasons),
            "raw_event_count": self.raw_event_count,
            "planned_event_count": len(self.planned_events),
            "synthetic_event_count": self.synthetic_event_count,
            "should_run_workflow": self.should_run_workflow,
            "planned_topics": [
                str(event.get("semantic_topic") or event.get("event_type") or "unknown")
                for event in self.planned_events
            ],
        }


@dataclass(frozen=True)
class AutonomousDaemonState:
    autonomy_enabled: bool
    operator_paused: bool
    run_state: str
    cycle_count: int
    last_maintenance_cycle: int | None
    continuity: dict[str, Any]
    heartbeat: dict[str, Any]
    vitality_summary: dict[str, Any]
    persona_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "autonomy_enabled": self.autonomy_enabled,
            "operator_paused": self.operator_paused,
            "run_state": self.run_state,
            "cycle_count": self.cycle_count,
            "last_maintenance_cycle": self.last_maintenance_cycle,
            "continuity": dict(self.continuity),
            "heartbeat": dict(self.heartbeat),
            "vitality_summary": dict(self.vitality_summary),
            "persona_summary": dict(self.persona_summary),
        }


def build_vitality_summary(vitality_state: VitalityState | None) -> dict[str, Any]:
    if vitality_state is None:
        return {
            "present": False,
            "state": "unknown",
            "score": None,
            "urgency_modifier": None,
            "policy_impact": "salience_and_tone_only",
        }
    payload = vitality_state.to_dict()
    payload["present"] = True
    return payload


def build_persona_summary(persona_state: PersonaState | None) -> dict[str, Any]:
    if persona_state is None:
        return {
            "present": False,
            "persona_id": "",
            "mood": "unknown",
            "vitality_summary": "unknown",
            "relationship_count": 0,
        }
    summary = persona_state.rational_summary()
    summary["present"] = True
    summary["relationship_count"] = len(persona_state.relationship_summaries)
    return summary


def build_daemon_state(
    *,
    autonomy_enabled: bool,
    operator_paused: bool,
    cycle_count: int,
    last_maintenance_cycle: int | None,
    previous_execution_count: int,
    seeded_dedupe_key_count: int,
    last_cycle_timestamp: str | None,
    vitality_state: VitalityState | None,
    persona_state: PersonaState | None,
) -> AutonomousDaemonState:
    run_state = "paused" if operator_paused else "idle"
    return AutonomousDaemonState(
        autonomy_enabled=autonomy_enabled,
        operator_paused=operator_paused,
        run_state=run_state,
        cycle_count=cycle_count,
        last_maintenance_cycle=last_maintenance_cycle,
        continuity={
            "resumed_session": previous_execution_count > 0 or seeded_dedupe_key_count > 0,
            "previous_execution_count": previous_execution_count,
            "seeded_dedupe_key_count": seeded_dedupe_key_count,
        },
        heartbeat={
            "recorded": autonomy_enabled,
            "status": run_state,
            "last_cycle_index": cycle_count if cycle_count > 0 else None,
            "last_cycle_timestamp": last_cycle_timestamp,
        },
        vitality_summary=build_vitality_summary(vitality_state),
        persona_summary=build_persona_summary(persona_state),
    )


def build_time_tick_event(
    *,
    cycle_index: int,
    timestamp_wall: str,
    period_ms: int,
    priority: int,
) -> dict[str, Any]:
    suffix = f"{cycle_index:04d}"
    return {
        "event_id": f"evt-autonomy-time-tick-{suffix}",
        "source_kind": "clock",
        "source_node": "core-daemon",
        "event_type": "time.tick",
        "semantic_topic": "time.tick",
        "timestamp_wall": timestamp_wall,
        "priority": priority,
        "dedupe_key": f"autonomy-time-tick-{suffix}",
        "policy_tags": ["clock", "autonomy"],
        "payload": {
            "period_ms": period_ms,
            "cycle_index": cycle_index,
            "scheduler": "autonomy_planner",
        },
    }


def build_maintenance_tick_event(
    *,
    cycle_index: int,
    timestamp_wall: str,
    priority: int,
    reason: str,
    vitality_state: str | None,
) -> dict[str, Any]:
    suffix = f"{cycle_index:04d}"
    return {
        "event_id": f"evt-autonomy-maintenance-tick-{suffix}",
        "source_kind": "core",
        "source_node": "core-daemon",
        "event_type": "core.maintenance.tick",
        "semantic_topic": "core.maintenance.tick",
        "timestamp_wall": timestamp_wall,
        "priority": priority,
        "dedupe_key": f"autonomy-maintenance-tick-{suffix}",
        "policy_tags": ["maintenance", "autonomy"],
        "payload": {
            "cycle_index": cycle_index,
            "reason": reason,
            "vitality_state": vitality_state or "unknown",
            "scheduler": "autonomy_planner",
        },
    }


def plan_autonomous_cycle(
    raw_events: Iterable[dict[str, Any]],
    *,
    cycle_index: int,
    timestamp_wall: str,
    policy: AutonomousDaemonPolicy | None = None,
    vitality_state: VitalityState | None = None,
    last_maintenance_cycle: int | None = None,
    operator_paused: bool = False,
) -> AutonomousCyclePlan:
    active_policy = policy or AutonomousDaemonPolicy()
    base_events = [dict(event) for event in raw_events]
    planned_events = [dict(event) for event in base_events]
    reasons: list[str] = []
    topics = {
        str(event.get("semantic_topic") or event.get("event_type") or "unknown")
        for event in planned_events
    }

    if operator_paused:
        return AutonomousCyclePlan(
            cycle_index=cycle_index,
            cycle_kind="paused",
            wake_decision="paused",
            reasons=("operator_paused",),
            raw_event_count=len(base_events),
            planned_events=tuple(planned_events),
            synthetic_event_count=0,
            should_run_workflow=False,
        )

    if "time.tick" not in topics:
        planned_events.append(
            build_time_tick_event(
                cycle_index=cycle_index,
                timestamp_wall=timestamp_wall,
                period_ms=active_policy.time_tick_period_ms,
                priority=active_policy.time_tick_priority,
            )
        )
        topics.add("time.tick")
        reasons.append("time_tick_scheduled")

    maintenance_due = False
    maintenance_reason = ""
    if vitality_state is not None and vitality_state.state in {"concerned", "critical"}:
        maintenance_due = True
        maintenance_reason = f"vitality_{vitality_state.state}"
        reasons.append("low_vitality_maintenance_due")
    elif last_maintenance_cycle is None and (
        cycle_index % active_policy.maintenance_interval_cycles == 0
    ):
        maintenance_due = True
        maintenance_reason = "maintenance_interval_elapsed"
        reasons.append("maintenance_interval_elapsed")
    elif last_maintenance_cycle is not None and (
        cycle_index - last_maintenance_cycle >= active_policy.maintenance_interval_cycles
    ):
        maintenance_due = True
        maintenance_reason = "maintenance_interval_elapsed"
        reasons.append("maintenance_interval_elapsed")

    if maintenance_due and "core.maintenance.tick" not in topics:
        planned_events.append(
            build_maintenance_tick_event(
                cycle_index=cycle_index,
                timestamp_wall=timestamp_wall,
                priority=active_policy.maintenance_tick_priority,
                reason=maintenance_reason,
                vitality_state=vitality_state.state if vitality_state else None,
            )
        )
        topics.add("core.maintenance.tick")

    external_events = [
        event
        for event in planned_events
        if str(event.get("semantic_topic") or event.get("event_type") or "unknown")
        not in INTERNAL_AUTONOMY_TOPICS
    ]
    highest_priority = max(
        (int(event.get("priority") or 0) for event in planned_events),
        default=0,
    )

    if external_events:
        wake_decision = "affective_wake"
        reasons.append("external_event_present")
    elif "core.maintenance.tick" in topics:
        wake_decision = "maintenance_only"
        reasons.append("maintenance_tick_present")
    elif highest_priority >= active_policy.wake_priority_threshold:
        wake_decision = "affective_wake"
        reasons.append("priority_threshold_reached")
    else:
        wake_decision = "sleep"
        reasons.append("quiet_cycle")

    if external_events and "core.maintenance.tick" in topics:
        cycle_kind = "mixed"
    elif external_events:
        cycle_kind = "external_batch"
    elif "core.maintenance.tick" in topics:
        cycle_kind = "maintenance_tick"
    else:
        cycle_kind = "time_tick"

    return AutonomousCyclePlan(
        cycle_index=cycle_index,
        cycle_kind=cycle_kind,
        wake_decision=wake_decision,
        reasons=tuple(reasons),
        raw_event_count=len(base_events),
        planned_events=tuple(planned_events),
        synthetic_event_count=max(0, len(planned_events) - len(base_events)),
        should_run_workflow=wake_decision in {"affective_wake", "maintenance_only"},
    )