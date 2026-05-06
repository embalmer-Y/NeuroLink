from __future__ import annotations

from pathlib import Path
from typing import Any

import neuro_protocol as protocol


CANONICAL_SKILL_RELATIVE_PATH = "neuro_cli/skill/SKILL.md"
PROJECT_SHARED_SKILL_RELATIVE_PATH = ".github/skills/neuro-cli/SKILL.md"
PROJECT_SKILL_RELATIVE_PATH = PROJECT_SHARED_SKILL_RELATIVE_PATH
NEURO_CLI_WRAPPER_RELATIVE_PATH = "neuro_cli/scripts/invoke_neuro_cli.py"

AGENT_RUNTIME_SCHEMA_VERSION = "1.2.0-agent-runtime-v1"
TOOL_MANIFEST_SCHEMA_VERSION = "1.2.0-tool-manifest-v1"
STATE_SYNC_SCHEMA_VERSION = "1.2.0-state-sync-v1"
AGENT_EVENTS_SCHEMA_VERSION = "1.2.0-agent-events-v1"


def resolve_neurolink_path(
    neurolink_root: Path | None, relative_path: str
) -> Path:
    return neurolink_root / relative_path if neurolink_root else Path(relative_path)


def build_protocol_metadata() -> dict[str, Any]:
    return {
        "version": protocol.DEFAULT_PROTOCOL_VERSION,
        "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
        "supported_wire_encodings": protocol.SUPPORTED_WIRE_ENCODINGS,
        "planned_wire_encodings": protocol.PLANNED_WIRE_ENCODINGS,
        "cbor_v2_enabled": protocol.DEFAULT_WIRE_ENCODING == "cbor-v2",
    }


def build_agent_runtime_metadata(neurolink_root: Path | None) -> dict[str, Any]:
    wrapper_path = resolve_neurolink_path(neurolink_root, NEURO_CLI_WRAPPER_RELATIVE_PATH)
    return {
        "schema_version": AGENT_RUNTIME_SCHEMA_VERSION,
        "wrapper_relative_path": NEURO_CLI_WRAPPER_RELATIVE_PATH,
        "wrapper_path": str(wrapper_path),
        "wrapper_exists": wrapper_path.is_file(),
        "tool_manifest_command": "system tool-manifest --output json",
        "state_sync_command": "system state-sync --output json",
        "agent_events_command": "monitor agent-events --output jsonl",
        "supports": {
            "tool_manifest": True,
            "state_sync": True,
            "agent_events_jsonl": True,
        },
        "agent_events_mode": "bounded_equivalent",
        "side_effect_levels": [
            "observe_only",
            "read_only",
            "suggest_only",
            "low_risk_execute",
            "approval_required",
            "destructive",
        ],
    }


def build_tool_manifest_payload(
    neurolink_root: Path | None,
    release_target: str = "1.2.0",
) -> dict[str, Any]:
    common_failures = ["no_reply", "query_failed", "error_reply", "parse_failed"]
    capability_matrix = protocol.CAPABILITY_MATRIX
    control_failure_statuses = [
        "approval_required",
        "lease_missing",
        "control_failed",
        "parse_failed",
        *common_failures,
    ]
    tools = [
        {
            "name": "system_query_device",
            "description": "Read current Unit device/network state through the query plane.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "query",
                "device",
                "--output",
                "json",
            ],
            "resource": capability_matrix["query_device"]["resource"],
            "required_arguments": ["--node"],
            "side_effect_level": "read_only",
            "timeout_seconds": 10,
            "retryable": True,
            "approval_required": False,
            "lease_requirements": [],
            "cleanup_hints": [],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": common_failures,
            },
        },
        {
            "name": "system_query_apps",
            "description": "Read current Unit application lifecycle state through the query plane.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "query",
                "apps",
                "--output",
                "json",
            ],
            "resource": capability_matrix["query_apps"]["resource"],
            "required_arguments": ["--node"],
            "side_effect_level": "read_only",
            "timeout_seconds": 10,
            "retryable": True,
            "approval_required": False,
            "lease_requirements": [],
            "cleanup_hints": [],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": common_failures,
            },
        },
        {
            "name": "system_query_leases",
            "description": "Read current active leases before any side-effecting action.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "query",
                "leases",
                "--output",
                "json",
            ],
            "resource": capability_matrix["query_leases"]["resource"],
            "required_arguments": ["--node"],
            "side_effect_level": "read_only",
            "timeout_seconds": 10,
            "retryable": True,
            "approval_required": False,
            "lease_requirements": [],
            "cleanup_hints": [],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": common_failures,
            },
        },
        {
            "name": "system_state_sync",
            "description": "Aggregate device, apps, leases, protocol, and agent runtime metadata into one read-only sync snapshot.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "system",
                "state-sync",
                "--output",
                "json",
            ],
            "resource": "state sync aggregate",
            "required_arguments": ["--node"],
            "side_effect_level": "read_only",
            "timeout_seconds": 10,
            "retryable": True,
            "approval_required": False,
            "lease_requirements": [],
            "cleanup_hints": ["review active leases before side-effecting commands"],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": ["partial_failure", *common_failures],
            },
        },
        {
            "name": "system_activation_health_guard",
            "description": "Classify post-activation health from read-only state sync evidence before any recovery action.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "system",
                "state-sync",
                "--output",
                "json",
            ],
            "resource": "post-activation health observation",
            "required_arguments": ["--node", "--app-id"],
            "side_effect_level": "read_only",
            "timeout_seconds": 10,
            "retryable": True,
            "approval_required": False,
            "lease_requirements": [],
            "cleanup_hints": [
                "treat rollback as an operator decision after reviewing health evidence"
            ],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "classification_statuses": [
                    "healthy",
                    "degraded",
                    "no_reply",
                    "rollback_required",
                ],
            },
        },
        {
            "name": "system_rollback_app",
            "description": "Rollback a staged app update after explicit operator approval.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "deploy",
                "rollback",
                "--output",
                "json",
            ],
            "resource": capability_matrix["update_rollback"]["resource"],
            "required_arguments": ["--node", "--app-id", "--lease-id"],
            "side_effect_level": "approval_required",
            "timeout_seconds": 15,
            "retryable": False,
            "approval_required": True,
            "lease_requirements": ["update_rollback_lease"],
            "cleanup_hints": [
                "confirm rollback evidence, lease ownership, and target app identity before resume"
            ],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": control_failure_statuses,
            },
        },
        {
            "name": "system_capabilities",
            "description": "Read stable Neuro CLI protocol, workflow, and agent runtime metadata.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "system",
                "capabilities",
                "--output",
                "json",
            ],
            "resource": "capability map",
            "required_arguments": [],
            "side_effect_level": "observe_only",
            "timeout_seconds": 5,
            "retryable": False,
            "approval_required": False,
            "lease_requirements": [],
            "cleanup_hints": [],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": ["workspace_not_found", "handler_failed"],
            },
        },
        {
            "name": "system_restart_app",
            "description": "Restart a Unit application through the command plane after explicit approval.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "app",
                "stop",
                "--output",
                "json",
            ],
            "resource": "app control plane",
            "required_arguments": ["--node", "--app-id", "--lease-id"],
            "side_effect_level": "approval_required",
            "timeout_seconds": 15,
            "retryable": False,
            "approval_required": True,
            "lease_requirements": ["app_control_lease"],
            "cleanup_hints": ["confirm target app identity and active leases before restart"],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": control_failure_statuses,
            },
        },
        {
            "name": "system_start_app",
            "description": "Start a Unit application through the command plane after explicit approval.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "app",
                "start",
                "--output",
                "json",
            ],
            "resource": "app control plane",
            "required_arguments": ["--node", "--app-id", "--lease-id"],
            "side_effect_level": "approval_required",
            "timeout_seconds": 15,
            "retryable": False,
            "approval_required": True,
            "lease_requirements": ["app_control_lease"],
            "cleanup_hints": ["confirm target app identity and active leases before start"],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": control_failure_statuses,
            },
        },
        {
            "name": "system_stop_app",
            "description": "Stop a Unit application through the command plane after explicit approval.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "app",
                "stop",
                "--output",
                "json",
            ],
            "resource": "app control plane",
            "required_arguments": ["--node", "--app-id", "--lease-id"],
            "side_effect_level": "approval_required",
            "timeout_seconds": 15,
            "retryable": False,
            "approval_required": True,
            "lease_requirements": ["app_control_lease"],
            "cleanup_hints": ["confirm target app identity and active leases before stop"],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": control_failure_statuses,
            },
        },
        {
            "name": "system_unload_app",
            "description": "Unload a Unit application through the command plane after explicit approval.",
            "argv_template": [
                "python",
                NEURO_CLI_WRAPPER_RELATIVE_PATH,
                "app",
                "unload",
                "--output",
                "json",
            ],
            "resource": "app control plane",
            "required_arguments": ["--node", "--app-id", "--lease-id"],
            "side_effect_level": "approval_required",
            "timeout_seconds": 15,
            "retryable": False,
            "approval_required": True,
            "lease_requirements": ["app_control_lease"],
            "cleanup_hints": ["confirm target app identity and active leases before unload"],
            "output_contract": {
                "format": "json",
                "top_level_ok": True,
                "failure_statuses": control_failure_statuses,
            },
        },
    ]
    return {
        "ok": True,
        "status": "ok",
        "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
        "release_target": release_target,
        "agent_runtime": build_agent_runtime_metadata(neurolink_root),
        "tools": tools,
    }


def build_agent_event_rows(args: Any) -> list[dict[str, Any]]:
    rows = [
        {
            "schema_version": AGENT_EVENTS_SCHEMA_VERSION,
            "mode": "bounded_equivalent",
            "live_subscription": False,
            "event_id": "evt-demo-callback-001",
            "source_kind": "unit_app",
            "source_node": args.node,
            "source_app": "neuro_demo_gpio",
            "event_type": "callback",
            "semantic_topic": "unit.callback",
            "timestamp_mono": 0.0,
            "timestamp_wall": "2026-05-04T00:00:00Z",
            "priority": 80,
            "dedupe_key": "demo-callback-001",
            "causality_id": "demo-callback-001",
            "raw_payload_ref": "bounded_equivalent://agent-events/demo-callback-001",
            "policy_tags": ["bounded_equivalent", "read_only_ingress"],
            "payload_encoding": "json",
            "payload_hex": "",
            "payload": {"callback_enabled": True},
        },
        {
            "schema_version": AGENT_EVENTS_SCHEMA_VERSION,
            "mode": "bounded_equivalent",
            "live_subscription": False,
            "event_id": "evt-time-tick-001",
            "source_kind": "clock",
            "source_node": args.node,
            "source_app": "",
            "event_type": "time.tick",
            "semantic_topic": "time.tick",
            "timestamp_mono": 1.0,
            "timestamp_wall": "2026-05-04T00:00:01Z",
            "priority": 10,
            "dedupe_key": "time-tick-001",
            "causality_id": "time-tick-001",
            "raw_payload_ref": "bounded_equivalent://agent-events/time-tick-001",
            "policy_tags": ["bounded_equivalent", "clock"],
            "payload_encoding": "json",
            "payload_hex": "",
            "payload": {"period_ms": 1000},
        },
    ]
    max_events = max(0, int(getattr(args, "max_events", 0) or 0))
    if max_events > 0:
        return rows[:max_events]
    return rows