from __future__ import annotations

from typing import Any
import unittest

from neurolink_core.agents import AffectiveDecision, FakeRationalAgent
from neurolink_core.common import PerceptionFrame
from neurolink_core.rational_backends import (
    CopilotSdkRationalBackend,
    DeterministicRationalBackend,
    ProviderRationalBackend,
    validate_rational_plan_payload,
)


class TestRationalBackends(unittest.TestCase):
    def test_validate_rational_plan_accepts_strict_payload(self) -> None:
        plan = validate_rational_plan_payload(
            {
                "tool_name": "system_query_device",
                "args": {"reason": "test"},
                "reason": "read_current_device_state",
            }
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_query_device")
        self.assertEqual(plan.args, {"reason": "test"})
        self.assertEqual(plan.reason, "read_current_device_state")

    def test_validate_rational_plan_rejects_malformed_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "rational_plan_tool_name_must_be_string"):
            validate_rational_plan_payload({"args": {}, "reason": "missing tool"})
        with self.assertRaisesRegex(ValueError, "rational_plan_args_must_be_object"):
            validate_rational_plan_payload(
                {"tool_name": "system_query_device", "args": [], "reason": "bad args"}
            )
        with self.assertRaisesRegex(ValueError, "rational_plan_reason_must_be_string"):
            validate_rational_plan_payload(
                {"tool_name": "system_query_device", "args": {}, "reason": ""}
            )

    def test_deterministic_backend_preserves_existing_fake_planning(self) -> None:
        backend = DeterministicRationalBackend(FakeRationalAgent())
        decision = AffectiveDecision(
            delegated=True,
            reason="user_control_requested",
            salience=70,
        )
        frame = PerceptionFrame(
            frame_id="frame-control",
            event_ids=("evt-control",),
            highest_priority=70,
            topics=("user.input.control.app.stop",),
        )

        plan = backend.plan(
            decision,
            frame,
            session_context={"target_app_id": "neuro_demo_gpio"},
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_stop_app")
        self.assertEqual(plan.args["app_id"], "neuro_demo_gpio")
        self.assertFalse(backend.runtime_metadata()["can_execute_tools_directly"])

    def test_provider_backend_passes_context_and_validates_result(self) -> None:
        class FakeProviderClient:
            last_call: dict[str, Any]

            def plan(
                self,
                decision: AffectiveDecision,
                frame: PerceptionFrame,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                self.last_call = {
                    "decision": decision,
                    "frame": frame,
                    "profile": profile,
                    "available_tools": available_tools,
                    "session_context": session_context,
                }
                return {
                    "tool_name": "system_query_apps",
                    "args": {"source": "provider"},
                    "reason": "provider_selected_apps_query",
                }

        client = FakeProviderClient()
        backend = ProviderRationalBackend(
            provider_client=client,
            profile={"provider_mode": "real_provider"},
            provider_client_kind="test_provider",
        )
        decision = AffectiveDecision(
            delegated=True,
            reason="needs_rational_plan",
            salience=80,
        )
        frame = PerceptionFrame(
            frame_id="frame-provider",
            event_ids=("evt-provider",),
            highest_priority=80,
            topics=("user.input.query.apps",),
        )

        plan = backend.plan(
            decision,
            frame,
            available_tools=[{"name": "system_query_apps"}],
            session_context={"session_id": "session-provider"},
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_query_apps")
        self.assertEqual(client.last_call["available_tools"][0]["name"], "system_query_apps")
        self.assertEqual(client.last_call["session_context"]["session_id"], "session-provider")
        self.assertEqual(
            backend.runtime_metadata()["provider_client_kind"],
            "test_provider",
        )
        self.assertFalse(backend.runtime_metadata()["can_execute_tools_directly"])

    def test_provider_backend_rejects_invalid_provider_plan(self) -> None:
        class InvalidProviderClient:
            def plan(
                self,
                decision: AffectiveDecision,
                frame: PerceptionFrame,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any]:
                del decision, frame, profile, available_tools, session_context
                return {"tool_name": "system_query_apps", "args": [], "reason": "bad"}

        backend = ProviderRationalBackend(
            provider_client=InvalidProviderClient(),
            profile={"provider_mode": "real_provider"},
            provider_client_kind="invalid_provider",
        )

        with self.assertRaisesRegex(ValueError, "rational_plan_args_must_be_object"):
            backend.plan(
                AffectiveDecision(
                    delegated=True,
                    reason="needs_rational_plan",
                    salience=80,
                ),
                PerceptionFrame(
                    frame_id="frame-invalid",
                    event_ids=("evt-invalid",),
                    highest_priority=80,
                    topics=("user.input.query.apps",),
                ),
            )

    def test_copilot_backend_requires_explicit_model_call_gate(self) -> None:
        backend = CopilotSdkRationalBackend(allow_model_call=False)

        with self.assertRaisesRegex(
            ValueError,
            "copilot_rational_backend_requires_allow_model_call",
        ):
            backend.plan(
                AffectiveDecision(
                    delegated=True,
                    reason="needs_rational_plan",
                    salience=80,
                ),
                PerceptionFrame(
                    frame_id="frame-copilot-gated",
                    event_ids=("evt-copilot-gated",),
                    highest_priority=80,
                    topics=("user.input.query.device",),
                ),
            )

    def test_copilot_backend_uses_injected_agent_and_validates_plan(self) -> None:
        class FakeCopilotAgent:
            def __init__(self, default_options: dict[str, Any]) -> None:
                self.default_options = default_options

            async def __aenter__(self) -> "FakeCopilotAgent":
                return self

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                del exc_type, exc, tb

            async def run(self, prompt: str) -> str:
                self.prompt = prompt
                return (
                    '{"tool_name":"system_query_device",'
                    '"args":{"source":"copilot"},'
                    '"reason":"copilot_selected_device_query"}'
                )

        created_agents: list[FakeCopilotAgent] = []

        def agent_factory(default_options: dict[str, Any]) -> FakeCopilotAgent:
            agent = FakeCopilotAgent(default_options)
            created_agents.append(agent)
            return agent

        backend = CopilotSdkRationalBackend(
            allow_model_call=True,
            agent_factory=agent_factory,
            env={"GITHUB_COPILOT_MODEL": "gpt-5", "GITHUB_COPILOT_TIMEOUT": "120"},
        )

        plan = backend.plan(
            AffectiveDecision(
                delegated=True,
                reason="needs_rational_plan",
                salience=80,
            ),
            PerceptionFrame(
                frame_id="frame-copilot",
                event_ids=("evt-copilot",),
                highest_priority=80,
                topics=("user.input.query.device",),
            ),
            available_tools=[{"name": "system_query_device"}],
            session_context={"schema_version": "1.2.2-prompt-safe-context-v1"},
        )

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_query_device")
        self.assertEqual(plan.args["source"], "copilot")
        self.assertEqual(created_agents[0].default_options["model"], "gpt-5")
        self.assertEqual(created_agents[0].default_options["timeout"], 120)
        self.assertIn("available_tools", created_agents[0].prompt)
        self.assertEqual(
            backend.runtime_metadata()["backend_kind"],
            "github_copilot_sdk",
        )
        self.assertFalse(backend.runtime_metadata()["can_execute_tools_directly"])

    def test_copilot_backend_rejects_malformed_plan(self) -> None:
        class InvalidCopilotAgent:
            def __init__(self, default_options: dict[str, Any]) -> None:
                del default_options

            async def __aenter__(self) -> "InvalidCopilotAgent":
                return self

            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                del exc_type, exc, tb

            async def run(self, prompt: str) -> str:
                del prompt
                return '{"tool_name":"","args":{},"reason":"bad"}'

        backend = CopilotSdkRationalBackend(
            allow_model_call=True,
            agent_factory=lambda default_options: InvalidCopilotAgent(default_options),
        )

        with self.assertRaisesRegex(ValueError, "rational_plan_tool_name_must_be_string"):
            backend.plan(
                AffectiveDecision(
                    delegated=True,
                    reason="needs_rational_plan",
                    salience=80,
                ),
                PerceptionFrame(
                    frame_id="frame-copilot-invalid",
                    event_ids=("evt-copilot-invalid",),
                    highest_priority=80,
                    topics=("user.input.query.device",),
                ),
            )


if __name__ == "__main__":
    unittest.main()