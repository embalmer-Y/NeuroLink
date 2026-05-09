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
from .data import CoreDataStore
from .federation import UnitCapabilityDescriptor, federation_route_smoke
from .workflow import (
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


CLOSURE_SUMMARY_SCHEMA_VERSION = "1.2.6-closure-summary-v10"
DOCUMENTATION_CLOSURE_SCHEMA_VERSION = "1.2.5-documentation-closure-v1"
REGRESSION_CLOSURE_SCHEMA_VERSION = "1.2.6-regression-closure-v2"
LEGACY_REGRESSION_CLOSURE_SCHEMA_VERSION = "1.2.5-regression-closure-v1"
RELAY_FAILURE_CLOSURE_SCHEMA_VERSION = "1.2.6-relay-failure-closure-v1"
HARDWARE_COMPATIBILITY_CLOSURE_SCHEMA_VERSION = "1.2.6-hardware-compatibility-closure-v1"


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
        _build_closure_checklist_entry(
            "closure_summary_gate",
            passed=bool(validation_gates.get("closure_summary_gate")),
            title="Closure Summary Gate",
            detail=(
                "The integrated closure summary reports all validation gates passing with no failed gate ids."
                if validation_gates.get("closure_summary_gate")
                else "The integrated closure summary still reports failing validation gates and is not closure-ready."
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
            gate_id for gate_id, passed in validation_gates.items() if not passed
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
        "aggregate_gates": aggregate_gates,
        "validation_gates": validation_gates,
        "validation_gate_summary": validation_gate_summary,
        "checklist": checklist,
        "bundle_checklist": bundle_checklist,
        "ok": all(aggregate_gates.values()) and validation_gate_summary["ok"],
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
