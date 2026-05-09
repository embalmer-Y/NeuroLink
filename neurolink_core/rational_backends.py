from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
import json
import os
from collections.abc import Mapping
from typing import Any, Protocol, cast

from .agents import AffectiveDecision, FakeRationalAgent, RationalPlan
from .common import PerceptionFrame


class RationalBackend(Protocol):
    backend_kind: str

    def runtime_metadata(self) -> dict[str, Any]:
        ...

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        *,
        available_tools: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> RationalPlan | None:
        ...


def validate_rational_plan_payload(
    payload: dict[str, Any] | None,
    *,
    available_tools: list[dict[str, Any]] | None = None,
) -> RationalPlan | None:
    if payload is None:
        return None
    tool_name = payload.get("tool_name")
    args = payload.get("args")
    reason = payload.get("reason")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("rational_plan_tool_name_must_be_string")
    if not isinstance(args, dict):
        raise ValueError("rational_plan_args_must_be_object")
    if not isinstance(reason, str) or not reason:
        raise ValueError("rational_plan_reason_must_be_string")
    if available_tools is not None:
        available_tool_names = {
            str(tool.get("name") or tool.get("tool_name") or "")
            for tool in available_tools
        }
        if tool_name not in available_tool_names:
            raise ValueError("rational_plan_tool_not_in_available_tools")
    return RationalPlan(
        tool_name=tool_name,
        args=dict(args),
        reason=reason,
    )


@dataclass
class DeterministicRationalBackend:
    agent: FakeRationalAgent
    backend_kind: str = "deterministic_fake"

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "backend_kind": self.backend_kind,
            "backend_runtime": "local_deterministic",
            "requires_external_sdk": False,
            "can_execute_tools_directly": False,
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


@dataclass
class ProviderRationalBackend:
    provider_client: Any
    profile: Any
    provider_client_kind: str
    backend_kind: str = "maf_provider_client"

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "backend_kind": self.backend_kind,
            "backend_runtime": "provider_plan",
            "provider_client_kind": self.provider_client_kind,
            "requires_external_sdk": True,
            "can_execute_tools_directly": False,
        }

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        *,
        available_tools: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> RationalPlan | None:
        return validate_rational_plan_payload(
            self.provider_client.plan(
                decision,
                frame,
                self.profile,
                available_tools or [],
                session_context or {},
            ),
            available_tools=available_tools or [],
        )


@dataclass
class CopilotSdkRationalBackend:
    allow_model_call: bool = False
    env: Mapping[str, str] | None = None
    agent_factory: Any | None = None
    backend_kind: str = "github_copilot_sdk"

    def runtime_metadata(self) -> dict[str, Any]:
        resolved_env = self.env if self.env is not None else os.environ
        return {
            "backend_kind": self.backend_kind,
            "backend_runtime": "agent_framework_github_copilot",
            "package_name": "agent-framework-github-copilot",
            "package_available": _copilot_package_available(),
            "requires_external_sdk": True,
            "requires_copilot_cli_auth": True,
            "model_env_var": "GITHUB_COPILOT_MODEL"
            if resolved_env.get("GITHUB_COPILOT_MODEL")
            else None,
            "cli_path_env_var": "GITHUB_COPILOT_CLI_PATH"
            if resolved_env.get("GITHUB_COPILOT_CLI_PATH")
            else None,
            "timeout_env_var": "GITHUB_COPILOT_TIMEOUT"
            if resolved_env.get("GITHUB_COPILOT_TIMEOUT")
            else None,
            "log_level_env_var": "GITHUB_COPILOT_LOG_LEVEL"
            if resolved_env.get("GITHUB_COPILOT_LOG_LEVEL")
            else None,
            "model_call_allowed": self.allow_model_call,
            "can_execute_tools_directly": False,
        }

    def plan(
        self,
        decision: AffectiveDecision,
        frame: PerceptionFrame,
        *,
        available_tools: list[dict[str, Any]] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> RationalPlan | None:
        if not self.allow_model_call:
            raise ValueError("copilot_rational_backend_requires_allow_model_call")
        payload = {
            "decision": decision.to_dict(),
            "frame": frame.to_dict(),
            "available_tools": available_tools or [],
            "session_context": session_context or {},
            "response_contract": {
                "return_json_only": True,
                "nullable": True,
                "schema": {
                    "tool_name": "string from available_tools only",
                    "args": "object",
                    "reason": "non-empty string",
                },
            },
            "safety_boundaries": {
                "plan_only": True,
                "can_execute_tools_directly": False,
                "core_policy_and_approval_gates_authoritative": True,
            },
        }
        return validate_rational_plan_payload(
            _extract_json_object(
                self._run_copilot_agent(json.dumps(payload, sort_keys=True)),
                allow_none=True,
            ),
            available_tools=available_tools or [],
        )

    def _run_copilot_agent(self, prompt: str) -> str:
        async def _invoke() -> str:
            agent = self._build_agent()
            async with agent:
                response = await agent.run(prompt)
            return _extract_response_text(response)

        return asyncio.run(_invoke())

    def _build_agent(self) -> Any:
        default_options = _copilot_default_options(self.env)
        if self.agent_factory is not None:
            return self.agent_factory(default_options=default_options)
        if not _copilot_package_available():
            raise RuntimeError("github_copilot_agent_framework_package_not_installed")
        module = import_module("agent_framework.github")
        agent_cls = getattr(module, "GitHubCopilotAgent")
        return agent_cls(default_options=default_options)


def _copilot_package_available() -> bool:
    return find_spec("agent_framework.github") is not None


def _copilot_default_options(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    resolved_env = env if env is not None else os.environ
    options: dict[str, Any] = {
        "instructions": (
            "You are the NeuroLink Core Rational Agent running through GitHub Copilot. "
            "Return JSON only. Pick at most one tool from the provided available_tools list. "
            "Do not call shell commands, access files, fetch URLs, use MCP servers, or execute Unit tools. "
            "You may only propose a RationalPlan for the NeuroLink Core policy layer to evaluate. "
            "Return null if no tool should be executed."
        )
    }
    model = resolved_env.get("GITHUB_COPILOT_MODEL")
    timeout = resolved_env.get("GITHUB_COPILOT_TIMEOUT")
    if model:
        options["model"] = model
    if timeout:
        try:
            options["timeout"] = int(timeout)
        except ValueError:
            options["timeout"] = timeout
    return options


def _extract_response_text(response: Any) -> str:
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
    return str(response)


def _extract_json_object(text: str, *, allow_none: bool = False) -> dict[str, Any] | None:
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("copilot_response_missing_text")
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
    raise ValueError("copilot_response_not_valid_json_object")