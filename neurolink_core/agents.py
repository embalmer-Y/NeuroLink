from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .common import PerceptionFrame


@dataclass(frozen=True)
class AffectiveDecision:
    delegated: bool
    reason: str
    salience: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegated": self.delegated,
            "reason": self.reason,
            "salience": self.salience,
        }


@dataclass(frozen=True)
class RationalPlan:
    tool_name: str
    args: dict[str, Any]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "args": dict(self.args),
            "reason": self.reason,
        }


class FakeAffectiveAgent:
    OPERATIONAL_WAKE_TOPICS: dict[str, tuple[str, int]] = {
        "unit.network.endpoint_drift": (
            "network_endpoint_drift_requires_rational_window",
            85,
        ),
        "unit.health.degraded": (
            "degraded_health_requires_rational_window",
            85,
        ),
        "unit.lifecycle.activate_failed": (
            "activate_failure_requires_rational_window",
            90,
        ),
        "unit.state.offline": (
            "offline_state_requires_rational_window",
            90,
        ),
        "unit.state.online": (
            "online_state_requires_rational_window",
            70,
        ),
    }

    def decide(self, frame: PerceptionFrame, memory_items: list[dict[str, Any]]) -> AffectiveDecision:
        del memory_items
        for topic in frame.topics:
            if topic in self.OPERATIONAL_WAKE_TOPICS:
                reason, minimum_salience = self.OPERATIONAL_WAKE_TOPICS[topic]
                return AffectiveDecision(
                    delegated=True,
                    reason=reason,
                    salience=max(frame.highest_priority, minimum_salience),
                )
        delegated = frame.highest_priority >= 50 or "unit.callback" in frame.topics
        if delegated:
            return AffectiveDecision(
                delegated=True,
                reason="salient_perception_frame_requires_rational_window",
                salience=frame.highest_priority,
            )
        return AffectiveDecision(
            delegated=False,
            reason="low_salience_frame_recorded_without_action",
            salience=frame.highest_priority,
        )


class FakeRationalAgent:
    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        *,
        available_tools: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> RationalPlan | None:
        del available_tools
        if not decision.delegated:
            return None
        tool_name = "system_state_sync"
        reason = "state_sync_before_any_unit_side_effect"
        if "unit.lifecycle.activate_failed" in frame.topics:
            tool_name = "system_activation_health_guard"
            reason = "post_activate_health_guard_required"
        elif "user.input.control.app.restart" in frame.topics:
            tool_name = "system_restart_app"
            reason = "app_restart_requested_by_user_input"
        elif "user.input.control.app.start" in frame.topics:
            tool_name = "system_start_app"
            reason = "app_start_requested_by_user_input"
        elif "user.input.control.app.stop" in frame.topics:
            tool_name = "system_stop_app"
            reason = "app_stop_requested_by_user_input"
        elif "user.input.control.app.unload" in frame.topics:
            tool_name = "system_unload_app"
            reason = "app_unload_requested_by_user_input"
        elif "user.input.query.device" in frame.topics:
            tool_name = "system_query_device"
            reason = "device_query_requested_by_user_input"
        elif "user.input.query.apps" in frame.topics:
            tool_name = "system_query_apps"
            reason = "app_query_requested_by_user_input"
        elif "user.input.query.leases" in frame.topics:
            tool_name = "system_query_leases"
            reason = "lease_query_requested_by_user_input"
        elif "user.input.capabilities" in frame.topics:
            tool_name = "system_capabilities"
            reason = "capabilities_query_requested_by_user_input"
        args: dict[str, Any] = {
            "event_ids": list(frame.event_ids),
            "reason": decision.reason,
        }
        if session_context is not None and tool_name in {
            "system_activation_health_guard",
            "system_restart_app",
            "system_start_app",
            "system_stop_app",
            "system_unload_app",
        }:
            target_app_id = str(session_context.get("target_app_id") or "")
            if target_app_id:
                args["app_id"] = target_app_id
                args["app"] = target_app_id
        return RationalPlan(tool_name=tool_name, args=args, reason=reason)
