from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.util import find_spec
import json
import os
from typing import Any, Protocol, cast

from .agents import AffectiveDecision, FakeAffectiveAgent, FakeRationalAgent, RationalPlan
from .common import PerceptionFrame


MAF_RUNTIME_SCHEMA_VERSION = "1.2.0-maf-runtime-v1"
MAF_PROVIDER_SMOKE_SCHEMA_VERSION = "1.2.0-maf-provider-smoke-v1"
MAF_PROVIDER_CONFIG_SCHEMA_VERSION = "1.2.0-maf-provider-config-v1"
MAF_PROVIDER_ENV_VARS = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "OPENAI_API_KEY",
)
MAF_PROVIDER_ENDPOINT_ENV_VARS = (
    "AZURE_OPENAI_ENDPOINT",
    "OPENAI_BASE_URL",
)
MAF_PROVIDER_API_VERSION_ENV_VARS = (
    "AZURE_OPENAI_API_VERSION",
    "OPENAI_API_VERSION",
)
MAF_PROVIDER_MODEL_ENV_VARS = ("OPENAI_MODEL",)
MAF_PROVIDER_DEPLOYMENT_ENV_VARS = (
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
)
MAF_REAL_PROVIDER_ALLOWED_TOOLS = (
    "system_query_device",
    "system_query_apps",
    "system_query_leases",
    "system_state_sync",
    "system_capabilities",
)


class MafProviderMode(StrEnum):
    DETERMINISTIC_FAKE = "deterministic_fake"
    PROVIDER_AVAILABLE_NO_CALL = "provider_available_no_call"
    REAL_PROVIDER = "real_provider"


class MafProviderKind(StrEnum):
    AZURE_OPENAI = "azure_openai"
    OPENAI_COMPATIBLE = "openai_compatible"
    UNKNOWN = "unknown"


def _present_env_vars(
    env: Mapping[str, str],
    names: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(sorted(name for name in names if env.get(name)))


def _first_present_env_var(
    env: Mapping[str, str],
    names: tuple[str, ...],
) -> tuple[str | None, str | None]:
    for name in names:
        value = env.get(name)
        if value:
            return name, value
    return None, None


@dataclass(frozen=True)
class MafProviderConfig:
    provider_kind: str
    credential_env_vars: tuple[str, ...]
    endpoint_env_var: str | None = None
    model_env_var: str | None = None
    deployment_env_var: str | None = None
    configured_model: str | None = None
    configured_deployment: str | None = None
    schema_version: str = MAF_PROVIDER_CONFIG_SCHEMA_VERSION

    @property
    def credentials_available(self) -> bool:
        return bool(self.credential_env_vars)

    @property
    def model_identifier_configured(self) -> bool:
        return bool(self.configured_model or self.configured_deployment)

    @property
    def ready_for_model_call(self) -> bool:
        return self.credentials_available and self.model_identifier_configured

    def missing_requirements(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.credentials_available:
            missing.append("credentials")
        if not self.model_identifier_configured:
            missing.append("model_identifier")
        return tuple(missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_kind": self.provider_kind,
            "credential_env_vars": list(self.credential_env_vars),
            "credentials_available": self.credentials_available,
            "endpoint_env_var": self.endpoint_env_var,
            "endpoint_configured": bool(self.endpoint_env_var),
            "model_env_var": self.model_env_var,
            "deployment_env_var": self.deployment_env_var,
            "configured_model": self.configured_model,
            "configured_deployment": self.configured_deployment,
            "model_identifier_configured": self.model_identifier_configured,
            "ready_for_model_call": self.ready_for_model_call,
            "missing_requirements": list(self.missing_requirements()),
        }


def build_maf_provider_config(
    *,
    env: Mapping[str, str] | None = None,
) -> MafProviderConfig:
    resolved_env = env if env is not None else os.environ
    credential_env_vars = _present_env_vars(resolved_env, MAF_PROVIDER_ENV_VARS)
    endpoint_env_var, _endpoint_value = _first_present_env_var(
        resolved_env,
        MAF_PROVIDER_ENDPOINT_ENV_VARS,
    )
    model_env_var, configured_model = _first_present_env_var(
        resolved_env,
        MAF_PROVIDER_MODEL_ENV_VARS,
    )
    deployment_env_var, configured_deployment = _first_present_env_var(
        resolved_env,
        MAF_PROVIDER_DEPLOYMENT_ENV_VARS,
    )

    if endpoint_env_var == "AZURE_OPENAI_ENDPOINT" or any(
        name.startswith("AZURE_OPENAI_") for name in credential_env_vars
    ):
        provider_kind = MafProviderKind.AZURE_OPENAI.value
    elif endpoint_env_var == "OPENAI_BASE_URL" or "OPENAI_API_KEY" in credential_env_vars:
        provider_kind = MafProviderKind.OPENAI_COMPATIBLE.value
    else:
        provider_kind = MafProviderKind.UNKNOWN.value

    return MafProviderConfig(
        provider_kind=provider_kind,
        credential_env_vars=credential_env_vars,
        endpoint_env_var=endpoint_env_var,
        model_env_var=model_env_var,
        deployment_env_var=deployment_env_var,
        configured_model=configured_model,
        configured_deployment=configured_deployment,
    )


@dataclass(frozen=True)
class MafRuntimeProfile:
    provider_mode: str
    framework_package_available: bool
    real_provider_enabled: bool
    provider_config: MafProviderConfig
    provider_ready_for_model_call: bool
    skip_reason: str = ""
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
            "provider_ready_for_model_call": self.provider_ready_for_model_call,
            "skip_reason": self.skip_reason,
            "requires_model_credentials": self.real_provider_enabled,
            "agent_roles": ["affective", "rational"],
            "provider_config": self.provider_config.to_dict(),
        }


def build_maf_runtime_profile(
    *,
    provider_mode: str = MafProviderMode.DETERMINISTIC_FAKE.value,
    env: Mapping[str, str] | None = None,
) -> MafRuntimeProfile:
    resolved_provider_mode = MafProviderMode(provider_mode)
    provider_config = build_maf_provider_config(env=env)
    framework_package_available = find_spec("agent_framework") is not None
    real_provider_enabled = resolved_provider_mode == MafProviderMode.REAL_PROVIDER
    provider_ready_for_model_call = (
        framework_package_available and provider_config.ready_for_model_call
    )

    if resolved_provider_mode == MafProviderMode.DETERMINISTIC_FAKE:
        skip_reason = "deterministic_fake_mode"
    elif not framework_package_available:
        skip_reason = "agent_framework_package_not_installed"
    elif not provider_config.credentials_available:
        skip_reason = "model_credentials_not_configured"
    elif not provider_config.model_identifier_configured:
        skip_reason = "model_identifier_not_configured"
    elif resolved_provider_mode == MafProviderMode.PROVIDER_AVAILABLE_NO_CALL:
        skip_reason = "availability_only_mode"
    else:
        skip_reason = ""

    return MafRuntimeProfile(
        provider_mode=resolved_provider_mode.value,
        framework_package_available=framework_package_available,
        real_provider_enabled=real_provider_enabled,
        provider_config=provider_config,
        provider_ready_for_model_call=provider_ready_for_model_call,
        skip_reason=skip_reason,
    )


def maf_provider_smoke_status(
    *,
    allow_model_call: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    requested_mode = (
        MafProviderMode.REAL_PROVIDER.value
        if allow_model_call
        else MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value
    )
    runtime_profile = build_maf_runtime_profile(
        provider_mode=requested_mode,
        env=env,
    )
    framework_package_available = runtime_profile.framework_package_available
    present_env_vars = list(runtime_profile.provider_config.credential_env_vars)
    credentials_available = runtime_profile.provider_config.credentials_available
    runnable = runtime_profile.provider_ready_for_model_call
    if runnable:
        status = "ready"
        reason = "framework_package_and_provider_configuration_available"
    elif not framework_package_available:
        status = "skipped"
        reason = "agent_framework_package_not_installed"
    elif not credentials_available:
        status = "skipped"
        reason = "model_credentials_not_configured"
    else:
        status = "skipped"
        reason = "model_identifier_not_configured"
    return {
        "schema_version": MAF_PROVIDER_SMOKE_SCHEMA_VERSION,
        "ok": True,
        "status": status,
        "reason": reason,
        "smoke_mode": "provider_call_opt_in" if allow_model_call else "availability_only",
        "model_call_allowed": allow_model_call,
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
        "call_status": (
            "model_call_not_requested"
            if allow_model_call and runnable
            else "not_requested"
        ),
        "executes_model_call": False,
    }


class MafProviderNotReadyError(RuntimeError):
    pass


class MafProviderClient(Protocol):
    def decide(
        self,
        frame: PerceptionFrame,
        memory_items: list[dict[str, Any]],
        profile: MafRuntimeProfile,
    ) -> dict[str, Any]:
        ...

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        profile: MafRuntimeProfile,
        available_tools: list[dict[str, Any]],
        session_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        ...


def _provider_not_ready_message(profile: MafRuntimeProfile) -> str:
    reason = profile.skip_reason or "provider_not_ready"
    return f"real_microsoft_agent_framework_provider_unavailable:{reason}"


def _extract_json_object(text: str, *, allow_none: bool = False) -> dict[str, Any] | None:
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("provider_response_missing_text")

    candidate_values = [normalized_text]
    start = normalized_text.find("{")
    end = normalized_text.rfind("}")
    if start != -1 and end != -1 and end >= start:
        candidate_values.append(normalized_text[start : end + 1])

    if allow_none:
        candidate_values.append("null")

    for candidate in candidate_values:
        try:
            payload: Any = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if payload is None and allow_none:
            return None
        if isinstance(payload, dict):
            return cast(dict[str, Any], payload)

    raise ValueError("provider_response_not_valid_json_object")


def _extract_agent_response_text(response: Any) -> str:
    text_value = getattr(response, "text", "")
    if callable(text_value):
        text_value = text_value()
    if text_value:
        return str(text_value)

    value = getattr(response, "value", None)
    if value is not None:
        if hasattr(value, "to_dict"):
            return json.dumps(value.to_dict())
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    if hasattr(response, "to_dict"):
        return json.dumps(response.to_dict())

    return ""


def _resolve_agent_framework_openai_symbols() -> tuple[type[Any], type[Any], type[Any]]:
    try:
        from agent_framework import Agent, Message
        from agent_framework.openai import OpenAIChatClient
    except ImportError as exc:
        raise MafProviderNotReadyError(
            "real_microsoft_agent_framework_provider_unavailable:agent_framework_import_failed"
        ) from exc
    return Agent, Message, OpenAIChatClient


def _provider_client_kind(provider_client: Any) -> str:
    return str(getattr(provider_client, "provider_client_kind", "custom"))


class PlaceholderMafProviderClient:
    provider_client_kind = "placeholder"

    def decide(
        self,
        frame: PerceptionFrame,
        memory_items: list[dict[str, Any]],
        profile: MafRuntimeProfile,
    ) -> dict[str, Any]:
        del frame, memory_items, profile
        raise NotImplementedError("real_provider_affective_agent_not_implemented")

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        profile: MafRuntimeProfile,
        available_tools: list[dict[str, Any]],
        session_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        del decision, frame, profile, available_tools, session_context
        raise NotImplementedError("real_provider_rational_agent_not_implemented")


class AgentFrameworkMafProviderClient:
    provider_client_kind = "agent_framework_openai"

    def __init__(
        self,
        profile: MafRuntimeProfile,
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.profile = profile
        self.env = env if env is not None else os.environ
        if not self.profile.provider_ready_for_model_call:
            raise MafProviderNotReadyError(_provider_not_ready_message(self.profile))

        configured_model = (
            self.profile.provider_config.configured_deployment
            or self.profile.provider_config.configured_model
        )
        if not configured_model:
            raise MafProviderNotReadyError(
                "real_microsoft_agent_framework_provider_unavailable:model_identifier_not_configured"
            )

        credential_name, credential_value = _first_present_env_var(
            self.env,
            MAF_PROVIDER_ENV_VARS,
        )
        if not credential_name or not credential_value:
            raise MafProviderNotReadyError(
                "real_microsoft_agent_framework_provider_unavailable:model_credentials_not_configured"
            )

        endpoint_name, endpoint_value = _first_present_env_var(
            self.env,
            MAF_PROVIDER_ENDPOINT_ENV_VARS,
        )
        _api_version_name, api_version_value = _first_present_env_var(
            self.env,
            MAF_PROVIDER_API_VERSION_ENV_VARS,
        )

        agent_cls, message_cls, chat_client_cls = _resolve_agent_framework_openai_symbols()
        client_kwargs: dict[str, Any] = {
            "model": configured_model,
            "api_key": credential_value,
        }
        if endpoint_name == "AZURE_OPENAI_ENDPOINT" and endpoint_value:
            client_kwargs["azure_endpoint"] = endpoint_value
        elif endpoint_name == "OPENAI_BASE_URL" and endpoint_value:
            client_kwargs["base_url"] = endpoint_value
        if api_version_value:
            client_kwargs["api_version"] = api_version_value

        self._agent_cls = agent_cls
        self._message_cls = message_cls
        self.chat_client = chat_client_cls(**client_kwargs)

    @staticmethod
    def _affective_instructions() -> str:
        return (
            "You are the NeuroLink Core affective agent. "
            "Decide whether the current perception frame should delegate to the rational agent. "
            "Return JSON only with keys delegated (bool), reason (string), salience (int 0-100)."
        )

    @staticmethod
    def _rational_instructions() -> str:
        return (
            "You are the NeuroLink Core rational agent. "
            "Pick at most one available tool from the provided live tool manifest. "
            "Do not invent tools, arguments, or capabilities that are not present in that manifest. "
            "Use session context and recent execution history to avoid redundant work when possible. "
            "Return JSON only with keys tool_name (string), args (object), reason (string). "
            "Return null only if no tool should be executed."
        )

    def _run_json_agent(
        self,
        *,
        agent_name: str,
        instructions: str,
        prompt_payload: dict[str, Any],
        allow_none: bool = False,
    ) -> dict[str, Any] | None:
        prompt = json.dumps(prompt_payload, sort_keys=True)

        async def _invoke() -> dict[str, Any] | None:
            agent = self._agent_cls(
                self.chat_client,
                instructions=instructions,
                name=agent_name,
            )
            response = await agent.run(
                [self._message_cls(role="user", contents=[prompt])]
            )
            return _extract_json_object(
                _extract_agent_response_text(response),
                allow_none=allow_none,
            )

        return asyncio.run(_invoke())

    def decide(
        self,
        frame: PerceptionFrame,
        memory_items: list[dict[str, Any]],
        profile: MafRuntimeProfile,
    ) -> dict[str, Any]:
        payload = self._run_json_agent(
            agent_name="neurolink-core-affective",
            instructions=self._affective_instructions(),
            prompt_payload={
                "frame": frame.to_dict(),
                "memory_items": memory_items,
                "maf_runtime": profile.to_dict(),
            },
        )
        assert payload is not None
        return payload

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        profile: MafRuntimeProfile,
        available_tools: list[dict[str, Any]],
        session_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self._run_json_agent(
            agent_name="neurolink-core-rational",
            instructions=self._rational_instructions(),
            prompt_payload={
                "decision": decision.to_dict(),
                "frame": frame.to_dict(),
                "maf_runtime": profile.to_dict(),
                "available_tools": available_tools,
                "session_context": session_context,
                "allowed_tools": list(MAF_REAL_PROVIDER_ALLOWED_TOOLS),
            },
            allow_none=True,
        )


def build_default_maf_provider_client(
    profile: MafRuntimeProfile | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> MafProviderClient:
    resolved_profile = profile or build_maf_runtime_profile(
        provider_mode=MafProviderMode.REAL_PROVIDER.value,
        env=env,
    )
    if not resolved_profile.provider_ready_for_model_call:
        raise MafProviderNotReadyError(_provider_not_ready_message(resolved_profile))
    return AgentFrameworkMafProviderClient(resolved_profile, env=env)


def _coerce_affective_decision(payload: dict[str, Any]) -> AffectiveDecision:
    return AffectiveDecision(
        delegated=bool(payload.get("delegated", False)),
        reason=str(payload.get("reason") or "real_provider_affective_decision"),
        salience=int(payload.get("salience", 0)),
    )


def _coerce_rational_plan(payload: dict[str, Any] | None) -> RationalPlan | None:
    if payload is None:
        return None
    return RationalPlan(
        tool_name=str(payload.get("tool_name") or "system_state_sync"),
        args=dict(payload.get("args") or {}),
        reason=str(payload.get("reason") or "real_provider_rational_plan"),
    )


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


class RealMafAffectiveAgentAdapter:
    def __init__(
        self,
        profile: MafRuntimeProfile | None = None,
        provider_client: MafProviderClient | None = None,
    ) -> None:
        self.profile = profile or build_maf_runtime_profile(
            provider_mode=MafProviderMode.REAL_PROVIDER.value
        )
        if not self.profile.provider_ready_for_model_call:
            raise MafProviderNotReadyError(_provider_not_ready_message(self.profile))
        self.provider_client = provider_client or PlaceholderMafProviderClient()

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            **self.profile.to_dict(),
            "agent_role": "affective",
            "agent_adapter": f"real_provider_affective_{_provider_client_kind(self.provider_client)}",
            "provider_client_kind": _provider_client_kind(self.provider_client),
            "provider_call_supported": not isinstance(
                self.provider_client,
                PlaceholderMafProviderClient,
            ),
        }

    def decide(
        self,
        frame: PerceptionFrame,
        memory_items: list[dict[str, Any]],
    ) -> AffectiveDecision:
        return _coerce_affective_decision(
            self.provider_client.decide(frame, memory_items, self.profile)
        )


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
        *,
        available_tools: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> RationalPlan | None:
        return self.agent.plan(
            decision,
            frame,
            available_tools=available_tools,
            session_context=session_context,
        )


class RealMafRationalAgentAdapter:
    def __init__(
        self,
        profile: MafRuntimeProfile | None = None,
        provider_client: MafProviderClient | None = None,
    ) -> None:
        self.profile = profile or build_maf_runtime_profile(
            provider_mode=MafProviderMode.REAL_PROVIDER.value
        )
        if not self.profile.provider_ready_for_model_call:
            raise MafProviderNotReadyError(_provider_not_ready_message(self.profile))
        self.provider_client = provider_client or PlaceholderMafProviderClient()

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            **self.profile.to_dict(),
            "agent_role": "rational",
            "agent_adapter": f"real_provider_rational_{_provider_client_kind(self.provider_client)}",
            "provider_client_kind": _provider_client_kind(self.provider_client),
            "provider_call_supported": not isinstance(
                self.provider_client,
                PlaceholderMafProviderClient,
            ),
        }

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        *,
        available_tools: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> RationalPlan | None:
        return _coerce_rational_plan(
            self.provider_client.plan(
                decision,
                frame,
                self.profile,
                available_tools or [],
                session_context or {},
            )
        )


def build_affective_agent_adapter(
    profile: MafRuntimeProfile | None = None,
    provider_client: MafProviderClient | None = None,
) -> MafAffectiveAgentAdapter | RealMafAffectiveAgentAdapter:
    resolved_profile = profile or build_maf_runtime_profile()
    if resolved_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value:
        return RealMafAffectiveAgentAdapter(
            profile=resolved_profile,
            provider_client=provider_client,
        )
    return MafAffectiveAgentAdapter(profile=resolved_profile)


def build_rational_agent_adapter(
    profile: MafRuntimeProfile | None = None,
    provider_client: MafProviderClient | None = None,
) -> MafRationalAgentAdapter | RealMafRationalAgentAdapter:
    resolved_profile = profile or build_maf_runtime_profile()
    if resolved_profile.provider_mode == MafProviderMode.REAL_PROVIDER.value:
        return RealMafRationalAgentAdapter(
            profile=resolved_profile,
            provider_client=provider_client,
        )
    return MafRationalAgentAdapter(profile=resolved_profile)