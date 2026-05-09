from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any, Callable, cast

from .agents import AffectiveDecision
from .common import PerceptionEvent, PerceptionFrame, WorkflowResult, new_id, utc_now_iso
from .data import CoreDataStore
from .events import PerceptionEventRouter
from .inference import build_inference_route, normalize_multimodal_input
from .maf import (
    MafProviderMode,
    MafRuntimeProfile,
    build_affective_agent_adapter,
    build_default_maf_provider_client,
    build_maf_runtime_profile,
    build_rational_agent_adapter,
)
from .memory import FakeLongTermMemory, LongTermMemory, build_memory_backend
from .policy import ReadOnlyToolPolicy
from .session import CoreSessionManager, build_prompt_safe_context
from .tools import (
    CommandExecutionResult,
    FakeUnitToolAdapter,
    NeuroCliToolAdapter,
    ToolContract,
    ToolExecutionResult,
    load_mcp_bridge_descriptor_payload,
    load_neuro_cli_skill_descriptor_payload,
    validate_tool_workflow_catalog_consistency,
)


AGENT_RUN_EVIDENCE_SCHEMA_VERSION = "1.2.2-agent-run-evidence-v1"
APP_BUILD_PLAN_SCHEMA_VERSION = "1.2.4-app-build-plan-v1"
APP_ARTIFACT_ADMISSION_SCHEMA_VERSION = "1.2.4-app-artifact-admission-v1"
APP_DEPLOY_PLAN_SCHEMA_VERSION = "1.2.4-app-deploy-plan-v1"
APP_DEPLOY_PREPARE_VERIFY_SCHEMA_VERSION = "1.2.4-app-deploy-prepare-verify-v1"
APP_DEPLOY_ACTIVATE_SCHEMA_VERSION = "1.2.4-app-deploy-activate-v1"
APP_DEPLOY_ROLLBACK_SCHEMA_VERSION = "1.2.4-app-deploy-rollback-v1"
EVENT_SERVICE_SCHEMA_VERSION = "1.2.4-event-service-v1"
RATIONAL_PLAN_QUALITY_SCHEMA_VERSION = "1.2.6-rational-plan-quality-v2"
RATIONAL_PLAN_EVIDENCE_SCHEMA_VERSION = "1.2.5-rational-plan-evidence-v1"
AFFECTIVE_RUNTIME_CONTEXT_SCHEMA_VERSION = "1.2.5-affective-runtime-context-v1"


ELF_MACHINE_NAMES = {
    3: "x86",
    40: "arm",
    62: "x86_64",
    94: "xtensa",
    183: "aarch64",
    243: "riscv",
}


BOARD_ARCHITECTURE_NAMES = {
    "dnesp32s3b/esp32s3/procpu": "xtensa",
}


def _validate_app_build_app_id(app_id: str) -> str:
    normalized = app_id.strip()
    if not normalized:
        raise ValueError("app_build_plan_requires_app_id")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", normalized):
        raise ValueError("invalid_app_build_app_id")
    return normalized


def _validate_app_build_dir(build_dir: str) -> str:
    normalized = build_dir.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("app_build_plan_requires_build_dir")
    if ".." in normalized:
        raise ValueError("invalid_app_build_dir")
    if re.fullmatch(r"build_[^/]+", normalized):
        raise ValueError("invalid_app_build_dir")
    if not re.fullmatch(r"build/.+", normalized):
        raise ValueError("invalid_app_build_dir")
    return normalized


def _resolve_app_build_source_dir(app_id: str, app_source_dir: str | None) -> str:
    candidate = (app_source_dir or "").strip().replace("\\", "/")
    if not candidate:
        candidate = f"applocation/NeuroLink/subprojects/{app_id}"
    if ".." in candidate:
        raise ValueError("invalid_app_build_source_dir")
    return candidate


def _get_unit_app_build_dir(build_dir: str, app_id: str) -> str:
    parent_dir, _, base_name = build_dir.rpartition("/")
    if app_id == "neuro_unit_app":
        return f"{parent_dir}/{base_name}_app"
    normalized_app_id = app_id.replace("-", "_")
    return f"{parent_dir}/{base_name}_{normalized_app_id}_app"


def build_app_build_plan(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    check_c_style: bool = False,
) -> dict[str, Any]:
    normalized_preset = preset.strip()
    if normalized_preset not in ("unit-app", "unit-ext"):
        raise ValueError("unsupported_app_build_preset")

    normalized_app_id = _validate_app_build_app_id(app_id)
    normalized_build_dir = _validate_app_build_dir(build_dir)
    normalized_source_dir = _resolve_app_build_source_dir(
        normalized_app_id,
        app_source_dir,
    )
    app_build_dir = _get_unit_app_build_dir(normalized_build_dir, normalized_app_id)
    source_artifact_file = f"{app_build_dir}/{normalized_app_id}.llext"
    staged_artifact_file = f"{normalized_build_dir}/llext/{normalized_app_id}.llext"

    build_command_parts = [
        "bash",
        "applocation/NeuroLink/scripts/build_neurolink.sh",
        "--preset",
        normalized_preset,
    ]
    if normalized_app_id != "neuro_unit_app":
        build_command_parts.extend(["--app", normalized_app_id])
    if normalized_source_dir != f"applocation/NeuroLink/subprojects/{normalized_app_id}":
        build_command_parts.extend(["--app-source-dir", normalized_source_dir])
    if normalized_build_dir != "build/neurolink_unit":
        build_command_parts.extend(["--build-dir", normalized_build_dir])
    if board != "dnesp32s3b/esp32s3/procpu":
        build_command_parts.extend(["--board", board])
    if not check_c_style:
        build_command_parts.append("--no-c-style-check")

    plan = {
        "schema_version": APP_BUILD_PLAN_SCHEMA_VERSION,
        "release_slice": "1.2.4",
        "preset": normalized_preset,
        "board": board,
        "app_id": normalized_app_id,
        "app_source_dir": normalized_source_dir,
        "unit_build_dir": normalized_build_dir,
        "app_build_dir": app_build_dir,
        "source_artifact_file": source_artifact_file,
        "staged_artifact_file": staged_artifact_file,
        "canonical_artifact_file": source_artifact_file,
        "build_script": "applocation/NeuroLink/scripts/build_neurolink.sh",
        "build_command": " ".join(build_command_parts),
        "uses_edk_external_app_flow": True,
        "admission_checks": [
            "source_artifact_exists",
            "source_artifact_is_nonempty",
            "source_artifact_has_valid_elf_header",
            "staged_artifact_exists",
            "staged_artifact_is_nonempty",
            "staged_artifact_has_valid_elf_header",
            "artifact_app_id_matches_request",
        ],
    }
    return {
        "ok": True,
        "status": "ok",
        "command": "app-build-plan",
        "build_plan": plan,
    }


def _resolve_app_artifact_file(artifact_file: str | None, fallback_file: str) -> str:
    candidate = (artifact_file or "").strip().replace("\\", "/")
    if not candidate:
        candidate = fallback_file
    if not candidate:
        raise ValueError("app_artifact_admission_requires_artifact_file")
    return candidate


def _validate_deploy_plan_identifier(value: str, failure_status: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(failure_status)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", normalized):
        raise ValueError(failure_status)
    return normalized


def _suggest_activation_lease_id(app_id: str) -> str:
    return f"l-{app_id.replace('_', '-').replace('.', '-').lower()}-act"


def _load_app_source_identity(app_source_dir: str, app_id: str) -> dict[str, str]:
    source_file = Path(app_source_dir) / "src" / "main.c"
    if not source_file.is_file():
        raise ValueError("source_identity_file_missing")

    source_text = source_file.read_text(encoding="utf-8")

    def require_match(pattern: str, failure_status: str) -> re.Match[str]:
        match = re.search(pattern, source_text, re.MULTILINE | re.DOTALL)
        if match is None:
            raise ValueError(failure_status)
        return match

    source_app_id = require_match(
        r'static const char app_id\[\]\s*=\s*"([^"]+)";',
        "source_identity_app_id_missing",
    ).group(1)
    if source_app_id != app_id:
        raise ValueError("source_app_id_mismatch")

    app_version = require_match(
        r'static const char app_version\[\]\s*=\s*"([^"]+)";',
        "source_identity_version_missing",
    ).group(1)
    build_id = require_match(
        r'static const char app_build_id\[\]\s*=\s*"([^"]+)";',
        "source_identity_build_id_missing",
    ).group(1)
    manifest_match = require_match(
        r'\.version\s*=\s*\{\s*\.major\s*=\s*(\d+)\s*,\s*\.minor\s*=\s*(\d+)\s*,\s*\.patch\s*=\s*(\d+)',
        "source_identity_manifest_version_missing",
    )
    manifest_version = ".".join(manifest_match.groups())
    if manifest_version != app_version:
        raise ValueError("source_manifest_version_mismatch")

    return {
        "source_identity_file": source_file.as_posix(),
        "app_id": source_app_id,
        "app_version": app_version,
        "build_id": build_id,
        "manifest_version": manifest_version,
    }


def _read_elf_identity(artifact_bytes: bytes) -> dict[str, Any]:
    if len(artifact_bytes) < 24:
        raise ValueError("artifact_invalid_elf_header")
    if artifact_bytes[:4] != b"\x7fELF":
        raise ValueError("artifact_invalid_elf_header")

    elf_class = artifact_bytes[4]
    elf_data = artifact_bytes[5]
    elf_version = artifact_bytes[6]
    if elf_class not in (1, 2) or elf_data not in (1, 2) or elf_version != 1:
        raise ValueError("artifact_invalid_elf_header")

    byte_order = "little" if elf_data == 1 else "big"
    struct_prefix = "<" if elf_data == 1 else ">"
    e_type = struct.unpack(f"{struct_prefix}H", artifact_bytes[16:18])[0]
    e_machine = struct.unpack(f"{struct_prefix}H", artifact_bytes[18:20])[0]
    e_version_word = struct.unpack(f"{struct_prefix}I", artifact_bytes[20:24])[0]
    if e_version_word != 1:
        raise ValueError("artifact_invalid_elf_header")

    return {
        "elf_class": "ELF32" if elf_class == 1 else "ELF64",
        "endianness": "little_endian" if byte_order == "little" else "big_endian",
        "elf_version": e_version_word,
        "elf_type": e_type,
        "machine_id": e_machine,
        "machine_name": ELF_MACHINE_NAMES.get(e_machine, f"unknown-{e_machine}"),
    }


def build_app_artifact_admission(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
) -> dict[str, Any]:
    build_plan_payload = build_app_build_plan(
        preset=preset,
        app_id=app_id,
        app_source_dir=app_source_dir,
        board=board,
        build_dir=build_dir,
    )
    build_plan = cast(dict[str, Any], build_plan_payload["build_plan"])
    resolved_artifact_file = _resolve_app_artifact_file(
        artifact_file,
        str(build_plan["source_artifact_file"]),
    )
    artifact_path = Path(resolved_artifact_file)
    if artifact_path.name != f"{app_id}.llext":
        raise ValueError("artifact_filename_app_id_mismatch")
    if not artifact_path.is_file():
        raise ValueError("artifact_missing")

    artifact_bytes = artifact_path.read_bytes()
    if not artifact_bytes:
        raise ValueError("artifact_empty")

    source_identity = _load_app_source_identity(str(build_plan["app_source_dir"]), app_id)
    elf_identity = _read_elf_identity(artifact_bytes)
    expected_architecture = BOARD_ARCHITECTURE_NAMES.get(board, "unknown")
    if (
        expected_architecture != "unknown"
        and elf_identity["machine_name"] != expected_architecture
    ):
        raise ValueError("artifact_target_arch_mismatch")

    contains_app_id = source_identity["app_id"].encode("utf-8") in artifact_bytes
    contains_build_id = source_identity["build_id"].encode("utf-8") in artifact_bytes
    contains_version = source_identity["app_version"].encode("utf-8") in artifact_bytes
    if not contains_app_id:
        raise ValueError("artifact_app_id_missing")
    if not contains_build_id:
        raise ValueError("artifact_build_id_missing")
    if not contains_version:
        raise ValueError("artifact_version_missing")

    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    artifact_size_bytes = len(artifact_bytes)
    admission = {
        "schema_version": APP_ARTIFACT_ADMISSION_SCHEMA_VERSION,
        "artifact_file": artifact_path.as_posix(),
        "artifact_size_bytes": artifact_size_bytes,
        "artifact_sha256": artifact_sha256,
        "expected_architecture": expected_architecture,
        "elf_identity": elf_identity,
        "source_identity": source_identity,
        "filename_matches_app_id": True,
        "artifact_contains_app_id_string": contains_app_id,
        "artifact_contains_build_id_string": contains_build_id,
        "artifact_contains_version_string": contains_version,
        "admission_checks": [
            "artifact_exists",
            "artifact_is_nonempty",
            "artifact_filename_matches_app_id",
            "artifact_has_valid_elf_header",
            "artifact_target_architecture_matches_board",
            "artifact_contains_app_id_string",
            "artifact_contains_build_id_string",
            "artifact_contains_version_string",
            "source_manifest_version_matches_source_version",
        ],
        "admitted": True,
    }
    return {
        "ok": True,
        "status": "ok",
        "command": "app-artifact-admission",
        "build_plan": build_plan,
        "artifact_admission": admission,
    }


def build_app_deploy_plan(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
    node_id: str = "unit-01",
    source_agent: str = "rational",
    lease_ttl_ms: int = 120000,
    start_args: str | None = None,
) -> dict[str, Any]:
    normalized_node_id = _validate_deploy_plan_identifier(node_id, "invalid_deploy_node_id")
    normalized_source_agent = _validate_deploy_plan_identifier(
        source_agent,
        "invalid_deploy_source_agent",
    )
    if lease_ttl_ms <= 0:
        raise ValueError("invalid_deploy_lease_ttl_ms")

    admission_payload = build_app_artifact_admission(
        preset=preset,
        app_id=app_id,
        app_source_dir=app_source_dir,
        board=board,
        build_dir=build_dir,
        artifact_file=artifact_file,
    )
    build_plan = cast(dict[str, Any], admission_payload["build_plan"])
    artifact_admission = cast(dict[str, Any], admission_payload["artifact_admission"])
    resolved_artifact_file = str(artifact_admission["artifact_file"])
    activation_resource = f"update/app/{app_id}/activate"
    suggested_lease_id = _suggest_activation_lease_id(app_id)
    normalized_start_args = (start_args or "").strip()

    preflight_command_parts = [
        "bash",
        "applocation/NeuroLink/scripts/preflight_neurolink_linux.sh",
        "--node",
        normalized_node_id,
        "--artifact-file",
        resolved_artifact_file,
        "--auto-start-router",
        "--require-serial",
        "--install-missing-cli-deps",
        "--output",
        "json",
    ]
    cli_prefix = [
        sys.executable,
        "applocation/NeuroLink/neuro_cli/src/neuro_cli.py",
        "--output",
        "json",
        "--node",
        normalized_node_id,
        "--source-agent",
        normalized_source_agent,
    ]
    lease_acquire_parts = cli_prefix + [
        "lease",
        "acquire",
        "--resource",
        activation_resource,
        "--lease-id",
        suggested_lease_id,
        "--ttl-ms",
        str(lease_ttl_ms),
    ]
    prepare_parts = cli_prefix + [
        "deploy",
        "prepare",
        "--app-id",
        app_id,
        "--file",
        resolved_artifact_file,
    ]
    verify_parts = cli_prefix + [
        "deploy",
        "verify",
        "--app-id",
        app_id,
    ]
    activate_parts = cli_prefix + [
        "deploy",
        "activate",
        "--app-id",
        app_id,
        "--lease-id",
        suggested_lease_id,
    ]
    if normalized_start_args:
        activate_parts.extend(["--start-args", normalized_start_args])
    health_guard_parts = [
        sys.executable,
        "-m",
        "neurolink_core.cli",
        "activation-health-guard",
        "--app-id",
        app_id,
        "--tool-adapter",
        "neuro-cli",
        "--output",
        "json",
    ]
    query_apps_parts = cli_prefix + ["query", "apps"]
    lease_release_parts = cli_prefix + [
        "lease",
        "release",
        "--lease-id",
        suggested_lease_id,
    ]
    query_leases_parts = cli_prefix + ["query", "leases"]

    steps = [
        {
            "name": "preflight",
            "kind": "preflight",
            "side_effect_free": False,
            "command": " ".join(preflight_command_parts),
            "argv": preflight_command_parts,
            "expected_status": "ready",
        },
        {
            "name": "artifact_admission",
            "kind": "admission",
            "side_effect_free": True,
            "command": "neurolink_core app-artifact-admission",
            "expected_status": "ok",
        },
        {
            "name": "lease_acquire_activate",
            "kind": "lease",
            "side_effect_free": False,
            "command": " ".join(lease_acquire_parts),
            "argv": lease_acquire_parts,
            "required_resource": activation_resource,
            "expected_status": "ok",
        },
        {
            "name": "deploy_prepare",
            "kind": "deploy_prepare",
            "side_effect_free": False,
            "command": " ".join(prepare_parts),
            "argv": prepare_parts,
            "expected_nested_payload_status": "ok",
        },
        {
            "name": "deploy_verify",
            "kind": "deploy_verify",
            "side_effect_free": False,
            "command": " ".join(verify_parts),
            "argv": verify_parts,
            "expected_nested_payload_status": "ok",
        },
        {
            "name": "activation_approval_gate",
            "kind": "approval_gate",
            "side_effect_free": True,
            "approval_required": True,
            "required_resource": activation_resource,
            "expected_decision": "approved",
        },
        {
            "name": "deploy_activate",
            "kind": "deploy_activate",
            "side_effect_free": False,
            "command": " ".join(activate_parts),
            "argv": activate_parts,
            "approval_required": True,
            "expected_nested_payload_status": "ok",
        },
        {
            "name": "activation_health_guard",
            "kind": "health_guard",
            "side_effect_free": True,
            "command": " ".join(health_guard_parts),
            "argv": health_guard_parts,
            "expected_status": "ok",
        },
        {
            "name": "query_apps",
            "kind": "query_apps",
            "side_effect_free": True,
            "command": " ".join(query_apps_parts),
            "argv": query_apps_parts,
            "expected_status": "ok",
        },
        {
            "name": "lease_release_activate",
            "kind": "lease_cleanup",
            "side_effect_free": False,
            "command": " ".join(lease_release_parts),
            "argv": lease_release_parts,
            "expected_status": "ok_or_lease_not_found",
        },
        {
            "name": "query_leases",
            "kind": "query_leases",
            "side_effect_free": True,
            "command": " ".join(query_leases_parts),
            "argv": query_leases_parts,
            "expected_status": "ok",
            "expected_leases": [],
        },
    ]

    deploy_plan = {
        "schema_version": APP_DEPLOY_PLAN_SCHEMA_VERSION,
        "release_slice": "1.2.4",
        "node_id": normalized_node_id,
        "source_agent": normalized_source_agent,
        "board": board,
        "app_id": app_id,
        "artifact_file": resolved_artifact_file,
        "activation_resource": activation_resource,
        "suggested_activate_lease_id": suggested_lease_id,
        "lease_ttl_ms": lease_ttl_ms,
        "start_args": normalized_start_args,
        "activation_approval_required": True,
        "cleanup_requires_empty_leases": True,
        "final_expected_app_state": "RUNNING_ACTIVE",
        "steps": steps,
    }
    return {
        "ok": True,
        "status": "ok",
        "command": "app-deploy-plan",
        "build_plan": build_plan,
        "artifact_admission": artifact_admission,
        "deploy_plan": deploy_plan,
    }


def _parse_command_json_result(command_result: CommandExecutionResult) -> dict[str, Any]:
    normalized_stdout = command_result.stdout.strip()
    candidates = [normalized_stdout]
    start = normalized_stdout.find("{")
    end = normalized_stdout.rfind("}")
    if start != -1 and end != -1 and end >= start:
        candidates.append(normalized_stdout[start : end + 1])

    payload: Any | None = None
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
            last_error = None
            break
        except json.JSONDecodeError as exc:
            last_error = exc
            continue

    if payload is None:
        if command_result.exit_code != 0:
            raise ValueError(f"command_exit_{command_result.exit_code}") from last_error
        raise ValueError("parse_failed") from last_error
    if not isinstance(payload, dict):
        raise ValueError("parse_failed")
    return cast(dict[str, Any], payload)


def _command_payload_failure_status(payload: dict[str, Any]) -> str:
    top_level_status = str(payload.get("status") or "")
    if payload.get("ok") is False and top_level_status:
        return top_level_status
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, dict):
        nested_status = str(cast(dict[str, Any], nested_payload).get("status") or "")
        if nested_status and nested_status != "ok":
            return nested_status
    replies = payload.get("replies")
    if isinstance(replies, list):
        for reply in cast(list[Any], replies):
            if not isinstance(reply, dict):
                continue
            reply_payload = cast(dict[str, Any] | None, reply.get("payload"))
            if not isinstance(reply_payload, dict):
                continue
            reply_status = str(reply_payload.get("status") or "")
            if reply_status and reply_status != "ok":
                return reply_status
    return ""


def _build_execution_step_result(
    *,
    name: str,
    argv: list[str],
    command_result: CommandExecutionResult | None,
    payload: dict[str, Any] | None,
    failure_status: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "command": " ".join(argv),
        "argv": list(argv),
        "ok": not failure_status,
        "failure_status": failure_status,
    }
    if command_result is not None:
        result["exit_code"] = command_result.exit_code
        if command_result.stderr:
            result["stderr"] = command_result.stderr
    if payload is not None:
        result["result"] = payload
    return result


def _build_tool_execution_step_result(
    *,
    name: str,
    tool_name: str,
    tool_result: ToolExecutionResult,
    failure_status: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "tool_name": tool_name,
        "status": tool_result.status,
        "ok": not failure_status,
        "failure_status": failure_status,
        "result": dict(tool_result.payload),
    }


def _tool_execution_failure_status(tool_result: ToolExecutionResult) -> str:
    if tool_result.status != "ok":
        return str(
            tool_result.payload.get("failure_status")
            or tool_result.status
            or "tool_execution_failed"
        )
    result_payload = tool_result.payload.get("result")
    if isinstance(result_payload, dict):
        nested_failure_status = _command_payload_failure_status(
            cast(dict[str, Any], result_payload)
        )
        if nested_failure_status:
            return nested_failure_status
    return ""


def _normalize_activation_approval_decision(decision: str) -> str:
    normalized = decision.strip().lower()
    if normalized in {"approve", "approved"}:
        return "approved"
    if normalized in {"deny", "denied"}:
        return "denied"
    if normalized in {"expire", "expired"}:
        return "expired"
    if normalized in {"pending", ""}:
        return "pending"
    raise ValueError("invalid_activation_approval_decision")


def _release_gate_approval_failure_class(status: str, *, prefix: str) -> str:
    if status == "pending_approval":
        return f"{prefix}_approval_required"
    if status == "denied":
        return f"{prefix}_approval_denied"
    if status == "expired":
        return f"{prefix}_approval_expired"
    return f"{prefix}_approval_required"


def _build_guarded_rollback_approval(
    *,
    tool_adapter: Any,
    recovery_candidate_summary: dict[str, Any],
) -> dict[str, Any]:
    rollback_contract = None
    describe_tool = getattr(tool_adapter, "describe_tool", None)
    if callable(describe_tool):
        rollback_contract = describe_tool("system_rollback_app")

    matching_lease_ids = cast(
        list[Any],
        recovery_candidate_summary.get("matching_lease_ids") or [],
    )
    requested_args = {
        "app_id": str(recovery_candidate_summary.get("app_id") or ""),
        "app": str(recovery_candidate_summary.get("app_id") or ""),
        "lease_id": str(matching_lease_ids[0] if matching_lease_ids else ""),
        "reason": "guarded_rollback_after_activation_health_failure",
    }
    payload: dict[str, Any] = {
        "status": "pending_approval",
        "tool_name": "system_rollback_app",
        "reason": "operator_approval_required_for_guarded_rollback",
        "requested_args": requested_args,
        "required_resources": ["update_rollback_lease"],
        "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
        "target_app_id": str(recovery_candidate_summary.get("app_id") or ""),
        "recovery_candidate_summary": dict(recovery_candidate_summary),
    }
    if rollback_contract is not None:
        payload["required_resources"] = list(rollback_contract.required_resources)
        payload["cleanup_hint"] = rollback_contract.cleanup_hint
        payload["contract"] = rollback_contract.to_dict()
    return payload


def _persist_release_gate_command_result(
    db_path: str,
    *,
    command_name: str,
    payload: dict[str, Any],
    fact_records: list[tuple[str, str, dict[str, Any]]],
) -> dict[str, str]:
    data_store = CoreDataStore(db_path)
    session_id = new_id("session")
    execution_span_id = new_id("exec")
    audit_id = new_id("audit")
    try:
        data_store.persist_execution_span(
            execution_span_id,
            "running",
            {"command": command_name, "status": "running"},
            session_id=session_id,
        )
        data_store.persist_fact(
            execution_span_id,
            "release_gate_command",
            command_name,
            {
                "command": command_name,
                "ok": bool(payload.get("ok", False)),
                "status": str(payload.get("status") or "unknown"),
            },
        )
        for fact_type, subject, fact_payload in fact_records:
            data_store.persist_fact(
                execution_span_id,
                fact_type,
                subject,
                fact_payload,
            )
        data_store.persist_audit_record(
            audit_id,
            execution_span_id,
            str(payload.get("status") or ("ok" if payload.get("ok") else "error")),
            payload,
            session_id=session_id,
        )
        data_store.persist_execution_span(
            execution_span_id,
            "ok" if bool(payload.get("ok", False)) else str(payload.get("status") or "error"),
            {
                "command": command_name,
                "status": str(payload.get("status") or "unknown"),
                "audit_id": audit_id,
            },
            session_id=session_id,
        )
    finally:
        data_store.close()
    return {
        "db_path": db_path,
        "session_id": session_id,
        "execution_span_id": execution_span_id,
        "audit_id": audit_id,
    }


def persist_app_deploy_activate_evidence(
    db_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    activation_decision = cast(dict[str, Any], payload.get("activation_decision") or {})
    app_id = str(activation_decision.get("resolved_app_id") or "app-deploy-activate")
    fact_records: list[tuple[str, str, dict[str, Any]]] = []
    if activation_decision:
        fact_records.append(("activation_decision", app_id, activation_decision))
    deploy_execution = cast(dict[str, Any], payload.get("deploy_execution") or {})
    activation_health_guard = cast(
        dict[str, Any],
        deploy_execution.get("activation_health_guard") or {},
    )
    activation_health_result = cast(
        dict[str, Any],
        activation_health_guard.get("result") or {},
    )
    activation_health = cast(
        dict[str, Any],
        activation_health_result.get("activation_health")
        or activation_health_result.get("health_observation")
        or {},
    )
    if activation_health:
        fact_records.append(
            (
                "activation_health_observation",
                str(activation_health.get("app_id") or app_id),
                activation_health,
            )
        )
    recovery_candidate_summary = cast(
        dict[str, Any],
        payload.get("recovery_candidate_summary") or {},
    )
    if recovery_candidate_summary:
        fact_records.append(
            (
                "recovery_candidate",
                str(recovery_candidate_summary.get("app_id") or app_id),
                recovery_candidate_summary,
            )
        )
    rollback_approval = cast(dict[str, Any], payload.get("rollback_approval") or {})
    if rollback_approval:
        fact_records.append(
            (
                "rollback_approval",
                str(rollback_approval.get("target_app_id") or app_id),
                rollback_approval,
            )
        )
    return _persist_release_gate_command_result(
        db_path,
        command_name="app-deploy-activate",
        payload=payload,
        fact_records=fact_records,
    )


def persist_app_deploy_rollback_evidence(
    db_path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    rollback_decision = cast(dict[str, Any], payload.get("rollback_decision") or {})
    app_id = str(rollback_decision.get("resolved_app_id") or "app-deploy-rollback")
    fact_records: list[tuple[str, str, dict[str, Any]]] = []
    if rollback_decision:
        fact_records.append(("rollback_decision", app_id, rollback_decision))
    rollback_execution = cast(dict[str, Any], payload.get("rollback_execution") or {})
    rollback_step = cast(dict[str, Any], rollback_execution.get("rollback") or {})
    rollback_result = cast(dict[str, Any], rollback_step.get("result") or {})
    if rollback_result:
        fact_records.append(("rollback_result", app_id, rollback_result))
    rollback_failure_summary = cast(
        dict[str, Any],
        payload.get("rollback_failure_summary") or {},
    )
    if rollback_failure_summary:
        fact_records.append(("rollback_failure_summary", app_id, rollback_failure_summary))
    return _persist_release_gate_command_result(
        db_path,
        command_name="app-deploy-rollback",
        payload=payload,
        fact_records=fact_records,
    )


def _extract_query_apps_target_state(
    payload: dict[str, Any],
    *,
    app_id: str,
) -> dict[str, Any]:
    observed_apps: list[Any] = []
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, dict) and isinstance(nested_payload.get("apps"), list):
        observed_apps = cast(list[Any], nested_payload["apps"])
    else:
        replies = payload.get("replies")
        if isinstance(replies, list):
            for reply in cast(list[Any], replies):
                if not isinstance(reply, dict):
                    continue
                reply_payload = cast(dict[str, Any] | None, reply.get("payload"))
                if isinstance(reply_payload, dict) and isinstance(reply_payload.get("apps"), list):
                    observed_apps = cast(list[Any], reply_payload["apps"])
                    break

    matched_app: dict[str, Any] | None = None
    for candidate in observed_apps:
        if not isinstance(candidate, dict):
            continue
        app_payload = cast(dict[str, Any], candidate)
        candidate_app_id = str(app_payload.get("app_id") or app_payload.get("name") or "")
        if candidate_app_id == app_id:
            matched_app = app_payload
            break

    if matched_app is None:
        return {
            "app_present": False,
            "observed_app_state": "missing",
            "app_running": False,
        }

    observed_app_state = str(
        matched_app.get("state") or matched_app.get("status") or "unknown"
    )
    normalized_state = observed_app_state.lower()
    return {
        "app_present": True,
        "observed_app_state": observed_app_state,
        "app_running": normalized_state in {"running", "active", "started", "running_active"},
    }


def run_app_deploy_prepare_verify(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
    node_id: str = "unit-01",
    source_agent: str = "rational",
    lease_ttl_ms: int = 120000,
    timeout_seconds: int = 30,
    tool_adapter: NeuroCliToolAdapter | None = None,
) -> dict[str, Any]:
    deploy_payload = build_app_deploy_plan(
        preset=preset,
        app_id=app_id,
        app_source_dir=app_source_dir,
        board=board,
        build_dir=build_dir,
        artifact_file=artifact_file,
        node_id=node_id,
        source_agent=source_agent,
        lease_ttl_ms=lease_ttl_ms,
    )
    build_plan = cast(dict[str, Any], deploy_payload["build_plan"])
    artifact_admission = cast(dict[str, Any], deploy_payload["artifact_admission"])
    deploy_plan = cast(dict[str, Any], deploy_payload["deploy_plan"])
    adapter = tool_adapter or NeuroCliToolAdapter(
        node=node_id,
        source_agent=source_agent,
        timeout_seconds=timeout_seconds,
    )

    execution: dict[str, Any] = {
        "schema_version": APP_DEPLOY_PREPARE_VERIFY_SCHEMA_VERSION,
        "completed_through": "",
        "cleanup_attempted": False,
    }

    def run_json_step(name: str, argv: list[str], *, expected_status: str | None = None) -> tuple[dict[str, Any], str]:
        command_result = adapter.runner(argv, timeout_seconds)
        try:
            payload = _parse_command_json_result(command_result)
        except ValueError as exc:
            failure_status = str(exc)
            return (
                _build_execution_step_result(
                    name=name,
                    argv=argv,
                    command_result=command_result,
                    payload=None,
                    failure_status=failure_status,
                ),
                failure_status,
            )
        failure_status = _command_payload_failure_status(payload)
        if expected_status is not None and str(payload.get("status") or "") != expected_status:
            failure_status = str(payload.get("status") or "unexpected_status")
        return (
            _build_execution_step_result(
                name=name,
                argv=argv,
                command_result=command_result,
                payload=payload,
                failure_status=failure_status,
            ),
            failure_status,
        )

    steps = cast(list[dict[str, Any]], deploy_plan["steps"])
    preflight_step, preflight_failure = run_json_step(
        "preflight",
        cast(list[str], steps[0]["argv"]),
        expected_status="ready",
    )
    execution["preflight"] = preflight_step
    if preflight_failure:
        return {
            "ok": False,
            "status": "error",
            "command": "app-deploy-prepare-verify",
            "failure_class": "app_deploy_prepare_verify_failed",
            "failure_status": preflight_failure,
            "failed_step": "preflight",
            "build_plan": build_plan,
            "artifact_admission": artifact_admission,
            "deploy_plan": deploy_plan,
            "deploy_execution": execution,
        }

    lease_step, lease_failure = run_json_step(
        "lease_acquire_activate",
        cast(list[str], steps[2]["argv"]),
    )
    execution["lease_acquire"] = lease_step
    lease_acquired = not lease_failure

    failed_step = ""
    failure_status = ""

    if lease_failure:
        failed_step = "lease_acquire_activate"
        failure_status = lease_failure
    else:
        prepare_step, prepare_failure = run_json_step(
            "deploy_prepare",
            cast(list[str], steps[3]["argv"]),
        )
        execution["deploy_prepare"] = prepare_step
        if prepare_failure:
            failed_step = "deploy_prepare"
            failure_status = prepare_failure
        else:
            verify_step, verify_failure = run_json_step(
                "deploy_verify",
                cast(list[str], steps[4]["argv"]),
            )
            execution["deploy_verify"] = verify_step
            if verify_failure:
                failed_step = "deploy_verify"
                failure_status = verify_failure
            else:
                execution["completed_through"] = "deploy_verify"

    if lease_acquired:
        execution["cleanup_attempted"] = True
        release_step, release_failure = run_json_step(
            "lease_release_activate",
            cast(list[str], steps[9]["argv"]),
        )
        execution["lease_release"] = release_step
        leases_step, leases_failure = run_json_step(
            "query_leases",
            cast(list[str], steps[10]["argv"]),
        )
        execution["query_leases"] = leases_step
        leases_payload = cast(dict[str, Any] | None, leases_step.get("result"))
        observed_leases: list[Any] = []
        if isinstance(leases_payload, dict):
            replies = cast(list[Any] | None, leases_payload.get("replies"))
            if isinstance(replies, list):
                for reply in replies:
                    if not isinstance(reply, dict):
                        continue
                    reply_payload = cast(dict[str, Any] | None, reply.get("payload"))
                    if isinstance(reply_payload, dict) and isinstance(reply_payload.get("leases"), list):
                        observed_leases = cast(list[Any], reply_payload["leases"])
                        break
        if release_failure and not failure_status:
            failed_step = "lease_release_activate"
            failure_status = release_failure
        if not leases_failure and observed_leases:
            leases_failure = "cleanup_leases_not_empty"
            execution["query_leases"]["failure_status"] = leases_failure
            execution["query_leases"]["ok"] = False
        if leases_failure and not failure_status:
            failed_step = "query_leases"
            failure_status = leases_failure

    if failure_status:
        return {
            "ok": False,
            "status": "error",
            "command": "app-deploy-prepare-verify",
            "failure_class": "app_deploy_prepare_verify_failed",
            "failure_status": failure_status,
            "failed_step": failed_step,
            "build_plan": build_plan,
            "artifact_admission": artifact_admission,
            "deploy_plan": deploy_plan,
            "deploy_execution": execution,
        }

    return {
        "ok": True,
        "status": "ok",
        "command": "app-deploy-prepare-verify",
        "build_plan": build_plan,
        "artifact_admission": artifact_admission,
        "deploy_plan": deploy_plan,
        "deploy_execution": execution,
    }


def run_app_deploy_activate(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
    node_id: str = "unit-01",
    source_agent: str = "rational",
    lease_ttl_ms: int = 120000,
    start_args: str | None = None,
    timeout_seconds: int = 30,
    activation_approval_decision: str = "pending",
    activation_approval_note: str = "",
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    normalized_approval_decision = _normalize_activation_approval_decision(
        activation_approval_decision,
    )
    deploy_payload = build_app_deploy_plan(
        preset=preset,
        app_id=app_id,
        app_source_dir=app_source_dir,
        board=board,
        build_dir=build_dir,
        artifact_file=artifact_file,
        node_id=node_id,
        source_agent=source_agent,
        lease_ttl_ms=lease_ttl_ms,
        start_args=start_args,
    )
    build_plan = cast(dict[str, Any], deploy_payload["build_plan"])
    artifact_admission = cast(dict[str, Any], deploy_payload["artifact_admission"])
    deploy_plan = cast(dict[str, Any], deploy_payload["deploy_plan"])
    adapter = tool_adapter or NeuroCliToolAdapter(
        node=node_id,
        source_agent=source_agent,
        timeout_seconds=timeout_seconds,
    )

    activation_decision = {
        "approval_required": True,
        "decision": normalized_approval_decision,
        "status": (
            "approved"
            if normalized_approval_decision == "approved"
            else "pending_approval"
            if normalized_approval_decision == "pending"
            else "expired"
            if normalized_approval_decision == "expired"
            else "denied"
        ),
        "activation_resource": str(deploy_plan["activation_resource"]),
        "resolved_app_id": app_id,
        "resolved_lease_id": str(deploy_plan["suggested_activate_lease_id"]),
        "approval_note": activation_approval_note.strip(),
        "resume_hint": "rerun with --approval-decision approve to execute activation",
    }
    execution: dict[str, Any] = {
        "schema_version": APP_DEPLOY_ACTIVATE_SCHEMA_VERSION,
        "completed_through": "",
        "cleanup_attempted": False,
    }
    recovery_candidate_summary: dict[str, Any] | None = None
    rollback_approval: dict[str, Any] | None = None

    if normalized_approval_decision != "approved":
        return {
            "ok": False,
            "status": activation_decision["status"],
            "command": "app-deploy-activate",
            "failure_class": _release_gate_approval_failure_class(
                activation_decision["status"],
                prefix="activation",
            ),
            "failure_status": activation_decision["status"],
            "build_plan": build_plan,
            "artifact_admission": artifact_admission,
            "deploy_plan": deploy_plan,
            "activation_decision": activation_decision,
            "deploy_execution": execution,
        }

    def run_json_step(
        name: str,
        argv: list[str],
        *,
        expected_status: str | None = None,
        allowed_failure_statuses: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], str]:
        command_result = adapter.runner(argv, timeout_seconds)
        try:
            payload = _parse_command_json_result(command_result)
        except ValueError as exc:
            failure_status = str(exc)
            return (
                _build_execution_step_result(
                    name=name,
                    argv=argv,
                    command_result=command_result,
                    payload=None,
                    failure_status=failure_status,
                ),
                failure_status,
            )
        failure_status = _command_payload_failure_status(payload)
        if expected_status is not None and str(payload.get("status") or "") != expected_status:
            failure_status = str(payload.get("status") or "unexpected_status")
        if failure_status in allowed_failure_statuses:
            failure_status = ""
        return (
            _build_execution_step_result(
                name=name,
                argv=argv,
                command_result=command_result,
                payload=payload,
                failure_status=failure_status,
            ),
            failure_status,
        )

    steps = cast(list[dict[str, Any]], deploy_plan["steps"])
    step_indices = {
        "preflight": 0,
        "lease_acquire_activate": 2,
        "deploy_prepare": 3,
        "deploy_verify": 4,
        "deploy_activate": 6,
        "query_apps": 8,
        "lease_release_activate": 9,
        "query_leases": 10,
    }

    failed_step = ""
    failure_status = ""
    lease_acquired = False

    preflight_step, preflight_failure = run_json_step(
        "preflight",
        cast(list[str], steps[step_indices["preflight"]]["argv"]),
        expected_status="ready",
    )
    execution["preflight"] = preflight_step
    if preflight_failure:
        return {
            "ok": False,
            "status": "error",
            "command": "app-deploy-activate",
            "failure_class": "app_deploy_activate_failed",
            "failure_status": preflight_failure,
            "failed_step": "preflight",
            "build_plan": build_plan,
            "artifact_admission": artifact_admission,
            "deploy_plan": deploy_plan,
            "activation_decision": activation_decision,
            "deploy_execution": execution,
        }

    lease_step, lease_failure = run_json_step(
        "lease_acquire_activate",
        cast(list[str], steps[step_indices["lease_acquire_activate"]]["argv"]),
    )
    execution["lease_acquire"] = lease_step
    lease_acquired = not lease_failure
    if lease_failure:
        failed_step = "lease_acquire_activate"
        failure_status = lease_failure
    else:
        prepare_step, prepare_failure = run_json_step(
            "deploy_prepare",
            cast(list[str], steps[step_indices["deploy_prepare"]]["argv"]),
        )
        execution["deploy_prepare"] = prepare_step
        if prepare_failure:
            failed_step = "deploy_prepare"
            failure_status = prepare_failure
        else:
            verify_step, verify_failure = run_json_step(
                "deploy_verify",
                cast(list[str], steps[step_indices["deploy_verify"]]["argv"]),
            )
            execution["deploy_verify"] = verify_step
            if verify_failure:
                failed_step = "deploy_verify"
                failure_status = verify_failure
            else:
                activate_step, activate_failure = run_json_step(
                    "deploy_activate",
                    cast(list[str], steps[step_indices["deploy_activate"]]["argv"]),
                )
                execution["deploy_activate"] = activate_step
                if activate_failure:
                    failed_step = "deploy_activate"
                    failure_status = activate_failure
                else:
                    health_tool_result = adapter.execute(
                        "system_activation_health_guard",
                        {"app_id": app_id, "app": app_id},
                    )
                    health_failure = ""
                    health_payload = dict(health_tool_result.payload)
                    if health_tool_result.status != "ok":
                        health_failure = str(
                            health_payload.get("failure_status")
                            or health_tool_result.status
                            or "activation_health_failed"
                        )
                    else:
                        activation_health = cast(
                            dict[str, Any],
                            health_payload.get("activation_health")
                            or health_payload.get("health_observation")
                            or {},
                        )
                        health_classification = str(
                            activation_health.get("classification") or "unknown"
                        )
                        if health_classification != "healthy":
                            health_failure = (
                                health_classification
                                if health_classification != "unknown"
                                else "activation_health_not_healthy"
                            )
                    execution["activation_health_guard"] = _build_tool_execution_step_result(
                        name="activation_health_guard",
                        tool_name="system_activation_health_guard",
                        tool_result=health_tool_result,
                        failure_status=health_failure,
                    )
                    if health_failure:
                        lease_observation_result = adapter.execute(
                            "system_query_leases",
                            {
                                "app_id": app_id,
                                "app": app_id,
                                "reason": "activation_rollback_candidate_lease_observation",
                            },
                        )
                        lease_observation_failure = ""
                        if lease_observation_result.status != "ok":
                            lease_observation_failure = str(
                                lease_observation_result.payload.get("failure_status")
                                or lease_observation_result.status
                                or "rollback_candidate_lease_observation_failed"
                            )
                        execution["rollback_candidate_lease_observation"] = _build_tool_execution_step_result(
                            name="rollback_candidate_lease_observation",
                            tool_name="system_query_leases",
                            tool_result=lease_observation_result,
                            failure_status=lease_observation_failure,
                        )
                        recovery_candidate_summary = _build_recovery_candidate_summary(
                            activation_health=activation_health,
                            lease_observation=lease_observation_result.to_dict(),
                            activate_failed_payload={
                                "target_app_id": app_id,
                                "artifact_id": str(
                                    cast(
                                        dict[str, Any],
                                        artifact_admission.get("source_identity") or {},
                                    ).get("build_id")
                                    or artifact_admission.get("artifact_sha256")
                                    or ""
                                ),
                                "activation_result": health_failure,
                                "status": health_failure,
                            },
                        )
                        if health_failure == "rollback_required":
                            rollback_approval = _build_guarded_rollback_approval(
                                tool_adapter=adapter,
                                recovery_candidate_summary=recovery_candidate_summary,
                            )
                        failed_step = "activation_health_guard"
                        failure_status = health_failure
                    else:
                        query_apps_step, query_apps_failure = run_json_step(
                            "query_apps",
                            cast(list[str], steps[step_indices["query_apps"]]["argv"]),
                        )
                        query_apps_payload = cast(
                            dict[str, Any] | None,
                            query_apps_step.get("result"),
                        )
                        if isinstance(query_apps_payload, dict):
                            query_app_state = _extract_query_apps_target_state(
                                query_apps_payload,
                                app_id=app_id,
                            )
                            query_apps_step["observed_app_state"] = str(
                                query_app_state["observed_app_state"]
                            )
                            query_apps_step["app_present"] = bool(
                                query_app_state["app_present"]
                            )
                            if not query_apps_failure and not bool(query_app_state["app_running"]):
                                query_apps_failure = "app_not_running_after_activate"
                                query_apps_step["failure_status"] = query_apps_failure
                                query_apps_step["ok"] = False
                        execution["query_apps"] = query_apps_step
                        if query_apps_failure:
                            failed_step = "query_apps"
                            failure_status = query_apps_failure
                        else:
                            execution["completed_through"] = "query_apps"

    if lease_acquired:
        execution["cleanup_attempted"] = True
        release_step, release_failure = run_json_step(
            "lease_release_activate",
            cast(list[str], steps[step_indices["lease_release_activate"]]["argv"]),
            allowed_failure_statuses=("lease_not_found",),
        )
        execution["lease_release"] = release_step
        leases_step, leases_failure = run_json_step(
            "query_leases",
            cast(list[str], steps[step_indices["query_leases"]]["argv"]),
        )
        execution["query_leases"] = leases_step
        leases_payload = cast(dict[str, Any] | None, leases_step.get("result"))
        observed_leases: list[Any] = []
        if isinstance(leases_payload, dict):
            replies = cast(list[Any] | None, leases_payload.get("replies"))
            if isinstance(replies, list):
                for reply in replies:
                    if not isinstance(reply, dict):
                        continue
                    reply_payload = cast(dict[str, Any] | None, reply.get("payload"))
                    if isinstance(reply_payload, dict) and isinstance(reply_payload.get("leases"), list):
                        observed_leases = cast(list[Any], reply_payload["leases"])
                        break
        if release_failure and not failure_status:
            failed_step = "lease_release_activate"
            failure_status = release_failure
        if not leases_failure and observed_leases:
            leases_failure = "cleanup_leases_not_empty"
            execution["query_leases"]["failure_status"] = leases_failure
            execution["query_leases"]["ok"] = False
        if leases_failure and not failure_status:
            failed_step = "query_leases"
            failure_status = leases_failure

    if failure_status:
        payload = {
            "ok": False,
            "status": "error",
            "command": "app-deploy-activate",
            "failure_class": "app_deploy_activate_failed",
            "failure_status": failure_status,
            "failed_step": failed_step,
            "build_plan": build_plan,
            "artifact_admission": artifact_admission,
            "deploy_plan": deploy_plan,
            "activation_decision": activation_decision,
            "deploy_execution": execution,
        }
        if recovery_candidate_summary is not None:
            payload["recovery_candidate_summary"] = recovery_candidate_summary
        if rollback_approval is not None:
            payload["rollback_approval"] = rollback_approval
        return payload

    return {
        "ok": True,
        "status": "ok",
        "command": "app-deploy-activate",
        "build_plan": build_plan,
        "artifact_admission": artifact_admission,
        "deploy_plan": deploy_plan,
        "activation_decision": activation_decision,
        "deploy_execution": execution,
    }


def run_app_deploy_rollback(
    *,
    app_id: str,
    node_id: str = "unit-01",
    source_agent: str = "rational",
    lease_id: str | None = None,
    rollback_reason: str = "guarded_rollback_after_activation_health_failure",
    timeout_seconds: int = 30,
    rollback_approval_decision: str = "pending",
    rollback_approval_note: str = "",
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    normalized_app_id = _validate_app_build_app_id(app_id)
    normalized_node_id = _validate_deploy_plan_identifier(node_id, "invalid_deploy_node_id")
    normalized_source_agent = _validate_deploy_plan_identifier(
        source_agent,
        "invalid_deploy_source_agent",
    )
    normalized_approval_decision = _normalize_activation_approval_decision(
        rollback_approval_decision,
    )
    normalized_lease_id = (lease_id or "").strip()
    rollback_decision = {
        "approval_required": True,
        "decision": normalized_approval_decision,
        "status": (
            "approved"
            if normalized_approval_decision == "approved"
            else "pending_approval"
            if normalized_approval_decision == "pending"
            else "expired"
            if normalized_approval_decision == "expired"
            else "denied"
        ),
        "rollback_resource": f"update/app/{normalized_app_id}/rollback",
        "resolved_app_id": normalized_app_id,
        "requested_lease_id": normalized_lease_id,
        "rollback_reason": rollback_reason,
        "approval_note": rollback_approval_note.strip(),
        "resume_hint": "rerun with --approval-decision approve to execute rollback",
        "node_id": normalized_node_id,
        "source_agent": normalized_source_agent,
    }
    execution: dict[str, Any] = {
        "schema_version": APP_DEPLOY_ROLLBACK_SCHEMA_VERSION,
        "completed_through": "",
        "observation_attempted": False,
    }
    rollback_failure_summary: dict[str, Any] | None = None

    if normalized_approval_decision != "approved":
        return {
            "ok": False,
            "status": rollback_decision["status"],
            "command": "app-deploy-rollback",
            "failure_class": _release_gate_approval_failure_class(
                rollback_decision["status"],
                prefix="rollback",
            ),
            "failure_status": rollback_decision["status"],
            "rollback_decision": rollback_decision,
            "rollback_execution": execution,
        }

    adapter = tool_adapter or NeuroCliToolAdapter(
        node=normalized_node_id,
        source_agent=normalized_source_agent,
        timeout_seconds=timeout_seconds,
    )
    rollback_result = adapter.execute(
        "system_rollback_app",
        {
            "app_id": normalized_app_id,
            "app": normalized_app_id,
            **({"lease_id": normalized_lease_id} if normalized_lease_id else {}),
            "reason": rollback_reason,
        },
    )
    rollback_failure = _tool_execution_failure_status(rollback_result)
    execution["rollback"] = _build_tool_execution_step_result(
        name="rollback",
        tool_name="system_rollback_app",
        tool_result=rollback_result,
        failure_status=rollback_failure,
    )

    failed_step = ""
    failure_status = ""
    if rollback_failure:
        failed_step = "rollback"
        failure_status = rollback_failure
    else:
        execution["observation_attempted"] = True
        query_apps_result = adapter.execute(
            "system_query_apps",
            {
                "app_id": normalized_app_id,
                "app": normalized_app_id,
                "reason": "post_rollback_app_observation",
            },
        )
        query_apps_failure = _tool_execution_failure_status(query_apps_result)
        execution["query_apps"] = _build_tool_execution_step_result(
            name="query_apps",
            tool_name="system_query_apps",
            tool_result=query_apps_result,
            failure_status=query_apps_failure,
        )
        if not query_apps_failure:
            query_apps_state = _extract_rollback_query_apps_state(
                query_apps_result.to_dict(),
                app_id=normalized_app_id,
            )
            execution["query_apps"]["observed_app_state"] = str(
                query_apps_state["observed_app_state"]
            )
            execution["query_apps"]["app_present"] = bool(
                query_apps_state["app_present"]
            )
            if bool(query_apps_state["app_running"]):
                query_apps_failure = "app_still_running_after_rollback"
                execution["query_apps"]["failure_status"] = query_apps_failure
                execution["query_apps"]["ok"] = False
        query_leases_result = adapter.execute(
            "system_query_leases",
            {
                "app_id": normalized_app_id,
                "app": normalized_app_id,
                "reason": "post_rollback_lease_observation",
            },
        )
        query_leases_failure = _tool_execution_failure_status(query_leases_result)
        execution["query_leases"] = _build_tool_execution_step_result(
            name="query_leases",
            tool_name="system_query_leases",
            tool_result=query_leases_result,
            failure_status=query_leases_failure,
        )
        if not query_leases_failure:
            rollback_resource = f"update/app/{normalized_app_id}/rollback"
            matching_lease_ids = _extract_matching_lease_ids_for_resource(
                query_leases_result.to_dict(),
                rollback_resource,
            )
            execution["query_leases"]["rollback_resource"] = rollback_resource
            execution["query_leases"]["matching_lease_ids"] = matching_lease_ids
            if matching_lease_ids:
                query_leases_failure = "rollback_lease_still_held_after_rollback"
                execution["query_leases"]["failure_status"] = query_leases_failure
                execution["query_leases"]["ok"] = False
        execution["completed_through"] = "query_leases"
        if query_apps_failure:
            failed_step = "query_apps"
            failure_status = query_apps_failure
        elif query_leases_failure:
            failed_step = "query_leases"
            failure_status = query_leases_failure

    if failure_status:
        rollback_failure_summary = _build_rollback_failure_summary(
            failed_step=failed_step,
            failure_status=failure_status,
            rollback_decision=rollback_decision,
            rollback_execution=execution,
        )
        return {
            "ok": False,
            "status": "error",
            "command": "app-deploy-rollback",
            "failure_class": "app_deploy_rollback_failed",
            "failure_status": failure_status,
            "failed_step": failed_step,
            "rollback_decision": rollback_decision,
            "rollback_execution": execution,
            "rollback_failure_summary": rollback_failure_summary,
        }

    return {
        "ok": True,
        "status": "ok",
        "command": "app-deploy-rollback",
        "rollback_decision": rollback_decision,
        "rollback_execution": execution,
    }


def _extract_observed_resource_names(leases: list[Any]) -> list[str]:
    observed_resources: list[str] = []
    for lease in leases:
        if not isinstance(lease, dict):
            continue
        lease_dict = cast(dict[str, Any], lease)
        for key in ("resource", "resource_name", "lease_name", "name"):
            value = lease_dict.get(key)
            if isinstance(value, str) and value:
                observed_resources.append(value)
                break
    return sorted(set(observed_resources))


def _extract_observed_lease_rows(lease_observation: dict[str, Any]) -> list[dict[str, Any]]:
    if lease_observation.get("status") != "ok":
        return []
    payload = cast(dict[str, Any] | None, lease_observation.get("payload"))
    if not isinstance(payload, dict):
        return []
    result_payload = cast(dict[str, Any] | None, payload.get("result"))
    if not isinstance(result_payload, dict):
        return []
    replies = cast(list[Any] | None, result_payload.get("replies"))
    if not isinstance(replies, list) or not replies:
        return []
    first_reply = cast(dict[str, Any], replies[0])
    reply_payload = cast(dict[str, Any] | None, first_reply.get("payload"))
    if not isinstance(reply_payload, dict):
        return []
    leases = cast(list[Any] | None, reply_payload.get("leases"))
    if not isinstance(leases, list):
        return []
    rows: list[dict[str, Any]] = []
    for lease in leases:
        if isinstance(lease, dict):
            rows.append(cast(dict[str, Any], lease))
    return rows


def _extract_matching_lease_ids_for_resource(
    lease_observation: dict[str, Any],
    resource_name: str,
) -> list[str]:
    if not resource_name:
        return []
    matching_lease_ids: list[str] = []
    for lease in _extract_observed_lease_rows(lease_observation):
        resource = str(lease.get("resource") or "")
        if resource != resource_name:
            continue
        lease_id = str(lease.get("lease_id") or "")
        if lease_id:
            matching_lease_ids.append(lease_id)
    return matching_lease_ids


def _extract_activate_failed_event_payload(
    events: list[PerceptionEvent],
) -> dict[str, Any]:
    for event in events:
        if event.semantic_topic == "unit.lifecycle.activate_failed":
            return dict(event.payload)
    return {}


def _build_recovery_candidate_summary(
    *,
    activation_health: dict[str, Any],
    lease_observation: dict[str, Any],
    activate_failed_payload: dict[str, Any],
) -> dict[str, Any]:
    app_id = str(activation_health.get("app_id") or activate_failed_payload.get("target_app_id") or "")
    lease_resource = f"update/app/{app_id}/rollback" if app_id else ""
    matching_lease_ids = _extract_matching_lease_ids_for_resource(
        lease_observation,
        lease_resource,
    )
    observed_health = str(activation_health.get("classification") or "unknown")
    observed_app_state = str(activation_health.get("observed_app_state") or "unknown")
    return {
        "trigger_topic": "unit.lifecycle.activate_failed",
        "app_id": app_id,
        "artifact_id": str(activate_failed_payload.get("artifact_id") or ""),
        "activation_result": str(
            activate_failed_payload.get("activation_result")
            or activate_failed_payload.get("status")
            or "activate_failed"
        ),
        "observed_health": observed_health,
        "rollback_decision": (
            "operator_review_required"
            if observed_health == "rollback_required"
            else "not_required"
        ),
        "final_app_state": observed_app_state,
        "lease_resource": lease_resource,
        "lease_ownership_status": "held" if matching_lease_ids else "missing",
        "matching_lease_ids": matching_lease_ids,
        "ready_for_rollback_consideration": bool(
            activation_health.get("ready_for_rollback_consideration", False)
        ),
    }


def _extract_observed_app_rows(apps_observation: dict[str, Any]) -> list[dict[str, Any]]:
    if apps_observation.get("status") != "ok":
        return []
    payload = cast(dict[str, Any] | None, apps_observation.get("payload"))
    if not isinstance(payload, dict):
        return []
    result_payload = cast(dict[str, Any] | None, payload.get("result"))
    if not isinstance(result_payload, dict):
        return []
    replies = cast(list[Any] | None, result_payload.get("replies"))
    if not isinstance(replies, list) or not replies:
        return []
    first_reply = cast(dict[str, Any], replies[0])
    reply_payload = cast(dict[str, Any] | None, first_reply.get("payload"))
    if not isinstance(reply_payload, dict):
        return []
    apps = cast(list[Any] | None, reply_payload.get("apps"))
    if not isinstance(apps, list):
        return []
    rows: list[dict[str, Any]] = []
    for app in apps:
        if isinstance(app, dict):
            rows.append(cast(dict[str, Any], app))
    return rows


def _extract_rollback_query_apps_state(
    apps_observation: dict[str, Any],
    *,
    app_id: str,
) -> dict[str, Any]:
    matched_app: dict[str, Any] | None = None
    for candidate in _extract_observed_app_rows(apps_observation):
        candidate_app_id = str(candidate.get("app_id") or candidate.get("name") or "")
        if candidate_app_id == app_id:
            matched_app = candidate
            break

    if matched_app is None:
        return {
            "app_present": False,
            "observed_app_state": "missing",
            "app_running": False,
        }

    observed_app_state = str(
        matched_app.get("state") or matched_app.get("status") or "unknown"
    )
    normalized_state = observed_app_state.lower()
    return {
        "app_present": True,
        "observed_app_state": observed_app_state,
        "app_running": normalized_state in {"running", "active", "started", "running_active"},
    }


def _build_rollback_failure_summary(
    *,
    failed_step: str,
    failure_status: str,
    rollback_decision: dict[str, Any],
    rollback_execution: dict[str, Any],
) -> dict[str, Any]:
    rollback_step = cast(dict[str, Any], rollback_execution.get("rollback") or {})
    rollback_result = cast(dict[str, Any], rollback_step.get("result") or {})
    resolved_args = cast(dict[str, Any], rollback_result.get("resolved_args") or {})

    category = "rollback_execution"
    recommended_next_actions: list[str] = [
        "inspect rollback result and query apps/leases evidence before retry",
    ]
    if failure_status == "rollback_args_unresolved":
        category = "argument_resolution"
        recommended_next_actions = [
            "provide explicit rollback lease identity or verify rollback lease discovery before retry",
        ]
    elif failure_status == "lease_holder_mismatch":
        category = "lease_ownership"
        recommended_next_actions = [
            "reacquire or release the rollback lease with the correct source_agent before retry",
        ]
    elif failure_status == "lease_not_found":
        category = "lease_resolution"
        recommended_next_actions = [
            "query rollback leases and confirm update/app/<app_id>/rollback is held before retry",
        ]
    elif failure_status == "no_reply":
        category = "transport"
        recommended_next_actions = [
            "verify Unit and router reachability, then rerun preflight or state sync before retry",
        ]
    elif failure_status == "app_still_running_after_rollback":
        category = "post_rollback_observation"
        recommended_next_actions = [
            "inspect app lifecycle state and confirm rollback target actually stopped before retry",
        ]
    elif failure_status == "rollback_lease_still_held_after_rollback":
        category = "post_rollback_cleanup"
        recommended_next_actions = [
            "inspect rollback lease ownership and release stale rollback lease state before retry",
        ]

    summary = {
        "app_id": str(rollback_decision.get("resolved_app_id") or ""),
        "failed_step": failed_step,
        "failure_status": failure_status,
        "failure_category": category,
        "rollback_resource": str(rollback_decision.get("rollback_resource") or ""),
        "requested_lease_id": str(rollback_decision.get("requested_lease_id") or ""),
        "resolved_lease_id": str(resolved_args.get("lease_id") or ""),
        "source_agent": str(rollback_decision.get("source_agent") or ""),
        "recommended_next_actions": recommended_next_actions,
    }

    if failed_step == "query_apps":
        query_apps_step = cast(dict[str, Any], rollback_execution.get("query_apps") or {})
        summary["observed_app_state"] = str(query_apps_step.get("observed_app_state") or "unknown")
        summary["app_present"] = bool(query_apps_step.get("app_present", False))
    elif failed_step == "query_leases":
        query_leases_step = cast(dict[str, Any], rollback_execution.get("query_leases") or {})
        summary["matching_lease_ids"] = list(query_leases_step.get("matching_lease_ids") or [])

    tool_failure_class = str(rollback_result.get("failure_class") or "")
    if tool_failure_class:
        summary["tool_failure_class"] = tool_failure_class
    return summary


def _build_operator_requirements(
    approval_request: dict[str, Any],
    *,
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    adapter = tool_adapter or FakeUnitToolAdapter()
    request_payload = cast(dict[str, Any], approval_request["payload"])
    raw_required_resources = request_payload.get("required_resources")
    required_resources: list[str] = []
    if isinstance(raw_required_resources, (list, tuple)):
        required_resources = [
            str(item) for item in cast(list[Any] | tuple[Any, ...], raw_required_resources)
        ]
    contract_payload = cast(dict[str, Any], request_payload.get("contract") or {})
    plan_quality = cast(dict[str, Any], request_payload.get("plan_quality") or {})
    skill_requirements = cast(
        dict[str, Any],
        plan_quality.get("skill_requirements") or request_payload.get("skill_requirements") or {},
    )
    mcp_requirements = cast(
        dict[str, Any],
        plan_quality.get("mcp_requirements") or request_payload.get("mcp_requirements") or {},
    )

    lease_observation = adapter.execute(
        "system_query_leases",
        {"reason": "approval_operator_inspect"},
    ).to_dict()
    apps_observation = adapter.execute(
        "system_query_apps",
        {"reason": "approval_operator_inspect"},
    ).to_dict()
    state_sync_observation = adapter.execute(
        "system_state_sync",
        {"reason": "approval_operator_inspect"},
    ).to_dict()

    observed_leases = _extract_observed_lease_rows(lease_observation)
    observed_apps = _extract_observed_app_rows(apps_observation)

    requested_args = cast(dict[str, Any], request_payload.get("requested_args") or {})
    recovery_candidate_summary = cast(
        dict[str, Any],
        request_payload.get("recovery_candidate_summary") or {},
    )
    target_app_id = str(
        requested_args.get("app_id")
        or requested_args.get("app")
        or request_payload.get("target_app_id")
        or recovery_candidate_summary.get("app_id")
        or ""
    )
    if not target_app_id and len(observed_apps) == 1:
        observed_app = observed_apps[0]
        target_app_id = str(
            observed_app.get("app_id")
            or observed_app.get("name")
            or observed_app.get("app")
            or ""
        )

    observed_resources = _extract_observed_resource_names(observed_leases)
    resolved_required_resources: list[str] = []
    unresolved_required_resources: list[str] = []
    for resource in required_resources:
        if resource == "app_control_lease":
            if target_app_id:
                resolved_required_resources.append(f"app/{target_app_id}/control")
            else:
                unresolved_required_resources.append(resource)
            continue
        if resource == "update_rollback_lease":
            if target_app_id:
                resolved_required_resources.append(f"update/app/{target_app_id}/rollback")
            else:
                unresolved_required_resources.append(resource)
            continue
        resolved_required_resources.append(resource)

    matching_lease_ids: list[str] = []
    for lease in observed_leases:
        resource = str(lease.get("resource") or "")
        if resource not in resolved_required_resources:
            continue
        lease_id = str(lease.get("lease_id") or "")
        if lease_id:
            matching_lease_ids.append(lease_id)

    missing_required_resources = [
        resource
        for resource in resolved_required_resources
        if resource not in observed_resources
    ]
    missing_required_resources.extend(unresolved_required_resources)
    missing_operational_prerequisites: list[str] = []
    if (
        bool(skill_requirements.get("workflow_plan_required"))
        and not bool(skill_requirements.get("workflow_plan_evidence_present"))
    ):
        missing_operational_prerequisites.append("workflow_plan_evidence")

    return {
        "resource": str(contract_payload.get("resource") or request_payload.get("tool_name") or ""),
        "required_resources": required_resources,
        "resolved_required_resources": resolved_required_resources,
        "unresolved_required_resources": unresolved_required_resources,
        "observed_resources": observed_resources,
        "missing_required_resources": missing_required_resources,
        "resource_requirements_satisfied": not missing_required_resources,
        "plan_quality": plan_quality or None,
        "skill_requirements": skill_requirements or None,
        "mcp_requirements": mcp_requirements or None,
        "workflow_plan_required": bool(skill_requirements.get("workflow_plan_required")),
        "workflow_plan_evidence_present": bool(
            skill_requirements.get("workflow_plan_evidence_present")
        ),
        "missing_operational_prerequisites": missing_operational_prerequisites,
        "cleanup_hint": request_payload.get("cleanup_hint"),
        "target_app_id": target_app_id,
        "matching_lease_ids": matching_lease_ids,
        "recovery_candidate_summary": recovery_candidate_summary or None,
        "lease_observation": lease_observation,
        "apps_observation": apps_observation,
        "state_sync_observation": state_sync_observation,
    }


def build_approval_context(
    data_store: CoreDataStore,
    approval_request: dict[str, Any],
    *,
    tool_adapter: Any | None = None,
    resumed_execution: dict[str, Any] | None = None,
    operator_requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_execution_span_id = str(approval_request["source_execution_span_id"])
    source_execution_span = data_store.get_execution_span(source_execution_span_id)
    source_audit_id = None
    if source_execution_span is not None:
        source_audit_id = source_execution_span["payload"].get("audit_id")
    source_execution_evidence = (
        data_store.build_execution_evidence(
            source_execution_span_id,
            str(source_audit_id),
        )
        if source_audit_id is not None
        else None
    )

    resumed_execution_evidence: dict[str, Any] | None = None
    if resumed_execution is not None:
        resumed_execution_evidence = data_store.build_execution_evidence(
            str(resumed_execution["execution_span_id"]),
            str(resumed_execution["audit_id"]),
        )
    else:
        resumed_execution_span_id = approval_request["payload"].get(
            "resumed_execution_span_id"
        )
        if resumed_execution_span_id is not None:
            resumed_execution_span = data_store.get_execution_span(
                str(resumed_execution_span_id)
            )
            if resumed_execution_span is not None:
                resumed_audit_id = resumed_execution_span["payload"].get("audit_id")
                if resumed_audit_id is not None:
                    resumed_execution_evidence = data_store.build_execution_evidence(
                        str(resumed_execution_span_id),
                        str(resumed_audit_id),
                    )

    effective_operator_requirements = (
        operator_requirements
        if operator_requirements is not None
        else _build_operator_requirements(
            approval_request,
            tool_adapter=tool_adapter,
        )
    )
    if isinstance(source_execution_evidence, dict):
        audit_record = cast(
            dict[str, Any],
            source_execution_evidence.get("audit_record") or {},
        )
        audit_payload = cast(dict[str, Any], audit_record.get("payload") or {})
        rational_plan_evidence = cast(
            dict[str, Any],
            audit_payload.get("rational_plan_evidence") or {},
        )
        if rational_plan_evidence:
            merged_operator_requirements: dict[str, Any] = {
                **effective_operator_requirements,
                "rational_plan_evidence": rational_plan_evidence,
            }
            effective_operator_requirements = merged_operator_requirements

    return {
        "source_execution_span": source_execution_span,
        "source_execution_evidence": source_execution_evidence,
        "resumed_execution_evidence": resumed_execution_evidence,
        "operator_requirements": effective_operator_requirements,
        "recovery_candidate_summary": effective_operator_requirements.get(
            "recovery_candidate_summary"
        ),
    }


def sample_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "evt-demo-callback-001",
            "source_kind": "unit_app",
            "source_node": "unit-01",
            "source_app": "neuro_demo_gpio",
            "event_type": "callback",
            "semantic_topic": "unit.callback",
            "timestamp_wall": "2026-05-04T00:00:00Z",
            "priority": 80,
            "dedupe_key": "demo-callback-001",
            "policy_tags": ["demo", "no_model"],
            "payload": {"callback_enabled": True},
        },
        {
            "event_id": "evt-time-tick-001",
            "source_kind": "clock",
            "event_type": "time.tick",
            "semantic_topic": "time.tick",
            "timestamp_wall": "2026-05-04T00:00:01Z",
            "priority": 10,
            "dedupe_key": "tick-001",
            "policy_tags": ["clock"],
            "payload": {"period_ms": 1000},
        },
    ]


def build_user_prompt_event(input_text: str) -> list[dict[str, Any]]:
    lowered = input_text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    semantic_topic = "user.input"
    has_app_target = "app" in tokens or "apps" in tokens or "application" in tokens
    target_app_id = _extract_explicit_app_id(input_text)
    if "restart" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.restart"
    elif "start" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.start"
    elif "stop" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.stop"
    elif "unload" in tokens and has_app_target:
        semantic_topic = "user.input.control.app.unload"
    elif "lease" in tokens or "leases" in tokens:
        semantic_topic = "user.input.query.leases"
    elif has_app_target:
        semantic_topic = "user.input.query.apps"
    elif "device" in tokens or "network" in tokens or "status" in tokens:
        semantic_topic = "user.input.query.device"
    elif "capability" in tokens or "capabilities" in tokens:
        semantic_topic = "user.input.capabilities"
    return [
        {
            "event_id": new_id("evt"),
            "source_kind": "user",
            "source_app": target_app_id,
            "event_type": "user.input",
            "semantic_topic": semantic_topic,
            "timestamp_wall": "2026-05-04T00:00:02Z",
            "priority": 70,
            "policy_tags": ["user_input", "agent_run"],
            "payload": {
                "text": input_text,
                **({"target_app_id": target_app_id} if target_app_id else {}),
            },
        }
    ]


def _extract_explicit_app_id(input_text: str) -> str | None:
    candidate_pattern = re.compile(r"[a-z0-9][a-z0-9_-]{2,}")
    stopwords = {
        "restart",
        "start",
        "stop",
        "unload",
        "app",
        "apps",
        "application",
        "please",
        "the",
        "now",
        "current",
        "show",
        "query",
        "device",
        "status",
        "lease",
        "leases",
        "unit",
    }
    lowered = input_text.lower()
    for match in candidate_pattern.finditer(lowered):
        candidate = match.group(0)
        if candidate in stopwords:
            continue
        if candidate.startswith("neuro") or "_" in candidate or "-" in candidate:
            return candidate
    return None


def _extract_target_app_id_from_events(events: list[PerceptionEvent]) -> str | None:
    for event in events:
        payload_target_app_id = str(event.payload.get("target_app_id") or "")
        if payload_target_app_id:
            return payload_target_app_id
        if event.source_kind == "user" and event.source_app:
            return str(event.source_app)
        if event.semantic_topic == "unit.lifecycle.activate_failed" and event.source_app:
            return str(event.source_app)
    return None


class NoModelCoreWorkflow:
    def __init__(
        self,
        data_store: CoreDataStore | None = None,
        affective_agent: Any | None = None,
        rational_agent: Any | None = None,
        memory: LongTermMemory | None = None,
        tool_adapter: Any | None = None,
        tool_policy: ReadOnlyToolPolicy | None = None,
        maf_runtime_profile: MafRuntimeProfile | None = None,
        provider_client: Any | None = None,
        rational_backend: str = "auto",
        allow_model_call: bool = False,
        copilot_agent_factory: Any | None = None,
        event_router: PerceptionEventRouter | None = None,
        session_manager: CoreSessionManager | None = None,
        federation_route_provider: Callable[[PerceptionFrame, dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> None:
        self.maf_runtime_profile = maf_runtime_profile or build_maf_runtime_profile()
        self.data_store = data_store or CoreDataStore()
        self.event_router = event_router or PerceptionEventRouter()
        self.session_manager = session_manager or CoreSessionManager(self.data_store)
        self.affective_agent = affective_agent or build_affective_agent_adapter(
            self.maf_runtime_profile,
            provider_client=provider_client,
        )
        self.rational_agent = rational_agent or build_rational_agent_adapter(
            self.maf_runtime_profile,
            provider_client=provider_client,
            rational_backend=rational_backend,
            allow_model_call=allow_model_call,
            copilot_agent_factory=copilot_agent_factory,
        )
        self.memory = memory or FakeLongTermMemory()
        self.tool_adapter = tool_adapter or FakeUnitToolAdapter()
        self.tool_policy = tool_policy or ReadOnlyToolPolicy()
        self.federation_route_provider = federation_route_provider

    def run(
        self,
        raw_events: Iterable[dict[str, Any]],
        use_db_events: bool = False,
        query_limit: int = 100,
        min_priority: int = 0,
        topic: str | None = None,
        session_id: str | None = None,
        event_source: str = "provided",
    ) -> WorkflowResult:
        steps: list[str] = []
        execution_span_id = new_id("span")
        resolved_session_id = self.session_manager.resolve_session_id(session_id)
        initial_session_context = self.session_manager.build_context(
            resolved_session_id,
            limit=5,
        )

        steps.append("event_ingress")
        events = self.event_router.route(raw_events)
        self.data_store.persist_execution_span(
            execution_span_id,
            "running",
            {
                "event_source": event_source,
                "normalized_event_count": len(events),
                "session_id": resolved_session_id,
            },
            session_id=resolved_session_id,
        )

        steps.append("database_persistence")
        for event in events:
            self.data_store.persist_event(event)

        steps.append("perception_frame_build")
        frame = self._build_frame(events)

        if use_db_events:
            steps.append("database_query")
            db_events = self.data_store.query_events(
                limit=query_limit,
                min_priority=min_priority,
                topic=topic,
            )
            if db_events:
                steps.append("frame_build_from_db")
                frame_data = self.data_store.build_frame(db_events)
                frame = PerceptionFrame(**frame_data)

        source_fact_refs = self._persist_frame_facts(execution_span_id, frame, events)
        activate_failed_payload = _extract_activate_failed_event_payload(events)

        steps.append("session_context_load")
        target_app_id = _extract_target_app_id_from_events(events)
        session_context: dict[str, Any] = {
            "execution_span_id": execution_span_id,
            **initial_session_context,
            "maf_runtime": self.maf_runtime_metadata(),
            "memory_runtime": self.memory_runtime_metadata(),
            **({"target_app_id": target_app_id} if target_app_id else {}),
        }
        session_context["skill_descriptors"] = [self._skill_descriptor_summary()]
        session_context["mcp_descriptors"] = [self._mcp_descriptor_summary()]
        federation_route_evidence: dict[str, Any] | None = None
        if callable(self.federation_route_provider):
            federation_route_evidence = self.federation_route_provider(
                frame,
                dict(session_context),
            )
            if isinstance(federation_route_evidence, dict) and federation_route_evidence:
                session_context["federation_route_evidence"] = federation_route_evidence
                route_decision = cast(
                    dict[str, Any],
                    federation_route_evidence.get("route_decision") or {},
                )
                self.data_store.persist_fact(
                    execution_span_id,
                    "federation_route",
                    str(
                        route_decision.get("target_node")
                        or federation_route_evidence.get("command")
                        or frame.frame_id
                    ),
                    federation_route_evidence,
                )

        steps.append("long_term_memory_lookup_stub")
        memory_items = self.memory.lookup(frame)
        session_context["memory_lookup_count"] = len(memory_items)
        session_context["memory_runtime"] = self.memory_runtime_metadata()
        candidate_payloads: list[dict[str, Any]] = []
        screened_candidate_payloads: list[dict[str, Any]] = []
        if hasattr(self.memory, "propose_candidates"):
            for candidate in self.memory.propose_candidates(frame):
                candidate_payload = dict(candidate)
                candidate_payload["source_fact_refs"] = list(source_fact_refs)
                governance = dict(candidate_payload.get("memory_governance") or {})
                governance["source_fact_refs"] = list(source_fact_refs)
                governance["source_fact_ref_count"] = len(source_fact_refs)
                candidate_payload["memory_governance"] = governance
                candidate_payloads.append(candidate_payload)
            screen_candidates = getattr(self.memory, "screen_candidates", None)
            if callable(screen_candidates):
                screen_candidates_fn = cast(
                    Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
                    screen_candidates,
                )
                screened_candidate_payloads = screen_candidates_fn(candidate_payloads)
            else:
                screened_candidate_payloads = candidate_payloads
            for candidate_payload in screened_candidate_payloads:
                self.data_store.persist_memory_candidate(
                    execution_span_id,
                    str(candidate_payload.get("semantic_topic") or "unknown"),
                    candidate_payload,
                )
            session_context["memory_candidate_count"] = len(screened_candidate_payloads)
            session_context["accepted_memory_candidate_count"] = sum(
                1
                for candidate_payload in screened_candidate_payloads
                if str(
                    dict(candidate_payload.get("memory_governance") or {}).get(
                        "lifecycle_state"
                    )
                )
                == "accepted"
            )
            session_context["rejected_memory_candidate_count"] = sum(
                1
                for candidate_payload in screened_candidate_payloads
                if str(
                    dict(candidate_payload.get("memory_governance") or {}).get(
                        "lifecycle_state"
                    )
                )
                == "rejected"
            )
        commit_candidates = getattr(self.memory, "commit_candidates", None)
        if callable(commit_candidates):
            commit_candidates_fn = cast(
                Callable[[str, list[dict[str, Any]]], list[str]],
                commit_candidates,
            )
            committed_memory_ids = commit_candidates_fn(
                execution_span_id,
                screened_candidate_payloads or candidate_payloads,
            )
            session_context["committed_memory_count"] = len(committed_memory_ids)
            session_context["committed_memory_ids"] = committed_memory_ids
            session_context["memory_runtime"] = self.memory_runtime_metadata()
        self.data_store.persist_fact(
            execution_span_id,
            "memory_governance_summary",
            frame.frame_id,
            {
                "candidate_count": len(screened_candidate_payloads or candidate_payloads),
                "accepted_candidate_count": int(
                    session_context.get("accepted_memory_candidate_count") or 0
                ),
                "rejected_candidate_count": int(
                    session_context.get("rejected_memory_candidate_count") or 0
                ),
                "committed_memory_count": int(
                    session_context.get("committed_memory_count") or 0
                ),
                "source_fact_ref_count": len(source_fact_refs),
                "memory_runtime": self.memory_runtime_metadata(),
            },
        )

        available_tools = self._available_tool_context()
        session_context["available_tools"] = available_tools
        affective_runtime_context = self._build_affective_runtime_context(frame, events)
        session_context["affective_runtime_context"] = affective_runtime_context
        self.data_store.persist_fact(
            execution_span_id,
            "affective_runtime_context",
            frame.frame_id,
            affective_runtime_context,
        )
        prompt_safe_context = build_prompt_safe_context(
            session_context,
            frame=frame,
            memory_items=memory_items,
            available_tools=available_tools,
        )
        session_context["prompt_safe_context"] = prompt_safe_context
        memory_prompt_context = cast(
            dict[str, Any],
            prompt_safe_context.get("memory") or {},
        )
        memory_recall_policy = cast(
            dict[str, Any],
            memory_prompt_context.get("recall_policy") or {},
        )
        session_context["memory_recall_policy"] = memory_recall_policy
        self.data_store.persist_fact(
            execution_span_id,
            "memory_recall_policy",
            frame.frame_id,
            memory_recall_policy,
        )

        affective_step = (
            "affective_model_call"
            if self.maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
            else "affective_arbitration"
        )
        steps.append(affective_step)
        safe_memory_items = cast(
            list[dict[str, Any]],
            memory_prompt_context.get("affective_items") or [],
        )
        prompt_safe_affective_context = cast(
            dict[str, Any],
            prompt_safe_context.get("affective_runtime") or {},
        )
        profile_route_summary = cast(
            dict[str, Any],
            prompt_safe_affective_context.get("profile_route") or {},
        )
        if (
            self.maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
            and not bool(profile_route_summary.get("route_ready", False))
        ):
            route_failure_status = str(
                profile_route_summary.get("failure_status")
                or profile_route_summary.get("route_status")
                or "unavailable"
            )
            raise ValueError(
                f"affective_provider_inference_route_unavailable:{route_failure_status}"
            )
        decision = self.affective_agent.decide(
            frame,
            safe_memory_items,
            affective_context=prompt_safe_affective_context,
        )
        model_call_evidence = self._build_model_call_evidence(
            frame,
            decision,
            self.maf_runtime_metadata(),
            prompt_safe_affective_context,
        )
        session_context["model_call_evidence"] = model_call_evidence

        steps.append("rational_delegate_optional")
        rational_plan_failure_status = ""
        plan = None
        try:
            plan = self.rational_agent.plan(
                decision,
                frame,
                available_tools=available_tools,
                session_context=prompt_safe_context,
            )
        except ValueError as exc:
            rational_plan_failure_status = str(exc)

        steps.append("tool_and_unit_execution")
        tool_results: list[ToolExecutionResult] = []
        if rational_plan_failure_status:
            tool_results.append(
                ToolExecutionResult(
                    tool_result_id=new_id("tool"),
                    tool_name="rational_plan_validation",
                    status="error",
                    payload={
                        "failure_status": rational_plan_failure_status,
                        "failure_class": "rational_plan_payload_invalid",
                        "available_tools": available_tools,
                    },
                )
            )
        elif plan is not None:
            contract = self.tool_adapter.describe_tool(plan.tool_name)
            if contract is None:
                result = ToolExecutionResult(
                    tool_result_id=new_id("tool"),
                    tool_name=plan.tool_name,
                    status="error",
                    payload={
                        "failure_status": "unknown_tool",
                        "failure_class": "manifest_lookup_failed",
                        "requested_plan": plan.to_dict(),
                        "available_tools": available_tools,
                    },
                )
            else:
                plan_quality = self._build_rational_plan_quality(
                    plan,
                    contract,
                    available_tools,
                )
                if not bool(plan_quality.get("valid", False)):
                    result = ToolExecutionResult(
                        tool_result_id=new_id("tool"),
                        tool_name=plan.tool_name,
                        status="error",
                        payload={
                            "failure_status": "missing_required_arguments",
                            "failure_class": "rational_plan_contract_invalid",
                            "requested_plan": plan.to_dict(),
                            "contract": contract.to_dict(),
                            "plan_quality": plan_quality,
                        },
                    )
                else:
                    policy_decision = self.tool_policy.evaluate_contract(contract)
                    policy_payload = policy_decision.to_dict()
                    self.data_store.persist_policy_decision(
                        execution_span_id,
                        plan.tool_name,
                        policy_payload,
                    )
                    if policy_decision.allowed:
                        result = self.tool_adapter.execute(plan.tool_name, plan.args)
                        result.payload["policy_decision"] = policy_payload
                        result.payload["plan_quality"] = plan_quality
                    else:
                        if policy_decision.approval_required:
                            approval_request_id = new_id("approval")
                            approval_request_payload: dict[str, Any] = {
                                "approval_request_id": approval_request_id,
                                "tool_name": plan.tool_name,
                                "reason": "operator_approval_required_before_execution",
                                "requested_args": dict(plan.args),
                                "required_resources": list(contract.required_resources),
                                "cleanup_hint": contract.cleanup_hint,
                                "side_effect_level": contract.side_effect_level.value,
                                "policy_decision": policy_payload,
                                "contract": contract.to_dict(),
                                "plan_quality": plan_quality,
                                "skill_requirements": plan_quality.get("skill_requirements"),
                                "status": "pending",
                            }
                            self.data_store.persist_approval_request(
                                resolved_session_id,
                                execution_span_id,
                                plan.tool_name,
                                "pending",
                                approval_request_payload,
                                approval_request_id=approval_request_id,
                            )
                            result = ToolExecutionResult(
                                tool_result_id=new_id("tool"),
                                tool_name=plan.tool_name,
                                status="pending_approval",
                                payload={
                                    "failure_status": "approval_required",
                                    "failure_class": "approval_gate_pending",
                                    "policy_decision": policy_payload,
                                    "plan_quality": plan_quality,
                                    "approval_request": approval_request_payload,
                                },
                            )
                            session_context["pending_approval_request_ids"] = list(
                                {
                                    *cast(
                                        list[str],
                                        session_context.get(
                                            "pending_approval_request_ids",
                                            [],
                                        ),
                                    ),
                                    approval_request_id,
                                }
                            )
                        else:
                            result = ToolExecutionResult(
                                tool_result_id=new_id("tool"),
                                tool_name=plan.tool_name,
                                status="blocked",
                                payload={
                                    "failure_status": "policy_blocked",
                                    "failure_class": "tool_policy_denied",
                                    "policy_decision": policy_payload,
                                    "plan_quality": plan_quality,
                                },
                            )
            self.data_store.persist_tool_result(
                result.tool_result_id,
                execution_span_id,
                result.tool_name,
                result.status,
                result.payload,
            )
            if result.tool_name == "system_activation_health_guard" and result.status == "ok":
                activation_health = cast(
                    dict[str, Any],
                    result.payload.get("activation_health") or {},
                )
                self.data_store.persist_fact(
                    execution_span_id,
                    "activation_health_observation",
                    str(
                        activation_health.get("app_id")
                        or activation_health.get("classification")
                        or "activation-health"
                    ),
                    activation_health,
                )
                tool_results.append(result)
                if activation_health.get("classification") == "rollback_required":
                    recovery_contract = self.tool_adapter.describe_tool("system_query_leases")
                    if recovery_contract is not None:
                        recovery_policy = self.tool_policy.evaluate_contract(recovery_contract)
                        recovery_policy_payload = recovery_policy.to_dict()
                        self.data_store.persist_policy_decision(
                            execution_span_id,
                            "system_query_leases",
                            recovery_policy_payload,
                        )
                        if recovery_policy.allowed:
                            lease_result = self.tool_adapter.execute(
                                "system_query_leases",
                                {
                                    "event_ids": list(frame.event_ids),
                                    "reason": "rollback_candidate_lease_observation",
                                },
                            )
                            lease_result.payload["policy_decision"] = recovery_policy_payload
                            self.data_store.persist_tool_result(
                                lease_result.tool_result_id,
                                execution_span_id,
                                lease_result.tool_name,
                                lease_result.status,
                                lease_result.payload,
                            )
                            tool_results.append(lease_result)
                            recovery_candidate_summary = _build_recovery_candidate_summary(
                                activation_health=activation_health,
                                lease_observation=lease_result.to_dict(),
                                activate_failed_payload=activate_failed_payload,
                            )
                            session_context["recovery_candidate_summary"] = recovery_candidate_summary
                            self.data_store.persist_fact(
                                execution_span_id,
                                "recovery_candidate",
                                str(
                                    recovery_candidate_summary.get("app_id")
                                    or recovery_candidate_summary.get("rollback_decision")
                                    or "recovery-candidate"
                                ),
                                recovery_candidate_summary,
                            )
                            rollback_contract = self.tool_adapter.describe_tool(
                                "system_rollback_app"
                            )
                            if rollback_contract is not None:
                                rollback_policy = self.tool_policy.evaluate_contract(
                                    rollback_contract
                                )
                                rollback_policy_payload = rollback_policy.to_dict()
                                self.data_store.persist_policy_decision(
                                    execution_span_id,
                                    "system_rollback_app",
                                    rollback_policy_payload,
                                )
                                if rollback_policy.approval_required:
                                    approval_request_id = new_id("approval")
                                    rollback_request_payload: dict[str, Any] = {
                                        "approval_request_id": approval_request_id,
                                        "tool_name": "system_rollback_app",
                                        "reason": "operator_approval_required_for_guarded_rollback",
                                        "requested_args": {
                                            "app_id": str(
                                                recovery_candidate_summary.get("app_id") or ""
                                            ),
                                            "app": str(
                                                recovery_candidate_summary.get("app_id") or ""
                                            ),
                                            "reason": "guarded_rollback_after_activation_health_failure",
                                        },
                                        "required_resources": list(
                                            rollback_contract.required_resources
                                        ),
                                        "cleanup_hint": rollback_contract.cleanup_hint,
                                        "side_effect_level": rollback_contract.side_effect_level.value,
                                        "policy_decision": rollback_policy_payload,
                                        "contract": rollback_contract.to_dict(),
                                        "status": "pending",
                                        "target_app_id": str(
                                            recovery_candidate_summary.get("app_id") or ""
                                        ),
                                        "recovery_candidate_summary": recovery_candidate_summary,
                                    }
                                    self.data_store.persist_approval_request(
                                        resolved_session_id,
                                        execution_span_id,
                                        "system_rollback_app",
                                        "pending",
                                        rollback_request_payload,
                                        approval_request_id=approval_request_id,
                                    )
                                    rollback_pending_result = ToolExecutionResult(
                                        tool_result_id=new_id("tool"),
                                        tool_name="system_rollback_app",
                                        status="pending_approval",
                                        payload={
                                            "failure_status": "approval_required",
                                            "failure_class": "approval_gate_pending",
                                            "policy_decision": rollback_policy_payload,
                                            "approval_request": rollback_request_payload,
                                        },
                                    )
                                    self.data_store.persist_tool_result(
                                        rollback_pending_result.tool_result_id,
                                        execution_span_id,
                                        rollback_pending_result.tool_name,
                                        rollback_pending_result.status,
                                        rollback_pending_result.payload,
                                    )
                                    tool_results.append(rollback_pending_result)
                                    session_context["pending_approval_request_ids"] = list(
                                        {
                                            *cast(
                                                list[str],
                                                session_context.get(
                                                    "pending_approval_request_ids",
                                                    [],
                                                ),
                                            ),
                                            approval_request_id,
                                        }
                                    )
            else:
                tool_results.append(result)

        session_context["rational_plan_evidence"] = self._build_rational_plan_evidence(
            plan=plan,
            failure_status=rational_plan_failure_status,
            available_tools=available_tools,
            tool_results=tool_results,
        )

        steps.append("audit_record")
        final_response = self._build_final_response(frame, decision, tool_results)
        notification_summary = self._build_notification_summary(
            frame,
            decision,
            final_response,
        )
        self.data_store.persist_fact(
            execution_span_id,
            "notification_dispatch",
            str(notification_summary.get("notification_id") or final_response.get("speaker") or "notification"),
            notification_summary,
        )
        audit_id = new_id("audit")
        self.data_store.persist_audit_record(
            audit_id,
            execution_span_id,
            "ok",
            self._build_audit_payload(
                frame,
                decision,
                session_context,
                tool_results,
                final_response,
                notification_summary,
                self.tool_adapter,
                self.maf_runtime_metadata(),
            ),
            session_id=resolved_session_id,
        )
        self.data_store.persist_execution_span(
            execution_span_id,
            "ok",
            {
                "event_source": event_source,
                "session_id": resolved_session_id,
                "steps": steps,
                "events_persisted": len(events),
                "normalized_event_count": len(events),
                "delegated": plan is not None,
                "tool_result_count": len(tool_results),
                "audit_id": audit_id,
                "federation_route_status": str(
                    (federation_route_evidence or {}).get("status") or ""
                ),
                "federation_route_kind": str(
                    cast(
                        dict[str, Any],
                        (federation_route_evidence or {}).get("route_decision") or {},
                    ).get("route_kind")
                    or ""
                ),
            },
            session_id=resolved_session_id,
        )

        steps.append("notification_dispatch")
        return WorkflowResult(
            status="ok",
            execution_span_id=execution_span_id,
            session_id=resolved_session_id,
            final_response=final_response,
            steps=tuple(steps),
            events_persisted=len(events),
            delegated=plan is not None,
            tool_results=tuple(result.to_dict() for result in tool_results),
            audit_id=audit_id,
        )

    @staticmethod
    def _build_frame(events: list[PerceptionEvent]) -> PerceptionFrame:
        event_ids = tuple(event.event_id for event in events)
        topics = tuple(
            sorted(
                {
                    event.semantic_topic or event.event_type
                    for event in events
                    if event.semantic_topic or event.event_type
                }
            )
        )
        highest_priority = max((event.priority for event in events), default=0)
        return PerceptionFrame(
            frame_id=new_id("frame"),
            event_ids=event_ids,
            highest_priority=highest_priority,
            topics=topics,
        )

    def maf_runtime_metadata(self) -> dict[str, Any]:
        agent_adapters: list[dict[str, Any]] = []
        for agent in (self.affective_agent, self.rational_agent):
            runtime_metadata = getattr(agent, "runtime_metadata", None)
            if callable(runtime_metadata):
                agent_adapters.append(cast(dict[str, Any], runtime_metadata()))
        return {
            **self.maf_runtime_profile.to_dict(),
            "agent_adapters": agent_adapters,
        }

    def memory_runtime_metadata(self) -> dict[str, Any]:
        runtime_metadata = getattr(self.memory, "runtime_metadata", None)
        if callable(runtime_metadata):
            return cast(dict[str, Any], runtime_metadata())
        return {
            "backend_kind": "unknown",
            "backend_runtime": "unknown",
            "requires_external_service": False,
            "fallback_active": False,
            "can_execute_tools_directly": False,
        }

    def _build_affective_runtime_context(
        self,
        frame: PerceptionFrame,
        events: list[PerceptionEvent],
    ) -> dict[str, Any]:
        text_inputs: list[str] = []
        image_refs: list[str] = []
        audio_refs: list[str] = []
        video_refs: list[str] = []
        response_modes: list[str] = []
        profile_hint = "auto"
        profile_override = ""
        for event in events:
            payload = event.payload
            text_value = payload.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_inputs.append(text_value.strip())
            for singular_key, plural_key, target in (
                ("image_ref", "image_refs", image_refs),
                ("audio_ref", "audio_refs", audio_refs),
                ("video_ref", "video_refs", video_refs),
            ):
                singular_value = payload.get(singular_key)
                if isinstance(singular_value, str) and singular_value.strip():
                    target.append(singular_value.strip())
                plural_value = payload.get(plural_key)
                if isinstance(plural_value, list):
                    plural_items = cast(list[Any], plural_value)
                    target.extend(
                        item.strip()
                        for item in plural_items
                        if isinstance(item, str) and item.strip()
                    )
            response_mode = payload.get("response_mode")
            if isinstance(response_mode, str) and response_mode.strip():
                response_modes.append(response_mode.strip())
            response_mode_values = payload.get("response_modes")
            if isinstance(response_mode_values, list):
                response_mode_items = cast(list[Any], response_mode_values)
                response_modes.extend(
                    item.strip()
                    for item in response_mode_items
                    if isinstance(item, str) and item.strip()
                )
            payload_profile_hint = payload.get("profile_hint")
            if isinstance(payload_profile_hint, str) and payload_profile_hint.strip():
                profile_hint = payload_profile_hint.strip()
            payload_profile_override = payload.get("profile_override")
            if isinstance(payload_profile_override, str) and payload_profile_override.strip():
                profile_override = payload_profile_override.strip()

        provenance = "workflow_event_payload"
        if not (text_inputs or image_refs or audio_refs or video_refs):
            provenance = "workflow_frame_summary"
            text_inputs = [
                f"Perception topics: {', '.join(frame.topics) if frame.topics else 'unknown'}"
            ]

        require_live_backend = (
            self.maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
        )
        effective_profile_override = profile_override
        if require_live_backend and not effective_profile_override:
            effective_profile_override = "remote_openai_compatible"
        normalized = normalize_multimodal_input(
            request_id=frame.frame_id,
            text=text_inputs,
            image_refs=image_refs,
            audio_refs=audio_refs,
            video_refs=video_refs,
            response_modes=response_modes or None,
            profile_hint=profile_hint,
            provenance=provenance,
        )
        route = build_inference_route(
            normalized,
            profile_override=effective_profile_override,
            require_live_backend=require_live_backend,
        )
        selected_profile = cast(dict[str, Any], route.get("selected_profile") or {})
        presentation_policy = {
            "prompt_safe_multimodal_summary_only": True,
            "internal_facts_remain_core_owned": True,
            "model_may_not_execute_tools_directly": True,
            "user_visible_output_separated_from_internal_facts": True,
        }
        return {
            "schema_version": AFFECTIVE_RUNTIME_CONTEXT_SCHEMA_VERSION,
            "multimodal_summary": {
                "request_id": normalized.request_id,
                "input_modes": list(normalized.input_modes),
                "response_modes": list(normalized.response_modes),
                "profile_hint": normalized.profile_hint,
                "latency_class": normalized.latency_class,
                "text_count": len(normalized.text),
                "text_preview": [text[:160] for text in list(normalized.text)[:2]],
                "image_ref_count": len(normalized.images),
                "audio_ref_count": len(normalized.audio),
                "video_ref_count": len(normalized.video),
                "provenance": normalized.provenance,
            },
            "profile_route": {
                "requested_profile": str(route.get("requested_profile") or "auto"),
                "selected_profile": str(selected_profile.get("name") or ""),
                "route_status": str(route.get("status") or "unknown"),
                "route_reason": str(route.get("route_reason") or ""),
                "failure_status": str(route.get("failure_status") or ""),
                "fallback_used": bool(route.get("fallback_used", False)),
                "candidate_rejection_count": len(
                    cast(list[Any], route.get("candidate_rejections") or [])
                ),
                "requires_live_backend": require_live_backend,
                "route_ready": bool(route.get("ok")),
            },
            "presentation_policy": presentation_policy,
        }

    def _skill_descriptor_summary(self) -> dict[str, Any]:
        payload = load_neuro_cli_skill_descriptor_payload()
        return {
            "schema_version": str(payload.get("schema_version") or ""),
            "name": str(payload.get("name") or ""),
            "workflow_plan_required": bool(payload.get("workflow_plan_required", False)),
            "json_output_required": bool(payload.get("json_output_required", False)),
            "release_target_promotion_blocked": bool(
                payload.get("release_target_promotion_blocked", False)
            ),
            "callback_audit_required": bool(payload.get("callback_audit_required", False)),
            "first_check_commands": list(payload.get("first_check_commands") or [])[:3],
        }

    def _mcp_descriptor_summary(self, contract: ToolContract | None = None) -> dict[str, Any]:
        bridge_mode = "read_only_descriptor_only"
        if contract is not None:
            if contract.approval_required or contract.required_resources:
                bridge_mode = "core_governed_approval_required_proposal"
            elif contract.side_effect_level.value in {"read_only", "observe_only"}:
                bridge_mode = "core_governed_read_only_execution"
        payload = load_mcp_bridge_descriptor_payload(self.tool_adapter, bridge_mode=bridge_mode)
        safety_boundaries = cast(dict[str, Any], payload.get("safety_boundaries") or {})
        return {
            "schema_version": str(payload.get("schema_version") or ""),
            "bridge_name": str(payload.get("bridge_name") or ""),
            "bridge_mode": str(payload.get("bridge_mode") or ""),
            "transport": str(payload.get("transport") or ""),
            "allowed_operations": list(payload.get("allowed_operations") or []),
            "read_only_tool_count": len(payload.get("read_only_tools") or []),
            "approval_required_tool_count": len(payload.get("approval_required_tools") or []),
            "blocked_tool_count": len(payload.get("blocked_tools") or []),
            "tool_execution_via_mcp_forbidden": bool(
                safety_boundaries.get("tool_execution_via_mcp_forbidden", False)
            ),
            "approval_required_tool_proposals_allowed": bool(
                safety_boundaries.get("approval_required_tool_proposals_allowed", False)
            ),
            "external_mcp_connection_enabled": bool(
                safety_boundaries.get("external_mcp_connection_enabled", False)
            ),
        }

    @staticmethod
    def _required_argument_aliases(argument_name: str) -> tuple[str, ...]:
        normalized_key = argument_name.lstrip("-").replace("-", "_")
        aliases = [normalized_key]
        if argument_name == "--app-id":
            aliases.append("app")
        if argument_name == "--lease-id":
            aliases.append("lease")
        return tuple(aliases)

    @staticmethod
    def _build_skill_ground_rule_validation(
        contract: ToolContract,
        skill_descriptor: dict[str, Any],
    ) -> dict[str, Any]:
        argv_template = list(contract.argv_template)
        output_contract = dict(contract.output_contract or {})
        uses_wrapper_command = any(
            "invoke_neuro_cli.py" in str(item) for item in argv_template
        )
        json_output_flag_present = any(
            argv_template[index] == "--output" and index + 1 < len(argv_template)
            and argv_template[index + 1] == "json"
            for index in range(len(argv_template))
        )
        json_output_contract_satisfied = (
            str(output_contract.get("format") or "") == "json"
            and bool(output_contract.get("top_level_ok", False))
            and json_output_flag_present
        )
        callback_audit_rule_satisfied = (
            not bool(skill_descriptor.get("callback_audit_required", False))
            or "callback" not in contract.tool_name
            or bool(contract.approval_required)
            or bool(contract.cleanup_hint)
        )
        closure_gates = {
            "wrapper_command_required": uses_wrapper_command,
            "json_output_required": (
                not bool(skill_descriptor.get("json_output_required", False))
                or json_output_contract_satisfied
            ),
            "callback_audit_rule_satisfied": callback_audit_rule_satisfied,
        }
        return {
            "wrapper_command_required": uses_wrapper_command,
            "json_output_flag_present": json_output_flag_present,
            "json_output_contract_satisfied": json_output_contract_satisfied,
            "callback_audit_rule_satisfied": callback_audit_rule_satisfied,
            "closure_gates": closure_gates,
            "valid": all(closure_gates.values()),
            "failure_status": (
                "skill_ground_rule_violation" if not all(closure_gates.values()) else ""
            ),
        }

    def _build_rational_plan_quality(
        self,
        plan: Any,
        contract: ToolContract,
        available_tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        available_tool_index = {
            str(tool.get("name") or tool.get("tool_name") or ""): tool
            for tool in available_tools
        }
        available_tool_names = set(available_tool_index)
        required_argument_coverage: dict[str, bool] = {}
        missing_required_arguments: list[str] = []
        for argument_name in contract.required_arguments:
            if argument_name == "--node":
                required_argument_coverage[argument_name] = True
                continue
            aliases = self._required_argument_aliases(argument_name)
            present = any(
                plan.args.get(alias) not in (None, "", [])
                for alias in aliases
            )
            required_argument_coverage[argument_name] = present
            if not present:
                missing_required_arguments.append(argument_name)

        skill_descriptor = self._skill_descriptor_summary()
        workflow_plan_required = bool(skill_descriptor.get("workflow_plan_required")) and (
            contract.approval_required or bool(contract.required_resources)
        )
        skill_requirements: dict[str, Any] = {
            "skill_name": skill_descriptor.get("name"),
            "workflow_plan_required": workflow_plan_required,
            "workflow_plan_evidence_present": False,
            "json_output_required": bool(skill_descriptor.get("json_output_required", False)),
            "release_target_promotion_blocked": bool(
                skill_descriptor.get("release_target_promotion_blocked", False)
            ),
            "callback_audit_required": bool(skill_descriptor.get("callback_audit_required", False)),
            "suggested_first_check_commands": list(skill_descriptor.get("first_check_commands") or []),
        }
        skill_ground_rules = self._build_skill_ground_rule_validation(
            contract,
            skill_descriptor,
        )
        workflow_catalog_consistency = validate_tool_workflow_catalog_consistency(contract)
        skill_requirements["workflow_plan_evidence_present"] = bool(
            workflow_catalog_consistency.get("valid", False)
        )
        mcp_descriptor = self._mcp_descriptor_summary(contract)
        mcp_requirements: dict[str, Any] = {
            "bridge_name": mcp_descriptor.get("bridge_name"),
            "bridge_mode": mcp_descriptor.get("bridge_mode"),
            "allowed_operations": list(mcp_descriptor.get("allowed_operations") or []),
            "read_only_tool_count": int(mcp_descriptor.get("read_only_tool_count") or 0),
            "approval_required_tool_count": int(
                mcp_descriptor.get("approval_required_tool_count") or 0
            ),
            "blocked_tool_count": int(mcp_descriptor.get("blocked_tool_count") or 0),
            "tool_execution_via_mcp_forbidden": bool(
                mcp_descriptor.get("tool_execution_via_mcp_forbidden", False)
            ),
            "approval_required_tool_proposals_allowed": bool(
                mcp_descriptor.get("approval_required_tool_proposals_allowed", False)
            ),
            "external_mcp_connection_enabled": bool(
                mcp_descriptor.get("external_mcp_connection_enabled", False)
            ),
            "bridge_mode_satisfies_tool_governance": (
                bool(mcp_descriptor.get("approval_required_tool_proposals_allowed", False))
                if contract.approval_required or contract.required_resources
                else not bool(mcp_descriptor.get("tool_execution_via_mcp_forbidden", True))
            ),
        }
        matched_available_tool = available_tool_index.get(plan.tool_name) or {}
        matched_required_resources = list(
            matched_available_tool.get("required_resources")
            or matched_available_tool.get("lease_requirements")
            or []
        )
        available_tool_contract_match = bool(matched_available_tool) and all(
            (
                matched_required_resources == list(contract.required_resources),
                bool(matched_available_tool.get("approval_required", False))
                == bool(contract.approval_required),
                bool(matched_available_tool.get("retryable", False))
                == bool(contract.retryable),
                str(matched_available_tool.get("side_effect_level") or "")
                == contract.side_effect_level.value,
            )
        )
        resource_fit: dict[str, Any] = {
            "required_resources": list(contract.required_resources),
            "approval_required_for_required_resources": (
                not bool(contract.required_resources) or bool(contract.approval_required)
            ),
            "valid": not bool(contract.required_resources) or bool(contract.approval_required),
        }
        cleanup_awareness: dict[str, Any] = {
            "cleanup_hint_present": bool(contract.cleanup_hint),
            "cleanup_review_required": bool(contract.approval_required or contract.required_resources),
            "valid": (
                not bool(contract.approval_required or contract.required_resources)
                or bool(contract.cleanup_hint)
            ),
        }
        retryability: dict[str, Any] = {
            "retryable": bool(contract.retryable),
            "operator_retry_guidance_required": bool(
                not contract.retryable and (contract.approval_required or contract.required_resources)
            ),
            "valid": True,
        }
        operator_resolvable_missing_arguments = [
            argument_name
            for argument_name in missing_required_arguments
            if contract.approval_required and argument_name in {"--app", "--app-id", "--lease-id"}
        ]
        blocking_missing_arguments = [
            argument_name
            for argument_name in missing_required_arguments
            if argument_name not in operator_resolvable_missing_arguments
        ]
        return {
            "schema_version": RATIONAL_PLAN_QUALITY_SCHEMA_VERSION,
            "tool_name": plan.tool_name,
            "available_tool_match": plan.tool_name in available_tool_names,
            "available_tool_contract_match": available_tool_contract_match,
            "failure_status": (
                str(skill_ground_rules.get("failure_status") or "")
                or str(workflow_catalog_consistency.get("failure_status") or "")
                or (
                    "missing_required_arguments"
                    if blocking_missing_arguments
                    else ""
                )
                or (
                    "rational_plan_tool_not_in_available_tools"
                    if plan.tool_name not in available_tool_names
                    else ""
                )
                or (
                    "rational_plan_tool_contract_mismatch"
                    if not available_tool_contract_match
                    else ""
                )
            ),
            "required_argument_coverage": required_argument_coverage,
            "missing_required_arguments": missing_required_arguments,
            "operator_resolvable_missing_arguments": operator_resolvable_missing_arguments,
            "blocking_missing_arguments": blocking_missing_arguments,
            "required_resources": list(contract.required_resources),
            "approval_required": contract.approval_required,
            "resource_fit": resource_fit,
            "retryability": retryability,
            "retryable": contract.retryable,
            "cleanup_awareness": cleanup_awareness,
            "cleanup_hint_present": bool(contract.cleanup_hint),
            "skill_ground_rules": skill_ground_rules,
            "workflow_catalog_consistency": workflow_catalog_consistency,
            "valid": (
                not blocking_missing_arguments
                and plan.tool_name in available_tool_names
                and available_tool_contract_match
                and bool(resource_fit.get("valid", False))
                and bool(cleanup_awareness.get("valid", False))
                and bool(retryability.get("valid", False))
                and bool(skill_ground_rules.get("valid", False))
                and bool(workflow_catalog_consistency.get("valid", False))
                and bool(mcp_requirements.get("bridge_mode_satisfies_tool_governance", False))
            ),
            "skill_requirements": skill_requirements,
            "mcp_requirements": mcp_requirements,
        }

    def _available_tool_context(self) -> list[dict[str, Any]]:
        tool_manifest = getattr(self.tool_adapter, "tool_manifest", None)
        if not callable(tool_manifest):
            return []
        manifest = cast(tuple[ToolContract, ...], tool_manifest())
        available_tools: list[dict[str, Any]] = []
        for contract in manifest:
            available_tools.append(contract.to_dict())
        return available_tools

    def _persist_frame_facts(
        self,
        execution_span_id: str,
        frame: PerceptionFrame,
        events: list[PerceptionEvent],
    ) -> list[str]:
        fact_ids: list[str] = []
        fact_ids.append(
            self.data_store.persist_fact(
            execution_span_id,
            "perception_frame",
            frame.frame_id,
            frame.to_dict(),
        )
        )
        for event in events:
            fact_ids.append(
                self.data_store.persist_fact(
                execution_span_id,
                "perception_event_topic",
                event.semantic_topic or event.event_type,
                {
                    "event_id": event.event_id,
                    "source_kind": event.source_kind,
                    "source_node": event.source_node,
                    "source_app": event.source_app,
                    "priority": event.priority,
                },
            )
            )
        return fact_ids

    @staticmethod
    def _build_audit_payload(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        session_context: dict[str, Any],
        tool_results: list[ToolExecutionResult],
        final_response: dict[str, Any],
        notification_summary: dict[str, Any],
        tool_adapter: Any,
        maf_runtime: dict[str, Any],
    ) -> dict[str, Any]:
        adapter_runtime = {}
        if hasattr(tool_adapter, "runtime_metadata"):
            adapter_runtime = dict(tool_adapter.runtime_metadata())

        state_sync_summary: dict[str, Any] | None = None
        activation_health_summary: dict[str, Any] | None = None
        recovery_candidate_summary = cast(
            dict[str, Any] | None,
            session_context.get("recovery_candidate_summary"),
        )
        rational_plan_evidence = cast(
            dict[str, Any] | None,
            session_context.get("rational_plan_evidence"),
        )
        for result in tool_results:
            if result.tool_name != "system_state_sync":
                if result.tool_name != "system_activation_health_guard":
                    continue
                payload = result.payload
                observation = dict(payload.get("activation_health") or {})
                activation_health_summary = {
                    "tool_status": result.status,
                    "classification": str(observation.get("classification") or "unknown"),
                    "reason": str(observation.get("reason") or ""),
                    "ready_for_rollback_consideration": bool(
                        observation.get("ready_for_rollback_consideration", False)
                    ),
                    "app_id": str(observation.get("app_id") or ""),
                    "network_state": str(observation.get("network_state") or "unknown"),
                    "observed_app_state": str(observation.get("observed_app_state") or "unknown"),
                    "recommended_next_actions": list(
                        observation.get("recommended_next_actions") or []
                    ),
                }
                continue
            payload = result.payload
            if result.status == "ok":
                snapshot = dict(payload.get("state_sync") or {})
                state_sync_summary = {
                    "tool_status": result.status,
                    "snapshot_status": snapshot.get("status", "unknown"),
                    "recommended_next_actions": list(
                        snapshot.get("recommended_next_actions") or []
                    ),
                    "failure_class": "",
                    "failure_status": "",
                }
            else:
                raw_nested_payload = payload.get("payload")
                nested_payload: dict[str, Any] = (
                    cast(dict[str, Any], raw_nested_payload)
                    if isinstance(raw_nested_payload, dict)
                    else {}
                )
                recommended_next_actions: list[Any] = []
                if nested_payload:
                    recommended_next_actions = list(
                        nested_payload.get("recommended_next_actions") or []
                    )
                state_sync_summary = {
                    "tool_status": result.status,
                    "snapshot_status": str((nested_payload or {}).get("status") or "error"),
                    "recommended_next_actions": recommended_next_actions,
                    "failure_class": str(payload.get("failure_class") or ""),
                    "failure_status": str(payload.get("failure_status") or ""),
                }

        return {
            "frame": frame.to_dict(),
            "decision": decision.to_dict(),
            "session_context": dict(session_context),
            "maf_runtime": dict(maf_runtime),
            "adapter_runtime": adapter_runtime,
            "state_sync_summary": state_sync_summary,
            "activation_health_summary": activation_health_summary,
            "rational_plan_evidence": dict(rational_plan_evidence)
            if isinstance(rational_plan_evidence, dict)
            else None,
            "recovery_candidate_summary": dict(recovery_candidate_summary)
            if isinstance(recovery_candidate_summary, dict)
            else None,
            "notification_summary": dict(notification_summary),
            "final_response": dict(final_response),
            "tool_results": [result.to_dict() for result in tool_results],
        }

    @staticmethod
    def _build_rational_plan_evidence(
        *,
        plan: Any,
        failure_status: str,
        available_tools: list[dict[str, Any]],
        tool_results: list[ToolExecutionResult],
    ) -> dict[str, Any]:
        available_tool_names = [
            str(tool.get("name") or tool.get("tool_name") or "")
            for tool in available_tools
        ]
        selected_tool_name = str(getattr(plan, "tool_name", "") or "")
        tool_result_status = tool_results[0].status if tool_results else None
        if failure_status:
            status = "invalid_payload"
        elif plan is None:
            status = "no_tool_selected"
        else:
            status = "tool_selected"
        return {
            "schema_version": RATIONAL_PLAN_EVIDENCE_SCHEMA_VERSION,
            "status": status,
            "failure_status": failure_status,
            "selected_tool_name": selected_tool_name,
            "selected_tool_in_available_tools": (
                selected_tool_name in available_tool_names if selected_tool_name else False
            ),
            "available_tool_count": len(available_tool_names),
            "tool_result_status": tool_result_status,
        }

    @staticmethod
    def _build_notification_summary(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        final_response: dict[str, Any],
    ) -> dict[str, Any]:
        interactive_topics = [topic for topic in frame.topics if topic.startswith("user.input")]
        trigger_kind = "interactive_request" if interactive_topics else "event_driven_perception"
        if not decision.delegated:
            delivery_kind = "observation_only"
        elif any(topic.startswith("user.input") for topic in frame.topics):
            delivery_kind = "interactive_response"
        else:
            delivery_kind = "event_driven_notification"
        urgency = "high" if decision.salience >= 80 else "normal"
        return {
            "notification_id": new_id("notif"),
            "speaker": str(final_response.get("speaker") or "affective"),
            "trigger_kind": trigger_kind,
            "delivery_kind": delivery_kind,
            "audience": "user",
            "salience": decision.salience,
            "urgency": urgency,
            "topics": list(frame.topics),
            "delegated": decision.delegated,
            "text": str(final_response.get("text") or ""),
        }

    @staticmethod
    def _build_model_call_evidence(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        maf_runtime: dict[str, Any],
        affective_runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        provider_config = cast(dict[str, Any], maf_runtime.get("provider_config") or {})
        agent_adapters = cast(list[Any], maf_runtime.get("agent_adapters") or [])
        affective_adapter: dict[str, Any] = {}
        for adapter in agent_adapters:
            if not isinstance(adapter, dict):
                continue
            adapter_payload = cast(dict[str, Any], adapter)
            if adapter_payload.get("agent_role") == "affective":
                affective_adapter = adapter_payload
                break
        real_provider_enabled = bool(maf_runtime.get("real_provider_enabled", False))
        provider_call_supported = bool(
            affective_adapter.get("provider_call_supported", False)
        )
        multimodal_summary = cast(
            dict[str, Any],
            affective_runtime_context.get("multimodal_summary") or {},
        )
        profile_route = cast(
            dict[str, Any],
            affective_runtime_context.get("profile_route") or {},
        )
        presentation_policy = cast(
            dict[str, Any],
            affective_runtime_context.get("presentation_policy") or {},
        )
        return {
            "agent_role": "affective",
            "call_status": (
                "model_call_succeeded"
                if real_provider_enabled and provider_call_supported
                else "deterministic_fake"
            ),
            "executes_model_call": real_provider_enabled and provider_call_supported,
            "frame_id": frame.frame_id,
            "event_ids": list(frame.event_ids),
            "provider_kind": str(provider_config.get("provider_kind") or "unknown"),
            "provider_client_kind": str(
                affective_adapter.get("provider_client_kind") or "deterministic_fake"
            ),
            "response_schema": "AffectiveDecision",
            "decision": decision.to_dict(),
            "multimodal_summary": multimodal_summary,
            "profile_route": profile_route,
            "presentation_policy": presentation_policy,
            "provider_failure_mode": "fail_closed",
        }

    @staticmethod
    def _build_final_response(
        frame: PerceptionFrame,
        decision: AffectiveDecision,
        tool_results: list[ToolExecutionResult],
    ) -> dict[str, Any]:
        topics = ", ".join(frame.topics) if frame.topics else "unknown"
        if not decision.delegated:
            text = f"Recorded perception topics {topics}; no delegated action was required."
        elif not tool_results:
            text = f"Observed {topics} and opened a reasoning window, but no tool execution was required."
        else:
            result = tool_results[0]
            tool_label = result.tool_name.replace("system_", "").replace("_", " ")
            if result.status == "ok":
                text = f"Observed {topics} and completed a read-only {tool_label} before responding."
            elif result.status == "pending_approval":
                text = f"Observed {topics} and prepared delegated {tool_label}, but execution is waiting for explicit approval."
            elif result.status == "blocked":
                text = f"Observed {topics} but blocked delegated {tool_label} due to policy constraints."
            else:
                text = f"Observed {topics} and attempted delegated {tool_label}, but the tool path reported an error."
        return {
            "speaker": "affective",
            "delegated": decision.delegated,
            "text": text,
            "salience": decision.salience,
            "trigger_kind": (
                "interactive_request"
                if any(topic.startswith("user.input") for topic in frame.topics)
                else "event_driven_perception"
            ),
            "delivery_kind": (
                "observation_only"
                if not decision.delegated
                else "interactive_response"
                if any(topic.startswith("user.input") for topic in frame.topics)
                else "event_driven_notification"
            ),
            "topics": list(frame.topics),
        }


def run_no_model_dry_run(
    db_path: str = ":memory:",
    *,
    use_db_events: bool = False,
    query_limit: int = 100,
    min_priority: int = 0,
    topic: str | None = None,
    tool_adapter: Any | None = None,
    events: Iterable[dict[str, Any]] | None = None,
    session_id: str | None = None,
    maf_provider_mode: str = "deterministic_fake",
    allow_model_call: bool = False,
    memory: Any | None = None,
    memory_backend: str = "fake",
    mem0_client: Any | None = None,
    provider_client: Any | None = None,
    rational_backend: str = "auto",
    copilot_agent_factory: Any | None = None,
    require_real_tool_adapter: bool = False,
    event_source_label: str | None = None,
    federation_route_provider: Callable[[PerceptionFrame, dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    data_store = CoreDataStore(db_path)
    try:
        maf_runtime_profile = build_maf_runtime_profile(provider_mode=maf_provider_mode)
        resolved_provider_client = provider_client
        if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value:
            if not allow_model_call:
                raise ValueError("real_provider_mode_requires_allow_model_call")
            if resolved_provider_client is None:
                resolved_provider_client = build_default_maf_provider_client(
                    maf_runtime_profile
                )
        if rational_backend == "copilot" and not allow_model_call:
            raise ValueError("copilot_rational_backend_requires_allow_model_call")
        resolved_memory = memory or build_memory_backend(
            memory_backend,
            data_store,
            mem0_client=mem0_client,
        )
        workflow = NoModelCoreWorkflow(
            data_store=data_store,
            memory=resolved_memory,
            tool_adapter=tool_adapter,
            maf_runtime_profile=maf_runtime_profile,
            provider_client=resolved_provider_client,
            rational_backend=rational_backend,
            allow_model_call=allow_model_call,
            copilot_agent_factory=copilot_agent_factory,
            federation_route_provider=federation_route_provider,
        )
        result = workflow.run(
            events if events is not None else sample_events(),
            use_db_events=use_db_events,
            query_limit=query_limit,
            min_priority=min_priority,
            topic=topic,
            session_id=session_id,
            event_source=(
                event_source_label
                if event_source_label is not None
                else "provided"
                if events is not None
                else "sample"
            ),
        )
        return _build_workflow_run_payload(
            result,
            workflow,
            data_store,
            maf_runtime_profile=maf_runtime_profile,
            use_db_events=use_db_events,
            query_limit=query_limit,
            min_priority=min_priority,
            topic=topic,
            require_real_tool_adapter=require_real_tool_adapter,
            event_source=(
                event_source_label
                if event_source_label is not None
                else "provided"
                if events is not None
                else "sample"
            ),
        )
    finally:
        data_store.close()


def _build_db_counts(data_store: CoreDataStore) -> dict[str, int]:
    return {
        "perception_events": data_store.count("perception_events"),
        "execution_spans": data_store.count("execution_spans"),
        "facts": data_store.count("facts"),
        "policy_decisions": data_store.count("policy_decisions"),
        "memory_candidates": data_store.count("memory_candidates"),
        "long_term_memories": data_store.count("long_term_memories"),
        "tool_results": data_store.count("tool_results"),
        "approval_requests": data_store.count("approval_requests"),
        "approval_decisions": data_store.count("approval_decisions"),
        "audit_records": data_store.count("audit_records"),
    }


def _build_workflow_run_payload(
    result: WorkflowResult,
    workflow: NoModelCoreWorkflow,
    data_store: CoreDataStore,
    *,
    maf_runtime_profile: MafRuntimeProfile,
    use_db_events: bool,
    query_limit: int,
    min_priority: int,
    topic: str | None,
    require_real_tool_adapter: bool,
    event_source: str,
) -> dict[str, Any]:
    payload = result.to_dict()
    payload["maf_runtime"] = workflow.maf_runtime_metadata()
    payload["memory_runtime"] = workflow.memory_runtime_metadata()
    payload["release_gate_require_real_tool_adapter"] = require_real_tool_adapter
    execution_evidence = data_store.build_execution_evidence(
        result.execution_span_id,
        result.audit_id,
    )
    payload["runtime_mode"] = (
        "real_llm"
        if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
        else "deterministic"
    )
    audit_payload = cast(dict[str, Any], execution_evidence["audit_record"]["payload"])
    session_context = cast(dict[str, Any], audit_payload.get("session_context") or {})
    payload["model_call_evidence"] = session_context.get("model_call_evidence")
    payload["db_counts"] = _build_db_counts(data_store)
    payload["query"] = {
        "use_db_events": use_db_events,
        "query_limit": query_limit,
        "min_priority": min_priority,
        "topic": topic,
        "recent_topics": data_store.get_recent_topics(limit=min(query_limit, 10)),
    }
    payload["execution_evidence"] = execution_evidence
    payload["event_source"] = event_source
    payload["session"] = {
        **workflow.session_manager.load_snapshot(
            result.session_id,
            current_execution_span_id=result.execution_span_id,
            limit=5,
        ).to_dict()
    }
    payload["agent_run_evidence"] = _build_agent_run_evidence(payload)
    return payload


def run_event_replay(
    events: Iterable[dict[str, Any]],
    db_path: str = ":memory:",
    *,
    session_id: str | None = None,
    maf_provider_mode: str = "deterministic_fake",
    allow_model_call: bool = False,
    memory: Any | None = None,
    memory_backend: str = "fake",
    mem0_client: Any | None = None,
    provider_client: Any | None = None,
    rational_backend: str = "auto",
    copilot_agent_factory: Any | None = None,
    tool_adapter: Any | None = None,
    require_real_tool_adapter: bool = False,
    replay_label: str | None = None,
    federation_route_provider: Callable[[PerceptionFrame, dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    raw_events = [dict(event) for event in events]
    payload = run_no_model_dry_run(
        db_path,
        tool_adapter=tool_adapter,
        events=raw_events,
        session_id=session_id,
        maf_provider_mode=maf_provider_mode,
        allow_model_call=allow_model_call,
        memory=memory,
        memory_backend=memory_backend,
        mem0_client=mem0_client,
        provider_client=provider_client,
        rational_backend=rational_backend,
        copilot_agent_factory=copilot_agent_factory,
        require_real_tool_adapter=require_real_tool_adapter,
        event_source_label="replay_file",
        federation_route_provider=federation_route_provider,
    )
    replay_topics = sorted(
        {
            str(event.get("semantic_topic") or event.get("event_type") or "unknown")
            for event in raw_events
        }
    )
    payload["command"] = "event-replay"
    payload["event_source"] = "replay_file"
    payload["event_replay"] = {
        "replay_label": replay_label or "inline",
        "provided_event_count": len(raw_events),
        "normalized_event_count": int(payload.get("events_persisted", 0)),
        "duplicate_event_count": max(
            0,
            len(raw_events) - int(payload.get("events_persisted", 0)),
        ),
        "replayed_topics": replay_topics,
    }
    return payload


def run_event_daemon_replay(
    event_batches: Iterable[Iterable[dict[str, Any]]],
    db_path: str = ":memory:",
    *,
    session_id: str | None = None,
    maf_provider_mode: str = "deterministic_fake",
    allow_model_call: bool = False,
    memory: Any | None = None,
    memory_backend: str = "fake",
    mem0_client: Any | None = None,
    provider_client: Any | None = None,
    rational_backend: str = "auto",
    copilot_agent_factory: Any | None = None,
    tool_adapter: Any | None = None,
    require_real_tool_adapter: bool = False,
    replay_label: str | None = None,
    federation_route_provider: Callable[[PerceptionFrame, dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    batches = [[dict(event) for event in batch] for batch in event_batches]
    data_store = CoreDataStore(db_path)
    try:
        maf_runtime_profile = build_maf_runtime_profile(provider_mode=maf_provider_mode)
        resolved_provider_client = provider_client
        if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value:
            if not allow_model_call:
                raise ValueError("real_provider_mode_requires_allow_model_call")
            if resolved_provider_client is None:
                resolved_provider_client = build_default_maf_provider_client(
                    maf_runtime_profile
                )
        if rational_backend == "copilot" and not allow_model_call:
            raise ValueError("copilot_rational_backend_requires_allow_model_call")
        resolved_memory = memory or build_memory_backend(
            memory_backend,
            data_store,
            mem0_client=mem0_client,
        )
        shared_router = PerceptionEventRouter()
        workflow = NoModelCoreWorkflow(
            data_store=data_store,
            memory=resolved_memory,
            tool_adapter=tool_adapter,
            maf_runtime_profile=maf_runtime_profile,
            provider_client=resolved_provider_client,
            rational_backend=rational_backend,
            allow_model_call=allow_model_call,
            copilot_agent_factory=copilot_agent_factory,
            event_router=shared_router,
            federation_route_provider=federation_route_provider,
        )
        seeded_dedupe_keys = data_store.get_recent_dedupe_keys(limit=1000)
        shared_router.seed_dedupe_keys(seeded_dedupe_keys)
        resolved_session_id = session_id
        cycle_results: list[dict[str, Any]] = []
        total_provided_events = 0
        total_normalized_events = 0
        observed_topics: set[str] = set()
        for index, batch in enumerate(batches, start=1):
            total_provided_events += len(batch)
            for event in batch:
                observed_topics.add(
                    str(event.get("semantic_topic") or event.get("event_type") or "unknown")
                )
            result = workflow.run(
                batch,
                session_id=resolved_session_id,
                event_source="daemon_replay_file",
            )
            resolved_session_id = result.session_id
            total_normalized_events += result.events_persisted
            cycle_results.append(
                {
                    "cycle_index": index,
                    "provided_event_count": len(batch),
                    "normalized_event_count": result.events_persisted,
                    "duplicate_event_count": max(0, len(batch) - result.events_persisted),
                    "execution_span_id": result.execution_span_id,
                    "audit_id": result.audit_id,
                    "status": result.status,
                    "delegated": result.delegated,
                    "steps": list(result.steps),
                    "tool_result_count": len(result.tool_results),
                    "final_response": dict(result.final_response),
                }
            )
        payload: dict[str, Any] = {
            "ok": True,
            "status": "ok",
            "command": "event-daemon",
            "event_source": "daemon_replay_file",
            "runtime_mode": (
                "real_llm"
                if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value
                else "deterministic"
            ),
            "session_id": resolved_session_id,
            "maf_runtime": workflow.maf_runtime_metadata(),
            "memory_runtime": workflow.memory_runtime_metadata(),
            "db_counts": {
                "perception_events": data_store.count("perception_events"),
                "execution_spans": data_store.count("execution_spans"),
                "facts": data_store.count("facts"),
                "policy_decisions": data_store.count("policy_decisions"),
                "memory_candidates": data_store.count("memory_candidates"),
                "long_term_memories": data_store.count("long_term_memories"),
                "tool_results": data_store.count("tool_results"),
                "approval_requests": data_store.count("approval_requests"),
                "approval_decisions": data_store.count("approval_decisions"),
                "audit_records": data_store.count("audit_records"),
            },
            "event_daemon_evidence": {
                "schema_version": "1.2.3-event-daemon-evidence-v1",
                "replay_label": replay_label or "inline",
                "cycle_count": len(cycle_results),
                "provided_event_count": total_provided_events,
                "normalized_event_count": total_normalized_events,
                "duplicate_event_count": max(0, total_provided_events - total_normalized_events),
                "seeded_dedupe_key_count": len(seeded_dedupe_keys),
                "dedupe_key_count": len(shared_router.seen_dedupe_keys),
                "observed_topics": sorted(observed_topics),
                "cycles": cycle_results,
            },
            "release_gate_require_real_tool_adapter": require_real_tool_adapter,
        }
        return payload
    finally:
        data_store.close()


def _event_service_failure_class(failure_status: str) -> str:
    if failure_status == "no_reply":
        return "event_service_monitor_unreachable"
    if failure_status in ("endpoint_drift", "stale_endpoint"):
        return "event_service_stale_endpoint"
    if failure_status == "no_events_collected":
        return "event_service_monitor_empty"
    return "event_service_monitor_failed"


def _event_service_topics(events: Iterable[Any]) -> list[str]:
    topics: set[str] = set()
    for event in events:
        if isinstance(event, PerceptionEvent):
            payload = event.payload
            if isinstance(payload, dict):
                payload_topic = str(
                    payload.get("semantic_topic") or payload.get("event_type") or ""
                )
                if payload_topic:
                    topics.add(payload_topic)
            topic = str(event.semantic_topic or event.event_type or "")
        else:
            payload = event.get("payload") if isinstance(event, dict) else None
            if isinstance(payload, dict):
                payload_topic = str(
                    payload.get("semantic_topic") or payload.get("event_type") or ""
                )
                if payload_topic:
                    topics.add(payload_topic)
            topic = (
                str(event.get("semantic_topic") or event.get("event_type") or "")
                if isinstance(event, dict)
                else ""
            )
        if topic:
            topics.add(topic)
    return sorted(topic for topic in topics if topic)


def run_live_event_service(
    db_path: str = ":memory:",
    *,
    event_source: str = "app",
    app_id: str = "",
    duration: int = 5,
    max_events: int = 1,
    cycles: int = 1,
    ready_file: str = "",
    session_id: str | None = None,
    maf_provider_mode: str = "deterministic_fake",
    allow_model_call: bool = False,
    memory: Any | None = None,
    memory_backend: str = "fake",
    mem0_client: Any | None = None,
    provider_client: Any | None = None,
    rational_backend: str = "auto",
    copilot_agent_factory: Any | None = None,
    tool_adapter: Any | None = None,
    federation_route_provider: Callable[[PerceptionFrame, dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    if event_source not in ("app", "unit"):
        raise ValueError("event_service_requires_valid_event_source")
    if event_source == "app" and not app_id:
        raise ValueError("event_service_requires_app_id")
    if int(cycles) <= 0:
        raise ValueError("event_service_requires_positive_cycles")

    resolved_tool_adapter = tool_adapter or NeuroCliToolAdapter()
    data_store = CoreDataStore(db_path)
    try:
        maf_runtime_profile = build_maf_runtime_profile(provider_mode=maf_provider_mode)
        resolved_provider_client = provider_client
        if maf_runtime_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value:
            if not allow_model_call:
                raise ValueError("real_provider_mode_requires_allow_model_call")
            if resolved_provider_client is None:
                resolved_provider_client = build_default_maf_provider_client(
                    maf_runtime_profile
                )
        if rational_backend == "copilot" and not allow_model_call:
            raise ValueError("copilot_rational_backend_requires_allow_model_call")
        resolved_memory = memory or build_memory_backend(
            memory_backend,
            data_store,
            mem0_client=mem0_client,
        )
        shared_router = PerceptionEventRouter()
        seeded_dedupe_keys = data_store.get_recent_dedupe_keys(limit=1000)
        shared_router.seed_dedupe_keys(seeded_dedupe_keys)
        workflow = NoModelCoreWorkflow(
            data_store=data_store,
            memory=resolved_memory,
            tool_adapter=resolved_tool_adapter,
            maf_runtime_profile=maf_runtime_profile,
            provider_client=resolved_provider_client,
            rational_backend=rational_backend,
            allow_model_call=allow_model_call,
            copilot_agent_factory=copilot_agent_factory,
            event_router=shared_router,
            federation_route_provider=federation_route_provider,
        )
        resolved_session_id = workflow.session_manager.resolve_session_id(session_id)
        service_execution_span_id = new_id("span")
        service_subject = app_id if event_source == "app" else "unit-events"
        event_source_label = (
            "neuro_cli_app_events_live"
            if event_source == "app"
            else "neuro_cli_events_live"
        )
        monitor_command = "app-events" if event_source == "app" else "events"
        lifecycle: list[dict[str, Any]] = []
        cycle_summaries: list[dict[str, Any]] = []
        total_collected_event_count = 0
        total_persisted_event_count = 0
        total_duplicate_event_count = 0
        last_workflow_payload: dict[str, Any] | None = None
        last_checkpoint_event_id = ""
        latest_subscription: Any | None = None
        latest_listener_mode: Any | None = None
        latest_handler_audit: Any | None = None

        def record_lifecycle(state: str, **extra: Any) -> None:
            entry = {
                "lifecycle_state": state,
                "timestamp_wall": utc_now_iso(),
                **extra,
            }
            lifecycle.append(entry)
            data_store.persist_fact(
                service_execution_span_id,
                "event_service_lifecycle",
                service_subject,
                entry,
            )

        def base_event_service_payload() -> dict[str, Any]:
            payload: dict[str, Any] = {
                "schema_version": EVENT_SERVICE_SCHEMA_VERSION,
                "bounded_runtime": True,
                "event_source_kind": event_source,
                "monitor_command": monitor_command,
                "duration": duration,
                "max_events": max_events,
                "cycle_count": cycles,
                "execution_span_id": service_execution_span_id,
                "workflow_execution_span_id": None,
                "session_id": resolved_session_id,
                "subscription": None,
                "listener_mode": None,
                "handler_audit": None,
                "lifecycle": lifecycle,
                "cycle_summaries": cycle_summaries,
                "checkpoint": {
                    "last_event_id": "",
                    "persisted_event_count": 0,
                },
                "seeded_dedupe_key_count": len(seeded_dedupe_keys),
                "collected_event_count": total_collected_event_count,
                "duplicate_event_count": total_duplicate_event_count,
                "normalized_event_count": total_persisted_event_count,
            }
            if event_source == "app":
                payload["app_id"] = app_id
            return payload

        data_store.persist_execution_span(
            service_execution_span_id,
            "running",
            {
                "command": "event-service",
                "event_source": event_source_label,
                "event_source_kind": event_source,
                "monitor_command": monitor_command,
                "app_id": app_id,
                "duration": duration,
                "max_events": max_events,
                "cycles": cycles,
            },
            session_id=resolved_session_id,
        )
        record_lifecycle(
            "start",
            service_status="running",
            event_source=event_source_label,
            bounded_runtime=True,
        )
        if seeded_dedupe_keys:
            record_lifecycle(
                "restart",
                service_status="running",
                restart_reason="checkpoint_seeded",
                seeded_dedupe_key_count=len(seeded_dedupe_keys),
            )

        def fail_event_service(status: str, failure_status: str) -> dict[str, Any]:
            record_lifecycle(
                "clean_shutdown",
                service_status="failed",
                shutdown_reason=failure_status,
            )
            event_service_payload = base_event_service_payload()
            event_service_payload["failure_status"] = failure_status
            data_store.persist_fact(
                service_execution_span_id,
                "event_service_checkpoint",
                service_subject,
                dict(event_service_payload["checkpoint"]),
            )
            data_store.persist_execution_span(
                service_execution_span_id,
                "failed",
                {
                    "command": "event-service",
                    "status": status,
                    "failure_status": failure_status,
                    "event_source": event_source_label,
                    "event_service": event_service_payload,
                },
                session_id=resolved_session_id,
            )
            return {
                "ok": False,
                "status": status,
                "command": "event-service",
                "failure_class": _event_service_failure_class(failure_status),
                "failure_status": failure_status,
                "event_source": event_source_label,
                "tool_adapter_runtime": resolved_tool_adapter.runtime_metadata(),
                "session_id": resolved_session_id,
                "db_counts": _build_db_counts(data_store),
                "event_service": event_service_payload,
            }

        for cycle_index in range(1, int(cycles) + 1):
            try:
                if event_source == "app":
                    live_event_payload = resolved_tool_adapter.collect_app_events(
                        app_id,
                        duration=duration,
                        max_events=max_events,
                        ready_file=ready_file,
                    )
                else:
                    live_event_payload = resolved_tool_adapter.collect_live_events(
                        duration=duration,
                        max_events=max_events,
                        ready_file=ready_file,
                    )
            except ValueError as exc:
                failure_status = str(exc) or "event_service_monitor_failed"
                record_lifecycle(
                    failure_status,
                    service_status="failed",
                    cycle_index=cycle_index,
                    failure_status=failure_status,
                )
                return fail_event_service("event_service_monitor_failed", failure_status)

            events = [
                dict(event)
                for event in cast(list[Any], live_event_payload.get("events") or [])
                if isinstance(event, dict)
            ]
            topic_probe_router = PerceptionEventRouter()
            topic_probe_router.seed_dedupe_keys(shared_router.seen_dedupe_keys)
            normalized_probe_events = topic_probe_router.normalize(events)
            duplicate_event_count = max(0, len(events) - len(normalized_probe_events))
            observed_topics = _event_service_topics(normalized_probe_events or events)
            total_collected_event_count += len(events)
            total_duplicate_event_count += duplicate_event_count

            record_lifecycle(
                "ready",
                service_status="ready",
                cycle_index=cycle_index,
                subscription=live_event_payload.get("subscription"),
                listener_mode=live_event_payload.get("listener_mode"),
            )

            event_service_payload = base_event_service_payload()
            latest_subscription = live_event_payload.get("subscription")
            latest_listener_mode = live_event_payload.get("listener_mode")
            latest_handler_audit = live_event_payload.get("handler_audit")
            event_service_payload["subscription"] = latest_subscription
            event_service_payload["listener_mode"] = latest_listener_mode
            event_service_payload["handler_audit"] = latest_handler_audit
            event_service_payload["collected_event_count"] = total_collected_event_count
            event_service_payload["duplicate_event_count"] = total_duplicate_event_count

            if not events and cycle_index == 1 and total_persisted_event_count == 0:
                record_lifecycle(
                    "no_events",
                    service_status="completed",
                    cycle_index=cycle_index,
                    collected_event_count=0,
                )
                return fail_event_service("event_service_ingest_empty", "no_events_collected")

            workflow_result = workflow.run(
                events,
                session_id=resolved_session_id,
                event_source=event_source_label,
            )
            resolved_session_id = workflow_result.session_id
            workflow_payload = _build_workflow_run_payload(
                workflow_result,
                workflow,
                data_store,
                maf_runtime_profile=maf_runtime_profile,
                use_db_events=False,
                query_limit=100,
                min_priority=0,
                topic=None,
                require_real_tool_adapter=True,
                event_source=event_source_label,
            )
            last_workflow_payload = workflow_payload
            persisted_event_count = int(workflow_payload.get("events_persisted", 0))
            total_persisted_event_count += persisted_event_count
            cycle_summary = {
                "cycle_index": cycle_index,
                "raw_event_count": len(events),
                "duplicate_event_count": duplicate_event_count,
                "persisted_event_count": persisted_event_count,
                "workflow_execution_span_id": workflow_payload.get("execution_span_id"),
                "observed_topics": observed_topics,
                "last_event_id": str(events[-1].get("event_id") or "") if events else "",
            }
            cycle_summaries.append(cycle_summary)
            event_service_payload["normalized_event_count"] = total_persisted_event_count
            event_service_payload["workflow_execution_span_id"] = workflow_payload.get(
                "execution_span_id"
            )
            if cycle_summary["last_event_id"]:
                last_checkpoint_event_id = str(cycle_summary["last_event_id"])
            event_service_payload["checkpoint"] = {
                "last_event_id": last_checkpoint_event_id,
                "persisted_event_count": total_persisted_event_count,
            }

            if "unit.network.endpoint_drift" in observed_topics:
                record_lifecycle(
                    "stale_endpoint",
                    service_status="running",
                    cycle_index=cycle_index,
                    observed_topics=observed_topics,
                )

            if persisted_event_count > 0:
                record_lifecycle(
                    "events_persisted",
                    service_status="running" if cycle_index < int(cycles) else "completed",
                    cycle_index=cycle_index,
                    collected_event_count=len(events),
                    persisted_event_count=persisted_event_count,
                    duplicate_event_count=duplicate_event_count,
                    workflow_execution_span_id=workflow_payload.get("execution_span_id"),
                )

            if cycle_index < int(cycles) or persisted_event_count == 0:
                record_lifecycle(
                    "heartbeat",
                    service_status="running" if cycle_index < int(cycles) else "completed",
                    cycle_index=cycle_index,
                    collected_event_count=len(events),
                    persisted_event_count=persisted_event_count,
                    duplicate_event_count=duplicate_event_count,
                    workflow_execution_span_id=workflow_payload.get("execution_span_id"),
                )

        event_service_payload = base_event_service_payload()
        event_service_payload["subscription"] = latest_subscription
        event_service_payload["listener_mode"] = latest_listener_mode
        event_service_payload["handler_audit"] = latest_handler_audit
        if last_workflow_payload is not None:
            event_service_payload["workflow_execution_span_id"] = last_workflow_payload.get(
                "execution_span_id"
            )
        event_service_payload["checkpoint"] = {
            "last_event_id": last_checkpoint_event_id,
            "persisted_event_count": total_persisted_event_count,
        }
        data_store.persist_fact(
            service_execution_span_id,
            "event_service_checkpoint",
            service_subject,
            dict(event_service_payload["checkpoint"]),
        )
        record_lifecycle(
            "clean_shutdown",
            service_status="completed",
            shutdown_reason="bounded_runtime_complete",
        )
        data_store.persist_execution_span(
            service_execution_span_id,
            "completed",
            {
                "command": "event-service",
                "status": "ok",
                "event_source": event_source_label,
                "event_service": event_service_payload,
                "workflow_execution_span_id": event_service_payload.get(
                    "workflow_execution_span_id"
                ),
            },
            session_id=resolved_session_id,
        )
        payload = dict(last_workflow_payload or {})
        payload["ok"] = True
        payload["status"] = "ok"
        payload["command"] = "event-service"
        payload["event_source"] = event_source_label
        payload["session_id"] = resolved_session_id
        payload["events_persisted"] = total_persisted_event_count
        payload["db_counts"] = _build_db_counts(data_store)
        payload["event_service"] = event_service_payload
        return payload
    finally:
        data_store.close()


def _build_agent_run_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    maf_runtime = cast(dict[str, Any], payload.get("maf_runtime") or {})
    memory_runtime = cast(dict[str, Any], payload.get("memory_runtime") or {})
    model_call_evidence = cast(dict[str, Any] | None, payload.get("model_call_evidence"))
    execution_evidence = cast(dict[str, Any], payload.get("execution_evidence") or {})
    audit_record = cast(dict[str, Any] | None, execution_evidence.get("audit_record"))
    audit_payload = cast(dict[str, Any], (audit_record or {}).get("payload") or {})
    tool_adapter_runtime = cast(dict[str, Any], audit_payload.get("adapter_runtime") or {})
    session_context = cast(dict[str, Any], audit_payload.get("session_context") or {})
    rational_plan_evidence = cast(
        dict[str, Any] | None,
        audit_payload.get("rational_plan_evidence")
        or session_context.get("rational_plan_evidence"),
    )
    prompt_safe_context = cast(dict[str, Any], session_context.get("prompt_safe_context") or {})
    affective_runtime = cast(dict[str, Any], prompt_safe_context.get("affective_runtime") or {})
    prompt_memory = cast(dict[str, Any], prompt_safe_context.get("memory") or {})
    recall_policy = cast(dict[str, Any], prompt_memory.get("recall_policy") or {})
    db_counts = cast(dict[str, Any], payload.get("db_counts") or {})
    tool_results = cast(list[Any], payload.get("tool_results") or [])
    policy_decisions = cast(list[Any], execution_evidence.get("policy_decisions") or [])
    approval_requests = cast(list[Any], execution_evidence.get("approval_requests") or [])
    rational_backend = _extract_rational_backend_metadata(maf_runtime)
    prompt_safety_boundaries = cast(
        dict[str, Any],
        prompt_safe_context.get("safety_boundaries") or {},
    )
    affective_multimodal = cast(
        dict[str, Any],
        affective_runtime.get("multimodal_summary") or {},
    )
    affective_profile_route = cast(
        dict[str, Any],
        affective_runtime.get("profile_route") or {},
    )
    affective_presentation_policy = cast(
        dict[str, Any],
        affective_runtime.get("presentation_policy") or {},
    )
    real_tool_adapter_required = bool(payload.get("release_gate_require_real_tool_adapter", False))
    real_tool_adapter_present = tool_adapter_runtime.get("adapter_kind") == "neuro-cli"
    real_tool_execution_succeeded = False
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        result_payload = cast(dict[str, Any], result)
        if result_payload.get("status") == "ok":
            real_tool_execution_succeeded = True
            break
    closure_gates: dict[str, bool] = {
        "provider_runtime_metadata_present": bool(maf_runtime),
        "rational_backend_metadata_present": bool(rational_backend),
        "rational_plan_evidence_present": bool(rational_plan_evidence),
        "rational_plan_outcome_recorded": str(
            (rational_plan_evidence or {}).get("status") or ""
        )
        in {"tool_selected", "no_tool_selected", "invalid_payload"},
        "memory_runtime_metadata_present": bool(memory_runtime),
        "model_call_evidence_present": model_call_evidence is not None,
        "prompt_safe_context_present": bool(prompt_safe_context),
        "affective_runtime_context_present": bool(affective_runtime),
        "db_counts_present": bool(db_counts),
        "execution_evidence_present": bool(execution_evidence),
        "policy_or_pending_evidence_present": bool(policy_decisions or approval_requests),
        "tool_result_or_pending_approval_present": bool(tool_results or approval_requests),
        "audit_record_present": audit_record is not None,
        "final_response_present": bool(payload.get("final_response")),
        "provider_context_is_prompt_safe": (
            prompt_safe_context.get("schema_version") == "1.2.5-prompt-safe-context-v2"
        ),
        "multimodal_summary_present": bool(affective_multimodal),
        "profile_route_recorded": bool(affective_profile_route),
        "presentation_policy_recorded": bool(affective_presentation_policy),
        "memory_recall_policy_present": bool(recall_policy),
        "affective_memory_recall_recorded": bool(recall_policy.get("affective_recall")),
        "rational_memory_recall_recorded": bool(recall_policy.get("rational_recall")),
        "direct_tool_execution_by_model_disabled": bool(
            prompt_safety_boundaries.get("can_execute_tools_directly") is False
        ),
    }
    if real_tool_adapter_required:
        closure_gates["real_tool_adapter_present"] = real_tool_adapter_present
        closure_gates["real_tool_execution_succeeded"] = real_tool_execution_succeeded
    return {
        "schema_version": AGENT_RUN_EVIDENCE_SCHEMA_VERSION,
        "workflow": "agent-run",
        "event_source": payload.get("event_source"),
        "runtime_mode": payload.get("runtime_mode"),
        "provider_runtime": {
            "provider_mode": maf_runtime.get("provider_mode"),
            "real_provider_enabled": maf_runtime.get("real_provider_enabled"),
            "provider_ready_for_model_call": maf_runtime.get(
                "provider_ready_for_model_call"
            ),
            "agent_adapter_count": len(maf_runtime.get("agent_adapters") or []),
        },
        "rational_backend": rational_backend,
        "memory_runtime": memory_runtime,
        "tool_adapter_runtime": tool_adapter_runtime,
        "release_gate_require_real_tool_adapter": real_tool_adapter_required,
        "real_tool_adapter_present": real_tool_adapter_present,
        "real_tool_execution_succeeded": real_tool_execution_succeeded,
        "model_call_evidence": model_call_evidence,
        "rational_plan_evidence": rational_plan_evidence,
        "prompt_safe_context": {
            "schema_version": prompt_safe_context.get("schema_version"),
            "memory_lookup_count": prompt_memory.get("lookup_count"),
            "affective_memory_count": cast(
                dict[str, Any], recall_policy.get("affective_recall") or {}
            ).get("selected_count"),
            "rational_memory_count": cast(
                dict[str, Any], recall_policy.get("rational_recall") or {}
            ).get("selected_count"),
            "available_tool_count": len(prompt_safe_context.get("available_tools") or []),
            "pending_approval_count": len(prompt_safe_context.get("pending_approvals") or []),
            "safety_boundaries": prompt_safety_boundaries,
        },
        "memory_recall_policy": recall_policy,
        "affective_runtime": {
            "schema_version": affective_runtime.get("schema_version"),
            "input_modes": list(affective_multimodal.get("input_modes") or []),
            "selected_profile": affective_profile_route.get("selected_profile"),
            "route_status": affective_profile_route.get("route_status"),
            "route_ready": affective_profile_route.get("route_ready"),
            "presentation_policy": affective_presentation_policy,
        },
        "db_counts": db_counts,
        "evidence_counts": {
            "facts": len(execution_evidence.get("facts") or []),
            "policy_decisions": len(policy_decisions),
            "memory_candidates": len(execution_evidence.get("memory_candidates") or []),
            "long_term_memories": len(execution_evidence.get("long_term_memories") or []),
            "approval_requests": len(approval_requests),
            "tool_results": len(tool_results),
        },
        "audit": {
            "audit_id": payload.get("audit_id"),
            "audit_record_present": audit_record is not None,
            "session_id": payload.get("session_id"),
        },
        "final_response": payload.get("final_response"),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _extract_rational_backend_metadata(maf_runtime: dict[str, Any]) -> dict[str, Any]:
    for adapter in cast(list[Any], maf_runtime.get("agent_adapters") or []):
        if not isinstance(adapter, dict):
            continue
        adapter_payload = cast(dict[str, Any], adapter)
        if adapter_payload.get("agent_role") != "rational":
            continue
        rational_backend = adapter_payload.get("rational_backend")
        if isinstance(rational_backend, dict):
            return cast(dict[str, Any], rational_backend)
    return {}


def apply_approval_decision(
    db_path: str,
    *,
    approval_request_id: str,
    decision: str,
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    if decision not in {"approve", "deny", "expire"}:
        raise ValueError("approval_decision_must_be_approve_deny_or_expire")

    data_store = CoreDataStore(db_path)
    try:
        approval_request = data_store.get_approval_request(approval_request_id)
        if approval_request is None:
            raise ValueError("approval_request_not_found")
        if approval_request["status"] != "pending":
            raise ValueError(
                f"approval_request_not_pending_{approval_request['status']}"
            )

        session_id = str(approval_request["session_id"])
        request_payload = cast(dict[str, Any], approval_request["payload"])
        decision_payload: dict[str, Any] = {
            "decision": decision,
            "tool_name": approval_request["tool_name"],
            "source_execution_span_id": approval_request["source_execution_span_id"],
        }
        resumed_execution: dict[str, Any] | None = None
        updated_status = "denied"

        if decision == "approve":
            adapter = tool_adapter or FakeUnitToolAdapter()
            operator_requirements = _build_operator_requirements(
                approval_request,
                tool_adapter=adapter,
            )
            decision_payload["operator_requirements"] = operator_requirements
            if not operator_requirements["resource_requirements_satisfied"]:
                decision_payload.update(
                    {
                        "decision_outcome": "blocked_resource_gate",
                        "failure_class": "approval_resource_gate_unsatisfied",
                        "failure_status": "missing_required_resources",
                        "missing_required_resources": list(
                            operator_requirements["missing_required_resources"]
                        ),
                    }
                )
                data_store.persist_approval_decision(
                    approval_request_id,
                    session_id,
                    decision,
                    decision_payload,
                )
                updated_request_payload: dict[str, Any] = {
                    **request_payload,
                    "status": "pending",
                    "last_decision_attempt": decision,
                    "last_decision_outcome": "blocked_resource_gate",
                    "last_missing_required_resources": list(
                        operator_requirements["missing_required_resources"]
                    ),
                }
                data_store.persist_approval_request(
                    session_id,
                    str(approval_request["source_execution_span_id"]),
                    str(approval_request["tool_name"]),
                    "pending",
                    updated_request_payload,
                    approval_request_id=approval_request_id,
                )

                updated_request = data_store.get_approval_request(approval_request_id)
                assert updated_request is not None
                return {
                    "ok": False,
                    "status": "blocked_resource_gate",
                    "failure_class": "approval_resource_gate_unsatisfied",
                    "failure_status": "missing_required_resources",
                    "approval_request": updated_request,
                    "approval_decisions": data_store.get_approval_decisions(
                        approval_request_id
                    ),
                    "resumed_execution": None,
                    "approval_context": build_approval_context(
                        data_store,
                        updated_request,
                        tool_adapter=adapter,
                        operator_requirements=operator_requirements,
                    ),
                    "session": CoreSessionManager(data_store).load_snapshot(
                        session_id, limit=5
                    ).to_dict(),
                }

            execution_span_id = new_id("span")
            tool_name = str(approval_request["tool_name"])
            requested_args = cast(dict[str, Any], request_payload.get("requested_args") or {})
            resolved_args = dict(requested_args)
            target_app_id = str(operator_requirements.get("target_app_id") or "")
            if target_app_id:
                resolved_args.setdefault("app_id", target_app_id)
                resolved_args.setdefault("app", target_app_id)
            matching_lease_ids = cast(
                list[Any],
                operator_requirements.get("matching_lease_ids") or [],
            )
            if matching_lease_ids:
                first_lease_id = str(matching_lease_ids[0] or "")
                if first_lease_id:
                    resolved_args.setdefault("lease_id", first_lease_id)
            result = adapter.execute(tool_name, resolved_args)
            result.payload["approval_request_id"] = approval_request_id
            result.payload["approval_decision"] = "approve"
            final_response: dict[str, Any] = {
                "speaker": "affective",
                "delegated": True,
                "text": f"Approved delegated {tool_name.replace('system_', '').replace('_', ' ')} and resumed execution.",
                "salience": 80,
            }
            audit_id = new_id("audit")

            data_store.persist_execution_span(
                execution_span_id,
                "running",
                {
                    "session_id": session_id,
                    "approval_request_id": approval_request_id,
                    "resumed_from_execution_span_id": approval_request["source_execution_span_id"],
                    "decision": decision,
                },
                session_id=session_id,
            )
            data_store.persist_tool_result(
                result.tool_result_id,
                execution_span_id,
                result.tool_name,
                result.status,
                result.payload,
            )
            data_store.persist_audit_record(
                audit_id,
                execution_span_id,
                "ok",
                {
                    "approval_request_id": approval_request_id,
                    "approval_decision": decision,
                    "resumed_execution": result.to_dict(),
                    "final_response": final_response,
                },
                session_id=session_id,
            )
            data_store.persist_execution_span(
                execution_span_id,
                "ok",
                {
                    "session_id": session_id,
                    "approval_request_id": approval_request_id,
                    "decision": decision,
                    "tool_result_id": result.tool_result_id,
                    "audit_id": audit_id,
                },
                session_id=session_id,
            )
            resumed_execution = {
                "execution_span_id": execution_span_id,
                "tool_result": result.to_dict(),
                "audit_id": audit_id,
                "final_response": final_response,
            }
            decision_payload["resumed_execution_span_id"] = execution_span_id
            updated_status = "approved"
        elif decision == "expire":
            updated_status = "expired"

        data_store.persist_approval_decision(
            approval_request_id,
            session_id,
            decision,
            decision_payload,
        )
        updated_request_payload: dict[str, Any] = {
            **request_payload,
            "status": updated_status,
            "last_decision": decision,
        }
        if resumed_execution is not None:
            updated_request_payload["resumed_execution_span_id"] = resumed_execution[
                "execution_span_id"
            ]
        data_store.persist_approval_request(
            session_id,
            str(approval_request["source_execution_span_id"]),
            str(approval_request["tool_name"]),
            updated_status,
            updated_request_payload,
            approval_request_id=approval_request_id,
        )

        updated_request = data_store.get_approval_request(approval_request_id)
        assert updated_request is not None

        return {
            "ok": True,
            "status": updated_status,
            "approval_request": updated_request,
            "approval_decisions": data_store.get_approval_decisions(approval_request_id),
            "resumed_execution": resumed_execution,
            "approval_context": build_approval_context(
                data_store,
                updated_request,
                tool_adapter=tool_adapter,
                resumed_execution=resumed_execution,
                operator_requirements=(
                    decision_payload.get("operator_requirements")
                    if isinstance(decision_payload.get("operator_requirements"), dict)
                    else None
                ),
            ),
            "session": CoreSessionManager(data_store).load_snapshot(session_id, limit=5).to_dict(),
        }
    finally:
        data_store.close()
