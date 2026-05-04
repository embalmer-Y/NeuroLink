from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
import os
from typing import Any

from .agents import AffectiveDecision, FakeAffectiveAgent, FakeRationalAgent, RationalPlan
from .common import PerceptionFrame


MAF_RUNTIME_SCHEMA_VERSION = "1.2.0-maf-runtime-v1"
MAF_PROVIDER_SMOKE_SCHEMA_VERSION = "1.2.0-maf-provider-smoke-v1"
MAF_PROVIDER_ENV_VARS = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "OPENAI_API_KEY",
)


@dataclass(frozen=True)
class MafRuntimeProfile:
    provider_mode: str
    framework_package_available: bool
    real_provider_enabled: bool
    workflow_api: str = "functional_workflow_compatible"
    framework: str = "microsoft_agent_framework"
    schema_version: str = MAF_RUNTIME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "framework": self.framework,
            "workflow_api": self.workflow_api,
            "provider_mode": self.provider_mode,
            "framework_package_available": self.framework_package_available,
            "real_provider_enabled": self.real_provider_enabled,
            "requires_model_credentials": self.real_provider_enabled,
            "agent_roles": ["affective", "rational"],
        }


def build_maf_runtime_profile(
    *,
    provider_mode: str = "deterministic_fake",
) -> MafRuntimeProfile:
    real_provider_enabled = provider_mode != "deterministic_fake"
    return MafRuntimeProfile(
        provider_mode=provider_mode,
        framework_package_available=find_spec("agent_framework") is not None,
        real_provider_enabled=real_provider_enabled,
    )


def maf_provider_smoke_status() -> dict[str, Any]:
    runtime_profile = build_maf_runtime_profile()
    framework_package_available = find_spec("agent_framework") is not None
    present_env_vars = sorted(name for name in MAF_PROVIDER_ENV_VARS if os.environ.get(name))
    credentials_available = bool(present_env_vars)
    runnable = framework_package_available and credentials_available
    if runnable:
        status = "ready"
        reason = "framework_package_and_credentials_available"
    elif not framework_package_available:
        status = "skipped"
        reason = "agent_framework_package_not_installed"
    else:
        status = "skipped"
        reason = "model_credentials_not_configured"
    return {
        "schema_version": MAF_PROVIDER_SMOKE_SCHEMA_VERSION,
        "ok": True,
        "status": status,
        "reason": reason,
        "framework_package_available": framework_package_available,
        "credentials_available": credentials_available,
        "present_env_vars": present_env_vars,
        "maf_runtime": {
            **runtime_profile.to_dict(),
            "agent_adapters": [
                {"agent_role": "affective", "agent_adapter": "deterministic_fake_affective"},
                {"agent_role": "rational", "agent_adapter": "deterministic_fake_rational"},
            ],
        },
        "requires_model_credentials": True,
        "executes_model_call": False,
    }


class MafAffectiveAgentAdapter:
    def __init__(
        self,
        agent: FakeAffectiveAgent | None = None,
        profile: MafRuntimeProfile | None = None,
    ) -> None:
        self.agent = agent or FakeAffectiveAgent()
        self.profile = profile or build_maf_runtime_profile()

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            **self.profile.to_dict(),
            "agent_role": "affective",
            "agent_adapter": "deterministic_fake_affective",
        }

    def decide(
        self,
        frame: PerceptionFrame,
        memory_items: list[dict[str, Any]],
    ) -> AffectiveDecision:
        return self.agent.decide(frame, memory_items)


class MafRationalAgentAdapter:
    def __init__(
        self,
        agent: FakeRationalAgent | None = None,
        profile: MafRuntimeProfile | None = None,
    ) -> None:
        self.agent = agent or FakeRationalAgent()
        self.profile = profile or build_maf_runtime_profile()

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            **self.profile.to_dict(),
            "agent_role": "rational",
            "agent_adapter": "deterministic_fake_rational",
        }

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
    ) -> RationalPlan | None:
        return self.agent.plan(decision, frame)