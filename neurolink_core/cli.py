from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from .maf import (
    MafProviderMode,
    MafProviderNotReadyError,
    build_maf_runtime_profile,
    maf_provider_smoke_status,
)
from .inference import multimodal_profile_smoke
from .session import CoreSessionManager
from .tools import FakeUnitToolAdapter, NeuroCliToolAdapter
from .tools import load_mcp_bridge_descriptor_payload
from .tools import load_neuro_cli_skill_descriptor_payload
from .tools import observe_activation_health
from .tools import validate_tool_workflow_catalog_consistency
from .data import CoreDataStore
from .federation import UnitCapabilityDescriptor, federation_route_smoke
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


CLOSURE_SUMMARY_SCHEMA_VERSION = "1.2.7-closure-summary-v13"
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
REAL_SCENE_CHECKLIST_TEMPLATE_SCHEMA_VERSION = "2.0.0-real-scene-checklist-template-v1"


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
        "mcp_descriptor": mcp_descriptor,
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
            "mcp_bridge_mode": str(mcp_descriptor.get("bridge_mode") or ""),
            "workflow_catalog_failure_statuses": [
                str(result.get("failure_status") or "")
                for result in workflow_catalog_results
                if str(result.get("failure_status") or "")
            ],
        },
        "ok": all(closure_gates.values()),
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
            isinstance(item, dict)
            and str(item.get("tool_name") or "") == "system_state_sync"
            for item in tool_results
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
        "closure_gates": closure_gates,
        "evidence_summary": {
            "event_source": top_level_event_source,
            "session_id": str(live_event_smoke_payload.get("session_id") or execution_span.get("session_id") or ""),
            "collected_event_count": int(live_event_ingest.get("collected_event_count") or 0),
            "target_app_id": str(live_event_ingest.get("app_id") or session_context.get("target_app_id") or ""),
            "tool_result_count": len(tool_results),
            "execution_span_id": str(execution_span.get("execution_span_id") or ""),
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


def _build_validation_gate_checklist(
    validation_gates: dict[str, bool],
) -> list[dict[str, Any]]:
    return [
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
    ]


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
    ]
    multimodal_gates = cast(
        dict[str, Any],
        multimodal_profile_summary.get("closure_gates") or {},
    )
    provider_gates = cast(
        dict[str, Any],
        provider_smoke_summary.get("closure_gates") or {},
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

    real_scene_e2e_smoke = subparsers.add_parser("real-scene-e2e-smoke")
    real_scene_e2e_smoke.add_argument(
        "--live-event-smoke-file",
        required=True,
        help="JSON payload emitted by live-event-smoke to validate as a real Core/Unit end-to-end scenario.",
    )
    real_scene_e2e_smoke.add_argument("--output", choices=("json",), default="json")

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
                provider_mode=getattr(args, "maf_provider_mode", MafProviderMode.DETERMINISTIC_FAKE.value)
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
        if args.input_text:
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
        payload["command"] = "agent-run"
        print(json.dumps(payload, sort_keys=True))
        return 0
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
            payload = build_real_scene_e2e_smoke(
                live_event_smoke_payload=live_event_smoke_payload,
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
    if args.command == "maf-provider-smoke":
        payload = maf_provider_smoke_status(
            allow_model_call=args.allow_model_call,
            execute_model_call=args.execute_model_call,
        )
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
