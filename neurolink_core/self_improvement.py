from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


PROHIBITED_SELF_IMPROVEMENT_ACTIONS = (
    "git_push",
    "firmware_flash",
    "credential_mutation",
    "production_deploy",
)


@dataclass(frozen=True)
class ImprovementEvidence:
    tests_passed: bool = False
    lint_passed: bool = False
    smoke_passed: bool = False
    evidence_refs: tuple[str, ...] = ()

    def verified_success(self) -> bool:
        return self.tests_passed and self.lint_passed and self.smoke_passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "tests_passed": self.tests_passed,
            "lint_passed": self.lint_passed,
            "smoke_passed": self.smoke_passed,
            "evidence_refs": list(self.evidence_refs),
            "verified_success": self.verified_success(),
        }


@dataclass(frozen=True)
class ImprovementProposal:
    proposal_id: str
    source: str
    summary: str
    risk_level: Literal["low", "medium", "high"]
    sandbox_mode: Literal["simulation", "isolated_workspace"]
    status: Literal["proposed", "pending_approval"]
    touches_code: bool = True
    targets_runtime: bool = False
    approval_required: bool = True
    prohibited_actions: tuple[str, ...] = PROHIBITED_SELF_IMPROVEMENT_ACTIONS
    evidence: ImprovementEvidence = field(default_factory=ImprovementEvidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "source": self.source,
            "summary": self.summary,
            "risk_level": self.risk_level,
            "sandbox_mode": self.sandbox_mode,
            "status": self.status,
            "touches_code": self.touches_code,
            "targets_runtime": self.targets_runtime,
            "approval_required": self.approval_required,
            "prohibited_actions": list(self.prohibited_actions),
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True)
class ImprovementReview:
    proposal: ImprovementProposal
    decision: Literal["pending_approval", "denied", "approved"]
    execution_mode: Literal["sandbox_only", "not_executed"]
    can_apply_changes: bool
    vitality_replenishment_allowed: bool
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal.to_dict(),
            "decision": self.decision,
            "execution_mode": self.execution_mode,
            "can_apply_changes": self.can_apply_changes,
            "vitality_replenishment_allowed": self.vitality_replenishment_allowed,
            "failure_reason": self.failure_reason,
        }


def classify_improvement_risk(
    *,
    source: str,
    touches_code: bool,
    targets_runtime: bool,
) -> Literal["low", "medium", "high"]:
    if targets_runtime:
        return "high"
    if touches_code or source in {"failed_test", "maintenance_finding"}:
        return "medium"
    return "low"


def propose_self_improvement(
    *,
    proposal_id: str,
    source: str,
    summary: str,
    touches_code: bool = True,
    targets_runtime: bool = False,
    evidence: ImprovementEvidence | None = None,
) -> ImprovementProposal:
    risk_level = classify_improvement_risk(
        source=source,
        touches_code=touches_code,
        targets_runtime=targets_runtime,
    )
    sandbox_mode: Literal["simulation", "isolated_workspace"] = (
        "isolated_workspace" if touches_code or targets_runtime else "simulation"
    )
    return ImprovementProposal(
        proposal_id=proposal_id,
        source=source,
        summary=summary,
        risk_level=risk_level,
        sandbox_mode=sandbox_mode,
        status="pending_approval",
        touches_code=touches_code,
        targets_runtime=targets_runtime,
        approval_required=True,
        evidence=evidence or ImprovementEvidence(),
    )


def review_self_improvement(
    proposal: ImprovementProposal,
    *,
    approved: bool,
    evidence: ImprovementEvidence,
) -> ImprovementReview:
    reviewed = ImprovementProposal(
        proposal_id=proposal.proposal_id,
        source=proposal.source,
        summary=proposal.summary,
        risk_level=proposal.risk_level,
        sandbox_mode=proposal.sandbox_mode,
        status=proposal.status,
        touches_code=proposal.touches_code,
        targets_runtime=proposal.targets_runtime,
        approval_required=proposal.approval_required,
        prohibited_actions=proposal.prohibited_actions,
        evidence=evidence,
    )
    if not approved:
        return ImprovementReview(
            proposal=reviewed,
            decision="denied",
            execution_mode="not_executed",
            can_apply_changes=False,
            vitality_replenishment_allowed=False,
            failure_reason="operator_denied",
        )
    if not evidence.verified_success():
        return ImprovementReview(
            proposal=reviewed,
            decision="approved",
            execution_mode="sandbox_only",
            can_apply_changes=False,
            vitality_replenishment_allowed=False,
            failure_reason="verified_evidence_incomplete",
        )
    return ImprovementReview(
        proposal=reviewed,
        decision="approved",
        execution_mode="sandbox_only",
        can_apply_changes=False,
        vitality_replenishment_allowed=True,
        failure_reason=None,
    )