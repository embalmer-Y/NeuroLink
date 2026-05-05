from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
import json
import os
from typing import Protocol
from typing import Any

from .common import PerceptionFrame
from .data import CoreDataStore


class LongTermMemory(Protocol):
    def runtime_metadata(self) -> dict[str, Any]:
        ...

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        ...

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        ...


class FakeLongTermMemory:
    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "backend_kind": "fake",
            "backend_runtime": "local_deterministic_empty",
            "requires_external_service": False,
            "fallback_active": False,
            "can_execute_tools_directly": False,
        }

    def lookup(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        del frame
        return []

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            {
                "semantic_topic": topic,
                "source": "no_model_perception_frame",
                "event_ids": list(frame.event_ids),
                "priority": frame.highest_priority,
            }
            for topic in frame.topics
        ]


class LocalCandidateBackedMemory:
    def __init__(self, data_store: CoreDataStore) -> None:
        self.data_store = data_store

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "backend_kind": "local_sqlite",
            "backend_runtime": "sqlite_candidate_store",
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
                    limit=5,
                )
            )
        return memory_items

    def propose_candidates(self, frame: PerceptionFrame) -> list[dict[str, Any]]:
        return [
            {
                "semantic_topic": topic,
                "source": "local_candidate_backed_memory",
                "event_ids": list(frame.event_ids),
                "priority": frame.highest_priority,
            }
            for topic in frame.topics
        ]

    def commit_candidates(
        self,
        execution_span_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        memory_ids: list[str] = []
        for candidate in candidates:
            memory_ids.append(
                self.data_store.persist_long_term_memory(
                    execution_span_id,
                    str(candidate.get("semantic_topic") or "unknown"),
                    dict(candidate),
                )
            )
        return memory_ids


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
            {
                "semantic_topic": topic,
                "source": "mem0_sidecar_memory",
                "event_ids": list(frame.event_ids),
                "priority": frame.highest_priority,
                "memory_backend": "mem0_sidecar",
                "user_id": self.user_id,
                "agent_id": self.agent_id,
            }
            for topic in frame.topics
        ]

    def commit_candidates(
        self,
        execution_span_id: str,
        candidates: list[dict[str, Any]],
    ) -> list[str]:
        sidecar_memory_ids: list[str] = []
        if self.client is not None:
            for candidate in candidates:
                try:
                    result = self._add_sidecar_memory(execution_span_id, candidate)
                except Exception as exc:
                    self.last_commit_status = f"sqlite_mirror_after_{exc.__class__.__name__}"
                    sidecar_memory_ids = []
                    break
                sidecar_memory_id = self._extract_sidecar_memory_id(result)
                if sidecar_memory_id:
                    sidecar_memory_ids.append(sidecar_memory_id)
            else:
                self.last_commit_status = "sidecar_and_sqlite_mirror"
        else:
            self.last_commit_status = "fallback_local_sqlite"

        self.last_sidecar_memory_ids = sidecar_memory_ids
        mirrored_candidates = []
        for candidate in candidates:
            mirrored_candidate = dict(candidate)
            mirrored_candidate["memory_backend"] = "mem0_sidecar"
            mirrored_candidate["sidecar_status"] = self.last_commit_status
            mirrored_candidate["sidecar_memory_ids"] = list(sidecar_memory_ids)
            mirrored_candidates.append(mirrored_candidate)
        return self.local_fallback.commit_candidates(execution_span_id, mirrored_candidates)

    def _search_sidecar(self, query: str) -> Any:
        search = getattr(self.client, "search")
        try:
            return search(query=query, user_id=self.user_id, limit=5)
        except TypeError:
            return search(query, user_id=self.user_id, limit=5)

    def _add_sidecar_memory(self, execution_span_id: str, candidate: dict[str, Any]) -> Any:
        add = getattr(self.client, "add")
        metadata = {
            "source_execution_span_id": execution_span_id,
            "semantic_topic": candidate.get("semantic_topic"),
            "event_ids": candidate.get("event_ids", []),
            "agent_id": self.agent_id,
        }
        message = json.dumps(candidate, sort_keys=True)
        try:
            return add(message, user_id=self.user_id, metadata=metadata)
        except TypeError:
            return add(messages=message, user_id=self.user_id, metadata=metadata)

    @staticmethod
    def _normalize_search_results(raw_results: Any) -> list[dict[str, Any]]:
        if isinstance(raw_results, dict):
            candidate_results = raw_results.get("results") or raw_results.get("memories") or []
        else:
            candidate_results = raw_results
        if not isinstance(candidate_results, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in candidate_results:
            if isinstance(item, dict):
                payload = dict(item)
            else:
                payload = {"memory": str(item)}
            payload.setdefault("source", "mem0_sidecar")
            normalized.append(payload)
        return normalized

    @staticmethod
    def _extract_sidecar_memory_id(result: Any) -> str | None:
        if isinstance(result, dict):
            for key in ("id", "memory_id", "memoryId"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
            results = result.get("results")
            if isinstance(results, list) and results and isinstance(results[0], dict):
                value = results[0].get("id") or results[0].get("memory_id")
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
