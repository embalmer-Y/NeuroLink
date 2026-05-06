from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .common import PerceptionEvent, new_id, utc_now_iso


SCHEMA = """
CREATE TABLE IF NOT EXISTS perception_events (
    event_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_node TEXT,
    source_app TEXT,
    event_type TEXT NOT NULL,
    semantic_topic TEXT,
    timestamp_mono REAL,
    timestamp_wall TEXT NOT NULL,
    priority INTEGER NOT NULL,
    dedupe_key TEXT,
    causality_id TEXT,
    raw_payload_ref TEXT,
    policy_tags_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_spans (
    execution_span_id TEXT PRIMARY KEY,
    session_id TEXT,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    execution_span_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_decisions (
    policy_decision_id TEXT PRIMARY KEY,
    execution_span_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_candidates (
    memory_candidate_id TEXT PRIMARY KEY,
    execution_span_id TEXT NOT NULL,
    semantic_topic TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS long_term_memories (
    memory_id TEXT PRIMARY KEY,
    source_execution_span_id TEXT NOT NULL,
    semantic_topic TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_results (
    tool_result_id TEXT PRIMARY KEY,
    execution_span_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    approval_request_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_execution_span_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    approval_decision_id TEXT PRIMARY KEY,
    approval_request_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    audit_id TEXT PRIMARY KEY,
    execution_span_id TEXT NOT NULL,
    session_id TEXT,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class CoreDataStore:
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._ensure_optional_columns()
        self._conn.commit()

    def _ensure_optional_columns(self) -> None:
        self._ensure_column("execution_spans", "session_id", "TEXT")
        self._ensure_column("audit_records", "session_id", "TEXT")

    def _ensure_column(self, table_name: str, column_name: str, column_type: str) -> None:
        rows = self._conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {row["name"] for row in rows}
        if column_name in existing:
            return
        self._conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )

    def close(self) -> None:
        self._conn.close()

    def persist_event(self, event: PerceptionEvent) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO perception_events (
                event_id, source_kind, source_node, source_app, event_type,
                semantic_topic, timestamp_mono, timestamp_wall, priority,
                dedupe_key, causality_id, raw_payload_ref, policy_tags_json,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.source_kind,
                event.source_node,
                event.source_app,
                event.event_type,
                event.semantic_topic,
                event.timestamp_mono,
                event.timestamp_wall,
                event.priority,
                event.dedupe_key,
                event.causality_id,
                event.raw_payload_ref,
                json.dumps(list(event.policy_tags), sort_keys=True),
                json.dumps(event.payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()

    def persist_execution_span(
        self,
        execution_span_id: str,
        status: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO execution_spans (
                execution_span_id, session_id, status, payload_json, started_at, completed_at
            ) VALUES (?, ?, ?, ?, COALESCE((SELECT started_at FROM execution_spans WHERE execution_span_id = ?), ?), ?)
            """,
            (
                execution_span_id,
                session_id,
                status,
                json.dumps(payload, sort_keys=True),
                execution_span_id,
                utc_now_iso(),
                utc_now_iso() if status != "running" else None,
            ),
        )
        self._conn.commit()

    def persist_fact(
        self,
        execution_span_id: str,
        fact_type: str,
        subject: str,
        payload: dict[str, Any],
    ) -> str:
        fact_id = new_id("fact")
        self._conn.execute(
            """
            INSERT INTO facts (
                fact_id, execution_span_id, fact_type, subject, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fact_id,
                execution_span_id,
                fact_type,
                subject,
                json.dumps(payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()
        return fact_id

    def persist_policy_decision(
        self,
        execution_span_id: str,
        tool_name: str,
        decision: dict[str, Any],
    ) -> str:
        policy_decision_id = new_id("policy")
        self._conn.execute(
            """
            INSERT INTO policy_decisions (
                policy_decision_id, execution_span_id, tool_name, allowed,
                reason, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy_decision_id,
                execution_span_id,
                tool_name,
                1 if bool(decision.get("allowed", False)) else 0,
                str(decision.get("reason") or ""),
                json.dumps(decision, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()
        return policy_decision_id

    def persist_memory_candidate(
        self,
        execution_span_id: str,
        semantic_topic: str,
        payload: dict[str, Any],
    ) -> str:
        memory_candidate_id = new_id("memcand")
        self._conn.execute(
            """
            INSERT INTO memory_candidates (
                memory_candidate_id, execution_span_id, semantic_topic,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                memory_candidate_id,
                execution_span_id,
                semantic_topic,
                json.dumps(payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()
        return memory_candidate_id

    def persist_tool_result(
        self,
        tool_result_id: str,
        execution_span_id: str,
        tool_name: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO tool_results (
                tool_result_id, execution_span_id, tool_name, status,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tool_result_id,
                execution_span_id,
                tool_name,
                status,
                json.dumps(payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()

    def persist_audit_record(
        self,
        audit_id: str,
        execution_span_id: str,
        status: str,
        payload: dict[str, Any],
        session_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_records (
                audit_id, execution_span_id, session_id, status, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                execution_span_id,
                session_id,
                status,
                json.dumps(payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()

    def persist_approval_request(
        self,
        session_id: str,
        source_execution_span_id: str,
        tool_name: str,
        status: str,
        payload: dict[str, Any],
        approval_request_id: str | None = None,
    ) -> str:
        resolved_approval_request_id = approval_request_id or new_id("approval")
        timestamp = utc_now_iso()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO approval_requests (
                approval_request_id, session_id, source_execution_span_id,
                tool_name, status, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM approval_requests WHERE approval_request_id = ?), ?), ?)
            """,
            (
                resolved_approval_request_id,
                session_id,
                source_execution_span_id,
                tool_name,
                status,
                json.dumps(payload, sort_keys=True),
                resolved_approval_request_id,
                timestamp,
                timestamp,
            ),
        )
        self._conn.commit()
        return resolved_approval_request_id

    def persist_approval_decision(
        self,
        approval_request_id: str,
        session_id: str,
        decision: str,
        payload: dict[str, Any],
    ) -> str:
        approval_decision_id = new_id("approvaldec")
        self._conn.execute(
            """
            INSERT INTO approval_decisions (
                approval_decision_id, approval_request_id, session_id,
                decision, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                approval_decision_id,
                approval_request_id,
                session_id,
                decision,
                json.dumps(payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()
        return approval_decision_id

    def count(self, table_name: str) -> int:
        if table_name not in {
            "perception_events",
            "execution_spans",
            "facts",
            "policy_decisions",
            "memory_candidates",
            "long_term_memories",
            "tool_results",
            "approval_requests",
            "approval_decisions",
            "audit_records",
        }:
            raise ValueError(f"unsupported table: {table_name}")
        row = self._conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"])

    def persist_long_term_memory(
        self,
        source_execution_span_id: str,
        semantic_topic: str,
        payload: dict[str, Any],
    ) -> str:
        memory_id = new_id("memory")
        self._conn.execute(
            """
            INSERT INTO long_term_memories (
                memory_id, source_execution_span_id, semantic_topic,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                source_execution_span_id,
                semantic_topic,
                json.dumps(payload, sort_keys=True),
                utc_now_iso(),
            ),
        )
        self._conn.commit()
        return memory_id

    def get_policy_decisions(self, execution_span_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM policy_decisions WHERE execution_span_id = ? ORDER BY created_at",
            (execution_span_id,),
        ).fetchall()
        return [
            {
                "policy_decision_id": row["policy_decision_id"],
                "execution_span_id": row["execution_span_id"],
                "tool_name": row["tool_name"],
                "allowed": bool(row["allowed"]),
                "reason": row["reason"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_execution_span(self, execution_span_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM execution_spans WHERE execution_span_id = ?",
            (execution_span_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "execution_span_id": row["execution_span_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }

    def get_execution_spans_for_session(
        self,
        session_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM execution_spans
            WHERE session_id = ?
            ORDER BY started_at DESC, execution_span_id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            {
                "execution_span_id": row["execution_span_id"],
                "session_id": row["session_id"],
                "status": row["status"],
                "payload": json.loads(row["payload_json"]),
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
            }
            for row in rows
        ]

    def get_approval_request(self, approval_request_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM approval_requests WHERE approval_request_id = ?",
            (approval_request_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "approval_request_id": row["approval_request_id"],
            "session_id": row["session_id"],
            "source_execution_span_id": row["source_execution_span_id"],
            "tool_name": row["tool_name"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_approval_requests(
        self,
        *,
        session_id: str | None = None,
        source_execution_span_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM approval_requests WHERE 1 = 1"
        params: list[Any] = []
        if session_id is not None:
            sql += " AND session_id = ?"
            params.append(session_id)
        if source_execution_span_id is not None:
            sql += " AND source_execution_span_id = ?"
            params.append(source_execution_span_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC, approval_request_id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "approval_request_id": row["approval_request_id"],
                "session_id": row["session_id"],
                "source_execution_span_id": row["source_execution_span_id"],
                "tool_name": row["tool_name"],
                "status": row["status"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_approval_decisions(
        self,
        approval_request_id: str,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM approval_decisions WHERE approval_request_id = ? ORDER BY created_at",
            (approval_request_id,),
        ).fetchall()
        return [
            {
                "approval_decision_id": row["approval_decision_id"],
                "approval_request_id": row["approval_request_id"],
                "session_id": row["session_id"],
                "decision": row["decision"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_facts(
        self,
        execution_span_id: str,
        fact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM facts WHERE execution_span_id = ?"
        params: list[Any] = [execution_span_id]
        if fact_type:
            sql += " AND fact_type = ?"
            params.append(fact_type)
        sql += " ORDER BY created_at"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "fact_id": row["fact_id"],
                "execution_span_id": row["execution_span_id"],
                "fact_type": row["fact_type"],
                "subject": row["subject"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_memory_candidates(self, execution_span_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM memory_candidates WHERE execution_span_id = ? ORDER BY created_at",
            (execution_span_id,),
        ).fetchall()
        return [
            {
                "memory_candidate_id": row["memory_candidate_id"],
                "execution_span_id": row["execution_span_id"],
                "semantic_topic": row["semantic_topic"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_long_term_memories(
        self,
        *,
        source_execution_span_id: str | None = None,
        semantic_topic: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM long_term_memories WHERE 1 = 1"
        params: list[Any] = []
        if source_execution_span_id is not None:
            sql += " AND source_execution_span_id = ?"
            params.append(source_execution_span_id)
        if semantic_topic is not None:
            sql += " AND semantic_topic = ?"
            params.append(semantic_topic)
        sql += " ORDER BY created_at DESC, memory_id DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "memory_id": row["memory_id"],
                "source_execution_span_id": row["source_execution_span_id"],
                "semantic_topic": row["semantic_topic"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_audit_record(self, audit_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM audit_records WHERE audit_id = ?",
            (audit_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "audit_id": row["audit_id"],
            "execution_span_id": row["execution_span_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    def build_execution_evidence(
        self,
        execution_span_id: str,
        audit_id: str,
    ) -> dict[str, Any]:
        return {
            "execution_span": self.get_execution_span(execution_span_id),
            "facts": self.get_facts(execution_span_id),
            "policy_decisions": self.get_policy_decisions(execution_span_id),
            "memory_candidates": self.get_memory_candidates(execution_span_id),
            "approval_requests": self.get_approval_requests(
                source_execution_span_id=execution_span_id,
                limit=20,
            ),
            "long_term_memories": self.get_long_term_memories(
                source_execution_span_id=execution_span_id,
                limit=20,
            ),
            "audit_record": self.get_audit_record(audit_id),
        }

    def query_events(self, limit: int = 100, min_priority: int = 0, topic: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM perception_events WHERE priority >= ?"
        params: list[Any] = [min_priority]
        if topic:
            sql += " AND semantic_topic = ?"
            params.append(topic)
        sql += " ORDER BY timestamp_wall DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_event_dict(row) for row in rows]

    def get_recent_topics(self, limit: int = 10) -> list[str]:
        sql = "SELECT DISTINCT semantic_topic FROM perception_events WHERE semantic_topic IS NOT NULL ORDER BY timestamp_wall DESC LIMIT ?"
        rows = self._conn.execute(sql, (limit,)).fetchall()
        return [row["semantic_topic"] for row in rows if row["semantic_topic"]]

    def get_recent_dedupe_keys(self, limit: int = 1000) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT dedupe_key
            FROM perception_events
            WHERE dedupe_key IS NOT NULL AND dedupe_key != ''
            ORDER BY timestamp_wall DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [str(row["dedupe_key"]) for row in rows if row["dedupe_key"]]

    def build_frame(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            return {}
        event_ids = tuple(e["event_id"] for e in events)
        highest_priority = max(e["priority"] for e in events)
        topics = tuple(sorted({e["semantic_topic"] for e in events if e["semantic_topic"]}))
        return {
            "frame_id": new_id("frame"),
            "event_ids": event_ids,
            "highest_priority": highest_priority,
            "topics": topics,
        }

    def _row_to_event_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        # Helper to convert DB row to event dict
        return {
            "event_id": row["event_id"],
            "source_kind": row["source_kind"],
            "source_node": row["source_node"],
            "source_app": row["source_app"],
            "event_type": row["event_type"],
            "semantic_topic": row["semantic_topic"],
            "timestamp_mono": row["timestamp_mono"],
            "timestamp_wall": row["timestamp_wall"],
            "priority": row["priority"],
            "dedupe_key": row["dedupe_key"],
            "causality_id": row["causality_id"],
            "raw_payload_ref": row["raw_payload_ref"],
            "policy_tags": tuple(json.loads(row["policy_tags_json"])),
            "payload": json.loads(row["payload_json"]),
        }
