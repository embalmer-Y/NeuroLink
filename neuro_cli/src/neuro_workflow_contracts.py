from __future__ import annotations

from pathlib import Path
from typing import Any


def workflow_agent_metadata(
    workflow_name: str,
    metadata_defaults: dict[str, Any],
    plan_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metadata = dict(metadata_defaults)
    metadata.update(plan_metadata.get(workflow_name, {}))
    return metadata


def build_workflow_surface(
    workflow_plans: dict[str, dict[str, Any]],
    metadata_defaults: dict[str, Any],
    plan_metadata: dict[str, dict[str, Any]],
    schema_version: str,
) -> dict[str, Any]:
    plans = []
    for workflow_name in sorted(workflow_plans.keys()):
        workflow = workflow_plans[workflow_name]
        metadata = workflow_agent_metadata(
            workflow_name,
            metadata_defaults,
            plan_metadata,
        )
        plans.append(
            {
                "workflow": workflow_name,
                "category": workflow["category"],
                "description": workflow["description"],
                "host_support": metadata["host_support"],
                "requires_hardware": metadata["requires_hardware"],
                "requires_serial": metadata["requires_serial"],
                "requires_router": metadata["requires_router"],
                "requires_network": metadata["requires_network"],
                "destructive": metadata["destructive"],
                "plan_command": f"workflow plan {workflow_name}",
            }
        )

    return {
        "schema_version": schema_version,
        "plan_command": "workflow plan <name>",
        "system_plan_command": "system workflow plan <name>",
        "categories": sorted({plan["category"] for plan in plans}),
        "plans": plans,
    }


def build_workflow_plan_payload(
    *,
    workflow_name: str,
    workflow_plans: dict[str, dict[str, Any]],
    metadata_defaults: dict[str, Any],
    plan_metadata: dict[str, dict[str, Any]],
    schema_version: str,
    release_target: str,
    protocol_metadata: dict[str, Any],
    workspace_root: Path,
    agent_skill: dict[str, Any],
) -> dict[str, Any]:
    workflow = workflow_plans[workflow_name]
    metadata = workflow_agent_metadata(
        workflow_name,
        metadata_defaults,
        plan_metadata,
    )
    return {
        "ok": True,
        "workflow": workflow_name,
        "schema_version": schema_version,
        "category": workflow["category"],
        "description": workflow["description"],
        "release_target": release_target,
        "host_support": metadata["host_support"],
        "requires_hardware": metadata["requires_hardware"],
        "requires_serial": metadata["requires_serial"],
        "requires_router": metadata["requires_router"],
        "requires_network": metadata["requires_network"],
        "destructive": metadata["destructive"],
        "preconditions": metadata["preconditions"],
        "expected_success": metadata["expected_success"],
        "failure_statuses": metadata["failure_statuses"],
        "cleanup": metadata["cleanup"],
        "protocol": protocol_metadata,
        "executes_commands": False,
        "workspace_root": str(workspace_root),
        "agent_skill": agent_skill,
        "commands": workflow["commands"],
        "artifacts": workflow["artifacts"],
        "json_contract": workflow.get("json_contract", {}),
        "next_step": "run the listed command explicitly after reviewing it",
    }