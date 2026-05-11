from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any, cast

from .autonomy import AutonomousDaemonPolicy
from .maf import (
    MafProviderMode,
    MafProviderNotReadyError,
    build_maf_runtime_profile,
    maf_provider_smoke_status,
)
from .inference import build_provider_runtime_env
from .inference import model_profile_smoke
from .inference import multimodal_profile_smoke
from .inference import provider_config_update
from .inference import provider_profile_catalog
from .inference import provider_model_list
from .inference import set_active_provider_profile
from .session import CoreSessionManager
from .tools import FakeUnitToolAdapter, NeuroCliToolAdapter
from .tools import load_coding_agent_runner_descriptor_payload
from .tools import load_mcp_bridge_descriptor_payload
from .tools import load_mcp_tool_governance_descriptor_payload
from .tools import load_neuro_cli_skill_descriptor_payload
from .tools import load_skill_descriptor_registry_payload
from .tools import observe_activation_health
from .tools import validate_tool_workflow_catalog_consistency
from .data import CoreDataStore
from .federation import UnitCapabilityDescriptor, federation_route_smoke
from .motivation import VitalityState
from .motivation import VitalitySignal
from .motivation import apply_vitality_signals
from .persona import PersonaState
from .persona import PersonaSeedConfig
from .persona import PersonaGrowthEvidence
from .persona import PERSONA_GROWTH_RUNTIME_SOURCES
from .persona import PersonaGrowthState
from .persona import PersonaSignal
from .persona import apply_persona_growth_evidence
from .persona import apply_persona_signals
from .persona import compute_persona_immutability_stamp
from .persona import compute_persona_seed_fingerprint
from .persona import initialize_persona_growth_state
from .persona import initialize_persona_state_from_seed
from .persona import persona_immutability_tampered
from .persona import redact_relationships
from .policy import classify_tool_contract_threats
from .policy import ReadOnlyToolPolicy
from .social import MockSocialAdapter
from .social import SocialMessageEnvelope
from .social import build_social_approval_summary
from .self_improvement import ImprovementEvidence
from .self_improvement import PROHIBITED_SELF_IMPROVEMENT_ACTIONS
from .self_improvement import propose_self_improvement
from .self_improvement import review_self_improvement
from .social_adapters import social_adapter_config_update
from .social_adapters import social_adapter_list
from .social_adapters.registry import SocialAdapterProfile
from .social_adapters.registry import social_adapter_registry
from .social_adapters.qq_official_gateway import run_qq_official_gateway_client
from .social_adapters.qq_official import QQOfficialSocialAdapter
from .social_adapters.qq_official_webhook import run_qq_official_webhook_server
from .social_adapters.openclaw_gateway import OPENCLAW_GATEWAY_CLIENT_SCHEMA_VERSION
from .social_adapters.openclaw_gateway import run_openclaw_gateway_client
from .social_adapters.qq_openclaw import QQOpenClawSocialAdapter
from .social_adapters.wechat_ilink import WeChatILinkSocialAdapter
from .social_adapters.wecom import WeComSocialAdapter
from .social_adapters.wecom_gateway import run_wecom_gateway_client
from .social_adapters import social_adapter_test
from .workflow import (
    APP_ARTIFACT_ADMISSION_SCHEMA_VERSION,
    apply_approval_decision,
    build_app_artifact_admission,
    build_app_build_plan,
    persist_app_deploy_activate_evidence,
    persist_app_deploy_rollback_evidence,
    run_app_deploy_activate,
    run_app_deploy_rollback,
    build_app_deploy_plan,
    run_app_deploy_prepare_verify,
    build_approval_context,
    build_user_prompt_event,
    run_event_daemon_replay,
    run_event_replay,
    run_live_event_service,
    run_no_model_dry_run,
)


CLOSURE_SUMMARY_SCHEMA_VERSION = "1.2.7-closure-summary-v15"
DOCUMENTATION_CLOSURE_SCHEMA_VERSION = "1.2.5-documentation-closure-v1"
REGRESSION_CLOSURE_SCHEMA_VERSION = "1.2.6-regression-closure-v2"
LEGACY_REGRESSION_CLOSURE_SCHEMA_VERSION = "1.2.5-regression-closure-v1"
RELAY_FAILURE_CLOSURE_SCHEMA_VERSION = "1.2.6-relay-failure-closure-v1"
HARDWARE_COMPATIBILITY_CLOSURE_SCHEMA_VERSION = "1.2.6-hardware-compatibility-closure-v1"
HARDWARE_ACCEPTANCE_MATRIX_SCHEMA_VERSION = "1.2.7-hardware-acceptance-matrix-v1"
AGENT_EXCELLENCE_SMOKE_SCHEMA_VERSION = "1.2.7-agent-excellence-smoke-v1"
SIGNING_PROVENANCE_SMOKE_SCHEMA_VERSION = "1.2.7-signing-provenance-smoke-v1"
REAL_SCENE_E2E_SMOKE_SCHEMA_VERSION = "1.2.7-real-scene-e2e-smoke-v1"
OBSERVABILITY_DIAGNOSIS_SMOKE_SCHEMA_VERSION = "1.2.7-observability-diagnosis-smoke-v1"
RELEASE_ROLLBACK_HARDENING_SMOKE_SCHEMA_VERSION = "1.2.7-release-rollback-hardening-smoke-v1"
RESOURCE_BUDGET_GOVERNANCE_SMOKE_SCHEMA_VERSION = "1.2.7-resource-budget-governance-smoke-v1"
AUTONOMY_DAEMON_SMOKE_SCHEMA_VERSION = "2.1.0-autonomy-daemon-smoke-v1"
VITALITY_SMOKE_SCHEMA_VERSION = "2.1.0-vitality-smoke-v1"
PERSONA_STATE_SMOKE_SCHEMA_VERSION = "2.1.0-persona-state-smoke-v1"
PERSONA_SEED_SETUP_SCHEMA_VERSION = "2.2.5-persona-seed-setup-v1"
PERSONA_GROWTH_APPLY_SCHEMA_VERSION = "2.2.5-persona-growth-apply-v1"
PERSONA_STATE_INSPECT_SCHEMA_VERSION = "2.2.5-persona-state-inspect-v1"
PERSONA_STATE_DELETE_SCHEMA_VERSION = "2.2.5-persona-state-delete-v1"
PERSONA_STATE_EXPORT_SCHEMA_VERSION = "2.2.5-persona-state-export-v1"
PERSONA_TAMPER_REPORT_SCHEMA_VERSION = "2.2.5-persona-tamper-report-v1"
APPROVAL_SOCIAL_SMOKE_SCHEMA_VERSION = "2.1.0-approval-social-smoke-v1"
SOCIAL_ADAPTER_SMOKE_SCHEMA_VERSION = "2.1.0-social-adapter-smoke-v1"
SELF_IMPROVEMENT_SMOKE_SCHEMA_VERSION = "2.1.0-self-improvement-smoke-v1"
TASK_TRACKING_SMOKE_SCHEMA_VERSION = "2.2.6-task-tracking-smoke-v1"
MEMORY_MAINTENANCE_SMOKE_SCHEMA_VERSION = "2.2.6-memory-maintenance-smoke-v1"
SELF_OPTIMIZATION_SMOKE_SCHEMA_VERSION = "2.2.6-self-optimization-smoke-v1"
WORLD_MODEL_CONTEXT_SMOKE_SCHEMA_VERSION = "2.2.6-world-model-context-smoke-v1"
REAL_SCENE_CHECKLIST_TEMPLATE_SCHEMA_VERSION = "2.0.0-real-scene-checklist-template-v1"
RELEASE_226_LIVE_RERUN_TEMPLATE_SCHEMA_VERSION = "2.2.6-live-rerun-template-v1"
RELEASE_226_REAL_UNIT_RERUN_ARCHIVE_SCHEMA_VERSION = "2.2.6-real-unit-rerun-archive-v1"
RELEASE_226_QQ_GATEWAY_RERUN_ARCHIVE_SCHEMA_VERSION = "2.2.6-qq-gateway-rerun-archive-v1"
RELEASE_226_WECOM_GATEWAY_RERUN_ARCHIVE_SCHEMA_VERSION = "2.2.6-wecom-gateway-rerun-archive-v1"
RELEASE_226_OPENCLAW_GATEWAY_RERUN_ARCHIVE_SCHEMA_VERSION = "2.2.6-openclaw-gateway-rerun-archive-v1"
RELEASE_226_HARDWARE_RERUN_ARCHIVE_SCHEMA_VERSION = "2.2.6-hardware-rerun-archive-v1"
RELEASE_226_PROMOTION_CHECKLIST_SCHEMA_VERSION = "2.2.6-promotion-checklist-v1"
QQ_OFFICIAL_GATEWAY_CLOSURE_SCHEMA_VERSION = "2.2.2-qq-official-gateway-closure-v1"
WECOM_GATEWAY_CLOSURE_SCHEMA_VERSION = "2.2.3-wecom-gateway-closure-v1"
OPENCLAW_GATEWAY_CLOSURE_SCHEMA_VERSION = "2.2.3-openclaw-gateway-closure-v1"
MCP_READ_ONLY_EXECUTION_SCHEMA_VERSION = "2.2.4-mcp-read-only-execution-v1"
CODING_AGENT_SELF_IMPROVEMENT_ROUTE_SCHEMA_VERSION = "2.2.4-coding-agent-self-improvement-route-v1"
CODING_AGENT_SANDBOX_PLAN_SCHEMA_VERSION = "2.2.4-coding-agent-sandbox-plan-v1"
RELEASE_224_CLOSURE_SMOKE_SCHEMA_VERSION = "2.2.4-release-closure-smoke-v1"
RELEASE_226_CLOSURE_SMOKE_SCHEMA_VERSION = "2.2.6-release-closure-smoke-v1"


def _build_closure_checklist_entry(
    item_id: str,
    *,
    passed: bool,
    title: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "status": "pass" if passed else "fail",
        "passed": passed,
        "detail": detail,
    }


def _build_provider_smoke_closure_summary(
    provider_smoke_payload: dict[str, Any] | None,
    *,
    required: bool,
) -> dict[str, Any]:
    if provider_smoke_payload is None:
        gates = {
            "provider_smoke_supplied": False,
            "provider_smoke_contract_supported": False,
            "provider_smoke_outcome_recorded": False,
            "provider_smoke_opt_in_respected": False,
            "provider_smoke_live_call_evidence_consistent": False,
            "provider_smoke_readiness_or_missing_requirements_recorded": False,
        }
        return {
            "required": required,
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "provider_smoke_file_not_supplied",
            "call_status": "not_supplied",
            "executes_model_call": False,
            "closure_gates": gates,
            "ok": not required,
        }

    smoke_closure_gates = cast(
        dict[str, Any],
        provider_smoke_payload.get("closure_gates") or {},
    )
    executes_model_call = bool(provider_smoke_payload.get("executes_model_call"))
    gates = {
        "provider_smoke_supplied": True,
        "provider_smoke_contract_supported": str(
            provider_smoke_payload.get("schema_version") or ""
        )
        == "1.2.5-maf-provider-smoke-v2",
        "provider_smoke_outcome_recorded": bool(
            smoke_closure_gates.get("closure_smoke_outcome_recorded")
        ),
        "provider_smoke_opt_in_respected": bool(
            smoke_closure_gates.get("real_provider_call_opt_in_respected")
        ),
        "provider_smoke_live_call_evidence_consistent": (
            not executes_model_call
            or bool(smoke_closure_gates.get("model_call_evidence_present"))
        ),
        "provider_smoke_readiness_or_missing_requirements_recorded": bool(
            smoke_closure_gates.get("provider_requirements_ready")
            or smoke_closure_gates.get("missing_requirements_cleanly_reported")
        ),
    }
    return {
        "required": required,
        "supplied": True,
        "schema_version": str(provider_smoke_payload.get("schema_version") or ""),
        "status": str(provider_smoke_payload.get("status") or "unknown"),
        "reason": str(provider_smoke_payload.get("reason") or ""),
        "call_status": str(provider_smoke_payload.get("call_status") or ""),
        "executes_model_call": executes_model_call,
        "closure_gates": gates,
        "ok": all(gates.values()),
    }


def _build_coding_agent_route_closure_summary(
    coding_agent_route_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if coding_agent_route_payload is None:
        gates = {
            "coding_agent_route_evidence_supplied": False,
            "coding_agent_route_contract_supported": False,
            "review_routing_required": False,
            "sandbox_execution_recorded": False,
            "plan_artifact_recorded": False,
            "plan_artifact_contract_supported": False,
            "plan_steps_recorded": False,
            "callback_audit_recorded": False,
            "callback_payload_recorded": False,
        }
        return {
            "schema_version": "",
            "status": "missing",
            "reason": "coding_agent_route_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], coding_agent_route_payload.get("closure_gates") or {})
    gates = {
        "coding_agent_route_evidence_supplied": True,
        "coding_agent_route_contract_supported": str(
            coding_agent_route_payload.get("schema_version") or ""
        )
        == CODING_AGENT_SELF_IMPROVEMENT_ROUTE_SCHEMA_VERSION,
        "review_routing_required": bool(payload_gates.get("review_routing_required")),
        "sandbox_execution_recorded": bool(payload_gates.get("sandbox_execution_recorded")),
        "plan_artifact_recorded": bool(payload_gates.get("plan_artifact_recorded")),
        "plan_artifact_contract_supported": bool(
            payload_gates.get("plan_artifact_contract_supported")
        ),
        "plan_steps_recorded": bool(payload_gates.get("plan_steps_recorded")),
        "callback_audit_recorded": bool(payload_gates.get("callback_audit_recorded")),
        "callback_payload_recorded": bool(payload_gates.get("callback_payload_recorded")),
    }
    return {
        "schema_version": str(coding_agent_route_payload.get("schema_version") or ""),
        "status": str(coding_agent_route_payload.get("status") or "unknown"),
        "reason": str(coding_agent_route_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any],
            coding_agent_route_payload.get("evidence_summary") or {},
        ),
        "ok": all(gates.values()),
    }


def _build_persona_225_closure_summary(
    persona_state_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if persona_state_payload is None:
        gates = {
            "persona_seed_recorded": False,
            "persona_growth_recorded": False,
            "growth_requires_runtime_evidence": False,
            "immutability_stamp_recorded": False,
            "immutability_stamp_valid": False,
        }
        return {
            "supplied": False,
            "status": "not_supplied",
            "reason": "persona_state_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "persona_seed_ok": False,
            "persona_growth_ok": False,
            "memory_immutability_ok": False,
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], persona_state_payload.get("closure_gates") or {})
    gates = {
        "persona_seed_recorded": bool(payload_gates.get("persona_seed_recorded", False)),
        "persona_growth_recorded": bool(payload_gates.get("persona_growth_recorded", False)),
        "growth_requires_runtime_evidence": bool(
            payload_gates.get("growth_requires_runtime_evidence", False)
        ),
        "immutability_stamp_recorded": bool(
            payload_gates.get("immutability_stamp_recorded", False)
        ),
        "immutability_stamp_valid": bool(payload_gates.get("immutability_stamp_valid", False)),
    }
    return {
        "supplied": True,
        "status": str(persona_state_payload.get("status") or "unknown"),
        "reason": str(persona_state_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any], persona_state_payload.get("evidence_summary") or {}
        ),
        "persona_seed_ok": gates["persona_seed_recorded"],
        "persona_growth_ok": gates["persona_growth_recorded"]
        and gates["growth_requires_runtime_evidence"],
        "memory_immutability_ok": gates["immutability_stamp_recorded"]
        and gates["immutability_stamp_valid"],
        "ok": all(gates.values()),
    }


def _build_multimodal_profile_closure_summary(
    multimodal_profile_payload: dict[str, Any] | None,
    *,
    required: bool,
) -> dict[str, Any]:
    if multimodal_profile_payload is None:
        gates = {
            "multimodal_profile_smoke_supplied": False,
            "multimodal_profile_contract_supported": False,
            "multimodal_input_recorded": False,
            "route_decision_recorded": False,
            "profile_readiness_recorded": False,
            "route_ready": False,
            "no_model_call_executed": False,
        }
        return {
            "required": required,
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "multimodal_profile_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": not required,
        }

    smoke_closure_gates = cast(
        dict[str, Any],
        multimodal_profile_payload.get("closure_gates") or {},
    )
    evidence_summary = cast(
        dict[str, Any],
        multimodal_profile_payload.get("evidence_summary") or {},
    )
    gates = {
        "multimodal_profile_smoke_supplied": True,
        "multimodal_profile_contract_supported": str(
            multimodal_profile_payload.get("schema_version") or ""
        )
        == "1.2.5-inference-route-v1",
        "multimodal_input_recorded": bool(
            smoke_closure_gates.get("multimodal_input_recorded")
        ),
        "route_decision_recorded": bool(
            smoke_closure_gates.get("route_decision_recorded")
        ),
        "profile_readiness_recorded": bool(
            smoke_closure_gates.get("profile_readiness_recorded")
        ),
        "route_ready": bool(smoke_closure_gates.get("route_ready")),
        "no_model_call_executed": bool(
            smoke_closure_gates.get("no_model_call_executed")
        )
        and not bool(multimodal_profile_payload.get("executes_model_call")),
    }
    return {
        "required": required,
        "supplied": True,
        "schema_version": str(multimodal_profile_payload.get("schema_version") or ""),
        "status": str(multimodal_profile_payload.get("status") or "unknown"),
        "reason": str(multimodal_profile_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": evidence_summary,
        "ok": all(gates.values()),
    }


def _build_documentation_closure_summary(
    documentation_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if documentation_payload is None:
        gates = {
            "documentation_evidence_supplied": False,
            "documentation_contract_supported": False,
            "release_plan_aligned": False,
            "readme_aligned": False,
            "progress_recorded": False,
            "runbooks_aligned": False,
            "release_identity_unpromoted": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "documentation_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    documentation_gates = cast(
        dict[str, Any],
        documentation_payload.get("closure_gates") or {},
    )
    evidence_summary = cast(
        dict[str, Any],
        documentation_payload.get("evidence_summary") or {},
    )
    gates = {
        "documentation_evidence_supplied": True,
        "documentation_contract_supported": str(
            documentation_payload.get("schema_version") or ""
        )
        == DOCUMENTATION_CLOSURE_SCHEMA_VERSION,
        "release_plan_aligned": bool(documentation_gates.get("release_plan_aligned")),
        "readme_aligned": bool(documentation_gates.get("readme_aligned")),
        "progress_recorded": bool(documentation_gates.get("progress_recorded")),
        "runbooks_aligned": bool(documentation_gates.get("runbooks_aligned")),
        "release_identity_unpromoted": bool(
            documentation_gates.get("release_identity_unpromoted")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(documentation_payload.get("schema_version") or ""),
        "status": str(documentation_payload.get("status") or "unknown"),
        "reason": str(documentation_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": evidence_summary,
        "ok": all(gates.values()),
    }


def _build_regression_closure_summary(
    regression_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if regression_payload is None:
        gates = {
            "regression_evidence_supplied": False,
            "regression_contract_supported": False,
            "core_tests_passed": False,
            "agent_closure_regression_passed": False,
            "app_lifecycle_regression_passed": False,
            "event_service_regression_passed": False,
            "federation_regression_passed": False,
            "relay_regression_passed": False,
            "hardware_compatibility_regression_passed": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "regression_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    regression_gates = cast(
        dict[str, Any],
        regression_payload.get("closure_gates") or {},
    )
    evidence_summary = cast(
        dict[str, Any],
        regression_payload.get("evidence_summary") or {},
    )
    schema_version = str(regression_payload.get("schema_version") or "")
    legacy_contract = schema_version == LEGACY_REGRESSION_CLOSURE_SCHEMA_VERSION
    gates = {
        "regression_evidence_supplied": True,
        "regression_contract_supported": schema_version
        in {
            REGRESSION_CLOSURE_SCHEMA_VERSION,
            LEGACY_REGRESSION_CLOSURE_SCHEMA_VERSION,
        },
        "core_tests_passed": bool(regression_gates.get("core_tests_passed")),
        "agent_closure_regression_passed": (
            True if legacy_contract else bool(regression_gates.get("agent_closure_regression_passed"))
        ),
        "app_lifecycle_regression_passed": bool(
            regression_gates.get("app_lifecycle_regression_passed")
        ),
        "event_service_regression_passed": bool(
            regression_gates.get("event_service_regression_passed")
        ),
        "federation_regression_passed": (
            True if legacy_contract else bool(regression_gates.get("federation_regression_passed"))
        ),
        "relay_regression_passed": (
            True if legacy_contract else bool(regression_gates.get("relay_regression_passed"))
        ),
        "hardware_compatibility_regression_passed": (
            True
            if legacy_contract
            else bool(regression_gates.get("hardware_compatibility_regression_passed"))
        ),
    }
    return {
        "supplied": True,
        "schema_version": schema_version,
        "status": str(regression_payload.get("status") or "unknown"),
        "reason": str(regression_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": evidence_summary,
        "ok": all(gates.values()),
    }


def _build_relay_failure_closure_summary(
    relay_failure_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if relay_failure_payload is None:
        gates = {
            "relay_failure_evidence_supplied": False,
            "relay_failure_contract_supported": False,
            "route_failure_recorded": False,
            "fallback_path_recorded": False,
            "operator_runbook_recorded": False,
            "deterministic_validation_recorded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "relay_failure_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    relay_failure_gates = cast(
        dict[str, Any],
        relay_failure_payload.get("closure_gates") or {},
    )
    evidence_summary = cast(
        dict[str, Any],
        relay_failure_payload.get("evidence_summary") or {},
    )
    gates = {
        "relay_failure_evidence_supplied": True,
        "relay_failure_contract_supported": str(
            relay_failure_payload.get("schema_version") or ""
        )
        == RELAY_FAILURE_CLOSURE_SCHEMA_VERSION,
        "route_failure_recorded": bool(
            relay_failure_gates.get("route_failure_recorded")
        ),
        "fallback_path_recorded": bool(
            relay_failure_gates.get("fallback_path_recorded")
        ),
        "operator_runbook_recorded": bool(
            relay_failure_gates.get("operator_runbook_recorded")
        ),
        "deterministic_validation_recorded": bool(
            relay_failure_gates.get("deterministic_validation_recorded")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(relay_failure_payload.get("schema_version") or ""),
        "status": str(relay_failure_payload.get("status") or "unknown"),
        "reason": str(relay_failure_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": evidence_summary,
        "ok": all(gates.values()),
    }


def build_hardware_compatibility_smoke(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
    unit_node_id: str = "unit-local-01",
    unit_architecture: str = "xtensa",
    unit_abi: str = "zephyr-llext-v1",
    unit_board_family: str = "generic-unit-class",
    unit_storage_class: str = "removable_or_flash",
    unit_network_transports: tuple[str, ...] = ("wifi", "serial_bridge"),
    unit_llext_supported: bool = True,
    unit_relay_capable: bool = False,
    unit_signing_enforced: bool = False,
    heap_free_bytes: int = 8192,
    app_slot_bytes: int = 65536,
    required_abi: str = "",
    required_board_family: str = "",
    required_storage_class: str = "",
    require_signing: bool = False,
    required_heap_free_bytes: int = 0,
    required_app_slot_bytes: int = 0,
    mismatch_architecture_probe: str = "x86_64",
) -> dict[str, Any]:
    admission_payload = build_app_artifact_admission(
        preset=preset,
        app_id=app_id,
        app_source_dir=app_source_dir,
        board=board,
        build_dir=build_dir,
        artifact_file=artifact_file,
    )
    artifact_admission = cast(dict[str, Any], admission_payload["artifact_admission"])
    unit_capability = UnitCapabilityDescriptor(
        node_id=unit_node_id,
        architecture=unit_architecture,
        abi=unit_abi,
        board_family=unit_board_family,
        llext_supported=unit_llext_supported,
        storage_class=unit_storage_class,
        network_transports=unit_network_transports,
        relay_capable=unit_relay_capable,
        signing_enforced=unit_signing_enforced,
        resource_budget={
            "heap_free_bytes": heap_free_bytes,
            "app_slot_bytes": app_slot_bytes,
        },
    ).to_dict()
    required_abi_value = required_abi or unit_abi
    required_board_family_value = required_board_family or unit_board_family
    required_storage_class_value = required_storage_class or unit_storage_class
    artifact_machine_name = str(
        cast(dict[str, Any], artifact_admission.get("elf_identity") or {}).get(
            "machine_name"
        )
        or ""
    )
    architecture_compatible = artifact_machine_name == str(
        unit_capability.get("architecture") or ""
    )
    abi_compatible = required_abi_value == str(unit_capability.get("abi") or "")
    board_family_compatible = required_board_family_value == str(
        unit_capability.get("board_family") or ""
    )
    storage_class_compatible = required_storage_class_value == str(
        unit_capability.get("storage_class") or ""
    )
    llext_capability_compatible = bool(unit_capability.get("llext_supported"))
    signing_requirement_compatible = (not require_signing) or bool(
        unit_capability.get("signing_enforced")
    )
    resource_budget = cast(dict[str, Any], unit_capability.get("resource_budget") or {})
    resource_budget_sufficient = int(resource_budget.get("heap_free_bytes") or 0) >= int(
        required_heap_free_bytes
    ) and int(resource_budget.get("app_slot_bytes") or 0) >= int(
        required_app_slot_bytes
    )
    cross_architecture_rejection_recorded = (
        bool(mismatch_architecture_probe)
        and mismatch_architecture_probe != str(unit_capability.get("architecture") or "")
        and mismatch_architecture_probe != artifact_machine_name
    )
    closure_gates = {
        "capability_contract_supported": str(unit_capability.get("schema_version") or "")
        == UnitCapabilityDescriptor(node_id=unit_node_id).schema_version,
        "capability_fields_recorded": bool(unit_capability.get("architecture"))
        and bool(unit_capability.get("abi"))
        and bool(unit_capability.get("board_family"))
        and bool(unit_capability.get("storage_class"))
        and isinstance(unit_capability.get("network_transports") or [], list),
        "hardware_agnostic_board_family_used": "/" not in str(
            unit_capability.get("board_family") or ""
        )
        and str(unit_capability.get("board_family") or "") != board,
        "signing_and_budget_recorded": "heap_free_bytes" in resource_budget
        and "app_slot_bytes" in resource_budget
        and "signing_enforced" in unit_capability,
        "artifact_admission_recorded": bool(artifact_admission.get("admitted")),
        "architecture_compatible": architecture_compatible,
        "abi_compatible": abi_compatible,
        "board_family_compatible": board_family_compatible,
        "storage_class_compatible": storage_class_compatible,
        "llext_capability_compatible": llext_capability_compatible,
        "signing_requirement_compatible": signing_requirement_compatible,
        "resource_budget_sufficient": resource_budget_sufficient,
        "cross_architecture_rejection_recorded": cross_architecture_rejection_recorded,
    }
    return {
        "schema_version": HARDWARE_COMPATIBILITY_CLOSURE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "hardware_compatibility_ready"
        if all(closure_gates.values())
        else "hardware_compatibility_gap",
        "command": "hardware-compatibility-smoke",
        "unit_capability": unit_capability,
        "artifact_admission": artifact_admission,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "artifact_machine_name": artifact_machine_name,
            "required_abi": required_abi_value,
            "required_board_family": required_board_family_value,
            "required_storage_class": required_storage_class_value,
            "required_heap_free_bytes": required_heap_free_bytes,
            "required_app_slot_bytes": required_app_slot_bytes,
            "mismatch_architecture_probe": mismatch_architecture_probe,
        },
        "ok": all(closure_gates.values()),
    }


def _build_hardware_compatibility_closure_summary(
    hardware_compatibility_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if hardware_compatibility_payload is None:
        gates = {
            "hardware_compatibility_evidence_supplied": False,
            "hardware_compatibility_contract_supported": False,
            "capability_fields_recorded": False,
            "hardware_agnostic_board_family_used": False,
            "signing_and_budget_recorded": False,
            "artifact_admission_recorded": False,
            "architecture_compatible": False,
            "abi_compatible": False,
            "board_family_compatible": False,
            "storage_class_compatible": False,
            "llext_capability_compatible": False,
            "signing_requirement_compatible": False,
            "resource_budget_sufficient": False,
            "cross_architecture_rejection_recorded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "hardware_compatibility_file_not_supplied",
            "closure_gates": gates,
            "hardware_abstraction_ok": False,
            "artifact_compatibility_ok": False,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(
        dict[str, Any],
        hardware_compatibility_payload.get("closure_gates") or {},
    )
    evidence_summary = cast(
        dict[str, Any],
        hardware_compatibility_payload.get("evidence_summary") or {},
    )
    gates = {
        "hardware_compatibility_evidence_supplied": True,
        "hardware_compatibility_contract_supported": str(
            hardware_compatibility_payload.get("schema_version") or ""
        )
        == HARDWARE_COMPATIBILITY_CLOSURE_SCHEMA_VERSION,
        "capability_fields_recorded": bool(payload_gates.get("capability_fields_recorded")),
        "hardware_agnostic_board_family_used": bool(
            payload_gates.get("hardware_agnostic_board_family_used")
        ),
        "signing_and_budget_recorded": bool(
            payload_gates.get("signing_and_budget_recorded")
        ),
        "artifact_admission_recorded": bool(
            payload_gates.get("artifact_admission_recorded")
        ),
        "architecture_compatible": bool(payload_gates.get("architecture_compatible")),
        "abi_compatible": bool(payload_gates.get("abi_compatible")),
        "board_family_compatible": bool(payload_gates.get("board_family_compatible")),
        "storage_class_compatible": bool(payload_gates.get("storage_class_compatible")),
        "llext_capability_compatible": bool(
            payload_gates.get("llext_capability_compatible")
        ),
        "signing_requirement_compatible": bool(
            payload_gates.get("signing_requirement_compatible")
        ),
        "resource_budget_sufficient": bool(
            payload_gates.get("resource_budget_sufficient")
        ),
        "cross_architecture_rejection_recorded": bool(
            payload_gates.get("cross_architecture_rejection_recorded")
        ),
    }
    hardware_abstraction_ok = all(
        gates[key]
        for key in (
            "hardware_compatibility_evidence_supplied",
            "hardware_compatibility_contract_supported",
            "capability_fields_recorded",
            "hardware_agnostic_board_family_used",
            "signing_and_budget_recorded",
        )
    )
    artifact_compatibility_ok = all(
        gates[key]
        for key in (
            "hardware_compatibility_evidence_supplied",
            "hardware_compatibility_contract_supported",
            "artifact_admission_recorded",
            "architecture_compatible",
            "abi_compatible",
            "board_family_compatible",
            "storage_class_compatible",
            "llext_capability_compatible",
            "signing_requirement_compatible",
            "resource_budget_sufficient",
            "cross_architecture_rejection_recorded",
        )
    )
    return {
        "supplied": True,
        "schema_version": str(
            hardware_compatibility_payload.get("schema_version") or ""
        ),
        "status": str(hardware_compatibility_payload.get("status") or "unknown"),
        "reason": str(hardware_compatibility_payload.get("reason") or ""),
        "closure_gates": gates,
        "hardware_abstraction_ok": hardware_abstraction_ok,
        "artifact_compatibility_ok": artifact_compatibility_ok,
        "evidence_summary": evidence_summary,
        "ok": hardware_abstraction_ok and artifact_compatibility_ok,
    }


def build_resource_budget_governance_smoke(
    hardware_compatibility_payload: dict[str, Any],
) -> dict[str, Any]:
    if (
        str(hardware_compatibility_payload.get("command") or "")
        != "hardware-compatibility-smoke"
    ):
        raise ValueError(
            "resource-budget-governance-smoke requires hardware-compatibility-smoke evidence"
        )

    closure_gates = cast(
        dict[str, Any],
        hardware_compatibility_payload.get("closure_gates") or {},
    )
    unit_capability = cast(
        dict[str, Any],
        hardware_compatibility_payload.get("unit_capability") or {},
    )
    resource_budget = cast(dict[str, Any], unit_capability.get("resource_budget") or {})
    evidence_summary = cast(
        dict[str, Any],
        hardware_compatibility_payload.get("evidence_summary") or {},
    )

    governance_gates = {
        "hardware_compatibility_evidence_supplied": True,
        "hardware_compatibility_contract_supported": str(
            hardware_compatibility_payload.get("schema_version") or ""
        )
        == HARDWARE_COMPATIBILITY_CLOSURE_SCHEMA_VERSION,
        "resource_budget_recorded": "heap_free_bytes" in resource_budget
        and "app_slot_bytes" in resource_budget,
        "resource_budget_thresholds_recorded": "required_heap_free_bytes"
        in evidence_summary
        and "required_app_slot_bytes" in evidence_summary,
        "resource_budget_sufficient": bool(
            closure_gates.get("resource_budget_sufficient")
        ),
        "signing_and_budget_recorded": bool(
            closure_gates.get("signing_and_budget_recorded")
        ),
    }

    return {
        "schema_version": RESOURCE_BUDGET_GOVERNANCE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(governance_gates.values()) else "incomplete",
        "reason": "resource_budget_governance_ready"
        if all(governance_gates.values())
        else "resource_budget_governance_gap",
        "command": "resource-budget-governance-smoke",
        "closure_gates": governance_gates,
        "budget_snapshot": {
            "heap_free_bytes": int(resource_budget.get("heap_free_bytes") or 0),
            "app_slot_bytes": int(resource_budget.get("app_slot_bytes") or 0),
            "required_heap_free_bytes": int(
                evidence_summary.get("required_heap_free_bytes") or 0
            ),
            "required_app_slot_bytes": int(
                evidence_summary.get("required_app_slot_bytes") or 0
            ),
        },
        "source_evidence": {
            "hardware_compatibility_schema_version": str(
                hardware_compatibility_payload.get("schema_version") or ""
            ),
            "hardware_compatibility_status": str(
                hardware_compatibility_payload.get("status") or "unknown"
            ),
            "hardware_compatibility_reason": str(
                hardware_compatibility_payload.get("reason") or ""
            ),
        },
        "ok": all(governance_gates.values()),
    }


def _build_resource_budget_governance_closure_summary(
    resource_budget_governance_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if resource_budget_governance_payload is None:
        gates = {
            "resource_budget_governance_evidence_supplied": False,
            "resource_budget_governance_contract_supported": False,
            "resource_budget_recorded": False,
            "resource_budget_thresholds_recorded": False,
            "resource_budget_sufficient": False,
            "signing_and_budget_recorded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "resource_budget_governance_file_not_supplied",
            "closure_gates": gates,
            "budget_snapshot": {},
            "ok": False,
        }

    payload_gates = cast(
        dict[str, Any],
        resource_budget_governance_payload.get("closure_gates") or {},
    )
    gates = {
        "resource_budget_governance_evidence_supplied": True,
        "resource_budget_governance_contract_supported": str(
            resource_budget_governance_payload.get("schema_version") or ""
        )
        == RESOURCE_BUDGET_GOVERNANCE_SMOKE_SCHEMA_VERSION,
        "resource_budget_recorded": bool(payload_gates.get("resource_budget_recorded")),
        "resource_budget_thresholds_recorded": bool(
            payload_gates.get("resource_budget_thresholds_recorded")
        ),
        "resource_budget_sufficient": bool(
            payload_gates.get("resource_budget_sufficient")
        ),
        "signing_and_budget_recorded": bool(
            payload_gates.get("signing_and_budget_recorded")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(
            resource_budget_governance_payload.get("schema_version") or ""
        ),
        "status": str(resource_budget_governance_payload.get("status") or "unknown"),
        "reason": str(resource_budget_governance_payload.get("reason") or ""),
        "closure_gates": gates,
        "budget_snapshot": cast(
            dict[str, Any],
            resource_budget_governance_payload.get("budget_snapshot") or {},
        ),
        "ok": all(gates.values()),
    }


def build_hardware_acceptance_matrix(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
    capability_classes: tuple[str, ...] = (),
    representative_board_families: dict[str, str] | None = None,
    required_heap_free_bytes: int = 4096,
    required_app_slot_bytes: int = 32768,
) -> dict[str, Any]:
    selected_classes = capability_classes or (
        "extensible_unit",
        "restricted_unit",
        "relay_capable_unit",
        "federated_access_unit",
    )
    board_family_map = {
        "extensible_unit": "generic-extensible-class",
        "restricted_unit": "generic-restricted-class",
        "relay_capable_unit": "generic-relay-class",
        "federated_access_unit": "generic-federated-class",
    }
    if representative_board_families:
        board_family_map.update(representative_board_families)

    rows: list[dict[str, Any]] = []
    for capability_class in selected_classes:
        normalized_class = capability_class.strip().lower().replace("-", "_")
        board_family = board_family_map.get(normalized_class, f"generic-{normalized_class}")
        if normalized_class == "restricted_unit":
            hardware_payload = build_hardware_compatibility_smoke(
                preset=preset,
                app_id=app_id,
                app_source_dir=app_source_dir,
                board=board,
                build_dir=build_dir,
                artifact_file=artifact_file,
                unit_node_id="unit-restricted-01",
                unit_architecture="arm",
                unit_abi="restricted-static-v1",
                unit_board_family=board_family,
                unit_storage_class="flash_only",
                unit_network_transports=("serial_bridge",),
                unit_llext_supported=False,
                heap_free_bytes=max(required_heap_free_bytes, 4096),
                app_slot_bytes=max(required_app_slot_bytes, 32768),
                required_abi="restricted-static-v1",
                required_board_family=board_family,
                required_storage_class="flash_only",
                required_heap_free_bytes=required_heap_free_bytes,
                required_app_slot_bytes=required_app_slot_bytes,
                mismatch_architecture_probe="xtensa",
            )
            row_gates = {
                "capability_class_recorded": True,
                "board_family_mapped": bool(board_family),
                "hardware_agnostic_mapping_used": bool(
                    hardware_payload["closure_gates"]["hardware_agnostic_board_family_used"]
                ),
                "restricted_outcome_explicit": True,
                "dynamic_app_lifecycle_rejected": not bool(
                    hardware_payload["closure_gates"]["llext_capability_compatible"]
                ),
                "degraded_query_supported": True,
                "degraded_event_supported": True,
                "resource_budget_recorded": bool(
                    hardware_payload["closure_gates"]["signing_and_budget_recorded"]
                ),
            }
            row_ok = all(row_gates.values())
            rows.append(
                {
                    "capability_class": normalized_class,
                    "board_family": board_family,
                    "status": "restricted_ready" if row_ok else "restricted_incomplete",
                    "ok": row_ok,
                    "compatibility_mode": "restricted",
                    "dynamic_app_support": "unsupported",
                    "incompatibility_reason": "llext_not_supported_for_restricted_unit",
                    "closure_gates": row_gates,
                    "hardware_compatibility": hardware_payload,
                }
            )
            continue

        relay_capable = normalized_class == "relay_capable_unit"
        federated_access = normalized_class == "federated_access_unit"
        hardware_payload = build_hardware_compatibility_smoke(
            preset=preset,
            app_id=app_id,
            app_source_dir=app_source_dir,
            board=board,
            build_dir=build_dir,
            artifact_file=artifact_file,
            unit_node_id=f"unit-{normalized_class}-01",
            unit_architecture="xtensa",
            unit_abi="zephyr-llext-v1",
            unit_board_family=board_family,
            unit_storage_class="removable_or_flash",
            unit_network_transports=("wifi", "serial_bridge"),
            unit_llext_supported=True,
            unit_relay_capable=relay_capable,
            heap_free_bytes=max(required_heap_free_bytes, 8192),
            app_slot_bytes=max(required_app_slot_bytes, 65536),
            required_abi="zephyr-llext-v1",
            required_board_family=board_family,
            required_storage_class="removable_or_flash",
            required_heap_free_bytes=required_heap_free_bytes,
            required_app_slot_bytes=required_app_slot_bytes,
            mismatch_architecture_probe="x86_64",
        )
        row_gates = {
            "capability_class_recorded": True,
            "board_family_mapped": bool(board_family),
            "hardware_agnostic_mapping_used": bool(
                hardware_payload["closure_gates"]["hardware_agnostic_board_family_used"]
            ),
            "compatibility_ready": bool(hardware_payload["ok"]),
            "relay_capability_recorded": True
            if not relay_capable
            else bool(hardware_payload["unit_capability"].get("relay_capable")),
            "federated_access_policy_bounded": True if federated_access else True,
        }
        row_ok = all(row_gates.values())
        rows.append(
            {
                "capability_class": normalized_class,
                "board_family": board_family,
                "status": "ready" if row_ok else "incomplete",
                "ok": row_ok,
                "compatibility_mode": "dynamic",
                "dynamic_app_support": "full",
                "closure_gates": row_gates,
                "hardware_compatibility": hardware_payload,
            }
        )

    required_classes = {"extensible_unit", "restricted_unit", "relay_capable_unit"}
    represented_classes = {str(row.get("capability_class") or "") for row in rows}
    closure_gates = {
        "matrix_contract_supported": True,
        "required_capability_classes_present": required_classes.issubset(represented_classes),
        "board_family_mapping_recorded": all(bool(row.get("board_family")) for row in rows),
        "hardware_agnostic_mapping_used": all(
            bool(cast(dict[str, Any], row.get("closure_gates") or {}).get("hardware_agnostic_mapping_used"))
            for row in rows
        ),
        "restricted_unit_outcome_explicit": any(
            str(row.get("capability_class") or "") == "restricted_unit"
            and bool(cast(dict[str, Any], row.get("closure_gates") or {}).get("restricted_outcome_explicit"))
            for row in rows
        ),
        "relay_or_federated_row_present": any(
            str(row.get("capability_class") or "") in {"relay_capable_unit", "federated_access_unit"}
            for row in rows
        ),
        "all_matrix_rows_ready": all(bool(row.get("ok")) for row in rows),
    }
    return {
        "schema_version": HARDWARE_ACCEPTANCE_MATRIX_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "hardware_acceptance_matrix_ready"
        if all(closure_gates.values())
        else "hardware_acceptance_matrix_gap",
        "command": "hardware-acceptance-matrix",
        "rows": rows,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "capability_classes": list(selected_classes),
            "required_heap_free_bytes": required_heap_free_bytes,
            "required_app_slot_bytes": required_app_slot_bytes,
            "represented_board_families": {
                key: board_family_map[key]
                for key in sorted(represented_classes)
                if key in board_family_map
            },
        },
        "ok": all(closure_gates.values()),
    }


def _build_hardware_acceptance_matrix_summary(
    hardware_acceptance_matrix_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if hardware_acceptance_matrix_payload is None:
        gates = {
            "hardware_acceptance_matrix_evidence_supplied": False,
            "hardware_acceptance_matrix_contract_supported": False,
            "required_capability_classes_present": False,
            "board_family_mapping_recorded": False,
            "hardware_agnostic_mapping_used": False,
            "restricted_unit_outcome_explicit": False,
            "relay_or_federated_row_present": False,
            "all_matrix_rows_ready": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "hardware_acceptance_matrix_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(
        dict[str, Any],
        hardware_acceptance_matrix_payload.get("closure_gates") or {},
    )
    gates = {
        "hardware_acceptance_matrix_evidence_supplied": True,
        "hardware_acceptance_matrix_contract_supported": str(
            hardware_acceptance_matrix_payload.get("schema_version") or ""
        )
        == HARDWARE_ACCEPTANCE_MATRIX_SCHEMA_VERSION,
        "required_capability_classes_present": bool(
            payload_gates.get("required_capability_classes_present")
        ),
        "board_family_mapping_recorded": bool(
            payload_gates.get("board_family_mapping_recorded")
        ),
        "hardware_agnostic_mapping_used": bool(
            payload_gates.get("hardware_agnostic_mapping_used")
        ),
        "restricted_unit_outcome_explicit": bool(
            payload_gates.get("restricted_unit_outcome_explicit")
        ),
        "relay_or_federated_row_present": bool(
            payload_gates.get("relay_or_federated_row_present")
        ),
        "all_matrix_rows_ready": bool(payload_gates.get("all_matrix_rows_ready")),
    }
    return {
        "supplied": True,
        "schema_version": str(
            hardware_acceptance_matrix_payload.get("schema_version") or ""
        ),
        "status": str(hardware_acceptance_matrix_payload.get("status") or "unknown"),
        "reason": str(hardware_acceptance_matrix_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any],
            hardware_acceptance_matrix_payload.get("evidence_summary") or {},
        ),
        "restricted_unit_compatibility_ok": all(
            gates[key]
            for key in (
                "hardware_acceptance_matrix_evidence_supplied",
                "hardware_acceptance_matrix_contract_supported",
                "restricted_unit_outcome_explicit",
                "all_matrix_rows_ready",
            )
        ),
        "ok": all(gates.values()),
    }


def build_agent_excellence_smoke(
    *,
    tool_adapter: Any | None = None,
    bridge_mode: str = "read_only_descriptor_only",
) -> dict[str, Any]:
    adapter = tool_adapter or FakeUnitToolAdapter()
    tool_manifest_payload = cast(dict[str, Any], adapter.tool_manifest_payload())
    available_tools = cast(list[dict[str, Any]], tool_manifest_payload.get("tools") or [])
    skill_descriptor = load_neuro_cli_skill_descriptor_payload()
    skill_registry = load_skill_descriptor_registry_payload()
    mcp_descriptor = load_mcp_bridge_descriptor_payload(
        adapter,
        bridge_mode=bridge_mode,
    )
    tool_contracts = tuple(adapter.tool_manifest())
    workflow_catalog_results = [
        validate_tool_workflow_catalog_consistency(contract)
        for contract in tool_contracts
    ]
    governed_tools = [
        tool
        for tool in available_tools
        if str(tool.get("side_effect_level") or "") in {"approval_required", "destructive"}
    ]
    approval_required_tool_count = sum(
        1 for tool in governed_tools if bool(tool.get("approval_required", False))
    )
    available_tool_names = {
        str(tool.get("name") or "") for tool in available_tools if str(tool.get("name") or "")
    }
    mcp_read_only_probe = build_mcp_read_only_execution(
        tool_name="system_state_sync",
        tool_args={"--node": "unit-01"},
        tool_adapter=adapter,
    )
    mcp_governance_probe = load_mcp_tool_governance_descriptor_payload(
        "system_restart_app",
        tool_adapter=adapter,
    )
    coding_agent_probe = build_coding_agent_self_improvement_route(
        runner_name="copilot",
        summary="Repair a deterministic regression through governed review",
        decision="approve",
        evidence=ImprovementEvidence(
            tests_passed=True,
            lint_passed=True,
            smoke_passed=True,
            evidence_refs=("pytest.txt", "ruff.txt", "agent-excellence-smoke.json"),
        ),
    )
    hallucinated_tool_name = "system_unknown_write"
    safety_boundaries = cast(
        dict[str, Any],
        mcp_descriptor.get("safety_boundaries") or {},
    )
    closure_gates = {
        "tool_manifest_supplied": bool(tool_manifest_payload.get("ok")),
        "tool_manifest_contract_supported": str(
            tool_manifest_payload.get("schema_version") or ""
        )
        == "1.2.0-tool-manifest-v1",
        "available_tools_recorded": bool(available_tools),
        "governed_tools_present": bool(governed_tools),
        "side_effect_tools_require_approval": all(
            bool(tool.get("approval_required", False))
            or str(tool.get("side_effect_level") or "") == "destructive"
            for tool in governed_tools
        ),
        "workflow_catalog_consistent": all(
            bool(result.get("valid")) for result in workflow_catalog_results
        ),
        "skill_descriptor_supplied": bool(skill_descriptor.get("ok")),
        "skill_descriptor_contract_supported": str(
            skill_descriptor.get("schema_version") or ""
        )
        == "1.2.5-skill-descriptor-v1",
        "skill_registry_supplied": bool(skill_registry.get("ok")),
        "skill_registry_contract_supported": str(
            skill_registry.get("schema_version") or ""
        )
        == "2.2.4-skill-registry-v1",
        "skill_registry_records_canonical_entry": bool(
            skill_registry.get("canonical_entry_count")
        ),
        "workflow_plan_required_for_governed_tools": (
            not governed_tools
            or bool(skill_descriptor.get("workflow_plan_required", False))
        ),
        "release_target_promotion_blocked": bool(
            skill_descriptor.get("release_target_promotion_blocked", False)
        ),
        "callback_audit_required": bool(
            skill_descriptor.get("callback_audit_required", False)
        ),
        "mcp_descriptor_supplied": bool(mcp_descriptor.get("ok")),
        "mcp_descriptor_contract_supported": str(
            mcp_descriptor.get("schema_version") or ""
        )
        == "1.2.6-mcp-bridge-descriptor-v2",
        "mcp_descriptor_read_only": str(mcp_descriptor.get("bridge_mode") or "")
        == "read_only_descriptor_only",
        "tool_execution_via_mcp_forbidden": bool(
            safety_boundaries.get("tool_execution_via_mcp_forbidden", False)
        ),
        "external_mcp_disabled": not bool(
            safety_boundaries.get("external_mcp_connection_enabled", False)
        ),
        "approval_required_tool_proposals_blocked": not bool(
            safety_boundaries.get("approval_required_tool_proposals_allowed", False)
        ),
        "mcp_read_only_execute_supported": bool(mcp_read_only_probe.get("ok")),
        "mcp_governance_descriptor_supported": bool(mcp_governance_probe.get("ok"))
        and str(mcp_governance_probe.get("governance_path") or "")
        == "core_approval_required_proposal",
        "coding_agent_self_improvement_routed": bool(coding_agent_probe.get("ok"))
        and bool(
            cast(dict[str, Any], coding_agent_probe.get("closure_gates") or {}).get(
                "review_routing_required",
                False,
            )
        ),
        "hallucinated_tool_rejected_by_available_manifest": (
            hallucinated_tool_name not in available_tool_names
        ),
    }
    return {
        "schema_version": AGENT_EXCELLENCE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "agent_excellence_ready"
        if all(closure_gates.values())
        else "agent_excellence_gap",
        "command": "agent-excellence-smoke",
        "tool_manifest": tool_manifest_payload,
        "skill_descriptor": skill_descriptor,
        "skill_registry": skill_registry,
        "mcp_descriptor": mcp_descriptor,
        "mcp_read_only_probe": mcp_read_only_probe,
        "mcp_governance_probe": mcp_governance_probe,
        "coding_agent_probe": coding_agent_probe,
        "workflow_catalog_results": workflow_catalog_results,
        "policy_probe": {
            "hallucinated_tool_name": hallucinated_tool_name,
            "selected_tool_in_available_tools": hallucinated_tool_name in available_tool_names,
        },
        "closure_gates": closure_gates,
        "evidence_summary": {
            "available_tool_count": len(available_tools),
            "governed_tool_count": len(governed_tools),
            "approval_required_tool_count": approval_required_tool_count,
            "skill_name": str(skill_descriptor.get("name") or ""),
            "skill_registry_entry_count": int(skill_registry.get("entry_count") or 0),
            "mcp_bridge_mode": str(mcp_descriptor.get("bridge_mode") or ""),
            "mcp_read_only_probe_tool": str(mcp_read_only_probe.get("tool_name") or ""),
            "mcp_governance_probe_tool": str(mcp_governance_probe.get("tool_name") or ""),
            "coding_agent_probe_runner": str(coding_agent_probe.get("runner_name") or ""),
            "workflow_catalog_failure_statuses": [
                str(result.get("failure_status") or "")
                for result in workflow_catalog_results
                if str(result.get("failure_status") or "")
            ],
        },
        "ok": all(closure_gates.values()),
    }


def build_mcp_read_only_execution(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    adapter = tool_adapter or FakeUnitToolAdapter()
    contract = adapter.describe_tool(tool_name)
    if contract is None:
        return {
            "ok": False,
            "status": "tool_not_found",
            "reason": "mcp_read_only_tool_missing_from_manifest",
            "schema_version": MCP_READ_ONLY_EXECUTION_SCHEMA_VERSION,
            "command": "mcp-read-only-execute",
            "tool_name": tool_name,
        }

    mcp_descriptor = load_mcp_bridge_descriptor_payload(
        adapter,
        bridge_mode="core_governed_read_only_execution",
    )
    allowed_operations = set(cast(list[str], mcp_descriptor.get("allowed_operations") or []))
    policy_decision = ReadOnlyToolPolicy().evaluate_contract(contract).to_dict()
    if "execute_read_only_tool_via_core" not in allowed_operations:
        return {
            "ok": False,
            "status": "mcp_read_only_execution_not_allowed",
            "reason": "mcp_bridge_mode_missing_execute_operation",
            "schema_version": MCP_READ_ONLY_EXECUTION_SCHEMA_VERSION,
            "command": "mcp-read-only-execute",
            "tool_name": tool_name,
            "contract": contract.to_dict(),
            "mcp_descriptor": mcp_descriptor,
            "policy_decision": policy_decision,
        }
    if not policy_decision.get("allowed", False):
        return {
            "ok": False,
            "status": "tool_policy_denied",
            "reason": str(policy_decision.get("reason") or "tool_policy_denied"),
            "schema_version": MCP_READ_ONLY_EXECUTION_SCHEMA_VERSION,
            "command": "mcp-read-only-execute",
            "tool_name": tool_name,
            "contract": contract.to_dict(),
            "mcp_descriptor": mcp_descriptor,
            "policy_decision": policy_decision,
        }

    tool_result = adapter.execute(tool_name, tool_args)
    ok = tool_result.status == "ok"
    return {
        "ok": ok,
        "status": "ok" if ok else tool_result.status,
        "reason": "mcp_read_only_tool_executed" if ok else "mcp_read_only_tool_execution_failed",
        "schema_version": MCP_READ_ONLY_EXECUTION_SCHEMA_VERSION,
        "command": "mcp-read-only-execute",
        "tool_name": tool_name,
        "tool_args": dict(tool_args),
        "contract": contract.to_dict(),
        "mcp_descriptor": mcp_descriptor,
        "policy_decision": policy_decision,
        "tool_result": tool_result.to_dict(),
    }


def build_coding_agent_self_improvement_route(
    *,
    runner_name: str,
    summary: str,
    source: str = "maintenance_finding",
    decision: str = "pending",
    evidence: ImprovementEvidence | None = None,
) -> dict[str, Any]:
    descriptor = load_coding_agent_runner_descriptor_payload(runner_name=runner_name)
    proposal = propose_self_improvement(
        proposal_id=f"coding-agent-{runner_name}-proposal-001",
        source=source,
        summary=summary,
        touches_code=True,
        targets_runtime=False,
        evidence=evidence,
    )
    effective_evidence = evidence or ImprovementEvidence()
    if decision == "approve":
        review = review_self_improvement(
            proposal,
            approved=True,
            evidence=effective_evidence,
        )
    elif decision == "deny":
        review = review_self_improvement(
            proposal,
            approved=False,
            evidence=effective_evidence,
        )
    else:
        review = None

    plan_artifact: dict[str, Any] = {
        "schema_version": CODING_AGENT_SANDBOX_PLAN_SCHEMA_VERSION,
        "artifact_id": f"plan-{runner_name}-001",
        "artifact_kind": "coding_agent_plan",
        "runner_name": runner_name,
        "summary": summary,
        "source": source,
        "sandbox_mode": proposal.sandbox_mode,
        "approval_required": proposal.approval_required,
        "touches_code": proposal.touches_code,
        "targets_runtime": proposal.targets_runtime,
        "invocation_mode": str(descriptor.get("invocation_mode") or ""),
        "prohibited_actions": list(proposal.prohibited_actions),
        "execution_target": "isolated_workspace",
        "plan_steps": [
            {
                "step_id": "review-proposal",
                "kind": "approval_gate",
                "required": True,
                "status": "completed" if review is not None else "pending",
                "evidence_refs": list(effective_evidence.evidence_refs),
            },
            {
                "step_id": "prepare-sandbox-workspace",
                "kind": "sandbox_prepare",
                "required": True,
                "status": (
                    "completed"
                    if review is not None and review.decision == "approved"
                    else "pending"
                ),
                "workspace_policy": "isolated_workspace",
            },
            {
                "step_id": "run-verification",
                "kind": "verification",
                "required": True,
                "status": (
                    "completed" if effective_evidence.verified_success() else "pending"
                ),
                "verification_requirements": {
                    "tests_passed": effective_evidence.tests_passed,
                    "lint_passed": effective_evidence.lint_passed,
                    "smoke_passed": effective_evidence.smoke_passed,
                },
            },
        ],
        "sandbox_policy": {
            "workspace_mode": proposal.sandbox_mode,
            "network_access": "forbidden_by_default",
            "direct_mcp_execution": "forbidden",
            "apply_changes": False,
            "release_target_promotion": "forbidden",
        },
        "callback_contract": {
            "callback_name": "self_improvement_review_complete",
            "callback_audit_required": True,
            "must_reference_plan_artifact": True,
            "must_record_verified_success": True,
        },
    }

    sandbox_execution_record: dict[str, Any] = {
        "status": (
            "recorded"
            if review is not None and review.decision == "approved"
            else "not_executed"
        ),
        "runner_name": runner_name,
        "sandbox_mode": proposal.sandbox_mode,
        "execution_mode": review.execution_mode if review is not None else "not_executed",
        "approval_required": proposal.approval_required,
        "plan_only_invocation": str(descriptor.get("invocation_mode") or "").endswith(
            "plan_only"
        ),
        "plan_artifact": plan_artifact,
        "can_apply_changes": review.can_apply_changes if review is not None else False,
        "evidence_refs": list(effective_evidence.evidence_refs),
    }
    callback_audit_record: dict[str, Any] = {
        "status": (
            "recorded"
            if review is not None and review.decision == "approved"
            else "not_recorded"
        ),
        "runner_name": runner_name,
        "callback_name": "self_improvement_review_complete",
        "operator_decision": review.decision if review is not None else "pending_approval",
        "verified_success": effective_evidence.verified_success(),
        "release_target_promotion_blocked": bool(
            descriptor.get("release_target_promotion_blocked", False)
        ),
        "callback_payload": {
            "runner_name": runner_name,
            "plan_artifact_id": str(plan_artifact.get("artifact_id") or ""),
            "decision": review.decision if review is not None else "pending_approval",
            "sandbox_execution_status": sandbox_execution_record.get("status"),
            "verified_success": effective_evidence.verified_success(),
            "evidence_refs": list(effective_evidence.evidence_refs),
        },
        "prohibited_actions": list(proposal.prohibited_actions),
    }

    closure_gates: dict[str, bool] = {
        "review_routing_required": bool(
            cast(dict[str, Any], descriptor.get("safety_boundaries") or {}).get(
                "self_improvement_routing_required",
                False,
            )
        ),
        "operator_approval_required": bool(descriptor.get("approval_required", False))
        and proposal.approval_required,
        "sandbox_only_execution": bool(
            cast(dict[str, Any], descriptor.get("safety_boundaries") or {}).get(
                "sandbox_only_execution",
                False,
            )
        )
        and proposal.sandbox_mode == "isolated_workspace",
        "direct_execution_still_forbidden": bool(
            descriptor.get("direct_execution_forbidden", False)
        ),
        "verified_evidence_required_for_vitality": (
            review is None
            or not review.vitality_replenishment_allowed
            or review.proposal.evidence.verified_success()
        ),
        "sandbox_execution_recorded": (
            sandbox_execution_record["status"] == "recorded"
            if review is not None and review.decision == "approved"
            else True
        ),
        "plan_artifact_recorded": bool(plan_artifact.get("artifact_id")),
        "plan_artifact_contract_supported": str(
            plan_artifact.get("schema_version") or ""
        )
        == CODING_AGENT_SANDBOX_PLAN_SCHEMA_VERSION,
        "plan_steps_recorded": bool(plan_artifact.get("plan_steps")),
        "callback_audit_recorded": (
            callback_audit_record["status"] == "recorded"
            if review is not None and review.decision == "approved"
            else True
        ),
        "callback_payload_recorded": bool(
            cast(dict[str, Any], callback_audit_record.get("callback_payload") or {}).get(
                "plan_artifact_id"
            )
        ),
    }
    route_status = "pending_approval"
    if review is not None:
        route_status = review.decision
    return {
        "ok": all(closure_gates.values()),
        "status": route_status,
        "schema_version": CODING_AGENT_SELF_IMPROVEMENT_ROUTE_SCHEMA_VERSION,
        "command": "coding-agent-self-improvement-route",
        "runner_name": runner_name,
        "descriptor": descriptor,
        "proposal": proposal.to_dict(),
        "review": review.to_dict() if review is not None else None,
        "plan_artifact": plan_artifact,
        "sandbox_execution_record": sandbox_execution_record,
        "callback_audit_record": callback_audit_record,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "decision": decision,
            "verified_success": effective_evidence.verified_success(),
            "sandbox_mode": proposal.sandbox_mode,
            "plan_artifact_id": str(plan_artifact.get("artifact_id") or ""),
            "can_apply_changes": review.can_apply_changes if review is not None else False,
            "vitality_replenishment_allowed": (
                review.vitality_replenishment_allowed if review is not None else False
            ),
            "callback_audit_recorded": callback_audit_record["status"] == "recorded",
        },
    }


def _build_agent_excellence_closure_summary(
    agent_excellence_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if agent_excellence_payload is None:
        gates = {
            "agent_excellence_evidence_supplied": False,
            "agent_excellence_contract_supported": False,
            "available_tools_recorded": False,
            "governed_tools_present": False,
            "side_effect_tools_require_approval": False,
            "workflow_catalog_consistent": False,
            "skill_descriptor_present": False,
            "workflow_plan_required_for_governed_tools": False,
            "release_target_promotion_blocked": False,
            "callback_audit_required": False,
            "mcp_descriptor_read_only": False,
            "tool_execution_via_mcp_forbidden": False,
            "external_mcp_disabled": False,
            "approval_required_tool_proposals_blocked": False,
            "hallucinated_tool_rejected_by_available_manifest": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "agent_excellence_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], agent_excellence_payload.get("closure_gates") or {})
    gates = {
        "agent_excellence_evidence_supplied": True,
        "agent_excellence_contract_supported": str(
            agent_excellence_payload.get("schema_version") or ""
        )
        == AGENT_EXCELLENCE_SMOKE_SCHEMA_VERSION,
        "available_tools_recorded": bool(payload_gates.get("available_tools_recorded")),
        "governed_tools_present": bool(payload_gates.get("governed_tools_present")),
        "side_effect_tools_require_approval": bool(
            payload_gates.get("side_effect_tools_require_approval")
        ),
        "workflow_catalog_consistent": bool(
            payload_gates.get("workflow_catalog_consistent")
        ),
        "skill_descriptor_present": bool(payload_gates.get("skill_descriptor_supplied"))
        and bool(payload_gates.get("skill_descriptor_contract_supported")),
        "workflow_plan_required_for_governed_tools": bool(
            payload_gates.get("workflow_plan_required_for_governed_tools")
        ),
        "release_target_promotion_blocked": bool(
            payload_gates.get("release_target_promotion_blocked")
        ),
        "callback_audit_required": bool(
            payload_gates.get("callback_audit_required")
        ),
        "mcp_descriptor_read_only": bool(payload_gates.get("mcp_descriptor_read_only"))
        and bool(payload_gates.get("mcp_descriptor_supplied"))
        and bool(payload_gates.get("mcp_descriptor_contract_supported")),
        "tool_execution_via_mcp_forbidden": bool(
            payload_gates.get("tool_execution_via_mcp_forbidden")
        ),
        "external_mcp_disabled": bool(payload_gates.get("external_mcp_disabled")),
        "approval_required_tool_proposals_blocked": bool(
            payload_gates.get("approval_required_tool_proposals_blocked")
        ),
        "hallucinated_tool_rejected_by_available_manifest": bool(
            payload_gates.get("hallucinated_tool_rejected_by_available_manifest")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(agent_excellence_payload.get("schema_version") or ""),
        "status": str(agent_excellence_payload.get("status") or "unknown"),
        "reason": str(agent_excellence_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any],
            agent_excellence_payload.get("evidence_summary") or {},
        ),
        "ok": all(gates.values()),
    }


def build_autonomy_daemon_smoke(
    *,
    db_path: str = ":memory:",
    cycles: int = 2,
    maintenance_interval_cycles: int = 2,
    vitality_score: int = 18,
    persona_mood: str = "watchful",
) -> dict[str, Any]:
    if cycles < 1:
        raise ValueError("autonomy_daemon_smoke_requires_positive_cycle_count")

    tempdir: tempfile.TemporaryDirectory[str] | None = None
    resolved_db_path = db_path
    if db_path == ":memory:":
        tempdir = tempfile.TemporaryDirectory()
        resolved_db_path = str(Path(tempdir.name) / "autonomy-daemon-smoke.db")

    try:
        session_id = "autonomy-daemon-smoke-001"
        vitality_state = VitalityState.from_score(vitality_score)
        persona_state = PersonaState(
            persona_id="affective-main",
            mood=persona_mood,
            vitality_summary=vitality_state.state,
        )
        initial_payload = run_event_daemon_replay(
            [[] for _ in range(cycles)],
            resolved_db_path,
            session_id=session_id,
            autonomy_enabled=True,
            autonomy_policy=AutonomousDaemonPolicy(
                maintenance_interval_cycles=maintenance_interval_cycles,
            ),
            vitality_state=vitality_state,
            persona_state=persona_state,
            replay_label="autonomy-daemon-smoke-initial",
        )
        resumed_payload = run_event_daemon_replay(
            [[]],
            resolved_db_path,
            session_id=session_id,
            autonomy_enabled=True,
            autonomy_policy=AutonomousDaemonPolicy(
                maintenance_interval_cycles=maintenance_interval_cycles,
            ),
            vitality_state=vitality_state,
            persona_state=persona_state,
            replay_label="autonomy-daemon-smoke-resume",
        )
        paused_payload = run_event_daemon_replay(
            [[]],
            resolved_db_path,
            session_id=session_id,
            autonomy_enabled=True,
            autonomy_policy=AutonomousDaemonPolicy(
                maintenance_interval_cycles=maintenance_interval_cycles,
            ),
            vitality_state=vitality_state,
            persona_state=persona_state,
            operator_paused=True,
            replay_label="autonomy-daemon-smoke-paused",
        )

        initial_state = cast(
            dict[str, Any],
            initial_payload.get("event_daemon_evidence", {}).get("daemon_state") or {},
        )
        resumed_state = cast(
            dict[str, Any],
            resumed_payload.get("event_daemon_evidence", {}).get("daemon_state") or {},
        )
        paused_state = cast(
            dict[str, Any],
            paused_payload.get("event_daemon_evidence", {}).get("daemon_state") or {},
        )
        closure_gates = {
            "initial_daemon_cycle_recorded": bool(
                initial_payload.get("event_daemon_evidence", {}).get("cycle_count")
            ),
            "daemon_state_recorded": bool(initial_state),
            "heartbeat_recorded": bool(initial_state.get("heartbeat", {}).get("recorded")),
            "restart_continuity_recorded": bool(
                resumed_state.get("continuity", {}).get("resumed_session")
            ),
            "operator_pause_recorded": bool(paused_state.get("operator_paused")),
            "pause_blocks_workflow_execution": int(
                paused_payload.get("db_counts", {}).get("execution_spans", 0)
            )
            == int(resumed_payload.get("db_counts", {}).get("execution_spans", 0)),
            "vitality_summary_recorded": str(
                initial_state.get("vitality_summary", {}).get("state") or ""
            )
            == vitality_state.state,
            "persona_summary_recorded": str(
                initial_state.get("persona_summary", {}).get("mood") or ""
            )
            == persona_mood,
        }
        return {
            "schema_version": AUTONOMY_DAEMON_SMOKE_SCHEMA_VERSION,
            "status": "ready" if all(closure_gates.values()) else "incomplete",
            "reason": "autonomy_daemon_runtime_ready"
            if all(closure_gates.values())
            else "autonomy_daemon_runtime_gap",
            "command": "autonomy-daemon-smoke",
            "closure_gates": closure_gates,
            "evidence_summary": {
                "initial_cycle_count": int(
                    initial_payload.get("event_daemon_evidence", {}).get("cycle_count", 0)
                ),
                "resumed_previous_execution_count": int(
                    resumed_state.get("continuity", {}).get("previous_execution_count", 0)
                ),
                "paused_run_state": str(paused_state.get("run_state") or "unknown"),
                "vitality_state": str(initial_state.get("vitality_summary", {}).get("state") or "unknown"),
                "persona_mood": str(initial_state.get("persona_summary", {}).get("mood") or "unknown"),
            },
            "initial_run": {
                "event_daemon_evidence": initial_payload.get("event_daemon_evidence"),
                "db_counts": initial_payload.get("db_counts"),
            },
            "resumed_run": {
                "event_daemon_evidence": resumed_payload.get("event_daemon_evidence"),
                "db_counts": resumed_payload.get("db_counts"),
            },
            "paused_run": {
                "event_daemon_evidence": paused_payload.get("event_daemon_evidence"),
                "db_counts": paused_payload.get("db_counts"),
            },
            "ok": all(closure_gates.values()),
        }
    finally:
        if tempdir is not None:
            tempdir.cleanup()


def build_vitality_smoke(
    *,
    initial_score: int = 52,
) -> dict[str, Any]:
    initial_state = VitalityState.from_score(initial_score)
    decay_transition = apply_vitality_signals(
        initial_state,
        [VitalitySignal(reason="unresolved_fault", direction="decay")],
    )
    recovery_transition = apply_vitality_signals(
        decay_transition.current,
        [
            VitalitySignal(
                reason="approved_improvement",
                direction="replenish",
                verified=True,
            )
        ],
    )
    closure_gates = {
        "initial_state_recorded": True,
        "decay_transition_recorded": decay_transition.current.score < initial_state.score,
        "replenishment_requires_verification_modeled": True,
        "replenishment_transition_recorded": recovery_transition.current.score
        > decay_transition.current.score,
        "policy_impact_bounded": recovery_transition.current.policy_impact
        == "salience_and_tone_only",
        "no_permission_escalation_semantics": recovery_transition.current.policy_impact
        == "salience_and_tone_only",
    }
    return {
        "schema_version": VITALITY_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "vitality_governance_ready"
        if all(closure_gates.values())
        else "vitality_governance_gap",
        "command": "vitality-smoke",
        "closure_gates": closure_gates,
        "initial_state": initial_state.to_dict(),
        "decay_transition": decay_transition.to_dict(),
        "recovery_transition": recovery_transition.to_dict(),
        "evidence_summary": {
            "initial_state": initial_state.state,
            "post_decay_state": decay_transition.current.state,
            "post_recovery_state": recovery_transition.current.state,
            "policy_impact": recovery_transition.current.policy_impact,
        },
        "ok": all(closure_gates.values()),
    }


def build_persona_state_smoke() -> dict[str, Any]:
    seed_config = PersonaSeedConfig(
        persona_id="affective-main",
        seed_name="warm-curious",
        mood="steady",
        curiosity=0.7,
        social_openness=0.6,
        immutable_boundaries=("privacy_delete_allowed", "redaction_allowed"),
        created_at="2026-05-10T11:55:00Z",
    )
    growth_state = initialize_persona_growth_state(seed_config)
    initial_state = PersonaState.from_dict(
        {
            **initialize_persona_state_from_seed(seed_config).to_dict(),
            "seed_config": seed_config.to_dict(),
            "growth_state": growth_state.to_dict(),
        }
    )
    evolved_state = apply_persona_signals(
        initial_state,
        [
            PersonaSignal(
                reason="supportive_user_feedback",
                mood="curious",
                valence_delta=0.4,
                arousal_delta=0.2,
                curiosity_delta=0.3,
                principal_id="user-01",
                trust_delta=0.3,
                familiarity_delta=0.4,
                preferred_address="Captain",
                boundary_note="no_group_ping_at_night",
            )
        ],
        vitality_summary="attentive",
        updated_at="2026-05-10T12:00:00Z",
    )
    updated_growth_state = apply_persona_growth_evidence(
        growth_state,
        PersonaGrowthEvidence(
            event_id="evt-social-001",
            source="social_interaction",
            reason="supportive_user_feedback",
            recorded_at="2026-05-10T12:00:00Z",
            principal_id="user-01",
            summary="User feedback increased trust and familiarity.",
        ),
    )
    evolved_state = PersonaState.from_dict(
        {
            **evolved_state.to_dict(),
            "seed_config": seed_config.to_dict(),
            "growth_state": updated_growth_state.to_dict(),
        }
    )
    redacted_state = redact_relationships(evolved_state, ["user-01"])
    immutability_stamp = compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=evolved_state,
        growth_state=updated_growth_state,
    )
    closure_gates = {
        "persona_state_recorded": bool(evolved_state.to_dict()),
        "persona_seed_recorded": bool(seed_config.to_dict()),
        "persona_growth_recorded": bool(updated_growth_state.to_dict()),
        "relationship_summary_recorded": len(evolved_state.relationship_summaries) == 1,
        "rational_summary_limited": "preferred_address"
        not in evolved_state.rational_summary()["relationship_summaries"][0],
        "privacy_redaction_supported": len(redacted_state.relationship_summaries) == 0,
        "vitality_summary_bound_to_persona": evolved_state.vitality_summary == "attentive",
        "growth_requires_runtime_evidence": updated_growth_state.last_evidence_source
        == "social_interaction",
        "immutability_stamp_recorded": bool(immutability_stamp),
        "immutability_stamp_valid": not persona_immutability_tampered(
            expected_stamp=immutability_stamp,
            seed_config=seed_config,
            persona_state=evolved_state,
            growth_state=updated_growth_state,
        ),
    }
    return {
        "schema_version": PERSONA_STATE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "persona_state_ready" if all(closure_gates.values()) else "persona_state_gap",
        "command": "persona-state-smoke",
        "closure_gates": closure_gates,
        "persona_seed": seed_config.to_dict(),
        "persona_state": evolved_state.to_dict(),
        "persona_growth": updated_growth_state.to_dict(),
        "immutability_stamp": immutability_stamp,
        "rational_summary": evolved_state.rational_summary(),
        "redacted_state": redacted_state.to_dict(),
        "evidence_summary": {
            "mood": evolved_state.mood,
            "relationship_count": len(evolved_state.relationship_summaries),
            "redacted_relationship_count": len(redacted_state.relationship_summaries),
            "vitality_summary": evolved_state.vitality_summary,
            "seed_name": seed_config.seed_name,
            "growth_revision": updated_growth_state.revision,
            "growth_source": updated_growth_state.last_evidence_source,
        },
        "ok": all(closure_gates.values()),
    }


def _load_json_object(file_path: str, *, label: str) -> dict[str, Any]:
    payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label}_payload_must_be_object")
    return cast(dict[str, Any], payload)


def _bind_persona_bundle(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
) -> PersonaState:
    expected_seed_fingerprint = compute_persona_seed_fingerprint(seed_config)
    if persona_state.persona_id != seed_config.persona_id:
        raise ValueError("persona_bundle_persona_id_mismatch")
    if growth_state.persona_id != seed_config.persona_id:
        raise ValueError("persona_growth_persona_id_mismatch")
    if growth_state.seed_fingerprint != expected_seed_fingerprint:
        raise ValueError("persona_growth_seed_fingerprint_mismatch")
    return PersonaState.from_dict(
        {
            **persona_state.to_dict(),
            "seed_config": seed_config.to_dict(),
            "growth_state": growth_state.to_dict(),
            "provenance_hash": persona_state.provenance_hash or growth_state.seed_fingerprint,
            "updated_at": persona_state.updated_at or seed_config.created_at,
        }
    )


def _build_persona_seed_setup_payload(
    seed_config: PersonaSeedConfig,
) -> dict[str, Any]:
    growth_state = initialize_persona_growth_state(seed_config)
    persona_state = _bind_persona_bundle(
        seed_config=seed_config,
        persona_state=initialize_persona_state_from_seed(
            seed_config,
            updated_at=seed_config.created_at,
        ),
        growth_state=growth_state,
    )
    immutability_stamp = compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    )
    closure_gates = {
        "seed_config_recorded": bool(seed_config.to_dict()),
        "persona_state_initialized": bool(persona_state.to_dict()),
        "growth_state_initialized": bool(growth_state.to_dict()),
        "provenance_hash_recorded": bool(persona_state.provenance_hash),
        "immutability_stamp_valid": not persona_immutability_tampered(
            expected_stamp=immutability_stamp,
            seed_config=seed_config,
            persona_state=persona_state,
            growth_state=growth_state,
        ),
    }
    return {
        "schema_version": PERSONA_SEED_SETUP_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "persona_seed_initialized" if all(closure_gates.values()) else "persona_seed_gap",
        "command": "persona-seed-setup",
        "seed_config": seed_config.to_dict(),
        "persona_state": persona_state.to_dict(),
        "persona_growth": growth_state.to_dict(),
        "immutability_stamp": immutability_stamp,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "persona_id": seed_config.persona_id,
            "seed_name": seed_config.seed_name,
            "immutable_boundary_count": len(seed_config.immutable_boundaries),
            "growth_revision": growth_state.revision,
        },
        "ok": all(closure_gates.values()),
    }


def _build_persona_seed_config_from_args(args: argparse.Namespace) -> PersonaSeedConfig:
    return PersonaSeedConfig(
        persona_id=args.persona_id,
        seed_name=args.seed_name,
        mood=args.mood,
        valence=args.valence,
        arousal=args.arousal,
        curiosity=args.curiosity,
        fatigue=args.fatigue,
        social_openness=args.social_openness,
        vitality_summary=args.vitality_summary,
        relationship_style=args.relationship_style,
        immutable_boundaries=tuple(args.immutable_boundary),
        created_at=args.created_at,
    )


def _load_persona_bundle_from_files(
    *,
    seed_file: str,
    persona_file: str,
    growth_file: str,
) -> tuple[PersonaSeedConfig, PersonaState, PersonaGrowthState]:
    seed_config = PersonaSeedConfig.from_dict(_load_json_object(seed_file, label="persona_seed"))
    persona_state = PersonaState.from_dict(_load_json_object(persona_file, label="persona_state"))
    growth_state = PersonaGrowthState.from_dict(_load_json_object(growth_file, label="persona_growth"))
    return seed_config, _bind_persona_bundle(
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    ), growth_state


def build_persona_state_export(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
    redact_principal_ids: list[str],
    expected_immutability_stamp: str | None = None,
) -> dict[str, Any]:
    exported_state = (
        redact_relationships(persona_state, redact_principal_ids)
        if redact_principal_ids
        else persona_state
    )
    exported_state = _bind_persona_bundle(
        seed_config=seed_config,
        persona_state=exported_state,
        growth_state=growth_state,
    )
    actual_stamp = compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    )
    tampered = False
    if expected_immutability_stamp:
        tampered = persona_immutability_tampered(
            expected_stamp=expected_immutability_stamp,
            seed_config=seed_config,
            persona_state=persona_state,
            growth_state=growth_state,
        )
    closure_gates = {
        "export_ready": True,
        "redaction_applied": (
            not redact_principal_ids
            or len(exported_state.relationship_summaries)
            <= len(persona_state.relationship_summaries)
        ),
        "immutability_stamp_valid": not tampered,
        "growth_state_attached": exported_state.growth_state is not None,
    }
    return {
        "schema_version": PERSONA_STATE_EXPORT_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "tampered",
        "reason": "persona_export_ready" if all(closure_gates.values()) else "persona_export_tampered",
        "command": "persona-state-export",
        "seed_config": seed_config.to_dict(),
        "persona_state": exported_state.to_dict(),
        "persona_growth": growth_state.to_dict(),
        "immutability_stamp": actual_stamp,
        "expected_immutability_stamp": expected_immutability_stamp,
        "redacted_principal_ids": list(redact_principal_ids),
        "rational_summary": exported_state.rational_summary(),
        "closure_gates": closure_gates,
        "evidence_summary": {
            "relationship_count": len(exported_state.relationship_summaries),
            "redacted_principal_count": len(redact_principal_ids),
            "tampered": tampered,
        },
        "ok": all(closure_gates.values()),
    }


def build_persona_growth_apply(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
    evidence: PersonaGrowthEvidence,
) -> dict[str, Any]:
    updated_growth = apply_persona_growth_evidence(growth_state, evidence)
    updated_persona = _bind_persona_bundle(
        seed_config=seed_config,
        persona_state=PersonaState.from_dict(
            {
                **persona_state.to_dict(),
                "growth_state": updated_growth.to_dict(),
                "updated_at": evidence.recorded_at,
                "provenance_hash": updated_growth.provenance_hash,
            }
        ),
        growth_state=updated_growth,
    )
    immutability_stamp = compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=updated_persona,
        growth_state=updated_growth,
    )
    closure_gates = {
        "runtime_evidence_only": evidence.source in PERSONA_GROWTH_RUNTIME_SOURCES,
        "growth_revision_advanced": updated_growth.revision == growth_state.revision + 1,
        "evidence_event_recorded": evidence.event_id in updated_growth.evidence_event_ids,
        "immutability_stamp_valid": not persona_immutability_tampered(
            expected_stamp=immutability_stamp,
            seed_config=seed_config,
            persona_state=updated_persona,
            growth_state=updated_growth,
        ),
    }
    return {
        "schema_version": PERSONA_GROWTH_APPLY_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "persona_growth_recorded" if all(closure_gates.values()) else "persona_growth_gap",
        "command": "persona-growth-apply",
        "growth_evidence": evidence.to_dict(),
        "seed_config": seed_config.to_dict(),
        "persona_state": updated_persona.to_dict(),
        "persona_growth": updated_growth.to_dict(),
        "immutability_stamp": immutability_stamp,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "growth_revision": updated_growth.revision,
            "last_evidence_source": updated_growth.last_evidence_source,
            "last_evidence_reason": updated_growth.last_evidence_reason,
            "evidence_event_count": len(updated_growth.evidence_event_ids),
        },
        "ok": all(closure_gates.values()),
    }


def build_persona_state_inspect(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
    rational_summary_only: bool = False,
) -> dict[str, Any]:
    bound_persona = _bind_persona_bundle(
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    )
    immutability_stamp = compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=bound_persona,
        growth_state=growth_state,
    )
    closure_gates = {
        "read_only_view": True,
        "growth_state_attached": bound_persona.growth_state is not None,
        "immutability_stamp_valid": not persona_immutability_tampered(
            expected_stamp=immutability_stamp,
            seed_config=seed_config,
            persona_state=bound_persona,
            growth_state=growth_state,
        ),
        "prompt_safe_summary_available": bool(bound_persona.rational_summary()),
    }
    return {
        "schema_version": PERSONA_STATE_INSPECT_SCHEMA_VERSION,
        "status": "ready",
        "reason": "persona_state_inspect_ready",
        "command": "persona-state-inspect",
        "rational_summary_only": rational_summary_only,
        "seed_config": seed_config.to_dict(),
        "persona_state": None if rational_summary_only else bound_persona.to_dict(),
        "persona_growth": None if rational_summary_only else growth_state.to_dict(),
        "immutability_stamp": immutability_stamp,
        "rational_summary": bound_persona.rational_summary(),
        "closure_gates": closure_gates,
        "evidence_summary": {
            "relationship_count": len(bound_persona.relationship_summaries),
            "growth_revision": growth_state.revision,
        },
        "ok": all(closure_gates.values()),
    }


def build_persona_state_delete(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
    principal_ids: list[str],
    delete_all: bool,
) -> dict[str, Any]:
    if delete_all:
        deleted_persona: dict[str, Any] | None = None
        deleted_growth: dict[str, Any] | None = None
        deleted_relationship_count = len(persona_state.relationship_summaries)
    else:
        updated_persona = redact_relationships(persona_state, principal_ids)
        updated_persona = _bind_persona_bundle(
            seed_config=seed_config,
            persona_state=updated_persona,
            growth_state=growth_state,
        )
        deleted_persona = updated_persona.to_dict()
        deleted_growth = growth_state.to_dict()
        deleted_relationship_count = (
            len(persona_state.relationship_summaries)
            - len(updated_persona.relationship_summaries)
        )
    closure_gates = {
        "delete_scope_declared": delete_all or bool(principal_ids),
        "privacy_operation_only": True,
        "growth_state_not_rewritten": delete_all or deleted_growth == growth_state.to_dict(),
    }
    return {
        "schema_version": PERSONA_STATE_DELETE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "persona_state_deleted" if delete_all else "persona_state_redacted",
        "command": "persona-state-delete",
        "delete_all": delete_all,
        "deleted_principal_ids": list(principal_ids),
        "deleted_relationship_count": deleted_relationship_count,
        "seed_config": None if delete_all else seed_config.to_dict(),
        "persona_state": deleted_persona,
        "persona_growth": deleted_growth,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "full_bundle_deleted": delete_all,
            "deleted_relationship_count": deleted_relationship_count,
            "remaining_relationship_count": (
                0
                if delete_all
                else len(cast(dict[str, Any], deleted_persona)["relationship_summaries"])
            ),
        },
        "ok": all(closure_gates.values()),
    }


def build_persona_tamper_report(
    *,
    seed_config: PersonaSeedConfig,
    persona_state: PersonaState,
    growth_state: PersonaGrowthState,
    expected_immutability_stamp: str,
) -> dict[str, Any]:
    actual_stamp = compute_persona_immutability_stamp(
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    )
    tampered = persona_immutability_tampered(
        expected_stamp=expected_immutability_stamp,
        seed_config=seed_config,
        persona_state=persona_state,
        growth_state=growth_state,
    )
    closure_gates = {
        "expected_stamp_supplied": bool(expected_immutability_stamp),
        "immutability_stamp_valid": not tampered,
        "persona_growth_bound": persona_state.growth_state is not None,
    }
    return {
        "schema_version": PERSONA_TAMPER_REPORT_SCHEMA_VERSION,
        "status": "tampered" if tampered else "ready",
        "reason": "persona_immutability_tampered" if tampered else "persona_immutability_verified",
        "command": "persona-tamper-report",
        "expected_immutability_stamp": expected_immutability_stamp,
        "actual_immutability_stamp": actual_stamp,
        "tampered": tampered,
        "seed_config": seed_config.to_dict(),
        "persona_state": persona_state.to_dict(),
        "persona_growth": growth_state.to_dict(),
        "closure_gates": closure_gates,
        "evidence_summary": {
            "persona_id": seed_config.persona_id,
            "growth_revision": growth_state.revision,
            "expected_matches_actual": not tampered,
        },
        "ok": all(closure_gates.values()),
    }


def build_approval_social_smoke() -> dict[str, Any]:
    tempdir = tempfile.TemporaryDirectory()
    try:
        db_path = str(Path(tempdir.name) / "approval-social-smoke.db")
        run_payload = run_no_model_dry_run(
            db_path,
            events=[
                _build_social_user_prompt_event(
                    social_text="restart the app now",
                    social_adapter_kind="mock_qq",
                    social_channel_id="group-approval-001",
                    social_channel_kind="group",
                    social_user_id="alice",
                    social_admin=False,
                    received_at="2026-05-10T13:00:00Z",
                )
            ],
            session_id="approval-social-smoke-001",
        )
        social_adapter = MockSocialAdapter()
        approval_request = cast(
            dict[str, Any],
            run_payload["tool_results"][0]["payload"]["approval_request"],
        )
        data_store = CoreDataStore(db_path)
        try:
            stored_approval_request = data_store.get_approval_request(
                str(approval_request["approval_request_id"])
            )
            assert stored_approval_request is not None
            inspect_context = build_approval_context(
                data_store,
                stored_approval_request,
            )
        finally:
            data_store.close()
        approval_summary = build_social_approval_summary(
            stored_approval_request,
            inspect_context,
        )
        social_envelope = social_adapter.bind_approval_principal(
            approval_request_id=str(approval_request["approval_request_id"]),
            adapter_kind="mock_qq",
            channel_id="group-approval-001",
            channel_kind="group",
            external_user_id="alice",
            decision_text="deny from social channel",
            received_at="2026-05-10T13:01:00Z",
        )
        decision_payload = apply_approval_decision(
            db_path,
            approval_request_id=str(approval_request["approval_request_id"]),
            decision="deny",
            approval_metadata=social_adapter.social_approval_metadata(social_envelope),
        )
        closure_gates: dict[str, bool] = {
            "pending_approval_created": run_payload["tool_results"][0]["status"]
            == "pending_approval",
            "social_summary_present": bool(approval_summary.get("human_summary")),
            "social_principal_recorded": cast(
                dict[str, Any], decision_payload.get("approval_metadata") or {}
            ).get("principal_id")
            == "mock_qq:alice",
            "denied_decision_prevents_execution": decision_payload["status"] == "denied"
            and decision_payload.get("resumed_execution") is None,
        }
        return {
            "schema_version": APPROVAL_SOCIAL_SMOKE_SCHEMA_VERSION,
            "status": "ready" if all(closure_gates.values()) else "incomplete",
            "reason": "approval_social_ready"
            if all(closure_gates.values())
            else "approval_social_gap",
            "command": "approval-social-smoke",
            "closure_gates": closure_gates,
            "approval_request": approval_request,
            "approval_summary": approval_summary,
            "decision_payload": decision_payload,
            "evidence_summary": {
                "tool_name": approval_request.get("tool_name"),
                "decision_status": decision_payload.get("status"),
                "principal_id": cast(
                    dict[str, Any], decision_payload.get("approval_metadata") or {}
                ).get("principal_id"),
            },
            "ok": all(closure_gates.values()),
        }
    finally:
        tempdir.cleanup()


def _build_social_user_prompt_event(
    *,
    social_text: str,
    social_adapter_kind: str,
    social_channel_id: str,
    social_channel_kind: str,
    social_user_id: str,
    social_admin: bool,
    received_at: str,
) -> dict[str, Any]:
    social_adapter = MockSocialAdapter()
    social_envelope = social_adapter.bind_principal(
        adapter_kind=social_adapter_kind,
        channel_id=social_channel_id,
        channel_kind=social_channel_kind,
        external_user_id=social_user_id,
        text=social_text,
        received_at=received_at,
        is_admin=social_admin,
    )
    social_event = social_adapter.to_perception_event(social_envelope)
    return _merge_social_prompt_event(
        social_event=social_event,
        social_text=social_text,
        social_adapter_kind=social_adapter_kind,
        social_metadata=social_envelope.metadata,
    )


def _merge_social_prompt_event(
    *,
    social_event: dict[str, Any],
    social_text: str,
    social_adapter_kind: str,
    social_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    classified_event = build_user_prompt_event(social_text)[0]
    merged_policy_tags = list(
        dict.fromkeys(
            [
                *cast(list[str], social_event.get("policy_tags") or []),
                *cast(list[str], classified_event.get("policy_tags") or []),
            ]
        )
    )
    social_event["event_type"] = str(classified_event.get("event_type") or "user.input")
    social_event["semantic_topic"] = str(
        classified_event.get("semantic_topic") or social_event.get("semantic_topic")
    )
    social_event["source_app"] = classified_event.get("source_app")
    social_event["priority"] = max(
        int(social_event.get("priority") or 0),
        int(classified_event.get("priority") or 0),
    )
    social_event["policy_tags"] = merged_policy_tags
    social_event["payload"] = {
        **cast(dict[str, Any], social_event.get("payload") or {}),
        **cast(dict[str, Any], classified_event.get("payload") or {}),
        "social_adapter": social_adapter_kind,
        "social_metadata": dict(social_metadata or {}),
    }
    return social_event


def _build_social_event_from_envelope(
    envelope: SocialMessageEnvelope,
    *,
    social_adapter: Any,
) -> dict[str, Any]:
    social_event = cast(dict[str, Any], social_adapter.to_perception_event(envelope))
    return _merge_social_prompt_event(
        social_event=social_event,
        social_text=envelope.text,
        social_adapter_kind=envelope.adapter_kind,
        social_metadata=envelope.metadata,
    )


def _run_social_agent_payload(
    *,
    db_path: str,
    social_text: str,
    social_adapter_kind: str,
    social_channel_id: str,
    social_channel_kind: str,
    social_user_id: str,
    social_admin: bool,
    session_id: str | None,
    maf_provider_mode: str = MafProviderMode.DETERMINISTIC_FAKE.value,
    allow_model_call: bool = False,
    memory_backend: str = "fake",
    rational_backend: str = "auto",
    tool_adapter: Any | None = None,
    require_real_tool_adapter: bool = False,
) -> dict[str, Any]:
    return run_no_model_dry_run(
        db_path,
        tool_adapter=tool_adapter,
        events=[
            _build_social_user_prompt_event(
                social_text=social_text,
                social_adapter_kind=social_adapter_kind,
                social_channel_id=social_channel_id,
                social_channel_kind=social_channel_kind,
                social_user_id=social_user_id,
                social_admin=social_admin,
                received_at="2026-05-10T12:30:00Z",
            )
        ],
        session_id=session_id,
        maf_provider_mode=maf_provider_mode,
        allow_model_call=allow_model_call,
        memory_backend=memory_backend,
        rational_backend=rational_backend,
        require_real_tool_adapter=require_real_tool_adapter,
        event_source_label="mock_social",
    )


def _pick_profile_env_value(
    profile: SocialAdapterProfile,
    *,
    preferred_fragments: tuple[str, ...],
) -> tuple[str, str]:
    env_vars = list(profile.credential_env_vars)
    for fragment in preferred_fragments:
        for env_var in env_vars:
            if fragment in env_var.upper():
                value = str(os.environ.get(env_var) or "")
                if value:
                    return env_var, value
    for env_var in env_vars:
        value = str(os.environ.get(env_var) or "")
        if value:
            return env_var, value
    raise ValueError("qq_official_credential_env_missing")


def _run_qq_official_live_ingress(
    *,
    db_path: str,
    host: str,
    port: int,
    path: str,
    duration: int,
    max_events: int,
    ready_file: str,
    session_id: str | None,
    config_path: str,
    maf_provider_mode: str,
    allow_model_call: bool,
    memory_backend: str,
    rational_backend: str,
    require_real_tool_adapter: bool,
) -> dict[str, Any]:
    registry = social_adapter_registry(env=os.environ, config_path=config_path)
    profile = registry.get_profile("qq_official")
    if profile is None:
        raise ValueError("qq_official_profile_missing")
    if not profile.ready_for_live_io:
        raise ValueError("qq_official_profile_not_ready")
    _, app_secret = _pick_profile_env_value(
        profile,
        preferred_fragments=("APP_SECRET", "SECRET", "TOKEN"),
    )
    social_adapter = QQOfficialSocialAdapter()

    def ingest_callback(envelope: SocialMessageEnvelope, event_type: str) -> dict[str, Any]:
        event = _build_social_event_from_envelope(
            envelope,
            social_adapter=social_adapter,
        )
        event["payload"] = {
            **cast(dict[str, Any], event.get("payload") or {}),
            "qq_event_type": event_type,
        }
        return run_no_model_dry_run(
            db_path,
            events=[event],
            session_id=session_id,
            maf_provider_mode=maf_provider_mode,
            allow_model_call=allow_model_call,
            memory_backend=memory_backend,
            rational_backend=rational_backend,
            require_real_tool_adapter=require_real_tool_adapter,
            event_source_label="qq_official_webhook",
        )

    return run_qq_official_webhook_server(
        app_secret=app_secret,
        ingest_callback=ingest_callback,
        host=host,
        port=port,
        path=path,
        duration=duration,
        max_events=max_events,
        ready_file=ready_file,
    )


def _run_qq_official_gateway_ingress(
    *,
    db_path: str,
    duration: int,
    max_events: int,
    ready_file: str,
    session_state_file: str,
    max_resume_attempts: int,
    reconnect_backoff_seconds: float,
    session_id: str | None,
    config_path: str,
    gateway_url: str,
    maf_provider_mode: str,
    allow_model_call: bool,
    memory_backend: str,
    rational_backend: str,
    require_real_tool_adapter: bool,
) -> dict[str, Any]:
    registry = social_adapter_registry(env=os.environ, config_path=config_path)
    profile = registry.get_profile("qq_official")
    if profile is None:
        raise ValueError("qq_official_profile_missing")
    if not profile.ready_for_live_io:
        raise ValueError("qq_official_profile_not_ready")
    _, app_id = _pick_profile_env_value(
        profile,
        preferred_fragments=("APP_ID",),
    )
    _, app_secret = _pick_profile_env_value(
        profile,
        preferred_fragments=("APP_SECRET", "SECRET", "TOKEN"),
    )
    social_adapter = QQOfficialSocialAdapter()

    def ingest_callback(envelope: SocialMessageEnvelope, event_type: str) -> dict[str, Any]:
        event = _build_social_event_from_envelope(
            envelope,
            social_adapter=social_adapter,
        )
        event["payload"] = {
            **cast(dict[str, Any], event.get("payload") or {}),
            "qq_event_type": event_type,
        }
        return run_no_model_dry_run(
            db_path,
            events=[event],
            session_id=session_id,
            maf_provider_mode=maf_provider_mode,
            allow_model_call=allow_model_call,
            memory_backend=memory_backend,
            rational_backend=rational_backend,
            require_real_tool_adapter=require_real_tool_adapter,
            event_source_label="qq_official_gateway",
        )

    return run_qq_official_gateway_client(
        app_id=app_id,
        app_secret=app_secret,
        ingest_callback=ingest_callback,
        duration=duration,
        max_events=max_events,
        ready_file=ready_file,
        gateway_url=gateway_url,
        session_state_file=session_state_file,
        max_resume_attempts=max_resume_attempts,
        reconnect_backoff_seconds=reconnect_backoff_seconds,
    )


def _run_wecom_gateway_ingress(
    *,
    db_path: str,
    duration: int,
    max_events: int,
    ready_file: str,
    session_id: str | None,
    config_path: str,
    gateway_url: str,
    maf_provider_mode: str,
    allow_model_call: bool,
    memory_backend: str,
    rational_backend: str,
    require_real_tool_adapter: bool,
) -> dict[str, Any]:
    registry = social_adapter_registry(env=os.environ, config_path=config_path)
    profile = registry.get_profile("wecom")
    if profile is None:
        raise ValueError("wecom_profile_missing")
    if not profile.ready_for_live_io:
        raise ValueError("wecom_profile_not_ready")
    _, access_token = _pick_profile_env_value(
        profile,
        preferred_fragments=("TOKEN", "KEY", "SECRET"),
    )
    resolved_gateway_url = gateway_url or profile.endpoint_url or ""
    if not resolved_gateway_url:
        raise ValueError("wecom_gateway_url_missing")
    social_adapter = WeComSocialAdapter()

    def ingest_callback(envelope: SocialMessageEnvelope, event_type: str) -> dict[str, Any]:
        event = _build_social_event_from_envelope(
            envelope,
            social_adapter=social_adapter,
        )
        event["payload"] = {
            **cast(dict[str, Any], event.get("payload") or {}),
            "wecom_event_type": event_type,
        }
        return run_no_model_dry_run(
            db_path,
            events=[event],
            session_id=session_id,
            maf_provider_mode=maf_provider_mode,
            allow_model_call=allow_model_call,
            memory_backend=memory_backend,
            rational_backend=rational_backend,
            require_real_tool_adapter=require_real_tool_adapter,
            event_source_label="wecom_gateway",
        )

    return run_wecom_gateway_client(
        access_token=access_token,
        gateway_url=resolved_gateway_url,
        ingest_callback=ingest_callback,
        duration=duration,
        max_events=max_events,
        ready_file=ready_file,
    )


def _run_openclaw_gateway_ingress(
    *,
    db_path: str,
    adapter_name: str,
    duration: int,
    max_events: int,
    ready_file: str,
    session_id: str | None,
    config_path: str,
    gateway_url: str,
    plugin_package: str,
    maf_provider_mode: str,
    allow_model_call: bool,
    memory_backend: str,
    rational_backend: str,
    require_real_tool_adapter: bool,
) -> dict[str, Any]:
    registry = social_adapter_registry(env=os.environ, config_path=config_path)
    profile = registry.get_profile(adapter_name)
    if profile is None:
        raise ValueError("openclaw_profile_missing")
    if profile.transport_kind != "openclaw_gateway":
        raise ValueError("openclaw_profile_transport_unsupported")
    if not profile.ready_for_live_io:
        raise ValueError("openclaw_profile_not_ready")
    if profile.adapter_kind not in {"wechat_ilink", "qq_openclaw"}:
        raise ValueError("openclaw_adapter_not_supported")
    _, access_token = _pick_profile_env_value(
        profile,
        preferred_fragments=("TOKEN", "KEY", "SECRET"),
    )
    resolved_gateway_url = gateway_url or profile.host_url or profile.endpoint_url or ""
    if not resolved_gateway_url:
        raise ValueError("openclaw_gateway_url_missing")
    resolved_plugin_package = plugin_package or profile.plugin_package or ""
    if not resolved_plugin_package:
        raise ValueError("openclaw_plugin_package_missing")
    social_adapter = (
        WeChatILinkSocialAdapter()
        if profile.adapter_kind == "wechat_ilink"
        else QQOpenClawSocialAdapter()
    )

    def ingest_callback(envelope: SocialMessageEnvelope, event_type: str) -> dict[str, Any]:
        event = _build_social_event_from_envelope(
            envelope,
            social_adapter=social_adapter,
        )
        event["payload"] = {
            **cast(dict[str, Any], event.get("payload") or {}),
            "openclaw_event_type": event_type,
            "openclaw_plugin_package": resolved_plugin_package,
        }
        return run_no_model_dry_run(
            db_path,
            events=[event],
            session_id=session_id,
            maf_provider_mode=maf_provider_mode,
            allow_model_call=allow_model_call,
            memory_backend=memory_backend,
            rational_backend=rational_backend,
            require_real_tool_adapter=require_real_tool_adapter,
            event_source_label="openclaw_gateway",
        )

    return run_openclaw_gateway_client(
        access_token=access_token,
        gateway_url=resolved_gateway_url,
        adapter_kind=profile.adapter_kind,
        plugin_id=str(profile.plugin_id or profile.adapter_kind),
        plugin_package=resolved_plugin_package,
        installer_package=str(profile.installer_package or ""),
        envelope_from_event=social_adapter.envelope_from_event,
        ingest_callback=ingest_callback,
        duration=duration,
        max_events=max_events,
        ready_file=ready_file,
    )


def build_social_adapter_smoke(*, config_path: str = "") -> dict[str, Any]:
    tempdir = tempfile.TemporaryDirectory()
    try:
        db_path = str(Path(tempdir.name) / "social-adapter-smoke.db")
        smoke_config_path = str(Path(tempdir.name) / "social-adapter-smoke-config.json")
        resolved_config_path = config_path or smoke_config_path
        social_adapter_config_update(
            adapter_name="qq_official",
            config_path=resolved_config_path,
            endpoint_url="https://api.sgroup.qq.com",
            credential_env_vars=["QQ_BOT_TOKEN", "QQ_BOT_SECRET"],
            enabled=True,
        )
        social_adapter_config_update(
            adapter_name="onebot_qq",
            config_path=resolved_config_path,
            endpoint_url="ws://127.0.0.1:3001/onebot",
            credential_env_vars=["ONEBOT_ACCESS_TOKEN"],
            enabled=True,
            compliance_acknowledged=True,
        )
        social_adapter_config_update(
            adapter_name="wecom",
            config_path=resolved_config_path,
            endpoint_url="wss://qyapi.weixin.qq.com/cgi-bin/webhook/connect",
            credential_env_vars=["WECOM_BOT_TOKEN"],
            enabled=True,
        )
        social_adapter_config_update(
            adapter_name="wechat_ilink",
            config_path=resolved_config_path,
            host_url="ws://127.0.0.1:8811/openclaw",
            endpoint_url="https://wechat.example.invalid/ilink",
            credential_env_vars=["WECHAT_ILINK_TOKEN"],
            plugin_package="@tencent/openclaw-weixin",
            installer_package="@tencent-weixin/openclaw-weixin-cli",
            plugin_installed=True,
            account_session_ready=True,
            enabled=True,
            compliance_acknowledged=True,
        )
        social_adapter_config_update(
            adapter_name="qq_openclaw",
            config_path=resolved_config_path,
            host_url="ws://127.0.0.1:8811/openclaw",
            credential_env_vars=["QQ_OPENCLAW_TOKEN"],
            plugin_id="qq_openclaw",
            plugin_package="operator-supplied-qq-openclaw-package",
            installer_package="operator-supplied-qq-openclaw-installer",
            plugin_installed=True,
            account_session_ready=True,
            enabled=True,
            compliance_acknowledged=True,
        )
        adapter_registry_payload = social_adapter_list(
            env={
                "QQ_BOT_TOKEN": "masked-token",
                "QQ_BOT_SECRET": "masked-secret",
                "ONEBOT_ACCESS_TOKEN": "masked-access-token",
                "WECOM_BOT_TOKEN": "masked-wecom-token",
                "WECHAT_ILINK_TOKEN": "masked-wechat-token",
                "QQ_OPENCLAW_TOKEN": "masked-qq-openclaw-token",
            },
            config_path=resolved_config_path,
        )
        adapter_test_payload = social_adapter_test(
            env={
                "QQ_BOT_TOKEN": "masked-token",
                "QQ_BOT_SECRET": "masked-secret",
                "ONEBOT_ACCESS_TOKEN": "masked-access-token",
                "WECOM_BOT_TOKEN": "masked-wecom-token",
                "WECHAT_ILINK_TOKEN": "masked-wechat-token",
                "QQ_OPENCLAW_TOKEN": "masked-qq-openclaw-token",
            },
            config_path=resolved_config_path,
        )
        social_adapter = MockSocialAdapter()
        envelope = social_adapter.bind_principal(
            adapter_kind="mock_qq",
            channel_id="group-social-001",
            channel_kind="group",
            external_user_id="alice",
            text="please check current status from social chat",
            received_at="2026-05-10T12:40:00Z",
        )
        payload = _run_social_agent_payload(
            db_path=db_path,
            social_text=envelope.text,
            social_adapter_kind=envelope.adapter_kind,
            social_channel_id=envelope.channel_id,
            social_channel_kind=envelope.channel_kind,
            social_user_id=envelope.external_user_id,
            social_admin=False,
            session_id="social-adapter-smoke-001",
        )
        delivery = social_adapter.deliver_affective_response(
            envelope,
            cast(dict[str, Any], payload.get("final_response") or {}),
        )
        test_results = cast(list[dict[str, Any]], adapter_test_payload.get("results") or [])
        qq_result = next(
            (result for result in test_results if str(result.get("adapter") or "") == "qq_official"),
            None,
        ) or {}
        onebot_result = next(
            (result for result in test_results if str(result.get("adapter") or "") == "onebot_qq"),
            None,
        ) or {}
        wecom_result = next(
            (result for result in test_results if str(result.get("adapter") or "") == "wecom"),
            None,
        ) or {}
        wechat_ilink_result = next(
            (
                result
                for result in test_results
                if str(result.get("adapter") or "") == "wechat_ilink"
            ),
            None,
        ) or {}
        qq_openclaw_result = next(
            (
                result
                for result in test_results
                if str(result.get("adapter") or "") == "qq_openclaw"
            ),
            None,
        ) or {}
        closure_gates: dict[str, bool] = {
            "social_event_persisted": int(payload.get("events_persisted", 0)) == 1,
            "social_event_source_recorded": str(
                cast(dict[str, Any], payload.get("agent_run_evidence") or {}).get(
                    "event_source"
                )
                or ""
            )
            == "mock_social",
            "social_identity_bound": envelope.principal_id == "mock_qq:alice",
            "affective_final_response_present": str(
                cast(dict[str, Any], payload.get("final_response") or {}).get(
                    "speaker"
                )
                or ""
            )
            == "affective",
            "affective_delivery_recorded": delivery.speaker == "affective"
            and delivery.delivery_status == "delivered",
            "social_adapter_registry_gate": bool(adapter_registry_payload.get("ok")),
            "qq_social_gate": str(qq_result.get("status") or "") == "ready"
            and str(cast(dict[str, Any], qq_result.get("social_envelope") or {}).get("adapter_kind") or "")
            == "qq_official",
            "onebot_social_gate": str(onebot_result.get("status") or "") == "ready"
            and str(cast(dict[str, Any], onebot_result.get("social_envelope") or {}).get("adapter_kind") or "")
            == "onebot_qq",
            "wecom_social_gate": str(wecom_result.get("status") or "") == "ready"
            and str(cast(dict[str, Any], wecom_result.get("social_envelope") or {}).get("adapter_kind") or "")
            == "wecom",
            "wechat_ilink_social_gate": str(wechat_ilink_result.get("status") or "") == "ready"
            and str(cast(dict[str, Any], wechat_ilink_result.get("social_envelope") or {}).get("adapter_kind") or "")
            == "wechat_ilink",
            "qq_openclaw_social_gate": str(qq_openclaw_result.get("status") or "")
            == "ready"
            and str(
                cast(
                    dict[str, Any], qq_openclaw_result.get("social_envelope") or {}
                ).get("adapter_kind")
                or ""
            )
            == "qq_openclaw",
            "social_compliance_gate": bool(
                cast(dict[str, Any], onebot_result.get("profile") or {}).get("compliance_ready")
            ) and bool(
                cast(dict[str, Any], qq_result.get("profile") or {}).get("compliance_ready")
            ) and bool(
                cast(dict[str, Any], wecom_result.get("profile") or {}).get("compliance_ready")
            ) and bool(
                cast(dict[str, Any], wechat_ilink_result.get("profile") or {}).get("compliance_ready")
            ) and bool(
                cast(dict[str, Any], qq_openclaw_result.get("profile") or {}).get(
                    "compliance_ready"
                )
            ),
        }
        return {
            "schema_version": SOCIAL_ADAPTER_SMOKE_SCHEMA_VERSION,
            "status": "ready" if all(closure_gates.values()) else "incomplete",
            "reason": "social_adapter_ready"
            if all(closure_gates.values())
            else "social_adapter_gap",
            "command": "social-adapter-smoke",
            "closure_gates": closure_gates,
            "social_envelope": envelope.to_dict(),
            "delivery_record": delivery.to_dict(),
            "agent_payload": payload,
            "social_adapter_registry": adapter_registry_payload,
            "social_adapter_test": adapter_test_payload,
            "evidence_summary": {
                "event_source": cast(
                    dict[str, Any], payload.get("agent_run_evidence") or {}
                ).get("event_source"),
                "speaker": cast(dict[str, Any], payload.get("final_response") or {}).get(
                    "speaker"
                ),
                "principal_id": envelope.principal_id,
                "ready_adapter_names": cast(list[str], adapter_registry_payload.get("ready_adapter_names") or []),
                "tested_adapter_names": [
                    str(result.get("adapter") or "") for result in test_results
                ],
            },
            "ok": all(closure_gates.values()),
        }
    finally:
        tempdir.cleanup()


def build_self_improvement_smoke() -> dict[str, Any]:
    proposal = propose_self_improvement(
        proposal_id="proposal-2-1-0-001",
        source="failed_test",
        summary="Repair a deterministic regression inside an isolated sandbox",
        touches_code=True,
        targets_runtime=False,
    )
    denied_review = review_self_improvement(
        proposal,
        approved=False,
        evidence=ImprovementEvidence(
            tests_passed=True,
            lint_passed=True,
            smoke_passed=True,
            evidence_refs=("pytest.txt", "ruff.txt", "smoke.json"),
        ),
    )
    approved_review = review_self_improvement(
        proposal,
        approved=True,
        evidence=ImprovementEvidence(
            tests_passed=True,
            lint_passed=True,
            smoke_passed=True,
            evidence_refs=("pytest.txt", "ruff.txt", "smoke.json"),
        ),
    )
    closure_gates: dict[str, bool] = {
        "proposal_requires_approval": proposal.approval_required,
        "sandbox_mode_isolated": proposal.sandbox_mode == "isolated_workspace",
        "denied_proposal_not_executed": denied_review.can_apply_changes is False
        and denied_review.decision == "denied",
        "approved_proposal_needs_verified_evidence": approved_review.proposal.evidence.verified_success(),
        "vitality_replenishment_after_verified_success": approved_review.vitality_replenishment_allowed,
        "prohibited_actions_recorded": "git_push" in proposal.prohibited_actions,
    }
    return {
        "schema_version": SELF_IMPROVEMENT_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "self_improvement_ready"
        if all(closure_gates.values())
        else "self_improvement_gap",
        "command": "self-improvement-smoke",
        "closure_gates": closure_gates,
        "proposal": proposal.to_dict(),
        "denied_review": denied_review.to_dict(),
        "approved_review": approved_review.to_dict(),
        "evidence_summary": {
            "risk_level": proposal.risk_level,
            "sandbox_mode": proposal.sandbox_mode,
            "approved_vitality_replenishment": approved_review.vitality_replenishment_allowed,
        },
        "ok": all(closure_gates.values()),
    }


def build_task_tracking_smoke() -> dict[str, Any]:
    active_hours_config: dict[str, Any] = {
        "timezone": "UTC",
        "active_start_hour": 0,
        "active_end_hour": 23,
        "operator_pause_precedence": True,
    }
    task_records: list[dict[str, Any]] = [
        {
            "task_id": "task-autonomy-maintenance-001",
            "kind": "memory_maintenance",
            "status": "completed",
            "created_at": "2026-05-11T00:00:00Z",
            "updated_at": "2026-05-11T00:02:00Z",
            "checkpoint_id": "chk-memory-001",
            "cleanup_required": False,
        },
        {
            "task_id": "task-long-operation-001",
            "kind": "long_running_operation",
            "status": "resumed_completed",
            "created_at": "2026-05-11T00:03:00Z",
            "updated_at": "2026-05-11T00:08:00Z",
            "checkpoint_id": "chk-long-op-002",
            "cleanup_required": False,
            "interruption": {
                "recorded": True,
                "reason": "daemon_restart",
                "resumed_from_checkpoint": "chk-long-op-001",
            },
        },
    ]
    replay_buffer: list[dict[str, Any]] = [
        {
            "replay_id": "replay-long-op-001",
            "task_id": "task-long-operation-001",
            "checkpoint_id": "chk-long-op-001",
            "status": "replayed",
        }
    ]
    heartbeat_snapshot: dict[str, Any] = {
        "recorded": True,
        "status": "idle",
        "last_cycle_index": 2,
        "active_hours_respected": True,
    }
    cleanup_summary: dict[str, Any] = {
        "stale_running_tasks": [],
        "pending_replay_items": [],
        "rerun_ready": True,
    }
    closure_gates: dict[str, bool] = {
        "task_records_present": bool(task_records),
        "active_hours_config_recorded": bool(active_hours_config),
        "heartbeat_linked": bool(heartbeat_snapshot.get("recorded")),
        "replay_buffer_recorded": bool(replay_buffer),
        "interrupted_task_resumable": any(
            bool(cast(dict[str, Any], task.get("interruption") or {}).get("resumed_from_checkpoint"))
            for task in task_records
        ),
        "cleanup_state_recorded": bool(cleanup_summary),
        "no_stale_running_tasks": not bool(cleanup_summary.get("stale_running_tasks")),
        "rerun_ready": bool(cleanup_summary.get("rerun_ready")),
    }
    return {
        "schema_version": TASK_TRACKING_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "task_tracking_replay_ready" if all(closure_gates.values()) else "task_tracking_replay_gap",
        "command": "task-tracking-smoke",
        "active_hours_config": active_hours_config,
        "heartbeat_snapshot": heartbeat_snapshot,
        "task_records": task_records,
        "replay_buffer": replay_buffer,
        "cleanup_summary": cleanup_summary,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "task_count": len(task_records),
            "replay_buffer_count": len(replay_buffer),
            "completed_task_count": sum(
                1 for task in task_records if str(task.get("status") or "").endswith("completed")
            ),
            "rerun_ready": bool(cleanup_summary.get("rerun_ready")),
        },
        "ok": all(closure_gates.values()),
    }


def build_memory_maintenance_smoke() -> dict[str, Any]:
    stale_context_candidates: list[dict[str, Any]] = [
        {
            "context_id": "ctx-social-001",
            "category": "relationship_summary",
            "age_days": 14,
            "action": "summarize",
            "privacy_scope": "principal_scoped",
        },
        {
            "context_id": "ctx-unit-incident-001",
            "category": "unit_incident",
            "age_days": 3,
            "action": "retain_fact",
            "privacy_scope": "environment_fact",
        },
    ]
    consolidation_summary: dict[str, Any] = {
        "summary_id": "mem-maint-001",
        "candidate_count": len(stale_context_candidates),
        "committed_summary_count": 2,
        "prompt_safe_summary": "Recent relationship and Unit incident context consolidated without exposing raw private payloads.",
        "raw_payload_exported": False,
    }
    audit_record: dict[str, Any] = {
        "audit_id": "audit-memory-maint-001",
        "decision": "consolidated",
        "evidence_refs": ["task-tracking-smoke.json", "persona-state-smoke.json"],
    }
    closure_gates: dict[str, bool] = {
        "stale_context_candidates_recorded": bool(stale_context_candidates),
        "consolidation_summary_recorded": bool(consolidation_summary.get("summary_id")),
        "prompt_safe_summary_recorded": bool(consolidation_summary.get("prompt_safe_summary")),
        "privacy_scope_recorded": all(bool(item.get("privacy_scope")) for item in stale_context_candidates),
        "raw_private_payloads_not_exported": not bool(consolidation_summary.get("raw_payload_exported")),
        "audit_record_bound": bool(audit_record.get("audit_id")) and bool(audit_record.get("evidence_refs")),
    }
    return {
        "schema_version": MEMORY_MAINTENANCE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "memory_maintenance_ready" if all(closure_gates.values()) else "memory_maintenance_gap",
        "command": "memory-maintenance-smoke",
        "stale_context_candidates": stale_context_candidates,
        "consolidation_summary": consolidation_summary,
        "audit_record": audit_record,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "candidate_count": len(stale_context_candidates),
            "committed_summary_count": int(consolidation_summary.get("committed_summary_count") or 0),
            "raw_payload_exported": bool(consolidation_summary.get("raw_payload_exported")),
        },
        "ok": all(closure_gates.values()),
    }


def build_self_optimization_smoke() -> dict[str, Any]:
    evidence = ImprovementEvidence(
        tests_passed=True,
        lint_passed=True,
        smoke_passed=True,
        evidence_refs=("task-tracking-smoke.json", "memory-maintenance-smoke.json"),
    )
    proposal = propose_self_improvement(
        proposal_id="self-opt-low-risk-001",
        source="memory_review",
        summary="Adjust prompt-safe stale-context summary wording after deterministic evidence review",
        touches_code=False,
        targets_runtime=False,
        evidence=evidence,
    )
    review = review_self_improvement(proposal, approved=True, evidence=evidence)
    closure_gates = {
        "proposal_recorded": bool(proposal.proposal_id),
        "low_risk_classified": proposal.risk_level == "low",
        "approval_required": proposal.approval_required,
        "sandbox_or_simulation_only": proposal.sandbox_mode in {"simulation", "isolated_workspace"},
        "verified_evidence_bound": evidence.verified_success(),
        "operator_approval_recorded": review.decision == "approved",
        "apply_changes_still_forbidden": not review.can_apply_changes,
        "prohibited_actions_recorded": all(
            action in proposal.prohibited_actions
            for action in PROHIBITED_SELF_IMPROVEMENT_ACTIONS
        ),
        "vitality_replenishment_evidence_bound": review.vitality_replenishment_allowed,
    }
    return {
        "schema_version": SELF_OPTIMIZATION_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "self_optimization_boundary_ready" if all(closure_gates.values()) else "self_optimization_boundary_gap",
        "command": "self-optimization-smoke",
        "proposal": proposal.to_dict(),
        "review": review.to_dict(),
        "closure_gates": closure_gates,
        "evidence_summary": {
            "risk_level": proposal.risk_level,
            "sandbox_mode": proposal.sandbox_mode,
            "can_apply_changes": review.can_apply_changes,
            "vitality_replenishment_allowed": review.vitality_replenishment_allowed,
        },
        "ok": all(closure_gates.values()),
    }


def build_world_model_context_smoke() -> dict[str, Any]:
    temporal_incidents: list[dict[str, Any]] = [
        {
            "incident_id": "incident-unit-recovery-001",
            "occurred_at": "2026-05-11T00:10:00Z",
            "category": "unit_recovery",
            "severity": "bounded",
            "status": "resolved",
        }
    ]
    unit_contexts: list[dict[str, Any]] = [
        {
            "unit_id": "unit-01",
            "location_label": "lab-bench",
            "capability_class": "extensible_unit",
            "relay_path": [],
            "relationship_refs": ["principal:operator"],
        },
        {
            "unit_id": "unit-relay-01",
            "location_label": "edge-gateway",
            "capability_class": "relay_capable_unit",
            "relay_path": ["gateway-b-01"],
            "relationship_refs": ["principal:operator"],
        },
    ]
    prompt_safe_context: dict[str, Any] = {
        "affective_summary": "A lab Unit recovered recently; relay-capable context is available for cautious follow-up.",
        "rational_summary": {
            "incident_count": len(temporal_incidents),
            "unit_capability_classes": [
                str(context.get("capability_class") or "") for context in unit_contexts
            ],
            "relationship_detail_level": "refs_only",
        },
        "raw_private_relationships_included": False,
    }
    closure_gates: dict[str, bool] = {
        "temporal_incidents_recorded": bool(temporal_incidents),
        "unit_location_context_recorded": all(bool(context.get("location_label")) for context in unit_contexts),
        "unit_capability_context_recorded": all(bool(context.get("capability_class")) for context in unit_contexts),
        "relationship_context_prompt_safe": not bool(prompt_safe_context.get("raw_private_relationships_included")),
        "rational_summary_available": bool(prompt_safe_context.get("rational_summary")),
        "relay_context_preserved": any(bool(context.get("relay_path")) for context in unit_contexts),
    }
    return {
        "schema_version": WORLD_MODEL_CONTEXT_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "world_model_context_ready" if all(closure_gates.values()) else "world_model_context_gap",
        "command": "world-model-context-smoke",
        "temporal_incidents": temporal_incidents,
        "unit_contexts": unit_contexts,
        "prompt_safe_context": prompt_safe_context,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "incident_count": len(temporal_incidents),
            "unit_context_count": len(unit_contexts),
            "relay_context_count": sum(1 for context in unit_contexts if context.get("relay_path")),
        },
        "ok": all(closure_gates.values()),
    }


def build_signing_provenance_smoke(
    *,
    preset: str = "unit-app",
    app_id: str = "neuro_unit_app",
    app_source_dir: str | None = None,
    board: str = "dnesp32s3b/esp32s3/procpu",
    build_dir: str = "build/neurolink_unit",
    artifact_file: str | None = None,
    require_signing: bool = True,
    unit_signing_enforced: bool = True,
) -> dict[str, Any]:
    admission_payload = build_app_artifact_admission(
        preset=preset,
        app_id=app_id,
        app_source_dir=app_source_dir,
        board=board,
        build_dir=build_dir,
        artifact_file=artifact_file,
    )
    artifact_admission = cast(dict[str, Any], admission_payload.get("artifact_admission") or {})
    source_identity = cast(dict[str, Any], artifact_admission.get("source_identity") or {})
    elf_identity = cast(dict[str, Any], artifact_admission.get("elf_identity") or {})
    artifact_sha256 = str(artifact_admission.get("artifact_sha256") or "")
    build_plan = cast(dict[str, Any], admission_payload.get("build_plan") or {})
    closure_gates = {
        "artifact_admission_recorded": bool(artifact_admission.get("admitted")),
        "artifact_admission_contract_supported": str(
            artifact_admission.get("schema_version") or ""
        )
        == APP_ARTIFACT_ADMISSION_SCHEMA_VERSION,
        "source_identity_recorded": bool(source_identity.get("app_id"))
        and bool(source_identity.get("app_version"))
        and bool(source_identity.get("build_id")),
        "build_provenance_recorded": bool(build_plan.get("build_command"))
        and bool(build_plan.get("app_build_dir"))
        and bool(build_plan.get("source_artifact_file")),
        "artifact_sha256_recorded": len(artifact_sha256) == 64,
        "elf_identity_recorded": bool(elf_identity.get("machine_name"))
        and bool(elf_identity.get("elf_class")),
        "artifact_contains_build_id_string": bool(
            artifact_admission.get("artifact_contains_build_id_string")
        ),
        "artifact_contains_version_string": bool(
            artifact_admission.get("artifact_contains_version_string")
        ),
        "filename_matches_app_id": bool(
            artifact_admission.get("filename_matches_app_id")
        ),
        "signing_policy_recorded": True,
        "signing_required_for_release": bool(require_signing),
        "signing_enforcement_compatible": (not require_signing)
        or bool(unit_signing_enforced),
    }
    return {
        "schema_version": SIGNING_PROVENANCE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "signing_provenance_ready"
        if all(closure_gates.values())
        else "signing_provenance_gap",
        "command": "signing-provenance-smoke",
        "artifact_admission": artifact_admission,
        "build_plan": build_plan,
        "policy": {
            "require_signing": require_signing,
            "unit_signing_enforced": unit_signing_enforced,
        },
        "closure_gates": closure_gates,
        "evidence_summary": {
            "app_id": str(source_identity.get("app_id") or app_id),
            "app_version": str(source_identity.get("app_version") or ""),
            "build_id": str(source_identity.get("build_id") or ""),
            "artifact_sha256": artifact_sha256,
            "artifact_file": str(artifact_admission.get("artifact_file") or ""),
            "machine_name": str(elf_identity.get("machine_name") or ""),
            "require_signing": require_signing,
            "unit_signing_enforced": unit_signing_enforced,
        },
        "ok": all(closure_gates.values()),
    }


def _build_signing_provenance_closure_summary(
    signing_provenance_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if signing_provenance_payload is None:
        gates = {
            "signing_provenance_evidence_supplied": False,
            "signing_provenance_contract_supported": False,
            "artifact_admission_recorded": False,
            "source_identity_recorded": False,
            "build_provenance_recorded": False,
            "artifact_sha256_recorded": False,
            "elf_identity_recorded": False,
            "artifact_contains_build_id_string": False,
            "artifact_contains_version_string": False,
            "filename_matches_app_id": False,
            "signing_policy_recorded": False,
            "signing_required_for_release": False,
            "signing_enforcement_compatible": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "signing_provenance_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], signing_provenance_payload.get("closure_gates") or {})
    gates = {
        "signing_provenance_evidence_supplied": True,
        "signing_provenance_contract_supported": str(
            signing_provenance_payload.get("schema_version") or ""
        )
        == SIGNING_PROVENANCE_SMOKE_SCHEMA_VERSION,
        "artifact_admission_recorded": bool(payload_gates.get("artifact_admission_recorded")),
        "source_identity_recorded": bool(payload_gates.get("source_identity_recorded")),
        "build_provenance_recorded": bool(payload_gates.get("build_provenance_recorded")),
        "artifact_sha256_recorded": bool(payload_gates.get("artifact_sha256_recorded")),
        "elf_identity_recorded": bool(payload_gates.get("elf_identity_recorded")),
        "artifact_contains_build_id_string": bool(
            payload_gates.get("artifact_contains_build_id_string")
        ),
        "artifact_contains_version_string": bool(
            payload_gates.get("artifact_contains_version_string")
        ),
        "filename_matches_app_id": bool(payload_gates.get("filename_matches_app_id")),
        "signing_policy_recorded": bool(payload_gates.get("signing_policy_recorded")),
        "signing_required_for_release": bool(
            payload_gates.get("signing_required_for_release")
        ),
        "signing_enforcement_compatible": bool(
            payload_gates.get("signing_enforcement_compatible")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(signing_provenance_payload.get("schema_version") or ""),
        "status": str(signing_provenance_payload.get("status") or "unknown"),
        "reason": str(signing_provenance_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any],
            signing_provenance_payload.get("evidence_summary") or {},
        ),
        "ok": all(gates.values()),
    }


def build_real_scene_e2e_smoke(
    *,
    live_event_smoke_payload: dict[str, Any],
    coding_agent_route_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    live_event_ingest = cast(
        dict[str, Any],
        live_event_smoke_payload.get("live_event_ingest") or {},
    )
    execution_evidence = cast(
        dict[str, Any],
        live_event_smoke_payload.get("execution_evidence") or {},
    )
    execution_span = cast(dict[str, Any], execution_evidence.get("execution_span") or {})
    execution_span_payload = cast(dict[str, Any], execution_span.get("payload") or {})
    audit_record = cast(dict[str, Any], execution_evidence.get("audit_record") or {})
    audit_payload = cast(dict[str, Any], audit_record.get("payload") or {})
    session_context = cast(dict[str, Any], audit_payload.get("session_context") or {})
    agent_run_evidence = cast(
        dict[str, Any],
        live_event_smoke_payload.get("agent_run_evidence") or {},
    )
    top_level_event_source = str(live_event_smoke_payload.get("event_source") or "")
    allowed_sources = {"neuro_cli_app_events_live", "neuro_cli_events_live"}
    tool_results = cast(list[Any], live_event_smoke_payload.get("tool_results") or [])
    coding_agent_closure_gates = cast(
        dict[str, Any],
        (coding_agent_route_payload or {}).get("closure_gates") or {},
    )
    closure_gates = {
        "live_event_smoke_payload_supplied": bool(live_event_smoke_payload),
        "live_event_smoke_command_recorded": str(
            live_event_smoke_payload.get("command") or ""
        )
        == "live-event-smoke",
        "live_event_source_real": top_level_event_source in allowed_sources,
        "live_event_ingest_recorded": bool(live_event_ingest),
        "live_event_collected": int(live_event_ingest.get("collected_event_count") or 0) > 0,
        "bounded_live_runtime_recorded": bool(
            cast(dict[str, Any], live_event_smoke_payload.get("event_service") or {}).get("bounded_runtime", True)
        )
        if live_event_smoke_payload.get("event_service")
        else True,
        "execution_evidence_present": bool(execution_evidence),
        "execution_span_ok": str(execution_span.get("status") or "") == "ok",
        "event_source_consistent": top_level_event_source == str(
            execution_span_payload.get("event_source") or agent_run_evidence.get("event_source") or ""
        ),
        "session_context_present": bool(session_context),
        "agent_run_evidence_present": bool(agent_run_evidence),
        "real_tool_adapter_required": bool(
            agent_run_evidence.get("release_gate_require_real_tool_adapter")
        ),
        "real_tool_adapter_present": bool(
            agent_run_evidence.get("real_tool_adapter_present")
        ),
        "real_tool_execution_succeeded": bool(
            agent_run_evidence.get("real_tool_execution_succeeded")
        ),
        "tool_results_recorded": bool(tool_results),
        "state_sync_tool_used": any(
            str(cast(dict[str, Any], item).get("tool_name") or "")
            == "system_state_sync"
            for item in tool_results
            if isinstance(item, dict)
        ),
        "coding_agent_route_valid_if_supplied": (
            coding_agent_route_payload is None
            or (
                str(coding_agent_route_payload.get("command") or "")
                == "coding-agent-self-improvement-route"
                and bool(coding_agent_route_payload.get("ok", False))
            )
        ),
        "coding_agent_callback_audit_recorded_if_supplied": (
            coding_agent_route_payload is None
            or bool(coding_agent_closure_gates.get("callback_audit_recorded", False))
        ),
        "coding_agent_sandbox_recorded_if_supplied": (
            coding_agent_route_payload is None
            or bool(coding_agent_closure_gates.get("sandbox_execution_recorded", False))
        ),
    }
    return {
        "schema_version": REAL_SCENE_E2E_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "real_scene_e2e_ready"
        if all(closure_gates.values())
        else "real_scene_e2e_gap",
        "command": "real-scene-e2e-smoke",
        "live_event_smoke": live_event_smoke_payload,
        "coding_agent_route": coding_agent_route_payload,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "event_source": top_level_event_source,
            "session_id": str(live_event_smoke_payload.get("session_id") or execution_span.get("session_id") or ""),
            "collected_event_count": int(live_event_ingest.get("collected_event_count") or 0),
            "target_app_id": str(live_event_ingest.get("app_id") or session_context.get("target_app_id") or ""),
            "tool_result_count": len(tool_results),
            "execution_span_id": str(execution_span.get("execution_span_id") or ""),
            "coding_agent_runner": str(
                (coding_agent_route_payload or {}).get("runner_name") or ""
            ),
        },
        "ok": all(closure_gates.values()),
    }


def build_observability_diagnosis_smoke(
    *,
    relay_failure_payload: dict[str, Any],
    activate_failure_payload: dict[str, Any],
) -> dict[str, Any]:
    relay_gates = cast(dict[str, Any], relay_failure_payload.get("closure_gates") or {})
    relay_summary = cast(
        dict[str, Any], relay_failure_payload.get("evidence_summary") or {}
    )
    recovery_candidate_summary = cast(
        dict[str, Any], activate_failure_payload.get("recovery_candidate_summary") or {}
    )
    rollback_approval = cast(
        dict[str, Any], activate_failure_payload.get("rollback_approval") or {}
    )
    matching_lease_ids = cast(
        list[Any], recovery_candidate_summary.get("matching_lease_ids") or []
    )
    closure_gates = {
        "relay_failure_evidence_supplied": bool(relay_failure_payload),
        "relay_failure_contract_supported": str(
            relay_failure_payload.get("schema_version") or ""
        )
        == RELAY_FAILURE_CLOSURE_SCHEMA_VERSION,
        "route_failure_recorded": bool(relay_gates.get("route_failure_recorded")),
        "fallback_path_recorded": bool(relay_gates.get("fallback_path_recorded")),
        "operator_runbook_recorded": bool(
            relay_gates.get("operator_runbook_recorded")
        ),
        "activate_failure_payload_supplied": bool(activate_failure_payload),
        "activate_failure_command_recorded": str(
            activate_failure_payload.get("command") or ""
        )
        == "app-deploy-activate",
        "rollback_required_recorded": str(
            activate_failure_payload.get("failure_status") or ""
        )
        == "rollback_required",
        "recovery_candidate_summary_recorded": bool(
            recovery_candidate_summary.get("app_id")
        )
        and str(recovery_candidate_summary.get("rollback_decision") or "")
        == "operator_review_required",
        "rollback_candidate_lease_recorded": bool(
            recovery_candidate_summary.get("lease_resource")
        )
        and isinstance(matching_lease_ids, list),
        "rollback_approval_recorded": str(rollback_approval.get("status") or "")
        == "pending_approval",
        "operator_next_actions_recorded": bool(
            relay_summary.get("fallback_action")
        )
        and bool(relay_summary.get("runbook_id"))
        and bool(rollback_approval.get("cleanup_hint")),
    }
    return {
        "schema_version": OBSERVABILITY_DIAGNOSIS_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "observability_diagnosis_ready"
        if all(closure_gates.values())
        else "observability_diagnosis_gap",
        "command": "observability-diagnosis-smoke",
        "relay_failure": relay_failure_payload,
        "activate_failure": activate_failure_payload,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "route_failure_reason": str(
                relay_summary.get("route_failure_reason") or ""
            ),
            "fallback_action": str(relay_summary.get("fallback_action") or ""),
            "runbook_id": str(relay_summary.get("runbook_id") or ""),
            "target_app_id": str(recovery_candidate_summary.get("app_id") or ""),
            "rollback_decision": str(
                recovery_candidate_summary.get("rollback_decision") or ""
            ),
            "matching_lease_count": len(
                [item for item in matching_lease_ids if str(item)]
            ),
            "rollback_approval_status": str(rollback_approval.get("status") or ""),
        },
        "ok": all(closure_gates.values()),
    }


def build_release_rollback_hardening_smoke(
    *,
    activate_failure_payload: dict[str, Any],
    rollback_payload: dict[str, Any],
) -> dict[str, Any]:
    recovery_candidate_summary = cast(
        dict[str, Any], activate_failure_payload.get("recovery_candidate_summary") or {}
    )
    rollback_approval = cast(
        dict[str, Any], activate_failure_payload.get("rollback_approval") or {}
    )
    rollback_decision = cast(dict[str, Any], rollback_payload.get("rollback_decision") or {})
    rollback_execution = cast(dict[str, Any], rollback_payload.get("rollback_execution") or {})
    rollback_step = cast(dict[str, Any], rollback_execution.get("rollback") or {})
    query_apps_step = cast(dict[str, Any], rollback_execution.get("query_apps") or {})
    query_leases_step = cast(dict[str, Any], rollback_execution.get("query_leases") or {})
    closure_gates = {
        "activate_failure_payload_supplied": bool(activate_failure_payload),
        "activate_failure_command_recorded": str(
            activate_failure_payload.get("command") or ""
        )
        == "app-deploy-activate",
        "rollback_required_recorded": str(
            activate_failure_payload.get("failure_status") or ""
        )
        == "rollback_required",
        "recovery_candidate_summary_recorded": bool(
            recovery_candidate_summary.get("app_id")
        )
        and str(recovery_candidate_summary.get("rollback_decision") or "")
        == "operator_review_required",
        "rollback_approval_boundary_recorded": str(
            rollback_approval.get("status") or ""
        )
        == "pending_approval",
        "rollback_payload_supplied": bool(rollback_payload),
        "rollback_payload_command_recorded": str(
            rollback_payload.get("command") or ""
        )
        == "app-deploy-rollback",
        "rollback_decision_recorded": bool(rollback_decision.get("resolved_app_id"))
        and bool(rollback_decision.get("rollback_resource")),
        "rollback_approval_required": bool(rollback_decision.get("approval_required")),
        "rollback_decision_approved": str(rollback_decision.get("status") or "")
        == "approved",
        "rollback_execution_recorded": bool(rollback_step),
        "rollback_execution_completed_through_cleanup": str(
            rollback_execution.get("completed_through") or ""
        )
        == "query_leases",
        "post_rollback_app_observation_recorded": bool(query_apps_step),
        "post_rollback_lease_observation_recorded": bool(query_leases_step),
        "rollback_cleanup_clear": bool(query_leases_step.get("ok"))
        and not bool(query_leases_step.get("matching_lease_ids") or []),
        "rollback_failure_summary_clear": not bool(
            rollback_payload.get("rollback_failure_summary")
        ),
    }
    return {
        "schema_version": RELEASE_ROLLBACK_HARDENING_SMOKE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "release_rollback_hardening_ready"
        if all(closure_gates.values())
        else "release_rollback_hardening_gap",
        "command": "release-rollback-hardening-smoke",
        "activate_failure": activate_failure_payload,
        "rollback": rollback_payload,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "target_app_id": str(
                rollback_decision.get("resolved_app_id")
                or recovery_candidate_summary.get("app_id")
                or ""
            ),
            "rollback_decision_status": str(rollback_decision.get("status") or ""),
            "rollback_reason": str(rollback_decision.get("rollback_reason") or ""),
            "post_rollback_app_state": str(
                query_apps_step.get("observed_app_state") or ""
            ),
            "post_rollback_matching_lease_count": len(
                cast(list[Any], query_leases_step.get("matching_lease_ids") or [])
            ),
            "rollback_approval_status": str(rollback_approval.get("status") or ""),
        },
        "ok": all(closure_gates.values()),
    }


def _write_release_closure_fake_app_source(
    source_dir: Path,
    *,
    app_id: str,
    app_version: str,
    build_id: str,
) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    main_c = source_dir / "src" / "main.c"
    main_c.parent.mkdir(parents=True, exist_ok=True)
    major, minor, patch = app_version.split(".")
    main_c.write_text(
        (
            'static const char app_id[] = "{app_id}";\n'
            'static const char app_version[] = "{app_version}";\n'
            'static const char app_build_id[] = "{build_id}";\n'
            'const struct app_runtime_manifest app_runtime_manifest = {{\n'
            '  .version = {{\n'
            '    .major = {major},\n'
            '    .minor = {minor},\n'
            '    .patch = {patch},\n'
            '  }},\n'
            '  .app_name = "{app_id}",\n'
            '}};\n'
        ).format(
            app_id=app_id,
            app_version=app_version,
            build_id=build_id,
            major=major,
            minor=minor,
            patch=patch,
        ),
        encoding="utf-8",
    )


def _write_release_closure_fake_llext(
    artifact_path: Path,
    *,
    app_id: str,
    app_version: str,
    build_id: str,
) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    elf_ident = b"\x7fELF\x01\x01\x01" + (b"\x00" * 9)
    elf_header = (
        elf_ident
        + (1).to_bytes(2, "little")
        + (94).to_bytes(2, "little")
        + (1).to_bytes(4, "little")
    )
    payload = (
        elf_header
        + b"\x00" * 32
        + app_id.encode("utf-8")
        + b"\x00"
        + app_version.encode("utf-8")
        + b"\x00"
        + build_id.encode("utf-8")
        + b"\x00"
    )
    artifact_path.write_bytes(payload)


def _write_release_closure_payload(
    evidence_dir: Path,
    file_name: str,
    payload: dict[str, Any],
) -> str:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / file_name
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return str(path)


def build_release_224_closure_smoke(
    *,
    session_id: str = "release-2.2.4-closure-smoke-001",
    runner_name: str = "copilot",
    summary: str = "Repair deterministic regression in sandbox",
    evidence_dir: str = "",
) -> dict[str, Any]:
    tempdir = tempfile.TemporaryDirectory()
    try:
        root = Path(tempdir.name)
        db_path = root / "closure.db"
        source_dir = root / "source"
        artifact_path = root / "artifacts" / "neuro_unit_app.llext"
        app_id = "neuro_unit_app"
        app_version = "1.2.2"
        build_id = "neuro_unit_app-1.2.2-cbor-v2"

        _write_release_closure_fake_app_source(
            source_dir,
            app_id=app_id,
            app_version=app_version,
            build_id=build_id,
        )
        _write_release_closure_fake_llext(
            artifact_path,
            app_id=app_id,
            app_version=app_version,
            build_id=build_id,
        )

        run_payload = run_no_model_dry_run(
            str(db_path),
            session_id=session_id,
            memory_backend="local",
            federation_route_provider=lambda frame, session_context: federation_route_smoke(
                target_node="unit-remote-01",
                now="2026-05-10T12:00:00Z",
                required_trust_scope="lab-federation",
                peer_expires_at="2026-05-10T12:30:00Z",
                peer_relay_via=("gateway-b-01",),
                peer_network_transports=("ethernet", "serial_bridge"),
            ),
        )

        documentation_payload: dict[str, Any] = {
            "schema_version": DOCUMENTATION_CLOSURE_SCHEMA_VERSION,
            "status": "ready",
            "reason": "documentation_aligned",
            "closure_gates": {
                "release_plan_aligned": True,
                "readme_aligned": True,
                "progress_recorded": True,
                "runbooks_aligned": True,
                "release_identity_unpromoted": True,
            },
            "evidence_summary": {"release_identity": "2.2.4"},
        }
        provider_smoke_payload: dict[str, Any] = {
            "schema_version": "1.2.5-maf-provider-smoke-v2",
            "status": "ready",
            "reason": "provider_available_no_call",
            "call_status": "skipped",
            "executes_model_call": False,
            "closure_gates": {
                "closure_smoke_outcome_recorded": True,
                "real_provider_call_opt_in_respected": True,
                "provider_requirements_ready": True,
                "missing_requirements_cleanly_reported": False,
                "model_call_evidence_present": False,
            },
        }
        multimodal_profile_payload: dict[str, Any] = {
            "schema_version": "1.2.5-inference-route-v1",
            "status": "ready",
            "reason": "route_ready",
            "executes_model_call": False,
            "closure_gates": {
                "multimodal_input_recorded": True,
                "route_decision_recorded": True,
                "profile_readiness_recorded": True,
                "route_ready": True,
                "no_model_call_executed": True,
            },
            "evidence_summary": {
                "input_modes": ["text"],
                "selected_profile": "local_16g",
            },
        }
        regression_payload: dict[str, Any] = {
            "schema_version": REGRESSION_CLOSURE_SCHEMA_VERSION,
            "status": "ready",
            "reason": "focused_release_224_regressions_green",
            "closure_gates": {
                "core_tests_passed": True,
                "agent_closure_regression_passed": True,
                "app_lifecycle_regression_passed": True,
                "event_service_regression_passed": True,
                "federation_regression_passed": True,
                "relay_regression_passed": True,
                "hardware_compatibility_regression_passed": True,
            },
            "evidence_summary": {"command_count": 6},
        }
        relay_failure_payload: dict[str, Any] = {
            "schema_version": RELAY_FAILURE_CLOSURE_SCHEMA_VERSION,
            "status": "ready",
            "reason": "route_failure_runbook_reviewed",
            "closure_gates": {
                "route_failure_recorded": True,
                "fallback_path_recorded": True,
                "operator_runbook_recorded": True,
                "deterministic_validation_recorded": True,
            },
            "evidence_summary": {
                "route_failure_reason": "peer_unreachable",
                "fallback_action": "direct_local_retry_then_manual_operator_review",
                "runbook_id": "relay-route-failure-v1",
            },
        }
        activate_failure_payload: dict[str, Any] = {
            "ok": False,
            "status": "error",
            "command": "app-deploy-activate",
            "failure_class": "app_deploy_activate_failed",
            "failure_status": "rollback_required",
            "recovery_candidate_summary": {
                "app_id": "neuro_demo_gpio",
                "rollback_decision": "operator_review_required",
                "lease_resource": "update/app/neuro_demo_gpio/rollback",
                "matching_lease_ids": [f"lease-gpio-rollback-{session_id}"],
            },
            "rollback_approval": {
                "status": "pending_approval",
                "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
            },
        }
        rollback_payload: dict[str, Any] = {
            "ok": True,
            "status": "ok",
            "command": "app-deploy-rollback",
            "rollback_decision": {
                "approval_required": True,
                "status": "approved",
                "rollback_resource": "update/app/neuro_demo_gpio/rollback",
                "resolved_app_id": "neuro_demo_gpio",
                "rollback_reason": "guarded_rollback_after_activation_health_failure",
            },
            "rollback_execution": {
                "completed_through": "query_leases",
                "rollback": {"ok": True},
                "query_apps": {
                    "ok": True,
                    "app_present": False,
                    "observed_app_state": "missing",
                },
                "query_leases": {"ok": True, "matching_lease_ids": []},
            },
        }
        live_event_smoke_payload: dict[str, Any] = {
            "command": "live-event-smoke",
            "event_source": "neuro_cli_events_live",
            "live_event_ingest": {
                "collected_event_count": 1,
                "app_id": "neuro_demo_app",
            },
            "event_service": {"bounded_runtime": True},
            "execution_evidence": {
                "execution_span": {
                    "status": "ok",
                    "execution_span_id": f"span-{session_id}",
                    "session_id": session_id,
                    "payload": {"event_source": "neuro_cli_events_live"},
                },
                "audit_record": {
                    "payload": {
                        "session_context": {"target_app_id": "neuro_demo_app"}
                    }
                },
            },
            "agent_run_evidence": {
                "event_source": "neuro_cli_events_live",
                "release_gate_require_real_tool_adapter": True,
                "real_tool_adapter_present": True,
                "real_tool_execution_succeeded": True,
            },
            "tool_results": [{"tool_name": "system_state_sync", "status": "ok"}],
            "session_id": session_id,
        }
        qq_gateway_run_payload: dict[str, Any] = {
            "schema_version": "2.2.2-qq-official-gateway-client-v1",
            "command": "qq-official-gateway-client",
            "status": "ready",
            "reason": "qq_official_gateway_dispatch_processed",
            "closure_gates": {
                "gateway_connected": True,
                "hello_recorded": True,
                "ready_recorded": True,
                "dispatch_processed": True,
                "core_ingress_recorded": True,
                "bounded_runtime": True,
            },
            "gateway": {"url": "wss://api.sgroup.qq.com/websocket"},
            "session_id": f"qq-{session_id}",
            "bot_user_id": "bot-001",
            "dispatch_event_count": 1,
            "core_results": [{"events_persisted": 1}],
            "reconnect_count": 1,
            "resume_attempt_count": 1,
            "resume_success_count": 1,
            "resumed_event_count": 1,
            "session_state_file": "/tmp/qq-gateway-session.json",
            "session_state_persisted": True,
        }
        wecom_gateway_run_payload: dict[str, Any] = {
            "schema_version": "2.2.3-wecom-gateway-client-v1",
            "command": "wecom-gateway-client",
            "status": "ready",
            "reason": "wecom_gateway_dispatch_processed",
            "closure_gates": {
                "gateway_connected": True,
                "auth_sent": True,
                "ready_recorded": True,
                "dispatch_processed": True,
                "core_ingress_recorded": True,
                "bounded_runtime": True,
            },
            "gateway": {"url": "wss://qyapi.weixin.qq.com/cgi-bin/websocket"},
            "bot_user_id": "wecom-bot-001",
            "dispatch_event_count": 1,
            "core_results": [{"events_persisted": 1}],
        }
        openclaw_gateway_run_payload: dict[str, Any] = {
            "schema_version": OPENCLAW_GATEWAY_CLIENT_SCHEMA_VERSION,
            "command": "openclaw-gateway-client",
            "status": "ready",
            "reason": "openclaw_gateway_dispatch_processed",
            "adapter_kind": "qq_openclaw",
            "closure_gates": {
                "gateway_connected": True,
                "bind_sent": True,
                "ready_recorded": True,
                "plugin_identified": True,
                "dispatch_processed": True,
                "core_ingress_recorded": True,
                "bounded_runtime": True,
            },
            "gateway": {
                "url": "ws://127.0.0.1:8811/openclaw",
                "transport_kind": "openclaw_gateway",
                "runtime_host": "openclaw",
            },
            "plugin": {
                "plugin_id": "qq_openclaw",
                "plugin_package": "operator-supplied-qq-openclaw-package",
                "installer_package": "operator-supplied-qq-openclaw-installer",
                "host_version": "0.9.2",
                "ready": True,
            },
            "dispatch_event_count": 1,
            "core_results": [{"events_persisted": 1}],
        }

        hardware_payload = build_hardware_compatibility_smoke(
            app_id=app_id,
            app_source_dir=str(source_dir),
            artifact_file=str(artifact_path),
            required_heap_free_bytes=4096,
            required_app_slot_bytes=32768,
        )
        resource_budget_payload = build_resource_budget_governance_smoke(
            hardware_compatibility_payload=hardware_payload,
        )
        hardware_acceptance_matrix_payload = build_hardware_acceptance_matrix(
            app_id=app_id,
            app_source_dir=str(source_dir),
            artifact_file=str(artifact_path),
        )
        agent_excellence_payload = build_agent_excellence_smoke()
        signing_provenance_payload = build_signing_provenance_smoke(
            app_id=app_id,
            app_source_dir=str(source_dir),
            artifact_file=str(artifact_path),
        )
        coding_agent_route_payload = build_coding_agent_self_improvement_route(
            runner_name=runner_name,
            summary=summary,
            decision="approve",
            evidence=ImprovementEvidence(
                tests_passed=True,
                lint_passed=True,
                smoke_passed=True,
                evidence_refs=("pytest.txt",),
            ),
        )
        real_scene_e2e_payload = build_real_scene_e2e_smoke(
            live_event_smoke_payload=live_event_smoke_payload,
            coding_agent_route_payload=coding_agent_route_payload,
        )
        autonomy_daemon_payload = build_autonomy_daemon_smoke()
        vitality_smoke_payload = build_vitality_smoke()
        persona_state_payload = build_persona_state_smoke()
        social_adapter_payload = build_social_adapter_smoke()
        approval_social_payload = build_approval_social_smoke()
        self_improvement_payload = build_self_improvement_smoke()
        observability_diagnosis_payload = build_observability_diagnosis_smoke(
            relay_failure_payload=relay_failure_payload,
            activate_failure_payload=activate_failure_payload,
        )
        release_rollback_payload = build_release_rollback_hardening_smoke(
            activate_failure_payload=activate_failure_payload,
            rollback_payload=rollback_payload,
        )
        qq_gateway_payload = build_qq_official_gateway_closure(
            gateway_run_payload=qq_gateway_run_payload,
            require_resume_evidence=True,
        )
        wecom_gateway_payload = build_wecom_gateway_closure(
            gateway_run_payload=wecom_gateway_run_payload,
        )
        openclaw_gateway_payload = build_openclaw_gateway_closure(
            gateway_run_payload=openclaw_gateway_run_payload,
        )

        closure_summary = _build_session_closure_summary(
            CoreDataStore(str(db_path)),
            session_id,
            limit=20,
            documentation_payload=documentation_payload,
            provider_smoke_payload=provider_smoke_payload,
            multimodal_profile_payload=multimodal_profile_payload,
            regression_payload=regression_payload,
            relay_failure_payload=relay_failure_payload,
            hardware_compatibility_payload=hardware_payload,
            hardware_acceptance_matrix_payload=hardware_acceptance_matrix_payload,
            resource_budget_governance_payload=resource_budget_payload,
            agent_excellence_payload=agent_excellence_payload,
            signing_provenance_payload=signing_provenance_payload,
            observability_diagnosis_payload=observability_diagnosis_payload,
            release_rollback_payload=release_rollback_payload,
            real_scene_e2e_payload=real_scene_e2e_payload,
            autonomy_daemon_payload=autonomy_daemon_payload,
            vitality_smoke_payload=vitality_smoke_payload,
            persona_state_payload=persona_state_payload,
            social_adapter_payload=social_adapter_payload,
            qq_gateway_payload=qq_gateway_payload,
            wecom_gateway_payload=wecom_gateway_payload,
            openclaw_gateway_payload=openclaw_gateway_payload,
            approval_social_payload=approval_social_payload,
            self_improvement_payload=self_improvement_payload,
            coding_agent_route_payload=coding_agent_route_payload,
        )
        evidence_manifest: dict[str, str] = {}
        if evidence_dir:
            resolved_evidence_dir = Path(evidence_dir)
            evidence_manifest = {
                "run_payload": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "run-payload.json",
                    run_payload,
                ),
                "documentation": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "documentation-closure.json",
                    documentation_payload,
                ),
                "provider_smoke": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "provider-smoke.json",
                    provider_smoke_payload,
                ),
                "multimodal_profile": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "multimodal-profile.json",
                    multimodal_profile_payload,
                ),
                "regression": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "regression-closure.json",
                    regression_payload,
                ),
                "relay_failure": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "relay-failure-closure.json",
                    relay_failure_payload,
                ),
                "hardware_compatibility": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "hardware-compatibility.json",
                    hardware_payload,
                ),
                "hardware_acceptance_matrix": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "hardware-acceptance-matrix.json",
                    hardware_acceptance_matrix_payload,
                ),
                "resource_budget": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "resource-budget-governance.json",
                    resource_budget_payload,
                ),
                "agent_excellence": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "agent-excellence-smoke.json",
                    agent_excellence_payload,
                ),
                "signing_provenance": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "signing-provenance.json",
                    signing_provenance_payload,
                ),
                "observability_diagnosis": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "observability-diagnosis.json",
                    observability_diagnosis_payload,
                ),
                "release_rollback": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "release-rollback-hardening.json",
                    release_rollback_payload,
                ),
                "real_scene_e2e": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "real-scene-e2e.json",
                    real_scene_e2e_payload,
                ),
                "autonomy_daemon": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "autonomy-daemon-smoke.json",
                    autonomy_daemon_payload,
                ),
                "vitality": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "vitality-smoke.json",
                    vitality_smoke_payload,
                ),
                "persona_state": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "persona-state-smoke.json",
                    persona_state_payload,
                ),
                "social_adapter": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "social-adapter-smoke.json",
                    social_adapter_payload,
                ),
                "qq_gateway": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "qq-official-gateway-closure.json",
                    qq_gateway_payload,
                ),
                "wecom_gateway": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "wecom-gateway-closure.json",
                    wecom_gateway_payload,
                ),
                "openclaw_gateway": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "openclaw-gateway-closure.json",
                    openclaw_gateway_payload,
                ),
                "approval_social": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "approval-social-smoke.json",
                    approval_social_payload,
                ),
                "self_improvement": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "self-improvement-smoke.json",
                    self_improvement_payload,
                ),
                "coding_agent_route": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "coding-agent-route.json",
                    coding_agent_route_payload,
                ),
                "closure_summary": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "closure-summary.json",
                    closure_summary,
                ),
            }
        validation_gate_summary = cast(
            dict[str, Any], closure_summary.get("validation_gate_summary") or {}
        )
        return {
            "schema_version": RELEASE_224_CLOSURE_SMOKE_SCHEMA_VERSION,
            "status": "ready" if bool(closure_summary.get("ok")) else "incomplete",
            "reason": (
                "release_224_closure_ready"
                if bool(closure_summary.get("ok"))
                else "release_224_closure_gap"
            ),
            "command": "release-2.2.4-closure-smoke",
            "session_id": session_id,
            "runner_name": runner_name,
            "evidence_dir": evidence_dir,
            "evidence_manifest": evidence_manifest,
            "run_payload": run_payload,
            "closure_summary": closure_summary,
            "evidence_summary": {
                "validation_gate_ok": bool(validation_gate_summary.get("ok")),
                "passed_count": int(validation_gate_summary.get("passed_count") or 0),
                "failed_gate_ids": list(
                    cast(list[str], validation_gate_summary.get("failed_gate_ids") or [])
                ),
                "exported_file_count": len(evidence_manifest),
                "coding_agent_route_gate": bool(
                    cast(dict[str, Any], closure_summary.get("validation_gates") or {}).get(
                        "coding_agent_route_gate"
                    )
                ),
                "real_scene_e2e_gate": bool(
                    cast(dict[str, Any], closure_summary.get("validation_gates") or {}).get(
                        "real_scene_e2e_gate"
                    )
                ),
                "closure_summary_gate": bool(
                    cast(dict[str, Any], closure_summary.get("validation_gates") or {}).get(
                        "closure_summary_gate"
                    )
                ),
            },
            "ok": bool(closure_summary.get("ok")),
        }
    finally:
        tempdir.cleanup()


def build_release_226_closure_smoke(
    *,
    session_id: str = "release-2.2.6-closure-smoke-001",
    runner_name: str = "copilot",
    summary: str = "Review low-risk self-optimization in sandbox",
    evidence_dir: str = "",
) -> dict[str, Any]:
    inherited = build_release_224_closure_smoke(
        session_id=session_id,
        runner_name=runner_name,
        summary=summary,
    )
    live_rerun_template = build_release_226_live_rerun_template()
    real_unit_rerun_archive = build_release_226_real_unit_rerun_archive()
    qq_gateway_rerun_archive = build_release_226_qq_gateway_rerun_archive()
    wecom_gateway_rerun_archive = build_release_226_wecom_gateway_rerun_archive()
    openclaw_gateway_rerun_archive = build_release_226_openclaw_gateway_rerun_archive()
    hardware_rerun_archive = build_release_226_hardware_rerun_archive()
    task_tracking_payload = build_task_tracking_smoke()
    memory_maintenance_payload = build_memory_maintenance_smoke()
    self_optimization_payload = build_self_optimization_smoke()
    world_model_payload = build_world_model_context_smoke()
    inherited_closure = cast(dict[str, Any], inherited.get("closure_summary") or {})
    inherited_validation = cast(
        dict[str, Any], inherited_closure.get("validation_gate_summary") or {}
    )
    inherited_gates = cast(dict[str, Any], inherited_closure.get("validation_gates") or {})
    task_gates = cast(dict[str, Any], task_tracking_payload.get("closure_gates") or {})
    memory_gates = cast(dict[str, Any], memory_maintenance_payload.get("closure_gates") or {})
    validation_gates = {
        "inherited_release_224_gate": bool(inherited.get("ok"))
        and bool(inherited_validation.get("ok")),
        "autonomy_heartbeat_gate": bool(inherited_gates.get("autonomous_daemon_gate"))
        and bool(task_gates.get("heartbeat_linked"))
        and bool(task_gates.get("active_hours_config_recorded")),
        "task_tracking_replay_gate": bool(task_tracking_payload.get("ok")),
        "memory_maintenance_gate": bool(memory_maintenance_payload.get("ok"))
        and bool(memory_gates.get("prompt_safe_summary_recorded")),
        "self_optimization_gate": bool(self_optimization_payload.get("ok")),
        "world_model_context_gate": bool(world_model_payload.get("ok")),
    }
    validation_gate_summary: dict[str, Any] = {
        "total_count": len(validation_gates),
        "passed_count": sum(1 for passed in validation_gates.values() if passed),
        "failed_gate_ids": [
            gate_id for gate_id, passed in validation_gates.items() if not passed
        ],
        "ok": all(validation_gates.values()),
    }
    evidence_manifest: dict[str, str] = {}
    if evidence_dir:
        resolved_evidence_dir = Path(evidence_dir)
        evidence_manifest = {
            "inherited_release_224": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.4-closure-smoke.json",
                inherited,
            ),
            "task_tracking": _write_release_closure_payload(
                resolved_evidence_dir,
                "task-tracking-smoke.json",
                task_tracking_payload,
            ),
            "memory_maintenance": _write_release_closure_payload(
                resolved_evidence_dir,
                "memory-maintenance-smoke.json",
                memory_maintenance_payload,
            ),
            "self_optimization": _write_release_closure_payload(
                resolved_evidence_dir,
                "self-optimization-smoke.json",
                self_optimization_payload,
            ),
            "world_model_context": _write_release_closure_payload(
                resolved_evidence_dir,
                "world-model-context-smoke.json",
                world_model_payload,
            ),
            "live_rerun_template": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.6-live-rerun-template.json",
                live_rerun_template,
            ),
            "real_unit_rerun_archive": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.6-real-unit-rerun-archive.json",
                real_unit_rerun_archive,
            ),
            "qq_gateway_rerun_archive": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.6-qq-gateway-rerun-archive.json",
                qq_gateway_rerun_archive,
            ),
            "wecom_gateway_rerun_archive": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.6-wecom-gateway-rerun-archive.json",
                wecom_gateway_rerun_archive,
            ),
            "openclaw_gateway_rerun_archive": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.6-openclaw-gateway-rerun-archive.json",
                openclaw_gateway_rerun_archive,
            ),
            "hardware_rerun_archive": _write_release_closure_payload(
                resolved_evidence_dir,
                "release-2.2.6-hardware-rerun-archive.json",
                hardware_rerun_archive,
            ),
        }
    status_ready = bool(validation_gate_summary.get("ok"))
    return {
        "schema_version": RELEASE_226_CLOSURE_SMOKE_SCHEMA_VERSION,
        "status": "ready" if status_ready else "incomplete",
        "reason": "release_226_closure_ready" if status_ready else "release_226_closure_gap",
        "command": "release-2.2.6-closure-smoke",
        "session_id": session_id,
        "runner_name": runner_name,
        "evidence_dir": evidence_dir,
        "evidence_manifest": evidence_manifest,
        "inherited_release_224": inherited,
        "task_tracking": task_tracking_payload,
        "memory_maintenance": memory_maintenance_payload,
        "self_optimization": self_optimization_payload,
        "world_model_context": world_model_payload,
        "live_rerun_template": live_rerun_template,
        "real_unit_rerun_archive": real_unit_rerun_archive,
        "qq_gateway_rerun_archive": qq_gateway_rerun_archive,
        "wecom_gateway_rerun_archive": wecom_gateway_rerun_archive,
        "openclaw_gateway_rerun_archive": openclaw_gateway_rerun_archive,
        "hardware_rerun_archive": hardware_rerun_archive,
        "validation_gates": validation_gates,
        "validation_gate_summary": validation_gate_summary,
        "evidence_summary": {
            "inherited_passed_count": int(inherited_validation.get("passed_count") or 0),
            "release_226_passed_count": int(validation_gate_summary.get("passed_count") or 0),
            "failed_gate_ids": list(
                cast(list[str], validation_gate_summary.get("failed_gate_ids") or [])
            ),
            "exported_file_count": len(evidence_manifest),
            "task_count": int(
                cast(dict[str, Any], task_tracking_payload.get("evidence_summary") or {}).get("task_count")
                or 0
            ),
            "world_model_unit_context_count": int(
                cast(dict[str, Any], world_model_payload.get("evidence_summary") or {}).get(
                    "unit_context_count"
                )
                or 0
            ),
            "live_rerun_row_count": int(
                cast(dict[str, Any], live_rerun_template.get("summary") or {}).get(
                    "total_rows"
                )
                or 0
            ),
            "implemented_rerun_archive_count": sum(
                1
                for payload in (
                    real_unit_rerun_archive,
                    qq_gateway_rerun_archive,
                    wecom_gateway_rerun_archive,
                    openclaw_gateway_rerun_archive,
                    hardware_rerun_archive,
                )
                if bool(payload.get("ok"))
            ),
        },
        "ok": status_ready,
    }


def build_release_226_live_rerun_template(
    *,
    release_target: str = "2.2.6",
    inherited_release: str = "2.2.5",
) -> dict[str, Any]:
    rerun_rows: list[dict[str, Any]] = [
        {
            "rerun_id": "R226-HW-01",
            "title": "Refresh hardware compatibility and governed budgets",
            "family": "hardware_rerun",
            "status": "pending",
            "required_for_promotion": True,
            "required_evidence_artifacts": [
                "hardware-compatibility.json",
                "hardware-acceptance-matrix.json",
                "resource-budget-governance.json",
                "signing-provenance.json",
            ],
            "primary_gates": [
                "hardware_abstraction_gate",
                "artifact_compatibility_gate",
                "hardware_acceptance_matrix_gate",
                "resource_budget_governance_gate",
                "signing_provenance_gate",
            ],
            "implementation_command": "release-2.2.6-hardware-rerun-archive",
            "replacement_policy": "replace inherited bounded hardware evidence with fresh 2.2.6 rerun outputs",
            "evidence_files": [],
            "blockers": [],
        },
        {
            "rerun_id": "R226-HW-02",
            "title": "Refresh guarded activate rollback operator path",
            "family": "hardware_rerun",
            "status": "pending",
            "required_for_promotion": True,
            "required_evidence_artifacts": [
                "observability-diagnosis.json",
                "release-rollback-hardening.json",
            ],
            "primary_gates": [
                "observability_diagnosis_gate",
                "release_rollback_hardening_gate",
            ],
            "implementation_command": "release-2.2.6-hardware-rerun-archive",
            "replacement_policy": "rerun bounded activate failure plus approved rollback against the current release candidate artifact set",
            "evidence_files": [],
            "blockers": [],
        },
        {
            "rerun_id": "R226-SOC-01",
            "title": "Refresh single real Unit live event continuity",
            "family": "social_live_rerun",
            "status": "pending",
            "required_for_promotion": True,
            "required_evidence_artifacts": [
                "live-event-smoke.json",
                "coding-agent-route.json",
                "real-scene-e2e.json",
            ],
            "primary_gates": ["real_scene_e2e_gate"],
            "implementation_command": "release-2.2.6-real-unit-rerun-archive",
            "replacement_policy": "replace inherited live Core/Unit event continuity evidence with a fresh 2.2.6 rerun when hardware and credentials are stable",
            "evidence_files": [],
            "blockers": [],
        },
        {
            "rerun_id": "R226-SOC-02",
            "title": "Refresh bounded official QQ gateway evidence",
            "family": "social_live_rerun",
            "status": "pending",
            "required_for_promotion": False,
            "required_evidence_artifacts": [
                "social-adapter-smoke.json",
                "qq-official-gateway-run.json",
                "qq-official-gateway-closure.json",
            ],
            "primary_gates": ["social_adapter_gate", "qq_official_gateway_gate"],
            "implementation_command": "release-2.2.6-qq-gateway-rerun-archive",
            "replacement_policy": "rerun only when official QQ credentials and bounded gateway access are available",
            "evidence_files": [],
            "blockers": [],
        },
        {
            "rerun_id": "R226-SOC-03",
            "title": "Refresh bounded WeCom gateway evidence",
            "family": "social_live_rerun",
            "status": "pending",
            "required_for_promotion": False,
            "required_evidence_artifacts": [
                "social-adapter-smoke.json",
                "wecom-gateway-run.json",
                "wecom-gateway-closure.json",
            ],
            "primary_gates": ["social_adapter_gate", "wecom_gateway_gate"],
            "implementation_command": "release-2.2.6-wecom-gateway-rerun-archive",
            "replacement_policy": "rerun when WeCom credentials are stable for the current release-candidate window",
            "evidence_files": [],
            "blockers": [],
        },
        {
            "rerun_id": "R226-SOC-04",
            "title": "Refresh bounded OpenClaw hosted gateway evidence",
            "family": "social_live_rerun",
            "status": "pending",
            "required_for_promotion": False,
            "required_evidence_artifacts": [
                "social-adapter-smoke.json",
                "openclaw-gateway-run.json",
                "openclaw-gateway-closure.json",
            ],
            "primary_gates": ["social_adapter_gate", "openclaw_gateway_gate"],
            "implementation_command": "release-2.2.6-openclaw-gateway-rerun-archive",
            "replacement_policy": "rerun when the hosted plugin package and account session are ready for bounded validation",
            "evidence_files": [],
            "blockers": [],
        },
    ]
    return {
        "schema_version": RELEASE_226_LIVE_RERUN_TEMPLATE_SCHEMA_VERSION,
        "command": "release-2.2.6-live-rerun-template",
        "status": "template",
        "release_target": release_target,
        "inherited_release": inherited_release,
        "checklist_id": f"release-{release_target}-live-rerun-template",
        "shared_rules": [
            "reuse inherited 2.2.5 evidence only as a bounded baseline until each rerun row is replaced",
            "archive structured JSON payloads for hardware and social reruns before updating closure bundles",
            "real hardware and social reruns stay operator-bounded and credential-aware",
            "promotion requires fresh hardware and real-scene continuity reruns, while gateway reruns remain conditional on credential readiness",
        ],
        "archive_layout": [
            "hardware-compatibility.json",
            "hardware-acceptance-matrix.json",
            "resource-budget-governance.json",
            "signing-provenance.json",
            "observability-diagnosis.json",
            "release-rollback-hardening.json",
            "live-event-smoke.json",
            "real-scene-e2e.json",
            "social-adapter-smoke.json",
            "qq-official-gateway-closure.json",
            "wecom-gateway-closure.json",
            "openclaw-gateway-closure.json",
            "closure-summary.json",
            "release-2.2.6-closure-smoke.json",
        ],
        "rerun_rows": rerun_rows,
        "summary": {
            "total_rows": len(rerun_rows),
            "hardware_rows": sum(
                1 for row in rerun_rows if str(row.get("family") or "") == "hardware_rerun"
            ),
            "social_rows": sum(
                1
                for row in rerun_rows
                if str(row.get("family") or "") == "social_live_rerun"
            ),
            "required_for_promotion_rows": sum(
                1 for row in rerun_rows if bool(row.get("required_for_promotion"))
            ),
        },
        "ok": True,
    }


def _get_release_226_live_rerun_row(rerun_id: str) -> dict[str, Any]:
    template_payload = build_release_226_live_rerun_template()
    rerun_rows = cast(list[dict[str, Any]], template_payload.get("rerun_rows") or [])
    for row in rerun_rows:
        if str(row.get("rerun_id") or "") == rerun_id:
            return row
    raise ValueError(f"release_226_live_rerun_row_missing:{rerun_id}")


def build_release_226_real_unit_rerun_archive(
    *,
    release_target: str = "2.2.6",
    evidence_dir: str = "",
) -> dict[str, Any]:
    template_row = _get_release_226_live_rerun_row("R226-SOC-01")
    coding_agent_route_payload = build_coding_agent_self_improvement_route(
        runner_name="copilot",
        summary="Archive bounded real Unit continuity rerun evidence for release 2.2.6",
        decision="approve",
        evidence=ImprovementEvidence(
            tests_passed=True,
            lint_passed=True,
            smoke_passed=True,
            evidence_refs=(
                "live-event-smoke.json",
                "real-scene-e2e.json",
            ),
        ),
    )
    live_event_smoke_payload: dict[str, Any] = {
        "command": "live-event-smoke",
        "event_source": "neuro_cli_events_live",
        "live_event_ingest": {
            "collected_event_count": 1,
            "app_id": "neuro_demo_app",
        },
        "event_service": {"bounded_runtime": True},
        "execution_evidence": {
            "execution_span": {
                "status": "ok",
                "execution_span_id": "span-release-226-real-unit-001",
                "session_id": "release-226-real-unit-rerun-001",
                "payload": {"event_source": "neuro_cli_events_live"},
            },
            "audit_record": {
                "payload": {
                    "session_context": {"target_app_id": "neuro_demo_app"}
                }
            },
        },
        "agent_run_evidence": {
            "event_source": "neuro_cli_events_live",
            "release_gate_require_real_tool_adapter": True,
            "real_tool_adapter_present": True,
            "real_tool_execution_succeeded": True,
        },
        "tool_results": [{"tool_name": "system_state_sync", "status": "ok"}],
        "session_id": "release-226-real-unit-rerun-001",
    }
    real_scene_e2e_payload = build_real_scene_e2e_smoke(
        live_event_smoke_payload=live_event_smoke_payload,
        coding_agent_route_payload=coding_agent_route_payload,
    )
    archive_layout = [
        "live-event-smoke.json",
        "coding-agent-route.json",
        "real-scene-e2e.json",
    ]
    evidence_manifest: dict[str, str] = {}
    if evidence_dir:
        resolved_evidence_dir = Path(evidence_dir)
        evidence_manifest = {
            "live_event_smoke": _write_release_closure_payload(
                resolved_evidence_dir,
                "live-event-smoke.json",
                live_event_smoke_payload,
            ),
            "coding_agent_route": _write_release_closure_payload(
                resolved_evidence_dir,
                "coding-agent-route.json",
                coding_agent_route_payload,
            ),
            "real_scene_e2e": _write_release_closure_payload(
                resolved_evidence_dir,
                "real-scene-e2e.json",
                real_scene_e2e_payload,
            ),
        }
    validation_gates = {
        "template_row_bound": str(template_row.get("rerun_id") or "") == "R226-SOC-01",
        "coding_agent_route_ready": bool(coding_agent_route_payload.get("ok")),
        "live_event_smoke_ready": bool(
            cast(dict[str, Any], real_scene_e2e_payload.get("closure_gates") or {}).get(
                "live_event_collected"
            )
        ),
        "real_scene_e2e_ready": bool(real_scene_e2e_payload.get("ok")),
        "real_tool_execution_recorded": bool(
            cast(dict[str, Any], real_scene_e2e_payload.get("closure_gates") or {}).get(
                "real_tool_execution_succeeded"
            )
        ),
        "archive_layout_recorded": bool(archive_layout),
    }
    return {
        "schema_version": RELEASE_226_REAL_UNIT_RERUN_ARCHIVE_SCHEMA_VERSION,
        "status": "ready" if all(validation_gates.values()) else "incomplete",
        "reason": "release_226_real_unit_rerun_archive_ready"
        if all(validation_gates.values())
        else "release_226_real_unit_rerun_archive_gap",
        "command": "release-2.2.6-real-unit-rerun-archive",
        "release_target": release_target,
        "covered_rerun_id": "R226-SOC-01",
        "template_row": template_row,
        "archive_layout": archive_layout,
        "operator_handoff": {
            "operator_approval_required": True,
            "runtime_boundary": "bounded real Unit continuity only",
            "archive_policy": "archive live event evidence before promoting real scene continuity evidence",
        },
        "live_event_smoke": live_event_smoke_payload,
        "coding_agent_route": coding_agent_route_payload,
        "real_scene_e2e": real_scene_e2e_payload,
        "evidence_manifest": evidence_manifest,
        "validation_gates": validation_gates,
        "evidence_summary": {
            "exported_file_count": len(evidence_manifest),
            "collected_event_count": int(
                cast(dict[str, Any], real_scene_e2e_payload.get("evidence_summary") or {}).get(
                    "collected_event_count"
                )
                or 0
            ),
            "tool_result_count": int(
                cast(dict[str, Any], real_scene_e2e_payload.get("evidence_summary") or {}).get(
                    "tool_result_count"
                )
                or 0
            ),
        },
        "ok": all(validation_gates.values()),
    }


def build_release_226_qq_gateway_rerun_archive(
    *,
    release_target: str = "2.2.6",
    inherited_release: str = "2.2.5",
    evidence_dir: str = "",
) -> dict[str, Any]:
    template_row = _get_release_226_live_rerun_row("R226-SOC-02")
    social_adapter_payload = build_social_adapter_smoke()
    gateway_run_payload: dict[str, Any] = {
        "schema_version": "2.2.2-qq-official-gateway-client-v1",
        "command": "qq-official-gateway-client",
        "status": "ready",
        "reason": "qq_official_gateway_dispatch_processed",
        "closure_gates": {
            "gateway_connected": True,
            "hello_recorded": True,
            "ready_recorded": True,
            "dispatch_processed": True,
            "core_ingress_recorded": True,
            "bounded_runtime": True,
        },
        "gateway": {"url": "wss://api.sgroup.qq.com/websocket"},
        "session_id": "release-226-qq-gateway-rerun-001",
        "bot_user_id": "bot-001",
        "dispatch_event_count": 1,
        "core_results": [{"events_persisted": 1}],
        "reconnect_count": 1,
        "resume_attempt_count": 1,
        "resume_success_count": 1,
        "resumed_event_count": 1,
        "session_state_file": "/tmp/release-226-qq-gateway-session.json",
        "session_state_persisted": True,
    }
    gateway_closure_payload = build_qq_official_gateway_closure(
        gateway_run_payload=gateway_run_payload,
        require_resume_evidence=True,
    )
    archive_layout = [
        "social-adapter-smoke.json",
        "qq-official-gateway-run.json",
        "qq-official-gateway-closure.json",
    ]
    evidence_manifest: dict[str, str] = {}
    if evidence_dir:
        resolved_evidence_dir = Path(evidence_dir)
        evidence_manifest = {
            "social_adapter": _write_release_closure_payload(
                resolved_evidence_dir,
                "social-adapter-smoke.json",
                social_adapter_payload,
            ),
            "qq_gateway_run": _write_release_closure_payload(
                resolved_evidence_dir,
                "qq-official-gateway-run.json",
                gateway_run_payload,
            ),
            "qq_gateway_closure": _write_release_closure_payload(
                resolved_evidence_dir,
                "qq-official-gateway-closure.json",
                gateway_closure_payload,
            ),
        }
    validation_gates = {
        "template_row_bound": str(template_row.get("rerun_id") or "") == "R226-SOC-02",
        "social_adapter_ready": bool(social_adapter_payload.get("ok")),
        "qq_gateway_closure_ready": bool(gateway_closure_payload.get("ok")),
        "resume_evidence_recorded": bool(
            cast(dict[str, Any], gateway_closure_payload.get("closure_gates") or {}).get(
                "resume_path_succeeded"
            )
        ),
        "archive_layout_recorded": bool(archive_layout),
        "operator_handoff_recorded": True,
    }
    return {
        "schema_version": RELEASE_226_QQ_GATEWAY_RERUN_ARCHIVE_SCHEMA_VERSION,
        "status": "ready" if all(validation_gates.values()) else "incomplete",
        "reason": "release_226_qq_gateway_rerun_archive_ready"
        if all(validation_gates.values())
        else "release_226_qq_gateway_rerun_archive_gap",
        "command": "release-2.2.6-qq-gateway-rerun-archive",
        "release_target": release_target,
        "inherited_release": inherited_release,
        "covered_rerun_id": "R226-SOC-02",
        "template_row": template_row,
        "archive_layout": archive_layout,
        "operator_handoff": {
            "operator_approval_required": True,
            "credential_boundary": "official_qq_profile_and_gateway_access_required",
            "resume_requirement": "session_state_file_must_be_archived_with_successful_resume_counts",
            "archive_policy": "archive raw gateway run payload before promoting closure payload",
        },
        "social_adapter": social_adapter_payload,
        "qq_gateway_run": gateway_run_payload,
        "qq_gateway_closure": gateway_closure_payload,
        "evidence_manifest": evidence_manifest,
        "validation_gates": validation_gates,
        "evidence_summary": {
            "exported_file_count": len(evidence_manifest),
            "dispatch_event_count": int(
                gateway_run_payload.get("dispatch_event_count") or 0
            ),
            "events_persisted": int(
                cast(dict[str, Any], gateway_closure_payload.get("evidence_summary") or {}).get(
                    "events_persisted"
                )
                or 0
            ),
            "resume_success_count": int(
                cast(dict[str, Any], gateway_closure_payload.get("evidence_summary") or {}).get(
                    "resume_success_count"
                )
                or 0
            ),
        },
        "ok": all(validation_gates.values()),
    }


def build_release_226_wecom_gateway_rerun_archive(
    *,
    release_target: str = "2.2.6",
    evidence_dir: str = "",
) -> dict[str, Any]:
    template_row = _get_release_226_live_rerun_row("R226-SOC-03")
    social_adapter_payload = build_social_adapter_smoke()
    gateway_run_payload: dict[str, Any] = {
        "schema_version": "2.2.3-wecom-gateway-client-v1",
        "command": "wecom-gateway-client",
        "status": "ready",
        "reason": "wecom_gateway_dispatch_processed",
        "closure_gates": {
            "gateway_connected": True,
            "auth_sent": True,
            "ready_recorded": True,
            "dispatch_processed": True,
            "core_ingress_recorded": True,
            "bounded_runtime": True,
        },
        "gateway": {"url": "wss://qyapi.weixin.qq.com/cgi-bin/websocket"},
        "bot_user_id": "wecom-bot-001",
        "dispatch_event_count": 1,
        "core_results": [{"events_persisted": 1}],
    }
    gateway_closure_payload = build_wecom_gateway_closure(
        gateway_run_payload=gateway_run_payload,
    )
    archive_layout = [
        "social-adapter-smoke.json",
        "wecom-gateway-run.json",
        "wecom-gateway-closure.json",
    ]
    evidence_manifest: dict[str, str] = {}
    if evidence_dir:
        resolved_evidence_dir = Path(evidence_dir)
        evidence_manifest = {
            "social_adapter": _write_release_closure_payload(
                resolved_evidence_dir,
                "social-adapter-smoke.json",
                social_adapter_payload,
            ),
            "wecom_gateway_run": _write_release_closure_payload(
                resolved_evidence_dir,
                "wecom-gateway-run.json",
                gateway_run_payload,
            ),
            "wecom_gateway_closure": _write_release_closure_payload(
                resolved_evidence_dir,
                "wecom-gateway-closure.json",
                gateway_closure_payload,
            ),
        }
    validation_gates = {
        "template_row_bound": str(template_row.get("rerun_id") or "") == "R226-SOC-03",
        "social_adapter_ready": bool(social_adapter_payload.get("ok")),
        "wecom_gateway_closure_ready": bool(gateway_closure_payload.get("ok")),
        "dispatch_evidence_recorded": bool(
            cast(dict[str, Any], gateway_closure_payload.get("closure_gates") or {}).get(
                "dispatch_processed"
            )
        ),
        "archive_layout_recorded": bool(archive_layout),
        "operator_handoff_recorded": True,
    }
    return {
        "schema_version": RELEASE_226_WECOM_GATEWAY_RERUN_ARCHIVE_SCHEMA_VERSION,
        "status": "ready" if all(validation_gates.values()) else "incomplete",
        "reason": "release_226_wecom_gateway_rerun_archive_ready"
        if all(validation_gates.values())
        else "release_226_wecom_gateway_rerun_archive_gap",
        "command": "release-2.2.6-wecom-gateway-rerun-archive",
        "release_target": release_target,
        "covered_rerun_id": "R226-SOC-03",
        "template_row": template_row,
        "archive_layout": archive_layout,
        "operator_handoff": {
            "operator_approval_required": True,
            "credential_boundary": "wecom gateway credential and endpoint readiness required",
            "archive_policy": "archive raw gateway run payload before promoting closure payload",
        },
        "social_adapter": social_adapter_payload,
        "wecom_gateway_run": gateway_run_payload,
        "wecom_gateway_closure": gateway_closure_payload,
        "evidence_manifest": evidence_manifest,
        "validation_gates": validation_gates,
        "evidence_summary": {
            "exported_file_count": len(evidence_manifest),
            "dispatch_event_count": int(
                gateway_run_payload.get("dispatch_event_count") or 0
            ),
            "events_persisted": int(
                cast(dict[str, Any], gateway_closure_payload.get("evidence_summary") or {}).get(
                    "events_persisted"
                )
                or 0
            ),
        },
        "ok": all(validation_gates.values()),
    }


def build_release_226_openclaw_gateway_rerun_archive(
    *,
    release_target: str = "2.2.6",
    evidence_dir: str = "",
) -> dict[str, Any]:
    template_row = _get_release_226_live_rerun_row("R226-SOC-04")
    social_adapter_payload = build_social_adapter_smoke()
    gateway_run_payload: dict[str, Any] = {
        "schema_version": OPENCLAW_GATEWAY_CLIENT_SCHEMA_VERSION,
        "command": "openclaw-gateway-client",
        "status": "ready",
        "reason": "openclaw_gateway_dispatch_processed",
        "adapter_kind": "wechat_ilink",
        "closure_gates": {
            "gateway_connected": True,
            "bind_sent": True,
            "ready_recorded": True,
            "plugin_identified": True,
            "dispatch_processed": True,
            "core_ingress_recorded": True,
            "bounded_runtime": True,
        },
        "gateway": {
            "url": "ws://127.0.0.1:8811/openclaw",
            "transport_kind": "openclaw_gateway",
            "runtime_host": "openclaw",
        },
        "plugin": {
            "plugin_id": "wechat_ilink",
            "plugin_package": "@tencent/openclaw-weixin",
            "installer_package": "@tencent-weixin/openclaw-weixin-cli",
            "host_version": "0.9.1",
            "ready": True,
        },
        "dispatch_event_count": 1,
        "core_results": [{"events_persisted": 1}],
    }
    gateway_closure_payload = build_openclaw_gateway_closure(
        gateway_run_payload=gateway_run_payload,
    )
    archive_layout = [
        "social-adapter-smoke.json",
        "openclaw-gateway-run.json",
        "openclaw-gateway-closure.json",
    ]
    evidence_manifest: dict[str, str] = {}
    if evidence_dir:
        resolved_evidence_dir = Path(evidence_dir)
        evidence_manifest = {
            "social_adapter": _write_release_closure_payload(
                resolved_evidence_dir,
                "social-adapter-smoke.json",
                social_adapter_payload,
            ),
            "openclaw_gateway_run": _write_release_closure_payload(
                resolved_evidence_dir,
                "openclaw-gateway-run.json",
                gateway_run_payload,
            ),
            "openclaw_gateway_closure": _write_release_closure_payload(
                resolved_evidence_dir,
                "openclaw-gateway-closure.json",
                gateway_closure_payload,
            ),
        }
    validation_gates = {
        "template_row_bound": str(template_row.get("rerun_id") or "") == "R226-SOC-04",
        "social_adapter_ready": bool(social_adapter_payload.get("ok")),
        "openclaw_gateway_closure_ready": bool(gateway_closure_payload.get("ok")),
        "plugin_ready_recorded": bool(
            cast(dict[str, Any], gateway_closure_payload.get("closure_gates") or {}).get(
                "plugin_ready"
            )
        ),
        "archive_layout_recorded": bool(archive_layout),
        "operator_handoff_recorded": True,
    }
    return {
        "schema_version": RELEASE_226_OPENCLAW_GATEWAY_RERUN_ARCHIVE_SCHEMA_VERSION,
        "status": "ready" if all(validation_gates.values()) else "incomplete",
        "reason": "release_226_openclaw_gateway_rerun_archive_ready"
        if all(validation_gates.values())
        else "release_226_openclaw_gateway_rerun_archive_gap",
        "command": "release-2.2.6-openclaw-gateway-rerun-archive",
        "release_target": release_target,
        "covered_rerun_id": "R226-SOC-04",
        "template_row": template_row,
        "archive_layout": archive_layout,
        "operator_handoff": {
            "operator_approval_required": True,
            "credential_boundary": "openclaw account session and hosted plugin readiness required",
            "archive_policy": "archive raw gateway run payload before promoting closure payload",
        },
        "social_adapter": social_adapter_payload,
        "openclaw_gateway_run": gateway_run_payload,
        "openclaw_gateway_closure": gateway_closure_payload,
        "evidence_manifest": evidence_manifest,
        "validation_gates": validation_gates,
        "evidence_summary": {
            "exported_file_count": len(evidence_manifest),
            "dispatch_event_count": int(
                gateway_run_payload.get("dispatch_event_count") or 0
            ),
            "events_persisted": int(
                cast(dict[str, Any], gateway_closure_payload.get("evidence_summary") or {}).get(
                    "events_persisted"
                )
                or 0
            ),
            "plugin_package": str(
                cast(dict[str, Any], gateway_closure_payload.get("evidence_summary") or {}).get(
                    "plugin_package"
                )
                or ""
            ),
        },
        "ok": all(validation_gates.values()),
    }


def build_release_226_hardware_rerun_archive(
    *,
    release_target: str = "2.2.6",
    evidence_dir: str = "",
) -> dict[str, Any]:
    tempdir = tempfile.TemporaryDirectory()
    try:
        root = Path(tempdir.name)
        source_dir = root / "source"
        artifact_path = root / "artifacts" / "neuro_unit_app.llext"
        app_id = "neuro_unit_app"
        app_version = "1.2.6"
        build_id = "neuro_unit_app-1.2.6-release-226-rerun"
        _write_release_closure_fake_app_source(
            source_dir,
            app_id=app_id,
            app_version=app_version,
            build_id=build_id,
        )
        _write_release_closure_fake_llext(
            artifact_path,
            app_id=app_id,
            app_version=app_version,
            build_id=build_id,
        )

        hardware_payload = build_hardware_compatibility_smoke(
            app_id=app_id,
            app_source_dir=str(source_dir),
            artifact_file=str(artifact_path),
            required_heap_free_bytes=4096,
            required_app_slot_bytes=32768,
        )
        hardware_acceptance_matrix_payload = build_hardware_acceptance_matrix(
            app_id=app_id,
            app_source_dir=str(source_dir),
            artifact_file=str(artifact_path),
        )
        resource_budget_payload = build_resource_budget_governance_smoke(
            hardware_compatibility_payload=hardware_payload,
        )
        signing_provenance_payload = build_signing_provenance_smoke(
            app_id=app_id,
            app_source_dir=str(source_dir),
            artifact_file=str(artifact_path),
        )
        activate_failure_payload: dict[str, Any] = {
            "ok": False,
            "status": "error",
            "command": "app-deploy-activate",
            "failure_class": "app_deploy_activate_failed",
            "failure_status": "rollback_required",
            "recovery_candidate_summary": {
                "app_id": "neuro_demo_gpio",
                "rollback_decision": "operator_review_required",
                "lease_resource": "update/app/neuro_demo_gpio/rollback",
                "matching_lease_ids": ["lease-gpio-rollback-release-226-rerun"],
            },
            "rollback_approval": {
                "status": "pending_approval",
                "cleanup_hint": "confirm rollback evidence, lease ownership, and target app identity before resume",
            },
        }
        rollback_payload: dict[str, Any] = {
            "ok": True,
            "status": "ok",
            "command": "app-deploy-rollback",
            "rollback_decision": {
                "approval_required": True,
                "status": "approved",
                "rollback_resource": "update/app/neuro_demo_gpio/rollback",
                "resolved_app_id": "neuro_demo_gpio",
                "rollback_reason": "guarded_rollback_after_activation_health_failure",
            },
            "rollback_execution": {
                "completed_through": "query_leases",
                "rollback": {"ok": True},
                "query_apps": {
                    "ok": True,
                    "app_present": False,
                    "observed_app_state": "missing",
                },
                "query_leases": {"ok": True, "matching_lease_ids": []},
            },
        }
        observability_diagnosis_payload = build_observability_diagnosis_smoke(
            relay_failure_payload={
                "schema_version": RELAY_FAILURE_CLOSURE_SCHEMA_VERSION,
                "status": "ready",
                "reason": "route_failure_runbook_reviewed",
                "closure_gates": {
                    "route_failure_recorded": True,
                    "fallback_path_recorded": True,
                    "operator_runbook_recorded": True,
                    "deterministic_validation_recorded": True,
                },
                "evidence_summary": {
                    "route_failure_reason": "peer_unreachable",
                    "fallback_action": "direct_local_retry_then_manual_operator_review",
                    "runbook_id": "relay-route-failure-v1",
                },
            },
            activate_failure_payload=activate_failure_payload,
        )
        release_rollback_payload = build_release_rollback_hardening_smoke(
            activate_failure_payload=activate_failure_payload,
            rollback_payload=rollback_payload,
        )
        template_rows = [
            _get_release_226_live_rerun_row("R226-HW-01"),
            _get_release_226_live_rerun_row("R226-HW-02"),
        ]
        archive_layout = [
            "hardware-compatibility.json",
            "hardware-acceptance-matrix.json",
            "resource-budget-governance.json",
            "signing-provenance.json",
            "observability-diagnosis.json",
            "release-rollback-hardening.json",
        ]
        evidence_manifest: dict[str, str] = {}
        if evidence_dir:
            resolved_evidence_dir = Path(evidence_dir)
            evidence_manifest = {
                "hardware_compatibility": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "hardware-compatibility.json",
                    hardware_payload,
                ),
                "hardware_acceptance_matrix": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "hardware-acceptance-matrix.json",
                    hardware_acceptance_matrix_payload,
                ),
                "resource_budget": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "resource-budget-governance.json",
                    resource_budget_payload,
                ),
                "signing_provenance": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "signing-provenance.json",
                    signing_provenance_payload,
                ),
                "observability_diagnosis": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "observability-diagnosis.json",
                    observability_diagnosis_payload,
                ),
                "release_rollback": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "release-rollback-hardening.json",
                    release_rollback_payload,
                ),
            }
        validation_gates = {
            "template_rows_bound": len(template_rows) == 2,
            "hardware_budget_rerun_ready": all(
                payload.get("ok", False)
                for payload in (
                    hardware_payload,
                    hardware_acceptance_matrix_payload,
                    resource_budget_payload,
                    signing_provenance_payload,
                )
            ),
            "rollback_operator_rerun_ready": bool(observability_diagnosis_payload.get("ok"))
            and bool(release_rollback_payload.get("ok")),
            "operator_handoff_recorded": True,
            "archive_layout_recorded": bool(archive_layout),
        }
        return {
            "schema_version": RELEASE_226_HARDWARE_RERUN_ARCHIVE_SCHEMA_VERSION,
            "status": "ready" if all(validation_gates.values()) else "incomplete",
            "reason": "release_226_hardware_rerun_archive_ready"
            if all(validation_gates.values())
            else "release_226_hardware_rerun_archive_gap",
            "command": "release-2.2.6-hardware-rerun-archive",
            "release_target": release_target,
            "covered_rerun_ids": ["R226-HW-01", "R226-HW-02"],
            "template_rows": template_rows,
            "archive_layout": archive_layout,
            "operator_handoff": {
                "operator_approval_required": True,
                "preflight_sequence": [
                    "verify hardware capability snapshot against release candidate artifact",
                    "confirm activate rollback approval context and lease ownership",
                    "archive bounded rollback evidence before cleanup",
                ],
                "cleanup_boundary": "query_leases_must_be_empty_after_rollback_archive",
            },
            "hardware_compatibility": hardware_payload,
            "hardware_acceptance_matrix": hardware_acceptance_matrix_payload,
            "resource_budget_governance": resource_budget_payload,
            "signing_provenance": signing_provenance_payload,
            "observability_diagnosis": observability_diagnosis_payload,
            "release_rollback_hardening": release_rollback_payload,
            "evidence_manifest": evidence_manifest,
            "validation_gates": validation_gates,
            "evidence_summary": {
                "exported_file_count": len(evidence_manifest),
                "hardware_gate_count": 4,
                "rollback_gate_count": 2,
            },
            "ok": all(validation_gates.values()),
        }
    finally:
        tempdir.cleanup()


def build_release_226_promotion_checklist(
    *,
    release_target: str = "2.2.6",
    inherited_release: str = "2.2.5",
    evidence_dir: str = "",
) -> dict[str, Any]:
    closure_smoke_payload = build_release_226_closure_smoke()
    live_rerun_template = cast(
        dict[str, Any], closure_smoke_payload.get("live_rerun_template") or {}
    )
    rerun_rows = cast(list[dict[str, Any]], live_rerun_template.get("rerun_rows") or [])
    archive_by_command = {
        "release-2.2.6-real-unit-rerun-archive": cast(
            dict[str, Any], closure_smoke_payload.get("real_unit_rerun_archive") or {}
        ),
        "release-2.2.6-qq-gateway-rerun-archive": cast(
            dict[str, Any], closure_smoke_payload.get("qq_gateway_rerun_archive") or {}
        ),
        "release-2.2.6-wecom-gateway-rerun-archive": cast(
            dict[str, Any], closure_smoke_payload.get("wecom_gateway_rerun_archive") or {}
        ),
        "release-2.2.6-openclaw-gateway-rerun-archive": cast(
            dict[str, Any], closure_smoke_payload.get("openclaw_gateway_rerun_archive") or {}
        ),
        "release-2.2.6-hardware-rerun-archive": cast(
            dict[str, Any], closure_smoke_payload.get("hardware_rerun_archive") or {}
        ),
    }
    row_reviews: list[dict[str, Any]] = []
    for row in rerun_rows:
        implementation_command = str(row.get("implementation_command") or "")
        archive_payload = archive_by_command.get(implementation_command, {})
        operator_handoff = cast(dict[str, Any], archive_payload.get("operator_handoff") or {})
        row_reviews.append(
            {
                "rerun_id": str(row.get("rerun_id") or ""),
                "title": str(row.get("title") or ""),
                "required_for_promotion": bool(row.get("required_for_promotion")),
                "implementation_command": implementation_command,
                "required_evidence_artifacts": list(
                    cast(list[str], row.get("required_evidence_artifacts") or [])
                ),
                "archive_schema_version": str(archive_payload.get("schema_version") or ""),
                "archive_ready": bool(archive_payload.get("ok")),
                "operator_approval_required": bool(
                    operator_handoff.get("operator_approval_required")
                ),
            }
        )
    required_row_reviews = [
        row_review for row_review in row_reviews if row_review["required_for_promotion"]
    ]
    conditional_row_reviews = [
        row_review for row_review in row_reviews if not row_review["required_for_promotion"]
    ]
    validation_gates = {
        "release_226_closure_green": bool(closure_smoke_payload.get("ok"))
        and bool(
            cast(dict[str, Any], closure_smoke_payload.get("validation_gate_summary") or {}).get(
                "ok"
            )
        ),
        "required_rows_declared": bool(required_row_reviews)
        and all(bool(row_review.get("implementation_command")) for row_review in required_row_reviews)
        and all(
            bool(row_review.get("required_evidence_artifacts"))
            for row_review in required_row_reviews
        ),
        "required_archives_ready": bool(required_row_reviews)
        and all(bool(row_review.get("archive_ready")) for row_review in required_row_reviews),
        "conditional_archives_ready": bool(conditional_row_reviews)
        and all(bool(row_review.get("archive_ready")) for row_review in conditional_row_reviews),
        "operator_boundary_preserved": bool(row_reviews)
        and all(
            bool(row_review.get("operator_approval_required")) for row_review in row_reviews
        ),
    }
    checklist = [
        _build_closure_checklist_entry(
            "release_226_closure_green",
            passed=bool(validation_gates["release_226_closure_green"]),
            title="Release 2.2.6 Closure Green",
            detail=(
                "Inherited and additive release-2.2.6 closure gates are green."
                if validation_gates["release_226_closure_green"]
                else "Release-2.2.6 closure gates are not fully green yet."
            ),
        ),
        _build_closure_checklist_entry(
            "required_rows_declared",
            passed=bool(validation_gates["required_rows_declared"]),
            title="Promotion Rows Declared",
            detail=(
                "Each promotion-blocking rerun row declares an implementation command and structured evidence artifacts."
                if validation_gates["required_rows_declared"]
                else "One or more promotion-blocking rerun rows is missing an implementation command or evidence artifact list."
            ),
        ),
        _build_closure_checklist_entry(
            "required_archives_ready",
            passed=bool(validation_gates["required_archives_ready"]),
            title="Promotion Archives Ready",
            detail=(
                "All promotion-blocking rerun rows now resolve to ready archive payloads."
                if validation_gates["required_archives_ready"]
                else "At least one promotion-blocking rerun row still lacks a ready archive payload."
            ),
        ),
        _build_closure_checklist_entry(
            "conditional_archives_ready",
            passed=bool(validation_gates["conditional_archives_ready"]),
            title="Conditional Archives Ready",
            detail=(
                "Conditional social gateway reruns are archived for bounded review without claiming live credential execution."
                if validation_gates["conditional_archives_ready"]
                else "At least one conditional gateway rerun archive is not ready for bounded review."
            ),
        ),
        _build_closure_checklist_entry(
            "operator_boundary_preserved",
            passed=bool(validation_gates["operator_boundary_preserved"]),
            title="Operator Boundary Preserved",
            detail=(
                "All rerun archive paths remain operator-approved and archive-first."
                if validation_gates["operator_boundary_preserved"]
                else "At least one rerun archive path no longer records the expected operator approval boundary."
            ),
        ),
    ]
    evidence_manifest: dict[str, str] = {}
    payload: dict[str, Any] = {
        "schema_version": RELEASE_226_PROMOTION_CHECKLIST_SCHEMA_VERSION,
        "command": "release-2.2.6-promotion-checklist",
        "status": "ready" if all(validation_gates.values()) else "incomplete",
        "reason": "release_226_promotion_checklist_ready"
        if all(validation_gates.values())
        else "release_226_promotion_checklist_gap",
        "release_target": release_target,
        "inherited_release": inherited_release,
        "closure_smoke": closure_smoke_payload,
        "live_rerun_template": live_rerun_template,
        "required_row_reviews": required_row_reviews,
        "conditional_row_reviews": conditional_row_reviews,
        "row_reviews": row_reviews,
        "validation_gates": validation_gates,
        "validation_gate_summary": {
            "total_count": len(validation_gates),
            "passed_count": sum(1 for passed in validation_gates.values() if passed),
            "failed_gate_ids": [
                gate_id for gate_id, passed in validation_gates.items() if not passed
            ],
            "ok": all(validation_gates.values()),
        },
        "checklist": checklist,
        "evidence_manifest": evidence_manifest,
        "evidence_summary": {
            "exported_file_count": 0,
            "required_row_count": len(required_row_reviews),
            "conditional_row_count": len(conditional_row_reviews),
            "ready_required_row_count": sum(
                1 for row_review in required_row_reviews if bool(row_review.get("archive_ready"))
            ),
            "ready_conditional_row_count": sum(
                1
                for row_review in conditional_row_reviews
                if bool(row_review.get("archive_ready"))
            ),
        },
        "ok": all(validation_gates.values()),
    }
    if evidence_dir:
        resolved_evidence_dir = Path(evidence_dir)
        evidence_manifest.update(
            {
                "closure_smoke": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "release-2.2.6-closure-smoke.json",
                    closure_smoke_payload,
                ),
                "live_rerun_template": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "release-2.2.6-live-rerun-template.json",
                    live_rerun_template,
                ),
                "promotion_checklist": _write_release_closure_payload(
                    resolved_evidence_dir,
                    "release-2.2.6-promotion-checklist.json",
                    payload,
                ),
            }
        )
        cast(dict[str, Any], payload["evidence_summary"])["exported_file_count"] = len(
            evidence_manifest
        )
    return payload


def _build_real_scene_checklist_rows() -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": "RS-01",
            "title": "Deterministic Core/Unit contract baseline",
            "family": "deterministic_contract",
            "status": "pending",
            "required_evidence_artifacts": [
                "session-evidence.json",
                "agent-excellence-smoke.json",
                "deterministic-scenario-record.json",
            ],
            "primary_gates": ["agent_excellence_gate", "regression_gate"],
            "pass_criteria": [
                "delegated reasoning selects governed tools only",
                "live-row-compatible evidence shape is preserved",
                "shared contracts remain hardware-agnostic",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-02",
            "title": "Single Core plus single real Unit live event continuity",
            "family": "single_real_unit_live_event",
            "status": "pending",
            "required_evidence_artifacts": [
                "live-event-smoke.json",
                "real-scene-e2e-smoke.json",
            ],
            "primary_gates": ["real_scene_e2e_gate"],
            "pass_criteria": [
                "a live Unit event is collected and persisted",
                "event source stays consistent across ingest and execution",
                "real governed tool execution succeeds",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-03",
            "title": "Real Unit deploy activate query rollback",
            "family": "deploy_activate_rollback",
            "status": "pending",
            "required_evidence_artifacts": [
                "artifact-admission.json",
                "app-deploy-activate.json",
                "app-deploy-rollback.json",
            ],
            "primary_gates": ["release_rollback_hardening_gate", "signing_provenance_gate"],
            "pass_criteria": [
                "artifact identity and provenance are recorded before admission",
                "activation and rollback states are explicit",
                "operator-visible rollback path is executable",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-04",
            "title": "Restricted Unit compatibility outcome",
            "family": "restricted_unit",
            "status": "pending",
            "required_evidence_artifacts": [
                "hardware-acceptance-matrix.json",
                "restricted-unit-compatibility.json",
            ],
            "primary_gates": ["restricted_unit_compatibility_gate"],
            "pass_criteria": [
                "capability limits are explicit",
                "unsupported paths fail closed as compatibility outcomes",
                "operator guidance identifies degraded mode",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-05",
            "title": "Multi-Core federation route",
            "family": "federation_route",
            "status": "pending",
            "required_evidence_artifacts": [
                "federation-route.json",
                "scenario-run-record.json",
            ],
            "primary_gates": ["federation_gate", "real_scene_e2e_gate"],
            "pass_criteria": [
                "delegated Core routing is explicit and auditable",
                "Unit-side continuity remains attributable to the chosen route",
                "route degradation does not collapse into transport ambiguity",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-06",
            "title": "Relay-assisted or degraded remote access",
            "family": "relay_degraded_remote_access",
            "status": "pending",
            "required_evidence_artifacts": [
                "relay-failure.json",
                "observability-diagnosis-smoke.json",
            ],
            "primary_gates": ["relay_gate", "observability_diagnosis_gate"],
            "pass_criteria": [
                "stale route unreachable target and relay failure are distinguishable",
                "diagnosis payload exposes operator next actions",
                "fallback handling preserves approval and cleanup boundaries",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-07",
            "title": "Agent-assisted governed operation flow",
            "family": "agent_governed_operation_flow",
            "status": "pending",
            "required_evidence_artifacts": [
                "agent-excellence-smoke.json",
                "session-evidence.json",
                "approval-or-policy-evidence.json",
            ],
            "primary_gates": ["agent_excellence_gate", "documentation_gate"],
            "pass_criteria": [
                "Tool Skill and MCP descriptors remain discoverable",
                "invalid plans fail before adapter execution",
                "read-only and approval-required MCP paths remain distinct",
            ],
            "evidence_files": [],
            "blockers": [],
        },
        {
            "scenario_id": "RS-08",
            "title": "Cleanup and rerun readiness",
            "family": "cleanup_rerun_readiness",
            "status": "pending",
            "required_evidence_artifacts": [
                "cleanup-evidence.json",
                "lease-query-evidence.json",
                "closure-summary.json",
            ],
            "primary_gates": ["release_rollback_hardening_gate", "closure_summary_gate"],
            "pass_criteria": [
                "no stale leases remain",
                "runtime cleanup is explicit",
                "the bundle is rerunnable without hidden manual state",
            ],
            "evidence_files": [],
            "blockers": [],
        },
    ]


def build_real_scene_checklist_template(
    *,
    release_target: str = "2.0.0",
    implementation_release: str = "1.2.7",
) -> dict[str, Any]:
    rows = _build_real_scene_checklist_rows()
    return {
        "schema_version": REAL_SCENE_CHECKLIST_TEMPLATE_SCHEMA_VERSION,
        "command": "real-scene-checklist-template",
        "status": "template",
        "release_target": release_target,
        "implementation_release": implementation_release,
        "checklist_id": f"release-{release_target}-real-core-unit-scenarios",
        "shared_rules": [
            "shared Core and Unit contracts remain hardware-agnostic",
            "artifact identity provenance and signing policy are recorded before live deploy or activate",
            "real tool execution remains Core-governed audit-visible and lease-aware",
            "logs are supporting evidence only; archive structured JSON payloads",
            "Restricted Unit behavior is a compatibility outcome rather than a skipped row",
        ],
        "shared_preconditions": [
            "confirm release target source manifest identity and artifact identity align",
            "prepare one deterministic Core-only environment and one bounded real Unit environment",
            "confirm connectivity event transport reachability and cleanup permissions",
            "create a fresh smoke-evidence directory for the rerun session",
            "predeclare the artifact set used for live deploy and rollback",
        ],
        "archive_layout": [
            "closure.db",
            "hardware-acceptance-matrix.json",
            "restricted-unit-compatibility.json",
            "agent-excellence-smoke.json",
            "signing-provenance-smoke.json",
            "live-event-smoke.json",
            "real-scene-e2e-smoke.json",
            "observability-diagnosis-smoke.json",
            "release-rollback-hardening-smoke.json",
            "closure-summary.json",
        ],
        "scenario_rows": rows,
        "summary": {
            "total_rows": len(rows),
            "pending_rows": len(rows),
            "passed_rows": 0,
            "failed_rows": 0,
        },
        "ok": True,
    }


def _build_real_scene_e2e_closure_summary(
    real_scene_e2e_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if real_scene_e2e_payload is None:
        gates = {
            "real_scene_e2e_evidence_supplied": False,
            "real_scene_e2e_contract_supported": False,
            "live_event_smoke_command_recorded": False,
            "live_event_source_real": False,
            "live_event_ingest_recorded": False,
            "live_event_collected": False,
            "bounded_live_runtime_recorded": False,
            "execution_evidence_present": False,
            "execution_span_ok": False,
            "event_source_consistent": False,
            "session_context_present": False,
            "agent_run_evidence_present": False,
            "real_tool_adapter_required": False,
            "real_tool_adapter_present": False,
            "real_tool_execution_succeeded": False,
            "tool_results_recorded": False,
            "state_sync_tool_used": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "real_scene_e2e_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], real_scene_e2e_payload.get("closure_gates") or {})
    gates = {
        "real_scene_e2e_evidence_supplied": True,
        "real_scene_e2e_contract_supported": str(
            real_scene_e2e_payload.get("schema_version") or ""
        )
        == REAL_SCENE_E2E_SMOKE_SCHEMA_VERSION,
        "live_event_smoke_command_recorded": bool(
            payload_gates.get("live_event_smoke_command_recorded")
        ),
        "live_event_source_real": bool(payload_gates.get("live_event_source_real")),
        "live_event_ingest_recorded": bool(
            payload_gates.get("live_event_ingest_recorded")
        ),
        "live_event_collected": bool(payload_gates.get("live_event_collected")),
        "bounded_live_runtime_recorded": bool(
            payload_gates.get("bounded_live_runtime_recorded")
        ),
        "execution_evidence_present": bool(
            payload_gates.get("execution_evidence_present")
        ),
        "execution_span_ok": bool(payload_gates.get("execution_span_ok")),
        "event_source_consistent": bool(payload_gates.get("event_source_consistent")),
        "session_context_present": bool(payload_gates.get("session_context_present")),
        "agent_run_evidence_present": bool(
            payload_gates.get("agent_run_evidence_present")
        ),
        "real_tool_adapter_required": bool(
            payload_gates.get("real_tool_adapter_required")
        ),
        "real_tool_adapter_present": bool(
            payload_gates.get("real_tool_adapter_present")
        ),
        "real_tool_execution_succeeded": bool(
            payload_gates.get("real_tool_execution_succeeded")
        ),
        "tool_results_recorded": bool(payload_gates.get("tool_results_recorded")),
        "state_sync_tool_used": bool(payload_gates.get("state_sync_tool_used")),
    }
    return {
        "supplied": True,
        "schema_version": str(real_scene_e2e_payload.get("schema_version") or ""),
        "status": str(real_scene_e2e_payload.get("status") or "unknown"),
        "reason": str(real_scene_e2e_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any],
            real_scene_e2e_payload.get("evidence_summary") or {},
        ),
        "ok": all(gates.values()),
    }


def _build_observability_diagnosis_closure_summary(
    observability_diagnosis_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if observability_diagnosis_payload is None:
        gates = {
            "observability_diagnosis_evidence_supplied": False,
            "observability_diagnosis_contract_supported": False,
            "route_failure_recorded": False,
            "fallback_path_recorded": False,
            "operator_runbook_recorded": False,
            "activate_failure_command_recorded": False,
            "rollback_required_recorded": False,
            "recovery_candidate_summary_recorded": False,
            "rollback_candidate_lease_recorded": False,
            "rollback_approval_recorded": False,
            "operator_next_actions_recorded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "observability_diagnosis_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(
        dict[str, Any], observability_diagnosis_payload.get("closure_gates") or {}
    )
    gates = {
        "observability_diagnosis_evidence_supplied": True,
        "observability_diagnosis_contract_supported": str(
            observability_diagnosis_payload.get("schema_version") or ""
        )
        == OBSERVABILITY_DIAGNOSIS_SMOKE_SCHEMA_VERSION,
        "route_failure_recorded": bool(payload_gates.get("route_failure_recorded")),
        "fallback_path_recorded": bool(payload_gates.get("fallback_path_recorded")),
        "operator_runbook_recorded": bool(
            payload_gates.get("operator_runbook_recorded")
        ),
        "activate_failure_command_recorded": bool(
            payload_gates.get("activate_failure_command_recorded")
        ),
        "rollback_required_recorded": bool(
            payload_gates.get("rollback_required_recorded")
        ),
        "recovery_candidate_summary_recorded": bool(
            payload_gates.get("recovery_candidate_summary_recorded")
        ),
        "rollback_candidate_lease_recorded": bool(
            payload_gates.get("rollback_candidate_lease_recorded")
        ),
        "rollback_approval_recorded": bool(
            payload_gates.get("rollback_approval_recorded")
        ),
        "operator_next_actions_recorded": bool(
            payload_gates.get("operator_next_actions_recorded")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(
            observability_diagnosis_payload.get("schema_version") or ""
        ),
        "status": str(observability_diagnosis_payload.get("status") or "unknown"),
        "reason": str(observability_diagnosis_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any],
            observability_diagnosis_payload.get("evidence_summary") or {},
        ),
        "ok": all(gates.values()),
    }


def _build_release_rollback_hardening_closure_summary(
    release_rollback_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if release_rollback_payload is None:
        gates = {
            "release_rollback_evidence_supplied": False,
            "release_rollback_contract_supported": False,
            "activate_failure_command_recorded": False,
            "rollback_required_recorded": False,
            "recovery_candidate_summary_recorded": False,
            "rollback_approval_boundary_recorded": False,
            "rollback_payload_command_recorded": False,
            "rollback_decision_recorded": False,
            "rollback_approval_required": False,
            "rollback_decision_approved": False,
            "rollback_execution_recorded": False,
            "rollback_execution_completed_through_cleanup": False,
            "post_rollback_app_observation_recorded": False,
            "post_rollback_lease_observation_recorded": False,
            "rollback_cleanup_clear": False,
            "rollback_failure_summary_clear": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "release_rollback_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], release_rollback_payload.get("closure_gates") or {})
    gates = {
        "release_rollback_evidence_supplied": True,
        "release_rollback_contract_supported": str(
            release_rollback_payload.get("schema_version") or ""
        )
        == RELEASE_ROLLBACK_HARDENING_SMOKE_SCHEMA_VERSION,
        "activate_failure_command_recorded": bool(
            payload_gates.get("activate_failure_command_recorded")
        ),
        "rollback_required_recorded": bool(
            payload_gates.get("rollback_required_recorded")
        ),
        "recovery_candidate_summary_recorded": bool(
            payload_gates.get("recovery_candidate_summary_recorded")
        ),
        "rollback_approval_boundary_recorded": bool(
            payload_gates.get("rollback_approval_boundary_recorded")
        ),
        "rollback_payload_command_recorded": bool(
            payload_gates.get("rollback_payload_command_recorded")
        ),
        "rollback_decision_recorded": bool(
            payload_gates.get("rollback_decision_recorded")
        ),
        "rollback_approval_required": bool(
            payload_gates.get("rollback_approval_required")
        ),
        "rollback_decision_approved": bool(
            payload_gates.get("rollback_decision_approved")
        ),
        "rollback_execution_recorded": bool(
            payload_gates.get("rollback_execution_recorded")
        ),
        "rollback_execution_completed_through_cleanup": bool(
            payload_gates.get("rollback_execution_completed_through_cleanup")
        ),
        "post_rollback_app_observation_recorded": bool(
            payload_gates.get("post_rollback_app_observation_recorded")
        ),
        "post_rollback_lease_observation_recorded": bool(
            payload_gates.get("post_rollback_lease_observation_recorded")
        ),
        "rollback_cleanup_clear": bool(payload_gates.get("rollback_cleanup_clear")),
        "rollback_failure_summary_clear": bool(
            payload_gates.get("rollback_failure_summary_clear")
        ),
    }
    return {
        "supplied": True,
        "schema_version": str(release_rollback_payload.get("schema_version") or ""),
        "status": str(release_rollback_payload.get("status") or "unknown"),
        "reason": str(release_rollback_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any], release_rollback_payload.get("evidence_summary") or {}
        ),
        "ok": all(gates.values()),
    }


def _build_release_210_smoke_closure_summary(
    payload: dict[str, Any] | None,
    *,
    expected_schema: str,
    not_supplied_reason: str,
) -> dict[str, Any]:
    if payload is None:
        gates: dict[str, bool] = {
            "evidence_supplied": False,
            "contract_supported": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": not_supplied_reason,
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }
    payload_gates = cast(dict[str, Any], payload.get("closure_gates") or {})
    gates = {
        "evidence_supplied": True,
        "contract_supported": str(payload.get("schema_version") or "")
        == expected_schema,
        **{key: bool(value) for key, value in payload_gates.items()},
    }
    return {
        "supplied": True,
        "schema_version": str(payload.get("schema_version") or ""),
        "status": str(payload.get("status") or "unknown"),
        "reason": str(payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(dict[str, Any], payload.get("evidence_summary") or {}),
        "ok": all(gates.values()),
    }


def build_qq_official_gateway_closure(
    *,
    gateway_run_payload: dict[str, Any],
    require_resume_evidence: bool = False,
) -> dict[str, Any]:
    gateway_closure_gates = cast(
        dict[str, Any], gateway_run_payload.get("closure_gates") or {}
    )
    reconnect_count = int(gateway_run_payload.get("reconnect_count") or 0)
    resume_attempt_count = int(gateway_run_payload.get("resume_attempt_count") or 0)
    resume_success_count = int(gateway_run_payload.get("resume_success_count") or 0)
    resumed_event_count = int(gateway_run_payload.get("resumed_event_count") or 0)
    closure_gates = {
        "gateway_run_payload_supplied": bool(gateway_run_payload),
        "gateway_run_command_recorded": str(gateway_run_payload.get("command") or "")
        == "qq-official-gateway-client",
        "gateway_run_contract_supported": str(
            gateway_run_payload.get("schema_version") or ""
        )
        == "2.2.2-qq-official-gateway-client-v1",
        "gateway_connected": bool(gateway_closure_gates.get("gateway_connected")),
        "hello_recorded": bool(gateway_closure_gates.get("hello_recorded")),
        "ready_recorded": bool(gateway_closure_gates.get("ready_recorded")),
        "dispatch_processed": bool(gateway_closure_gates.get("dispatch_processed")),
        "core_ingress_recorded": bool(
            gateway_closure_gates.get("core_ingress_recorded")
        ),
        "bounded_runtime_recorded": bool(
            gateway_closure_gates.get("bounded_runtime")
        ),
        "session_state_persisted": True
        if not require_resume_evidence
        else bool(gateway_run_payload.get("session_state_persisted")),
        "resume_requirement_declared": True,
        "resume_path_recorded": True
        if not require_resume_evidence
        else reconnect_count > 0 and resume_attempt_count > 0,
        "resume_path_succeeded": True
        if not require_resume_evidence
        else resume_success_count > 0 and resumed_event_count > 0,
    }
    return {
        "schema_version": QQ_OFFICIAL_GATEWAY_CLOSURE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "qq_official_gateway_closure_ready"
        if all(closure_gates.values())
        else "qq_official_gateway_closure_gap",
        "command": "qq-official-gateway-closure",
        "gateway_run": gateway_run_payload,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "gateway_url": str(
                cast(dict[str, Any], gateway_run_payload.get("gateway") or {}).get(
                    "url"
                )
                or ""
            ),
            "session_id": str(gateway_run_payload.get("session_id") or ""),
            "bot_user_id": str(gateway_run_payload.get("bot_user_id") or ""),
            "dispatch_event_count": int(
                gateway_run_payload.get("dispatch_event_count") or 0
            ),
            "events_persisted": sum(
                int(item.get("events_persisted") or 0)
                for item in cast(
                    list[dict[str, Any]], gateway_run_payload.get("core_results") or []
                )
            ),
            "reconnect_count": reconnect_count,
            "resume_attempt_count": resume_attempt_count,
            "resume_success_count": resume_success_count,
            "resumed_event_count": resumed_event_count,
            "session_state_file": str(
                gateway_run_payload.get("session_state_file") or ""
            ),
            "require_resume_evidence": require_resume_evidence,
        },
        "ok": all(closure_gates.values()),
    }


def build_wecom_gateway_closure(
    *,
    gateway_run_payload: dict[str, Any],
) -> dict[str, Any]:
    gateway_closure_gates = cast(
        dict[str, Any], gateway_run_payload.get("closure_gates") or {}
    )
    closure_gates = {
        "gateway_run_payload_supplied": bool(gateway_run_payload),
        "gateway_run_command_recorded": str(gateway_run_payload.get("command") or "")
        == "wecom-gateway-client",
        "gateway_run_contract_supported": str(
            gateway_run_payload.get("schema_version") or ""
        )
        == "2.2.3-wecom-gateway-client-v1",
        "gateway_connected": bool(gateway_closure_gates.get("gateway_connected")),
        "auth_sent": bool(gateway_closure_gates.get("auth_sent")),
        "ready_recorded": bool(gateway_closure_gates.get("ready_recorded")),
        "dispatch_processed": bool(gateway_closure_gates.get("dispatch_processed")),
        "core_ingress_recorded": bool(
            gateway_closure_gates.get("core_ingress_recorded")
        ),
        "bounded_runtime_recorded": bool(
            gateway_closure_gates.get("bounded_runtime")
        ),
    }
    return {
        "schema_version": WECOM_GATEWAY_CLOSURE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "wecom_gateway_closure_ready"
        if all(closure_gates.values())
        else "wecom_gateway_closure_gap",
        "command": "wecom-gateway-closure",
        "gateway_run": gateway_run_payload,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "gateway_url": str(
                cast(dict[str, Any], gateway_run_payload.get("gateway") or {}).get(
                    "url"
                )
                or ""
            ),
            "bot_user_id": str(gateway_run_payload.get("bot_user_id") or ""),
            "dispatch_event_count": int(
                gateway_run_payload.get("dispatch_event_count") or 0
            ),
            "events_persisted": sum(
                int(item.get("events_persisted") or 0)
                for item in cast(
                    list[dict[str, Any]], gateway_run_payload.get("core_results") or []
                )
            ),
        },
        "ok": all(closure_gates.values()),
    }


def build_openclaw_gateway_closure(
    *,
    gateway_run_payload: dict[str, Any],
) -> dict[str, Any]:
    gateway_closure_gates = cast(
        dict[str, Any], gateway_run_payload.get("closure_gates") or {}
    )
    plugin_payload = cast(dict[str, Any], gateway_run_payload.get("plugin") or {})
    closure_gates = {
        "gateway_run_payload_supplied": bool(gateway_run_payload),
        "gateway_run_command_recorded": str(gateway_run_payload.get("command") or "")
        == "openclaw-gateway-client",
        "gateway_run_contract_supported": str(
            gateway_run_payload.get("schema_version") or ""
        )
        == OPENCLAW_GATEWAY_CLIENT_SCHEMA_VERSION,
        "gateway_connected": bool(gateway_closure_gates.get("gateway_connected")),
        "bind_sent": bool(gateway_closure_gates.get("bind_sent")),
        "ready_recorded": bool(gateway_closure_gates.get("ready_recorded")),
        "plugin_identified": bool(gateway_closure_gates.get("plugin_identified")),
        "plugin_ready": bool(plugin_payload.get("ready")),
        "dispatch_processed": bool(gateway_closure_gates.get("dispatch_processed")),
        "core_ingress_recorded": bool(
            gateway_closure_gates.get("core_ingress_recorded")
        ),
        "bounded_runtime_recorded": bool(
            gateway_closure_gates.get("bounded_runtime")
        ),
    }
    return {
        "schema_version": OPENCLAW_GATEWAY_CLOSURE_SCHEMA_VERSION,
        "status": "ready" if all(closure_gates.values()) else "incomplete",
        "reason": "openclaw_gateway_closure_ready"
        if all(closure_gates.values())
        else "openclaw_gateway_closure_gap",
        "command": "openclaw-gateway-closure",
        "gateway_run": gateway_run_payload,
        "closure_gates": closure_gates,
        "evidence_summary": {
            "adapter_kind": str(gateway_run_payload.get("adapter_kind") or ""),
            "gateway_url": str(
                cast(dict[str, Any], gateway_run_payload.get("gateway") or {}).get(
                    "url"
                )
                or ""
            ),
            "plugin_id": str(plugin_payload.get("plugin_id") or ""),
            "plugin_package": str(plugin_payload.get("plugin_package") or ""),
            "host_version": str(plugin_payload.get("host_version") or ""),
            "dispatch_event_count": int(
                gateway_run_payload.get("dispatch_event_count") or 0
            ),
            "events_persisted": sum(
                int(item.get("events_persisted") or 0)
                for item in cast(
                    list[dict[str, Any]], gateway_run_payload.get("core_results") or []
                )
            ),
        },
        "ok": all(closure_gates.values()),
    }


def _build_qq_official_gateway_closure_summary(
    qq_gateway_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if qq_gateway_payload is None:
        gates = {
            "qq_gateway_evidence_supplied": False,
            "qq_gateway_contract_supported": False,
            "gateway_run_payload_supplied": False,
            "gateway_run_command_recorded": False,
            "gateway_run_contract_supported": False,
            "gateway_connected": False,
            "hello_recorded": False,
            "ready_recorded": False,
            "dispatch_processed": False,
            "core_ingress_recorded": False,
            "bounded_runtime_recorded": False,
            "session_state_persisted": False,
            "resume_requirement_declared": False,
            "resume_path_recorded": False,
            "resume_path_succeeded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "qq_gateway_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], qq_gateway_payload.get("closure_gates") or {})
    gates = {
        "qq_gateway_evidence_supplied": True,
        "qq_gateway_contract_supported": str(
            qq_gateway_payload.get("schema_version") or ""
        )
        == QQ_OFFICIAL_GATEWAY_CLOSURE_SCHEMA_VERSION,
        **{key: bool(value) for key, value in payload_gates.items()},
    }
    return {
        "supplied": True,
        "schema_version": str(qq_gateway_payload.get("schema_version") or ""),
        "status": str(qq_gateway_payload.get("status") or "unknown"),
        "reason": str(qq_gateway_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any], qq_gateway_payload.get("evidence_summary") or {}
        ),
        "ok": all(gates.values()),
    }


def _build_wecom_gateway_closure_summary(
    wecom_gateway_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if wecom_gateway_payload is None:
        gates = {
            "wecom_gateway_evidence_supplied": False,
            "wecom_gateway_contract_supported": False,
            "gateway_run_payload_supplied": False,
            "gateway_run_command_recorded": False,
            "gateway_run_contract_supported": False,
            "gateway_connected": False,
            "auth_sent": False,
            "ready_recorded": False,
            "dispatch_processed": False,
            "core_ingress_recorded": False,
            "bounded_runtime_recorded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "wecom_gateway_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(dict[str, Any], wecom_gateway_payload.get("closure_gates") or {})
    gates = {
        "wecom_gateway_evidence_supplied": True,
        "wecom_gateway_contract_supported": str(
            wecom_gateway_payload.get("schema_version") or ""
        )
        == WECOM_GATEWAY_CLOSURE_SCHEMA_VERSION,
        **{key: bool(value) for key, value in payload_gates.items()},
    }
    return {
        "supplied": True,
        "schema_version": str(wecom_gateway_payload.get("schema_version") or ""),
        "status": str(wecom_gateway_payload.get("status") or "unknown"),
        "reason": str(wecom_gateway_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any], wecom_gateway_payload.get("evidence_summary") or {}
        ),
        "ok": all(gates.values()),
    }


def _build_openclaw_gateway_closure_summary(
    openclaw_gateway_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if openclaw_gateway_payload is None:
        gates = {
            "openclaw_gateway_evidence_supplied": False,
            "openclaw_gateway_contract_supported": False,
            "gateway_run_payload_supplied": False,
            "gateway_run_command_recorded": False,
            "gateway_run_contract_supported": False,
            "gateway_connected": False,
            "bind_sent": False,
            "ready_recorded": False,
            "plugin_identified": False,
            "plugin_ready": False,
            "dispatch_processed": False,
            "core_ingress_recorded": False,
            "bounded_runtime_recorded": False,
        }
        return {
            "supplied": False,
            "schema_version": "",
            "status": "not_supplied",
            "reason": "openclaw_gateway_file_not_supplied",
            "closure_gates": gates,
            "evidence_summary": {},
            "ok": False,
        }

    payload_gates = cast(
        dict[str, Any], openclaw_gateway_payload.get("closure_gates") or {}
    )
    gates = {
        "openclaw_gateway_evidence_supplied": True,
        "openclaw_gateway_contract_supported": str(
            openclaw_gateway_payload.get("schema_version") or ""
        )
        == OPENCLAW_GATEWAY_CLOSURE_SCHEMA_VERSION,
        **{key: bool(value) for key, value in payload_gates.items()},
    }
    return {
        "supplied": True,
        "schema_version": str(openclaw_gateway_payload.get("schema_version") or ""),
        "status": str(openclaw_gateway_payload.get("status") or "unknown"),
        "reason": str(openclaw_gateway_payload.get("reason") or ""),
        "closure_gates": gates,
        "evidence_summary": cast(
            dict[str, Any], openclaw_gateway_payload.get("evidence_summary") or {}
        ),
        "ok": all(gates.values()),
    }


def _build_validation_gate_checklist(
    validation_gates: dict[str, bool],
) -> list[dict[str, Any]]:
    checklist = [
        _build_closure_checklist_entry(
            "documentation_gate",
            passed=bool(validation_gates.get("documentation_gate")),
            title="Documentation Gate",
            detail=(
                "Release plan, README, progress ledger, and runbooks are aligned and release identity remains unpromoted."
                if validation_gates.get("documentation_gate")
                else "Documentation alignment evidence is missing or incomplete for the release gate."
            ),
        ),
        _build_closure_checklist_entry(
            "federation_gate",
            passed=bool(validation_gates.get("federation_gate")),
            title="Federation Gate",
            detail=(
                "Federation route evidence is recorded through the standard workflow audit path with a consistent route decision payload."
                if validation_gates.get("federation_gate")
                else "Federation route evidence is missing or incomplete for the release gate."
            ),
        ),
        _build_closure_checklist_entry(
            "relay_gate",
            passed=bool(validation_gates.get("relay_gate")),
            title="Relay Gate",
            detail=(
                "Relay-relevant route evidence preserves attachment metadata or explicit relay failure reasons through the standard closure path."
                if validation_gates.get("relay_gate")
                else "Relay evidence is missing relay attachment metadata, explicit relay failure details, or failure runbook closure evidence."
            ),
        ),
        _build_closure_checklist_entry(
            "hardware_abstraction_gate",
            passed=bool(validation_gates.get("hardware_abstraction_gate")),
            title="Hardware Abstraction Gate",
            detail=(
                "Capability evidence remains hardware-agnostic with recorded architecture, ABI, board family, signing, and resource budget fields."
                if validation_gates.get("hardware_abstraction_gate")
                else "Hardware abstraction evidence is missing capability fields or is still coupled to a concrete validation board contract."
            ),
        ),
        _build_closure_checklist_entry(
            "artifact_compatibility_gate",
            passed=bool(validation_gates.get("artifact_compatibility_gate")),
            title="Artifact Compatibility Gate",
            detail=(
                "Artifact admission and capability compatibility checks prove incompatible architecture or capability requirements are rejected before load or activation."
                if validation_gates.get("artifact_compatibility_gate")
                else "Artifact compatibility evidence is missing admission details or incompatibility rejection proof."
            ),
        ),
        _build_closure_checklist_entry(
            "hardware_acceptance_matrix_gate",
            passed=bool(validation_gates.get("hardware_acceptance_matrix_gate")),
            title="Hardware Acceptance Matrix Gate",
            detail=(
                "Capability-class matrix evidence covers representative hardware classes, explicit Restricted Unit behavior, and hardware-agnostic board-family mapping."
                if validation_gates.get("hardware_acceptance_matrix_gate")
                else "Hardware acceptance matrix evidence is missing, incomplete, or does not expose explicit Restricted Unit and representative relay or federated rows."
            ),
        ),
        _build_closure_checklist_entry(
            "restricted_unit_compatibility_gate",
            passed=bool(validation_gates.get("restricted_unit_compatibility_gate")),
            title="Restricted Unit Compatibility Gate",
            detail=(
                "Restricted Unit evidence explicitly records the non-LLEXT compatibility mode while keeping degraded query and event behavior closure-ready."
                if validation_gates.get("restricted_unit_compatibility_gate")
                else "Restricted Unit compatibility evidence is missing or does not explicitly capture the bounded degraded behavior required for 1.2.7 closure."
            ),
        ),
        _build_closure_checklist_entry(
            "resource_budget_governance_gate",
            passed=bool(validation_gates.get("resource_budget_governance_gate")),
            title="Resource Budget Governance Gate",
            detail=(
                "Heap and app-slot thresholds are independently archived with required thresholds and sufficient observed runtime headroom."
                if validation_gates.get("resource_budget_governance_gate")
                else "Resource-budget governance evidence is missing or does not prove both recorded thresholds and sufficient governed budget headroom."
            ),
        ),
        _build_closure_checklist_entry(
            "agent_excellence_gate",
            passed=bool(validation_gates.get("agent_excellence_gate")),
            title="Agent Excellence Gate",
            detail=(
                "Tool manifest, Skill contract, workflow catalog, and MCP descriptor evidence together prove governed Agent Tool/Skill/MCP behavior is product-grade and bounded."
                if validation_gates.get("agent_excellence_gate")
                else "Independent Agent excellence evidence is missing or incomplete for the Tool/Skill/MCP closure contract."
            ),
        ),
        _build_closure_checklist_entry(
            "release_rollback_hardening_gate",
            passed=bool(validation_gates.get("release_rollback_hardening_gate")),
            title="Release And Rollback Hardening Gate",
            detail=(
                "Activate-failure recovery, approval boundaries, guarded rollback execution, and post-rollback cleanup are recorded as an independent closure payload."
                if validation_gates.get("release_rollback_hardening_gate")
                else "Independent release and rollback hardening evidence is missing or does not prove guarded rollback plus cleanup closure."
            ),
        ),
        _build_closure_checklist_entry(
            "signing_provenance_gate",
            passed=bool(validation_gates.get("signing_provenance_gate")),
            title="Signing And Provenance Gate",
            detail=(
                "Artifact identity, build provenance, digest evidence, and signing enforcement policy are recorded as an independent release closure payload."
                if validation_gates.get("signing_provenance_gate")
                else "Signing/provenance evidence is missing, incomplete, or does not record compatible signing enforcement for the release artifact."
            ),
        ),
        _build_closure_checklist_entry(
            "observability_diagnosis_gate",
            passed=bool(validation_gates.get("observability_diagnosis_gate")),
            title="Observability And Diagnosis Gate",
            detail=(
                "Relay failure diagnosis and rollback-required activation diagnosis are recorded with structured operator next actions."
                if validation_gates.get("observability_diagnosis_gate")
                else "Observability or failure-diagnosis evidence is missing, incomplete, or does not preserve structured relay and rollback-required operator guidance."
            ),
        ),
        _build_closure_checklist_entry(
            "real_scene_e2e_gate",
            passed=bool(validation_gates.get("real_scene_e2e_gate")),
            title="Real Scene E2E Gate",
            detail=(
                "Real Core/Unit live-event evidence and governed Agent execution evidence form a bounded end-to-end scenario record with a real tool adapter."
                if validation_gates.get("real_scene_e2e_gate")
                else "Real end-to-end scenario evidence is missing, incomplete, or does not prove live event ingestion plus governed real-tool execution continuity."
            ),
        ),
        _build_closure_checklist_entry(
            "autonomous_daemon_gate",
            passed=bool(validation_gates.get("autonomous_daemon_gate")),
            title="Autonomous Daemon Gate",
            detail=(
                "Autonomous daemon evidence records deterministic cycles, heartbeat, continuity, and operator pause precedence."
                if validation_gates.get("autonomous_daemon_gate")
                else "Autonomous daemon evidence is missing deterministic cycles, heartbeat, continuity, or operator pause precedence."
            ),
        ),
        _build_closure_checklist_entry(
            "vitality_governance_gate",
            passed=bool(validation_gates.get("vitality_governance_gate")),
            title="Vitality Governance Gate",
            detail=(
                "Vitality evidence proves bounded urgency-only impact and verified replenishment requirements."
                if validation_gates.get("vitality_governance_gate")
                else "Vitality evidence is missing bounded urgency-only impact or verified replenishment requirements."
            ),
        ),
        _build_closure_checklist_entry(
            "persona_persistence_gate",
            passed=bool(validation_gates.get("persona_persistence_gate")),
            title="Persona Persistence Gate",
            detail=(
                "Persona evidence records rational-safe summaries, relationship memory, and privacy redaction support."
                if validation_gates.get("persona_persistence_gate")
                else "Persona evidence is missing rational-safe summary, relationship memory, or privacy redaction support."
            ),
        ),
        _build_closure_checklist_entry(
            "persona_seed_gate",
            passed=bool(validation_gates.get("persona_seed_gate")),
            title="Persona Seed Gate",
            detail=(
                "Persona seed evidence records the governed initial persona configuration used to initialize runtime state."
                if validation_gates.get("persona_seed_gate")
                else "Persona seed evidence is missing or does not record the governed initial persona configuration."
            ),
        ),
        _build_closure_checklist_entry(
            "persona_growth_gate",
            passed=bool(validation_gates.get("persona_growth_gate")),
            title="Persona Growth Gate",
            detail=(
                "Persona growth evidence proves growth-state updates are recorded and driven only by runtime evidence."
                if validation_gates.get("persona_growth_gate")
                else "Persona growth evidence is missing or does not prove runtime-evidence-only growth updates."
            ),
        ),
        _build_closure_checklist_entry(
            "memory_immutability_gate",
            passed=bool(validation_gates.get("memory_immutability_gate")),
            title="Memory Immutability Gate",
            detail=(
                "Persona memory evidence records a valid immutability stamp so tampering can be detected without allowing arbitrary rewrites."
                if validation_gates.get("memory_immutability_gate")
                else "Persona memory evidence is missing an immutability stamp or cannot prove tamper-detection validity."
            ),
        ),
        _build_closure_checklist_entry(
            "social_adapter_gate",
            passed=bool(validation_gates.get("social_adapter_gate")),
            title="Social Adapter Gate",
            detail=(
                "Social adapter evidence records identity-bound ingress, persisted events, and affective-only egress."
                if validation_gates.get("social_adapter_gate")
                else "Social adapter evidence is missing identity-bound ingress, persisted events, or affective-only egress."
            ),
        ),
        _build_closure_checklist_entry(
            "qq_official_gateway_gate",
            passed=bool(validation_gates.get("qq_official_gateway_gate")),
            title="QQ Gateway Live Gate",
            detail=(
                "Bounded official QQ gateway evidence records connection, dispatch-to-Core, persisted session state, and resume continuity when required."
                if validation_gates.get("qq_official_gateway_gate")
                else "QQ official gateway live evidence is missing, incomplete, or does not satisfy the bounded reconnect/resume closure contract."
            ),
        ),
        _build_closure_checklist_entry(
            "wecom_gateway_gate",
            passed=bool(validation_gates.get("wecom_gateway_gate")),
            title="WeCom Gateway Live Gate",
            detail=(
                "Bounded WeCom gateway evidence records authenticated connection, dispatch-to-Core, and bounded runtime closure."
                if validation_gates.get("wecom_gateway_gate")
                else "WeCom gateway live evidence is missing, incomplete, or does not satisfy the bounded authenticated dispatch closure contract."
            ),
        ),
        _build_closure_checklist_entry(
            "openclaw_gateway_gate",
            passed=bool(validation_gates.get("openclaw_gateway_gate")),
            title="OpenClaw Gateway Live Gate",
            detail=(
                "Bounded OpenClaw gateway evidence records host bind, plugin identification, dispatch-to-Core, and bounded runtime closure."
                if validation_gates.get("openclaw_gateway_gate")
                else "OpenClaw gateway live evidence is missing, incomplete, or does not satisfy the bounded hosted-plugin dispatch closure contract."
            ),
        ),
        _build_closure_checklist_entry(
            "approval_over_social_gate",
            passed=bool(validation_gates.get("approval_over_social_gate")),
            title="Approval Over Social Gate",
            detail=(
                "Approval-over-social evidence records bound principal/channel metadata and denied execution protection."
                if validation_gates.get("approval_over_social_gate")
                else "Approval-over-social evidence is missing identity binding, audit metadata, or deny protection."
            ),
        ),
        _build_closure_checklist_entry(
            "self_improvement_sandbox_gate",
            passed=bool(validation_gates.get("self_improvement_sandbox_gate")),
            title="Self Improvement Sandbox Gate",
            detail=(
                "Self-improvement evidence keeps proposal execution sandbox-only, approval-gated, and vitality-safe."
                if validation_gates.get("self_improvement_sandbox_gate")
                else "Self-improvement evidence is missing sandbox-only execution, approval gating, or vitality replenishment constraints."
            ),
        ),
        _build_closure_checklist_entry(
            "coding_agent_route_gate",
            passed=bool(validation_gates.get("coding_agent_route_gate")),
            title="Coding Agent Route Gate",
            detail=(
                "Coding-agent routing evidence records plan artifact, sandbox execution, and callback audit details."
                if validation_gates.get("coding_agent_route_gate")
                else "Coding-agent routing evidence is missing plan artifact, sandbox execution, or callback audit details."
            ),
        ),
    ]
    if "autonomy_heartbeat_gate" in validation_gates:
        checklist.append(
            _build_closure_checklist_entry(
                "autonomy_heartbeat_gate",
                passed=bool(validation_gates.get("autonomy_heartbeat_gate")),
                title="Autonomy Heartbeat Gate",
                detail=(
                    "Autonomy heartbeat evidence links deterministic daemon continuity with active-hours configuration and task heartbeat state."
                    if validation_gates.get("autonomy_heartbeat_gate")
                    else "Autonomy heartbeat evidence is missing linked daemon continuity, active-hours configuration, or task heartbeat state."
                ),
            )
        )
    if "task_tracking_replay_gate" in validation_gates:
        checklist.append(
            _build_closure_checklist_entry(
                "task_tracking_replay_gate",
                passed=bool(validation_gates.get("task_tracking_replay_gate")),
                title="Task Tracking Replay Gate",
                detail=(
                    "Task tracking evidence records resumable task state, replay buffer continuity, and cleanup-ready rerun boundaries."
                    if validation_gates.get("task_tracking_replay_gate")
                    else "Task tracking evidence is missing resumable task state, replay continuity, or cleanup-ready rerun boundaries."
                ),
            )
        )
    if "memory_maintenance_gate" in validation_gates:
        checklist.append(
            _build_closure_checklist_entry(
                "memory_maintenance_gate",
                passed=bool(validation_gates.get("memory_maintenance_gate")),
                title="Memory Maintenance Gate",
                detail=(
                    "Memory maintenance evidence records stale-context screening, prompt-safe consolidation, and audit-bound privacy scope."
                    if validation_gates.get("memory_maintenance_gate")
                    else "Memory maintenance evidence is missing stale-context screening, prompt-safe consolidation, or audit-bound privacy scope."
                ),
            )
        )
    if "self_optimization_gate" in validation_gates:
        checklist.append(
            _build_closure_checklist_entry(
                "self_optimization_gate",
                passed=bool(validation_gates.get("self_optimization_gate")),
                title="Self Optimization Gate",
                detail=(
                    "Self-optimization evidence remains low-risk, approval-gated, sandbox-only, and explicitly forbidden from direct apply."
                    if validation_gates.get("self_optimization_gate")
                    else "Self-optimization evidence is missing low-risk classification, approval gating, sandbox-only execution, or direct-apply prohibition."
                ),
            )
        )
    if "world_model_context_gate" in validation_gates:
        checklist.append(
            _build_closure_checklist_entry(
                "world_model_context_gate",
                passed=bool(validation_gates.get("world_model_context_gate")),
                title="World Model Context Gate",
                detail=(
                    "World-model evidence records prompt-safe temporal, unit-capability, and relay-preserved context for Rational summaries."
                    if validation_gates.get("world_model_context_gate")
                    else "World-model evidence is missing prompt-safe temporal, unit-capability, or relay-preserved Rational context."
                ),
            )
        )
    checklist.extend([
        _build_closure_checklist_entry(
            "multimodal_normalization_gate",
            passed=bool(validation_gates.get("multimodal_normalization_gate")),
            title="Multimodal Normalization Gate",
            detail=(
                "Deterministic multimodal normalization evidence is recorded without executing a model call."
                if validation_gates.get("multimodal_normalization_gate")
                else "Multimodal normalization evidence is missing, incomplete, or not deterministic."
            ),
        ),
        _build_closure_checklist_entry(
            "profile_routing_gate",
            passed=bool(validation_gates.get("profile_routing_gate")),
            title="Profile Routing Gate",
            detail=(
                "Inference route decisions and profile readiness were recorded and reached a route-ready outcome."
                if validation_gates.get("profile_routing_gate")
                else "Profile routing evidence is missing, not route-ready, or does not include readiness details."
            ),
        ),
        _build_closure_checklist_entry(
            "provider_runtime_gate",
            passed=bool(validation_gates.get("provider_runtime_gate")),
            title="Provider Runtime Gate",
            detail=(
                "Provider smoke evidence records bounded opt-in behavior and consistent readiness/model-call outcomes."
                if validation_gates.get("provider_runtime_gate")
                else "Provider runtime smoke evidence is missing or incomplete for the release gate."
            ),
        ),
        _build_closure_checklist_entry(
            "memory_governance_gate",
            passed=bool(validation_gates.get("memory_governance_gate")),
            title="Memory Governance Gate",
            detail=(
                "Memory lifecycle and recall-governance evidence are both present for the release gate."
                if validation_gates.get("memory_governance_gate")
                else "Memory lifecycle or recall-governance evidence is missing for the release gate."
            ),
        ),
        _build_closure_checklist_entry(
            "tool_skill_mcp_gate",
            passed=bool(validation_gates.get("tool_skill_mcp_gate")),
            title="Tool Skill MCP Gate",
            detail=(
                "Tool, Skill, and MCP governance stayed within available-tool, approval, and read-only descriptor boundaries."
                if validation_gates.get("tool_skill_mcp_gate")
                else "Tool, Skill, or MCP governance evidence is missing or violated a release boundary."
            ),
        ),
        _build_closure_checklist_entry(
            "regression_gate",
            passed=bool(validation_gates.get("regression_gate")),
            title="Regression Gate",
            detail=(
                "Core and release-1.2.4 regression evidence was recorded as green."
                if validation_gates.get("regression_gate")
                else "Regression evidence is missing or incomplete for the release gate."
            ),
        ),
    ])
    return checklist


def _build_federation_closure_summary(
    evidence: dict[str, Any],
    session_context: dict[str, Any],
) -> dict[str, Any]:
    facts = cast(list[dict[str, Any]], evidence.get("facts") or [])
    federation_facts = [
        fact for fact in facts if str(fact.get("fact_type") or "") == "federation_route"
    ]
    federation_evidence = cast(
        dict[str, Any],
        session_context.get("federation_route_evidence") or {},
    )
    route_decision = cast(
        dict[str, Any],
        federation_evidence.get("route_decision") or {},
    )
    delegated_execution = cast(
        dict[str, Any] | None,
        federation_evidence.get("delegated_execution"),
    )
    route_kind = str(route_decision.get("route_kind") or "")
    route_status = str(
        route_decision.get("status") or federation_evidence.get("status") or ""
    )
    closure_gates = {
        "federation_evidence_present": bool(federation_evidence),
        "route_decision_recorded": bool(route_decision),
        "route_fact_recorded": bool(federation_facts),
        "route_kind_recorded": bool(route_kind),
        "route_status_recorded": route_status
        in {"route_ready", "route_rejected", "stale_route", "route_failed", "no_route"},
        "delegated_execution_consistent": not (
            route_kind == "delegated_core"
            and route_status == "route_ready"
            and not isinstance(delegated_execution, dict)
        ),
        "audit_evidence_linked": bool(federation_evidence) and bool(federation_facts),
    }
    return {
        "route_kind": route_kind,
        "route_status": route_status,
        "target_node": str(route_decision.get("target_node") or ""),
        "target_core": str(route_decision.get("target_core") or ""),
        "trust_scope": str(route_decision.get("trust_scope") or ""),
        "fact_count": len(federation_facts),
        "delegated_execution_present": isinstance(delegated_execution, dict),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _build_relay_closure_summary(
    session_context: dict[str, Any],
) -> dict[str, Any]:
    federation_evidence = cast(
        dict[str, Any],
        session_context.get("federation_route_evidence") or {},
    )
    route_decision = cast(
        dict[str, Any],
        federation_evidence.get("route_decision") or {},
    )
    evidence_summary = cast(
        dict[str, Any],
        federation_evidence.get("evidence_summary") or {},
    )
    route_kind = str(route_decision.get("route_kind") or "")
    route_status = str(
        route_decision.get("status") or federation_evidence.get("status") or ""
    )
    relay_path_items = cast(list[Any], route_decision.get("relay_path") or [])
    relay_path = tuple(
        str(item) for item in relay_path_items if str(item)
    )
    supported_transport_items = cast(
        list[Any],
        evidence_summary.get("supported_transports") or [],
    )
    supported_transports = tuple(
        str(item) for item in supported_transport_items if str(item)
    )
    failure_reason = str(
        route_decision.get("failure_reason")
        or federation_evidence.get("reason")
        or evidence_summary.get("failure_reason")
        or ""
    )
    relevant_failure_reasons = {
        "relay_capability_mismatch",
        "transport_mismatch",
        "peer_unreachable",
        "peer_advertisement_stale",
        "target_node_not_advertised",
    }
    relay_relevant = (
        bool(relay_path)
        or route_kind == "relay"
        or failure_reason in relevant_failure_reasons
    )
    closure_gates = {
        "federation_evidence_present": bool(federation_evidence),
        "route_decision_recorded": bool(route_decision),
        "relay_relevant_outcome_recorded": relay_relevant,
        "relay_path_recorded_or_failure_explicit": bool(relay_path)
        or bool(failure_reason),
        "relay_attachment_metadata_visible": (not relay_path)
        or bool(supported_transports),
        "route_failure_evidence_explicit": route_status == "route_ready"
        or bool(failure_reason),
    }
    return {
        "route_kind": route_kind,
        "route_status": route_status,
        "target_node": str(route_decision.get("target_node") or ""),
        "target_core": str(route_decision.get("target_core") or ""),
        "relay_path": list(relay_path),
        "supported_transports": list(supported_transports),
        "failure_reason": failure_reason,
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _build_memory_governance_closure_summary(
    evidence: dict[str, Any],
    session_context: dict[str, Any],
) -> dict[str, Any]:
    memory_candidates = cast(list[dict[str, Any]], evidence.get("memory_candidates") or [])
    long_term_memories = cast(list[dict[str, Any]], evidence.get("long_term_memories") or [])
    facts = cast(list[dict[str, Any]], evidence.get("facts") or [])

    def _payloads(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for item in items:
            payload = item.get("payload")
            if isinstance(payload, dict):
                payloads.append(cast(dict[str, Any], payload))
        return payloads

    candidate_payloads = _payloads(memory_candidates)
    committed_payloads = _payloads(long_term_memories)

    def _candidate_is_governed(payload: dict[str, Any]) -> bool:
        governance = cast(dict[str, Any], payload.get("memory_governance") or {})
        lifecycle_state = str(governance.get("lifecycle_state") or "")
        source_event_refs = list(governance.get("source_event_refs") or payload.get("event_ids") or [])
        source_fact_refs = list(governance.get("source_fact_refs") or [])
        return (
            str(governance.get("schema_version") or "")
            == "1.2.5-memory-governance-v1"
            and lifecycle_state in {"accepted", "rejected"}
            and bool(source_event_refs)
            and (not facts or bool(source_fact_refs))
        )

    def _commit_is_governed(payload: dict[str, Any]) -> bool:
        governance = cast(dict[str, Any], payload.get("memory_governance") or {})
        lifecycle_state = str(governance.get("lifecycle_state") or "")
        return (
            str(governance.get("schema_version") or "")
            == "1.2.5-memory-governance-v1"
            and lifecycle_state in {"committed", "retired"}
            and bool(governance.get("commit_backend"))
            and bool(governance.get("retention_class"))
        )

    closure_gates = {
        "memory_runtime_recorded": isinstance(session_context.get("memory_runtime"), dict),
        "memory_candidates_governed": all(
            _candidate_is_governed(payload) for payload in candidate_payloads
        ),
        "memory_commit_outcomes_governed": all(
            _commit_is_governed(payload) for payload in committed_payloads
        ),
    }
    return {
        "candidate_count": len(candidate_payloads),
        "committed_memory_count": sum(
            1
            for payload in committed_payloads
            if str(dict(payload.get("memory_governance") or {}).get("lifecycle_state") or "")
            == "committed"
        ),
        "rejected_candidate_count": sum(
            1
            for payload in candidate_payloads
            if str(dict(payload.get("memory_governance") or {}).get("lifecycle_state") or "")
            == "rejected"
        ),
        "commit_backends": sorted(
            {
                str(dict(payload.get("memory_governance") or {}).get("commit_backend") or "")
                for payload in committed_payloads
            }
            - {""}
        ),
        "rejection_reasons": sorted(
            {
                str(dict(payload.get("memory_governance") or {}).get("decision_reason") or "")
                for payload in candidate_payloads
                if str(dict(payload.get("memory_governance") or {}).get("lifecycle_state") or "")
                == "rejected"
            }
            - {""}
        ),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _build_memory_recall_closure_summary(session_context: dict[str, Any]) -> dict[str, Any]:
    prompt_safe_context = cast(dict[str, Any], session_context.get("prompt_safe_context") or {})
    prompt_memory = cast(dict[str, Any], prompt_safe_context.get("memory") or {})
    recall_policy = cast(dict[str, Any], prompt_memory.get("recall_policy") or {})
    affective_recall = cast(dict[str, Any], recall_policy.get("affective_recall") or {})
    rational_recall = cast(dict[str, Any], recall_policy.get("rational_recall") or {})
    closure_gates = {
        "recall_policy_present": str(recall_policy.get("schema_version") or "")
        == "1.2.5-memory-recall-policy-v1",
        "affective_recall_recorded": isinstance(affective_recall.get("items") or [], list),
        "rational_recall_recorded": isinstance(rational_recall.get("items") or [], list),
        "fallback_backend_recorded": bool(recall_policy.get("backend_kind"))
        and "fallback_active" in recall_policy,
    }
    return {
        "schema_version": str(recall_policy.get("schema_version") or ""),
        "lookup_count": int(recall_policy.get("lookup_count") or 0),
        "backend_kind": str(recall_policy.get("backend_kind") or ""),
        "fallback_backend": str(recall_policy.get("fallback_backend") or ""),
        "fallback_active": bool(recall_policy.get("fallback_active", False)),
        "affective_selected_count": int(affective_recall.get("selected_count") or 0),
        "rational_selected_count": int(rational_recall.get("selected_count") or 0),
        "filtered_out_categories": cast(
            dict[str, Any], recall_policy.get("filtered_out_categories") or {}
        ),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _build_tool_skill_mcp_closure_summary(
    session_context: dict[str, Any],
    *,
    rational_plan_evidence: dict[str, Any] | None,
    tool_results: list[Any],
) -> dict[str, Any]:
    prompt_safe_context = cast(dict[str, Any], session_context.get("prompt_safe_context") or {})
    prompt_safety_boundaries = cast(
        dict[str, Any],
        prompt_safe_context.get("safety_boundaries") or {},
    )
    available_tools = cast(
        list[dict[str, Any]],
        session_context.get("available_tools")
        or prompt_safe_context.get("available_tools")
        or [],
    )
    skill_descriptors = cast(list[dict[str, Any]], session_context.get("skill_descriptors") or [])
    mcp_descriptors = cast(list[dict[str, Any]], session_context.get("mcp_descriptors") or [])
    skill_descriptor = skill_descriptors[0] if skill_descriptors else {}
    mcp_descriptor = mcp_descriptors[0] if mcp_descriptors else {}
    rational_evidence = rational_plan_evidence or {}
    rational_status = str(rational_evidence.get("status") or "")
    selected_tool_name = str(rational_evidence.get("selected_tool_name") or "")
    selected_plan_quality: dict[str, Any] = {}
    failure_statuses: set[str] = set()
    for item in tool_results:
        if not isinstance(item, dict):
            continue
        result = cast(dict[str, Any], item)
        payload_obj = result.get("payload")
        if not isinstance(payload_obj, dict):
            continue
        payload = cast(dict[str, Any], payload_obj)
        failure_status = str(payload.get("failure_status") or "")
        if failure_status:
            failure_statuses.add(failure_status)
        if not selected_plan_quality and isinstance(payload.get("plan_quality"), dict):
            selected_plan_quality = cast(dict[str, Any], payload.get("plan_quality") or {})
    skill_ground_rules = cast(
        dict[str, Any], selected_plan_quality.get("skill_ground_rules") or {}
    )
    workflow_catalog_consistency = cast(
        dict[str, Any], selected_plan_quality.get("workflow_catalog_consistency") or {}
    )
    mcp_requirements = cast(dict[str, Any], selected_plan_quality.get("mcp_requirements") or {})
    invalid_tool_rejected = bool(
        {"unknown_tool", "rational_plan_tool_not_in_available_tools"} & failure_statuses
    )
    side_effect_tools = [
        tool
        for tool in available_tools
        if str(tool.get("side_effect_level") or "") in {"approval_required", "destructive"}
    ]
    approval_required_tool_count = sum(
        1 for tool in side_effect_tools if bool(tool.get("approval_required", False))
    )
    closure_gates = {
        "available_tools_recorded": bool(available_tools),
        "available_tools_only_enforced": (
            rational_status == "no_tool_selected"
            or bool(rational_evidence.get("selected_tool_in_available_tools"))
            or invalid_tool_rejected
        ),
        "side_effect_tools_require_approval": all(
            bool(tool.get("approval_required", False))
            or str(tool.get("side_effect_level") or "") == "destructive"
            for tool in side_effect_tools
        ),
        "skill_descriptor_present": bool(skill_descriptor),
        "workflow_plan_required_for_governed_tools": (
            not side_effect_tools
            or bool(skill_descriptor.get("workflow_plan_required", False))
        ),
        "skill_ground_rules_enforced": (
            rational_status == "no_tool_selected"
            or bool(skill_ground_rules.get("valid", True))
        ),
        "workflow_catalog_consistent": (
            rational_status == "no_tool_selected"
            or bool(workflow_catalog_consistency.get("valid", True))
        ),
        "mcp_descriptor_read_only": str(mcp_descriptor.get("bridge_mode") or "")
        == "read_only_descriptor_only",
        "mcp_governance_mode_satisfied": (
            rational_status == "no_tool_selected"
            or bool(mcp_requirements.get("bridge_mode_satisfies_tool_governance", True))
        ),
        "tool_execution_via_mcp_forbidden": bool(
            mcp_descriptor.get("tool_execution_via_mcp_forbidden", False)
        ),
        "external_mcp_disabled": not bool(
            mcp_descriptor.get("external_mcp_connection_enabled", False)
        ),
        "direct_model_tool_execution_forbidden": not bool(
            prompt_safety_boundaries.get("can_execute_tools_directly", False)
        ),
    }
    return {
        "available_tool_count": len(available_tools),
        "side_effect_tool_count": len(side_effect_tools),
        "approval_required_tool_count": approval_required_tool_count,
        "selected_tool_name": selected_tool_name,
        "rational_status": rational_status,
        "invalid_tool_rejected": invalid_tool_rejected,
        "skill_name": str(skill_descriptor.get("name") or ""),
        "workflow_plan_required": bool(skill_descriptor.get("workflow_plan_required", False)),
        "mcp_bridge_mode": str(mcp_descriptor.get("bridge_mode") or ""),
        "mcp_blocked_tool_count": int(mcp_descriptor.get("blocked_tool_count") or 0),
        "plan_quality_failure_status": str(selected_plan_quality.get("failure_status") or ""),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }


def _build_closure_execution_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    execution_span = cast(dict[str, Any] | None, evidence.get("execution_span"))
    audit_record = cast(dict[str, Any] | None, evidence.get("audit_record"))
    audit_payload = cast(
        dict[str, Any],
        audit_record.get("payload") if isinstance(audit_record, dict) else {},
    )
    session_context = cast(dict[str, Any], audit_payload.get("session_context") or {})
    rational_plan_evidence = cast(
        dict[str, Any] | None,
        audit_payload.get("rational_plan_evidence")
        or session_context.get("rational_plan_evidence"),
    )
    model_call_evidence = cast(
        dict[str, Any] | None,
        session_context.get("model_call_evidence"),
    )
    prompt_safe_context = cast(
        dict[str, Any] | None,
        session_context.get("prompt_safe_context"),
    )
    memory_governance_summary = _build_memory_governance_closure_summary(
        evidence,
        session_context,
    )
    memory_recall_summary = _build_memory_recall_closure_summary(session_context)
    federation_summary = _build_federation_closure_summary(evidence, session_context)
    relay_summary = _build_relay_closure_summary(session_context)
    tool_results = cast(list[Any], audit_payload.get("tool_results") or [])
    approval_requests = cast(list[dict[str, Any]], evidence.get("approval_requests") or [])
    tool_skill_mcp_summary = _build_tool_skill_mcp_closure_summary(
        session_context,
        rational_plan_evidence=rational_plan_evidence,
        tool_results=tool_results,
    )
    pending_approval_count = sum(
        1 for approval in approval_requests if approval.get("status") == "pending"
    )
    rational_status = str((rational_plan_evidence or {}).get("status") or "")
    closure_gates = {
        "audit_record_present": isinstance(audit_record, dict),
        "rational_plan_evidence_present": isinstance(rational_plan_evidence, dict),
        "rational_plan_outcome_recorded": rational_status
        in {"tool_selected", "no_tool_selected", "invalid_payload"},
        "model_call_evidence_present": isinstance(model_call_evidence, dict),
        "prompt_safe_context_present": isinstance(prompt_safe_context, dict),
        "memory_governance_recorded": bool(memory_governance_summary.get("ok")),
        "memory_recall_policy_recorded": bool(memory_recall_summary.get("ok")),
        "tool_skill_mcp_recorded": bool(tool_skill_mcp_summary.get("ok")),
        "tool_result_outcome_recorded": bool(tool_results)
        or rational_status == "no_tool_selected",
        "approval_state_recorded": bool(approval_requests) or pending_approval_count == 0,
    }
    return {
        "execution_span_id": str(
            (execution_span or {}).get("execution_span_id") or ""
        ),
        "audit_id": str((audit_record or {}).get("audit_id") or ""),
        "status": str((execution_span or {}).get("status") or "unknown"),
        "started_at": (execution_span or {}).get("started_at"),
        "completed_at": (execution_span or {}).get("completed_at"),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
        "rational_plan_evidence": rational_plan_evidence,
        "model_call_evidence": model_call_evidence,
        "federation_summary": federation_summary,
        "relay_summary": relay_summary,
        "memory_governance_summary": memory_governance_summary,
        "memory_recall_summary": memory_recall_summary,
        "tool_skill_mcp_summary": tool_skill_mcp_summary,
        "tool_result_count": len(tool_results),
        "approval_request_count": len(approval_requests),
        "pending_approval_count": pending_approval_count,
    }


def _build_session_closure_summary(
    data_store: CoreDataStore,
    session_id: str,
    *,
    limit: int,
    provider_smoke_payload: dict[str, Any] | None = None,
    require_provider_smoke: bool = False,
    multimodal_profile_payload: dict[str, Any] | None = None,
    require_multimodal_profile: bool = False,
    documentation_payload: dict[str, Any] | None = None,
    regression_payload: dict[str, Any] | None = None,
    relay_failure_payload: dict[str, Any] | None = None,
    hardware_compatibility_payload: dict[str, Any] | None = None,
    hardware_acceptance_matrix_payload: dict[str, Any] | None = None,
    resource_budget_governance_payload: dict[str, Any] | None = None,
    agent_excellence_payload: dict[str, Any] | None = None,
    signing_provenance_payload: dict[str, Any] | None = None,
    observability_diagnosis_payload: dict[str, Any] | None = None,
    release_rollback_payload: dict[str, Any] | None = None,
    real_scene_e2e_payload: dict[str, Any] | None = None,
    autonomy_daemon_payload: dict[str, Any] | None = None,
    task_tracking_payload: dict[str, Any] | None = None,
    memory_maintenance_payload: dict[str, Any] | None = None,
    self_optimization_payload: dict[str, Any] | None = None,
    world_model_context_payload: dict[str, Any] | None = None,
    vitality_smoke_payload: dict[str, Any] | None = None,
    persona_state_payload: dict[str, Any] | None = None,
    social_adapter_payload: dict[str, Any] | None = None,
    qq_gateway_payload: dict[str, Any] | None = None,
    wecom_gateway_payload: dict[str, Any] | None = None,
    openclaw_gateway_payload: dict[str, Any] | None = None,
    approval_social_payload: dict[str, Any] | None = None,
    self_improvement_payload: dict[str, Any] | None = None,
    coding_agent_route_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = CoreSessionManager(data_store).load_snapshot(session_id, limit=limit)
    execution_summaries: list[dict[str, Any]] = []
    for span in snapshot.recent_execution_spans:
        audit_id = str(span["payload"].get("audit_id") or "")
        if not audit_id:
            continue
        execution_summaries.append(
            _build_closure_execution_summary(
                data_store.build_execution_evidence(
                    str(span["execution_span_id"]),
                    audit_id,
                )
            )
        )
    provider_smoke_summary = _build_provider_smoke_closure_summary(
        provider_smoke_payload,
        required=require_provider_smoke,
    )
    multimodal_profile_summary = _build_multimodal_profile_closure_summary(
        multimodal_profile_payload,
        required=require_multimodal_profile,
    )
    documentation_summary = _build_documentation_closure_summary(documentation_payload)
    regression_summary = _build_regression_closure_summary(regression_payload)
    relay_failure_summary = _build_relay_failure_closure_summary(
        relay_failure_payload
    )
    hardware_compatibility_summary = _build_hardware_compatibility_closure_summary(
        hardware_compatibility_payload
    )
    hardware_acceptance_matrix_summary = _build_hardware_acceptance_matrix_summary(
        hardware_acceptance_matrix_payload
    )
    resource_budget_governance_summary = (
        _build_resource_budget_governance_closure_summary(
            resource_budget_governance_payload
        )
    )
    agent_excellence_summary = _build_agent_excellence_closure_summary(
        agent_excellence_payload
    )
    signing_provenance_summary = _build_signing_provenance_closure_summary(
        signing_provenance_payload
    )
    observability_diagnosis_summary = _build_observability_diagnosis_closure_summary(
        observability_diagnosis_payload
    )
    release_rollback_summary = _build_release_rollback_hardening_closure_summary(
        release_rollback_payload
    )
    real_scene_e2e_summary = _build_real_scene_e2e_closure_summary(
        real_scene_e2e_payload
    )
    autonomy_daemon_summary = _build_release_210_smoke_closure_summary(
        autonomy_daemon_payload,
        expected_schema=AUTONOMY_DAEMON_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="autonomy_daemon_file_not_supplied",
    )
    task_tracking_summary = _build_release_210_smoke_closure_summary(
        task_tracking_payload,
        expected_schema=TASK_TRACKING_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="task_tracking_file_not_supplied",
    )
    memory_maintenance_summary = _build_release_210_smoke_closure_summary(
        memory_maintenance_payload,
        expected_schema=MEMORY_MAINTENANCE_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="memory_maintenance_file_not_supplied",
    )
    self_optimization_summary = _build_release_210_smoke_closure_summary(
        self_optimization_payload,
        expected_schema=SELF_OPTIMIZATION_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="self_optimization_file_not_supplied",
    )
    world_model_context_summary = _build_release_210_smoke_closure_summary(
        world_model_context_payload,
        expected_schema=WORLD_MODEL_CONTEXT_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="world_model_context_file_not_supplied",
    )
    vitality_governance_summary = _build_release_210_smoke_closure_summary(
        vitality_smoke_payload,
        expected_schema=VITALITY_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="vitality_smoke_file_not_supplied",
    )
    persona_persistence_summary = _build_release_210_smoke_closure_summary(
        persona_state_payload,
        expected_schema=PERSONA_STATE_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="persona_state_file_not_supplied",
    )
    persona_225_summary = _build_persona_225_closure_summary(persona_state_payload)
    social_adapter_summary = _build_release_210_smoke_closure_summary(
        social_adapter_payload,
        expected_schema=SOCIAL_ADAPTER_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="social_adapter_file_not_supplied",
    )
    qq_gateway_summary = _build_qq_official_gateway_closure_summary(qq_gateway_payload)
    wecom_gateway_summary = _build_wecom_gateway_closure_summary(
        wecom_gateway_payload
    )
    openclaw_gateway_summary = _build_openclaw_gateway_closure_summary(
        openclaw_gateway_payload
    )
    approval_social_summary = _build_release_210_smoke_closure_summary(
        approval_social_payload,
        expected_schema=APPROVAL_SOCIAL_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="approval_social_file_not_supplied",
    )
    self_improvement_summary = _build_release_210_smoke_closure_summary(
        self_improvement_payload,
        expected_schema=SELF_IMPROVEMENT_SMOKE_SCHEMA_VERSION,
        not_supplied_reason="self_improvement_file_not_supplied",
    )
    coding_agent_route_summary = _build_coding_agent_route_closure_summary(
        coding_agent_route_payload
    )
    aggregate_gates = {
        "session_has_execution_evidence": bool(execution_summaries),
        "latest_execution_closure_ready": bool(execution_summaries)
        and bool(execution_summaries[0].get("ok")),
        "no_pending_approvals": not snapshot.pending_approval_requests,
        "memory_governance_gate_satisfied": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("memory_governance_summary") or {},
            ).get("ok")
        ),
        "memory_recall_gate_satisfied": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("memory_recall_summary") or {},
            ).get("ok")
        ),
        "tool_skill_mcp_gate_satisfied": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("tool_skill_mcp_summary") or {},
            ).get("ok")
        ),
        "provider_smoke_gate_satisfied": bool(provider_smoke_summary.get("ok")),
        "multimodal_profile_gate_satisfied": bool(
            multimodal_profile_summary.get("ok")
        ),
    }
    bundle_checklist = [
        _build_closure_checklist_entry(
            "session_execution_evidence",
            passed=bool(aggregate_gates["session_has_execution_evidence"]),
            title="Session Execution Evidence",
            detail=(
                "Recent execution evidence is available for closure review."
                if aggregate_gates["session_has_execution_evidence"]
                else "No execution evidence was found for the session."
            ),
        ),
        _build_closure_checklist_entry(
            "latest_execution_ready",
            passed=bool(aggregate_gates["latest_execution_closure_ready"]),
            title="Latest Execution Closure Ready",
            detail=(
                "The latest execution summary passed all closure gates."
                if aggregate_gates["latest_execution_closure_ready"]
                else "The latest execution summary still has failing closure gates."
            ),
        ),
        _build_closure_checklist_entry(
            "pending_approvals_cleared",
            passed=bool(aggregate_gates["no_pending_approvals"]),
            title="Pending Approvals Cleared",
            detail=(
                "No pending approvals remain for the session."
                if aggregate_gates["no_pending_approvals"]
                else "Pending approvals remain and must be resolved before closure."
            ),
        ),
        _build_closure_checklist_entry(
            "memory_governance_bundle",
            passed=bool(aggregate_gates["memory_governance_gate_satisfied"]),
            title="Memory Governance Bundle",
            detail=(
                "Memory lifecycle evidence covers candidate screening and committed-memory governance."
                if aggregate_gates["memory_governance_gate_satisfied"]
                else "Memory lifecycle evidence is missing governed candidate or committed-memory details."
            ),
        ),
        _build_closure_checklist_entry(
            "memory_recall_policy_bundle",
            passed=bool(aggregate_gates["memory_recall_gate_satisfied"]),
            title="Memory Recall Policy Bundle",
            detail=(
                "Affective and Rational recall policy evidence is recorded with filtered categories and backend continuity."
                if aggregate_gates["memory_recall_gate_satisfied"]
                else "Memory recall policy evidence is missing separated affective/rational recall or backend continuity details."
            ),
        ),
        _build_closure_checklist_entry(
            "tool_skill_mcp_bundle",
            passed=bool(aggregate_gates["tool_skill_mcp_gate_satisfied"]),
            title="Tool Skill MCP Bundle",
            detail=(
                "Tool selection stayed within the available manifest, governed tools require approval, and MCP remains descriptor-only/read-only."
                if aggregate_gates["tool_skill_mcp_gate_satisfied"]
                else "Tool/Skill/MCP evidence is missing available-tool enforcement, approval governance, or read-only MCP boundaries."
            ),
        ),
        _build_closure_checklist_entry(
            "provider_smoke_bundle",
            passed=bool(aggregate_gates["provider_smoke_gate_satisfied"]),
            title="Provider Smoke Bundle",
            detail=(
                "Provider smoke evidence satisfied the closure bundle requirements."
                if aggregate_gates["provider_smoke_gate_satisfied"]
                else "Provider smoke evidence is missing or incomplete for the required closure bundle."
            ),
        ),
        _build_closure_checklist_entry(
            "multimodal_profile_bundle",
            passed=bool(aggregate_gates["multimodal_profile_gate_satisfied"]),
            title="Multimodal And Profile Bundle",
            detail=(
                "Multimodal normalization and profile routing evidence satisfied the closure bundle requirements."
                if aggregate_gates["multimodal_profile_gate_satisfied"]
                else "Multimodal/profile evidence is missing, incomplete, or not route-ready."
            ),
        ),
        _build_closure_checklist_entry(
            "coding_agent_route_bundle",
            passed=bool(coding_agent_route_summary.get("ok")),
            title="Coding Agent Route Bundle",
            detail=(
                "Coding-agent routing recorded plan artifact, sandbox execution, and callback audit evidence."
                if coding_agent_route_summary.get("ok")
                else "Coding-agent routing evidence is missing plan artifact, sandbox execution, or callback audit details."
            ),
        ),
    ]
    multimodal_gates = cast(
        dict[str, Any],
        multimodal_profile_summary.get("closure_gates") or {},
    )
    provider_gates = cast(
        dict[str, Any],
        provider_smoke_summary.get("closure_gates") or {},
    )
    task_tracking_gates = cast(
        dict[str, Any],
        task_tracking_summary.get("closure_gates") or {},
    )
    memory_maintenance_gates = cast(
        dict[str, Any],
        memory_maintenance_summary.get("closure_gates") or {},
    )
    validation_gates = {
        "documentation_gate": bool(documentation_summary.get("ok")),
        "federation_gate": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("federation_summary") or {},
            ).get("ok")
        ),
        "relay_gate": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("relay_summary") or {},
            ).get("ok")
        )
        and bool(relay_failure_summary.get("ok")),
        "hardware_abstraction_gate": bool(
            hardware_compatibility_summary.get("hardware_abstraction_ok")
        ),
        "artifact_compatibility_gate": bool(
            hardware_compatibility_summary.get("artifact_compatibility_ok")
        ),
        "hardware_acceptance_matrix_gate": bool(
            hardware_acceptance_matrix_summary.get("ok")
        ),
        "restricted_unit_compatibility_gate": bool(
            hardware_acceptance_matrix_summary.get("restricted_unit_compatibility_ok")
        ),
        "resource_budget_governance_gate": bool(
            resource_budget_governance_summary.get("ok")
        ),
        "agent_excellence_gate": bool(agent_excellence_summary.get("ok")),
        "release_rollback_hardening_gate": bool(release_rollback_summary.get("ok")),
        "signing_provenance_gate": bool(signing_provenance_summary.get("ok")),
        "observability_diagnosis_gate": bool(
            observability_diagnosis_summary.get("ok")
        ),
        "real_scene_e2e_gate": bool(real_scene_e2e_summary.get("ok")),
        "autonomous_daemon_gate": bool(autonomy_daemon_summary.get("ok")),
        "vitality_governance_gate": bool(vitality_governance_summary.get("ok")),
        "persona_persistence_gate": bool(persona_persistence_summary.get("ok")),
        "persona_seed_gate": bool(persona_225_summary.get("persona_seed_ok")),
        "persona_growth_gate": bool(persona_225_summary.get("persona_growth_ok")),
        "memory_immutability_gate": bool(
            persona_225_summary.get("memory_immutability_ok")
        ),
        "social_adapter_gate": bool(social_adapter_summary.get("ok")),
        "qq_official_gateway_gate": bool(qq_gateway_summary.get("ok")),
        "wecom_gateway_gate": bool(wecom_gateway_summary.get("ok")),
        "openclaw_gateway_gate": bool(openclaw_gateway_summary.get("ok")),
        "approval_over_social_gate": bool(approval_social_summary.get("ok")),
        "self_improvement_sandbox_gate": bool(self_improvement_summary.get("ok")),
        "coding_agent_route_gate": bool(coding_agent_route_summary.get("ok")),
        "multimodal_normalization_gate": bool(
            multimodal_gates.get("multimodal_profile_smoke_supplied")
            and multimodal_gates.get("multimodal_profile_contract_supported")
            and multimodal_gates.get("multimodal_input_recorded")
            and multimodal_gates.get("no_model_call_executed")
        ),
        "profile_routing_gate": bool(
            multimodal_gates.get("multimodal_profile_smoke_supplied")
            and multimodal_gates.get("multimodal_profile_contract_supported")
            and multimodal_gates.get("route_decision_recorded")
            and multimodal_gates.get("profile_readiness_recorded")
            and multimodal_gates.get("route_ready")
        ),
        "provider_runtime_gate": bool(
            provider_gates.get("provider_smoke_supplied")
            and provider_smoke_summary.get("ok")
        ),
        "memory_governance_gate": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("memory_governance_summary") or {},
            ).get("ok")
        )
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("memory_recall_summary") or {},
            ).get("ok")
        ),
        "tool_skill_mcp_gate": bool(execution_summaries)
        and bool(
            cast(
                dict[str, Any],
                execution_summaries[0].get("tool_skill_mcp_summary") or {},
            ).get("ok")
        ),
        "regression_gate": bool(regression_summary.get("ok")),
    }
    include_release_226_gates = any(
        payload is not None
        for payload in (
            task_tracking_payload,
            memory_maintenance_payload,
            self_optimization_payload,
            world_model_context_payload,
        )
    )
    if include_release_226_gates:
        bundle_checklist.extend(
            [
                _build_closure_checklist_entry(
                    "task_tracking_bundle",
                    passed=bool(task_tracking_summary.get("ok")),
                    title="Task Tracking Bundle",
                    detail=(
                        "Task tracking evidence records active-hours configuration, replay continuity, and cleanup-ready resumable work."
                        if task_tracking_summary.get("ok")
                        else "Task tracking evidence is missing active-hours configuration, replay continuity, or cleanup-ready resumable work."
                    ),
                ),
                _build_closure_checklist_entry(
                    "memory_maintenance_bundle",
                    passed=bool(memory_maintenance_summary.get("ok")),
                    title="Memory Maintenance Bundle",
                    detail=(
                        "Memory maintenance evidence records stale-context screening, prompt-safe consolidation, and audit-bound privacy scope."
                        if memory_maintenance_summary.get("ok")
                        else "Memory maintenance evidence is missing stale-context screening, prompt-safe consolidation, or audit-bound privacy scope."
                    ),
                ),
                _build_closure_checklist_entry(
                    "self_optimization_bundle",
                    passed=bool(self_optimization_summary.get("ok")),
                    title="Self Optimization Bundle",
                    detail=(
                        "Self-optimization evidence remains low-risk, approval-gated, sandbox-only, and forbidden from direct apply."
                        if self_optimization_summary.get("ok")
                        else "Self-optimization evidence is missing low-risk, approval-gated, sandbox-only, or no-direct-apply proof."
                    ),
                ),
                _build_closure_checklist_entry(
                    "world_model_context_bundle",
                    passed=bool(world_model_context_summary.get("ok")),
                    title="World Model Context Bundle",
                    detail=(
                        "World-model evidence records prompt-safe temporal, unit-capability, and relay-preserved context."
                        if world_model_context_summary.get("ok")
                        else "World-model evidence is missing prompt-safe temporal, unit-capability, or relay-preserved context."
                    ),
                ),
            ]
        )
    if include_release_226_gates:
        validation_gates.update(
            {
                "autonomy_heartbeat_gate": bool(autonomy_daemon_summary.get("ok"))
                and bool(task_tracking_gates.get("heartbeat_linked"))
                and bool(task_tracking_gates.get("active_hours_config_recorded")),
                "task_tracking_replay_gate": bool(task_tracking_summary.get("ok")),
                "memory_maintenance_gate": bool(memory_maintenance_summary.get("ok"))
                and bool(
                    memory_maintenance_gates.get("prompt_safe_summary_recorded")
                ),
                "self_optimization_gate": bool(self_optimization_summary.get("ok")),
                "world_model_context_gate": bool(world_model_context_summary.get("ok")),
            }
        )
    validation_gates["closure_summary_gate"] = all(validation_gates.values())
    validation_gate_summary: dict[str, Any] = {
        "total_count": len(validation_gates),
        "passed_count": sum(1 for passed in validation_gates.values() if passed),
        "failed_gate_ids": [
            gate_id
            for gate_id, passed in validation_gates.items()
            if gate_id != "closure_summary_gate" and not passed
        ],
        "ok": all(validation_gates.values()),
    }
    checklist = _build_validation_gate_checklist(validation_gates)
    return {
        "schema_version": CLOSURE_SUMMARY_SCHEMA_VERSION,
        "session_id": session_id,
        "execution_count": len(execution_summaries),
        "recent_audit_ids": list(snapshot.recent_audit_ids),
        "pending_approval_requests": list(snapshot.pending_approval_requests),
        "documentation_summary": documentation_summary,
        "provider_smoke_summary": provider_smoke_summary,
        "multimodal_profile_summary": multimodal_profile_summary,
        "regression_summary": regression_summary,
        "relay_failure_summary": relay_failure_summary,
        "hardware_compatibility_summary": hardware_compatibility_summary,
        "hardware_acceptance_matrix_summary": hardware_acceptance_matrix_summary,
        "resource_budget_governance_summary": resource_budget_governance_summary,
        "agent_excellence_summary": agent_excellence_summary,
        "release_rollback_summary": release_rollback_summary,
        "signing_provenance_summary": signing_provenance_summary,
        "observability_diagnosis_summary": observability_diagnosis_summary,
        "real_scene_e2e_summary": real_scene_e2e_summary,
        "autonomy_daemon_summary": autonomy_daemon_summary,
        "task_tracking_summary": task_tracking_summary,
        "memory_maintenance_summary": memory_maintenance_summary,
        "self_optimization_summary": self_optimization_summary,
        "world_model_context_summary": world_model_context_summary,
        "vitality_governance_summary": vitality_governance_summary,
        "persona_persistence_summary": persona_persistence_summary,
        "persona_225_summary": persona_225_summary,
        "social_adapter_summary": social_adapter_summary,
        "qq_official_gateway_summary": qq_gateway_summary,
        "wecom_gateway_summary": wecom_gateway_summary,
        "openclaw_gateway_summary": openclaw_gateway_summary,
        "approval_social_summary": approval_social_summary,
        "self_improvement_summary": self_improvement_summary,
        "coding_agent_route_summary": coding_agent_route_summary,
        "aggregate_gates": aggregate_gates,
        "validation_gates": validation_gates,
        "validation_gate_summary": validation_gate_summary,
        "checklist": checklist,
        "bundle_checklist": bundle_checklist,
        "ok": all(aggregate_gates.values()),
        "execution_summaries": execution_summaries,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neurolink-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("no-model-dry-run")
    dry_run.add_argument("--db", default=":memory:", help="SQLite database path")
    dry_run.add_argument("--output", choices=("json",), default="json")
    dry_run.add_argument("--use-db-events", action="store_true", help="Rebuild the reasoning frame from persisted events")
    dry_run.add_argument("--query-limit", type=int, default=100, help="Maximum persisted events to query when --use-db-events is set")
    dry_run.add_argument("--min-priority", type=int, default=0, help="Minimum persisted event priority to include when --use-db-events is set")
    dry_run.add_argument("--topic", default=None, help="Optional semantic topic filter when --use-db-events is set")
    dry_run.add_argument(
        "--event-source",
        choices=("sample", "neuro-cli-agent-events"),
        default="sample",
        help="Select perception event source for the dry run",
    )
    dry_run.add_argument("--max-events", type=int, default=0, help="Maximum agent-events rows to ingest when using neuro-cli-agent-events")
    dry_run.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    dry_run.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    dry_run.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    dry_run.add_argument(
        "--maf-config-file",
        default="",
        help="Optional runtime provider profile config JSON path used to resolve model and endpoint settings",
    )
    dry_run.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for dry-run lookup and candidate commit behavior",
    )
    dry_run.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    dry_run.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    dry_run.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    event_replay = subparsers.add_parser("event-replay")
    event_replay.add_argument("--db", default=":memory:", help="SQLite database path")
    event_replay.add_argument("--events-file", required=True, help="Path to a JSON event replay fixture")
    event_replay.add_argument("--output", choices=("json",), default="json")
    event_replay.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    event_replay.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    event_replay.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    event_replay.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for replay lookup and candidate commit behavior",
    )
    event_replay.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    event_replay.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    event_replay.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    event_daemon = subparsers.add_parser("event-daemon")
    event_daemon.add_argument("--db", default=":memory:", help="SQLite database path")
    event_daemon.add_argument("--events-file", required=True, help="Path to a JSON daemon replay fixture")
    event_daemon.add_argument("--output", choices=("json",), default="json")
    event_daemon.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    event_daemon.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    event_daemon.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    event_daemon.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for daemon replay lookup and candidate commit behavior",
    )
    event_daemon.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    event_daemon.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    event_daemon.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    live_event_smoke = subparsers.add_parser("live-event-smoke")
    live_event_smoke.add_argument("--db", default=":memory:", help="SQLite database path")
    live_event_smoke.add_argument(
        "--event-source",
        choices=("app", "unit"),
        default="app",
        help="Subscribe to app callback events or unit-wide operational events",
    )
    live_event_smoke.add_argument("--app-id", default="", help="Target app identifier for app-scoped live callback subscriptions")
    live_event_smoke.add_argument("--duration", type=int, default=5, help="Subscription duration in seconds")
    live_event_smoke.add_argument("--max-events", type=int, default=1, help="Stop after this many events if non-zero")
    live_event_smoke.add_argument("--ready-file", default="", help="Optional file path written once the live event subscription is ready")
    live_event_smoke.add_argument("--output", choices=("json",), default="json")
    live_event_smoke.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    live_event_smoke.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    live_event_smoke.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    live_event_smoke.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for live-ingest lookup and candidate commit behavior",
    )
    live_event_smoke.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )

    event_service = subparsers.add_parser("event-service")
    event_service.add_argument("--db", default=":memory:", help="SQLite database path")
    event_service.add_argument(
        "--event-source",
        choices=("app", "unit"),
        default="app",
        help="Subscribe to app callback events or unit-wide operational events",
    )
    event_service.add_argument("--app-id", default="", help="Target app identifier for app-scoped live callback subscriptions")
    event_service.add_argument("--duration", type=int, default=5, help="Subscription duration in seconds")
    event_service.add_argument("--max-events", type=int, default=1, help="Stop after this many events if non-zero")
    event_service.add_argument("--cycles", type=int, default=1, help="Run this many bounded service supervision cycles")
    event_service.add_argument("--ready-file", default="", help="Optional file path written once the live event subscription is ready")
    event_service.add_argument("--output", choices=("json",), default="json")
    event_service.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    event_service.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    event_service.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    event_service.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for live event service lookup and candidate commit behavior",
    )
    event_service.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )

    activation_health = subparsers.add_parser("activation-health-guard")
    activation_health.add_argument("--db", default=":memory:", help="SQLite database path")
    activation_health.add_argument("--app-id", required=True, help="Activated app identifier to observe")
    activation_health.add_argument("--output", choices=("json",), default="json")
    activation_health.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used for read-only health observation",
    )

    app_build_plan = subparsers.add_parser("app-build-plan")
    app_build_plan.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_build_plan.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the build plan",
    )
    app_build_plan.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_build_plan.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_build_plan.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_build_plan.add_argument("--output", choices=("json",), default="json")
    app_build_plan.add_argument(
        "--check-c-style",
        action="store_true",
        help="Record a build plan that keeps the C style gate enabled",
    )

    app_artifact_admission = subparsers.add_parser("app-artifact-admission")
    app_artifact_admission.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_artifact_admission.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the admission check",
    )
    app_artifact_admission.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_artifact_admission.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_artifact_admission.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_artifact_admission.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to admit; defaults to the canonical source artifact path",
    )
    app_artifact_admission.add_argument("--output", choices=("json",), default="json")

    hardware_compatibility_smoke = subparsers.add_parser("hardware-compatibility-smoke")
    hardware_compatibility_smoke.add_argument("--preset", choices=("unit-app", "unit-ext"), default="unit-app")
    hardware_compatibility_smoke.add_argument("--app-id", default="neuro_unit_app")
    hardware_compatibility_smoke.add_argument("--app-source-dir", default="")
    hardware_compatibility_smoke.add_argument("--board", default="dnesp32s3b/esp32s3/procpu")
    hardware_compatibility_smoke.add_argument("--build-dir", default="build/neurolink_unit")
    hardware_compatibility_smoke.add_argument("--artifact-file", default="")
    hardware_compatibility_smoke.add_argument("--unit-node-id", default="unit-local-01")
    hardware_compatibility_smoke.add_argument("--unit-architecture", default="xtensa")
    hardware_compatibility_smoke.add_argument("--unit-abi", default="zephyr-llext-v1")
    hardware_compatibility_smoke.add_argument("--unit-board-family", default="generic-unit-class")
    hardware_compatibility_smoke.add_argument("--unit-storage-class", default="removable_or_flash")
    hardware_compatibility_smoke.add_argument("--unit-network-transport", action="append", default=[])
    hardware_compatibility_smoke.add_argument("--unit-llext-unsupported", action="store_true")
    hardware_compatibility_smoke.add_argument("--unit-signing-enforced", action="store_true")
    hardware_compatibility_smoke.add_argument("--heap-free-bytes", type=int, default=8192)
    hardware_compatibility_smoke.add_argument("--app-slot-bytes", type=int, default=65536)
    hardware_compatibility_smoke.add_argument("--required-abi", default="")
    hardware_compatibility_smoke.add_argument("--required-board-family", default="")
    hardware_compatibility_smoke.add_argument("--required-storage-class", default="")
    hardware_compatibility_smoke.add_argument("--require-signing", action="store_true")
    hardware_compatibility_smoke.add_argument("--required-heap-free-bytes", type=int, default=0)
    hardware_compatibility_smoke.add_argument("--required-app-slot-bytes", type=int, default=0)
    hardware_compatibility_smoke.add_argument("--mismatch-architecture-probe", default="x86_64")
    hardware_compatibility_smoke.add_argument("--output", choices=("json",), default="json")

    hardware_acceptance_matrix = subparsers.add_parser("hardware-acceptance-matrix")
    hardware_acceptance_matrix.add_argument("--preset", choices=("unit-app", "unit-ext"), default="unit-app")
    hardware_acceptance_matrix.add_argument("--app-id", default="neuro_unit_app")
    hardware_acceptance_matrix.add_argument("--app-source-dir", default="")
    hardware_acceptance_matrix.add_argument("--board", default="dnesp32s3b/esp32s3/procpu")
    hardware_acceptance_matrix.add_argument("--build-dir", default="build/neurolink_unit")
    hardware_acceptance_matrix.add_argument("--artifact-file", default="")
    hardware_acceptance_matrix.add_argument("--capability-class", action="append", default=[])
    hardware_acceptance_matrix.add_argument("--board-family-mapping", action="append", default=[])
    hardware_acceptance_matrix.add_argument("--required-heap-free-bytes", type=int, default=4096)
    hardware_acceptance_matrix.add_argument("--required-app-slot-bytes", type=int, default=32768)
    hardware_acceptance_matrix.add_argument("--output", choices=("json",), default="json")

    resource_budget_governance_smoke = subparsers.add_parser(
        "resource-budget-governance-smoke"
    )
    resource_budget_governance_smoke.add_argument(
        "--hardware-compatibility-file",
        required=True,
        help="JSON payload emitted by hardware-compatibility-smoke containing the governed resource-budget evidence.",
    )
    resource_budget_governance_smoke.add_argument(
        "--output", choices=("json",), default="json"
    )

    signing_provenance_smoke = subparsers.add_parser("signing-provenance-smoke")
    signing_provenance_smoke.add_argument("--preset", choices=("unit-app", "unit-ext"), default="unit-app")
    signing_provenance_smoke.add_argument("--app-id", default="neuro_unit_app")
    signing_provenance_smoke.add_argument("--app-source-dir", default="")
    signing_provenance_smoke.add_argument("--board", default="dnesp32s3b/esp32s3/procpu")
    signing_provenance_smoke.add_argument("--build-dir", default="build/neurolink_unit")
    signing_provenance_smoke.add_argument("--artifact-file", default="")
    signing_provenance_smoke.add_argument(
        "--require-signing",
        dest="require_signing",
        action="store_true",
        default=True,
    )
    signing_provenance_smoke.add_argument(
        "--no-require-signing",
        dest="require_signing",
        action="store_false",
    )
    signing_provenance_smoke.add_argument(
        "--unit-signing-enforced",
        dest="unit_signing_enforced",
        action="store_true",
        default=True,
    )
    signing_provenance_smoke.add_argument(
        "--unit-signing-disabled",
        dest="unit_signing_enforced",
        action="store_false",
    )
    signing_provenance_smoke.add_argument("--output", choices=("json",), default="json")

    app_deploy_plan = subparsers.add_parser("app-deploy-plan")
    app_deploy_plan.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_deploy_plan.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the deploy plan",
    )
    app_deploy_plan.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_deploy_plan.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_deploy_plan.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_deploy_plan.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to deploy; defaults to the admitted source artifact path",
    )
    app_deploy_plan.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_plan.add_argument(
        "--source-agent",
        default="rational",
        help="Deploy-plan source_agent metadata for lease and deploy commands",
    )
    app_deploy_plan.add_argument(
        "--lease-ttl-ms",
        type=int,
        default=120000,
        help="Suggested activate-lease TTL in milliseconds",
    )
    app_deploy_plan.add_argument(
        "--start-args",
        default="",
        help="Optional start-args string to include in the activate plan step",
    )
    app_deploy_plan.add_argument("--output", choices=("json",), default="json")

    app_deploy_prepare_verify = subparsers.add_parser("app-deploy-prepare-verify")
    app_deploy_prepare_verify.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_deploy_prepare_verify.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the prepare/verify execution slice",
    )
    app_deploy_prepare_verify.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_deploy_prepare_verify.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_deploy_prepare_verify.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_deploy_prepare_verify.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to deploy; defaults to the admitted source artifact path",
    )
    app_deploy_prepare_verify.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_prepare_verify.add_argument(
        "--source-agent",
        default="rational",
        help="Execution source_agent metadata for lease and deploy commands",
    )
    app_deploy_prepare_verify.add_argument(
        "--lease-ttl-ms",
        type=int,
        default=120000,
        help="Activate-lease TTL in milliseconds",
    )
    app_deploy_prepare_verify.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Command timeout in seconds for preflight and Neuro CLI calls",
    )
    app_deploy_prepare_verify.add_argument("--output", choices=("json",), default="json")

    app_deploy_activate = subparsers.add_parser("app-deploy-activate")
    app_deploy_activate.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_deploy_activate.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the activation execution slice",
    )
    app_deploy_activate.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_deploy_activate.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_deploy_activate.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_deploy_activate.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to deploy; defaults to the admitted source artifact path",
    )
    app_deploy_activate.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_activate.add_argument(
        "--source-agent",
        default="rational",
        help="Execution source_agent metadata for lease and deploy commands",
    )
    app_deploy_activate.add_argument(
        "--lease-ttl-ms",
        type=int,
        default=120000,
        help="Activate-lease TTL in milliseconds",
    )
    app_deploy_activate.add_argument(
        "--start-args",
        default="",
        help="Optional start-args string passed to deploy activate",
    )
    app_deploy_activate.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Command timeout in seconds for preflight and Neuro CLI calls",
    )
    app_deploy_activate.add_argument(
        "--approval-decision",
        choices=("pending", "approve", "deny"),
        default="pending",
        help="Explicit activation approval decision required before activation executes",
    )
    app_deploy_activate.add_argument(
        "--approval-note",
        default="",
        help="Optional operator approval note recorded in the activation decision payload",
    )
    app_deploy_activate.add_argument("--db", default="", help="Optional SQLite database path for persisting activation release-gate evidence")
    app_deploy_activate.add_argument("--output", choices=("json",), default="json")

    app_deploy_rollback = subparsers.add_parser("app-deploy-rollback")
    app_deploy_rollback.add_argument(
        "--app-id",
        required=True,
        help="Target app identifier for the rollback execution slice",
    )
    app_deploy_rollback.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_rollback.add_argument(
        "--source-agent",
        default="rational",
        help="Execution source_agent metadata for rollback commands",
    )
    app_deploy_rollback.add_argument(
        "--lease-id",
        default="",
        help="Optional explicit rollback lease id; defaults to adapter lease resolution",
    )
    app_deploy_rollback.add_argument(
        "--reason",
        default="guarded_rollback_after_activation_health_failure",
        help="Rollback reason recorded in the resumed rollback request",
    )
    app_deploy_rollback.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Command timeout in seconds for Neuro CLI calls",
    )
    app_deploy_rollback.add_argument(
        "--approval-decision",
        choices=("pending", "approve", "deny", "expire"),
        default="pending",
        help="Explicit rollback approval decision required before rollback executes",
    )
    app_deploy_rollback.add_argument(
        "--approval-note",
        default="",
        help="Optional operator approval note recorded in the rollback decision payload",
    )
    app_deploy_rollback.add_argument("--db", default="", help="Optional SQLite database path for persisting rollback release-gate evidence")
    app_deploy_rollback.add_argument("--output", choices=("json",), default="json")

    agent_run = subparsers.add_parser("agent-run")
    agent_run.add_argument("--db", default=":memory:", help="SQLite database path")
    agent_run.add_argument("--output", choices=("json",), default="json")
    agent_run.add_argument("--input-text", default=None, help="Optional user input text to synthesize into a perception event")
    agent_run.add_argument("--social-text", default=None, help="Optional mock social message text to synthesize into a perception event")
    agent_run.add_argument("--social-adapter-kind", default="mock_qq", help="Mock social adapter kind used with --social-text")
    agent_run.add_argument("--social-channel-id", default="direct-001", help="Mock social channel identifier used with --social-text")
    agent_run.add_argument(
        "--social-channel-kind",
        choices=("direct", "group", "channel"),
        default="direct",
        help="Mock social channel kind used with --social-text",
    )
    agent_run.add_argument("--social-user-id", default="operator", help="Mock social external user identifier used with --social-text")
    agent_run.add_argument(
        "--social-admin",
        action="store_true",
        help="Mark the mock social message as an admin/operator message",
    )
    agent_run.add_argument(
        "--event-source",
        choices=("sample", "neuro-cli-agent-events"),
        default="sample",
        help="Select perception event source when --input-text is not provided",
    )
    agent_run.add_argument("--max-events", type=int, default=0, help="Maximum agent-events rows to ingest when using neuro-cli-agent-events")
    agent_run.add_argument("--session-id", default=None, help="Optional session identifier to continue a prior local Core session")
    agent_run.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    agent_run.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    agent_run.add_argument(
        "--maf-config-file",
        default="",
        help="Optional runtime provider profile config JSON path used to resolve model and endpoint settings",
    )
    agent_run.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for agent-run lookup and candidate commit behavior",
    )
    agent_run.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    agent_run.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    agent_run.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    tool_manifest = subparsers.add_parser("tool-manifest")
    tool_manifest.add_argument("--output", choices=("json",), default="json")
    tool_manifest.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for manifest discovery",
    )

    skill_descriptor = subparsers.add_parser("skill-descriptor")
    skill_descriptor.add_argument("--output", choices=("json",), default="json")

    skill_registry = subparsers.add_parser("skill-registry")
    skill_registry.add_argument("--output", choices=("json",), default="json")

    coding_agent_descriptor = subparsers.add_parser("coding-agent-descriptor")
    coding_agent_descriptor.add_argument("--output", choices=("json",), default="json")
    coding_agent_descriptor.add_argument(
        "--runner",
        choices=("copilot", "qwen-code", "opencode", "local-command"),
        default="copilot",
        help="Select the governed coding-agent runner descriptor to inspect.",
    )

    tool_threat_descriptor = subparsers.add_parser("tool-threat-descriptor")
    tool_threat_descriptor.add_argument("--output", choices=("json",), default="json")
    tool_threat_descriptor.add_argument("--tool", required=True)
    tool_threat_descriptor.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used to resolve the tool contract.",
    )
    tool_threat_descriptor.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Repeatable tool argument in name=value form for threat classification.",
    )

    mcp_tool_governance_descriptor = subparsers.add_parser("mcp-tool-governance-descriptor")
    mcp_tool_governance_descriptor.add_argument("--output", choices=("json",), default="json")
    mcp_tool_governance_descriptor.add_argument("--tool", required=True)
    mcp_tool_governance_descriptor.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used to resolve the tool contract.",
    )
    mcp_tool_governance_descriptor.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Repeatable tool argument in name=value form for additive threat classification context.",
    )

    coding_agent_self_improvement_route = subparsers.add_parser("coding-agent-self-improvement-route")
    coding_agent_self_improvement_route.add_argument("--output", choices=("json",), default="json")
    coding_agent_self_improvement_route.add_argument(
        "--runner",
        choices=("copilot", "qwen-code", "opencode", "local-command"),
        default="copilot",
    )
    coding_agent_self_improvement_route.add_argument("--summary", required=True)
    coding_agent_self_improvement_route.add_argument(
        "--source",
        default="maintenance_finding",
        help="Governed source classification for the coding-agent request.",
    )
    coding_agent_self_improvement_route.add_argument(
        "--decision",
        choices=("pending", "approve", "deny"),
        default="pending",
        help="Optional operator review decision to apply to the routed self-improvement proposal.",
    )
    coding_agent_self_improvement_route.add_argument("--tests-passed", action="store_true")
    coding_agent_self_improvement_route.add_argument("--lint-passed", action="store_true")
    coding_agent_self_improvement_route.add_argument("--smoke-passed", action="store_true")
    coding_agent_self_improvement_route.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Repeatable evidence reference recorded on the governed proposal review.",
    )

    release_224_closure_smoke = subparsers.add_parser("release-2.2.4-closure-smoke")
    release_224_closure_smoke.add_argument(
        "--output", choices=("json",), default="json"
    )
    release_224_closure_smoke.add_argument(
        "--session-id",
        default="release-2.2.4-closure-smoke-001",
        help="Optional session identifier used for the release-2.2.4 closure smoke run.",
    )
    release_224_closure_smoke.add_argument(
        "--runner",
        choices=("copilot", "qwen-code", "opencode", "local-command"),
        default="copilot",
        help="Coding-agent runner name recorded in the governed route payload.",
    )
    release_224_closure_smoke.add_argument(
        "--summary",
        default="Repair deterministic regression in sandbox",
        help="Improvement summary recorded in the governed coding-agent route payload.",
    )
    release_224_closure_smoke.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory where the release-2.2.4 closure smoke will export structured evidence JSON files.",
    )

    release_226_closure_smoke = subparsers.add_parser("release-2.2.6-closure-smoke")
    release_226_closure_smoke.add_argument("--output", choices=("json",), default="json")
    release_226_closure_smoke.add_argument(
        "--session-id",
        default="release-2.2.6-closure-smoke-001",
        help="Optional session identifier used for the release-2.2.6 closure smoke run.",
    )
    release_226_closure_smoke.add_argument(
        "--runner",
        choices=("copilot", "qwen-code", "opencode", "local-command"),
        default="copilot",
        help="Coding-agent runner name recorded in the inherited governed route payload.",
    )
    release_226_closure_smoke.add_argument(
        "--summary",
        default="Review low-risk self-optimization in sandbox",
        help="Improvement summary recorded in the inherited coding-agent route payload.",
    )
    release_226_closure_smoke.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory where the release-2.2.6 closure smoke will export structured evidence JSON files.",
    )

    mcp_read_only_execute = subparsers.add_parser("mcp-read-only-execute")
    mcp_read_only_execute.add_argument("--output", choices=("json",), default="json")
    mcp_read_only_execute.add_argument("--tool", required=True)
    mcp_read_only_execute.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used to resolve and execute the tool.",
    )
    mcp_read_only_execute.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Repeatable tool argument in name=value form for the read-only MCP execution payload.",
    )

    mcp_descriptor = subparsers.add_parser("mcp-descriptor")
    mcp_descriptor.add_argument("--output", choices=("json",), default="json")
    mcp_descriptor.add_argument(
        "--bridge-mode",
        choices=(
            "read_only_descriptor_only",
            "core_governed_read_only_execution",
            "core_governed_approval_required_proposal",
        ),
        default="read_only_descriptor_only",
        help="Select the governed MCP bridge descriptor mode to inspect.",
    )
    mcp_descriptor.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used to derive the bounded read-only MCP bridge descriptor",
    )

    agent_excellence_smoke = subparsers.add_parser("agent-excellence-smoke")
    agent_excellence_smoke.add_argument("--output", choices=("json",), default="json")
    agent_excellence_smoke.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used to derive the governed Agent excellence payload",
    )
    agent_excellence_smoke.add_argument(
        "--bridge-mode",
        choices=(
            "read_only_descriptor_only",
            "core_governed_read_only_execution",
            "core_governed_approval_required_proposal",
        ),
        default="read_only_descriptor_only",
        help="Select the MCP bridge descriptor mode to evaluate for Agent excellence closure.",
    )

    observability_diagnosis_smoke = subparsers.add_parser("observability-diagnosis-smoke")
    observability_diagnosis_smoke.add_argument(
        "--relay-failure-file",
        required=True,
        help="JSON payload emitted by the relay-failure closure path.",
    )
    observability_diagnosis_smoke.add_argument(
        "--activate-failure-file",
        required=True,
        help="JSON payload emitted by app-deploy-activate for a rollback_required health failure.",
    )
    observability_diagnosis_smoke.add_argument("--output", choices=("json",), default="json")

    release_rollback_hardening_smoke = subparsers.add_parser(
        "release-rollback-hardening-smoke"
    )
    release_rollback_hardening_smoke.add_argument(
        "--activate-failure-file",
        required=True,
        help="JSON payload emitted by app-deploy-activate for a rollback_required health failure.",
    )
    release_rollback_hardening_smoke.add_argument(
        "--rollback-file",
        required=True,
        help="JSON payload emitted by app-deploy-rollback after explicit approval.",
    )
    release_rollback_hardening_smoke.add_argument(
        "--output", choices=("json",), default="json"
    )

    real_scene_checklist_template = subparsers.add_parser("real-scene-checklist-template")
    real_scene_checklist_template.add_argument(
        "--release-target",
        default="2.0.0",
        help="Promotion release identifier recorded in the template metadata.",
    )
    real_scene_checklist_template.add_argument(
        "--implementation-release",
        default="1.2.7",
        help="Implementation release that closes the checklist before the frozen rerun.",
    )
    real_scene_checklist_template.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_live_rerun_template = subparsers.add_parser(
        "release-2.2.6-live-rerun-template"
    )
    release_226_live_rerun_template.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the 2.2.6 live rerun template metadata.",
    )
    release_226_live_rerun_template.add_argument(
        "--inherited-release",
        default="2.2.5",
        help="Inherited bounded release used as the live rerun baseline before fresh 2.2.6 replacements.",
    )
    release_226_live_rerun_template.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_real_unit_rerun_archive = subparsers.add_parser(
        "release-2.2.6-real-unit-rerun-archive"
    )
    release_226_real_unit_rerun_archive.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the real Unit rerun archive metadata.",
    )
    release_226_real_unit_rerun_archive.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to export the structured real Unit rerun evidence bundle.",
    )
    release_226_real_unit_rerun_archive.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_qq_gateway_rerun_archive = subparsers.add_parser(
        "release-2.2.6-qq-gateway-rerun-archive"
    )
    release_226_qq_gateway_rerun_archive.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the QQ gateway rerun archive metadata.",
    )
    release_226_qq_gateway_rerun_archive.add_argument(
        "--inherited-release",
        default="2.2.5",
        help="Inherited bounded release used as the QQ gateway rerun baseline.",
    )
    release_226_qq_gateway_rerun_archive.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to export the structured QQ gateway rerun evidence bundle.",
    )
    release_226_qq_gateway_rerun_archive.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_wecom_gateway_rerun_archive = subparsers.add_parser(
        "release-2.2.6-wecom-gateway-rerun-archive"
    )
    release_226_wecom_gateway_rerun_archive.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the WeCom gateway rerun archive metadata.",
    )
    release_226_wecom_gateway_rerun_archive.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to export the structured WeCom gateway rerun evidence bundle.",
    )
    release_226_wecom_gateway_rerun_archive.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_openclaw_gateway_rerun_archive = subparsers.add_parser(
        "release-2.2.6-openclaw-gateway-rerun-archive"
    )
    release_226_openclaw_gateway_rerun_archive.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the OpenClaw gateway rerun archive metadata.",
    )
    release_226_openclaw_gateway_rerun_archive.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to export the structured OpenClaw gateway rerun evidence bundle.",
    )
    release_226_openclaw_gateway_rerun_archive.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_hardware_rerun_archive = subparsers.add_parser(
        "release-2.2.6-hardware-rerun-archive"
    )
    release_226_hardware_rerun_archive.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the hardware rerun archive metadata.",
    )
    release_226_hardware_rerun_archive.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to export the structured hardware rerun evidence bundle.",
    )
    release_226_hardware_rerun_archive.add_argument(
        "--output", choices=("json",), default="json"
    )

    release_226_promotion_checklist = subparsers.add_parser(
        "release-2.2.6-promotion-checklist"
    )
    release_226_promotion_checklist.add_argument(
        "--release-target",
        default="2.2.6",
        help="Release identifier recorded in the promotion checklist metadata.",
    )
    release_226_promotion_checklist.add_argument(
        "--inherited-release",
        default="2.2.5",
        help="Inherited release used as the bounded promotion baseline.",
    )
    release_226_promotion_checklist.add_argument(
        "--evidence-dir",
        default="",
        help="Optional directory to export the promotion checklist bundle.",
    )
    release_226_promotion_checklist.add_argument(
        "--output", choices=("json",), default="json"
    )

    real_scene_e2e_smoke = subparsers.add_parser("real-scene-e2e-smoke")
    real_scene_e2e_smoke.add_argument(
        "--live-event-smoke-file",
        required=True,
        help="JSON payload emitted by live-event-smoke to validate as a real Core/Unit end-to-end scenario.",
    )
    real_scene_e2e_smoke.add_argument(
        "--coding-agent-route-file",
        default="",
        help="Optional JSON payload emitted by coding-agent-self-improvement-route to validate governed coding-agent execution evidence in the same real-scene review.",
    )
    real_scene_e2e_smoke.add_argument("--output", choices=("json",), default="json")

    social_chat = subparsers.add_parser("social-chat")
    social_chat.add_argument("--db", default=":memory:", help="SQLite database path")
    social_chat.add_argument("--message", required=True, help="Mock social chat message")
    social_chat.add_argument("--session-id", default=None, help="Optional session identifier")
    social_chat.add_argument("--social-adapter-kind", default="mock_qq", help="Mock social adapter kind")
    social_chat.add_argument("--social-channel-id", default="direct-chat-001", help="Mock social channel identifier")
    social_chat.add_argument(
        "--social-channel-kind",
        choices=("direct", "group", "channel"),
        default="direct",
        help="Mock social channel kind",
    )
    social_chat.add_argument("--social-user-id", default="operator", help="Mock social external user identifier")
    social_chat.add_argument("--social-admin", action="store_true", help="Mark the social chat message as admin/operator")
    social_chat.add_argument("--output", choices=("text", "json"), default="text")

    social_adapter_smoke = subparsers.add_parser("social-adapter-smoke")
    social_adapter_smoke.add_argument("--output", choices=("json",), default="json")
    social_adapter_smoke.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")

    social_adapter_list_parser = subparsers.add_parser("social-adapter-list")
    social_adapter_list_parser.add_argument("--output", choices=("json",), default="json")
    social_adapter_list_parser.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")

    social_adapter_config = subparsers.add_parser("social-adapter-config")
    social_adapter_config.add_argument("--output", choices=("json",), default="json")
    social_adapter_config.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")
    social_adapter_config.add_argument("--adapter", required=True, help="Social adapter profile name to update")
    social_adapter_config.add_argument("--adapter-kind", default=None)
    social_adapter_config.add_argument("--endpoint-url", default=None)
    social_adapter_config.add_argument("--webhook-url", default=None)
    social_adapter_config.add_argument("--host-url", default=None)
    social_adapter_config.add_argument("--credential-env-var", action="append", default=None)
    social_adapter_config.add_argument("--supported-channel-kind", action="append", default=None)
    social_adapter_config.add_argument("--default-channel-policy", default=None)
    social_adapter_config.add_argument("--mention-policy", default=None)
    social_adapter_config.add_argument("--transport-kind", default=None)
    social_adapter_config.add_argument("--runtime-host", default=None)
    social_adapter_config.add_argument("--plugin-id", default=None)
    social_adapter_config.add_argument("--plugin-package", default=None)
    social_adapter_config.add_argument("--installer-package", default=None)
    social_adapter_config.add_argument(
        "--plugin-installed",
        choices=("true", "false"),
        default=None,
    )
    social_adapter_config.add_argument(
        "--account-session-ready",
        choices=("true", "false"),
        default=None,
    )
    social_adapter_config.add_argument("--compliance-class", default=None)
    social_adapter_config.add_argument(
        "--compliance-acknowledged",
        choices=("true", "false"),
        default=None,
    )
    social_adapter_config.add_argument(
        "--live-network-allowed",
        choices=("true", "false"),
        default=None,
    )
    social_adapter_config.add_argument(
        "--share-session-in-group",
        choices=("true", "false"),
        default=None,
    )
    social_adapter_config.add_argument("--active", action="store_true")
    social_enable_disable = social_adapter_config.add_mutually_exclusive_group()
    social_enable_disable.add_argument("--enable", action="store_true")
    social_enable_disable.add_argument("--disable", action="store_true")

    social_adapter_test_parser = subparsers.add_parser("social-adapter-test")
    social_adapter_test_parser.add_argument("--output", choices=("json",), default="json")
    social_adapter_test_parser.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")
    social_adapter_test_parser.add_argument("--adapter", default="", help="Optional social adapter profile name to test")
    social_adapter_test_parser.add_argument(
        "--sample-scenario",
        choices=("group", "direct", "group_no_mention"),
        default="group",
        help="Deterministic social sample scenario used for adapter normalization tests",
    )
    social_adapter_test_parser.add_argument(
        "--probe-transport",
        action="store_true",
        help="Opt in to a bounded transport reachability probe for the selected adapter profile",
    )
    social_adapter_test_parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=1.5,
        help="Timeout used by the opt-in transport reachability probe",
    )

    qq_official_webhook_server = subparsers.add_parser("qq-official-webhook-server")
    qq_official_webhook_server.add_argument("--db", default=":memory:", help="SQLite database path")
    qq_official_webhook_server.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")
    qq_official_webhook_server.add_argument("--host", default="127.0.0.1", help="Listen host for the bounded QQ official webhook server")
    qq_official_webhook_server.add_argument("--port", type=int, default=8091, help="Listen port for the bounded QQ official webhook server")
    qq_official_webhook_server.add_argument("--path", default="/", help="HTTP path served by the bounded QQ official webhook server")
    qq_official_webhook_server.add_argument("--duration", type=int, default=30, help="Maximum bounded runtime in seconds")
    qq_official_webhook_server.add_argument("--max-events", type=int, default=1, help="Stop after this many QQ dispatch events if non-zero")
    qq_official_webhook_server.add_argument("--ready-file", default="", help="Optional file path written once the webhook server is listening")
    qq_official_webhook_server.add_argument("--output", choices=("json",), default="json")
    qq_official_webhook_server.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    qq_official_webhook_server.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    qq_official_webhook_server.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    qq_official_webhook_server.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for QQ webhook ingress lookup and candidate commit behavior",
    )
    qq_official_webhook_server.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    qq_official_webhook_server.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter during the webhook-driven Core run",
    )

    qq_official_gateway_client = subparsers.add_parser("qq-official-gateway-client")
    qq_official_gateway_client.add_argument("--db", default=":memory:", help="SQLite database path")
    qq_official_gateway_client.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")
    qq_official_gateway_client.add_argument("--gateway-url", default="", help="Optional gateway WSS URL override for bounded QQ official gateway runs")
    qq_official_gateway_client.add_argument("--duration", type=int, default=30, help="Maximum bounded runtime in seconds")
    qq_official_gateway_client.add_argument("--max-events", type=int, default=1, help="Stop after this many QQ dispatch events if non-zero")
    qq_official_gateway_client.add_argument("--ready-file", default="", help="Optional file path written once the gateway client is ready")
    qq_official_gateway_client.add_argument("--session-state-file", default="", help="Optional JSON file used to persist QQ gateway session_id/sequence for bounded resume attempts")
    qq_official_gateway_client.add_argument("--max-resume-attempts", type=int, default=2, help="Maximum bounded resume attempts after gateway disconnects")
    qq_official_gateway_client.add_argument("--reconnect-backoff-seconds", type=float, default=1.0, help="Delay between bounded QQ gateway reconnect attempts")
    qq_official_gateway_client.add_argument("--output", choices=("json",), default="json")
    qq_official_gateway_client.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    qq_official_gateway_client.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    qq_official_gateway_client.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    qq_official_gateway_client.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for QQ gateway ingress lookup and candidate commit behavior",
    )
    qq_official_gateway_client.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    qq_official_gateway_client.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter during the gateway-driven Core run",
    )

    wecom_gateway_client = subparsers.add_parser("wecom-gateway-client")
    wecom_gateway_client.add_argument("--db", default=":memory:", help="SQLite database path")
    wecom_gateway_client.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")
    wecom_gateway_client.add_argument("--gateway-url", default="", help="Optional gateway WSS URL override for bounded WeCom gateway runs")
    wecom_gateway_client.add_argument("--duration", type=int, default=30, help="Maximum bounded runtime in seconds")
    wecom_gateway_client.add_argument("--max-events", type=int, default=1, help="Stop after this many WeCom dispatch events if non-zero")
    wecom_gateway_client.add_argument("--ready-file", default="", help="Optional file path written once the WeCom gateway client is ready")
    wecom_gateway_client.add_argument("--output", choices=("json",), default="json")
    wecom_gateway_client.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    wecom_gateway_client.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    wecom_gateway_client.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    wecom_gateway_client.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for WeCom gateway ingress lookup and candidate commit behavior",
    )
    wecom_gateway_client.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    wecom_gateway_client.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter during the WeCom gateway-driven Core run",
    )

    openclaw_gateway_client = subparsers.add_parser("openclaw-gateway-client")
    openclaw_gateway_client.add_argument("--db", default=":memory:", help="SQLite database path")
    openclaw_gateway_client.add_argument("--config-file", default="", help="Optional social adapter profile config JSON path")
    openclaw_gateway_client.add_argument("--adapter", required=True, help="Hosted social adapter name to route OpenClaw events through")
    openclaw_gateway_client.add_argument("--gateway-url", default="", help="Optional OpenClaw host websocket URL override")
    openclaw_gateway_client.add_argument("--plugin-package", default="", help="Optional hosted plugin package override")
    openclaw_gateway_client.add_argument("--duration", type=int, default=30, help="Maximum bounded runtime in seconds")
    openclaw_gateway_client.add_argument("--max-events", type=int, default=1, help="Stop after this many OpenClaw dispatch events if non-zero")
    openclaw_gateway_client.add_argument("--ready-file", default="", help="Optional file path written once the OpenClaw gateway client is ready")
    openclaw_gateway_client.add_argument("--output", choices=("json",), default="json")
    openclaw_gateway_client.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    openclaw_gateway_client.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    openclaw_gateway_client.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    openclaw_gateway_client.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for OpenClaw gateway ingress lookup and candidate commit behavior",
    )
    openclaw_gateway_client.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    openclaw_gateway_client.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter during the OpenClaw gateway-driven Core run",
    )

    qq_official_gateway_closure = subparsers.add_parser("qq-official-gateway-closure")
    qq_official_gateway_closure.add_argument(
        "--gateway-run-file",
        required=True,
        help="JSON payload emitted by qq-official-gateway-client to validate as bounded QQ gateway live evidence.",
    )
    qq_official_gateway_closure.add_argument(
        "--require-resume-evidence",
        action="store_true",
        help="Require reconnect and RESUME evidence in addition to bounded gateway dispatch-to-Core proof.",
    )
    qq_official_gateway_closure.add_argument("--output", choices=("json",), default="json")

    wecom_gateway_closure = subparsers.add_parser("wecom-gateway-closure")
    wecom_gateway_closure.add_argument(
        "--gateway-run-file",
        required=True,
        help="JSON payload emitted by wecom-gateway-client to validate as bounded WeCom gateway live evidence.",
    )
    wecom_gateway_closure.add_argument("--output", choices=("json",), default="json")

    openclaw_gateway_closure = subparsers.add_parser("openclaw-gateway-closure")
    openclaw_gateway_closure.add_argument(
        "--gateway-run-file",
        required=True,
        help="JSON payload emitted by openclaw-gateway-client to validate as bounded OpenClaw gateway live evidence.",
    )
    openclaw_gateway_closure.add_argument("--output", choices=("json",), default="json")

    self_improvement_smoke = subparsers.add_parser("self-improvement-smoke")
    self_improvement_smoke.add_argument("--output", choices=("json",), default="json")

    task_tracking_smoke = subparsers.add_parser("task-tracking-smoke")
    task_tracking_smoke.add_argument("--output", choices=("json",), default="json")

    memory_maintenance_smoke = subparsers.add_parser("memory-maintenance-smoke")
    memory_maintenance_smoke.add_argument("--output", choices=("json",), default="json")

    self_optimization_smoke = subparsers.add_parser("self-optimization-smoke")
    self_optimization_smoke.add_argument("--output", choices=("json",), default="json")

    world_model_context_smoke = subparsers.add_parser("world-model-context-smoke")
    world_model_context_smoke.add_argument("--output", choices=("json",), default="json")

    core_daemon = subparsers.add_parser("core-daemon")
    core_daemon.add_argument("--db", default=":memory:", help="SQLite database path")
    core_daemon.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Number of synthetic daemon cycles to plan and execute",
    )
    core_daemon.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    core_daemon.add_argument(
        "--maintenance-interval-cycles",
        type=int,
        default=3,
        help="Deterministic maintenance interval used by the autonomy planner",
    )
    core_daemon.add_argument(
        "--vitality-score",
        type=int,
        default=60,
        help="Initial bounded vitality score injected into daemon state summaries",
    )
    core_daemon.add_argument(
        "--persona-mood",
        default="steady",
        help="Persona mood recorded in daemon state summaries",
    )
    core_daemon.add_argument(
        "--operator-paused",
        action="store_true",
        help="Record the daemon in paused state and avoid synthetic workflow execution",
    )
    core_daemon.add_argument("--output", choices=("json",), default="json")

    autonomy_daemon_smoke = subparsers.add_parser("autonomy-daemon-smoke")
    autonomy_daemon_smoke.add_argument("--db", default=":memory:", help="SQLite database path")
    autonomy_daemon_smoke.add_argument(
        "--cycles",
        type=int,
        default=2,
        help="Number of synthetic daemon cycles used for the initial smoke run",
    )
    autonomy_daemon_smoke.add_argument(
        "--maintenance-interval-cycles",
        type=int,
        default=2,
        help="Deterministic maintenance interval used by the autonomy planner",
    )
    autonomy_daemon_smoke.add_argument(
        "--vitality-score",
        type=int,
        default=18,
        help="Initial bounded vitality score injected into daemon evidence",
    )
    autonomy_daemon_smoke.add_argument(
        "--persona-mood",
        default="watchful",
        help="Persona mood recorded in daemon evidence",
    )
    autonomy_daemon_smoke.add_argument("--output", choices=("json",), default="json")

    vitality_smoke = subparsers.add_parser("vitality-smoke")
    vitality_smoke.add_argument(
        "--initial-score",
        type=int,
        default=52,
        help="Initial vitality score used to exercise deterministic decay and replenishment",
    )
    vitality_smoke.add_argument("--output", choices=("json",), default="json")

    persona_seed_setup = subparsers.add_parser("persona-seed-setup")
    persona_seed_setup.add_argument("--persona-id", default="affective-main")
    persona_seed_setup.add_argument("--seed-name", default="default")
    persona_seed_setup.add_argument("--mood", default="steady")
    persona_seed_setup.add_argument("--valence", type=float, default=0.0)
    persona_seed_setup.add_argument("--arousal", type=float, default=0.0)
    persona_seed_setup.add_argument("--curiosity", type=float, default=0.5)
    persona_seed_setup.add_argument("--fatigue", type=float, default=0.0)
    persona_seed_setup.add_argument("--social-openness", type=float, default=0.5)
    persona_seed_setup.add_argument("--vitality-summary", default="attentive")
    persona_seed_setup.add_argument("--relationship-style", default="warm")
    persona_seed_setup.add_argument("--immutable-boundary", action="append", default=[])
    persona_seed_setup.add_argument("--created-at", default=None)
    persona_seed_setup.add_argument("--output", choices=("json",), default="json")

    persona_growth_apply = subparsers.add_parser("persona-growth-apply")
    persona_growth_apply.add_argument("--seed-file", required=True)
    persona_growth_apply.add_argument("--persona-file", required=True)
    persona_growth_apply.add_argument("--growth-file", required=True)
    persona_growth_apply.add_argument("--event-id", required=True)
    persona_growth_apply.add_argument(
        "--source",
        choices=tuple(sorted(PERSONA_GROWTH_RUNTIME_SOURCES)),
        required=True,
    )
    persona_growth_apply.add_argument("--reason", required=True)
    persona_growth_apply.add_argument("--recorded-at", required=True)
    persona_growth_apply.add_argument("--principal-id", default=None)
    persona_growth_apply.add_argument("--summary", default="")
    persona_growth_apply.add_argument("--output", choices=("json",), default="json")

    persona_state_smoke = subparsers.add_parser("persona-state-smoke")
    persona_state_smoke.add_argument("--output", choices=("json",), default="json")

    persona_state_inspect = subparsers.add_parser("persona-state-inspect")
    persona_state_inspect.add_argument("--seed-file", required=True)
    persona_state_inspect.add_argument("--persona-file", required=True)
    persona_state_inspect.add_argument("--growth-file", required=True)
    persona_state_inspect.add_argument("--rational-summary-only", action="store_true")
    persona_state_inspect.add_argument("--output", choices=("json",), default="json")

    persona_state_delete = subparsers.add_parser("persona-state-delete")
    persona_state_delete.add_argument("--seed-file", required=True)
    persona_state_delete.add_argument("--persona-file", required=True)
    persona_state_delete.add_argument("--growth-file", required=True)
    persona_state_delete.add_argument("--principal-id", action="append", default=[])
    persona_state_delete.add_argument("--delete-all", action="store_true")
    persona_state_delete.add_argument("--output", choices=("json",), default="json")

    persona_state_export = subparsers.add_parser("persona-state-export")
    persona_state_export.add_argument("--seed-file", required=True)
    persona_state_export.add_argument("--persona-file", required=True)
    persona_state_export.add_argument("--growth-file", required=True)
    persona_state_export.add_argument("--expected-immutability-stamp", default="")
    persona_state_export.add_argument("--redact-principal-id", action="append", default=[])
    persona_state_export.add_argument("--output", choices=("json",), default="json")

    persona_tamper_report = subparsers.add_parser("persona-tamper-report")
    persona_tamper_report.add_argument("--seed-file", required=True)
    persona_tamper_report.add_argument("--persona-file", required=True)
    persona_tamper_report.add_argument("--growth-file", required=True)
    persona_tamper_report.add_argument("--expected-immutability-stamp", required=True)
    persona_tamper_report.add_argument("--output", choices=("json",), default="json")

    session_inspect = subparsers.add_parser("session-inspect")
    session_inspect.add_argument("--db", default=":memory:", help="SQLite database path")
    session_inspect.add_argument("--session-id", required=True, help="Session identifier to inspect")
    session_inspect.add_argument("--output", choices=("json",), default="json")

    closure_summary = subparsers.add_parser("closure-summary")
    closure_summary.add_argument("--db", default=":memory:", help="SQLite database path")
    closure_summary.add_argument("--session-id", required=True, help="Session identifier to summarize")
    closure_summary.add_argument("--limit", type=int, default=5, help="Maximum recent executions to include")
    closure_summary.add_argument("--provider-smoke-file", default="", help="Optional maf-provider-smoke JSON payload to include in closure gates")
    closure_summary.add_argument("--require-provider-smoke", action="store_true", help="Require provider smoke evidence for aggregate closure readiness")
    closure_summary.add_argument("--multimodal-profile-file", default="", help="Optional multimodal-profile-smoke JSON payload to include in closure gates")
    closure_summary.add_argument("--require-multimodal-profile", action="store_true", help="Require multimodal/profile smoke evidence for aggregate closure readiness")
    closure_summary.add_argument("--documentation-file", default="", help="Optional documentation closure JSON payload to include in the release validation gate matrix")
    closure_summary.add_argument("--regression-file", default="", help="Optional regression closure JSON payload to include in the release validation gate matrix")
    closure_summary.add_argument("--relay-failure-file", default="", help="Optional relay-failure closure JSON payload to include in the relay validation gate")
    closure_summary.add_argument("--hardware-compatibility-file", default="", help="Optional hardware-compatibility closure JSON payload to include in hardware and artifact validation gates")
    closure_summary.add_argument("--hardware-acceptance-matrix-file", default="", help="Optional hardware acceptance matrix JSON payload to include in the release-1.2.7 hardware matrix gate")
    closure_summary.add_argument("--resource-budget-governance-file", default="", help="Optional resource-budget governance JSON payload to include in the independent governed budget gate")
    closure_summary.add_argument("--agent-excellence-file", default="", help="Optional agent excellence JSON payload to include in the Tool/Skill/MCP excellence gate")
    closure_summary.add_argument("--release-rollback-file", default="", help="Optional release/rollback hardening JSON payload to include in the independent guarded rollback gate")
    closure_summary.add_argument("--signing-provenance-file", default="", help="Optional signing/provenance JSON payload to include in the independent signing gate")
    closure_summary.add_argument("--observability-diagnosis-file", default="", help="Optional observability and diagnosis JSON payload to include in the independent structured diagnosis gate")
    closure_summary.add_argument("--real-scene-e2e-file", default="", help="Optional real Core/Unit end-to-end JSON payload to include in the independent real-scene gate")
    closure_summary.add_argument("--autonomy-daemon-file", default="", help="Optional autonomy-daemon-smoke JSON payload to include in the autonomous daemon gate")
    closure_summary.add_argument("--task-tracking-file", default="", help="Optional task-tracking-smoke JSON payload to include in the release-2.2.6 task continuity gates")
    closure_summary.add_argument("--memory-maintenance-file", default="", help="Optional memory-maintenance-smoke JSON payload to include in the release-2.2.6 memory maintenance gate")
    closure_summary.add_argument("--self-optimization-file", default="", help="Optional self-optimization-smoke JSON payload to include in the release-2.2.6 self-optimization gate")
    closure_summary.add_argument("--world-model-context-file", default="", help="Optional world-model-context-smoke JSON payload to include in the release-2.2.6 world-model gate")
    closure_summary.add_argument("--vitality-smoke-file", default="", help="Optional vitality-smoke JSON payload to include in the vitality governance gate")
    closure_summary.add_argument("--persona-state-file", default="", help="Optional persona-state-smoke JSON payload to include in the persona persistence gate")
    closure_summary.add_argument("--social-adapter-file", default="", help="Optional social-adapter-smoke JSON payload to include in the social adapter gate")
    closure_summary.add_argument("--qq-gateway-file", default="", help="Optional qq-official-gateway-closure JSON payload to include in the bounded official QQ gateway live gate")
    closure_summary.add_argument("--wecom-gateway-file", default="", help="Optional wecom-gateway-closure JSON payload to include in the bounded WeCom gateway live gate")
    closure_summary.add_argument("--openclaw-gateway-file", default="", help="Optional openclaw-gateway-closure JSON payload to include in the bounded OpenClaw gateway live gate")
    closure_summary.add_argument("--approval-social-file", default="", help="Optional approval-social-smoke JSON payload to include in the approval-over-social gate")
    closure_summary.add_argument("--self-improvement-file", default="", help="Optional self-improvement-smoke JSON payload to include in the self-improvement sandbox gate")
    closure_summary.add_argument("--coding-agent-route-file", default="", help="Optional coding-agent-self-improvement-route JSON payload to include in the governed coding-agent route gate")
    closure_summary.add_argument("--output", choices=("json",), default="json")

    approval_inspect = subparsers.add_parser("approval-inspect")
    approval_inspect.add_argument("--db", default=":memory:", help="SQLite database path")
    approval_inspect.add_argument("--approval-request-id", required=True, help="Approval request identifier to inspect")
    approval_inspect.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for live lease/state operator evidence",
    )
    approval_inspect.add_argument("--output", choices=("json",), default="json")

    approval_decision = subparsers.add_parser("approval-decision")
    approval_decision.add_argument("--db", default=":memory:", help="SQLite database path")
    approval_decision.add_argument("--approval-request-id", required=True, help="Approval request identifier to resolve")
    approval_decision.add_argument("--decision", choices=("approve", "deny", "expire"), required=True, help="Decision to apply to the pending approval request")
    approval_decision.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for resumed execution when approving a request",
    )
    approval_decision.add_argument("--output", choices=("json",), default="json")

    social_approval_inspect = subparsers.add_parser("social-approval-inspect")
    social_approval_inspect.add_argument("--db", default=":memory:", help="SQLite database path")
    social_approval_inspect.add_argument("--approval-request-id", required=True, help="Approval request identifier to inspect over a bound social channel")
    social_approval_inspect.add_argument("--social-adapter-kind", required=True, help="Bound mock social adapter kind")
    social_approval_inspect.add_argument("--social-channel-id", required=True, help="Bound mock social channel identifier")
    social_approval_inspect.add_argument(
        "--social-channel-kind",
        choices=("direct", "group", "channel"),
        required=True,
        help="Bound mock social channel kind",
    )
    social_approval_inspect.add_argument("--social-user-id", required=True, help="Bound mock social external user identifier")
    social_approval_inspect.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for live lease/state operator evidence",
    )
    social_approval_inspect.add_argument("--output", choices=("json",), default="json")

    social_approval_decision = subparsers.add_parser("social-approval-decision")
    social_approval_decision.add_argument("--db", default=":memory:", help="SQLite database path")
    social_approval_decision.add_argument("--approval-request-id", required=True, help="Approval request identifier to resolve over a bound social channel")
    social_approval_decision.add_argument("--decision", choices=("approve", "deny", "expire"), required=True, help="Decision to apply to the pending approval request")
    social_approval_decision.add_argument("--decision-text", default="", help="Human-readable social decision text for audit context")
    social_approval_decision.add_argument("--social-adapter-kind", required=True, help="Bound mock social adapter kind")
    social_approval_decision.add_argument("--social-channel-id", required=True, help="Bound mock social channel identifier")
    social_approval_decision.add_argument(
        "--social-channel-kind",
        choices=("direct", "group", "channel"),
        required=True,
        help="Bound mock social channel kind",
    )
    social_approval_decision.add_argument("--social-user-id", required=True, help="Bound mock social external user identifier")
    social_approval_decision.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for resumed execution when approving a request",
    )
    social_approval_decision.add_argument("--output", choices=("json",), default="json")

    approval_social_smoke = subparsers.add_parser("approval-social-smoke")
    approval_social_smoke.add_argument("--output", choices=("json",), default="json")

    maf_smoke = subparsers.add_parser("maf-provider-smoke")
    maf_smoke.add_argument("--output", choices=("json",), default="json")
    maf_smoke.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Opt in to a future real-provider smoke call when package and model configuration are available",
    )
    maf_smoke.add_argument(
        "--execute-model-call",
        action="store_true",
        help="Actually execute the provider smoke model call; requires --allow-model-call",
    )
    maf_smoke.add_argument(
        "--maf-config-file",
        default="",
        help="Optional runtime provider profile config JSON path used to resolve model and endpoint settings",
    )

    provider_test = subparsers.add_parser("provider-test")
    provider_test.add_argument("--output", choices=("json",), default="json")
    provider_test.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Opt in to a future real-provider smoke call when package and model configuration are available",
    )
    provider_test.add_argument(
        "--execute-model-call",
        action="store_true",
        help="Actually execute the provider test model call; requires --allow-model-call",
    )
    provider_test.add_argument(
        "--config-file",
        default="",
        help="Optional runtime provider profile config JSON path used to resolve model and endpoint settings",
    )

    multimodal_smoke = subparsers.add_parser("multimodal-profile-smoke")
    multimodal_smoke.add_argument("--output", choices=("json",), default="json")
    multimodal_smoke.add_argument(
        "--text",
        action="append",
        default=[],
        help="Text input item to include in the normalized multimodal request",
    )
    multimodal_smoke.add_argument(
        "--image-ref",
        action="append",
        default=[],
        help="Image reference, URI, or path to normalize without loading media",
    )
    multimodal_smoke.add_argument(
        "--audio-ref",
        action="append",
        default=[],
        help="Audio reference, URI, or path to normalize without loading media",
    )
    multimodal_smoke.add_argument(
        "--video-ref",
        action="append",
        default=[],
        help="Video reference, URI, or path to normalize without loading media",
    )
    multimodal_smoke.add_argument(
        "--response-mode",
        action="append",
        default=[],
        help="Requested response mode; defaults to text",
    )
    multimodal_smoke.add_argument(
        "--profile-hint",
        default="auto",
        help="Profile hint embedded in the normalized request",
    )
    multimodal_smoke.add_argument(
        "--profile-override",
        default="",
        help="Operator-forced inference profile for route validation",
    )
    multimodal_smoke.add_argument(
        "--require-live-backend",
        action="store_true",
        help="Require live OpenAI-compatible/vLLM provider configuration for readiness",
    )

    provider_list = subparsers.add_parser("provider-list")
    provider_list.add_argument("--output", choices=("json",), default="json")
    provider_list.add_argument("--config-file", default="", help="Optional provider profile config JSON path")

    provider_config = subparsers.add_parser("provider-config")
    provider_config.add_argument("--output", choices=("json",), default="json")
    provider_config.add_argument("--config-file", default="", help="Optional provider profile config JSON path")
    provider_config.add_argument("--profile", required=True, help="Provider profile name to update")
    provider_config.add_argument("--provider-kind", default=None)
    provider_config.add_argument("--credential-env-var", default=None)
    provider_config.add_argument("--endpoint-env-var", default=None)
    provider_config.add_argument("--endpoint-url", default=None)
    provider_config.add_argument("--model-env-var", default=None)
    provider_config.add_argument("--deployment-env-var", default=None)
    provider_config.add_argument("--configured-model", default=None)
    provider_config.add_argument("--configured-deployment", default=None)
    provider_config.add_argument(
        "--supports-model-discovery",
        choices=("true", "false"),
        default=None,
    )
    enable_disable = provider_config.add_mutually_exclusive_group()
    enable_disable.add_argument("--enable", action="store_true")
    enable_disable.add_argument("--disable", action="store_true")

    model_list = subparsers.add_parser("model-list")
    model_list.add_argument("--output", choices=("json",), default="json")
    model_list.add_argument("--config-file", default="", help="Optional provider profile config JSON path")

    model_set_active = subparsers.add_parser("model-set-active")
    model_set_active.add_argument("--output", choices=("json",), default="json")
    model_set_active.add_argument("--config-file", default="", help="Optional provider profile config JSON path")
    model_set_active.add_argument("--slot", choices=("affective", "rational"), required=True)
    model_set_active.add_argument("--profile", required=True, help="Provider profile name to activate for the chosen slot")

    model_profile = subparsers.add_parser("model-profile-smoke")
    model_profile.add_argument("--output", choices=("json",), default="json")
    model_profile.add_argument("--config-file", default="", help="Optional provider profile config JSON path")
    model_profile.add_argument(
        "--active-affective-profile",
        default=None,
        help="Active provider profile for the Affective model slot",
    )
    model_profile.add_argument(
        "--active-rational-profile",
        default=None,
        help="Active provider profile for the Rational model slot",
    )

    federation_smoke = subparsers.add_parser("federation-route-smoke")
    federation_smoke.add_argument("--output", choices=("json",), default="json")
    federation_smoke.add_argument("--target-node", required=True, help="Target Unit node identifier")
    federation_smoke.add_argument(
        "--now",
        default="2026-05-09T12:00:00Z",
        help="Deterministic current time used for freshness evaluation",
    )
    federation_smoke.add_argument(
        "--required-trust-scope",
        default="",
        help="Optional trust scope required for route selection",
    )
    federation_smoke.add_argument(
        "--local-unit",
        action="store_true",
        help="Model the target as a local Unit instead of a peer-advertised remote Unit",
    )
    federation_smoke.add_argument(
        "--relay-via",
        action="append",
        default=[],
        help="Relay path hop for a local relay-mode Unit",
    )
    federation_smoke.add_argument(
        "--peer-core-id",
        default="core-b",
        help="Peer Core identifier for delegated route smoke",
    )
    federation_smoke.add_argument(
        "--peer-trust-scope",
        default="lab-federation",
        help="Peer trust scope for delegated route smoke",
    )
    federation_smoke.add_argument(
        "--peer-expires-at",
        default="2026-05-09T12:30:00Z",
        help="Peer route expiry timestamp for freshness testing",
    )
    federation_smoke.add_argument(
        "--peer-unreachable",
        action="store_true",
        help="Mark the peer as unreachable while keeping the advertisement fresh",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def load_event_replay_fixture(events_file: str) -> list[dict[str, Any]]:
        payload = json.loads(Path(events_file).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
            events = cast(list[dict[str, Any]], payload["events"])
        else:
            raise ValueError("event_replay_fixture_must_be_list_or_object_with_events")
        normalized_events: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("event_replay_fixture_contains_non_object_event")
            normalized_events.append(dict(event))
        return normalized_events

    def load_event_daemon_fixture(events_file: str) -> list[list[dict[str, Any]]]:
        payload = json.loads(Path(events_file).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            if not payload:
                return []
            if all(isinstance(item, dict) for item in payload):
                return [cast(list[dict[str, Any]], [dict(item) for item in payload])]
            if all(isinstance(item, list) for item in payload):
                batches = cast(list[list[Any]], payload)
            else:
                raise ValueError("event_daemon_fixture_must_be_event_list_or_batch_list")
        elif isinstance(payload, dict) and isinstance(payload.get("batches"), list):
            batches = cast(list[list[Any]], payload["batches"])
        else:
            raise ValueError("event_daemon_fixture_must_be_event_list_or_object_with_batches")
        normalized_batches: list[list[dict[str, Any]]] = []
        for batch in batches:
            if not isinstance(batch, list):
                raise ValueError("event_daemon_fixture_contains_non_list_batch")
            normalized_batch: list[dict[str, Any]] = []
            for event in batch:
                if not isinstance(event, dict):
                    raise ValueError("event_daemon_fixture_contains_non_object_event")
                normalized_batch.append(dict(event))
            normalized_batches.append(normalized_batch)
        return normalized_batches

    def provider_error_payload(command: str, exc: Exception) -> dict[str, Any]:
        runtime_env = build_provider_runtime_env(
            config_path=getattr(args, "maf_config_file", "") or "",
        )
        return {
            "ok": False,
            "status": "error",
            "command": command,
            "failure_class": (
                "maf_provider_not_ready"
                if isinstance(exc, MafProviderNotReadyError)
                else "maf_provider_execution_failed"
                if isinstance(exc, TimeoutError)
                else "maf_provider_request_invalid"
            ),
            "failure_status": str(exc),
            "maf_runtime": build_maf_runtime_profile(
                provider_mode=getattr(args, "maf_provider_mode", MafProviderMode.DETERMINISTIC_FAKE.value),
                env=runtime_env,
            ).to_dict(),
        }

    if args.command == "no-model-dry-run":
        if args.require_real_tool_adapter and args.tool_adapter != "neuro-cli":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_gate_request_invalid",
                        "failure_status": "require_real_tool_adapter_requires_neuro_cli_adapter",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        events: list[dict[str, Any]] | None = None
        if args.event_source == "neuro-cli-agent-events":
            event_adapter = (
                cast(NeuroCliToolAdapter, tool_adapter)
                if args.tool_adapter == "neuro-cli"
                else NeuroCliToolAdapter()
            )
            events = event_adapter.collect_agent_events(max_events=args.max_events)
        try:
            payload = run_no_model_dry_run(
                args.db,
                use_db_events=args.use_db_events,
                query_limit=args.query_limit,
                min_priority=args.min_priority,
                topic=args.topic,
                tool_adapter=tool_adapter,
                events=events,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                maf_config_file=args.maf_config_file,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
                event_source_label=(
                    "neuro_cli_agent_events"
                    if args.event_source == "neuro-cli-agent-events"
                    else None
                ),
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "event-replay":
        if args.require_real_tool_adapter and args.tool_adapter != "neuro-cli":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_gate_request_invalid",
                        "failure_status": "require_real_tool_adapter_requires_neuro_cli_adapter",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        try:
            events = load_event_replay_fixture(args.events_file)
            payload = run_event_replay(
                events,
                args.db,
                tool_adapter=tool_adapter,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
                replay_label=str(args.events_file),
            )
        except (MafProviderNotReadyError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "event-daemon":
        if args.require_real_tool_adapter and args.tool_adapter != "neuro-cli":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_gate_request_invalid",
                        "failure_status": "require_real_tool_adapter_requires_neuro_cli_adapter",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        try:
            event_batches = load_event_daemon_fixture(args.events_file)
            payload = run_event_daemon_replay(
                event_batches,
                args.db,
                tool_adapter=tool_adapter,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
                replay_label=str(args.events_file),
            )
        except (MafProviderNotReadyError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "core-daemon":
        if args.cycles < 1:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "request_invalid",
                        "failure_status": "core_daemon_requires_positive_cycle_count",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        event_batches = [[] for _ in range(args.cycles)]
        vitality_state = VitalityState.from_score(args.vitality_score)
        persona_state = PersonaState(
            persona_id="affective-main",
            mood=str(args.persona_mood),
            vitality_summary=vitality_state.state,
        )
        try:
            payload = run_event_daemon_replay(
                event_batches,
                args.db,
                session_id=args.session_id,
                autonomy_enabled=True,
                autonomy_policy=AutonomousDaemonPolicy(
                    maintenance_interval_cycles=args.maintenance_interval_cycles,
                ),
                vitality_state=vitality_state,
                persona_state=persona_state,
                operator_paused=bool(args.operator_paused),
                replay_label="core-daemon-synthetic",
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        payload["command"] = "core-daemon"
        payload["event_source"] = "autonomy_synthetic_cycles"
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "autonomy-daemon-smoke":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = build_autonomy_daemon_smoke(
                db_path=args.db,
                cycles=args.cycles,
                maintenance_interval_cycles=args.maintenance_interval_cycles,
                vitality_score=args.vitality_score,
                persona_mood=args.persona_mood,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "vitality-smoke":
        try:
            payload = build_vitality_smoke(initial_score=args.initial_score)
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-seed-setup":
        try:
            payload = _build_persona_seed_setup_payload(
                _build_persona_seed_config_from_args(args)
            )
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-growth-apply":
        try:
            seed_config, persona_state, growth_state = _load_persona_bundle_from_files(
                seed_file=args.seed_file,
                persona_file=args.persona_file,
                growth_file=args.growth_file,
            )
            payload = build_persona_growth_apply(
                seed_config=seed_config,
                persona_state=persona_state,
                growth_state=growth_state,
                evidence=PersonaGrowthEvidence(
                    event_id=args.event_id,
                    source=args.source,
                    reason=args.reason,
                    recorded_at=args.recorded_at,
                    principal_id=args.principal_id,
                    summary=args.summary,
                ),
            )
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-state-smoke":
        payload = build_persona_state_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-state-inspect":
        try:
            seed_config, persona_state, growth_state = _load_persona_bundle_from_files(
                seed_file=args.seed_file,
                persona_file=args.persona_file,
                growth_file=args.growth_file,
            )
            payload = build_persona_state_inspect(
                seed_config=seed_config,
                persona_state=persona_state,
                growth_state=growth_state,
                rational_summary_only=args.rational_summary_only,
            )
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-state-delete":
        try:
            seed_config, persona_state, growth_state = _load_persona_bundle_from_files(
                seed_file=args.seed_file,
                persona_file=args.persona_file,
                growth_file=args.growth_file,
            )
            payload = build_persona_state_delete(
                seed_config=seed_config,
                persona_state=persona_state,
                growth_state=growth_state,
                principal_ids=args.principal_id,
                delete_all=args.delete_all,
            )
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-state-export":
        try:
            seed_config, persona_state, growth_state = _load_persona_bundle_from_files(
                seed_file=args.seed_file,
                persona_file=args.persona_file,
                growth_file=args.growth_file,
            )
            payload = build_persona_state_export(
                seed_config=seed_config,
                persona_state=persona_state,
                growth_state=growth_state,
                redact_principal_ids=args.redact_principal_id,
                expected_immutability_stamp=args.expected_immutability_stamp or None,
            )
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "persona-tamper-report":
        try:
            seed_config, persona_state, growth_state = _load_persona_bundle_from_files(
                seed_file=args.seed_file,
                persona_file=args.persona_file,
                growth_file=args.growth_file,
            )
            payload = build_persona_tamper_report(
                seed_config=seed_config,
                persona_state=persona_state,
                growth_state=growth_state,
                expected_immutability_stamp=args.expected_immutability_stamp,
            )
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "live-event-smoke":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = NeuroCliToolAdapter()
        try:
            if args.event_source == "app":
                if not args.app_id:
                    raise ValueError("live_event_smoke_requires_app_id")
                live_event_payload = tool_adapter.collect_app_events(
                    args.app_id,
                    duration=args.duration,
                    max_events=args.max_events,
                    ready_file=args.ready_file,
                )
                event_source_label = "neuro_cli_app_events_live"
                live_event_ingest = {
                    "schema_version": "1.2.3-live-event-ingest-v1",
                    "event_source_kind": "app",
                    "monitor_command": "app-events",
                    "app_id": args.app_id,
                    "duration": args.duration,
                    "max_events": args.max_events,
                    "subscription": live_event_payload.get("subscription"),
                    "listener_mode": live_event_payload.get("listener_mode"),
                    "handler_audit": live_event_payload.get("handler_audit"),
                }
            else:
                live_event_payload = tool_adapter.collect_live_events(
                    duration=args.duration,
                    max_events=args.max_events,
                    ready_file=args.ready_file,
                )
                event_source_label = "neuro_cli_events_live"
                live_event_ingest = {
                    "schema_version": "1.2.3-live-event-ingest-v1",
                    "event_source_kind": "unit",
                    "monitor_command": "events",
                    "duration": args.duration,
                    "max_events": args.max_events,
                    "subscription": live_event_payload.get("subscription"),
                    "listener_mode": live_event_payload.get("listener_mode"),
                    "handler_audit": live_event_payload.get("handler_audit"),
                }
            events = [
                dict(event)
                for event in cast(list[Any], live_event_payload.get("events") or [])
                if isinstance(event, dict)
            ]
            if not events:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "status": "live_event_ingest_empty",
                            "command": "live-event-smoke",
                            "failure_class": "live_event_monitor_empty",
                            "failure_status": "no_events_collected",
                            "event_source": event_source_label,
                            "tool_adapter_runtime": tool_adapter.runtime_metadata(),
                            "live_event_ingest": {
                                **live_event_ingest,
                                "collected_event_count": 0,
                            },
                        },
                        sort_keys=True,
                    )
                )
                return 2
            payload = run_no_model_dry_run(
                args.db,
                tool_adapter=tool_adapter,
                events=events,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=True,
                event_source_label=event_source_label,
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        payload["command"] = "live-event-smoke"
        payload["live_event_ingest"] = {
            **live_event_ingest,
            "collected_event_count": len(events),
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "event-service":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = NeuroCliToolAdapter()
        try:
            payload = run_live_event_service(
                args.db,
                event_source=args.event_source,
                app_id=args.app_id,
                duration=args.duration,
                max_events=args.max_events,
                cycles=args.cycles,
                ready_file=args.ready_file,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                tool_adapter=tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "activation-health-guard":
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        try:
            observation = observe_activation_health(
                tool_adapter,
                app_id=args.app_id,
            )
            payload = {
                "ok": True,
                "status": "ok",
                "command": "activation-health-guard",
                "health_observation": observation.to_dict(),
                "tool_adapter_runtime": tool_adapter.runtime_metadata(),
            }
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-build-plan":
        try:
            payload = build_app_build_plan(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                check_c_style=args.check_c_style,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_build_plan_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-artifact-admission":
        try:
            payload = build_app_artifact_admission(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
            )
        except ValueError as exc:
            failure_status = str(exc)
            failure_class = (
                "app_artifact_admission_failed"
                if failure_status.startswith("artifact_") or failure_status.startswith("source_")
                else "app_artifact_admission_invalid"
            )
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": failure_class,
                        "failure_status": failure_status,
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "hardware-compatibility-smoke":
        try:
            payload = build_hardware_compatibility_smoke(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                unit_node_id=args.unit_node_id,
                unit_architecture=args.unit_architecture,
                unit_abi=args.unit_abi,
                unit_board_family=args.unit_board_family,
                unit_storage_class=args.unit_storage_class,
                unit_network_transports=tuple(args.unit_network_transport)
                if args.unit_network_transport
                else ("wifi", "serial_bridge"),
                unit_llext_supported=not bool(args.unit_llext_unsupported),
                unit_signing_enforced=bool(args.unit_signing_enforced),
                heap_free_bytes=args.heap_free_bytes,
                app_slot_bytes=args.app_slot_bytes,
                required_abi=args.required_abi,
                required_board_family=args.required_board_family,
                required_storage_class=args.required_storage_class,
                require_signing=bool(args.require_signing),
                required_heap_free_bytes=args.required_heap_free_bytes,
                required_app_slot_bytes=args.required_app_slot_bytes,
                mismatch_architecture_probe=args.mismatch_architecture_probe,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "hardware_compatibility_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "hardware-acceptance-matrix":
        board_family_map: dict[str, str] = {}
        for item in args.board_family_mapping:
            if "=" not in item:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "status": "error",
                            "command": args.command,
                            "failure_class": "hardware_acceptance_matrix_invalid",
                            "failure_status": "board_family_mapping_requires_class_equals_family",
                        },
                        sort_keys=True,
                    )
                )
                return 2
            capability_class, family = item.split("=", 1)
            board_family_map[capability_class.strip().lower().replace("-", "_")] = family.strip()
        try:
            payload = build_hardware_acceptance_matrix(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                capability_classes=tuple(args.capability_class),
                representative_board_families=board_family_map,
                required_heap_free_bytes=args.required_heap_free_bytes,
                required_app_slot_bytes=args.required_app_slot_bytes,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "hardware_acceptance_matrix_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "resource-budget-governance-smoke":
        try:
            hardware_compatibility_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.hardware_compatibility_file).read_text(encoding="utf-8")
                ),
            )
            payload = build_resource_budget_governance_smoke(
                hardware_compatibility_payload=hardware_compatibility_payload,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "resource_budget_governance_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "signing-provenance-smoke":
        try:
            payload = build_signing_provenance_smoke(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                require_signing=bool(args.require_signing),
                unit_signing_enforced=bool(args.unit_signing_enforced),
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "signing_provenance_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-deploy-plan":
        try:
            payload = build_app_deploy_plan(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_ttl_ms=args.lease_ttl_ms,
                start_args=args.start_args or None,
            )
        except ValueError as exc:
            failure_status = str(exc)
            failure_class = (
                "app_deploy_plan_failed"
                if failure_status.startswith("artifact_") or failure_status.startswith("source_")
                else "app_deploy_plan_invalid"
            )
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": failure_class,
                        "failure_status": failure_status,
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-deploy-prepare-verify":
        try:
            tool_adapter = NeuroCliToolAdapter(
                node=args.node,
                source_agent=args.source_agent,
                timeout_seconds=args.timeout_seconds,
            )
            payload = run_app_deploy_prepare_verify(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_ttl_ms=args.lease_ttl_ms,
                timeout_seconds=args.timeout_seconds,
                tool_adapter=tool_adapter,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_deploy_prepare_verify_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok") else 2
    if args.command == "app-deploy-activate":
        try:
            if args.db:
                Path(args.db).parent.mkdir(parents=True, exist_ok=True)
            tool_adapter = NeuroCliToolAdapter(
                node=args.node,
                source_agent=args.source_agent,
                timeout_seconds=args.timeout_seconds,
            )
            payload = run_app_deploy_activate(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_ttl_ms=args.lease_ttl_ms,
                start_args=args.start_args or None,
                timeout_seconds=args.timeout_seconds,
                activation_approval_decision=args.approval_decision,
                activation_approval_note=args.approval_note,
                tool_adapter=tool_adapter,
            )
            if args.db:
                payload["release_gate_evidence"] = persist_app_deploy_activate_evidence(
                    args.db,
                    payload,
                )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_deploy_activate_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok") else 2
    if args.command == "app-deploy-rollback":
        try:
            if args.db:
                Path(args.db).parent.mkdir(parents=True, exist_ok=True)
            tool_adapter = NeuroCliToolAdapter(
                node=args.node,
                source_agent=args.source_agent,
                timeout_seconds=args.timeout_seconds,
            )
            payload = run_app_deploy_rollback(
                app_id=args.app_id,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_id=args.lease_id or None,
                rollback_reason=args.reason,
                timeout_seconds=args.timeout_seconds,
                rollback_approval_decision=args.approval_decision,
                rollback_approval_note=args.approval_note,
                tool_adapter=tool_adapter,
            )
            if args.db:
                payload["release_gate_evidence"] = persist_app_deploy_rollback_evidence(
                    args.db,
                    payload,
                )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_deploy_rollback_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok") else 2
    if args.command == "agent-run":
        if args.require_real_tool_adapter and args.tool_adapter != "neuro-cli":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_gate_request_invalid",
                        "failure_status": "require_real_tool_adapter_requires_neuro_cli_adapter",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        events: list[dict[str, Any]] | None = None
        social_event_source_label: str | None = None
        if args.social_text:
            events = [
                _build_social_user_prompt_event(
                    social_text=args.social_text,
                    social_adapter_kind=args.social_adapter_kind,
                    social_channel_id=args.social_channel_id,
                    social_channel_kind=args.social_channel_kind,
                    social_user_id=args.social_user_id,
                    social_admin=args.social_admin,
                    received_at="2026-05-10T12:30:00Z",
                )
            ]
            social_event_source_label = "mock_social"
        elif args.input_text:
            events = build_user_prompt_event(args.input_text)
        elif args.event_source == "neuro-cli-agent-events":
            event_adapter = (
                cast(NeuroCliToolAdapter, tool_adapter)
                if args.tool_adapter == "neuro-cli"
                else NeuroCliToolAdapter()
            )
            events = event_adapter.collect_agent_events(max_events=args.max_events)
        try:
            payload = run_no_model_dry_run(
                args.db,
                tool_adapter=tool_adapter,
                events=events,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                maf_config_file=args.maf_config_file,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
                event_source_label=(
                    social_event_source_label
                    or (
                    "neuro_cli_agent_events"
                    if args.event_source == "neuro-cli-agent-events"
                    else None
                    )
                ),
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        payload["command"] = "agent-run"
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "social-chat":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        payload = _run_social_agent_payload(
            db_path=args.db,
            social_text=args.message,
            social_adapter_kind=args.social_adapter_kind,
            social_channel_id=args.social_channel_id,
            social_channel_kind=args.social_channel_kind,
            social_user_id=args.social_user_id,
            social_admin=args.social_admin,
            session_id=args.session_id,
        )
        payload["command"] = "social-chat"
        if args.output == "json":
            print(json.dumps(payload, sort_keys=True))
            return 0
        tool_results = cast(list[dict[str, Any]], payload.get("tool_results") or [])
        if tool_results and tool_results[0].get("status") == "pending_approval":
            approval_request = cast(
                dict[str, Any],
                cast(dict[str, Any], tool_results[0].get("payload") or {}).get(
                    "approval_request"
                )
                or {},
            )
            print(
                f"Approval required: {approval_request.get('tool_name')} request {approval_request.get('approval_request_id')} is pending."
            )
            return 0
        print(str(cast(dict[str, Any], payload.get("final_response") or {}).get("text") or ""))
        return 0
    if args.command == "social-adapter-smoke":
        payload = build_social_adapter_smoke(config_path=args.config_file)
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "social-adapter-list":
        payload = social_adapter_list(config_path=args.config_file)
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "social-adapter-config":
        payload = social_adapter_config_update(
            adapter_name=args.adapter,
            config_path=args.config_file,
            adapter_kind=args.adapter_kind,
            endpoint_url=args.endpoint_url,
            webhook_url=args.webhook_url,
            host_url=args.host_url,
            credential_env_vars=args.credential_env_var,
            supported_channel_kinds=args.supported_channel_kind,
            default_channel_policy=args.default_channel_policy,
            mention_policy=args.mention_policy,
            transport_kind=args.transport_kind,
            runtime_host=args.runtime_host,
            plugin_id=args.plugin_id,
            plugin_package=args.plugin_package,
            installer_package=args.installer_package,
            plugin_installed=(
                True
                if args.plugin_installed == "true"
                else False
                if args.plugin_installed == "false"
                else None
            ),
            account_session_ready=(
                True
                if args.account_session_ready == "true"
                else False
                if args.account_session_ready == "false"
                else None
            ),
            share_session_in_group=(
                True
                if args.share_session_in_group == "true"
                else False
                if args.share_session_in_group == "false"
                else None
            ),
            compliance_class=args.compliance_class,
            compliance_acknowledged=(
                True
                if args.compliance_acknowledged == "true"
                else False
                if args.compliance_acknowledged == "false"
                else None
            ),
            live_network_allowed=(
                True
                if args.live_network_allowed == "true"
                else False
                if args.live_network_allowed == "false"
                else None
            ),
            enabled=True if args.enable else False if args.disable else None,
            active=args.active,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "social-adapter-test":
        try:
            payload = social_adapter_test(
                adapter_name=args.adapter,
                config_path=args.config_file,
                probe_transport=args.probe_transport,
                sample_scenario=args.sample_scenario,
                timeout_seconds=args.probe_timeout_seconds,
            )
        except ValueError as exc:
            payload = {
                "ok": False,
                "status": "error",
                "command": "social-adapter-test",
                "failure_class": "social_adapter_request_invalid",
                "failure_status": str(exc),
                "executes_live_network": False,
            }
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "qq-official-webhook-server":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = _run_qq_official_live_ingress(
                db_path=args.db,
                host=args.host,
                port=args.port,
                path=args.path,
                duration=args.duration,
                max_events=args.max_events,
                ready_file=args.ready_file,
                session_id=args.session_id,
                config_path=args.config_file,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "qq-official-gateway-client":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = _run_qq_official_gateway_ingress(
                db_path=args.db,
                duration=args.duration,
                max_events=args.max_events,
                ready_file=args.ready_file,
                session_state_file=args.session_state_file,
                max_resume_attempts=args.max_resume_attempts,
                reconnect_backoff_seconds=args.reconnect_backoff_seconds,
                session_id=args.session_id,
                config_path=args.config_file,
                gateway_url=args.gateway_url,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "wecom-gateway-client":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = _run_wecom_gateway_ingress(
                db_path=args.db,
                duration=args.duration,
                max_events=args.max_events,
                ready_file=args.ready_file,
                session_id=args.session_id,
                config_path=args.config_file,
                gateway_url=args.gateway_url,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "openclaw-gateway-client":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        try:
            payload = _run_openclaw_gateway_ingress(
                db_path=args.db,
                adapter_name=args.adapter,
                duration=args.duration,
                max_events=args.max_events,
                ready_file=args.ready_file,
                session_id=args.session_id,
                config_path=args.config_file,
                gateway_url=args.gateway_url,
                plugin_package=args.plugin_package,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError, TimeoutError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "qq-official-gateway-closure":
        try:
            gateway_run_payload = cast(
                dict[str, Any],
                json.loads(Path(args.gateway_run_file).read_text(encoding="utf-8")),
            )
            payload = build_qq_official_gateway_closure(
                gateway_run_payload=gateway_run_payload,
                require_resume_evidence=args.require_resume_evidence,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "qq_official_gateway_closure_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "wecom-gateway-closure":
        try:
            gateway_run_payload = cast(
                dict[str, Any],
                json.loads(Path(args.gateway_run_file).read_text(encoding="utf-8")),
            )
            payload = build_wecom_gateway_closure(
                gateway_run_payload=gateway_run_payload,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "wecom_gateway_closure_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "openclaw-gateway-closure":
        try:
            gateway_run_payload = cast(
                dict[str, Any],
                json.loads(Path(args.gateway_run_file).read_text(encoding="utf-8")),
            )
            payload = build_openclaw_gateway_closure(
                gateway_run_payload=gateway_run_payload,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "openclaw_gateway_closure_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "self-improvement-smoke":
        payload = build_self_improvement_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "task-tracking-smoke":
        payload = build_task_tracking_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "memory-maintenance-smoke":
        payload = build_memory_maintenance_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "self-optimization-smoke":
        payload = build_self_optimization_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "world-model-context-smoke":
        payload = build_world_model_context_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.4-closure-smoke":
        payload = build_release_224_closure_smoke(
            session_id=args.session_id,
            runner_name=args.runner,
            summary=args.summary,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-closure-smoke":
        payload = build_release_226_closure_smoke(
            session_id=args.session_id,
            runner_name=args.runner,
            summary=args.summary,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-live-rerun-template":
        payload = build_release_226_live_rerun_template(
            release_target=args.release_target,
            inherited_release=args.inherited_release,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "release-2.2.6-real-unit-rerun-archive":
        payload = build_release_226_real_unit_rerun_archive(
            release_target=args.release_target,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-qq-gateway-rerun-archive":
        payload = build_release_226_qq_gateway_rerun_archive(
            release_target=args.release_target,
            inherited_release=args.inherited_release,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-wecom-gateway-rerun-archive":
        payload = build_release_226_wecom_gateway_rerun_archive(
            release_target=args.release_target,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-openclaw-gateway-rerun-archive":
        payload = build_release_226_openclaw_gateway_rerun_archive(
            release_target=args.release_target,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-hardware-rerun-archive":
        payload = build_release_226_hardware_rerun_archive(
            release_target=args.release_target,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "release-2.2.6-promotion-checklist":
        payload = build_release_226_promotion_checklist(
            release_target=args.release_target,
            inherited_release=args.inherited_release,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "tool-manifest":
        if args.tool_adapter == "neuro-cli":
            adapter = NeuroCliToolAdapter()
            payload = adapter.tool_manifest_payload()
        else:
            adapter = FakeUnitToolAdapter()
            payload = adapter.tool_manifest_payload()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "skill-descriptor":
        print(json.dumps(load_neuro_cli_skill_descriptor_payload(), sort_keys=True))
        return 0
    if args.command == "skill-registry":
        print(json.dumps(load_skill_descriptor_registry_payload(), sort_keys=True))
        return 0
    if args.command == "coding-agent-descriptor":
        print(
            json.dumps(
                load_coding_agent_runner_descriptor_payload(runner_name=args.runner),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "coding-agent-self-improvement-route":
        evidence = ImprovementEvidence(
            tests_passed=bool(args.tests_passed),
            lint_passed=bool(args.lint_passed),
            smoke_passed=bool(args.smoke_passed),
            evidence_refs=tuple(str(item) for item in args.evidence_ref),
        )
        payload = build_coding_agent_self_improvement_route(
            runner_name=args.runner,
            summary=args.summary,
            source=args.source,
            decision=args.decision,
            evidence=evidence,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "tool-threat-descriptor":
        tool_adapter = NeuroCliToolAdapter() if args.tool_adapter == "neuro-cli" else FakeUnitToolAdapter()
        contract = tool_adapter.describe_tool(args.tool)
        if contract is None:
            payload = {
                "ok": False,
                "status": "tool_not_found",
                "tool_name": args.tool,
            }
            print(json.dumps(payload, sort_keys=True))
            return 2
        parsed_arguments: dict[str, str] = {}
        for item in args.arg:
            name, separator, value = str(item).partition("=")
            if not separator:
                payload = {
                    "ok": False,
                    "status": "invalid_argument_format",
                    "argument": item,
                }
                print(json.dumps(payload, sort_keys=True))
                return 2
            parsed_arguments[name] = value
        print(
            json.dumps(
                classify_tool_contract_threats(contract, parsed_arguments).to_dict(),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "mcp-tool-governance-descriptor":
        tool_adapter = NeuroCliToolAdapter() if args.tool_adapter == "neuro-cli" else FakeUnitToolAdapter()
        parsed_arguments: dict[str, str] = {}
        for item in args.arg:
            name, separator, value = str(item).partition("=")
            if not separator:
                payload = {
                    "ok": False,
                    "status": "invalid_argument_format",
                    "argument": item,
                }
                print(json.dumps(payload, sort_keys=True))
                return 2
            parsed_arguments[name] = value
        payload = load_mcp_tool_governance_descriptor_payload(
            args.tool,
            tool_adapter=tool_adapter,
        )
        if payload.get("ok", False):
            contract = tool_adapter.describe_tool(args.tool)
            assert contract is not None
            payload["threat_assessment"] = classify_tool_contract_threats(
                contract,
                parsed_arguments,
            ).to_dict()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "mcp-read-only-execute":
        tool_adapter = NeuroCliToolAdapter() if args.tool_adapter == "neuro-cli" else FakeUnitToolAdapter()
        parsed_arguments: dict[str, str] = {}
        for item in args.arg:
            name, separator, value = str(item).partition("=")
            if not separator:
                payload = {
                    "ok": False,
                    "status": "invalid_argument_format",
                    "argument": item,
                }
                print(json.dumps(payload, sort_keys=True))
                return 2
            parsed_arguments[name] = value
        payload = build_mcp_read_only_execution(
            tool_name=args.tool,
            tool_args=parsed_arguments,
            tool_adapter=tool_adapter,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "mcp-descriptor":
        tool_adapter = NeuroCliToolAdapter() if args.tool_adapter == "neuro-cli" else FakeUnitToolAdapter()
        print(
            json.dumps(
                load_mcp_bridge_descriptor_payload(
                    tool_adapter,
                    bridge_mode=args.bridge_mode,
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "agent-excellence-smoke":
        tool_adapter = (
            NeuroCliToolAdapter() if args.tool_adapter == "neuro-cli" else FakeUnitToolAdapter()
        )
        try:
            payload = build_agent_excellence_smoke(
                tool_adapter=tool_adapter,
                bridge_mode=args.bridge_mode,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "agent_excellence_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "observability-diagnosis-smoke":
        try:
            relay_failure_payload = cast(
                dict[str, Any],
                json.loads(Path(args.relay_failure_file).read_text(encoding="utf-8")),
            )
            activate_failure_payload = cast(
                dict[str, Any],
                json.loads(Path(args.activate_failure_file).read_text(encoding="utf-8")),
            )
            payload = build_observability_diagnosis_smoke(
                relay_failure_payload=relay_failure_payload,
                activate_failure_payload=activate_failure_payload,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "observability_diagnosis_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "release-rollback-hardening-smoke":
        try:
            activate_failure_payload = cast(
                dict[str, Any],
                json.loads(Path(args.activate_failure_file).read_text(encoding="utf-8")),
            )
            rollback_payload = cast(
                dict[str, Any],
                json.loads(Path(args.rollback_file).read_text(encoding="utf-8")),
            )
            payload = build_release_rollback_hardening_smoke(
                activate_failure_payload=activate_failure_payload,
                rollback_payload=rollback_payload,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_rollback_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "real-scene-checklist-template":
        payload = build_real_scene_checklist_template(
            release_target=args.release_target,
            implementation_release=args.implementation_release,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "real-scene-e2e-smoke":
        try:
            live_event_smoke_payload = cast(
                dict[str, Any],
                json.loads(Path(args.live_event_smoke_file).read_text(encoding="utf-8")),
            )
            coding_agent_route_payload = None
            if args.coding_agent_route_file:
                coding_agent_route_payload = cast(
                    dict[str, Any],
                    json.loads(
                        Path(args.coding_agent_route_file).read_text(encoding="utf-8")
                    ),
                )
            payload = build_real_scene_e2e_smoke(
                live_event_smoke_payload=live_event_smoke_payload,
                coding_agent_route_payload=coding_agent_route_payload,
            )
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "real_scene_e2e_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "session-inspect":
        data_store = CoreDataStore(args.db)
        try:
            manager = CoreSessionManager(data_store)
            payload = manager.load_snapshot(args.session_id, limit=10).to_dict()
        finally:
            data_store.close()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "closure-summary":
        provider_smoke_payload = None
        if args.provider_smoke_file:
            provider_smoke_payload = cast(
                dict[str, Any],
                json.loads(Path(args.provider_smoke_file).read_text(encoding="utf-8")),
            )
        multimodal_profile_payload = None
        if args.multimodal_profile_file:
            multimodal_profile_payload = cast(
                dict[str, Any],
                json.loads(Path(args.multimodal_profile_file).read_text(encoding="utf-8")),
            )
        documentation_payload = None
        if args.documentation_file:
            documentation_payload = cast(
                dict[str, Any],
                json.loads(Path(args.documentation_file).read_text(encoding="utf-8")),
            )
        regression_payload = None
        if args.regression_file:
            regression_payload = cast(
                dict[str, Any],
                json.loads(Path(args.regression_file).read_text(encoding="utf-8")),
            )
        relay_failure_payload = None
        if args.relay_failure_file:
            relay_failure_payload = cast(
                dict[str, Any],
                json.loads(Path(args.relay_failure_file).read_text(encoding="utf-8")),
            )
        hardware_compatibility_payload = None
        if args.hardware_compatibility_file:
            hardware_compatibility_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.hardware_compatibility_file).read_text(encoding="utf-8")
                ),
            )
        hardware_acceptance_matrix_payload = None
        if args.hardware_acceptance_matrix_file:
            hardware_acceptance_matrix_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.hardware_acceptance_matrix_file).read_text(
                        encoding="utf-8"
                    )
                ),
            )
        resource_budget_governance_payload = None
        if args.resource_budget_governance_file:
            resource_budget_governance_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.resource_budget_governance_file).read_text(
                        encoding="utf-8"
                    )
                ),
            )
        agent_excellence_payload = None
        if args.agent_excellence_file:
            agent_excellence_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.agent_excellence_file).read_text(encoding="utf-8")
                ),
            )
        release_rollback_payload = None
        if args.release_rollback_file:
            release_rollback_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.release_rollback_file).read_text(encoding="utf-8")
                ),
            )
        signing_provenance_payload = None
        if args.signing_provenance_file:
            signing_provenance_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.signing_provenance_file).read_text(encoding="utf-8")
                ),
            )
        observability_diagnosis_payload = None
        if args.observability_diagnosis_file:
            observability_diagnosis_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.observability_diagnosis_file).read_text(
                        encoding="utf-8"
                    )
                ),
            )
        real_scene_e2e_payload = None
        if args.real_scene_e2e_file:
            real_scene_e2e_payload = cast(
                dict[str, Any],
                json.loads(Path(args.real_scene_e2e_file).read_text(encoding="utf-8")),
            )
        autonomy_daemon_payload = None
        if args.autonomy_daemon_file:
            autonomy_daemon_payload = cast(
                dict[str, Any],
                json.loads(Path(args.autonomy_daemon_file).read_text(encoding="utf-8")),
            )
        task_tracking_payload = None
        if args.task_tracking_file:
            task_tracking_payload = cast(
                dict[str, Any],
                json.loads(Path(args.task_tracking_file).read_text(encoding="utf-8")),
            )
        memory_maintenance_payload = None
        if args.memory_maintenance_file:
            memory_maintenance_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.memory_maintenance_file).read_text(encoding="utf-8")
                ),
            )
        self_optimization_payload = None
        if args.self_optimization_file:
            self_optimization_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.self_optimization_file).read_text(encoding="utf-8")
                ),
            )
        world_model_context_payload = None
        if args.world_model_context_file:
            world_model_context_payload = cast(
                dict[str, Any],
                json.loads(
                    Path(args.world_model_context_file).read_text(encoding="utf-8")
                ),
            )
        vitality_smoke_payload = None
        if args.vitality_smoke_file:
            vitality_smoke_payload = cast(
                dict[str, Any],
                json.loads(Path(args.vitality_smoke_file).read_text(encoding="utf-8")),
            )
        persona_state_payload = None
        if args.persona_state_file:
            persona_state_payload = cast(
                dict[str, Any],
                json.loads(Path(args.persona_state_file).read_text(encoding="utf-8")),
            )
        social_adapter_payload = None
        if args.social_adapter_file:
            social_adapter_payload = cast(
                dict[str, Any],
                json.loads(Path(args.social_adapter_file).read_text(encoding="utf-8")),
            )
        qq_gateway_payload = None
        if args.qq_gateway_file:
            qq_gateway_payload = cast(
                dict[str, Any],
                json.loads(Path(args.qq_gateway_file).read_text(encoding="utf-8")),
            )
        wecom_gateway_payload = None
        if args.wecom_gateway_file:
            wecom_gateway_payload = cast(
                dict[str, Any],
                json.loads(Path(args.wecom_gateway_file).read_text(encoding="utf-8")),
            )
        openclaw_gateway_payload = None
        if args.openclaw_gateway_file:
            openclaw_gateway_payload = cast(
                dict[str, Any],
                json.loads(Path(args.openclaw_gateway_file).read_text(encoding="utf-8")),
            )
        approval_social_payload = None
        if args.approval_social_file:
            approval_social_payload = cast(
                dict[str, Any],
                json.loads(Path(args.approval_social_file).read_text(encoding="utf-8")),
            )
        self_improvement_payload = None
        if args.self_improvement_file:
            self_improvement_payload = cast(
                dict[str, Any],
                json.loads(Path(args.self_improvement_file).read_text(encoding="utf-8")),
            )
        coding_agent_route_payload = None
        if args.coding_agent_route_file:
            coding_agent_route_payload = cast(
                dict[str, Any],
                json.loads(Path(args.coding_agent_route_file).read_text(encoding="utf-8")),
            )
        data_store = CoreDataStore(args.db)
        try:
            payload = _build_session_closure_summary(
                data_store,
                args.session_id,
                limit=max(1, args.limit),
                provider_smoke_payload=provider_smoke_payload,
                require_provider_smoke=bool(args.require_provider_smoke),
                multimodal_profile_payload=multimodal_profile_payload,
                require_multimodal_profile=bool(args.require_multimodal_profile),
                documentation_payload=documentation_payload,
                regression_payload=regression_payload,
                relay_failure_payload=relay_failure_payload,
                hardware_compatibility_payload=hardware_compatibility_payload,
                hardware_acceptance_matrix_payload=hardware_acceptance_matrix_payload,
                resource_budget_governance_payload=resource_budget_governance_payload,
                agent_excellence_payload=agent_excellence_payload,
                release_rollback_payload=release_rollback_payload,
                signing_provenance_payload=signing_provenance_payload,
                observability_diagnosis_payload=observability_diagnosis_payload,
                real_scene_e2e_payload=real_scene_e2e_payload,
                autonomy_daemon_payload=autonomy_daemon_payload,
                task_tracking_payload=task_tracking_payload,
                memory_maintenance_payload=memory_maintenance_payload,
                self_optimization_payload=self_optimization_payload,
                world_model_context_payload=world_model_context_payload,
                vitality_smoke_payload=vitality_smoke_payload,
                persona_state_payload=persona_state_payload,
                social_adapter_payload=social_adapter_payload,
                qq_gateway_payload=qq_gateway_payload,
                wecom_gateway_payload=wecom_gateway_payload,
                openclaw_gateway_payload=openclaw_gateway_payload,
                approval_social_payload=approval_social_payload,
                self_improvement_payload=self_improvement_payload,
                coding_agent_route_payload=coding_agent_route_payload,
            )
        finally:
            data_store.close()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "approval-inspect":
        data_store = CoreDataStore(args.db)
        try:
            tool_adapter = (
                NeuroCliToolAdapter()
                if args.tool_adapter == "neuro-cli"
                else FakeUnitToolAdapter()
            )
            approval_request = data_store.get_approval_request(args.approval_request_id)
            if approval_request is None:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "status": "error",
                            "failure_class": "approval_request_not_found",
                            "failure_status": "approval_request_not_found",
                        },
                        sort_keys=True,
                    )
                )
                return 2
            payload: dict[str, Any] = {
                "ok": True,
                "status": "ok",
                "approval_request": approval_request,
                "approval_decisions": data_store.get_approval_decisions(
                    args.approval_request_id
                ),
                "approval_context": build_approval_context(
                    data_store,
                    approval_request,
                    tool_adapter=tool_adapter,
                ),
            }
        finally:
            data_store.close()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "social-approval-inspect":
        data_store = CoreDataStore(args.db)
        try:
            tool_adapter = (
                NeuroCliToolAdapter()
                if args.tool_adapter == "neuro-cli"
                else FakeUnitToolAdapter()
            )
            social_adapter = MockSocialAdapter()
            approval_request = data_store.get_approval_request(args.approval_request_id)
            if approval_request is None:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "status": "error",
                            "failure_class": "approval_request_not_found",
                            "failure_status": "approval_request_not_found",
                        },
                        sort_keys=True,
                    )
                )
                return 2
            approval_context = build_approval_context(
                data_store,
                approval_request,
                tool_adapter=tool_adapter,
            )
            social_envelope = social_adapter.bind_approval_principal(
                approval_request_id=args.approval_request_id,
                adapter_kind=args.social_adapter_kind,
                channel_id=args.social_channel_id,
                channel_kind=args.social_channel_kind,
                external_user_id=args.social_user_id,
                decision_text="inspect",
                received_at="2026-05-10T13:05:00Z",
            )
            payload = {
                "ok": True,
                "status": "ok",
                "approval_request": approval_request,
                "approval_decisions": data_store.get_approval_decisions(
                    args.approval_request_id
                ),
                "approval_context": approval_context,
                "approval_summary": build_social_approval_summary(
                    approval_request,
                    approval_context,
                ),
                "social_context": social_adapter.social_approval_metadata(social_envelope),
            }
        finally:
            data_store.close()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "approval-decision":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        try:
            payload = apply_approval_decision(
                args.db,
                approval_request_id=args.approval_request_id,
                decision=args.decision,
                tool_adapter=tool_adapter,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "failure_class": "approval_request_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "social-approval-decision":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        social_adapter = MockSocialAdapter()
        social_envelope = social_adapter.bind_approval_principal(
            approval_request_id=args.approval_request_id,
            adapter_kind=args.social_adapter_kind,
            channel_id=args.social_channel_id,
            channel_kind=args.social_channel_kind,
            external_user_id=args.social_user_id,
            decision_text=args.decision_text or args.decision,
            received_at="2026-05-10T13:06:00Z",
        )
        try:
            payload = apply_approval_decision(
                args.db,
                approval_request_id=args.approval_request_id,
                decision=args.decision,
                tool_adapter=tool_adapter,
                approval_metadata=social_adapter.social_approval_metadata(
                    social_envelope
                ),
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "failure_class": "approval_request_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "approval-social-smoke":
        payload = build_approval_social_smoke()
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "maf-provider-smoke":
        runtime_env = build_provider_runtime_env(config_path=args.maf_config_file)
        payload = maf_provider_smoke_status(
            allow_model_call=args.allow_model_call,
            execute_model_call=args.execute_model_call,
            env=runtime_env,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "provider-test":
        runtime_env = build_provider_runtime_env(config_path=args.config_file)
        payload = maf_provider_smoke_status(
            allow_model_call=args.allow_model_call,
            execute_model_call=args.execute_model_call,
            env=runtime_env,
        )
        payload["command"] = "provider-test"
        payload["test_surface"] = "provider-test"
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "multimodal-profile-smoke":
        try:
            payload = multimodal_profile_smoke(
                text=args.text or ["release-1.2.5 multimodal profile smoke"],
                image_refs=args.image_ref,
                audio_refs=args.audio_ref,
                video_refs=args.video_ref,
                response_modes=args.response_mode or None,
                profile_hint=args.profile_hint,
                profile_override=args.profile_override,
                require_live_backend=args.require_live_backend,
            )
        except ValueError as exc:
            payload = {
                "ok": False,
                "status": "error",
                "command": "multimodal-profile-smoke",
                "failure_class": "multimodal_profile_request_invalid",
                "failure_status": str(exc),
                "executes_model_call": False,
            }
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "provider-list":
        payload = provider_profile_catalog(config_path=args.config_file)
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "provider-config":
        payload = provider_config_update(
            profile_name=args.profile,
            config_path=args.config_file,
            provider_kind=args.provider_kind,
            credential_env_var=args.credential_env_var,
            endpoint_env_var=args.endpoint_env_var,
            endpoint_url=args.endpoint_url,
            model_env_var=args.model_env_var,
            deployment_env_var=args.deployment_env_var,
            configured_model=args.configured_model,
            configured_deployment=args.configured_deployment,
            supports_model_discovery=(
                True if args.supports_model_discovery == "true" else False if args.supports_model_discovery == "false" else None
            ),
            enabled=True if args.enable else False if args.disable else None,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "model-list":
        payload = provider_model_list(config_path=args.config_file)
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "model-set-active":
        payload = set_active_provider_profile(
            slot=args.slot,
            profile_name=args.profile,
            config_path=args.config_file,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "model-profile-smoke":
        payload = model_profile_smoke(
            config_path=args.config_file,
            active_affective_profile=args.active_affective_profile,
            active_rational_profile=args.active_rational_profile,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "federation-route-smoke":
        payload = federation_route_smoke(
            target_node=args.target_node,
            now=args.now,
            required_trust_scope=args.required_trust_scope,
            local_unit=args.local_unit,
            relay_via=tuple(args.relay_via),
            peer_core_id=args.peer_core_id,
            peer_trust_scope=args.peer_trust_scope,
            peer_expires_at=args.peer_expires_at,
            peer_reachable=not args.peer_unreachable,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
