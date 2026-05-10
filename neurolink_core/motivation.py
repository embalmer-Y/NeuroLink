from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping


VITALITY_POLICY_IMPACT = "salience_and_tone_only"


@dataclass(frozen=True)
class VitalitySignal:
    reason: str
    direction: Literal["decay", "replenish"]
    verified: bool = False
    magnitude: int = 1

    def __post_init__(self) -> None:
        if self.magnitude < 1:
            raise ValueError("vitality signal magnitude must be >= 1")


@dataclass(frozen=True)
class VitalityPolicy:
    min_score: int = 0
    max_score: int = 100
    relaxed_min: int = 75
    attentive_min: int = 45
    concerned_min: int = 20
    decay_weights: Mapping[str, int] = field(
        default_factory=lambda: {
            "wall_clock_tick": 3,
            "no_effective_interaction": 4,
            "stale_memory": 5,
            "stalled_improvement": 6,
            "unresolved_fault": 8,
            "failed_test": 10,
        }
    )
    replenishment_weights: Mapping[str, int] = field(
        default_factory=lambda: {
            "useful_interaction": 4,
            "memory_consolidation": 6,
            "tests_passed": 8,
            "unit_recovery": 10,
            "approved_improvement": 12,
            "release_gate_passed": 14,
        }
    )

    def clamp(self, score: int) -> int:
        return max(self.min_score, min(self.max_score, score))

    def state_for_score(self, score: int) -> str:
        if score >= self.relaxed_min:
            return "relaxed"
        if score >= self.attentive_min:
            return "attentive"
        if score >= self.concerned_min:
            return "concerned"
        return "critical"

    def urgency_modifier_for_score(self, score: int) -> float:
        state = self.state_for_score(score)
        if state == "relaxed":
            return -0.2
        if state == "attentive":
            return 0.0
        if state == "concerned":
            return 0.35
        return 0.7

    def delta_for(self, signal: VitalitySignal) -> int:
        if signal.direction == "decay":
            weight = self.decay_weights.get(signal.reason)
            if weight is None:
                raise ValueError(f"unknown vitality decay reason: {signal.reason}")
            return -(weight * signal.magnitude)

        if not signal.verified:
            raise ValueError(
                "vitality replenishment requires verified evidence before it can be applied"
            )
        weight = self.replenishment_weights.get(signal.reason)
        if weight is None:
            raise ValueError(f"unknown vitality replenishment reason: {signal.reason}")
        return weight * signal.magnitude


@dataclass(frozen=True)
class VitalityState:
    score: int
    state: str
    last_decay_reason: str | None
    last_replenishment_reason: str | None
    urgency_modifier: float
    policy_impact: str = VITALITY_POLICY_IMPACT

    @classmethod
    def from_score(
        cls,
        score: int,
        *,
        policy: VitalityPolicy | None = None,
        last_decay_reason: str | None = None,
        last_replenishment_reason: str | None = None,
    ) -> "VitalityState":
        active_policy = policy or VitalityPolicy()
        clamped_score = active_policy.clamp(score)
        return cls(
            score=clamped_score,
            state=active_policy.state_for_score(clamped_score),
            last_decay_reason=last_decay_reason,
            last_replenishment_reason=last_replenishment_reason,
            urgency_modifier=active_policy.urgency_modifier_for_score(clamped_score),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "state": self.state,
            "last_decay_reason": self.last_decay_reason,
            "last_replenishment_reason": self.last_replenishment_reason,
            "urgency_modifier": self.urgency_modifier,
            "policy_impact": self.policy_impact,
        }


@dataclass(frozen=True)
class VitalityTransition:
    previous: VitalityState
    current: VitalityState
    applied_delta: int
    signals: tuple[VitalitySignal, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous": self.previous.to_dict(),
            "current": self.current.to_dict(),
            "applied_delta": self.applied_delta,
            "signals": [
                {
                    "reason": signal.reason,
                    "direction": signal.direction,
                    "verified": signal.verified,
                    "magnitude": signal.magnitude,
                }
                for signal in self.signals
            ],
        }


def apply_vitality_signals(
    current: VitalityState,
    signals: Iterable[VitalitySignal],
    *,
    policy: VitalityPolicy | None = None,
) -> VitalityTransition:
    active_policy = policy or VitalityPolicy()
    materialized_signals = tuple(signals)
    next_score = current.score
    last_decay_reason = current.last_decay_reason
    last_replenishment_reason = current.last_replenishment_reason

    for signal in materialized_signals:
        next_score += active_policy.delta_for(signal)
        if signal.direction == "decay":
            last_decay_reason = signal.reason
        else:
            last_replenishment_reason = signal.reason

    next_state = VitalityState.from_score(
        next_score,
        policy=active_policy,
        last_decay_reason=last_decay_reason,
        last_replenishment_reason=last_replenishment_reason,
    )
    return VitalityTransition(
        previous=current,
        current=next_state,
        applied_delta=next_state.score - current.score,
        signals=materialized_signals,
    )