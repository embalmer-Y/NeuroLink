import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, cast
from unittest import mock

from neurolink_core.cli import main as core_cli_main
from neurolink_core.tools import (
    CommandExecutionResult,
    FakeUnitToolAdapter,
    NeuroCliToolAdapter,
    SideEffectLevel,
    ToolContract,
    ToolExecutionResult,
)
from neurolink_core.data import CoreDataStore
from neurolink_core.session import CoreSessionManager
from neurolink_core.workflow import (
    NoModelCoreWorkflow,
    build_user_prompt_event,
    run_no_model_dry_run,
    sample_events,
)


class TestNoModelCoreWorkflow(unittest.TestCase):
    def test_build_user_prompt_event_extracts_explicit_target_app_id(self) -> None:
        events = build_user_prompt_event("stop neuro_demo_gpio app now")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["semantic_topic"], "user.input.control.app.stop")
        self.assertEqual(events[0]["source_app"], "neuro_demo_gpio")
        self.assertEqual(events[0]["payload"]["target_app_id"], "neuro_demo_gpio")

    def test_workflow_blocks_disallowed_tool_before_adapter_execution(self) -> None:
        class DestructiveStateSyncAdapter:
            executed = False

            def describe_tool(self, tool_name: str) -> ToolContract | None:
                assert tool_name == "system_state_sync"
                return ToolContract(
                    tool_name=tool_name,
                    description="unsafe state sync placeholder",
                    side_effect_level=SideEffectLevel.DESTRUCTIVE,
                )

            def execute(self, tool_name: str, args: dict) -> None:
                del tool_name, args
                self.executed = True
                raise AssertionError("policy should block before adapter execution")

        adapter = DestructiveStateSyncAdapter()
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store, tool_adapter=adapter)

        result = workflow.run(sample_events())

        self.assertFalse(adapter.executed)
        self.assertEqual(result.tool_results[0]["status"], "blocked")
        self.assertEqual(
            result.tool_results[0]["payload"]["failure_status"],
            "policy_blocked",
        )
        self.assertEqual(data_store.count("tool_results"), 1)
        self.assertEqual(data_store.count("policy_decisions"), 1)
        decisions = data_store.get_policy_decisions(result.execution_span_id)
        self.assertFalse(decisions[0]["allowed"])
        self.assertEqual(
            decisions[0]["reason"], "side_effect_level_not_allowed_in_no_model_slice"
        )
        data_store.close()

    def test_dry_run_persists_before_reasoning_and_seals_audit(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(sample_events())
        audit_record = data_store.get_audit_record(result.audit_id)

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.session_id.startswith("session-"))
        self.assertTrue(result.delegated)
        self.assertEqual(result.final_response["speaker"], "affective")
        self.assertIn("state sync", result.final_response["text"])
        self.assertEqual(result.events_persisted, 2)
        self.assertEqual(data_store.count("perception_events"), 2)
        self.assertEqual(data_store.count("execution_spans"), 1)
        self.assertEqual(data_store.count("facts"), 3)
        self.assertEqual(data_store.count("policy_decisions"), 1)
        self.assertEqual(data_store.count("memory_candidates"), 2)
        self.assertEqual(data_store.count("long_term_memories"), 0)
        self.assertEqual(data_store.count("tool_results"), 1)
        self.assertEqual(data_store.count("approval_requests"), 0)
        self.assertEqual(data_store.count("approval_decisions"), 0)
        self.assertEqual(data_store.count("audit_records"), 1)
        decisions = data_store.get_policy_decisions(result.execution_span_id)
        self.assertTrue(decisions[0]["allowed"])
        candidates = data_store.get_memory_candidates(result.execution_span_id)
        self.assertEqual(
            {candidate["semantic_topic"] for candidate in candidates},
            {"time.tick", "unit.callback"},
        )
        self.assertLess(
            result.steps.index("database_persistence"),
            result.steps.index("affective_arbitration"),
        )
        self.assertEqual(result.steps[-1], "notification_dispatch")
        self.assertIsNotNone(audit_record)
        self.assertEqual(audit_record["session_id"], result.session_id)
        self.assertEqual(audit_record["payload"]["adapter_runtime"]["adapter_kind"], "fake")
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["snapshot_status"], "ok"
        )
        data_store.close()

    def test_workflow_tracks_prior_execution_spans_within_session(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        first = workflow.run(sample_events(), session_id="session-demo-001")
        second = workflow.run(sample_events(), session_id="session-demo-001")

        spans = data_store.get_execution_spans_for_session("session-demo-001", limit=5)
        audit_record = data_store.get_audit_record(second.audit_id)

        self.assertEqual(len(spans), 2)
        self.assertEqual(first.session_id, "session-demo-001")
        self.assertEqual(second.session_id, "session-demo-001")
        self.assertIsNotNone(audit_record)
        assert audit_record is not None
        self.assertEqual(audit_record["session_id"], "session-demo-001")
        self.assertEqual(
            audit_record["payload"]["session_context"]["session_id"],
            "session-demo-001",
        )
        self.assertEqual(
            audit_record["payload"]["session_context"]["previous_execution_spans"][0]["execution_span_id"],
            first.execution_span_id,
        )
        data_store.close()

    def test_session_manager_loads_snapshot_for_existing_session(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)
        manager = CoreSessionManager(data_store)

        first = workflow.run(sample_events(), session_id="session-manager-001")
        second = workflow.run(sample_events(), session_id="session-manager-001")
        snapshot = manager.load_snapshot(
            "session-manager-001",
            current_execution_span_id=second.execution_span_id,
            limit=5,
        )

        self.assertEqual(snapshot.session_id, "session-manager-001")
        self.assertEqual(snapshot.current_execution_span_id, second.execution_span_id)
        self.assertEqual(len(snapshot.recent_execution_spans), 2)
        self.assertIn(first.audit_id, snapshot.recent_audit_ids)
        self.assertIn(second.audit_id, snapshot.recent_audit_ids)
        data_store.close()

    def test_low_salience_tick_does_not_delegate(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(
            [
                {
                    "event_id": "evt-low-tick-001",
                    "source_kind": "clock",
                    "event_type": "time.tick",
                    "semantic_topic": "time.tick",
                    "timestamp_wall": "2026-05-04T00:00:00Z",
                    "priority": 10,
                }
            ]
        )

        self.assertFalse(result.delegated)
        self.assertEqual(result.final_response["speaker"], "affective")
        self.assertIn("no delegated action", result.final_response["text"])
        self.assertEqual(data_store.count("perception_events"), 1)
        self.assertEqual(data_store.count("execution_spans"), 1)
        self.assertEqual(data_store.count("facts"), 2)
        self.assertEqual(data_store.count("memory_candidates"), 1)
        self.assertEqual(data_store.count("policy_decisions"), 0)
        self.assertEqual(data_store.count("tool_results"), 0)
        self.assertEqual(data_store.count("audit_records"), 1)
        data_store.close()

    def test_file_backed_dry_run_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_no_model_dry_run(str(Path(tmpdir) / "core.db"))

        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["session_id"].startswith("session-"))
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertEqual(payload["db_counts"]["perception_events"], 2)
        self.assertEqual(payload["db_counts"]["execution_spans"], 1)
        self.assertEqual(payload["db_counts"]["facts"], 3)
        self.assertEqual(payload["db_counts"]["policy_decisions"], 1)
        self.assertEqual(payload["db_counts"]["memory_candidates"], 2)
        self.assertEqual(payload["db_counts"]["tool_results"], 1)
        self.assertEqual(payload["db_counts"]["audit_records"], 1)

    def test_dry_run_reports_execution_evidence_snapshot(self) -> None:
        payload = run_no_model_dry_run()

        evidence = payload["execution_evidence"]
        self.assertEqual(evidence["execution_span"]["status"], "ok")
        self.assertEqual(evidence["execution_span"]["session_id"], payload["session_id"])
        self.assertEqual(
            evidence["execution_span"]["payload"]["audit_id"],
            payload["audit_id"],
        )
        self.assertEqual(evidence["audit_record"]["audit_id"], payload["audit_id"])
        self.assertEqual(
            {fact["fact_type"] for fact in evidence["facts"]},
            {"perception_event_topic", "perception_frame"},
        )
        self.assertEqual(len(evidence["policy_decisions"]), 1)
        self.assertTrue(evidence["policy_decisions"][0]["allowed"])
        self.assertEqual(evidence["long_term_memories"], [])
        self.assertEqual(
            {candidate["semantic_topic"] for candidate in evidence["memory_candidates"]},
            {"time.tick", "unit.callback"},
        )

    def test_local_memory_backend_commits_long_term_memories(self) -> None:
        payload = run_no_model_dry_run(memory_backend="local")

        self.assertEqual(payload["db_counts"]["long_term_memories"], 2)
        self.assertEqual(len(payload["execution_evidence"]["long_term_memories"]), 2)
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["committed_memory_count"],
            2,
        )

    def test_local_memory_backend_reuses_prior_memories_on_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")
            first = run_no_model_dry_run(
                db_path,
                session_id="memory-local-001",
                memory_backend="local",
            )
            second = run_no_model_dry_run(
                db_path,
                session_id="memory-local-001",
                memory_backend="local",
            )

        self.assertEqual(first["db_counts"]["long_term_memories"], 2)
        self.assertEqual(second["db_counts"]["long_term_memories"], 4)
        self.assertGreater(
            second["execution_evidence"]["audit_record"]["payload"]["session_context"]["memory_lookup_count"],
            0,
        )

    def test_cli_no_model_dry_run_outputs_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["no-model-dry-run"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["session_id"].startswith("session-"))
        self.assertTrue(payload["delegated"])
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertEqual(payload["db_counts"]["execution_spans"], 1)
        self.assertEqual(payload["db_counts"]["policy_decisions"], 1)
        self.assertEqual(payload["db_counts"]["audit_records"], 1)
        self.assertIn("execution_evidence", payload)
        self.assertEqual(payload["execution_evidence"]["execution_span"]["status"], "ok")

    def test_cli_no_model_dry_run_can_use_provider_availability_mode(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--maf-provider-mode",
                    "provider_available_no_call",
                    "--session-id",
                    "session-cli-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["session_id"], "session-cli-001")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "provider_available_no_call")
        self.assertEqual(payload["session"]["session_id"], "session-cli-001")
        self.assertEqual(len(payload["session"]["recent_execution_spans"]), 1)

    def test_cli_no_model_dry_run_rejects_real_provider_without_allow_flag(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--maf-provider-mode",
                    "real_provider",
                ]
            )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["failure_status"], "real_provider_mode_requires_allow_model_call")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")

    def test_cli_agent_run_can_use_real_provider_with_injected_default_factory(self) -> None:
        class FakeProviderClient:
            provider_client_kind = "test_client"

            def decide(self, frame, memory_items, profile):
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 88,
                }

            def plan(self, decision, frame, profile, available_tools, session_context):
                del decision, frame, profile
                self.available_tools = available_tools
                self.session_context = session_context
                return {
                    "tool_name": "system_query_device",
                    "args": {"source": "real-provider"},
                    "reason": "real_provider_rational_plan",
                }

        out = io.StringIO()
        env = {
            "OPENAI_API_KEY": "secret",
            "OPENAI_MODEL": "gpt-4.1-mini",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                with mock.patch(
                    "neurolink_core.workflow.build_default_maf_provider_client",
                    return_value=FakeProviderClient(),
                ):
                    with redirect_stdout(out):
                        code = core_cli_main(
                            [
                                "agent-run",
                                "--input-text",
                                "check current device status",
                                "--maf-provider-mode",
                                "real_provider",
                                "--allow-model-call",
                                "--session-id",
                                "agent-run-real-provider-001",
                            ]
                        )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "agent-run")
        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_device")
        self.assertEqual(payload["final_response"]["salience"], 88)
        self.assertEqual(
            {item["provider_client_kind"] for item in payload["maf_runtime"]["agent_adapters"]},
            {"test_client"},
        )

    def test_workflow_rejects_real_provider_plan_for_unknown_manifest_tool(self) -> None:
        class FakeProviderClient:
            provider_client_kind = "test_client"

            def decide(self, frame, memory_items, profile):
                del frame, memory_items, profile
                return {
                    "delegated": True,
                    "reason": "real_provider_affective_decision",
                    "salience": 93,
                }

            def plan(self, decision, frame, profile, available_tools, session_context):
                self.available_tools = available_tools
                self.session_context = session_context
                del decision, frame, profile
                return {
                    "tool_name": "system_unknown_write",
                    "args": {"source": "real-provider"},
                    "reason": "hallucinated_tool_from_provider",
                }

        with mock.patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "secret", "OPENAI_MODEL": "gpt-4.1-mini"},
            clear=False,
        ):
            with mock.patch("neurolink_core.maf.find_spec", return_value=object()):
                payload = run_no_model_dry_run(
                    maf_provider_mode="real_provider",
                    allow_model_call=True,
                    provider_client=FakeProviderClient(),
                )

        self.assertEqual(payload["maf_runtime"]["provider_mode"], "real_provider")
        self.assertEqual(payload["tool_results"][0]["status"], "error")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_status"],
            "unknown_tool",
        )
        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_class"],
            "manifest_lookup_failed",
        )
        self.assertGreater(
            len(payload["tool_results"][0]["payload"]["available_tools"]),
            0,
        )
        self.assertIn(
            "available_tools",
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"],
        )

    def test_cli_no_model_dry_run_can_use_local_memory_backend(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--memory-backend",
                    "local",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["db_counts"]["long_term_memories"], 2)
        self.assertEqual(
            payload["execution_evidence"]["audit_record"]["payload"]["session_context"]["committed_memory_count"],
            2,
        )

    def test_cli_session_inspect_reports_existing_session_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            first_out = io.StringIO()
            with redirect_stdout(first_out):
                first_code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--db",
                        db_path,
                        "--session-id",
                        "session-cli-inspect-001",
                    ]
                )

            second_out = io.StringIO()
            with redirect_stdout(second_out):
                second_code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--db",
                        db_path,
                        "--session-id",
                        "session-cli-inspect-001",
                    ]
                )

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "session-inspect",
                        "--db",
                        db_path,
                        "--session-id",
                        "session-cli-inspect-001",
                    ]
                )

        self.assertEqual(first_code, 0)
        self.assertEqual(second_code, 0)
        self.assertEqual(inspect_code, 0)
        snapshot = json.loads(inspect_out.getvalue())
        self.assertEqual(snapshot["session_id"], "session-cli-inspect-001")
        self.assertEqual(len(snapshot["recent_execution_spans"]), 2)
        self.assertEqual(len(snapshot["recent_audit_ids"]), 2)

    def test_cli_agent_run_accepts_input_text_and_returns_final_response(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "please check current status",
                    "--session-id",
                    "agent-run-001",
                    "--memory-backend",
                    "local",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["command"], "agent-run")
        self.assertEqual(payload["session_id"], "agent-run-001")
        self.assertEqual(payload["final_response"]["speaker"], "affective")
        self.assertTrue(payload["final_response"]["delegated"])
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_device")
        self.assertIn("query device", payload["final_response"]["text"])

    def test_cli_agent_run_routes_user_query_to_apps_tool(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "show current apps on the unit",
                    "--session-id",
                    "agent-run-apps-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_query_apps")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["result"]["replies"][0]["payload"]["status"],
            "ok",
        )

    def test_cli_agent_run_routes_restart_request_to_pending_approval(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "agent-run",
                    "--input-text",
                    "restart the app now",
                    "--session-id",
                    "agent-run-restart-001",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_restart_app")
        self.assertEqual(payload["tool_results"][0]["status"], "pending_approval")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["failure_class"],
            "approval_gate_pending",
        )
        self.assertEqual(
            payload["tool_results"][0]["payload"]["approval_request"]["tool_name"],
            "system_restart_app",
        )
        self.assertIn(
            "approval_request_id",
            payload["tool_results"][0]["payload"]["approval_request"],
        )
        self.assertEqual(len(payload["session"]["pending_approval_requests"]), 1)
        self.assertIn("waiting for explicit approval", payload["final_response"]["text"])

    def test_cli_agent_run_routes_other_app_control_requests_to_pending_approval(self) -> None:
        for input_text, expected_tool_name in (
            ("start the app now", "system_start_app"),
            ("stop the app now", "system_stop_app"),
            ("unload the app now", "system_unload_app"),
        ):
            with self.subTest(input_text=input_text):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = core_cli_main(
                        [
                            "agent-run",
                            "--input-text",
                            input_text,
                            "--session-id",
                            f"agent-run-{expected_tool_name}",
                        ]
                    )

                self.assertEqual(code, 0)
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["tool_results"][0]["tool_name"], expected_tool_name)
                self.assertEqual(payload["tool_results"][0]["status"], "pending_approval")
                self.assertEqual(
                    payload["tool_results"][0]["payload"]["approval_request"]["tool_name"],
                    expected_tool_name,
                )
                self.assertEqual(len(payload["session"]["pending_approval_requests"]), 1)

    def test_cli_approval_inspect_and_approve_is_blocked_when_required_resources_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "approval-inspect",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                    ]
                )

            approve_out = io.StringIO()
            with redirect_stdout(approve_out):
                approve_code = core_cli_main(
                    [
                        "approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "approve",
                    ]
                )

            session_out = io.StringIO()
            with redirect_stdout(session_out):
                session_code = core_cli_main(
                    [
                        "session-inspect",
                        "--db",
                        db_path,
                        "--session-id",
                        "approval-session-001",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)
        self.assertEqual(session_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertEqual(inspect_payload["approval_request"]["status"], "pending")
        self.assertIsNotNone(
            inspect_payload["approval_context"]["source_execution_evidence"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["required_resources"],
            ["app_control_lease"],
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["missing_required_resources"],
            ["app_control_lease"],
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["lease_observation"]["status"],
            "ok",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["state_sync_observation"]["status"],
            "ok",
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertFalse(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "blocked_resource_gate")
        self.assertEqual(
            approve_payload["failure_status"],
            "missing_required_resources",
        )
        self.assertIsNone(approve_payload["resumed_execution"])
        self.assertEqual(approve_payload["approval_request"]["status"], "pending")
        self.assertIsNotNone(
            approve_payload["approval_context"]["source_execution_evidence"]
        )
        self.assertIsNone(
            approve_payload["approval_context"]["resumed_execution_evidence"]
        )
        self.assertEqual(
            approve_payload["approval_context"]["source_execution_evidence"]["policy_decisions"][0]["tool_name"],
            "system_restart_app",
        )
        self.assertEqual(
            approve_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"],
            False,
        )

        session_payload = json.loads(session_out.getvalue())
        self.assertEqual(session_payload["session_id"], "approval-session-001")
        self.assertEqual(len(session_payload["pending_approval_requests"]), 1)

    def test_cli_approval_inspect_and_approve_resume_execution_when_resources_are_satisfied(self) -> None:
        class LeaseSatisfiedAdapter(FakeUnitToolAdapter):
            def execute(self, tool_name: str, args: dict[str, object]) -> ToolExecutionResult:
                if tool_name == "system_query_leases":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-lease-satisfied-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-lease-001"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "resource": "app/neuro_demo_gpio/control",
                                                    "lease_id": "lease-gpio-001",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-app-satisfied-001",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-app-001"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "app_count": 1,
                                            "apps": [{"app_id": "neuro_demo_gpio"}],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                return super().execute(tool_name, cast(dict[str, Any], args))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-satisfied-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertTrue(
            inspect_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["missing_required_resources"],
            [],
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertIsNotNone(approve_payload["resumed_execution"])
        assert approve_payload["resumed_execution"] is not None
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["tool_name"],
            "system_restart_app",
        )
        self.assertEqual(
            approve_payload["approval_context"]["operator_requirements"]["missing_required_resources"],
            [],
        )

    def test_cli_approval_decision_resume_execution_uses_real_neuro_cli_restart_path(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            calls.append(argv)
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_query_apps",
                                    "description": "apps query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "apps",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_query_leases",
                                    "description": "leases query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "leases",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "lease query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_restart_app",
                                    "description": "restart app",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "app",
                                        "stop",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app control plane",
                                    "required_arguments": ["--node", "--app-id", "--lease-id"],
                                    "side_effect_level": "approval_required",
                                    "lease_requirements": ["app_control_lease"],
                                    "timeout_seconds": 15,
                                    "retryable": False,
                                    "approval_required": True,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                            ],
                        }
                    ),
                )
            if "query" in argv and "apps" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "app_count": 1,
                                        "apps": [{"app_id": "neuro_demo_gpio"}],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "query" in argv and "leases" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "leases": [
                                            {
                                                "resource": "app/neuro_demo_gpio/control",
                                                "lease_id": "lease-gpio-approve-001",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "system" in argv and "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"ok": True, "status": "ok", "payload": {"app_count": 1}},
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": ["state sync is clean; delegated reasoning may continue"],
                        }
                    ),
                )
            if "app" in argv and "stop" in argv:
                self.assertIn("--app-id", argv)
                self.assertIn("neuro_demo_gpio", argv)
                self.assertIn("--lease-id", argv)
                self.assertIn("lease-gpio-approve-001", argv)
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {"ok": True, "status": "ok", "replies": [{"ok": True, "payload": {"status": "ok", "app_id": "neuro_demo_gpio"}}]}
                    ),
                )
            self.assertIn("app", argv)
            self.assertIn("start", argv)
            self.assertIn("--app-id", argv)
            self.assertIn("neuro_demo_gpio", argv)
            self.assertIn("--lease-id", argv)
            self.assertIn("lease-gpio-approve-001", argv)
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {"ok": True, "status": "ok", "replies": [{"ok": True, "payload": {"status": "ok", "app_id": "neuro_demo_gpio"}}]}
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-real-restart-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertTrue(
            inspect_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["target_app_id"],
            "neuro_demo_gpio",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["matching_lease_ids"],
            ["lease-gpio-approve-001"],
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["app_id"],
            "neuro_demo_gpio",
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["lease_id"],
            "lease-gpio-approve-001",
        )

        query_apps_calls = [argv for argv in calls if "query" in argv and "apps" in argv]
        query_lease_calls = [argv for argv in calls if "query" in argv and "leases" in argv]
        self.assertEqual(len(query_apps_calls), 2)
        self.assertEqual(len(query_lease_calls), 2)

    def test_cli_approval_decision_resume_execution_uses_real_neuro_cli_stop_path(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            del timeout_seconds
            calls.append(argv)
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_query_apps",
                                    "description": "apps query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "apps",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_query_leases",
                                    "description": "leases query",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "query",
                                        "leases",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "lease query plane",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                                {
                                    "name": "system_stop_app",
                                    "description": "stop app",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "app",
                                        "stop",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "app control plane",
                                    "required_arguments": ["--node", "--app-id", "--lease-id"],
                                    "side_effect_level": "approval_required",
                                    "lease_requirements": ["app_control_lease"],
                                    "timeout_seconds": 15,
                                    "retryable": False,
                                    "approval_required": True,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                },
                            ],
                        }
                    ),
                )
            if "query" in argv and "apps" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "app_count": 2,
                                        "apps": [
                                            {"app_id": "neuro_demo_gpio"},
                                            {"app_id": "neuro_demo_spi"},
                                        ],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "query" in argv and "leases" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "replies": [
                                {
                                    "ok": True,
                                    "payload": {
                                        "status": "ok",
                                        "leases": [
                                            {
                                                "resource": "app/neuro_demo_spi/control",
                                                "lease_id": "lease-spi-stop-001",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ),
                )
            if "system" in argv and "state-sync" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-state-sync-v1",
                            "state": {
                                "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                                "apps": {"ok": True, "status": "ok", "payload": {"app_count": 1}},
                                "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                            },
                            "recommended_next_actions": ["state sync is clean; delegated reasoning may continue"],
                        }
                    ),
                )
            self.assertIn("app", argv)
            self.assertIn("stop", argv)
            self.assertIn("--app-id", argv)
            self.assertIn("neuro_demo_spi", argv)
            self.assertIn("--lease-id", argv)
            self.assertIn("lease-spi-stop-001", argv)
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {"ok": True, "status": "ok", "replies": [{"ok": True, "payload": {"status": "ok", "app_id": "neuro_demo_spi"}}]}
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "stop neuro_demo_spi app now",
                        "--session-id",
                        "approval-session-real-stop-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            inspect_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(inspect_out):
                    inspect_code = core_cli_main(
                        [
                            "approval-inspect",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            approve_out = io.StringIO()
            with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
                with redirect_stdout(approve_out):
                    approve_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(inspect_code, 0)
        self.assertEqual(approve_code, 0)

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertTrue(
            inspect_payload["approval_context"]["operator_requirements"]["resource_requirements_satisfied"]
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["target_app_id"],
            "neuro_demo_spi",
        )
        self.assertEqual(
            inspect_payload["approval_context"]["operator_requirements"]["matching_lease_ids"],
            ["lease-spi-stop-001"],
        )

        approve_payload = json.loads(approve_out.getvalue())
        self.assertTrue(approve_payload["ok"])
        self.assertEqual(approve_payload["status"], "approved")
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["tool_name"],
            "system_stop_app",
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["app_id"],
            "neuro_demo_spi",
        )
        self.assertEqual(
            approve_payload["resumed_execution"]["tool_result"]["payload"]["resolved_args"]["lease_id"],
            "lease-spi-stop-001",
        )

        stop_calls = [argv for argv in calls if "app" in argv and "stop" in argv]
        start_calls = [argv for argv in calls if "app" in argv and "start" in argv]
        self.assertEqual(len(stop_calls), 1)
        self.assertEqual(len(start_calls), 0)

    def test_cli_approval_decision_can_deny_without_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-deny-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            deny_out = io.StringIO()
            with redirect_stdout(deny_out):
                deny_code = core_cli_main(
                    [
                        "approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "deny",
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(deny_code, 0)
        deny_payload = json.loads(deny_out.getvalue())
        self.assertEqual(deny_payload["status"], "denied")
        self.assertIsNone(deny_payload["resumed_execution"])

    def test_cli_approval_decision_can_expire_without_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-expire-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            expire_out = io.StringIO()
            with redirect_stdout(expire_out):
                expire_code = core_cli_main(
                    [
                        "approval-decision",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                        "--decision",
                        "expire",
                    ]
                )

            inspect_out = io.StringIO()
            with redirect_stdout(inspect_out):
                inspect_code = core_cli_main(
                    [
                        "approval-inspect",
                        "--db",
                        db_path,
                        "--approval-request-id",
                        approval_request_id,
                    ]
                )

        self.assertEqual(run_code, 0)
        self.assertEqual(expire_code, 0)
        self.assertEqual(inspect_code, 0)

        expire_payload = json.loads(expire_out.getvalue())
        self.assertEqual(expire_payload["status"], "expired")
        self.assertIsNone(expire_payload["resumed_execution"])

        inspect_payload = json.loads(inspect_out.getvalue())
        self.assertEqual(inspect_payload["approval_request"]["status"], "expired")
        self.assertIsNone(inspect_payload["approval_context"]["resumed_execution_evidence"])

    def test_cli_approval_decision_rejects_replay_after_terminal_status(self) -> None:
        class LeaseSatisfiedAdapter(FakeUnitToolAdapter):
            def execute(self, tool_name: str, args: dict[str, object]) -> ToolExecutionResult:
                if tool_name == "system_query_leases":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-lease-satisfied-002",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-lease-002"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "leases": [
                                                {
                                                    "resource": "app/neuro_demo_gpio/control",
                                                    "lease_id": "lease-gpio-002",
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                if tool_name == "system_query_apps":
                    contract = self.describe_tool(tool_name)
                    assert contract is not None
                    return ToolExecutionResult(
                        tool_result_id="tool-app-satisfied-002",
                        tool_name=tool_name,
                        status="ok",
                        payload={
                            "contract": contract.to_dict(),
                            "mode": "fake_no_model",
                            "side_effect_level": contract.side_effect_level.value,
                            "result": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"request_id": "req-app-002"},
                                "replies": [
                                    {
                                        "ok": True,
                                        "payload": {
                                            "status": "ok",
                                            "app_count": 1,
                                            "apps": [{"app_id": "neuro_demo_gpio"}],
                                        },
                                    }
                                ],
                            },
                        },
                    )
                return super().execute(tool_name, cast(dict[str, Any], args))

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "core.db")

            run_out = io.StringIO()
            with redirect_stdout(run_out):
                run_code = core_cli_main(
                    [
                        "agent-run",
                        "--db",
                        db_path,
                        "--input-text",
                        "restart the app now",
                        "--session-id",
                        "approval-session-replay-001",
                    ]
                )

            run_payload = json.loads(run_out.getvalue())
            approval_request_id = run_payload["tool_results"][0]["payload"]["approval_request"][
                "approval_request_id"
            ]

            first_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(first_out):
                    first_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

            replay_out = io.StringIO()
            with mock.patch(
                "neurolink_core.cli.NeuroCliToolAdapter",
                return_value=LeaseSatisfiedAdapter(),
            ):
                with redirect_stdout(replay_out):
                    replay_code = core_cli_main(
                        [
                            "approval-decision",
                            "--db",
                            db_path,
                            "--approval-request-id",
                            approval_request_id,
                            "--decision",
                            "approve",
                            "--tool-adapter",
                            "neuro-cli",
                        ]
                    )

        self.assertEqual(run_code, 0)
        self.assertEqual(first_code, 0)
        self.assertEqual(replay_code, 2)
        replay_payload = json.loads(replay_out.getvalue())
        self.assertEqual(
            replay_payload["failure_status"],
            "approval_request_not_pending_approved",
        )

    def test_cli_no_model_dry_run_can_use_database_event_slice(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(
                [
                    "no-model-dry-run",
                    "--use-db-events",
                    "--min-priority",
                    "50",
                    "--topic",
                    "unit.callback",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["query"]["use_db_events"])
        self.assertEqual(payload["query"]["min_priority"], 50)
        self.assertEqual(payload["query"]["topic"], "unit.callback")
        self.assertIn("database_query", payload["steps"])
        self.assertIn("frame_build_from_db", payload["steps"])

    def test_cli_no_model_dry_run_can_use_neuro_cli_adapter(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                        "--output",
                                        "json",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                    "lease_requirements": [],
                                    "timeout_seconds": 10,
                                    "retryable": True,
                                    "approval_required": False,
                                    "cleanup_hints": [],
                                    "output_contract": {"format": "json", "top_level_ok": True},
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": "1.2.0-state-sync-v1",
                        "state": {
                            "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                            "apps": {"ok": True, "status": "ok", "payload": {"app_count": 0}},
                            "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(["no-model-dry-run", "--tool-adapter", "neuro-cli"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_state_sync")
        self.assertEqual(
            payload["tool_results"][0]["payload"]["state_sync"]["status"], "ok"
        )

    def test_cli_no_model_dry_run_can_ingest_agent_events(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "agent-events" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "event_id": "evt-agent-callback-001",
                            "source_kind": "unit_app",
                            "source_node": "unit-01",
                            "source_app": "neuro_demo_gpio",
                            "event_type": "callback",
                            "semantic_topic": "unit.callback",
                            "timestamp_wall": "2026-05-04T00:00:00Z",
                            "priority": 80,
                            "payload": {"callback_enabled": True},
                        }
                    )
                    + "\n"
                    + json.dumps(
                        {
                            "event_id": "evt-agent-tick-001",
                            "source_kind": "clock",
                            "event_type": "time.tick",
                            "semantic_topic": "time.tick",
                            "timestamp_wall": "2026-05-04T00:00:01Z",
                            "priority": 10,
                            "payload": {"period_ms": 1000},
                        }
                    )
                    + "\n",
                )
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": ["python", "wrapper.py", "system", "state-sync"],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": "1.2.0-state-sync-v1",
                        "state": {
                            "device": {"ok": True, "status": "ok", "payload": {"network_state": "NETWORK_READY"}},
                            "apps": {"ok": True, "status": "ok", "payload": {"app_count": 0}},
                            "leases": {"ok": True, "status": "ok", "payload": {"leases": []}},
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)
        out = io.StringIO()
        with mock.patch("neurolink_core.cli.NeuroCliToolAdapter", return_value=adapter):
            with redirect_stdout(out):
                code = core_cli_main(
                    [
                        "no-model-dry-run",
                        "--tool-adapter",
                        "neuro-cli",
                        "--event-source",
                        "neuro-cli-agent-events",
                        "--max-events",
                        "2",
                    ]
                )

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["event_source"], "provided")
        self.assertEqual(payload["events_persisted"], 2)
        self.assertEqual(payload["db_counts"]["perception_events"], 2)
        self.assertEqual(payload["tool_results"][0]["tool_name"], "system_state_sync")

    def test_data_store_query_and_topic_index_follow_priority_and_topic_filters(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        workflow.run(sample_events())

        filtered = data_store.query_events(min_priority=50, topic="unit.callback")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["event_id"], "evt-demo-callback-001")
        self.assertEqual(data_store.get_recent_topics(limit=2), ["time.tick", "unit.callback"])

        frame = data_store.build_frame(filtered)
        self.assertEqual(frame["event_ids"], ("evt-demo-callback-001",))
        self.assertEqual(frame["highest_priority"], 80)
        self.assertEqual(frame["topics"], ("unit.callback",))
        data_store.close()

    def test_workflow_can_rebuild_frame_from_database_slice(self) -> None:
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store)

        result = workflow.run(
            sample_events(),
            use_db_events=True,
            min_priority=50,
            topic="unit.callback",
        )

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.delegated)
        self.assertIn("database_query", result.steps)
        self.assertIn("frame_build_from_db", result.steps)
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0]["tool_name"], "system_state_sync")
        self.assertEqual(
            result.tool_results[0]["payload"]["state_sync"]["status"], "ok"
        )
        data_store.close()

    def test_audit_record_preserves_state_sync_failure_summary(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": "1.2.0-tool-manifest-v1",
                            "tools": [
                                {
                                    "name": "system_state_sync",
                                    "description": "state sync",
                                    "argv_template": [
                                        "python",
                                        "neuro_cli/scripts/invoke_neuro_cli.py",
                                        "system",
                                        "state-sync",
                                    ],
                                    "resource": "state sync aggregate",
                                    "required_arguments": ["--node"],
                                    "side_effect_level": "read_only",
                                }
                            ],
                        }
                    ),
                )
            return CommandExecutionResult(
                exit_code=2,
                stdout=json.dumps(
                    {
                        "ok": False,
                        "status": "no_reply",
                        "recommended_next_actions": [
                            "rerun query device and verify router or Unit reachability before delegated control"
                        ],
                    }
                ),
                stderr="neuro_cli wrapper failure: no_reply",
            )

        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(
            data_store=data_store,
            tool_adapter=NeuroCliToolAdapter(runner=runner, source_agent="rational"),
        )

        result = workflow.run(sample_events())
        audit_record = data_store.get_audit_record(result.audit_id)

        self.assertIsNotNone(audit_record)
        self.assertEqual(result.tool_results[0]["status"], "error")
        self.assertEqual(
            audit_record["payload"]["adapter_runtime"]["adapter_kind"], "neuro-cli"
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["failure_status"], "no_reply"
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["failure_class"],
            "top_level_status_failure",
        )
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["recommended_next_actions"],
            [
                "rerun query device and verify router or Unit reachability before delegated control"
            ],
        )
        data_store.close()


if __name__ == "__main__":
    unittest.main()