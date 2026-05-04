from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SideEffectLevel(StrEnum):
    OBSERVE_ONLY = "observe_only"
    READ_ONLY = "read_only"
    SUGGEST_ONLY = "suggest_only"
    LOW_RISK_EXECUTE = "low_risk_execute"
    APPROVAL_REQUIRED = "approval_required"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    reason: str
    side_effect_level: SideEffectLevel
    approval_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "side_effect_level": self.side_effect_level.value,
            "approval_required": self.approval_required,
        }


class ReadOnlyToolPolicy:
    allowed_levels = frozenset(
        {
            SideEffectLevel.OBSERVE_ONLY,
            SideEffectLevel.READ_ONLY,
            SideEffectLevel.SUGGEST_ONLY,
        }
    )

    def evaluate_contract(self, contract: Any) -> ToolPolicyDecision:
        side_effect_level = SideEffectLevel(str(contract.side_effect_level))
        approval_required = bool(getattr(contract, "approval_required", False))
        if approval_required:
            return ToolPolicyDecision(
                allowed=False,
                reason="approval_required_tool_blocked_in_no_model_slice",
                side_effect_level=side_effect_level,
                approval_required=approval_required,
            )
        if side_effect_level not in self.allowed_levels:
            return ToolPolicyDecision(
                allowed=False,
                reason="side_effect_level_not_allowed_in_no_model_slice",
                side_effect_level=side_effect_level,
                approval_required=approval_required,
            )
        return ToolPolicyDecision(
            allowed=True,
            reason="read_only_policy_allows_tool",
            side_effect_level=side_effect_level,
            approval_required=approval_required,
        )