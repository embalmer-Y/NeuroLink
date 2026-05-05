from typing import Any, cast
import unittest
from unittest import mock

from neurolink_core.agents import AffectiveDecision
from neurolink_core.common import PerceptionFrame
from neurolink_core.maf import (
    AgentFrameworkMafProviderClient,
    MAF_RUNTIME_SCHEMA_VERSION,
    MAF_PROVIDER_SMOKE_SCHEMA_VERSION,
    MafAffectiveAgentAdapter,
    MafProviderNotReadyError,
    MafRationalAgentAdapter,
    MafProviderMode,
    RealMafAffectiveAgentAdapter,
    RealMafRationalAgentAdapter,
    build_affective_agent_adapter,
    build_default_maf_provider_client,
    build_rational_agent_adapter,
    build_maf_runtime_profile,
    maf_provider_smoke_status,
)
from neurolink_core.cli import main as core_cli_main
from neurolink_core.workflow import run_no_model_dry_run

import io
import json
from contextlib import redirect_stdout


class TestMafRuntimeBoundary(unittest.TestCase):
    def test_runtime_profile_defaults_to_deterministic_fake_provider(self) -> None:
        profile = build_maf_runtime_profile()
        payload = profile.to_dict()

        self.assertEqual(payload["schema_version"], MAF_RUNTIME_SCHEMA_VERSION)
        self.assertEqual(payload["framework"], "microsoft_agent_framework")
        self.assertEqual(payload["workflow_api"], "functional_workflow_compatible")
        self.assertEqual(payload["provider_mode"], "deterministic_fake")
        self.assertFalse(payload["real_provider_enabled"])
        self.assertFalse(payload["requires_model_credentials"])
        self.assertEqual(payload["skip_reason"], "deterministic_fake_mode")
        self.assertIn("provider_config", payload)
        self.assertEqual(payload["agent_roles"], ["affective", "rational"])

    def test_runtime_profile_reports_safe_provider_configuration(self) -> None:
        with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
            profile = build_maf_runtime_profile(
                provider_mode=MafProviderMode.REAL_PROVIDER.value,
                env={
                    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                    "AZURE_OPENAI_API_KEY": "secret",
                    "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-4.1-mini",
                },
            )

        payload = profile.to_dict()
        self.assertEqual(payload["provider_mode"], "real_provider")
        self.assertTrue(payload["real_provider_enabled"])
        self.assertTrue(payload["provider_ready_for_model_call"])
        self.assertEqual(payload["skip_reason"], "")
        self.assertEqual(
            payload["provider_config"]["provider_kind"],
            "azure_openai",
        )
        self.assertEqual(
            payload["provider_config"]["credential_env_vars"],
            ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"],
        )
        self.assertEqual(
            payload["provider_config"]["configured_deployment"],
            "gpt-4.1-mini",
        )

    def test_deterministic_maf_adapters_delegate_to_fake_agents(self) -> None:
        frame = PerceptionFrame(
            frame_id="frame-test",
            event_ids=("evt-1",),
            highest_priority=80,
            topics=("unit.callback",),
        )
        affective = MafAffectiveAgentAdapter()
        rational = MafRationalAgentAdapter()

        decision = affective.decide(frame, [])
        plan = rational.plan(decision, frame)

        self.assertTrue(decision.delegated)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_state_sync")
        self.assertEqual(plan.args["event_ids"], ["evt-1"])
        self.assertEqual(affective.runtime_metadata()["agent_role"], "affective")
        self.assertEqual(rational.runtime_metadata()["agent_role"], "rational")

    def test_real_provider_adapter_factory_fails_closed_when_not_ready(self) -> None:
        profile = build_maf_runtime_profile(
            provider_mode=MafProviderMode.REAL_PROVIDER.value,
            env={},
        )

        with self.assertRaises(MafProviderNotReadyError):
            build_affective_agent_adapter(profile)
        with self.assertRaises(MafProviderNotReadyError):
            build_rational_agent_adapter(profile)

    def test_real_provider_adapter_factory_returns_placeholder_when_ready(self) -> None:
        with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
            profile = build_maf_runtime_profile(
                provider_mode=MafProviderMode.REAL_PROVIDER.value,
                env={
                    "OPENAI_API_KEY": "secret",
                    "OPENAI_MODEL": "gpt-4.1-mini",
                },
            )

        affective = build_affective_agent_adapter(profile)
        rational = build_rational_agent_adapter(profile)

        self.assertIsInstance(affective, RealMafAffectiveAgentAdapter)
        self.assertIsInstance(rational, RealMafRationalAgentAdapter)
        self.assertFalse(affective.runtime_metadata()["provider_call_supported"])
        self.assertFalse(rational.runtime_metadata()["provider_call_supported"])

    def test_real_provider_adapters_can_use_injected_provider_client(self) -> None:
        class FakeProviderClient:
            last_decide: tuple[PerceptionFrame, list[dict[str, Any]], Any]
            last_plan: tuple[
                AffectiveDecision,
                PerceptionFrame,
                Any,
                list[dict[str, Any]],
                dict[str, Any],
            ]

            def decide(
                self,
                frame: PerceptionFrame,
                memory_items: list[dict[str, Any]],
                profile: Any,
            ) -> dict[str, Any]:
                self.last_decide = (frame, memory_items, profile)
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 91,
                }

            def plan(
                self,
                decision: AffectiveDecision,
                frame: PerceptionFrame,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any] | None:
                self.last_plan = (
                    decision,
                    frame,
                    profile,
                    available_tools,
                    session_context,
                )
                return {
                    "tool_name": "system_query_device",
                    "args": {"source": "real-provider"},
                    "reason": "real_provider_rational_plan",
                }

        frame = PerceptionFrame(
            frame_id="frame-real-provider",
            event_ids=("evt-real-1",),
            highest_priority=91,
            topics=("user.input.query.device",),
        )
        client = FakeProviderClient()
        with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
            profile = build_maf_runtime_profile(
                provider_mode=MafProviderMode.REAL_PROVIDER.value,
                env={
                    "OPENAI_API_KEY": "secret",
                    "OPENAI_MODEL": "gpt-4.1-mini",
                },
            )

        affective = build_affective_agent_adapter(profile, provider_client=client)
        rational = build_rational_agent_adapter(profile, provider_client=client)

        decision = affective.decide(frame, [{"memory_id": "mem-1"}])
        plan = rational.plan(decision, frame)

        self.assertIsInstance(affective, RealMafAffectiveAgentAdapter)
        self.assertIsInstance(rational, RealMafRationalAgentAdapter)
        self.assertTrue(affective.runtime_metadata()["provider_call_supported"])
        self.assertTrue(rational.runtime_metadata()["provider_call_supported"])
        self.assertTrue(decision.delegated)
        self.assertEqual(decision.salience, 91)
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.tool_name, "system_query_device")
        self.assertEqual(plan.args["source"], "real-provider")

    def test_real_provider_rational_adapter_passes_live_context_to_provider(self) -> None:
        class FakeProviderClient:
            last_plan: dict[str, Any]

            def decide(
                self,
                frame: PerceptionFrame,
                memory_items: list[dict[str, Any]],
                profile: Any,
            ) -> dict[str, Any]:
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 77,
                }

            def plan(
                self,
                decision: AffectiveDecision,
                frame: PerceptionFrame,
                profile: Any,
                available_tools: list[dict[str, Any]],
                session_context: dict[str, Any],
            ) -> dict[str, Any] | None:
                self.last_plan = {
                    "decision": decision,
                    "frame": frame,
                    "profile": profile,
                    "available_tools": available_tools,
                    "session_context": session_context,
                }
                return None

        frame = PerceptionFrame(
            frame_id="frame-plan-context",
            event_ids=("evt-ctx-1",),
            highest_priority=77,
            topics=("user.input.query.device",),
        )
        client = FakeProviderClient()
        with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
            profile = build_maf_runtime_profile(
                provider_mode=MafProviderMode.REAL_PROVIDER.value,
                env={
                    "OPENAI_API_KEY": "secret",
                    "OPENAI_MODEL": "gpt-4.1-mini",
                },
            )

        rational = build_rational_agent_adapter(profile, provider_client=client)
        decision = AffectiveDecision(
            delegated=True,
            reason="real_provider_affective_decision",
            salience=77,
        )

        plan = rational.plan(
            decision,
            frame,
            available_tools=[{"name": "system_query_device", "side_effect_level": "read_only"}],
            session_context={"session_id": "session-test-001"},
        )

        self.assertIsNone(plan)
        self.assertEqual(client.last_plan["available_tools"][0]["name"], "system_query_device")
        self.assertEqual(client.last_plan["session_context"]["session_id"], "session-test-001")

    def test_default_provider_client_factory_builds_agent_framework_client(self) -> None:
        class FakeChatClient:
            kwargs: dict[str, Any]

            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

        class FakeMessage:
            role: str
            contents: list[str]

            def __init__(self, role: str, contents: list[str]) -> None:
                self.role = role
                self.contents = contents

        class FakeAgent:
            client: Any
            instructions: str | None
            name: str | None

            def __init__(
                self,
                client: Any,
                instructions: str | None = None,
                name: str | None = None,
            ) -> None:
                self.client = client
                self.instructions = instructions
                self.name = name

        env = {
            "OPENAI_API_KEY": "secret",
            "OPENAI_MODEL": "gpt-4.1-mini",
            "OPENAI_BASE_URL": "https://example.test/v1",
        }
        with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
            profile = build_maf_runtime_profile(
                provider_mode=MafProviderMode.REAL_PROVIDER.value,
                env=env,
            )
        with mock.patch(
            "neurolink_core.maf._resolve_agent_framework_openai_symbols",
            return_value=(FakeAgent, FakeMessage, FakeChatClient),
        ):
            client = cast(
                AgentFrameworkMafProviderClient,
                build_default_maf_provider_client(profile, env=env),
            )

        self.assertIsInstance(client, AgentFrameworkMafProviderClient)
        self.assertEqual(client.provider_client_kind, "agent_framework_openai")
        self.assertEqual(client.chat_client.kwargs["model"], "gpt-4.1-mini")
        self.assertEqual(
            client.chat_client.kwargs["base_url"],
            "https://example.test/v1",
        )

    def test_no_model_dry_run_reports_maf_runtime_metadata(self) -> None:
        payload = run_no_model_dry_run()

        self.assertEqual(
            payload["maf_runtime"]["schema_version"],
            MAF_RUNTIME_SCHEMA_VERSION,
        )

    def test_provider_smoke_reports_skip_or_ready_without_model_call(self) -> None:
        payload = maf_provider_smoke_status()

        self.assertEqual(payload["schema_version"], MAF_PROVIDER_SMOKE_SCHEMA_VERSION)
        self.assertTrue(payload["ok"])
        self.assertIn(payload["status"], ("ready", "skipped"))
        self.assertEqual(payload["smoke_mode"], "availability_only")
        self.assertFalse(payload["model_call_allowed"])
        self.assertFalse(payload["executes_model_call"])
        if payload["status"] == "skipped":
            self.assertIn(
                payload["reason"],
                (
                    "agent_framework_package_not_installed",
                    "model_credentials_not_configured",
                    "model_identifier_not_configured",
                ),
            )

    def test_provider_smoke_accepts_opt_in_without_executing_call(self) -> None:
        with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
            payload = maf_provider_smoke_status(
                allow_model_call=True,
                env={
                    "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                    "AZURE_OPENAI_API_KEY": "secret",
                    "AZURE_OPENAI_CHAT_DEPLOYMENT": "gpt-4.1-mini",
                },
            )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["smoke_mode"], "provider_call_opt_in")
        self.assertTrue(payload["model_call_allowed"])
        self.assertFalse(payload["executes_model_call"])
        self.assertEqual(payload["call_status"], "model_call_not_requested")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")

    def test_cli_maf_provider_smoke_outputs_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["maf-provider-smoke", "--allow-model-call"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], MAF_PROVIDER_SMOKE_SCHEMA_VERSION)
        self.assertIn(payload["status"], ("ready", "skipped"))
        self.assertTrue(payload["model_call_allowed"])
        self.assertFalse(payload["executes_model_call"])
        self.assertEqual(
            {item["agent_role"] for item in payload["maf_runtime"]["agent_adapters"]},
            {"affective", "rational"},
        )


if __name__ == "__main__":
    unittest.main()
