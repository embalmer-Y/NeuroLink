from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
from typing import Any, Iterable, cast


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, round(value, 4)))


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[Any], value or []))


PERSONA_GROWTH_RUNTIME_SOURCES = frozenset(
    {
        "social_interaction",
        "unit_event",
        "relationship_summary",
        "vitality_transition",
        "self_improvement",
    }
)


@dataclass(frozen=True)
class PersonaSeedConfig:
    persona_id: str = "affective-main"
    seed_name: str = "default"
    mood: str = "steady"
    valence: float = 0.0
    arousal: float = 0.0
    curiosity: float = 0.5
    fatigue: float = 0.0
    social_openness: float = 0.5
    vitality_summary: str = "attentive"
    relationship_style: str = "warm"
    immutable_boundaries: tuple[str, ...] = ()
    created_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PersonaSeedConfig":
        return cls(
            persona_id=str(payload.get("persona_id") or "affective-main"),
            seed_name=str(payload.get("seed_name") or "default"),
            mood=str(payload.get("mood") or "steady"),
            valence=_clamp(float(payload.get("valence", 0.0)), minimum=-1.0, maximum=1.0),
            arousal=_clamp(float(payload.get("arousal", 0.0)), minimum=0.0, maximum=1.0),
            curiosity=_clamp(float(payload.get("curiosity", 0.5)), minimum=0.0, maximum=1.0),
            fatigue=_clamp(float(payload.get("fatigue", 0.0)), minimum=0.0, maximum=1.0),
            social_openness=_clamp(
                float(payload.get("social_openness", 0.5)), minimum=0.0, maximum=1.0
            ),
            vitality_summary=str(payload.get("vitality_summary") or "attentive"),
            relationship_style=str(payload.get("relationship_style") or "warm"),
            immutable_boundaries=_string_tuple(payload.get("immutable_boundaries")),
            created_at=payload.get("created_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "seed_name": self.seed_name,
            "mood": self.mood,
            "valence": self.valence,
            "arousal": self.arousal,
            "curiosity": self.curiosity,
            "fatigue": self.fatigue,
            "social_openness": self.social_openness,
            "vitality_summary": self.vitality_summary,
            "relationship_style": self.relationship_style,
            "immutable_boundaries": list(self.immutable_boundaries),
            "created_at": self.created_at,
        }


def compute_persona_seed_fingerprint(seed_config: PersonaSeedConfig) -> str:
    return _stable_hash(seed_config.to_dict())


@dataclass(frozen=True)
class PersonaGrowthEvidence:
    event_id: str
    source: str
    reason: str
    recorded_at: str
    principal_id: str | None = None
    summary: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PersonaGrowthEvidence":
        return cls(
            event_id=str(payload.get("event_id") or ""),
            source=str(payload.get("source") or ""),
            reason=str(payload.get("reason") or ""),
            recorded_at=str(payload.get("recorded_at") or ""),
            principal_id=(
                str(payload.get("principal_id"))
                if payload.get("principal_id") is not None
                else None
            ),
            summary=str(payload.get("summary") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "reason": self.reason,
            "recorded_at": self.recorded_at,
            "principal_id": self.principal_id,
            "summary": self.summary,
        }


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
            boundaries=_string_tuple(payload.get("boundaries")),
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
    seed_config: PersonaSeedConfig | None = None
    growth_state: PersonaGrowthState | None = None
    provenance_hash: str | None = None
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
                RelationshipSummary.from_dict(cast(dict[str, Any], item))
                for item in cast(list[Any], payload.get("relationship_summaries") or [])
            ),
            seed_config=(
                PersonaSeedConfig.from_dict(cast(dict[str, Any], payload.get("seed_config") or {}))
                if payload.get("seed_config")
                else None
            ),
            growth_state=(
                PersonaGrowthState.from_dict(
                    cast(dict[str, Any], payload.get("growth_state") or {})
                )
                if payload.get("growth_state")
                else None
            ),
            provenance_hash=(
                str(payload.get("provenance_hash"))
                if payload.get("provenance_hash") is not None
                else None
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
            "seed_config": self.seed_config.to_dict() if self.seed_config else None,
            "growth_state": self.growth_state.to_dict() if self.growth_state else None,
            "provenance_hash": self.provenance_hash,
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
            "growth_state": (
                {
                    "revision": self.growth_state.revision,
                    "last_evidence_source": self.growth_state.last_evidence_source,
                    "last_evidence_reason": self.growth_state.last_evidence_reason,
                }
                if self.growth_state is not None
                else None
            ),
        }


@dataclass(frozen=True)
class PersonaGrowthState:
    persona_id: str
    seed_fingerprint: str
    revision: int = 0
    social_interaction_count: int = 0
    unit_event_count: int = 0
    relationship_summary_count: int = 0
    vitality_event_count: int = 0
    self_improvement_count: int = 0
    evidence_event_ids: tuple[str, ...] = ()
    last_evidence_source: str | None = None
    last_evidence_reason: str | None = None
    last_evidence_at: str | None = None
    provenance_hash: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PersonaGrowthState":
        return cls(
            persona_id=str(payload.get("persona_id") or "affective-main"),
            seed_fingerprint=str(payload.get("seed_fingerprint") or ""),
            revision=int(payload.get("revision") or 0),
            social_interaction_count=int(payload.get("social_interaction_count") or 0),
            unit_event_count=int(payload.get("unit_event_count") or 0),
            relationship_summary_count=int(payload.get("relationship_summary_count") or 0),
            vitality_event_count=int(payload.get("vitality_event_count") or 0),
            self_improvement_count=int(payload.get("self_improvement_count") or 0),
            evidence_event_ids=_string_tuple(payload.get("evidence_event_ids")),
            last_evidence_source=(
                str(payload.get("last_evidence_source"))
                if payload.get("last_evidence_source") is not None
                else None
            ),
            last_evidence_reason=(
                str(payload.get("last_evidence_reason"))
                if payload.get("last_evidence_reason") is not None
                else None
            ),
            last_evidence_at=(
                str(payload.get("last_evidence_at"))
                if payload.get("last_evidence_at") is not None
                else None
            ),
            provenance_hash=str(payload.get("provenance_hash") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "seed_fingerprint": self.seed_fingerprint,
            "revision": self.revision,
            "social_interaction_count": self.social_interaction_count,
            "unit_event_count": self.unit_event_count,
            "relationship_summary_count": self.relationship_summary_count,
            "vitality_event_count": self.vitality_event_count,
            "self_improvement_count": self.self_improvement_count,
            "evidence_event_ids": list(self.evidence_event_ids),
            "last_evidence_source": self.last_evidence_source,
            "last_evidence_reason": self.last_evidence_reason,
            "last_evidence_at": self.last_evidence_at,
            "provenance_hash": self.provenance_hash,
        }


def initialize_persona_state_from_seed(
    seed_config: PersonaSeedConfig,
    *,
    updated_at: str | None = None,
) -> PersonaState:
    return PersonaState(
        persona_id=seed_config.persona_id,
        mood=seed_config.mood,
        valence=seed_config.valence,
        arousal=seed_config.arousal,
        curiosity=seed_config.curiosity,
        fatigue=seed_config.fatigue,
        social_openness=seed_config.social_openness,
        vitality_summary=seed_config.vitality_summary,
        updated_at=updated_at or seed_config.created_at,
    )


def initialize_persona_growth_state(
    seed_config: PersonaSeedConfig,
) -> PersonaGrowthState:
    growth_state = PersonaGrowthState(
        persona_id=seed_config.persona_id,
        seed_fingerprint=compute_persona_seed_fingerprint(seed_config),
    )
    return replace(
        growth_state,
        provenance_hash=compute_persona_growth_provenance_hash(growth_state),
    )


def compute_persona_growth_provenance_hash(
    growth_state: PersonaGrowthState,
) -> str:
    payload = growth_state.to_dict()
    payload["provenance_hash"] = ""
    return _stable_hash(payload)


def apply_persona_growth_evidence(
    current: PersonaGrowthState,
    evidence: PersonaGrowthEvidence,
) -> PersonaGrowthState:
    if evidence.source not in PERSONA_GROWTH_RUNTIME_SOURCES:
        raise ValueError("persona_growth_requires_runtime_evidence")
    if not evidence.event_id:
        raise ValueError("persona_growth_requires_event_id")
    if evidence.event_id in current.evidence_event_ids:
        raise ValueError("persona_growth_event_already_recorded")

    increments = {
        "social_interaction": (1, 0, 0, 0, 0),
        "unit_event": (0, 1, 0, 0, 0),
        "relationship_summary": (0, 0, 1, 0, 0),
        "vitality_transition": (0, 0, 0, 1, 0),
        "self_improvement": (0, 0, 0, 0, 1),
    }
    social_delta, unit_delta, relationship_delta, vitality_delta, self_improvement_delta = increments[
        evidence.source
    ]
    updated = PersonaGrowthState(
        persona_id=current.persona_id,
        seed_fingerprint=current.seed_fingerprint,
        revision=current.revision + 1,
        social_interaction_count=current.social_interaction_count + social_delta,
        unit_event_count=current.unit_event_count + unit_delta,
        relationship_summary_count=current.relationship_summary_count + relationship_delta,
        vitality_event_count=current.vitality_event_count + vitality_delta,
        self_improvement_count=current.self_improvement_count + self_improvement_delta,
        evidence_event_ids=current.evidence_event_ids + (evidence.event_id,),
        last_evidence_source=evidence.source,
        last_evidence_reason=evidence.reason,
        last_evidence_at=evidence.recorded_at,
        provenance_hash="",
    )
    return replace(
        updated,
        provenance_hash=compute_persona_growth_provenance_hash(updated),
    )


def compute_persona_immutability_stamp(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
) -> str:
    return _stable_hash(
        {
            "seed": seed_config.to_dict(),
            "persona_state": persona_state.to_dict(),
            "growth_state": growth_state.to_dict(),
        }
    )


def persona_immutability_tampered(
    *,
    expected_stamp: str,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
) -> bool:
    return expected_stamp != compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    )


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