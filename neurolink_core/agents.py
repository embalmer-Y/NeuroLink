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
    def decide(self, frame: PerceptionFrame, memory_items: list[dict[str, Any]]) -> AffectiveDecision:
        del memory_items
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
    def plan(self, decision: AffectiveDecision, frame: PerceptionFrame) -> RationalPlan | None:
        if not decision.delegated:
            return None
        return RationalPlan(
            tool_name="system_state_sync",
            args={"event_ids": list(frame.event_ids), "reason": decision.reason},
            reason="state_sync_before_any_unit_side_effect",
        )
