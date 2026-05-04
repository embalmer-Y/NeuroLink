import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from neurolink_core.cli import main as core_cli_main
from neurolink_core.tools import (
    CommandExecutionResult,
    NeuroCliToolAdapter,
    SideEffectLevel,
    ToolContract,
)
from neurolink_core.data import CoreDataStore
from neurolink_core.workflow import NoModelCoreWorkflow, run_no_model_dry_run, sample_events


class TestNoModelCoreWorkflow(unittest.TestCase):
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
        self.assertTrue(result.delegated)
        self.assertEqual(result.events_persisted, 2)
        self.assertEqual(data_store.count("perception_events"), 2)
        self.assertEqual(data_store.count("execution_spans"), 1)
        self.assertEqual(data_store.count("facts"), 3)
        self.assertEqual(data_store.count("policy_decisions"), 1)
        self.assertEqual(data_store.count("memory_candidates"), 2)
        self.assertEqual(data_store.count("tool_results"), 1)
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
        self.assertEqual(audit_record["payload"]["adapter_runtime"]["adapter_kind"], "fake")
        self.assertEqual(
            audit_record["payload"]["state_sync_summary"]["snapshot_status"], "ok"
        )
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
        self.assertEqual(
            {candidate["semantic_topic"] for candidate in evidence["memory_candidates"]},
            {"time.tick", "unit.callback"},
        )

    def test_cli_no_model_dry_run_outputs_json(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["no-model-dry-run"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["delegated"])
        self.assertEqual(payload["db_counts"]["execution_spans"], 1)
        self.assertEqual(payload["db_counts"]["policy_decisions"], 1)
        self.assertEqual(payload["db_counts"]["audit_records"], 1)
        self.assertIn("execution_evidence", payload)
        self.assertEqual(payload["execution_evidence"]["execution_span"]["status"], "ok")

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