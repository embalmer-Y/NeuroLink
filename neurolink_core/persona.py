from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, round(value, 4)))


@dataclass(frozen=True)
class RelationshipSummary:
    principal_id: str
    trust: float = 0.5
    familiarity: float = 0.0
    preferred_address: str = ""
    boundaries: tuple[str, ...] = ()
    last_interaction_reason: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RelationshipSummary":
        return cls(
            principal_id=str(payload.get("principal_id") or "unknown"),
            trust=_clamp(float(payload.get("trust", 0.5)), minimum=0.0, maximum=1.0),
            familiarity=_clamp(
                float(payload.get("familiarity", 0.0)), minimum=0.0, maximum=1.0
            ),
            preferred_address=str(payload.get("preferred_address") or ""),
            boundaries=tuple(str(item) for item in (payload.get("boundaries") or [])),
            last_interaction_reason=payload.get("last_interaction_reason"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "trust": self.trust,
            "familiarity": self.familiarity,
            "preferred_address": self.preferred_address,
            "boundaries": list(self.boundaries),
            "last_interaction_reason": self.last_interaction_reason,
        }

    def rational_summary(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "trust": self.trust,
            "familiarity": self.familiarity,
            "last_interaction_reason": self.last_interaction_reason,
        }


@dataclass(frozen=True)
class PersonaSignal:
    reason: str
    mood: str | None = None
    valence_delta: float = 0.0
    arousal_delta: float = 0.0
    curiosity_delta: float = 0.0
    fatigue_delta: float = 0.0
    social_openness_delta: float = 0.0
    principal_id: str | None = None
    trust_delta: float = 0.0
    familiarity_delta: float = 0.0
    preferred_address: str | None = None
    boundary_note: str | None = None


@dataclass(frozen=True)
class PersonaState:
    persona_id: str
    version: int = 1
    mood: str = "steady"
    valence: float = 0.0
    arousal: float = 0.0
    curiosity: float = 0.5
    fatigue: float = 0.0
    social_openness: float = 0.5
    vitality_summary: str = "attentive"
    relationship_summaries: tuple[RelationshipSummary, ...] = field(default_factory=tuple)
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PersonaState":
        return cls(
            persona_id=str(payload.get("persona_id") or "affective-main"),
            version=int(payload.get("version") or 1),
            mood=str(payload.get("mood") or "steady"),
            valence=_clamp(float(payload.get("valence", 0.0)), minimum=-1.0, maximum=1.0),
            arousal=_clamp(float(payload.get("arousal", 0.0)), minimum=0.0, maximum=1.0),
            curiosity=_clamp(float(payload.get("curiosity", 0.5)), minimum=0.0, maximum=1.0),
            fatigue=_clamp(float(payload.get("fatigue", 0.0)), minimum=0.0, maximum=1.0),
            social_openness=_clamp(
                float(payload.get("social_openness", 0.5)), minimum=0.0, maximum=1.0
            ),
            vitality_summary=str(payload.get("vitality_summary") or "attentive"),
            relationship_summaries=tuple(
                RelationshipSummary.from_dict(item)
                for item in (payload.get("relationship_summaries") or [])
            ),
            updated_at=payload.get("updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "version": self.version,
            "mood": self.mood,
            "valence": self.valence,
            "arousal": self.arousal,
            "curiosity": self.curiosity,
            "fatigue": self.fatigue,
            "social_openness": self.social_openness,
            "vitality_summary": self.vitality_summary,
            "relationship_summaries": [item.to_dict() for item in self.relationship_summaries],
            "updated_at": self.updated_at,
        }

    def rational_summary(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "mood": self.mood,
            "valence": self.valence,
            "arousal": self.arousal,
            "curiosity": self.curiosity,
            "fatigue": self.fatigue,
            "social_openness": self.social_openness,
            "vitality_summary": self.vitality_summary,
            "relationship_summaries": [
                item.rational_summary() for item in self.relationship_summaries
            ],
        }


def apply_persona_signals(
    current: PersonaState,
    signals: Iterable[PersonaSignal],
    *,
    vitality_summary: str | None = None,
    updated_at: str | None = None,
) -> PersonaState:
    mood = current.mood
    valence = current.valence
    arousal = current.arousal
    curiosity = current.curiosity
    fatigue = current.fatigue
    social_openness = current.social_openness
    relationships = {item.principal_id: item for item in current.relationship_summaries}

    for signal in signals:
        if signal.mood:
            mood = signal.mood
        valence = _clamp(valence + signal.valence_delta, minimum=-1.0, maximum=1.0)
        arousal = _clamp(arousal + signal.arousal_delta, minimum=0.0, maximum=1.0)
        curiosity = _clamp(curiosity + signal.curiosity_delta, minimum=0.0, maximum=1.0)
        fatigue = _clamp(fatigue + signal.fatigue_delta, minimum=0.0, maximum=1.0)
        social_openness = _clamp(
            social_openness + signal.social_openness_delta,
            minimum=0.0,
            maximum=1.0,
        )
        if signal.principal_id:
            previous = relationships.get(signal.principal_id) or RelationshipSummary(
                principal_id=signal.principal_id
            )
            boundaries = list(previous.boundaries)
            if signal.boundary_note and signal.boundary_note not in boundaries:
                boundaries.append(signal.boundary_note)
            relationships[signal.principal_id] = RelationshipSummary(
                principal_id=signal.principal_id,
                trust=_clamp(
                    previous.trust + signal.trust_delta,
                    minimum=0.0,
                    maximum=1.0,
                ),
                familiarity=_clamp(
                    previous.familiarity + signal.familiarity_delta,
                    minimum=0.0,
                    maximum=1.0,
                ),
                preferred_address=signal.preferred_address or previous.preferred_address,
                boundaries=tuple(boundaries),
                last_interaction_reason=signal.reason,
            )

    return PersonaState(
        persona_id=current.persona_id,
        version=current.version,
        mood=mood,
        valence=valence,
        arousal=arousal,
        curiosity=curiosity,
        fatigue=fatigue,
        social_openness=social_openness,
        vitality_summary=vitality_summary or current.vitality_summary,
        relationship_summaries=tuple(sorted(relationships.values(), key=lambda item: item.principal_id)),
        updated_at=updated_at or current.updated_at,
    )


def redact_relationships(
    current: PersonaState,
    principal_ids: Iterable[str],
    *,
    updated_at: str | None = None,
) -> PersonaState:
    removed = set(principal_ids)
    return PersonaState(
        persona_id=current.persona_id,
        version=current.version,
        mood=current.mood,
        valence=current.valence,
        arousal=current.arousal,
        curiosity=current.curiosity,
        fatigue=current.fatigue,
        social_openness=current.social_openness,
        vitality_summary=current.vitality_summary,
        relationship_summaries=tuple(
            item for item in current.relationship_summaries if item.principal_id not in removed
        ),
        updated_at=updated_at or current.updated_at,
    )