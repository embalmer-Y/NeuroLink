from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any, Iterable


class SideEffectLevel(StrEnum):
    OBSERVE_ONLY = "observe_only"
    READ_ONLY = "read_only"
    SUGGEST_ONLY = "suggest_only"
    LOW_RISK_EXECUTE = "low_risk_execute"
    APPROVAL_REQUIRED = "approval_required"
    DESTRUCTIVE = "destructive"


class ThreatSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ThreatCategory(StrEnum):
    STATE_MUTATION = "state_mutation"
    APPROVAL_GATE = "approval_gate"
    LEASE_SCOPE = "lease_scope"
    NETWORK_TARGET = "network_target"
    CREDENTIAL_REFERENCE = "credential_reference"
    SHELL_METACHAR = "shell_metachar"


@dataclass(frozen=True)
class ThreatFinding:
    category: ThreatCategory
    severity: ThreatSeverity
    reason: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ToolThreatAssessment:
    tool_name: str
    side_effect_level: SideEffectLevel
    approval_required: bool
    overall_severity: ThreatSeverity
    findings: tuple[ThreatFinding, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "tool_name": self.tool_name,
            "side_effect_level": self.side_effect_level.value,
            "approval_required": self.approval_required,
            "overall_severity": self.overall_severity.value,
            "findings": [item.to_dict() for item in self.findings],
            "threat_category_names": [item.category.value for item in self.findings],
            "requires_operator_approval": self.approval_required,
            "shell_metachar_arguments_present": any(
                item.category == ThreatCategory.SHELL_METACHAR for item in self.findings
            ),
            "network_target_arguments_present": any(
                item.category == ThreatCategory.NETWORK_TARGET for item in self.findings
            ),
            "credential_arguments_present": any(
                item.category == ThreatCategory.CREDENTIAL_REFERENCE for item in self.findings
            ),
            "lease_scoped_operation": any(
                item.category == ThreatCategory.LEASE_SCOPE for item in self.findings
            ),
        }


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    reason: str
    side_effect_level: SideEffectLevel
    approval_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "side_effect_level": self.side_effect_level.value,
            "approval_required": self.approval_required,
        }


class ReadOnlyToolPolicy:
    allowed_levels = frozenset(
        {
            SideEffectLevel.OBSERVE_ONLY,
            SideEffectLevel.READ_ONLY,
            SideEffectLevel.SUGGEST_ONLY,
        }
    )

    def evaluate_contract(self, contract: Any) -> ToolPolicyDecision:
        side_effect_level = SideEffectLevel(str(contract.side_effect_level))
        approval_required = bool(getattr(contract, "approval_required", False))
        if approval_required:
            return ToolPolicyDecision(
                allowed=False,
                reason="approval_required_tool_blocked_in_no_model_slice",
                side_effect_level=side_effect_level,
                approval_required=approval_required,
            )
        if side_effect_level not in self.allowed_levels:
            return ToolPolicyDecision(
                allowed=False,
                reason="side_effect_level_not_allowed_in_no_model_slice",
                side_effect_level=side_effect_level,
                approval_required=approval_required,
            )
        return ToolPolicyDecision(
            allowed=True,
            reason="read_only_policy_allows_tool",
            side_effect_level=side_effect_level,
            approval_required=approval_required,
        )


def _contains_shell_metacharacters(value: str) -> bool:
    return bool(re.search(r"(;|&&|\|\||\||\$\(|`|>|<|\n)", value))


def _looks_like_network_target(value: str) -> bool:
    return bool(
        re.match(r"^(?:https?://|wss?://|tcp/|udp/)", value)
        or re.match(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$", value)
    )


def _looks_like_credential_reference(argument_name: str, value: str) -> bool:
    lowered_name = argument_name.lower()
    lowered_value = value.lower()
    markers = ("token", "secret", "password", "credential", "api_key", "key", "env-var")
    return any(marker in lowered_name for marker in markers) or any(
        marker in lowered_value for marker in markers
    )


def _argument_items(arguments: dict[str, str] | None) -> Iterable[tuple[str, str]]:
    for name, value in (arguments or {}).items():
        yield str(name), str(value)


def classify_tool_contract_threats(
    contract: Any,
    arguments: dict[str, str] | None = None,
) -> ToolThreatAssessment:
    side_effect_level = SideEffectLevel(str(contract.side_effect_level))
    approval_required = bool(getattr(contract, "approval_required", False))
    tool_name = str(getattr(contract, "tool_name", "unknown_tool"))
    required_resources = tuple(str(item) for item in getattr(contract, "required_resources", ()) or ())
    findings: list[ThreatFinding] = []

    if side_effect_level in {
        SideEffectLevel.LOW_RISK_EXECUTE,
        SideEffectLevel.APPROVAL_REQUIRED,
        SideEffectLevel.DESTRUCTIVE,
    }:
        findings.append(
            ThreatFinding(
                category=ThreatCategory.STATE_MUTATION,
                severity=(
                    ThreatSeverity.HIGH
                    if side_effect_level == SideEffectLevel.DESTRUCTIVE
                    else ThreatSeverity.MEDIUM
                ),
                reason="tool_contract_can_mutate_runtime_state",
                evidence=side_effect_level.value,
            )
        )

    if approval_required:
        findings.append(
            ThreatFinding(
                category=ThreatCategory.APPROVAL_GATE,
                severity=ThreatSeverity.MEDIUM,
                reason="tool_contract_requires_operator_approval",
                evidence="approval_required=true",
            )
        )

    if required_resources:
        findings.append(
            ThreatFinding(
                category=ThreatCategory.LEASE_SCOPE,
                severity=ThreatSeverity.MEDIUM,
                reason="tool_contract_requires_scoped_runtime_resource",
                evidence=",".join(required_resources),
            )
        )

    for argument_name, value in _argument_items(arguments):
        if _looks_like_network_target(value):
            findings.append(
                ThreatFinding(
                    category=ThreatCategory.NETWORK_TARGET,
                    severity=ThreatSeverity.MEDIUM,
                    reason="argument_targets_network_or_remote_endpoint",
                    evidence=f"{argument_name}={value}",
                )
            )
        if _looks_like_credential_reference(argument_name, value):
            findings.append(
                ThreatFinding(
                    category=ThreatCategory.CREDENTIAL_REFERENCE,
                    severity=ThreatSeverity.MEDIUM,
                    reason="argument_references_sensitive_credential_material",
                    evidence=f"{argument_name}={value}",
                )
            )
        if _contains_shell_metacharacters(value):
            findings.append(
                ThreatFinding(
                    category=ThreatCategory.SHELL_METACHAR,
                    severity=ThreatSeverity.HIGH,
                    reason="argument_contains_shell_metacharacters",
                    evidence=f"{argument_name}={value}",
                )
            )

    overall_severity = ThreatSeverity.LOW
    if any(item.severity == ThreatSeverity.HIGH for item in findings):
        overall_severity = ThreatSeverity.HIGH
    elif any(item.severity == ThreatSeverity.MEDIUM for item in findings):
        overall_severity = ThreatSeverity.MEDIUM

    return ToolThreatAssessment(
        tool_name=tool_name,
        side_effect_level=side_effect_level,
        approval_required=approval_required,
        overall_severity=overall_severity,
        findings=tuple(findings),
    )