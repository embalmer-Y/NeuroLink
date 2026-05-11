from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from .common import new_id
from .policy import ReadOnlyToolPolicy
from .policy import SideEffectLevel


TOOL_MANIFEST_SCHEMA_VERSION = "1.2.0-tool-manifest-v1"
SKILL_DESCRIPTOR_SCHEMA_VERSION = "1.2.5-skill-descriptor-v1"
SKILL_REGISTRY_SCHEMA_VERSION = "2.2.4-skill-registry-v1"
MCP_BRIDGE_DESCRIPTOR_SCHEMA_VERSION = "1.2.6-mcp-bridge-descriptor-v2"
MCP_TOOL_GOVERNANCE_DESCRIPTOR_SCHEMA_VERSION = "2.2.4-mcp-tool-governance-descriptor-v1"
CODING_AGENT_DESCRIPTOR_SCHEMA_VERSION = "2.2.4-coding-agent-descriptor-v1"
STATE_SYNC_SCHEMA_VERSION = "1.2.0-state-sync-v1"
ACTIVATION_HEALTH_SCHEMA_VERSION = "1.2.3-activation-health-v1"
APP_CONTROL_TOOL_ACTIONS = {
    "system_start_app": "start",
    "system_stop_app": "stop",
    "system_unload_app": "unload",
}
INTERNAL_CORE_ONLY_TOOLS: set[str] = {
    "system_state_sync",
    "system_activation_health_guard",
}
TOOL_WORKFLOW_COVERAGE: dict[str, tuple[str, ...]] = {
    "system_query_device": ("discover-device", "control-health"),
    "system_query_apps": ("discover-apps",),
    "system_query_leases": ("discover-leases", "control-cleanup"),
    "system_capabilities": ("discover-host",),
    "system_start_app": ("control-app-start",),
    "system_restart_app": ("control-app-restart",),
    "system_stop_app": ("llext-lifecycle",),
    "system_unload_app": ("llext-lifecycle",),
    "system_rollback_app": ("control-rollback",),
}


@dataclass(frozen=True)
class McpBridgeDescriptor:
    bridge_name: str
    bridge_mode: str
    server_id: str
    server_label: str
    transport: str
    read_only_tools: tuple[dict[str, Any], ...]
    approval_required_tools: tuple[dict[str, Any], ...]
    blocked_tools: tuple[dict[str, Any], ...]
    allowed_operations: tuple[str, ...]
    safety_boundaries: dict[str, Any]
    schema_version: str = MCP_BRIDGE_DESCRIPTOR_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": self.schema_version,
            "bridge_name": self.bridge_name,
            "bridge_mode": self.bridge_mode,
            "server_id": self.server_id,
            "server_label": self.server_label,
            "transport": self.transport,
            "read_only_tools": [dict(item) for item in self.read_only_tools],
            "approval_required_tools": [dict(item) for item in self.approval_required_tools],
            "blocked_tools": [dict(item) for item in self.blocked_tools],
            "allowed_operations": list(self.allowed_operations),
            "safety_boundaries": dict(self.safety_boundaries),
        }


@dataclass(frozen=True)
class SkillDescriptor:
    name: str
    description: str
    argument_hint: str
    skill_path: str
    workflow_plan_required: bool
    json_output_required: bool
    release_target_promotion_blocked: bool
    callback_audit_required: bool
    ground_rules: tuple[str, ...]
    first_check_commands: tuple[str, ...]
    references: tuple[dict[str, str], ...]
    schema_version: str = SKILL_DESCRIPTOR_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "argument_hint": self.argument_hint,
            "skill_path": self.skill_path,
            "workflow_plan_required": self.workflow_plan_required,
            "json_output_required": self.json_output_required,
            "release_target_promotion_blocked": self.release_target_promotion_blocked,
            "callback_audit_required": self.callback_audit_required,
            "ground_rules": list(self.ground_rules),
            "first_check_commands": list(self.first_check_commands),
            "references": [dict(item) for item in self.references],
        }


@dataclass(frozen=True)
class SkillRegistryEntry:
    skill_id: str
    source_kind: str
    canonical: bool
    descriptor: SkillDescriptor

    def to_dict(self) -> dict[str, Any]:
        payload = self.descriptor.to_dict()
        payload.update(
            {
                "skill_id": self.skill_id,
                "source_kind": self.source_kind,
                "canonical": self.canonical,
            }
        )
        return payload


@dataclass(frozen=True)
class SkillDescriptorRegistry:
    entries: tuple[SkillRegistryEntry, ...]
    schema_version: str = SKILL_REGISTRY_SCHEMA_VERSION

    def get_entry(self, skill_id: str) -> SkillRegistryEntry | None:
        for entry in self.entries:
            if entry.skill_id == skill_id:
                return entry
        return None

    def canonical_entries(self) -> tuple[SkillRegistryEntry, ...]:
        return tuple(entry for entry in self.entries if entry.canonical)

    def to_dict(self) -> dict[str, Any]:
        canonical_entries = self.canonical_entries()
        return {
            "ok": True,
            "status": "ok",
            "schema_version": self.schema_version,
            "entry_count": len(self.entries),
            "canonical_entry_count": len(canonical_entries),
            "skill_ids": [entry.skill_id for entry in self.entries],
            "canonical_skill_ids": [entry.skill_id for entry in canonical_entries],
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class CodingAgentRunnerDescriptor:
    runner_name: str
    display_name: str
    invocation_mode: str
    disabled_by_default: bool
    approval_required: bool
    sandbox_required: bool
    direct_execution_forbidden: bool
    can_apply_changes: bool
    release_target_promotion_blocked: bool
    masked_env_vars: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    safety_boundaries: dict[str, Any]
    schema_version: str = CODING_AGENT_DESCRIPTOR_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": self.schema_version,
            "runner_name": self.runner_name,
            "display_name": self.display_name,
            "invocation_mode": self.invocation_mode,
            "disabled_by_default": self.disabled_by_default,
            "approval_required": self.approval_required,
            "sandbox_required": self.sandbox_required,
            "direct_execution_forbidden": self.direct_execution_forbidden,
            "can_apply_changes": self.can_apply_changes,
            "release_target_promotion_blocked": self.release_target_promotion_blocked,
            "masked_env_vars": list(self.masked_env_vars),
            "prohibited_actions": list(self.prohibited_actions),
            "allowed_operations": list(self.allowed_operations),
            "evidence_requirements": list(self.evidence_requirements),
            "safety_boundaries": dict(self.safety_boundaries),
        }


def _default_skill_contract_path() -> Path:
    return Path(__file__).resolve().parent.parent / "neuro_cli" / "skill" / "SKILL.md"


def _default_skill_registry_paths() -> tuple[Path, ...]:
    project_root = Path(__file__).resolve().parent.parent
    return (
        project_root / "neuro_cli" / "skill" / "SKILL.md",
        project_root / ".github" / "skills" / "neuro-cli" / "SKILL.md",
    )


def _default_workflow_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "neuro_cli" / "src" / "neuro_workflow_catalog.py"


@lru_cache(maxsize=4)
def load_workflow_catalog_definition(
    workflow_catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_path = Path(workflow_catalog_path) if workflow_catalog_path else _default_workflow_catalog_path()
    src_dir = str(resolved_path.parent)
    inserted_path = False
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
        inserted_path = True
    spec = importlib.util.spec_from_file_location(
        f"neurolink_workflow_catalog_{abs(hash(str(resolved_path)))}",
        resolved_path,
    )
    if spec is None or spec.loader is None:
        raise ValueError("workflow_catalog_load_failed")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted_path and sys.path and sys.path[0] == src_dir:
            sys.path.pop(0)
    return {
        "catalog_path": str(resolved_path),
        "plans": dict(getattr(module, "WORKFLOW_PLANS", {})),
        "metadata_defaults": dict(getattr(module, "WORKFLOW_METADATA_DEFAULTS", {})),
        "metadata": dict(getattr(module, "WORKFLOW_PLAN_METADATA", {})),
    }


def _canonical_contract_command_suffix(contract: "ToolContract") -> str:
    argv = [str(item) for item in contract.argv_template]
    if not argv:
        return ""
    wrapper_index = next(
        (index for index, item in enumerate(argv) if "invoke_neuro_cli.py" in item),
        -1,
    )
    suffix = argv[wrapper_index + 1 :] if wrapper_index >= 0 else list(argv)
    normalized: list[str] = []
    skip_next = False
    for item in suffix:
        if skip_next:
            skip_next = False
            continue
        if item == "--output":
            skip_next = True
            continue
        normalized.append(item)
    return " ".join(normalized).strip()


def _workflow_command_mentions_lease(metadata: dict[str, Any]) -> bool:
    for key in ("preconditions", "cleanup"):
        for item in cast(list[Any], metadata.get(key) or []):
            if "lease" in str(item).lower():
                return True
    return False


def validate_tool_workflow_catalog_consistency(
    contract: "ToolContract",
    workflow_catalog_path: str | Path | None = None,
) -> dict[str, Any]:
    coverage_workflows: tuple[str, ...] = TOOL_WORKFLOW_COVERAGE.get(contract.tool_name, ())
    if contract.tool_name in INTERNAL_CORE_ONLY_TOOLS:
        return {
            "catalog_path": str(
                Path(workflow_catalog_path) if workflow_catalog_path else _default_workflow_catalog_path()
            ),
            "internal_core_only": True,
            "coverage_workflows": [],
            "workflow_entries_present": True,
            "command_coverage_present": True,
            "destructive_alignment": True,
            "lease_governance_alignment": True,
            "valid": True,
            "failure_status": "",
        }

    catalog = load_workflow_catalog_definition(workflow_catalog_path)
    plans = cast(dict[str, dict[str, Any]], catalog.get("plans") or {})
    metadata_defaults = cast(dict[str, Any], catalog.get("metadata_defaults") or {})
    metadata = cast(dict[str, dict[str, Any]], catalog.get("metadata") or {})
    canonical_command = _canonical_contract_command_suffix(contract)
    workflow_entries_present = bool(coverage_workflows) and all(
        name in plans and name in metadata for name in coverage_workflows
    )

    command_coverage: list[str] = []
    destructive_alignment = True
    lease_governance_alignment = True
    governed_tool = bool(contract.approval_required or contract.required_resources) or (
        contract.side_effect_level
        not in {SideEffectLevel.READ_ONLY, SideEffectLevel.OBSERVE_ONLY}
    )

    if workflow_entries_present:
        for workflow_name in coverage_workflows:
            workflow_entry = dict(plans.get(workflow_name) or {})
            workflow_metadata = {**metadata_defaults, **dict(metadata.get(workflow_name) or {})}
            commands = cast(list[Any], workflow_entry.get("commands") or [])
            if canonical_command and any(
                canonical_command in " ".join(shlex.split(str(command)))
                for command in commands
            ):
                command_coverage.append(workflow_name)
            destructive_alignment = destructive_alignment and (
                bool(workflow_metadata.get("destructive", False)) if governed_tool else not bool(workflow_metadata.get("destructive", False))
            )
            if contract.required_resources:
                lease_governance_alignment = lease_governance_alignment and _workflow_command_mentions_lease(
                    workflow_metadata
                )

    valid = (
        workflow_entries_present
        and (bool(command_coverage) or not canonical_command)
        and destructive_alignment
        and lease_governance_alignment
    )
    failure_status = ""
    if not workflow_entries_present:
        failure_status = "workflow_catalog_missing"
    elif canonical_command and not command_coverage:
        failure_status = "workflow_catalog_command_gap"
    elif not destructive_alignment or not lease_governance_alignment:
        failure_status = "workflow_catalog_contract_mismatch"
    return {
        "catalog_path": str(catalog.get("catalog_path") or ""),
        "internal_core_only": False,
        "coverage_workflows": list(coverage_workflows),
        "workflow_entries_present": workflow_entries_present,
        "command_coverage_present": bool(command_coverage) or not canonical_command,
        "command_coverage_workflows": command_coverage,
        "canonical_command": canonical_command,
        "destructive_alignment": destructive_alignment,
        "lease_governance_alignment": lease_governance_alignment,
        "valid": valid,
        "failure_status": failure_status,
    }


def _split_markdown_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content
    closing_index = content.find("\n---\n", 4)
    if closing_index == -1:
        return {}, content
    frontmatter_block = content[4:closing_index]
    body = content[closing_index + 5 :]
    payload: dict[str, str] = {}
    for line in frontmatter_block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        payload[key.strip()] = value.strip().strip('"')
    return payload, body


def _markdown_section(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(?P<section>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if match is None:
        return ""
    return match.group("section").strip()


def _extract_numbered_items(section: str) -> tuple[str, ...]:
    items: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^\d+\.\s+(.*)$", line.strip())
        if match:
            items.append(match.group(1).strip())
    return tuple(items)


def _extract_fenced_commands(section: str) -> tuple[str, ...]:
    commands = [
        match.group(1).strip()
        for match in re.finditer(r"```(?:bash)?\n(.*?)```", section, re.DOTALL)
    ]
    return tuple(command for command in commands if command)


def _extract_references(section: str) -> tuple[dict[str, str], ...]:
    references: list[dict[str, str]] = []
    for line in section.splitlines():
        match = re.match(r"^-\s+\[(?P<title>[^\]]+)\]\((?P<path>[^)]+)\)\s*$", line.strip())
        if match is None:
            continue
        references.append(
            {
                "title": match.group("title"),
                "path": match.group("path"),
            }
        )
    return tuple(references)


def load_neuro_cli_skill_descriptor(
    skill_path: str | Path | None = None,
) -> SkillDescriptor:
    resolved_path = Path(skill_path) if skill_path else _default_skill_contract_path()
    content = resolved_path.read_text(encoding="utf-8")
    frontmatter, body = _split_markdown_frontmatter(content)
    ground_rules_section = _markdown_section(body, "Ground Rules")
    first_checks_section = _markdown_section(body, "First Checks")
    references_section = _markdown_section(body, "References")
    ground_rules = _extract_numbered_items(ground_rules_section)
    first_check_commands = _extract_fenced_commands(first_checks_section)
    workflow_plan_required = any(
        "workflow plan" in item.lower() for item in ground_rules + first_check_commands
    )
    json_output_required = any(
        "json" in item.lower() and "output" in item.lower() for item in ground_rules
    )
    release_target_promotion_blocked = any(
        "release_target" in item.lower() and "do not promote" in item.lower()
        for item in ground_rules
    )
    callback_audit_required = any(
        "callback" in item.lower() and "audit" in item.lower() for item in ground_rules
    )
    return SkillDescriptor(
        name=str(frontmatter.get("name") or "unknown-skill"),
        description=str(frontmatter.get("description") or ""),
        argument_hint=str(frontmatter.get("argument-hint") or ""),
        skill_path=str(resolved_path),
        workflow_plan_required=workflow_plan_required,
        json_output_required=json_output_required,
        release_target_promotion_blocked=release_target_promotion_blocked,
        callback_audit_required=callback_audit_required,
        ground_rules=ground_rules,
        first_check_commands=first_check_commands,
        references=_extract_references(references_section),
    )


def load_neuro_cli_skill_descriptor_payload(
    skill_path: str | Path | None = None,
) -> dict[str, Any]:
    return load_neuro_cli_skill_descriptor(skill_path).to_dict()


def _skill_source_kind(skill_path: Path) -> str:
    normalized = skill_path.as_posix()
    if "/.github/skills/" in normalized:
        return "vscode_discovery_adapter"
    if "/neuro_cli/skill/" in normalized:
        return "canonical_package_skill"
    return "external_skill"


def _skill_registry_entry_id(skill_path: Path, descriptor: SkillDescriptor) -> str:
    source_kind = _skill_source_kind(skill_path)
    return f"{descriptor.name}:{source_kind}"


@lru_cache(maxsize=4)
def load_skill_descriptor_registry(
    skill_paths: tuple[str, ...] | None = None,
) -> SkillDescriptorRegistry:
    resolved_paths = (
        tuple(Path(path) for path in skill_paths)
        if skill_paths is not None
        else _default_skill_registry_paths()
    )
    entries: list[SkillRegistryEntry] = []
    for skill_path in resolved_paths:
        descriptor = load_neuro_cli_skill_descriptor(skill_path)
        source_kind = _skill_source_kind(skill_path)
        entries.append(
            SkillRegistryEntry(
                skill_id=_skill_registry_entry_id(skill_path, descriptor),
                source_kind=source_kind,
                canonical=source_kind == "canonical_package_skill",
                descriptor=descriptor,
            )
        )
    return SkillDescriptorRegistry(entries=tuple(entries))


def load_skill_descriptor_registry_payload(
    skill_paths: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return load_skill_descriptor_registry(skill_paths=skill_paths).to_dict()


def _summarize_mcp_tool(contract: "ToolContract") -> dict[str, Any]:
    return {
        "name": contract.tool_name,
        "description": contract.description,
        "side_effect_level": contract.side_effect_level.value,
        "required_arguments": list(contract.required_arguments),
        "required_resources": list(contract.required_resources),
        "approval_required": contract.approval_required,
        "retryable": contract.retryable,
    }


def load_mcp_bridge_descriptor(
    tool_adapter: Any | None = None,
    bridge_mode: str = "read_only_descriptor_only",
) -> McpBridgeDescriptor:
    adapter = tool_adapter or FakeUnitToolAdapter()
    tool_manifest = getattr(adapter, "tool_manifest", None)
    manifest = cast(tuple[ToolContract, ...], tool_manifest()) if callable(tool_manifest) else ()
    read_only_tools = tuple(
        _summarize_mcp_tool(contract)
        for contract in manifest
        if contract.side_effect_level in {SideEffectLevel.READ_ONLY, SideEffectLevel.OBSERVE_ONLY}
    )
    approval_required_tools = tuple(
        _summarize_mcp_tool(contract)
        for contract in manifest
        if contract.approval_required
    )
    blocked_tools: tuple[dict[str, Any], ...]
    allowed_operations: tuple[str, ...]
    safety_boundaries: dict[str, Any]
    bridge_name = "neurolink-core-mcp-readonly-bridge"
    server_id = "neurolink.core.readonly"
    server_label = "NeuroLink Core Read-Only MCP Bridge"
    transport = "in_process_descriptor_only"

    if bridge_mode == "read_only_descriptor_only":
        blocked_tools = tuple(
            _summarize_mcp_tool(contract)
            for contract in manifest
            if contract.approval_required or contract.side_effect_level not in {SideEffectLevel.READ_ONLY, SideEffectLevel.OBSERVE_ONLY}
        )
        allowed_operations = ("describe_server", "list_read_only_tools")
        safety_boundaries = {
            "descriptor_only": True,
            "tool_execution_via_mcp_forbidden": True,
            "side_effecting_tools_excluded": True,
            "approval_and_core_policy_required": True,
            "approval_required_tool_proposals_allowed": False,
            "external_mcp_connection_enabled": False,
        }
    elif bridge_mode == "core_governed_read_only_execution":
        blocked_tools = tuple(
            _summarize_mcp_tool(contract)
            for contract in manifest
            if contract.approval_required or contract.side_effect_level not in {SideEffectLevel.READ_ONLY, SideEffectLevel.OBSERVE_ONLY}
        )
        allowed_operations = (
            "describe_server",
            "list_read_only_tools",
            "execute_read_only_tool_via_core",
        )
        safety_boundaries = {
            "descriptor_only": False,
            "tool_execution_via_mcp_forbidden": False,
            "read_only_tool_execution_via_core_required": True,
            "side_effecting_tools_excluded": True,
            "approval_and_core_policy_required": True,
            "approval_required_tool_proposals_allowed": False,
            "external_mcp_connection_enabled": False,
        }
        bridge_name = "neurolink-core-mcp-governed-readonly-bridge"
        server_id = "neurolink.core.readonly.execute"
        server_label = "NeuroLink Core Governed Read-Only MCP Bridge"
        transport = "in_process_core_governed"
    elif bridge_mode == "core_governed_approval_required_proposal":
        blocked_tools = tuple()
        allowed_operations = (
            "describe_server",
            "list_read_only_tools",
            "execute_read_only_tool_via_core",
            "list_approval_required_tools",
            "submit_approval_required_tool_proposal",
        )
        safety_boundaries = {
            "descriptor_only": False,
            "tool_execution_via_mcp_forbidden": False,
            "read_only_tool_execution_via_core_required": True,
            "approval_required_tool_proposals_allowed": True,
            "approval_required_tools_execute_only_after_core_approval": True,
            "side_effecting_tools_execute_directly_forbidden": True,
            "approval_and_core_policy_required": True,
            "external_mcp_connection_enabled": False,
        }
        bridge_name = "neurolink-core-mcp-governed-proposal-bridge"
        server_id = "neurolink.core.approval.proposal"
        server_label = "NeuroLink Core Governed Approval Proposal MCP Bridge"
        transport = "in_process_core_governed"
    else:
        raise ValueError("unsupported_mcp_bridge_mode")

    return McpBridgeDescriptor(
        bridge_name=bridge_name,
        bridge_mode=bridge_mode,
        server_id=server_id,
        server_label=server_label,
        transport=transport,
        read_only_tools=read_only_tools,
        approval_required_tools=approval_required_tools,
        blocked_tools=blocked_tools,
        allowed_operations=allowed_operations,
        safety_boundaries=safety_boundaries,
    )


def load_mcp_bridge_descriptor_payload(
    tool_adapter: Any | None = None,
    bridge_mode: str = "read_only_descriptor_only",
) -> dict[str, Any]:
    return load_mcp_bridge_descriptor(tool_adapter, bridge_mode=bridge_mode).to_dict()


def load_mcp_tool_governance_descriptor_payload(
    tool_name: str,
    tool_adapter: Any | None = None,
) -> dict[str, Any]:
    adapter = tool_adapter or FakeUnitToolAdapter()
    contract = adapter.describe_tool(tool_name)
    if contract is None:
        return {
            "ok": False,
            "status": "tool_not_found",
            "reason": "mcp_tool_missing_from_manifest",
            "schema_version": MCP_TOOL_GOVERNANCE_DESCRIPTOR_SCHEMA_VERSION,
            "tool_name": tool_name,
        }

    policy_decision = ReadOnlyToolPolicy().evaluate_contract(contract).to_dict()
    bridge_mode = "read_only_descriptor_only"
    governance_path = "descriptor_only"
    if bool(policy_decision.get("allowed", False)):
        bridge_mode = "core_governed_read_only_execution"
        governance_path = "core_read_only_execute"
    elif contract.approval_required or contract.required_resources:
        bridge_mode = "core_governed_approval_required_proposal"
        governance_path = "core_approval_required_proposal"

    mcp_descriptor = load_mcp_bridge_descriptor_payload(
        adapter,
        bridge_mode=bridge_mode,
    )
    allowed_operations = cast(list[str], mcp_descriptor.get("allowed_operations") or [])
    execution_requirements = {
        "read_only_execution_allowed": bool(policy_decision.get("allowed", False))
        and "execute_read_only_tool_via_core" in allowed_operations,
        "approval_proposal_allowed": bool(contract.approval_required or contract.required_resources)
        and "submit_approval_required_tool_proposal" in allowed_operations,
        "operator_approval_required": bool(contract.approval_required),
        "required_resources_present": bool(contract.required_resources),
        "blocked_from_direct_mcp_execution": bool(
            cast(dict[str, Any], mcp_descriptor.get("safety_boundaries") or {}).get(
                "side_effecting_tools_execute_directly_forbidden",
                False,
            )
        ) or bool(contract.approval_required or contract.required_resources),
    }
    return {
        "ok": True,
        "status": "ok",
        "schema_version": MCP_TOOL_GOVERNANCE_DESCRIPTOR_SCHEMA_VERSION,
        "tool_name": tool_name,
        "governance_path": governance_path,
        "contract": contract.to_dict(),
        "policy_decision": policy_decision,
        "mcp_descriptor": mcp_descriptor,
        "execution_requirements": execution_requirements,
    }


def load_coding_agent_runner_descriptor(
    runner_name: str = "copilot",
) -> CodingAgentRunnerDescriptor:
    normalized_runner = runner_name.strip().lower() or "copilot"
    runner_catalog: dict[str, dict[str, str | tuple[str, ...]]] = {
        "copilot": {
            "display_name": "GitHub Copilot Coding Runner",
            "invocation_mode": "cli_json_plan_only",
            "masked_env_vars": ("GITHUB_COPILOT_CLI_PATH", "GITHUB_COPILOT_MODEL"),
        },
        "qwen-code": {
            "display_name": "Qwen Code Runner",
            "invocation_mode": "external_cli_plan_only",
            "masked_env_vars": ("QWEN_CODE_MODEL",),
        },
        "opencode": {
            "display_name": "OpenCode Runner",
            "invocation_mode": "external_cli_plan_only",
            "masked_env_vars": ("OPENCODE_MODEL",),
        },
        "local-command": {
            "display_name": "Local Command Coding Runner",
            "invocation_mode": "local_wrapper_plan_only",
            "masked_env_vars": (),
        },
    }
    runner_metadata: dict[str, str | tuple[str, ...]] | None = runner_catalog.get(normalized_runner)
    if runner_metadata is None:
        raise ValueError("unsupported_coding_agent_runner")
    display_name = cast(str, runner_metadata["display_name"])
    invocation_mode = cast(str, runner_metadata["invocation_mode"])
    masked_env_vars = cast(tuple[str, ...], runner_metadata["masked_env_vars"])

    prohibited_actions = (
        "direct_shell_execution",
        "direct_mcp_execution",
        "git_push",
        "firmware_flash",
        "credential_mutation",
        "production_deploy",
    )
    return CodingAgentRunnerDescriptor(
        runner_name=normalized_runner,
        display_name=display_name,
        invocation_mode=invocation_mode,
        disabled_by_default=True,
        approval_required=True,
        sandbox_required=True,
        direct_execution_forbidden=True,
        can_apply_changes=False,
        release_target_promotion_blocked=True,
        masked_env_vars=masked_env_vars,
        prohibited_actions=prohibited_actions,
        allowed_operations=(
            "describe_runner",
            "submit_plan_for_self_improvement_review",
            "sandbox_only_execution_after_operator_approval",
        ),
        evidence_requirements=(
            "approval_record",
            "sandbox_execution_record",
            "verified_test_evidence",
            "audit_callback_record",
        ),
        safety_boundaries={
            "disabled_by_default": True,
            "self_improvement_routing_required": True,
            "operator_approval_required": True,
            "sandbox_only_execution": True,
            "direct_shell_execution_forbidden": True,
            "direct_file_mutation_forbidden": True,
            "direct_mcp_execution_forbidden": True,
            "release_identity_promotion_forbidden": True,
            "autonomous_commit_push_forbidden": True,
        },
    )


def load_coding_agent_runner_descriptor_payload(
    runner_name: str = "copilot",
) -> dict[str, Any]:
    return load_coding_agent_runner_descriptor(runner_name=runner_name).to_dict()


@dataclass(frozen=True)
class ToolContract:
    tool_name: str
    description: str
    side_effect_level: SideEffectLevel
    argv_template: tuple[str, ...] = ()
    resource: str = ""
    required_arguments: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    timeout_seconds: int = 10
    retryable: bool = False
    approval_required: bool = False
    cleanup_hint: str | None = None
    output_contract: dict[str, Any] = field(
        default_factory=lambda: cast(dict[str, Any], {})
    )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolContract":
        return cls(
            tool_name=str(payload.get("name") or payload.get("tool_name") or ""),
            description=str(payload.get("description") or ""),
            side_effect_level=SideEffectLevel(str(payload.get("side_effect_level") or "read_only")),
            argv_template=tuple(str(item) for item in payload.get("argv_template") or ()),
            resource=str(payload.get("resource") or ""),
            required_arguments=tuple(str(item) for item in payload.get("required_arguments") or ()),
            required_resources=tuple(str(item) for item in payload.get("lease_requirements") or payload.get("required_resources") or ()),
            timeout_seconds=int(payload.get("timeout_seconds", 10)),
            retryable=bool(payload.get("retryable", False)),
            approval_required=bool(payload.get("approval_required", False)),
            cleanup_hint=(payload.get("cleanup_hints") or [payload.get("cleanup_hint") or None])[0],
            output_contract=dict(payload.get("output_contract") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.tool_name,
            "description": self.description,
            "argv_template": list(self.argv_template),
            "resource": self.resource,
            "required_arguments": list(self.required_arguments),
            "side_effect_level": self.side_effect_level.value,
            "lease_requirements": list(self.required_resources),
            "timeout_seconds": self.timeout_seconds,
            "retryable": self.retryable,
            "approval_required": self.approval_required,
            "cleanup_hints": [self.cleanup_hint] if self.cleanup_hint else [],
            "output_contract": dict(self.output_contract),
        }


@dataclass(frozen=True)
class StateSyncSurface:
    ok: bool
    status: str
    payload: dict[str, Any]
    attempt: int = 1
    max_attempts: int = 1
    retried: bool = False
    failure_status: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StateSyncSurface":
        return cls(
            ok=bool(payload.get("ok", False)),
            status=str(payload.get("status") or "unknown"),
            payload=dict(payload.get("payload") or {}),
            attempt=int(payload.get("attempt", 1)),
            max_attempts=int(payload.get("max_attempts", 1)),
            retried=bool(payload.get("retried", False)),
            failure_status=str(payload.get("failure_status") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "payload": dict(self.payload),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "retried": self.retried,
            "failure_status": self.failure_status,
        }


@dataclass(frozen=True)
class StateSyncSnapshot:
    status: str
    state: dict[str, StateSyncSurface]
    recommended_next_actions: tuple[str, ...]
    schema_version: str = STATE_SYNC_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StateSyncSnapshot":
        state_payload = dict(payload.get("state") or {})
        return cls(
            status=str(payload.get("status") or "unknown"),
            state={
                name: StateSyncSurface.from_dict(dict(surface_payload))
                for name, surface_payload in state_payload.items()
            },
            recommended_next_actions=tuple(
                str(item) for item in payload.get("recommended_next_actions") or ()
            ),
            schema_version=str(payload.get("schema_version") or STATE_SYNC_SCHEMA_VERSION),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.status == "ok",
            "status": self.status,
            "schema_version": self.schema_version,
            "state": {
                name: surface.to_dict() for name, surface in self.state.items()
            },
            "recommended_next_actions": list(self.recommended_next_actions),
        }


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_result_id: str
    tool_name: str
    status: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_result_id": self.tool_result_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class ActivationHealthObservation:
    app_id: str
    classification: str
    reason: str
    ready_for_rollback_consideration: bool
    device_status: str
    network_state: str
    app_status: str
    app_present: bool
    observed_app_state: str
    recommended_next_actions: tuple[str, ...]
    schema_version: str = ACTIVATION_HEALTH_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "app_id": self.app_id,
            "classification": self.classification,
            "reason": self.reason,
            "ready_for_rollback_consideration": self.ready_for_rollback_consideration,
            "device_status": self.device_status,
            "network_state": self.network_state,
            "app_status": self.app_status,
            "app_present": self.app_present,
            "observed_app_state": self.observed_app_state,
            "recommended_next_actions": list(self.recommended_next_actions),
        }


@dataclass(frozen=True)
class CommandExecutionResult:
    exit_code: int
    stdout: str
    stderr: str = ""


class FakeUnitToolAdapter:
    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "adapter_kind": "fake",
            "runtime_source": "fake_no_model",
            "wrapper_path": "neuro_cli/scripts/invoke_neuro_cli.py",
            "node": "unit-01",
            "source_core": "core-cli",
            "source_agent": "rational",
            "supports_real_process": False,
        }

    def tool_manifest(self) -> tuple[ToolContract, ...]:
        return (
            ToolContract(
                tool_name="system_query_device",
                description="Read current Unit device/network state through the query plane.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "query",
                    "device",
                    "--output",
                    "json",
                ),
                resource="device query plane",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_query_apps",
                description="Read current Unit application lifecycle state through the query plane.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "query",
                    "apps",
                    "--output",
                    "json",
                ),
                resource="app query plane",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_query_leases",
                description="Read current active leases before any side-effecting action.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "query",
                    "leases",
                    "--output",
                    "json",
                ),
                resource="lease query plane",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_state_sync",
                description="Aggregate device, apps, leases, protocol, and agent runtime metadata into one read-only sync snapshot.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "system",
                    "state-sync",
                    "--output",
                    "json",
                ),
                resource="state sync aggregate",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                cleanup_hint="review active leases before side-effecting commands",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "partial_failure",
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_activation_health_guard",
                description="Classify post-activation health from read-only state sync evidence before any recovery action.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "system",
                    "state-sync",
                    "--output",
                    "json",
                ),
                resource="post-activation health observation",
                required_arguments=("--node", "--app-id"),
                timeout_seconds=10,
                retryable=True,
                cleanup_hint="treat rollback as an operator decision after reviewing health evidence",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "classification_statuses": [
                        "healthy",
                        "degraded",
                        "no_reply",
                        "rollback_required",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_rollback_app",
                description="Rollback a staged app update after explicit operator approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "deploy",
                    "rollback",
                    "--output",
                    "json",
                ),
                resource="neuro/<node>/update/app/<app-id>/rollback",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("update_rollback_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm rollback evidence, lease ownership, and target app identity before resume",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_capabilities",
                description="Read stable Neuro CLI protocol, workflow, and agent runtime metadata.",
                side_effect_level=SideEffectLevel.OBSERVE_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "system",
                    "capabilities",
                    "--output",
                    "json",
                ),
                resource="capability map",
                timeout_seconds=5,
                retryable=False,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": ["parse_failed"],
                },
            ),
            ToolContract(
                tool_name="system_restart_app",
                description="Restart a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "control",
                    "app-restart",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before restart",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_start_app",
                description="Start a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "app",
                    "start",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before start",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_stop_app",
                description="Stop a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "app",
                    "stop",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before stop",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_unload_app",
                description="Unload a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "app",
                    "unload",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before unload",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
        )

    def tool_manifest_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
            "tools": [contract.to_dict() for contract in self.tool_manifest()],
        }

    def parse_tool_manifest_payload(
        self, payload: dict[str, Any]
    ) -> tuple[ToolContract, ...]:
        return tuple(
            ToolContract.from_dict(dict(item)) for item in payload.get("tools") or ()
        )

    def parse_state_sync_payload(self, payload: dict[str, Any]) -> StateSyncSnapshot:
        return StateSyncSnapshot.from_dict(payload)

    def describe_tool(self, tool_name: str) -> ToolContract | None:
        for contract in self.tool_manifest():
            if contract.tool_name == tool_name:
                return contract
        return None

    def build_state_sync_snapshot(self, args: dict[str, Any]) -> StateSyncSnapshot:
        event_ids = list(args.get("event_ids") or [])
        target_app_id = str(args.get("app_id") or args.get("app") or "")
        apps_payload: dict[str, Any] = {
            "status": "ok",
            "app_count": 0,
            "apps": [],
            "observed_event_ids": event_ids,
        }
        if target_app_id:
            apps_payload = {
                "status": "ok",
                "app_count": 1,
                "apps": [
                    {
                        "app_id": target_app_id,
                        "state": "running",
                        "status": "active",
                    }
                ],
                "observed_event_ids": event_ids,
            }
        device = StateSyncSurface(
            ok=True,
            status="ok",
            payload={
                "status": "ok",
                "network_state": "NETWORK_READY",
                "ipv4": "192.168.2.67",
            },
        )
        apps = StateSyncSurface(
            ok=True,
            status="ok",
            payload=apps_payload,
        )
        leases = StateSyncSurface(
            ok=True,
            status="ok",
            payload={
                "status": "ok",
                "leases": [],
            },
        )
        return StateSyncSnapshot(
            status="ok",
            state={"device": device, "apps": apps, "leases": leases},
            recommended_next_actions=(
                "state sync is clean; read-only delegated reasoning may continue",
            ),
        )

    def _fake_query_payload(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        event_ids = list(args.get("event_ids") or [])
        reply_payload: dict[str, Any]
        if tool_name == "system_query_device":
            reply_payload = {
                "status": "ok",
                "network_state": "NETWORK_READY",
                "ipv4": "192.168.2.67",
            }
        elif tool_name == "system_query_apps":
            reply_payload = {
                "status": "ok",
                "app_count": 0,
                "apps": [],
                "observed_event_ids": event_ids,
            }
        elif tool_name == "system_query_leases":
            reply_payload = {
                "status": "ok",
                "leases": [],
            }
        elif tool_name == "system_capabilities":
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "agent_runtime": "1.2.0-agent-runtime-v1",
                    "tool_manifest_command": "system tool-manifest --output json",
                    "state_sync_command": "system state-sync --output json",
                },
            }
        elif tool_name == "system_restart_app":
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "status": "ok",
                    "requested_action": "restart_app",
                    "requested_app": str(args.get("app") or "default-app"),
                },
            }
        elif tool_name in APP_CONTROL_TOOL_ACTIONS:
            action = APP_CONTROL_TOOL_ACTIONS[tool_name]
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "status": "ok",
                    "requested_action": action,
                    "requested_app": str(
                        args.get("app_id") or args.get("app") or "default-app"
                    ),
                },
            }
        elif tool_name == "system_rollback_app":
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "status": "ok",
                    "requested_action": "rollback_app",
                    "requested_app": str(
                        args.get("app_id") or args.get("app") or "default-app"
                    ),
                    "reason": str(args.get("reason") or ""),
                },
            }
        else:
            raise ValueError(f"unsupported fake tool: {tool_name}")
        return {
            "ok": True,
            "status": "ok",
            "payload": {"request_id": new_id("req")},
            "replies": [{"ok": True, "payload": reply_payload}],
        }

    def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
        contract = self.describe_tool(tool_name)
        if contract is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": "unknown_tool",
                    "failure_class": "manifest_lookup_failed",
                },
            )
        payload: dict[str, Any] = {
            "contract": contract.to_dict(),
            "mode": "fake_no_model",
            "side_effect_level": contract.side_effect_level.value,
            "event_ids": list(args.get("event_ids") or []),
        }
        if tool_name == "system_state_sync":
            payload["state_sync"] = self.build_state_sync_snapshot(args).to_dict()
        elif tool_name == "system_activation_health_guard":
            state_sync_result = self.execute("system_state_sync", args)
            payload["activation_health"] = _classify_activation_health_result(
                state_sync_result,
                app_id=str(args.get("app_id") or args.get("app") or ""),
            ).to_dict()
            if state_sync_result.status == "ok":
                payload["state_sync"] = dict(state_sync_result.payload.get("state_sync") or {})
            else:
                payload["state_sync_error"] = dict(state_sync_result.payload)
        else:
            payload["result"] = self._fake_query_payload(tool_name, args)
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=tool_name,
            status="ok",
            payload=payload,
        )


class NeuroCliToolAdapter:
    def __init__(
        self,
        *,
        node: str = "unit-01",
        source_core: str = "core-cli",
        source_agent: str = "rational",
        timeout_seconds: int = 10,
        python_executable: str | None = None,
        wrapper_path: str | Path | None = None,
        runner: Any | None = None,
    ) -> None:
        self.node = node
        self.source_core = source_core
        self.source_agent = source_agent
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable or sys.executable
        self.wrapper_path = Path(wrapper_path) if wrapper_path else self._default_wrapper_path()
        self.runner = runner or self._run_subprocess
        self._manifest_cache: tuple[ToolContract, ...] | None = None

    @staticmethod
    def _default_wrapper_path() -> Path:
        return Path(__file__).resolve().parent.parent / "neuro_cli" / "scripts" / "invoke_neuro_cli.py"

    def _base_command(self, output: str = "json") -> list[str]:
        return [
            self.python_executable,
            str(self.wrapper_path),
            "--output",
            output,
            "--node",
            self.node,
            "--source-core",
            self.source_core,
            "--source-agent",
            self.source_agent,
            "--timeout",
            str(self.timeout_seconds),
        ]

    @staticmethod
    def _run_subprocess(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandExecutionResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _parse_json_stdout(command_result: CommandExecutionResult) -> dict[str, Any]:
        try:
            payload: Any = json.loads(command_result.stdout)
        except json.JSONDecodeError as exc:
            if command_result.exit_code != 0:
                raise ValueError(f"command_exit_{command_result.exit_code}") from exc
            raise ValueError("parse_failed") from exc
        if not isinstance(payload, dict):
            raise ValueError("parse_failed")
        return cast(dict[str, Any], payload)

    @staticmethod
    def _parse_jsonl_stdout(command_result: CommandExecutionResult) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in command_result.stdout.splitlines():
            if not line.strip():
                continue
            payload: Any = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("parse_failed")
            rows.append(cast(dict[str, Any], payload))
        if command_result.exit_code != 0:
            raise ValueError(f"command_exit_{command_result.exit_code}")
        return rows

    def tool_manifest(self) -> tuple[ToolContract, ...]:
        if self._manifest_cache is not None:
            return self._manifest_cache

        argv = [*self._base_command(), "system", "tool-manifest"]
        command_result = self.runner(argv, self.timeout_seconds)
        payload = self._parse_json_stdout(command_result)
        if not payload.get("ok", False):
            raise ValueError(str(payload.get("status") or "tool_manifest_failed"))
        self._manifest_cache = tuple(
            ToolContract.from_dict(dict(item)) for item in payload.get("tools") or ()
        )
        return self._manifest_cache

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "adapter_kind": "neuro-cli",
            "runtime_source": "neuro_cli_wrapper",
            "wrapper_path": str(self.wrapper_path),
            "node": self.node,
            "source_core": self.source_core,
            "source_agent": self.source_agent,
            "supports_real_process": self.runner is self._run_subprocess,
            "timeout_seconds": self.timeout_seconds,
        }

    def tool_manifest_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
            "tools": [contract.to_dict() for contract in self.tool_manifest()],
        }

    def describe_tool(self, tool_name: str) -> ToolContract | None:
        for contract in self.tool_manifest():
            if contract.tool_name == tool_name:
                return contract
        return None

    @staticmethod
    def _contract_command_suffix(contract: ToolContract) -> list[str]:
        argv = list(contract.argv_template)
        if len(argv) >= 2:
            argv = argv[2:]
        suffix: list[str] = []
        skip_next = False
        for token in argv:
            if skip_next:
                skip_next = False
                continue
            if token == "--output":
                skip_next = True
                continue
            suffix.append(token)
        return suffix

    @staticmethod
    def _extract_apps_payload(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
        replies = cast(list[Any] | None, result_payload.get("replies"))
        if not isinstance(replies, list):
            return []
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            reply_dict = cast(dict[str, Any], reply)
            reply_payload = cast(dict[str, Any] | None, reply_dict.get("payload"))
            if not isinstance(reply_payload, dict):
                continue
            apps = cast(list[Any] | None, reply_payload.get("apps"))
            if not isinstance(apps, list):
                continue
            resolved_apps: list[dict[str, Any]] = []
            for app in apps:
                if isinstance(app, dict):
                    resolved_apps.append(cast(dict[str, Any], app))
            return resolved_apps
        return []

    @staticmethod
    def _extract_lease_rows(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
        replies = cast(list[Any] | None, result_payload.get("replies"))
        if not isinstance(replies, list):
            return []
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            reply_dict = cast(dict[str, Any], reply)
            reply_payload = cast(dict[str, Any] | None, reply_dict.get("payload"))
            if not isinstance(reply_payload, dict):
                continue
            leases = cast(list[Any] | None, reply_payload.get("leases"))
            if not isinstance(leases, list):
                continue
            rows: list[dict[str, Any]] = []
            for lease in leases:
                if isinstance(lease, dict):
                    rows.append(cast(dict[str, Any], lease))
            return rows
        return []

    def _build_contract_command_with_args(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> list[str]:
        argv = [*self._base_command(), *self._contract_command_suffix(contract)]
        for argument_name in contract.required_arguments:
            if argument_name == "--node":
                continue
            candidate_keys = [argument_name.lstrip("-").replace("-", "_")]
            if argument_name == "--app-id":
                candidate_keys.extend(["app", "app_id"])
            if argument_name == "--lease-id":
                candidate_keys.append("lease_id")
            if argument_name == "--start-args":
                candidate_keys.append("start_args")
            value = None
            for key in candidate_keys:
                candidate = args.get(key)
                if candidate not in (None, ""):
                    value = candidate
                    break
            if value not in (None, ""):
                argv.extend([argument_name, str(value)])
        optional_start_args = args.get("start_args")
        if optional_start_args not in (None, "") and "--start-args" not in argv:
            argv.extend(["--start-args", str(optional_start_args)])
        return argv

    def _execute_raw_contract_command(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> tuple[CommandExecutionResult, dict[str, Any] | None, str | None]:
        argv = self._build_contract_command_with_args(contract, args)
        command_result = self.runner(argv, contract.timeout_seconds)
        try:
            payload = self._parse_json_stdout(command_result)
        except ValueError as exc:
            return command_result, None, str(exc)
        return command_result, payload, None

    def _resolve_control_app_args(self, args: dict[str, Any]) -> dict[str, Any] | None:
        resolved_args = dict(args)
        app_id = str(args.get("app_id") or args.get("app") or "")
        if not app_id:
            apps_contract = self.describe_tool("system_query_apps")
            if apps_contract is not None:
                _command_result, apps_payload, apps_error = self._execute_raw_contract_command(
                    apps_contract,
                    {},
                )
                if apps_payload is not None and apps_error is None:
                    observed_apps = self._extract_apps_payload(apps_payload)
                    if len(observed_apps) == 1:
                        observed_app = observed_apps[0]
                        app_id = str(
                            observed_app.get("app_id")
                            or observed_app.get("name")
                            or observed_app.get("app")
                            or ""
                        )
        if not app_id:
            return None

        lease_id = str(args.get("lease_id") or "")
        if not lease_id:
            leases_contract = self.describe_tool("system_query_leases")
            if leases_contract is not None:
                _command_result, leases_payload, leases_error = self._execute_raw_contract_command(
                    leases_contract,
                    {},
                )
                if leases_payload is not None and leases_error is None:
                    target_resource = f"app/{app_id}/control"
                    for lease in self._extract_lease_rows(leases_payload):
                        resource = str(lease.get("resource") or "")
                        if resource != target_resource:
                            continue
                        lease_id = str(lease.get("lease_id") or "")
                        if lease_id:
                            break
        if not lease_id:
            return None

        resolved_args.setdefault("app_id", app_id)
        resolved_args.setdefault("app", app_id)
        resolved_args.setdefault("lease_id", lease_id)
        return resolved_args

    def _execute_single_app_control(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        resolved_args = self._resolve_control_app_args(args)
        if resolved_args is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": "control_args_unresolved",
                    "failure_class": "dynamic_argument_resolution_failed",
                    "contract": contract.to_dict(),
                    "requested_args": dict(args),
                },
            )

        command_result, payload, command_error = self._execute_raw_contract_command(
            contract,
            resolved_args,
        )
        if command_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": command_error,
                    "failure_class": "control_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stderr": command_result.stderr,
                },
            )
        assert payload is not None
        payload_status = str(payload.get("status") or "unknown")
        nested_failure_status = self._extract_nested_failure_status(payload)
        if not payload.get("ok", False) or nested_failure_status:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": nested_failure_status or payload_status,
                    "failure_class": "control_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "result": payload,
                },
            )
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=contract.tool_name,
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "resolved_args": resolved_args,
                "result": payload,
            },
        )

    def _execute_restart_app(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        resolved_args = self._resolve_control_app_args(args)
        if resolved_args is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": "restart_args_unresolved",
                    "failure_class": "dynamic_argument_resolution_failed",
                    "contract": contract.to_dict(),
                    "requested_args": dict(args),
                },
            )

        stop_contract = ToolContract(
            tool_name="system_restart_app.stop",
            description="stop app as first half of restart",
            side_effect_level=contract.side_effect_level,
            argv_template=(
                "python",
                "neuro_cli/scripts/invoke_neuro_cli.py",
                "app",
                "stop",
                "--output",
                "json",
            ),
            required_arguments=("--node", "--app-id", "--lease-id"),
            timeout_seconds=contract.timeout_seconds,
        )
        start_contract = ToolContract(
            tool_name="system_restart_app.start",
            description="start app as second half of restart",
            side_effect_level=contract.side_effect_level,
            argv_template=(
                "python",
                "neuro_cli/scripts/invoke_neuro_cli.py",
                "app",
                "start",
                "--output",
                "json",
            ),
            required_arguments=("--node", "--app-id", "--lease-id"),
            timeout_seconds=contract.timeout_seconds,
        )

        stop_command_result, stop_payload, stop_error = self._execute_raw_contract_command(
            stop_contract,
            resolved_args,
        )
        if stop_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": stop_error,
                    "failure_class": "restart_stop_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stderr": stop_command_result.stderr,
                },
            )
        assert stop_payload is not None
        stop_status = str(stop_payload.get("status") or "unknown")
        if not stop_payload.get("ok", False) or self._extract_nested_failure_status(stop_payload):
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": self._extract_nested_failure_status(stop_payload)
                    or stop_status,
                    "failure_class": "restart_stop_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stop_result": stop_payload,
                },
            )

        start_command_result, start_payload, start_error = self._execute_raw_contract_command(
            start_contract,
            resolved_args,
        )
        if start_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": start_error,
                    "failure_class": "restart_start_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stop_result": stop_payload,
                    "stderr": start_command_result.stderr,
                },
            )
        assert start_payload is not None
        start_status = str(start_payload.get("status") or "unknown")
        if not start_payload.get("ok", False) or self._extract_nested_failure_status(start_payload):
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": self._extract_nested_failure_status(start_payload)
                    or start_status,
                    "failure_class": "restart_start_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stop_result": stop_payload,
                    "start_result": start_payload,
                },
            )

        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name="system_restart_app",
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "resolved_args": resolved_args,
                "stop_result": stop_payload,
                "start_result": start_payload,
            },
        )

    def _resolve_rollback_args(
        self,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        resolved_args = dict(args)
        app_id = str(args.get("app_id") or args.get("app") or "")
        if not app_id:
            apps_contract = self.describe_tool("system_query_apps")
            if apps_contract is not None:
                _command_result, apps_payload, apps_error = self._execute_raw_contract_command(
                    apps_contract,
                    {},
                )
                if apps_payload is not None and apps_error is None:
                    observed_apps = self._extract_apps_payload(apps_payload)
                    if len(observed_apps) == 1:
                        observed_app = observed_apps[0]
                        app_id = str(
                            observed_app.get("app_id")
                            or observed_app.get("name")
                            or observed_app.get("app")
                            or ""
                        )
        if not app_id:
            return None, "rollback_args_unresolved"

        lease_id = str(args.get("lease_id") or "")
        if not lease_id:
            leases_contract = self.describe_tool("system_query_leases")
            if leases_contract is not None:
                _command_result, leases_payload, leases_error = self._execute_raw_contract_command(
                    leases_contract,
                    {},
                )
                if leases_payload is not None and leases_error is None:
                    target_resource = f"update/app/{app_id}/rollback"
                    for lease in self._extract_lease_rows(leases_payload):
                        resource = str(lease.get("resource") or "")
                        if resource != target_resource:
                            continue
                        lease_id = str(lease.get("lease_id") or "")
                        if lease_id:
                            break
        if not lease_id:
            return None, "lease_not_found"

        resolved_args.setdefault("app_id", app_id)
        resolved_args.setdefault("app", app_id)
        resolved_args.setdefault("lease_id", lease_id)
        return resolved_args, ""

    def _execute_rollback_app(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        resolved_args, resolution_failure = self._resolve_rollback_args(args)
        if resolved_args is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": resolution_failure,
                    "failure_class": (
                        "rollback_lease_resolution_failed"
                        if resolution_failure == "lease_not_found"
                        else "dynamic_argument_resolution_failed"
                    ),
                    "contract": contract.to_dict(),
                    "requested_args": dict(args),
                },
            )

        command_result, payload, command_error = self._execute_raw_contract_command(
            contract,
            resolved_args,
        )
        if command_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": command_error,
                    "failure_class": "rollback_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stderr": command_result.stderr,
                },
            )
        assert payload is not None
        payload_status = str(payload.get("status") or "unknown")
        nested_failure_status = self._extract_nested_failure_status(payload)
        if not payload.get("ok", False) or nested_failure_status:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": nested_failure_status or payload_status,
                    "failure_class": "rollback_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "result": payload,
                },
            )
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=contract.tool_name,
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "resolved_args": resolved_args,
                "result": payload,
            },
        )

    def _execute_activation_health_guard(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        state_sync_result = self.execute("system_state_sync", args)
        observation = _classify_activation_health_result(
            state_sync_result,
            app_id=str(args.get("app_id") or args.get("app") or ""),
        )
        payload: dict[str, Any] = {
            "contract": contract.to_dict(),
            "activation_health": observation.to_dict(),
        }
        if state_sync_result.status == "ok":
            payload["state_sync"] = dict(state_sync_result.payload.get("state_sync") or {})
        else:
            payload["state_sync_error"] = dict(state_sync_result.payload)
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=contract.tool_name,
            status="ok",
            payload=payload,
        )

    @staticmethod
    def _extract_nested_failure_status(payload: dict[str, Any]) -> str:
        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            nested_payload_dict = cast(dict[str, Any], nested_payload)
            nested_status = str(nested_payload_dict.get("status") or "")
            if nested_status and nested_status != "ok":
                return nested_status
        replies = payload.get("replies")
        if isinstance(replies, list):
            for reply in cast(list[Any], replies):
                if not isinstance(reply, dict):
                    continue
                reply_dict = cast(dict[str, Any], reply)
                reply_payload = reply_dict.get("payload")
                if isinstance(reply_payload, dict):
                    reply_payload_dict = cast(dict[str, Any], reply_payload)
                    reply_status = str(reply_payload_dict.get("status") or "")
                    if reply_status and reply_status != "ok":
                        return reply_status
        return ""

    def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
        contract = self.describe_tool(tool_name)
        if contract is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": "unknown_tool",
                    "failure_class": "manifest_lookup_failed",
                },
            )

        if tool_name == "system_activation_health_guard":
            return self._execute_activation_health_guard(contract, args)
        if tool_name == "system_rollback_app":
            return self._execute_rollback_app(contract, args)
        if tool_name == "system_restart_app":
            return self._execute_restart_app(contract, args)
        if tool_name in APP_CONTROL_TOOL_ACTIONS:
            return self._execute_single_app_control(contract, args)

        argv = [*self._base_command(), *self._contract_command_suffix(contract)]
        command_result = self.runner(argv, contract.timeout_seconds)
        try:
            payload = self._parse_json_stdout(command_result)
        except ValueError as exc:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": str(exc),
                    "failure_class": "cli_execution_failed",
                    "stderr": command_result.stderr,
                },
            )

        status = str(payload.get("status") or "unknown")
        if not payload.get("ok", False):
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": status,
                    "failure_class": "top_level_status_failure",
                    "payload": payload,
                },
            )

        nested_failure_status = self._extract_nested_failure_status(payload)
        if nested_failure_status:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": nested_failure_status,
                    "failure_class": "nested_payload_status_failure",
                    "payload": payload,
                },
            )

        result_payload: dict[str, Any] = {"contract": contract.to_dict()}
        if tool_name == "system_state_sync":
            result_payload["state_sync"] = StateSyncSnapshot.from_dict(payload).to_dict()
        else:
            result_payload["result"] = payload
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=tool_name,
            status="ok",
            payload=result_payload,
        )

    def collect_agent_events(self, max_events: int = 0) -> list[dict[str, Any]]:
        argv = [
            *self._base_command(output="jsonl"),
            "monitor",
            "agent-events",
            "--max-events",
            str(max(0, int(max_events))),
        ]
        command_result = self.runner(argv, self.timeout_seconds)
        return self._parse_jsonl_stdout(command_result)

    @staticmethod
    def _source_node_from_keyexpr(keyexpr: str) -> str:
        parts = [segment for segment in str(keyexpr).split("/") if segment]
        if len(parts) >= 2 and parts[0] == "neuro":
            return parts[1]
        return ""

    @staticmethod
    def _source_app_from_keyexpr(keyexpr: str) -> str:
        parts = [segment for segment in str(keyexpr).split("/") if segment]
        if len(parts) >= 5 and parts[0] == "neuro" and parts[2] == "event" and parts[3] == "app":
            return parts[4]
        return ""

    @staticmethod
    def _event_id_token(value: Any) -> str:
        token = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "")).strip("-").lower()
        return token or "unknown"

    @staticmethod
    def _payload_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    @classmethod
    def _semantic_topic_for_live_payload(
        cls,
        *,
        payload: dict[str, Any],
        message_kind: str,
        keyexpr: str,
        current_semantic_topic: str,
    ) -> str:
        if current_semantic_topic:
            return current_semantic_topic

        if message_kind == "callback_event":
            return "unit.callback"
        if message_kind == "lease_event":
            return "lease_event"

        if message_kind == "update_event":
            stage = cls._payload_text(payload, "stage").lower()
            status = cls._payload_text(payload, "status", "update_state", "runtime_state").lower()
            if stage == "activate" and status not in ("", "ok", "active", "running"):
                return "unit.lifecycle.activate_failed"
            if stage:
                return f"unit.lifecycle.{stage}"

        if message_kind == "state_event":
            health = cls._payload_text(payload, "health").lower()
            network_state = cls._payload_text(payload, "network_state").lower()
            state = cls._payload_text(payload, "state", "runtime_state", "status").lower()
            expected_endpoint = cls._payload_text(payload, "expected_endpoint", "configured_endpoint")
            observed_endpoint = cls._payload_text(payload, "observed_endpoint", "actual_endpoint", "current_endpoint")
            drift_flag = cls._payload_text(payload, "endpoint_drift").lower()

            if (
                drift_flag in ("1", "true", "yes")
                or (expected_endpoint and observed_endpoint and expected_endpoint != observed_endpoint)
            ):
                return "unit.network.endpoint_drift"
            if health == "degraded" or state == "degraded":
                return "unit.health.degraded"
            if state == "offline" or network_state in ("offline", "disconnected", "no_reply"):
                return "unit.state.offline"
            if state == "online" or network_state == "network_ready":
                return "unit.state.online"

        if keyexpr.endswith("/health"):
            return "unit.health.unknown"
        if keyexpr.endswith("/state"):
            return "unit.state.unknown"
        return ""

    @classmethod
    def _normalize_live_event_row(
        cls,
        raw_event: dict[str, Any],
        *,
        default_source_kind: str,
        default_app_id: str = "",
    ) -> dict[str, Any]:
        normalized = dict(raw_event)
        if normalized.get("semantic_topic") and normalized.get("event_id"):
            return normalized

        event_payload = normalized.get("payload")
        if not isinstance(event_payload, dict):
            return normalized

        payload = dict(event_payload)
        keyexpr = str(normalized.get("keyexpr") or "")
        message_kind = str(payload.get("message_kind") or "")
        event_name = str(payload.get("event_name") or "")
        source_node = str(
            normalized.get("source_node")
            or payload.get("source_node")
            or cls._source_node_from_keyexpr(keyexpr)
        )
        source_app = str(
            normalized.get("source_app")
            or payload.get("source_app")
            or payload.get("app_id")
            or default_app_id
            or cls._source_app_from_keyexpr(keyexpr)
        )
        source_kind = str(
            normalized.get("source_kind")
            or payload.get("source_kind")
            or ("unit_app" if source_app else default_source_kind)
        )

        semantic_topic = cls._semantic_topic_for_live_payload(
            payload=payload,
            message_kind=message_kind,
            keyexpr=keyexpr,
            current_semantic_topic=str(
                normalized.get("semantic_topic") or payload.get("semantic_topic") or ""
            ),
        )

        event_type = str(normalized.get("event_type") or payload.get("event_type") or "")
        if not event_type:
            if message_kind == "callback_event":
                event_type = "callback"
            elif event_name:
                event_type = event_name
            elif semantic_topic:
                event_type = semantic_topic
            elif message_kind:
                event_type = message_kind
            else:
                event_type = "unknown"

        timestamp_wall = str(normalized.get("timestamp_wall") or payload.get("timestamp_wall") or "")
        if timestamp_wall:
            normalized["timestamp_wall"] = timestamp_wall

        if not normalized.get("event_id"):
            identity_seed = (
                payload.get("event_id")
                or timestamp_wall
                or payload.get("timestamp_ms")
                or payload.get("state_version")
                or payload.get("sequence")
                or payload.get("invoke_count")
                or payload.get("status")
                or payload.get("health")
                or payload.get("state")
                or payload.get("network_state")
                or "0"
            )
            normalized["event_id"] = (
                f"liveevt-{cls._event_id_token(source_node or 'node')}-"
                f"{cls._event_id_token(source_app or source_kind)}-"
                f"{cls._event_id_token(event_type)}-"
                f"{cls._event_id_token(identity_seed)}"
            )

        normalized["source_kind"] = source_kind
        normalized["source_node"] = source_node
        if source_app:
            normalized["source_app"] = source_app
        normalized["event_type"] = event_type
        normalized["semantic_topic"] = semantic_topic or event_type
        normalized["priority"] = int(
            normalized.get("priority")
            or payload.get("priority")
            or (80 if event_type == "callback" else 50)
        )
        normalized["payload"] = payload
        normalized.setdefault("dedupe_key", normalized["event_id"])
        return normalized

    @classmethod
    def _normalize_app_event_row(
        cls,
        raw_event: dict[str, Any],
        *,
        default_app_id: str,
    ) -> dict[str, Any]:
        raw_payload = raw_event.get("payload")
        payload_event_id = ""
        if isinstance(raw_payload, dict):
            payload_event_id = str(raw_payload.get("event_id") or "")
        normalized = cls._normalize_live_event_row(
            raw_event,
            default_source_kind="unit_app",
            default_app_id=default_app_id,
        )
        payload = normalized.get("payload")
        if isinstance(payload, dict) and str(normalized.get("event_type") or "") == "callback":
            invoke_count = payload.get("invoke_count")
            start_count = payload.get("start_count")
            if not payload_event_id:
                normalized["event_id"] = str(
                    payload.get("event_id")
                    or f"appevt-{normalized.get('source_app')}-{normalized.get('event_type')}-{invoke_count}-{start_count}"
                )
                normalized["dedupe_key"] = normalized["event_id"]
        return normalized

    def collect_live_events(
        self,
        *,
        duration: int = 5,
        max_events: int = 1,
        ready_file: str = "",
    ) -> dict[str, Any]:
        if int(duration) <= 0 and int(max_events) <= 0:
            raise ValueError("live_event_collection_requires_duration_or_max_events")

        argv = [
            *self._base_command(output="json"),
            "monitor",
            "events",
            "--duration",
            str(max(0, int(duration))),
            "--max-events",
            str(max(0, int(max_events))),
        ]
        if ready_file:
            argv.extend(["--ready-file", ready_file])

        command_timeout = max(
            self.timeout_seconds,
            int(duration) + self.timeout_seconds if int(duration) > 0 else self.timeout_seconds,
        )
        command_result = self.runner(argv, command_timeout)
        payload = self._parse_json_stdout(command_result)
        if not payload.get("ok", False):
            raise ValueError(str(payload.get("status") or "live_event_monitor_failed"))

        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            raise ValueError("live_event_monitor_missing_events")

        return {
            **payload,
            "events": [
                self._normalize_live_event_row(
                    dict(item),
                    default_source_kind="unit",
                )
                for item in raw_events
                if isinstance(item, dict)
            ],
        }

    def collect_app_events(
        self,
        app_id: str,
        *,
        duration: int = 5,
        max_events: int = 1,
        ready_file: str = "",
    ) -> dict[str, Any]:
        if int(duration) <= 0 and int(max_events) <= 0:
            raise ValueError("app_event_collection_requires_duration_or_max_events")

        argv = [
            *self._base_command(output="json"),
            "monitor",
            "app-events",
            "--app-id",
            app_id,
            "--duration",
            str(max(0, int(duration))),
            "--max-events",
            str(max(0, int(max_events))),
        ]
        if ready_file:
            argv.extend(["--ready-file", ready_file])

        command_timeout = max(
            self.timeout_seconds,
            int(duration) + self.timeout_seconds if int(duration) > 0 else self.timeout_seconds,
        )
        command_result = self.runner(argv, command_timeout)
        payload = self._parse_json_stdout(command_result)
        if not payload.get("ok", False):
            raise ValueError(str(payload.get("status") or "app_event_monitor_failed"))

        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            raise ValueError("app_event_monitor_missing_events")

        return {
            **payload,
            "events": [
                self._normalize_app_event_row(dict(item), default_app_id=app_id)
                for item in raw_events
                if isinstance(item, dict)
            ],
        }


def observe_activation_health(
    tool_adapter: Any,
    *,
    app_id: str,
    event_ids: list[str] | None = None,
) -> ActivationHealthObservation:
    state_sync_result = tool_adapter.execute(
        "system_state_sync",
        {
            "app_id": app_id,
            "app": app_id,
            "event_ids": list(event_ids or []),
        },
    )
    return _classify_activation_health_result(state_sync_result, app_id=app_id)


def _classify_activation_health_result(
    state_sync_result: ToolExecutionResult,
    *,
    app_id: str,
) -> ActivationHealthObservation:
    if state_sync_result.status != "ok":
        failure_status = str(state_sync_result.payload.get("failure_status") or "state_sync_failed")
        return ActivationHealthObservation(
            app_id=app_id,
            classification="no_reply",
            reason=failure_status,
            ready_for_rollback_consideration=False,
            device_status=failure_status,
            network_state="unknown",
            app_status="unknown",
            app_present=False,
            observed_app_state="unknown",
            recommended_next_actions=(
                "rerun state sync and verify Unit/router reachability before recovery",
            ),
        )

    snapshot = StateSyncSnapshot.from_dict(
        cast(dict[str, Any], state_sync_result.payload.get("state_sync") or {})
    )
    device_surface = snapshot.state.get(
        "device",
        StateSyncSurface(ok=False, status="unknown", payload={"status": "unknown"}),
    )
    apps_surface = snapshot.state.get(
        "apps",
        StateSyncSurface(ok=False, status="unknown", payload={"status": "unknown", "apps": []}),
    )
    device_payload = device_surface.payload
    apps_payload = apps_surface.payload
    network_state = str(device_payload.get("network_state") or "unknown")
    observed_apps = cast(list[Any], apps_payload.get("apps") or [])
    matched_app = None
    for app in observed_apps:
        if not isinstance(app, dict):
            continue
        app_payload = cast(dict[str, Any], app)
        if str(app_payload.get("app_id") or app_payload.get("name") or "") == app_id:
            matched_app = app_payload
            break
    observed_app_state = "unknown"
    app_status = str(apps_payload.get("status") or apps_surface.status or "unknown")
    app_present = matched_app is not None
    if matched_app is not None:
        observed_app_state = str(
            matched_app.get("state") or matched_app.get("status") or "unknown"
        )

    if not device_surface.ok or device_surface.status not in ("ok", "ready"):
        classification = "no_reply"
        reason = str(device_surface.status or "device_unreachable")
        ready_for_rollback_consideration = False
        recommended_next_actions = (
            "rerun query device and verify Unit/router reachability before rollback",
        )
    elif network_state != "NETWORK_READY":
        classification = "degraded"
        reason = "network_not_ready_after_activate"
        ready_for_rollback_consideration = False
        recommended_next_actions = (
            "inspect network readiness and event stream before protected rollback",
        )
    elif not app_present:
        classification = "rollback_required"
        reason = "target_app_missing_after_activate"
        ready_for_rollback_consideration = True
        recommended_next_actions = (
            "confirm activation evidence and prepare protected rollback review",
        )
    elif observed_app_state.lower() in {"running", "active", "started"}:
        classification = "healthy"
        reason = "target_app_running_after_activate"
        ready_for_rollback_consideration = False
        recommended_next_actions = (
            "activation health is good; continue observation and preserve evidence",
        )
    else:
        classification = "degraded"
        reason = "target_app_not_running_after_activate"
        ready_for_rollback_consideration = True
        recommended_next_actions = (
            "inspect app lifecycle state and decide whether protected rollback is required",
        )

    return ActivationHealthObservation(
        app_id=app_id,
        classification=classification,
        reason=reason,
        ready_for_rollback_consideration=ready_for_rollback_consideration,
        device_status=str(device_surface.status or device_payload.get("status") or "unknown"),
        network_state=network_state,
        app_status=app_status,
        app_present=app_present,
        observed_app_state=observed_app_state,
        recommended_next_actions=recommended_next_actions,
    )
