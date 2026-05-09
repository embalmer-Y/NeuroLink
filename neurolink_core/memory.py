from __future__ import annotations

import hashlib
from importlib import import_module
from importlib.util import find_spec
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Protocol
from typing import Any
from typing import cast

from .common import PerceptionFrame
from .data import CoreDataStore


MEMORY_GOVERNANCE_SCHEMA_VERSION = "1.2.5-memory-governance-v1"


def _candidate_confidence(priority: int) -> float:
    if priority <= 0:
        return 0.2
    return round(min(1.0, max(0.2, priority / 100.0)), 3)


def _utc_after_days(days: int) -> str:
    return (
        datetime.now(timezone.utc) + timedelta(days=days)
    ).isoformat().replace("+00:00", "Z")


def _retention_policy_for_topic(semantic_topic: str) -> tuple[str, int]:
    if semantic_topic.startswith("user.input"):
        return ("user_context", 30)
    if semantic_topic.startswith("unit.callback"):
        return ("operational_lesson", 14)
    if semantic_topic.startswith("time."):
        return ("ephemeral_telemetry", 1)
    return ("operational_context", 7)


def _candidate_dedupe_key(
    semantic_topic: str,
    source: str,
    event_ids: list[str],
) -> str:
    joined = "|".join([semantic_topic, source, *sorted(event_ids)])
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"memcand:{digest[:16]}"


def _governed_candidate(
    *,
    semantic_topic: str,
    source: str,
    event_ids: list[str],
    priority: int,
    source_fact_refs: list[str] | None = None,
    memory_backend: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    dedupe_key = _candidate_dedupe_key(semantic_topic, source, event_ids)
    candidate: dict[str, Any] = {
        "semantic_topic": semantic_topic,
        "source": source,
        "event_ids": list(event_ids),
        "priority": priority,
        "candidate_dedupe_key": dedupe_key,
        "source_event_refs": list(event_ids),
        "memory_governance": {
            "schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "lifecycle_state": "proposed",
            "decision_reason": "frame_topic_candidate_detected",
            "confidence": _candidate_confidence(priority),
            "confidence_source": "frame_priority",
            "dedupe_key": dedupe_key,
            "source_event_refs": list(event_ids),
            "source_fact_refs": list(source_fact_refs or []),
            "source_fact_ref_count": len(source_fact_refs or []),
            "review_mode": "deterministic_auto_candidate",
            "lifecycle_history": ["proposed"],
        },
    }
    if memory_backend is not None:
        candidate["memory_backend"] = memory_backend
        candidate["memory_governance"]["memory_backend"] = memory_backend
    if user_id is not None:
        candidate["user_id"] = user_id
    if agent_id is not None:
        candidate["agent_id"] = agent_id
    return candidate


def _screen_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate)
    governance = dict(payload.get("memory_governance") or {})
    semantic_topic = str(payload.get("semantic_topic") or "unknown")
    source = str(payload.get("source") or "unknown")
    event_ids = list(payload.get("event_ids") or [])
    priority = int(payload.get("priority") or 0)
    dedupe_key = str(
        governance.get("dedupe_key")
        or payload.get("candidate_dedupe_key")
        or _candidate_dedupe_key(semantic_topic, source, event_ids)
    )
    source_fact_refs = list(
        governance.get("source_fact_refs") or payload.get("source_fact_refs") or []
    )
    retention_class, retention_ttl_days = _retention_policy_for_topic(semantic_topic)
    lifecycle_history = list(governance.get("lifecycle_history") or ["proposed"])
    if "screened" not in lifecycle_history:
        lifecycle_history.append("screened")
    if retention_class == "ephemeral_telemetry":
        lifecycle_state = "rejected"
        decision_reason = "ephemeral_telemetry_not_retained"
    elif priority < 10:
        lifecycle_state = "rejected"
        decision_reason = "candidate_confidence_below_threshold"
    else:
        lifecycle_state = "accepted"
        decision_reason = "deterministic_candidate_accepted"
    if lifecycle_state not in lifecycle_history:
        lifecycle_history.append(lifecycle_state)
    governance.update(
        {
            "schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "lifecycle_state": lifecycle_state,
            "decision_reason": decision_reason,
            "screening_reason": decision_reason,
            "confidence": _candidate_confidence(priority),
            "confidence_source": "frame_priority",
            "dedupe_key": dedupe_key,
            "source_event_refs": list(event_ids),
            "source_fact_refs": source_fact_refs,
            "source_fact_ref_count": len(source_fact_refs),
            "review_mode": "deterministic_auto_candidate",
            "retention_class": retention_class,
            "retention_ttl_days": retention_ttl_days,
            "retention_expires_at": _utc_after_days(retention_ttl_days),
            "commit_eligible": lifecycle_state == "accepted",
            "lifecycle_history": lifecycle_history,
        }
    )
    if lifecycle_state == "accepted":
        governance["accepted_at"] = governance.get("accepted_at") or _utc_after_days(0)
    else:
        governance["rejected_at"] = governance.get("rejected_at") or _utc_after_days(0)
    payload["candidate_dedupe_key"] = dedupe_key
    payload["source_event_refs"] = list(event_ids)
    payload["source_fact_refs"] = source_fact_refs
    payload["memory_governance"] = governance
    return payload


def _committed_memory_payload(
    candidate: dict[str, Any],
    *,
    commit_backend: str,
    commit_reason: str,
    external_memory_id: str | None = None,
    sidecar_status: str | None = None,
) -> dict[str, Any]:
    payload = dict(candidate)
    governance = dict(payload.get("memory_governance") or {})
    lifecycle_history = list(governance.get("lifecycle_history") or [])
    if "committed" not in lifecycle_history:
        lifecycle_history.append("committed")
    governance.update(
        {
            "schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "lifecycle_state": "committed",
            "decision_reason": commit_reason,
            "commit_backend": commit_backend,
            "committed_at": _utc_after_days(0),
            "lifecycle_history": lifecycle_history,
        }
    )
    if external_memory_id:
        governance["external_memory_id"] = external_memory_id
    if sidecar_status:
        governance["sidecar_status"] = sidecar_status
    payload["memory_governance"] = governance
    if external_memory_id:
        payload["external_memory_id"] = external_memory_id
    if sidecar_status:
        payload["sidecar_status"] = sidecar_status
    return payload


def _candidate_commit_eligible(candidate: dict[str, Any]) -> bool:
    governance = dict(candidate.get("memory_governance") or {})
    return bool(governance.get("commit_eligible", False)) or str(
        governance.get("lifecycle_state") or ""
    ) == "accepted"


def _external_memory_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    governance = dict(candidate.get("memory_governance") or {})
    return {
        "semantic_topic": str(candidate.get("semantic_topic") or "unknown"),
        "source": str(candidate.get("source") or "unknown"),
        "event_ids": list(candidate.get("event_ids") or []),
        "source_event_refs": list(governance.get("source_event_refs") or []),
        "source_fact_refs": list(governance.get("source_fact_refs") or []),
        "memory_governance": {
            "schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "lifecycle_state": str(governance.get("lifecycle_state") or "unknown"),
            "decision_reason": str(governance.get("decision_reason") or ""),
            "confidence": governance.get("confidence"),
            "confidence_source": str(governance.get("confidence_source") or ""),
            "dedupe_key": str(governance.get("dedupe_key") or ""),
            "retention_class": str(governance.get("retention_class") or ""),
            "retention_expires_at": str(governance.get("retention_expires_at") or ""),
            "review_mode": str(governance.get("review_mode") or ""),
        },
    }


class LongTermMemory(Protocol):
    def runtime_metadata(self) -> dict[str, Any]:
        ...

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        ...

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        ...

    def screen_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ...


class FakeLongTermMemory:
    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "backend_kind": "fake",
            "backend_runtime": "local_deterministic_empty",
            "governance_schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "requires_external_service": False,
            "fallback_active": False,
            "can_execute_tools_directly": False,
        }

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        del frame
        return []

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            _governed_candidate(
                semantic_topic=topic,
                source="no_model_perception_frame",
                event_ids=list(frame.event_ids),
                priority=frame.highest_priority,
            )
            for topic in frame.topics
        ]

    def screen_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_screen_candidate(candidate) for candidate in candidates]


class LocalCandidateBackedMemory:
    def __init__(self, data_store: CoreDataStore) -> None:
        self.data_store = data_store

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "backend_kind": "local_sqlite",
            "backend_runtime": "sqlite_candidate_store",
            "governance_schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "requires_external_service": False,
            "fallback_active": False,
            "can_execute_tools_directly": False,
        }

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        memory_items: list[dict[str, Any]] = []
        for topic in frame.topics:
            memory_items.extend(
                self.data_store.get_long_term_memories(
                    semantic_topic=topic,
                    include_retired=False,
                    limit=5,
                )
            )
        return memory_items

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            _governed_candidate(
                semantic_topic=topic,
                source="local_candidate_backed_memory",
                event_ids=list(frame.event_ids),
                priority=frame.highest_priority,
                memory_backend="local_sqlite",
            )
            for topic in frame.topics
        ]

    def screen_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_screen_candidate(candidate) for candidate in candidates]

    def commit_candidates(
        self,
        execution_span_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        memory_ids: list[str] = []
        committed_dedupe_keys: set[str] = set()
        for candidate in candidates:
            candidate_payload = dict(candidate)
            governance = dict(candidate_payload.get("memory_governance") or {})
            if str(governance.get("lifecycle_state") or "") in {"", "proposed"}:
                candidate_payload = _screen_candidate(candidate_payload)
            if not _candidate_commit_eligible(candidate_payload):
                continue
            governance = dict(candidate_payload.get("memory_governance") or {})
            dedupe_key = str(
                governance.get("dedupe_key")
                or candidate_payload.get("candidate_dedupe_key")
                or _candidate_dedupe_key(
                    str(candidate_payload.get("semantic_topic") or "unknown"),
                    str(candidate_payload.get("source") or "unknown"),
                    list(candidate_payload.get("event_ids") or []),
                )
            )
            if dedupe_key in committed_dedupe_keys:
                continue
            committed_dedupe_keys.add(dedupe_key)
            memory_ids.append(
                self.data_store.persist_long_term_memory(
                    execution_span_id,
                    str(candidate_payload.get("semantic_topic") or "unknown"),
                    _committed_memory_payload(
                        candidate_payload,
                        commit_backend="local_sqlite",
                        commit_reason="auto_commit_local_sqlite",
                    ),
                )
            )
        return memory_ids

    def retire_expired_memories(self, *, reference_time: str | None = None) -> list[str]:
        return self.data_store.retire_expired_long_term_memories(
            reference_time=reference_time
        )


class Mem0SidecarMemory:
    def __init__(
        self,
        data_store: CoreDataStore,
        *,
        client: Any | None = None,
        user_id: str = "neurolink-core",
        agent_id: str = "neurolink-rational",
        package_available: bool | None = None,
        unavailable_reason: str = "",
    ) -> None:
        self.data_store = data_store
        self.client = client
        self.user_id = user_id
        self.agent_id = agent_id
        self.package_available = bool(client) if package_available is None else package_available
        self.unavailable_reason = unavailable_reason
        self.local_fallback = LocalCandidateBackedMemory(data_store)
        self.last_lookup_status = "not_requested"
        self.last_commit_status = "not_requested"
        self.last_sidecar_memory_ids: list[str] = []

    def runtime_metadata(self) -> dict[str, Any]:
        fallback_active = self.client is None
        return {
            "backend_kind": "mem0_sidecar",
            "backend_runtime": "mem0_with_sqlite_mirror",
            "governance_schema_version": MEMORY_GOVERNANCE_SCHEMA_VERSION,
            "requires_external_service": True,
            "package_available": self.package_available,
            "sidecar_configured": self.client is not None,
            "fallback_backend": "local_sqlite",
            "fallback_active": fallback_active,
            "unavailable_reason": self.unavailable_reason if fallback_active else "",
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "last_lookup_status": self.last_lookup_status,
            "last_commit_status": self.last_commit_status,
            "sidecar_memory_ids": list(self.last_sidecar_memory_ids),
            "can_execute_tools_directly": False,
        }

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        local_items = self.local_fallback.lookup(frame)
        if self.client is None:
            self.last_lookup_status = "fallback_local_sqlite"
            return local_items
        query = " ".join(frame.topics) or frame.frame_id
        try:
            raw_results = self._search_sidecar(query)
        except Exception as exc:
            self.last_lookup_status = f"fallback_local_sqlite_after_{exc.__class__.__name__}"
            return local_items
        self.last_lookup_status = "sidecar_and_local_sqlite"
        return [*self._normalize_search_results(raw_results), *local_items]

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            _governed_candidate(
                semantic_topic=topic,
                source="mem0_sidecar_memory",
                event_ids=list(frame.event_ids),
                priority=frame.highest_priority,
                memory_backend="mem0_sidecar",
                user_id=self.user_id,
                agent_id=self.agent_id,
            )
            for topic in frame.topics
        ]

    def screen_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_screen_candidate(candidate) for candidate in candidates]

    def commit_candidates(
        self,
        execution_span_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        sidecar_memory_ids: list[str] = []
        committed_candidates: list[dict[str, Any]] = []
        committed_dedupe_keys: set[str] = set()
        if self.client is not None:
            for candidate in candidates:
                candidate_payload = dict(candidate)
                governance = dict(candidate_payload.get("memory_governance") or {})
                if str(governance.get("lifecycle_state") or "") in {"", "proposed"}:
                    candidate_payload = _screen_candidate(candidate_payload)
                if not _candidate_commit_eligible(candidate_payload):
                    continue
                governance = dict(candidate_payload.get("memory_governance") or {})
                dedupe_key = str(
                    governance.get("dedupe_key")
                    or candidate_payload.get("candidate_dedupe_key")
                    or _candidate_dedupe_key(
                        str(candidate_payload.get("semantic_topic") or "unknown"),
                        str(candidate_payload.get("source") or "unknown"),
                        list(candidate_payload.get("event_ids") or []),
                    )
                )
                if dedupe_key in committed_dedupe_keys:
                    continue
                try:
                    result = self._add_sidecar_memory(execution_span_id, candidate_payload)
                except Exception as exc:
                    self.last_commit_status = f"sqlite_mirror_after_{exc.__class__.__name__}"
                    sidecar_memory_ids = []
                    committed_candidates = []
                    break
                sidecar_memory_id = self._extract_sidecar_memory_id(result)
                committed_dedupe_keys.add(dedupe_key)
                if sidecar_memory_id:
                    sidecar_memory_ids.append(sidecar_memory_id)
                committed_candidates.append(
                    _committed_memory_payload(
                        candidate_payload,
                        commit_backend="mem0_sidecar",
                        commit_reason="auto_commit_mem0_sidecar",
                        external_memory_id=sidecar_memory_id,
                        sidecar_status="sidecar_committed",
                    )
                )
            else:
                self.last_commit_status = "sidecar_and_sqlite_mirror"
        else:
            self.last_commit_status = "fallback_local_sqlite"
            for candidate in candidates:
                candidate_payload = dict(candidate)
                governance = dict(candidate_payload.get("memory_governance") or {})
                if str(governance.get("lifecycle_state") or "") in {"", "proposed"}:
                    candidate_payload = _screen_candidate(candidate_payload)
                if not _candidate_commit_eligible(candidate_payload):
                    continue
                governance = dict(candidate_payload.get("memory_governance") or {})
                dedupe_key = str(
                    governance.get("dedupe_key")
                    or candidate_payload.get("candidate_dedupe_key")
                    or _candidate_dedupe_key(
                        str(candidate_payload.get("semantic_topic") or "unknown"),
                        str(candidate_payload.get("source") or "unknown"),
                        list(candidate_payload.get("event_ids") or []),
                    )
                )
                if dedupe_key in committed_dedupe_keys:
                    continue
                committed_dedupe_keys.add(dedupe_key)
                committed_candidates.append(
                    _committed_memory_payload(
                        candidate_payload,
                        commit_backend="local_sqlite_fallback",
                        commit_reason="auto_commit_mem0_fallback_local_sqlite",
                        sidecar_status="fallback_local_sqlite",
                    )
                )

        self.last_sidecar_memory_ids = sidecar_memory_ids
        mirrored_candidates: list[dict[str, Any]] = []
        if committed_candidates:
            for candidate in committed_candidates:
                mirrored_candidate = dict(candidate)
                mirrored_candidate["memory_backend"] = "mem0_sidecar"
                mirrored_candidate["sidecar_status"] = self.last_commit_status
                mirrored_candidate["sidecar_memory_ids"] = list(sidecar_memory_ids)
                governance = dict(mirrored_candidate.get("memory_governance") or {})
                governance["mirror_backend"] = "local_sqlite"
                governance["mirror_status"] = self.last_commit_status
                governance["sqlite_mirror_status"] = self.last_commit_status
                governance["sidecar_memory_ids"] = list(sidecar_memory_ids)
                governance["fallback_continuity"] = self.last_commit_status.startswith(
                    "fallback_"
                )
                mirrored_candidate["memory_governance"] = governance
                mirrored_candidates.append(mirrored_candidate)
        return self.local_fallback.commit_candidates(execution_span_id, mirrored_candidates)

    def retire_expired_memories(self, *, reference_time: str | None = None) -> list[str]:
        return self.data_store.retire_expired_long_term_memories(
            reference_time=reference_time
        )

    def _search_sidecar(self, query: str) -> Any:
        search = getattr(self.client, "search")
        try:
            return search(query=query, user_id=self.user_id, limit=5)
        except TypeError:
            return search(query, user_id=self.user_id, limit=5)

    def _add_sidecar_memory(self, execution_span_id: str, candidate: dict[str, Any]) -> Any:
        add = getattr(self.client, "add")
        metadata: dict[str, Any] = {
            "source_execution_span_id": execution_span_id,
            "semantic_topic": candidate.get("semantic_topic"),
            "event_ids": candidate.get("event_ids", []),
            "agent_id": self.agent_id,
        }
        message = json.dumps(_external_memory_payload(candidate), sort_keys=True)
        try:
            return add(message, user_id=self.user_id, metadata=metadata)
        except TypeError:
            return add(messages=message, user_id=self.user_id, metadata=metadata)

    @staticmethod
    def _normalize_search_results(raw_results: Any) -> list[dict[str, Any]]:
        if isinstance(raw_results, dict):
            raw_results_dict = cast(dict[str, Any], raw_results)
            candidate_results: Any = cast(
                Any,
                raw_results_dict.get("results") or raw_results_dict.get("memories") or [],
            )
        else:
            candidate_results = raw_results
        if not isinstance(candidate_results, list):
            return []
        candidate_items = cast(list[Any], candidate_results)
        normalized: list[dict[str, Any]] = []
        for item in candidate_items:
            if isinstance(item, dict):
                payload = cast(dict[str, Any], item)
            else:
                payload = {"memory": str(item)}
            payload.setdefault("source", "mem0_sidecar")
            normalized.append(payload)
        return normalized

    @staticmethod
    def _extract_sidecar_memory_id(result: Any) -> str | None:
        if isinstance(result, dict):
            result_dict = cast(dict[str, Any], result)
            for key in ("id", "memory_id", "memoryId"):
                value = result_dict.get(key)
                if isinstance(value, str) and value:
                    return value
            results = result_dict.get("results")
            if isinstance(results, list) and results and isinstance(results[0], dict):
                first_result = cast(dict[str, Any], results[0])
                value = first_result.get("id") or first_result.get("memory_id")
                if isinstance(value, str) and value:
                    return value
        return None


def build_memory_backend(
    memory_backend: str,
    data_store: CoreDataStore,
    *,
    mem0_client: Any | None = None,
    env: dict[str, str] | None = None,
) -> LongTermMemory:
    if memory_backend == "fake":
        return FakeLongTermMemory()
    if memory_backend == "local":
        return LocalCandidateBackedMemory(data_store)
    if memory_backend != "mem0":
        raise ValueError("memory_backend_must_be_fake_local_or_mem0")

    resolved_env = env if env is not None else os.environ
    user_id = resolved_env.get("MEM0_USER_ID", "neurolink-core")
    agent_id = resolved_env.get("MEM0_AGENT_ID", "neurolink-rational")
    package_available = find_spec("mem0") is not None or find_spec("mem0ai") is not None
    if mem0_client is not None:
        return Mem0SidecarMemory(
            data_store,
            client=mem0_client,
            user_id=user_id,
            agent_id=agent_id,
            package_available=package_available,
        )
    if not package_available:
        return Mem0SidecarMemory(
            data_store,
            user_id=user_id,
            agent_id=agent_id,
            package_available=False,
            unavailable_reason="mem0_package_not_installed",
        )
    try:
        mem0_module = import_module("mem0")
        memory_factory = getattr(mem0_module, "Memory")
        config_json = resolved_env.get("MEM0_CONFIG_JSON")
        if config_json and hasattr(memory_factory, "from_config"):
            client = memory_factory.from_config(json.loads(config_json))
        else:
            client = memory_factory()
    except Exception as exc:
        return Mem0SidecarMemory(
            data_store,
            user_id=user_id,
            agent_id=agent_id,
            package_available=True,
            unavailable_reason=f"mem0_client_init_failed_{exc.__class__.__name__}",
        )
    return Mem0SidecarMemory(
        data_store,
        client=client,
        user_id=user_id,
        agent_id=agent_id,
        package_available=True,
    )
