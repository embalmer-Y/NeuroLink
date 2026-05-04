import io
import json
import sys
import unittest

from contextlib import redirect_stdout

from neurolink_core.cli import main as core_cli_main
from neurolink_core.policy import ReadOnlyToolPolicy
from neurolink_core.tools import (
    CommandExecutionResult,
    NeuroCliToolAdapter,
    STATE_SYNC_SCHEMA_VERSION,
    TOOL_MANIFEST_SCHEMA_VERSION,
    FakeUnitToolAdapter,
    SideEffectLevel,
    ToolContract,
)


class TestFakeUnitToolAdapterContract(unittest.TestCase):
    def test_read_only_policy_allows_read_only_contracts(self) -> None:
        contract = ToolContract(
            tool_name="system_state_sync",
            description="state sync",
            side_effect_level=SideEffectLevel.READ_ONLY,
        )

        decision = ReadOnlyToolPolicy().evaluate_contract(contract)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "read_only_policy_allows_tool")
        self.assertEqual(decision.side_effect_level, SideEffectLevel.READ_ONLY)

    def test_read_only_policy_blocks_destructive_contracts(self) -> None:
        contract = ToolContract(
            tool_name="app_delete",
            description="delete app artifact",
            side_effect_level=SideEffectLevel.DESTRUCTIVE,
        )

        decision = ReadOnlyToolPolicy().evaluate_contract(contract)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "side_effect_level_not_allowed_in_no_model_slice")
        self.assertEqual(decision.side_effect_level, SideEffectLevel.DESTRUCTIVE)

    def test_manifest_exposes_state_sync_contract(self) -> None:
        adapter = FakeUnitToolAdapter()

        manifest = adapter.tool_manifest()
        self.assertEqual(len(manifest), 1)
        contract = manifest[0]
        self.assertEqual(contract.tool_name, "system_state_sync")
        self.assertEqual(contract.side_effect_level, SideEffectLevel.READ_ONLY)
        self.assertEqual(contract.required_resources, ())
        self.assertFalse(contract.approval_required)
        self.assertTrue(contract.retryable)
        self.assertEqual(contract.argv_template[2:4], ("system", "state-sync"))

    def test_describe_tool_returns_none_for_unknown_tool(self) -> None:
        adapter = FakeUnitToolAdapter()

        self.assertIsNone(adapter.describe_tool("does_not_exist"))

    def test_unknown_tool_execution_returns_structured_failure(self) -> None:
        adapter = FakeUnitToolAdapter()

        result = adapter.execute("does_not_exist", {})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.payload["failure_status"], "unknown_tool")
        self.assertEqual(result.payload["failure_class"], "manifest_lookup_failed")

    def test_state_sync_execution_returns_typed_snapshot(self) -> None:
        adapter = FakeUnitToolAdapter()

        result = adapter.execute("system_state_sync", {"event_ids": ["evt-1"]})

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload["contract"]["name"], "system_state_sync")
        self.assertEqual(
            result.payload["state_sync"]["schema_version"],
            STATE_SYNC_SCHEMA_VERSION,
        )
        self.assertEqual(
            result.payload["state_sync"]["state"]["apps"]["payload"]["observed_event_ids"],
            ["evt-1"],
        )

    def test_parse_cli_manifest_payload_returns_typed_contracts(self) -> None:
        adapter = FakeUnitToolAdapter()

        contracts = adapter.parse_tool_manifest_payload(adapter.tool_manifest_payload())

        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0].tool_name, "system_state_sync")
        self.assertEqual(contracts[0].resource, "state sync aggregate")

    def test_parse_state_sync_payload_returns_typed_snapshot(self) -> None:
        adapter = FakeUnitToolAdapter()
        raw_snapshot = adapter.execute("system_state_sync", {"event_ids": ["evt-2"]}).payload[
            "state_sync"
        ]

        snapshot = adapter.parse_state_sync_payload(raw_snapshot)

        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.schema_version, STATE_SYNC_SCHEMA_VERSION)
        self.assertEqual(
            snapshot.state["apps"].payload["observed_event_ids"], ["evt-2"]
        )
        self.assertEqual(
            snapshot.recommended_next_actions,
            ("state sync is clean; read-only delegated reasoning may continue",),
        )

    def test_cli_tool_manifest_outputs_contracts(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["tool-manifest"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["schema_version"], TOOL_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(len(payload["tools"]), 1)
        self.assertEqual(payload["tools"][0]["name"], "system_state_sync")
        self.assertEqual(payload["tools"][0]["side_effect_level"], "read_only")


class TestNeuroCliToolAdapter(unittest.TestCase):
    def test_describe_tool_reads_manifest_from_cli_json(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            self.assertIn("tool-manifest", argv)
            self.assertEqual(timeout_seconds, 10)
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
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
                                "cleanup_hints": ["review active leases before side-effecting commands"],
                                "output_contract": {"format": "json", "top_level_ok": True},
                            }
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        contract = adapter.describe_tool("system_state_sync")

        self.assertIsNotNone(contract)
        self.assertEqual(contract.tool_name, "system_state_sync")
        self.assertEqual(contract.resource, "state sync aggregate")

    def test_execute_reads_state_sync_from_cli_json(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            calls.append(argv)
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
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
            self.assertIn("state-sync", argv)
            self.assertEqual(timeout_seconds, 10)
            return CommandExecutionResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "status": "ok",
                        "schema_version": STATE_SYNC_SCHEMA_VERSION,
                        "state": {
                            "device": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"network_state": "NETWORK_READY"},
                            },
                            "apps": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"app_count": 0},
                            },
                            "leases": {
                                "ok": True,
                                "status": "ok",
                                "payload": {"leases": []},
                            },
                        },
                        "recommended_next_actions": [
                            "state sync is clean; read-only delegated reasoning may continue"
                        ],
                    }
                ),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        result = adapter.execute("system_state_sync", {})

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.payload["state_sync"]["state"]["device"]["payload"]["network_state"],
            "NETWORK_READY",
        )
        self.assertEqual(len(calls), 2)

    def test_execute_returns_structured_failure_for_top_level_error(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
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
                stdout=json.dumps({"ok": False, "status": "partial_failure"}),
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        result = adapter.execute("system_state_sync", {})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.payload["failure_status"], "partial_failure")
        self.assertEqual(result.payload["failure_class"], "top_level_status_failure")

    def test_execute_preserves_payload_status_on_nonzero_exit(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            if "tool-manifest" in argv:
                return CommandExecutionResult(
                    exit_code=0,
                    stdout=json.dumps(
                        {
                            "ok": True,
                            "status": "ok",
                            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
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
                exit_code=2,
                stdout=json.dumps({"ok": False, "status": "no_reply"}),
                stderr="neuro_cli wrapper failure: no_reply",
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        result = adapter.execute("system_state_sync", {})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.payload["failure_status"], "no_reply")
        self.assertEqual(result.payload["failure_class"], "top_level_status_failure")

    def test_tool_manifest_can_run_real_wrapper_process(self) -> None:
        adapter = NeuroCliToolAdapter(python_executable=sys.executable)

        payload = adapter.tool_manifest_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["schema_version"], TOOL_MANIFEST_SCHEMA_VERSION)
        tool_names = [item["name"] for item in payload["tools"]]
        self.assertIn("system_state_sync", tool_names)

    def test_cli_tool_manifest_can_use_neuro_cli_adapter(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = core_cli_main(["tool-manifest", "--tool-adapter", "neuro-cli"])

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["schema_version"], TOOL_MANIFEST_SCHEMA_VERSION)
        tool_names = [item["name"] for item in payload["tools"]]
        self.assertIn("system_state_sync", tool_names)

    def test_real_wrapper_state_sync_returns_structured_result(self) -> None:
        adapter = NeuroCliToolAdapter(python_executable=sys.executable, timeout_seconds=1)

        result = adapter.execute("system_state_sync", {})

        self.assertIn(result.status, ("ok", "error"))
        if result.status == "ok":
            self.assertEqual(result.payload["state_sync"]["status"], "ok")
            return
        self.assertEqual(result.payload["failure_class"], "top_level_status_failure")
        self.assertTrue(result.payload["failure_status"])

    def test_collect_agent_events_reads_jsonl_rows(self) -> None:
        def runner(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
            self.assertIn("--output", argv)
            self.assertIn("jsonl", argv)
            self.assertIn("agent-events", argv)
            return CommandExecutionResult(
                exit_code=0,
                stdout='{"event_id":"evt-1","semantic_topic":"unit.callback"}\n'
                '{"event_id":"evt-2","semantic_topic":"time.tick"}\n',
            )

        adapter = NeuroCliToolAdapter(runner=runner)

        rows = adapter.collect_agent_events(max_events=2)

        self.assertEqual([row["event_id"] for row in rows], ["evt-1", "evt-2"])
        self.assertEqual(rows[0]["semantic_topic"], "unit.callback")


if __name__ == "__main__":
    unittest.main()