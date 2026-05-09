# pyright: reportAttributeAccessIssue=false, reportMissingImports=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportOptionalMemberAccess=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import sys
import types
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest import mock


def _install_fake_zenoh() -> None:
    if "zenoh" in sys.modules:
        return

    fake = types.ModuleType("zenoh")

    class _Query:
        payload = None

    class _Session:
        pass

    class _Sample:
        payload = None
        key_expr = ""

    class _Config:
        pass

    fake.Query = _Query
    fake.Session = _Session
    fake.Sample = _Sample
    fake.Config = _Config

    def _open(config: object | None = None) -> None:
        del config

    def _init_log_from_env_or(level: object) -> None:
        del level

    fake.open = _open
    fake.init_log_from_env_or = _init_log_from_env_or
    sys.modules["zenoh"] = fake


_install_fake_zenoh()

THIS_DIR = Path(__file__).resolve().parent
NEURO_CLI_DIR = THIS_DIR.parent
SRC_DIR = NEURO_CLI_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import neuro_cli
import neuro_protocol
import neuro_workflow_catalog
import neuro_workflow_contracts


FIXTURES_DIR = THIS_DIR / "fixtures"


def extract_wrapper_cli_args(markdown_text: str) -> list[list[str]]:
    commands: list[list[str]] = []
    pattern = re.compile(
        r"^python\s+applocation/NeuroLink/neuro_cli/scripts/"
        r"invoke_neuro_cli\.py\s+(.+)$",
        re.MULTILINE,
    )
    for match in pattern.finditer(markdown_text):
        commands.append(shlex.split(match.group(1)))
    return commands


def extract_workflow_plan_names(markdown_text: str) -> set[str]:
    return set(re.findall(r"workflow plan ([a-z0-9-]+)", markdown_text))


class TestNeuroCliPayloadPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.base_payload = {
            "request_id": "req-1",
            "source_core": "core-a",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 5000,
        }

    def test_validate_common_payload_success(self) -> None:
        neuro_cli.validate_payload(dict(self.base_payload), "common")

    def test_validate_write_requires_idempotency(self) -> None:
        payload = dict(self.base_payload)
        payload["priority"] = 50
        with self.assertRaisesRegex(ValueError, "idempotency_key"):
            neuro_cli.validate_payload(payload, "write")

    def test_validate_protected_requires_lease_id(self) -> None:
        payload = dict(self.base_payload)
        payload["priority"] = 50
        payload["idempotency_key"] = "idem-1"
        with self.assertRaisesRegex(ValueError, "lease_id"):
            neuro_cli.validate_payload(payload, "protected")


class TestNeuroProtocolModule(unittest.TestCase):
    def test_cbor_schema_fixture_matches_protocol_constants(self) -> None:
        schema = json.loads(
            (FIXTURES_DIR / "protocol_cbor_v2_schema.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(schema["schema_version"], 2)
        self.assertEqual(schema["wire_encoding"], "cbor-v2")
        self.assertEqual(
            schema["message_kinds"], neuro_protocol.CBOR_V2_MESSAGE_KINDS
        )
        self.assertEqual(schema["keys"], neuro_protocol.CBOR_V2_KEYS)
        self.assertEqual(
            len(set(schema["message_kinds"].values())),
            len(schema["message_kinds"]),
        )
        self.assertEqual(len(set(schema["keys"].values())), len(schema["keys"]))

    def test_update_delete_route_maps_to_cbor_request_kind(self) -> None:
        self.assertEqual(
            neuro_protocol.message_kind_for_keyexpr(
                "neuro/unit-01/update/app/neuro_unit_app/delete",
                {"lease_id": "lease-1"},
            ),
            "update_delete_request",
        )

    def test_cbor_encode_matches_initial_golden_vectors(self) -> None:
        schema = json.loads(
            (FIXTURES_DIR / "protocol_cbor_v2_schema.json").read_text(
                encoding="utf-8"
            )
        )
        vectors = {item["name"]: item for item in schema["golden_vectors"]}

        envelope = neuro_protocol.encode_payload_cbor({}, "query_request")
        self.assertEqual(
            envelope.hex(),
            vectors["envelope_header.query_request"]["expected_cbor_hex"],
        )

        error_payload = {
            "status": "error",
            "request_id": "req-1",
            "node_id": "unit-01",
            "status_code": 404,
            "message": "missing",
        }
        error_reply = neuro_protocol.encode_payload_cbor(error_payload, "error_reply")
        self.assertEqual(
            error_reply.hex(),
            vectors["error_reply.not_found"]["expected_cbor_hex"],
        )

    def test_cbor_decode_maps_integer_keys_to_logical_payload(self) -> None:
        decoded = neuro_protocol.decode_payload_cbor(
            bytes.fromhex(
                "a70002011402656572726f7203657265712d310467756e69742d30311419019415676d697373696e67"
            )
        )

        self.assertEqual(
            decoded,
            {
                "schema_version": 2,
                "message_kind": "error_reply",
                "status": "error",
                "request_id": "req-1",
                "node_id": "unit-01",
                "status_code": 404,
                "message": "missing",
            },
        )

    def test_parse_reply_decodes_cbor_payload(self) -> None:
        class Payload:
            def to_bytes(self) -> bytes:
                return bytes.fromhex("a200020101")

            def to_string(self) -> str:
                raise AssertionError("CBOR reply should not be parsed as text")

        reply = Namespace(
            ok=Namespace(payload=Payload(), key_expr="neuro/unit-01/query/device")
        )

        parsed = neuro_protocol.parse_reply(reply)

        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["payload"]["schema_version"], 2)
        self.assertEqual(parsed["payload"]["message_kind"], "query_request")

    def test_parse_wire_payload_decodes_cbor_event(self) -> None:
        class Payload:
            def to_bytes(self) -> bytes:
                return neuro_protocol.encode_payload_cbor(
                    {
                        "app_id": "neuro_demo_app",
                        "event_name": "callback",
                        "invoke_count": 2,
                        "start_count": 1,
                    },
                    "callback_event",
                )

            def to_string(self) -> str:
                raise AssertionError("CBOR payload should not be parsed as text")

        parsed, encoding, payload_hex = neuro_protocol.parse_wire_payload(Payload())

        self.assertEqual(encoding, "cbor-v2")
        self.assertTrue(payload_hex)
        self.assertEqual(parsed["message_kind"], "callback_event")
        self.assertEqual(parsed["app_id"], "neuro_demo_app")
        self.assertEqual(parsed["invoke_count"], 2)

    def test_parse_wire_payload_decodes_cbor_lease_event(self) -> None:
        payload = neuro_protocol.encode_payload_cbor(
            {
                "node_id": "unit-01",
                "action": "released",
                "lease_id": "lease-1",
                "resource": "app/neuro_demo_app/control",
                "source_core": "core-cli",
                "source_agent": "rational",
                "priority": 50,
            },
            "lease_event",
        )

        parsed, encoding, _payload_hex = neuro_protocol.parse_wire_payload(payload)

        self.assertEqual(encoding, "cbor-v2")
        self.assertEqual(parsed["message_kind"], "lease_event")
        self.assertEqual(parsed["action"], "released")
        self.assertEqual(parsed["lease_id"], "lease-1")

    def test_route_builders_match_unit_contract(self) -> None:
        self.assertEqual(
            neuro_protocol.query_route("unit-01", "device"),
            "neuro/unit-01/query/device",
        )
        self.assertEqual(
            neuro_protocol.lease_route("unit-01", "acquire"),
            "neuro/unit-01/cmd/lease/acquire",
        )
        self.assertEqual(
            neuro_protocol.app_command_route("unit-01", "neuro_unit_app", "invoke"),
            "neuro/unit-01/cmd/app/neuro_unit_app/invoke",
        )
        self.assertEqual(
            neuro_protocol.update_route("unit-01", "neuro_unit_app", "activate"),
            "neuro/unit-01/update/app/neuro_unit_app/activate",
        )
        self.assertEqual(
            neuro_protocol.app_event_subscription_route("unit-01", "neuro_unit_app"),
            "neuro/unit-01/event/app/neuro_unit_app/**",
        )

    def test_payload_builders_match_protocol_contract(self) -> None:
        args = Namespace(
            request_id="req-1",
            source_core="core-cli",
            source_agent="rational",
            node="unit-01",
            timeout=10,
            priority=70,
            idempotency_key="idem-1",
            lease_id="lease-1",
            mode="on",
            trigger_every=3,
            event_name="notify",
        )

        payload = neuro_protocol.build_app_callback_config_payload(args)

        self.assertEqual(payload["request_id"], "req-1")
        self.assertEqual(payload["target_node"], "unit-01")
        self.assertEqual(payload["timeout_ms"], 10000)
        self.assertEqual(payload["priority"], 70)
        self.assertEqual(payload["idempotency_key"], "idem-1")
        self.assertEqual(payload["lease_id"], "lease-1")
        self.assertTrue(payload["callback_enabled"])
        self.assertEqual(payload["trigger_every"], 3)
        self.assertEqual(payload["event_name"], "notify")

    def test_base_write_and_protected_payload_contracts(self) -> None:
        args = Namespace(
            request_id="req-1",
            source_core="core-cli",
            source_agent="rational",
            node="unit-01",
            timeout=5,
            priority=60,
            idempotency_key="idem-1",
            lease_id="lease-1",
        )

        base_payload = neuro_protocol.base_payload(args)
        write_payload = neuro_protocol.write_payload(args)
        protected_payload = neuro_protocol.protected_write_payload(args)

        self.assertEqual(
            base_payload,
            {
                "request_id": "req-1",
                "source_core": "core-cli",
                "source_agent": "rational",
                "target_node": "unit-01",
                "timeout_ms": 5000,
            },
        )
        self.assertEqual(write_payload["priority"], 60)
        self.assertEqual(write_payload["idempotency_key"], "idem-1")
        self.assertEqual(protected_payload["lease_id"], "lease-1")

    def test_parse_reply_decodes_board_status_payload(self) -> None:
        class _Payload:
            def to_string(self) -> str:
                return '{"status":"error","status_code":409}'

        class _Ok:
            key_expr = "neuro/unit-01/cmd/app/neuro_unit_app/invoke"
            payload = _Payload()

        class _Reply:
            ok = _Ok()

        parsed = neuro_protocol.parse_reply(_Reply())

        self.assertTrue(parsed["ok"])
        self.assertEqual(
            parsed["keyexpr"], "neuro/unit-01/cmd/app/neuro_unit_app/invoke"
        )
        self.assertEqual(parsed["payload"], {"status": "error", "status_code": 409})

    def test_parse_reply_classifies_unreadable_ok_payload(self) -> None:
        class _Payload:
            def to_bytes(self) -> bytes:
                return b"\xa1\x01"

            def to_string(self) -> str:
                raise AssertionError("CBOR payload should not fall back to text")

        class _Ok:
            key_expr = "neuro/unit-01/query/device"
            payload = _Payload()

        class _Reply:
            ok = _Ok()

        parsed = neuro_protocol.parse_reply(_Reply())

        self.assertFalse(parsed["ok"])
        self.assertEqual(parsed["status"], "parse_failed")
        self.assertEqual(parsed["keyexpr"], "neuro/unit-01/query/device")
        self.assertIn("truncated", parsed["error"])


class TestNeuroCliParserAndPlaceholders(unittest.TestCase):
    def test_workflow_catalog_module_owns_exported_workflow_tables(self) -> None:
        self.assertIs(neuro_cli.WORKFLOW_PLANS, neuro_workflow_catalog.WORKFLOW_PLANS)
        self.assertIs(
            neuro_cli.WORKFLOW_METADATA_DEFAULTS,
            neuro_workflow_catalog.WORKFLOW_METADATA_DEFAULTS,
        )
        self.assertIs(
            neuro_cli.WORKFLOW_PLAN_METADATA,
            neuro_workflow_catalog.WORKFLOW_PLAN_METADATA,
        )
        self.assertIn("preflight", neuro_workflow_catalog.WORKFLOW_PLANS)

    def test_workflow_contract_module_builds_surface_from_explicit_inputs(self) -> None:
        payload = neuro_workflow_contracts.build_workflow_surface(
            {
                "sample-plan": {
                    "category": "verification",
                    "description": "sample workflow",
                    "commands": ["echo sample"],
                    "artifacts": [],
                }
            },
            neuro_cli.WORKFLOW_METADATA_DEFAULTS,
            {},
            neuro_cli.WORKFLOW_PLAN_SCHEMA_VERSION,
        )

        self.assertEqual(payload["schema_version"], neuro_cli.WORKFLOW_PLAN_SCHEMA_VERSION)
        self.assertEqual(payload["categories"], ["verification"])
        self.assertEqual(payload["plans"][0]["workflow"], "sample-plan")
        self.assertEqual(payload["plans"][0]["plan_command"], "workflow plan sample-plan")

    def test_parser_parses_grouped_prepare_path(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            ["deploy", "prepare", "--app-id", "neuro_demo_app", "--file", "build/neurolink_unit/llext/neuro_demo_app.llext"]
        )
        self.assertIs(args.handler, neuro_cli.handle_update)
        self.assertEqual(args.stage, "prepare")
        self.assertEqual(args.app_id, "neuro_demo_app")
        self.assertEqual(args.file, "build/neurolink_unit/llext/neuro_demo_app.llext")

    def test_parser_parses_grouped_rollback_path(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            [
                "deploy",
                "rollback",
                "--app-id",
                "neuro_demo_app",
                "--lease-id",
                "lease-1",
                "--reason",
                "operator requested",
            ]
        )
        self.assertIs(args.handler, neuro_cli.handle_update)
        self.assertEqual(args.stage, "rollback")
        self.assertEqual(args.lease_id, "lease-1")
        self.assertEqual(args.reason, "operator requested")

    def test_parser_accepts_lease_release_resource_compatibility_arg(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            ["lease", "release", "--lease-id", "lease-1", "--resource", "app/neuro_demo_app/control"]
        )
        self.assertIs(args.handler, neuro_cli.handle_lease_release)
        self.assertEqual(args.lease_id, "lease-1")
        self.assertEqual(args.resource, "app/neuro_demo_app/control")

    def test_parser_parses_placeholder_recovery(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["recovery"])
        self.assertIs(args.handler, neuro_cli.handle_placeholder)
        self.assertEqual(args.placeholder_capability, "recovery")
        self.assertEqual(args.placeholder_name, "recovery")

    def test_emit_placeholder_json_output(self) -> None:
        args = Namespace(output="json")
        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.emit_placeholder(args, "gateway", "gateway")
        self.assertEqual(code, 3)

        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "not_implemented")
        self.assertEqual(payload["capability"], "gateway")

    def test_capabilities_json_includes_protocol_and_agent_skill(self) -> None:
        args = Namespace(output="json")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_capabilities(None, args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["release_target"], "1.2.6")
        self.assertEqual(payload["protocol"]["version"], "2.0")
        self.assertEqual(payload["protocol"]["wire_encoding"], "cbor-v2")
        self.assertEqual(payload["protocol"]["supported_wire_encodings"], ["cbor-v2"])
        self.assertEqual(payload["protocol"]["planned_wire_encodings"], [])
        self.assertTrue(payload["protocol"]["cbor_v2_enabled"])
        self.assertTrue(payload["agent_skill"]["structured_stdout"])
        self.assertEqual(payload["agent_skill"]["name"], "neuro-cli")
        self.assertTrue(payload["agent_skill"]["canonical_exists"])
        self.assertTrue(payload["agent_skill"]["project_shared_exists"])
        self.assertTrue(payload["agent_skill"]["wrapper_exists"])
        self.assertEqual(
            Path(payload["agent_skill"]["canonical_path"]).as_posix().split(
                "applocation/NeuroLink/", 1
            )[-1],
            "neuro_cli/skill/SKILL.md",
        )
        self.assertEqual(
            Path(payload["agent_skill"]["project_shared_path"]).as_posix().split(
                "applocation/NeuroLink/", 1
            )[-1],
            ".github/skills/neuro-cli/SKILL.md",
        )
        self.assertEqual(
            Path(payload["agent_skill"]["discovery_adapter_path"]).as_posix().split(
                "applocation/NeuroLink/", 1
            )[-1],
            ".github/skills/neuro-cli/SKILL.md",
        )
        self.assertEqual(payload["agent_skill"]["source_of_truth"], "canonical")
        self.assertEqual(
            payload["agent_skill"]["callback_handler_execution"],
            "explicit_audited_runner",
        )
        self.assertIn("agent_runtime", payload)
        self.assertEqual(
            payload["agent_runtime"]["schema_version"],
            neuro_cli.AGENT_RUNTIME_SCHEMA_VERSION,
        )
        self.assertTrue(payload["agent_runtime"]["supports"]["tool_manifest"])
        self.assertTrue(payload["agent_runtime"]["supports"]["state_sync"])
        self.assertTrue(payload["agent_runtime"]["supports"]["agent_events_jsonl"])
        self.assertEqual(
            payload["agent_runtime"]["agent_events_mode"], "bounded_equivalent"
        )
        self.assertIn("capabilities", payload)
        workflow_surface = payload["workflow_surface"]
        self.assertEqual(
            workflow_surface["schema_version"],
            neuro_cli.WORKFLOW_PLAN_SCHEMA_VERSION,
        )
        self.assertEqual(workflow_surface["plan_command"], "workflow plan <name>")
        workflow_names = {item["workflow"] for item in workflow_surface["plans"]}
        self.assertEqual(workflow_names, set(neuro_cli.WORKFLOW_PLANS.keys()))
        self.assertIn("setup", workflow_surface["categories"])
        self.assertIn("discovery", workflow_surface["categories"])
        self.assertIn("control", workflow_surface["categories"])
        destructive = {
            item["workflow"]
            for item in workflow_surface["plans"]
            if item["destructive"]
        }
        self.assertIn("control-deploy", destructive)
        self.assertIn("control-callback", destructive)

    def test_parser_parses_system_init_without_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "system", "init"])

        self.assertIs(args.handler, neuro_cli.handle_init)
        self.assertFalse(args.requires_session)

    def test_parser_parses_system_tool_manifest_without_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "system", "tool-manifest"])

        self.assertIs(args.handler, neuro_cli.handle_tool_manifest)
        self.assertFalse(args.requires_session)

    def test_parser_parses_system_state_sync_with_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "system", "state-sync"])

        self.assertIs(args.handler, neuro_cli.handle_state_sync)
        self.assertTrue(getattr(args, "requires_session", True))

    def test_parser_parses_monitor_agent_events_without_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "jsonl", "monitor", "agent-events"])

        self.assertIs(args.handler, neuro_cli.handle_agent_events)
        self.assertFalse(args.requires_session)

    def test_agent_events_outputs_bounded_jsonl_rows(self) -> None:
        args = Namespace(output="jsonl", node="unit-01", max_events=1)

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_agent_events(None, args)

        self.assertEqual(code, 0)
        lines = [line for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertEqual(
            payload["schema_version"], neuro_cli.AGENT_EVENTS_SCHEMA_VERSION
        )
        self.assertEqual(payload["mode"], "bounded_equivalent")
        self.assertFalse(payload["live_subscription"])
        self.assertEqual(payload["semantic_topic"], "unit.callback")
        self.assertEqual(payload["dedupe_key"], "demo-callback-001")
        self.assertEqual(payload["causality_id"], "demo-callback-001")
        self.assertEqual(
            payload["raw_payload_ref"],
            "bounded_equivalent://agent-events/demo-callback-001",
        )
        self.assertEqual(payload["payload_encoding"], "json")
        self.assertIn("read_only_ingress", payload["policy_tags"])

    def test_tool_manifest_outputs_agent_facing_contracts(self) -> None:
        args = Namespace(output="json")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_tool_manifest(None, args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["schema_version"], neuro_cli.TOOL_MANIFEST_SCHEMA_VERSION
        )
        names = {item["name"] for item in payload["tools"]}
        self.assertIn("system_state_sync", names)
        self.assertIn("system_query_device", names)
        self.assertIn("system_restart_app", names)
        self.assertIn("system_start_app", names)
        self.assertIn("system_stop_app", names)
        self.assertIn("system_unload_app", names)

    def test_state_sync_aggregates_query_contracts(self) -> None:
        args = Namespace(
            output="json",
            node="unit-01",
            source_core="core-cli",
            source_agent="rational",
            timeout=10.0,
            request_id="",
            query_retries=1,
            query_retry_backoff_ms=0,
            query_retry_backoff_max_ms=0,
            dry_run=False,
        )

        device_result = {
            "ok": True,
            "status": "ok",
            "replies": [
                {
                    "ok": True,
                    "payload": {
                        "status": "ok",
                        "network_state": "NETWORK_READY",
                        "ipv4": "192.168.2.67",
                    },
                }
            ],
        }
        apps_result = {
            "ok": True,
            "status": "ok",
            "replies": [{"ok": True, "payload": {"status": "ok", "app_count": 0, "apps": []}}],
        }
        leases_result = {
            "ok": True,
            "status": "ok",
            "replies": [{"ok": True, "payload": {"status": "ok", "leases": []}}],
        }

        out = io.StringIO()
        with mock.patch.object(
            neuro_cli,
            "collect_query_result_with_retry",
            side_effect=[device_result, apps_result, leases_result],
        ) as collect_mock:
            with redirect_stdout(out):
                code = neuro_cli.handle_state_sync(mock.Mock(), args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema_version"], neuro_cli.STATE_SYNC_SCHEMA_VERSION)
        self.assertEqual(payload["state"]["device"]["payload"]["network_state"], "NETWORK_READY")
        self.assertEqual(payload["state"]["apps"]["payload"]["app_count"], 0)
        self.assertEqual(payload["state"]["leases"]["payload"]["leases"], [])
        self.assertEqual(
            payload["recommended_next_actions"],
            ["state sync is clean; read-only delegated reasoning may continue"],
        )
        self.assertEqual(collect_mock.call_count, 3)

    def test_init_diagnostics_reports_workspace_scripts(self) -> None:
        args = Namespace(output="json")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_init(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["protocol"]["wire_encoding"], "cbor-v2")
        self.assertFalse(payload["shell_setup"]["can_modify_parent_shell"])
        self.assertEqual(payload["agent_skill"]["name"], "neuro-cli")
        self.assertTrue(payload["agent_skill"]["canonical_exists"])
        self.assertTrue(payload["agent_skill"]["project_shared_exists"])
        self.assertTrue(payload["agent_skill"]["wrapper_exists"])
        self.assertIn(
            "neuro_cli/skill/SKILL.md",
            payload["agent_skill"]["canonical_path"],
        )
        self.assertIn(
            ".github/skills/neuro-cli/SKILL.md",
            payload["agent_skill"]["project_shared_path"],
        )
        self.assertTrue(payload["scripts"]["setup_neurolink_env.sh"]["exists"])

    def test_parser_parses_workflow_plan_without_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "workflow", "plan", "app-build"])

        self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
        self.assertFalse(args.requires_session)
        self.assertEqual(args.workflow, "app-build")

    def test_parser_accepts_setup_linux_workflow_plan(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "workflow", "plan", "setup-linux"])

        self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
        self.assertFalse(args.requires_session)
        self.assertEqual(args.workflow, "setup-linux")

    def test_parser_accepts_setup_windows_workflow_plan(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "workflow", "plan", "setup-windows"])

        self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
        self.assertFalse(args.requires_session)
        self.assertEqual(args.workflow, "setup-windows")

    def test_parser_accepts_discovery_workflow_plans(self) -> None:
        parser = neuro_cli.build_parser()

        for workflow in (
            "discover-host",
            "discover-router",
            "discover-serial",
            "discover-device",
            "discover-apps",
            "discover-leases",
        ):
            args = parser.parse_args(["--output", "json", "workflow", "plan", workflow])
            self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
            self.assertFalse(args.requires_session)
            self.assertEqual(args.workflow, workflow)

    def test_parser_accepts_control_workflow_plans(self) -> None:
        parser = neuro_cli.build_parser()

        for workflow in (
            "control-health",
            "control-deploy",
            "control-app-invoke",
            "control-callback",
            "control-monitor",
            "control-cleanup",
        ):
            args = parser.parse_args(["--output", "json", "workflow", "plan", workflow])
            self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
            self.assertFalse(args.requires_session)
            self.assertEqual(args.workflow, workflow)

    def test_parser_accepts_agent_evidence_workflow_plans(self) -> None:
        parser = neuro_cli.build_parser()

        for workflow in (
            "memory-evidence",
            "memory-layout-dump",
            "llext-memory-config",
            "llext-lifecycle",
            "callback-smoke",
            "release-closure",
        ):
            args = parser.parse_args(["--output", "json", "workflow", "plan", workflow])
            self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
            self.assertFalse(args.requires_session)
            self.assertEqual(args.workflow, workflow)

    def test_parser_accepts_release_1_1_10_demo_workflow_plans(self) -> None:
        parser = neuro_cli.build_parser()

        for workflow in (
            "demo-build",
            "demo-net-event-smoke",
        ):
            args = parser.parse_args(["--output", "json", "workflow", "plan", workflow])
            self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
            self.assertFalse(args.requires_session)
            self.assertEqual(args.workflow, workflow)

    def test_parser_accepts_memory_layout_dump_without_session(self) -> None:
        parser = neuro_cli.build_parser()

        legacy = parser.parse_args(["--output", "json", "memory-layout-dump"])
        grouped = parser.parse_args(["--output", "json", "memory", "layout-dump"])

        self.assertIs(legacy.handler, neuro_cli.handle_memory_layout_dump)
        self.assertFalse(legacy.requires_session)
        self.assertEqual(legacy.build_dir, "build/neurolink_unit")
        self.assertIs(grouped.handler, neuro_cli.handle_memory_layout_dump)
        self.assertFalse(grouped.requires_session)
        self.assertEqual(grouped.output_dir, "applocation/NeuroLink/memory-evidence")

    def test_parser_accepts_llext_memory_config_plan_without_session(self) -> None:
        parser = neuro_cli.build_parser()

        legacy = parser.parse_args(
            [
                "--output",
                "json",
                "llext-memory-config-plan",
                "--baseline-json",
                "baseline.json",
                "--candidate-json",
                "candidate.json",
            ]
        )
        grouped = parser.parse_args(
            [
                "--output",
                "json",
                "memory",
                "config-plan",
                "--baseline-json",
                "baseline.json",
                "--candidate-json",
                "candidate.json",
            ]
        )

        self.assertIs(legacy.handler, neuro_cli.handle_llext_memory_config_plan)
        self.assertFalse(legacy.requires_session)
        self.assertEqual(legacy.baseline_json, "baseline.json")
        self.assertIs(grouped.handler, neuro_cli.handle_llext_memory_config_plan)
        self.assertFalse(grouped.requires_session)
        self.assertEqual(grouped.candidate_json, "candidate.json")

    def test_parser_accepts_serial_commands_without_zenoh_session(self) -> None:
        parser = neuro_cli.build_parser()
        show = parser.parse_args(
            ["--output", "json", "serial", "zenoh", "show", "--port", "/dev/ttyACM0"]
        )
        set_endpoint = parser.parse_args(
            [
                "--output",
                "json",
                "serial",
                "zenoh",
                "set",
                "tcp/192.168.2.94:7447",
                "--port",
                "/dev/ttyACM0",
            ]
        )

        self.assertIs(show.handler, neuro_cli.handle_serial_zenoh)
        self.assertFalse(show.requires_session)
        self.assertEqual(show.serial_zenoh_command, "show")
        self.assertEqual(show.port, "/dev/ttyACM0")
        self.assertEqual(show.baudrate, neuro_cli.DEFAULT_SERIAL_BAUDRATE)
        self.assertIs(set_endpoint.handler, neuro_cli.handle_serial_zenoh)
        self.assertFalse(set_endpoint.requires_session)
        self.assertEqual(set_endpoint.serial_zenoh_command, "set")
        self.assertEqual(set_endpoint.endpoint, "tcp/192.168.2.94:7447")

    def test_parser_routes_app_unload_to_control_command(self) -> None:
        parser = neuro_cli.build_parser()

        args = parser.parse_args(
            [
                "--output",
                "json",
                "app",
                "unload",
                "--app-id",
                "neuro_unit_app",
                "--lease-id",
                "lease-1",
            ]
        )

        self.assertIs(args.handler, neuro_cli.handle_app_control)
        self.assertTrue(getattr(args, "requires_session", True))
        self.assertEqual(args.action, "unload")

    def test_parser_routes_app_delete_to_update_command(self) -> None:
        parser = neuro_cli.build_parser()

        args = parser.parse_args(
            [
                "--output",
                "json",
                "app",
                "delete",
                "--app-id",
                "neuro_unit_app",
                "--lease-id",
                "lease-1",
            ]
        )

        self.assertIs(args.handler, neuro_cli.handle_update)
        self.assertTrue(getattr(args, "requires_session", True))
        self.assertEqual(args.stage, "delete")

    def test_serial_list_reports_devices_as_json(self) -> None:
        args = Namespace(output="json")
        with mock.patch.object(
            neuro_cli,
            "discover_serial_devices",
            return_value=[{"device": "/dev/ttyACM0", "source": "pyserial"}],
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_serial_list(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["devices"][0]["device"], "/dev/ttyACM0")

    def test_serial_zenoh_set_verifies_shell_endpoint(self) -> None:
        args = Namespace(
            output="json",
            serial_zenoh_command="set",
            endpoint="tcp/192.168.2.94:7447",
        )
        with mock.patch.object(
            neuro_cli,
            "run_serial_shell_command",
            return_value={
                "ok": True,
                "status": "ok",
                "output": "zenoh connect override applied: tcp/192.168.2.94:7447\r\n",
            },
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_serial_zenoh(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["endpoint"], "tcp/192.168.2.94:7447")

    def test_serial_zenoh_set_fails_when_endpoint_does_not_match(self) -> None:
        args = Namespace(
            output="json",
            serial_zenoh_command="set",
            endpoint="tcp/192.168.2.94:7447",
        )
        with mock.patch.object(
            neuro_cli,
            "run_serial_shell_command",
            return_value={
                "ok": True,
                "status": "ok",
                "output": "zenoh connect override applied: tcp/192.168.2.95:7447\r\n",
            },
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_serial_zenoh(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "endpoint_verify_failed")

    def test_serial_zenoh_set_tolerates_success_output_with_following_warning(self) -> None:
        args = Namespace(
            output="json",
            serial_zenoh_command="set",
            endpoint="tcp/192.168.2.90:7447",
        )
        with mock.patch.object(
            neuro_cli,
            "run_serial_shell_command",
            return_value={
                "ok": False,
                "status": "shell_error",
                "output": (
                    "app zenoh_connect_set tcp/192.168.2.90:7447\r\n"
                    "zenoh connect override applied: tcp/192.168.2.90:7447\r\n"
                    "[00:10:16.293,000] <wrn> neurolink_unit: tcp probe connect failed: "
                    "endpoint=tcp/192.168.2.94:7447 errno=116\r\n"
                ),
                "error": "serial shell reported an error",
            },
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_serial_zenoh(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["endpoint"], "tcp/192.168.2.90:7447")

    def test_serial_workflow_plans_document_uart_recovery_contracts(self) -> None:
        expected = {
            "serial-discover": "serial list",
            "serial-zenoh-config": "serial zenoh set",
            "serial-zenoh-recover": "query device",
            "memory-layout-dump": "memory layout-dump",
            "llext-memory-config": "memory config-plan",
            "llext-lifecycle": "app delete",
        }

        for workflow, command in expected.items():
            payload = neuro_cli.build_workflow_plan(
                Namespace(output="json", workflow=workflow)
            )
            commands = "\n".join(payload["commands"])

            self.assertFalse(payload["executes_commands"], workflow)
            self.assertIn(command, commands, workflow)
            self.assertTrue(payload["json_contract"], workflow)
            self.assertIn("failure_statuses", payload["json_contract"], workflow)


class TestNeuroCliResultClassification(unittest.TestCase):
    def _reply(self, payload: dict):
        class _Payload:
            def to_string(self) -> str:
                return json.dumps(payload)

        class _Ok:
            key_expr = "neuro/unit-01/query/device"
            payload = _Payload()

        class _Reply:
            ok = _Ok()

        return _Reply()

    def test_collect_query_result_with_retry_fails_nested_error_status(self) -> None:
        class _Session:
            calls = 0

            def get(self, *args, **kwargs):
                del args, kwargs
                self.calls += 1
                return [self_reply]

        self_reply = self._reply(
            {"status": "error", "status_code": 409, "message": "lease conflict"}
        )
        session = _Session()
        args = Namespace(output="json")

        result = neuro_cli.collect_query_result_with_retry(
            session,
            "neuro/unit-01/query/device",
            {"request_id": "req-1"},
            1.0,
            neuro_cli.RetryPolicy(max_attempts=3, initial_backoff_sec=0, max_backoff_sec=0),
            args,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error_reply")
        self.assertEqual(result["failure_status"], "error")
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(session.calls, 1)

    def test_result_has_reply_error_treats_non_ok_status_as_failure(self) -> None:
        result = {
            "ok": True,
            "replies": [
                {"ok": True, "payload": {"status": "not_implemented"}},
            ],
        }

        self.assertTrue(neuro_cli.result_has_reply_error(result))

    def test_main_query_device_preserves_nested_not_implemented_failure_status(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            ["--output", "json", "--query-retries", "1", "query", "device"],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/query/device",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {
                        "ok": True,
                        "keyexpr": "neuro/unit-01/query/device",
                        "payload": {"status": "not_implemented", "status_code": 501},
                    }
                ],
            },
        )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error_reply")
        self.assertEqual(payload["failure_status"], "not_implemented")
        self.assertEqual(collect.call_args[0][1], "neuro/unit-01/query/device")

    def _run_main_with_collect_result(
        self, cli_args: list[str], collect_result: dict
    ) -> tuple[int, dict, mock.Mock]:
        session = mock.Mock()
        session.close = mock.Mock()
        collect = mock.Mock(return_value=collect_result)

        with mock.patch.object(sys, "argv", ["neuro_cli.py", *cli_args]), \
            mock.patch.object(neuro_cli, "open_session_with_retry", return_value=session), \
            mock.patch.object(neuro_cli, "collect_query_result", collect):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.main()

        payload = json.loads(out.getvalue())
        return code, payload, collect

    def test_main_query_device_reports_session_open_failure_json(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            ["neuro_cli.py", "--output", "json", "query", "device"],
        ), mock.patch.object(
            neuro_cli,
            "open_session_with_retry",
            side_effect=RuntimeError("router unavailable"),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.main()

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "session_open_failed")
        self.assertIn("router unavailable", payload["error"])

    def test_main_query_device_reports_handler_failure_json(self) -> None:
        session = mock.Mock()
        session.close = mock.Mock()

        with mock.patch.object(
            sys,
            "argv",
            ["neuro_cli.py", "--output", "json", "query", "device"],
        ), mock.patch.object(
            neuro_cli, "open_session_with_retry", return_value=session
        ), mock.patch.object(
            neuro_cli, "handle_query", side_effect=RuntimeError("handler boom")
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.main()

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "handler_failed")
        self.assertIn("handler boom", payload["error"])
        session.close.assert_called_once()

    def test_main_query_device_fails_nested_error_reply(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            ["--output", "json", "--query-retries", "1", "query", "device"],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/query/device",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {
                        "ok": True,
                        "keyexpr": "neuro/unit-01/query/device",
                        "payload": {"status": "error", "status_code": 409},
                    }
                ],
            },
        )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error_reply")
        self.assertEqual(collect.call_args[0][1], "neuro/unit-01/query/device")

    def test_main_grouped_lease_acquire_payload_path(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            [
                "--output",
                "json",
                "lease",
                "acquire",
                "--resource",
                "update/app/neuro_unit_app/activate",
                "--lease-id",
                "lease-1",
                "--ttl-ms",
                "120000",
            ],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/cmd/lease/acquire",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {"ok": True, "payload": {"status": "ok", "lease_id": "lease-1"}}
                ],
            },
        )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        keyexpr = collect.call_args[0][1]
        sent_payload = collect.call_args[0][2]
        self.assertEqual(keyexpr, "neuro/unit-01/cmd/lease/acquire")
        self.assertEqual(sent_payload["resource"], "update/app/neuro_unit_app/activate")
        self.assertEqual(sent_payload["lease_id"], "lease-1")
        self.assertEqual(sent_payload["ttl_ms"], 120000)

    def test_main_grouped_deploy_activate_payload_path(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            [
                "--output",
                "json",
                "deploy",
                "activate",
                "--app-id",
                "neuro_unit_app",
                "--lease-id",
                "lease-1",
                "--start-args",
                "mode=demo,profile=release",
            ],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/update/app/neuro_unit_app/activate",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {"ok": True, "payload": {"status": "ok", "app_id": "neuro_unit_app"}}
                ],
            },
        )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        keyexpr = collect.call_args[0][1]
        sent_payload = collect.call_args[0][2]
        self.assertEqual(keyexpr, "neuro/unit-01/update/app/neuro_unit_app/activate")
        self.assertEqual(sent_payload["lease_id"], "lease-1")
        self.assertEqual(sent_payload["start_args"], "mode=demo,profile=release")

    def test_main_grouped_deploy_rollback_payload_path(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            [
                "--output",
                "json",
                "deploy",
                "rollback",
                "--app-id",
                "neuro_unit_app",
                "--lease-id",
                "lease-rollback-1",
                "--reason",
                "rollback requested by guarded recovery review",
            ],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/update/app/neuro_unit_app/rollback",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {"ok": True, "payload": {"status": "ok", "app_id": "neuro_unit_app"}}
                ],
            },
        )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        keyexpr = collect.call_args[0][1]
        sent_payload = collect.call_args[0][2]
        self.assertEqual(keyexpr, "neuro/unit-01/update/app/neuro_unit_app/rollback")
        self.assertEqual(sent_payload["lease_id"], "lease-rollback-1")
        self.assertEqual(
            sent_payload["reason"],
            "rollback requested by guarded recovery review",
        )

    def test_main_grouped_app_unload_payload_path(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            [
                "--output",
                "json",
                "app",
                "unload",
                "--app-id",
                "neuro_unit_app",
                "--lease-id",
                "lease-1",
            ],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/cmd/app/neuro_unit_app/unload",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {"ok": True, "payload": {"status": "ok", "app_id": "neuro_unit_app"}}
                ],
            },
        )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        keyexpr = collect.call_args[0][1]
        sent_payload = collect.call_args[0][2]
        self.assertEqual(keyexpr, "neuro/unit-01/cmd/app/neuro_unit_app/unload")
        self.assertEqual(sent_payload["lease_id"], "lease-1")

    def test_main_grouped_app_delete_payload_path(self) -> None:
        code, payload, collect = self._run_main_with_collect_result(
            [
                "--output",
                "json",
                "app",
                "delete",
                "--app-id",
                "neuro_unit_app",
                "--lease-id",
                "lease-1",
            ],
            {
                "ok": True,
                "keyexpr": "neuro/unit-01/update/app/neuro_unit_app/delete",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {"ok": True, "payload": {"status": "ok", "app_id": "neuro_unit_app"}}
                ],
            },
        )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        keyexpr = collect.call_args[0][1]
        sent_payload = collect.call_args[0][2]
        self.assertEqual(keyexpr, "neuro/unit-01/update/app/neuro_unit_app/delete")
        self.assertEqual(sent_payload["lease_id"], "lease-1")

    def test_workflow_plan_outputs_command_plan_without_execution(self) -> None:
        args = Namespace(output="json", workflow="preflight")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_workflow_plan(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workflow"], "preflight")
        self.assertFalse(payload["executes_commands"])
        self.assertEqual(payload["agent_skill"]["name"], "neuro-cli")
        self.assertIn("invoke_neuro_cli.py", payload["agent_skill"]["wrapper"])
        self.assertIn("preflight_neurolink_linux.sh", payload["commands"][0])

    def test_workflow_plans_include_low_parameter_agent_metadata(self) -> None:
        required_fields = {
            "schema_version",
            "host_support",
            "requires_hardware",
            "requires_serial",
            "requires_router",
            "requires_network",
            "destructive",
            "preconditions",
            "expected_success",
            "failure_statuses",
            "cleanup",
        }

        for workflow in neuro_cli.WORKFLOW_PLANS:
            args = Namespace(output="json", workflow=workflow)
            payload = neuro_cli.build_workflow_plan(args)

            self.assertEqual(
                payload["schema_version"],
                neuro_cli.WORKFLOW_PLAN_SCHEMA_VERSION,
                workflow,
            )
            self.assertTrue(required_fields.issubset(payload), workflow)
            self.assertIsInstance(payload["host_support"], list, workflow)
            self.assertIsInstance(payload["preconditions"], list, workflow)
            self.assertIsInstance(payload["expected_success"], list, workflow)
            self.assertIsInstance(payload["failure_statuses"], list, workflow)
            self.assertIsInstance(payload["cleanup"], list, workflow)
            self.assertTrue(payload["host_support"], workflow)
            self.assertTrue(payload["preconditions"], workflow)
            self.assertTrue(payload["expected_success"], workflow)

    def test_workflow_plan_metadata_marks_hardware_and_destructive_paths(self) -> None:
        preflight = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="preflight")
        )
        callback_smoke = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="callback-smoke")
        )
        cli_tests = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="cli-tests")
        )

        self.assertTrue(preflight["requires_hardware"])
        self.assertTrue(preflight["requires_serial"])
        self.assertTrue(preflight["requires_router"])
        self.assertFalse(preflight["destructive"])
        self.assertIn("serial_device_missing", str(preflight["failure_statuses"]))

        self.assertTrue(callback_smoke["requires_hardware"])
        self.assertTrue(callback_smoke["requires_router"])
        self.assertTrue(callback_smoke["destructive"])
        self.assertIn("release callback smoke lease", " ".join(callback_smoke["cleanup"]))

        self.assertFalse(cli_tests["requires_hardware"])
        self.assertFalse(cli_tests["requires_router"])
        self.assertIn("windows", cli_tests["host_support"])
        self.assertFalse(cli_tests["requires_network"])

    def test_setup_linux_workflow_plan_documents_zero_host_bootstrap(self) -> None:
        payload = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="setup-linux")
        )
        commands = "\n".join(payload["commands"])

        self.assertEqual(payload["category"], "setup")
        self.assertEqual(payload["host_support"], ["linux"])
        self.assertFalse(payload["requires_hardware"])
        self.assertFalse(payload["requires_serial"])
        self.assertFalse(payload["requires_router"])
        self.assertTrue(payload["requires_network"])
        self.assertFalse(payload["destructive"])
        self.assertIn("sudo apt-get install", commands)
        self.assertIn("python3 -m venv .venv", commands)
        self.assertIn("west update", commands)
        self.assertIn("cat zephyr/SDK_VERSION", commands)
        self.assertIn("ZEPHYR_SDK_INSTALL_DIR", commands)
        self.assertIn("setup_neurolink_env.sh --activate --strict", commands)
        self.assertIn("workflow plan preflight", commands)
        self.assertIn("operator approves sudo", " ".join(payload["preconditions"]))
        self.assertIn("zephyr_sdk_missing", str(payload["failure_statuses"]))

    def test_setup_windows_workflow_plan_documents_zero_host_bootstrap(self) -> None:
        payload = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="setup-windows")
        )
        commands = "\n".join(payload["commands"])

        self.assertEqual(payload["category"], "setup")
        self.assertEqual(payload["host_support"], ["windows", "wsl"])
        self.assertFalse(payload["requires_hardware"])
        self.assertFalse(payload["requires_serial"])
        self.assertFalse(payload["requires_router"])
        self.assertTrue(payload["requires_network"])
        self.assertFalse(payload["destructive"])
        self.assertIn("winget install", commands)
        self.assertIn("py -3 -m venv .venv", commands)
        self.assertIn("Activate.ps1", commands)
        self.assertIn("west update", commands)
        self.assertIn("Get-Content zephyr/SDK_VERSION", commands)
        self.assertIn("setup_neurolink_env.ps1 -Strict", commands)
        self.assertIn("workflow plan preflight", commands)
        self.assertIn("operator approves winget", " ".join(payload["preconditions"]))
        self.assertIn("execution_policy_blocked", str(payload["failure_statuses"]))
        self.assertIn("wsl_usb_required", str(payload["failure_statuses"]))

    def test_demo_build_workflow_plan_documents_catalog_backed_wrapper(self) -> None:
        payload = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="demo-build")
        )
        commands = "\n".join(payload["commands"])

        self.assertEqual(payload["category"], "app_development")
        self.assertFalse(payload["requires_hardware"])
        self.assertFalse(payload["requires_serial"])
        self.assertFalse(payload["requires_router"])
        self.assertFalse(payload["requires_network"])
        self.assertFalse(payload["destructive"])
        self.assertIn("build_neurolink_demo.sh --demo neuro_demo_net_event", commands)
        self.assertIn("--print-artifact-path", commands)
        self.assertIn("demo_catalog.json", "\n".join(payload["artifacts"]))
        self.assertIn("catalog-backed wrapper exits 0", " ".join(payload["expected_success"]))
        self.assertIn("demo_not_defined", str(payload["failure_statuses"]))

    def test_discovery_workflow_plans_document_json_contracts(self) -> None:
        expected = {
            "discover-host": {
                "command": "system init",
                "status": "workspace_not_found",
                "hardware": False,
                "router": False,
            },
            "discover-router": {
                "command": "preflight_neurolink_linux.sh",
                "status": "router_not_listening",
                "hardware": False,
                "router": True,
            },
            "discover-serial": {
                "command": "--require-serial",
                "status": "serial_device_missing",
                "hardware": True,
                "router": False,
            },
            "discover-device": {
                "command": "query device",
                "status": "no_reply",
                "hardware": True,
                "router": True,
            },
            "discover-apps": {
                "command": "query apps",
                "status": "app_not_running",
                "hardware": True,
                "router": True,
            },
            "discover-leases": {
                "command": "query leases",
                "status": "lease_conflict",
                "hardware": True,
                "router": True,
            },
        }

        for workflow, checks in expected.items():
            payload = neuro_cli.build_workflow_plan(
                Namespace(output="json", workflow=workflow)
            )
            commands = "\n".join(payload["commands"])

            self.assertEqual(payload["category"], "discovery", workflow)
            self.assertFalse(payload["destructive"], workflow)
            self.assertFalse(payload["executes_commands"], workflow)
            self.assertEqual(payload["requires_hardware"], checks["hardware"], workflow)
            self.assertEqual(payload["requires_router"], checks["router"], workflow)
            self.assertIn(checks["command"], commands, workflow)
            self.assertIn(checks["status"], str(payload["failure_statuses"]), workflow)
            self.assertIn(checks["status"], str(payload["json_contract"]), workflow)

    def test_discovery_workflow_plans_use_linux_wrapper_or_json_commands(self) -> None:
        for workflow in (
            "discover-host",
            "discover-router",
            "discover-serial",
            "discover-device",
            "discover-apps",
            "discover-leases",
        ):
            payload = neuro_cli.build_workflow_plan(
                Namespace(output="json", workflow=workflow)
            )
            commands = "\n".join(payload["commands"])

            self.assertNotIn("winget", commands, workflow)
            self.assertNotIn("Activate.ps1", commands, workflow)
            self.assertTrue(
                "invoke_neuro_cli.py" in commands or "--output json" in commands,
                workflow,
            )

    def test_control_workflow_plans_document_safety_and_cleanup(self) -> None:
        expected = {
            "control-health": {
                "command": "query device",
                "status": "no_reply",
                "destructive": False,
                "cleanup": "",
            },
            "control-deploy": {
                "command": "deploy activate",
                "status": "lease_conflict",
                "destructive": True,
                "cleanup": "deploy",
            },
            "control-app-invoke": {
                "command": "app invoke",
                "status": "app_not_running",
                "destructive": True,
                "cleanup": "app-control",
            },
            "control-callback": {
                "command": "app callback-config",
                "status": "callback_timeout",
                "destructive": True,
                "cleanup": "callback",
            },
            "control-monitor": {
                "command": "monitor app-events",
                "status": "handler_failed",
                "destructive": False,
                "cleanup": "undeclare subscriber",
            },
            "control-cleanup": {
                "command": "lease release",
                "status": "lease_not_found",
                "destructive": False,
                "cleanup": "query leases",
            },
        }

        for workflow, checks in expected.items():
            payload = neuro_cli.build_workflow_plan(
                Namespace(output="json", workflow=workflow)
            )
            commands = "\n".join(payload["commands"])

            self.assertEqual(payload["category"], "control", workflow)
            self.assertFalse(payload["executes_commands"], workflow)
            self.assertEqual(payload["destructive"], checks["destructive"], workflow)
            self.assertTrue(payload["requires_hardware"], workflow)
            self.assertTrue(payload["requires_router"], workflow)
            self.assertIn(checks["command"], commands, workflow)
            self.assertIn(checks["status"], str(payload["failure_statuses"]), workflow)
            self.assertIn(checks["status"], str(payload["json_contract"]), workflow)
            if checks["cleanup"]:
                self.assertIn(checks["cleanup"], "\n".join(payload["cleanup"] + payload["commands"]), workflow)

    def test_control_workflow_plans_keep_lease_and_handler_boundaries_explicit(self) -> None:
        deploy = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="control-deploy")
        )
        app_invoke = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="control-app-invoke")
        )
        callback = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="control-callback")
        )
        monitor = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="control-monitor")
        )

        deploy_commands = "\n".join(deploy["commands"])
        app_commands = "\n".join(app_invoke["commands"])
        callback_commands = "\n".join(callback["commands"])
        monitor_commands = "\n".join(monitor["commands"])

        self.assertIn("update/app/neuro_unit_app/activate", deploy_commands)
        self.assertIn("lease release --lease-id", deploy_commands)
        self.assertIn("query leases", deploy_commands)
        self.assertIn("app/neuro_unit_app/control", app_commands)
        self.assertIn("lease release --lease-id", app_commands)
        self.assertIn("--mode on", callback_commands)
        self.assertIn("--mode off", callback_commands)
        self.assertIn("workflow plan callback-smoke", callback_commands)
        self.assertIn("--handler-python", monitor_commands)
        self.assertIn("callback_handler.py", monitor_commands)
        self.assertIn("handler audit", " ".join(monitor["expected_success"]))

    def test_demo_net_event_smoke_workflow_plan_documents_first_demo_contract(self) -> None:
        payload = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="demo-net-event-smoke")
        )
        commands = "\n".join(payload["commands"])

        self.assertEqual(payload["category"], "board_operation")
        self.assertTrue(payload["requires_hardware"])
        self.assertTrue(payload["requires_serial"])
        self.assertTrue(payload["requires_router"])
        self.assertFalse(payload["requires_network"])
        self.assertTrue(payload["destructive"])
        self.assertIn("workflow plan demo-build", commands)
        self.assertIn("preflight_neurolink_linux.sh", commands)
        self.assertIn("--artifact-file build/neurolink_unit/llext/neuro_demo_net_event.llext", commands)
        self.assertIn("update/app/neuro_demo_net_event/activate", commands)
        self.assertIn("app/neuro_demo_net_event/control", commands)
        self.assertIn("app invoke --app-id neuro_demo_net_event", commands)
        self.assertIn('"action": "publish"', commands)
        self.assertIn("monitor app-events --app-id neuro_demo_net_event", commands)
        self.assertIn("demo_event", str(payload["json_contract"]))
        self.assertIn("not_implemented", str(payload["failure_statuses"]))

    def test_memory_evidence_workflow_plan_outputs_collector_command(self) -> None:
        args = Namespace(output="json", workflow="memory-evidence")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_workflow_plan(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workflow"], "memory-evidence")
        self.assertFalse(payload["executes_commands"])
        self.assertIn("collect_neurolink_memory_evidence.py", payload["commands"][0])
        self.assertIn("--run-build", payload["commands"][0])
        self.assertIn(
            f"--label release-{neuro_cli.RELEASE_TARGET}-memory-evidence",
            payload["commands"][0],
        )
        self.assertIn("applocation/NeuroLink/memory-evidence", payload["artifacts"])

    def test_memory_layout_dump_reports_missing_build_dir(self) -> None:
        args = Namespace(
            output="json",
            build_dir="build/does-not-exist-for-test",
            output_dir="applocation/NeuroLink/memory-evidence",
            label="test-static-layout",
            build_log="",
            run_build=False,
            no_c_style_check=False,
        )

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_memory_layout_dump(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "build_dir_missing")

    def test_memory_layout_dump_invokes_collector_and_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            build_dir = temp_path / "build" / "unit"
            output_dir = temp_path / "evidence"
            (build_dir / "zephyr").mkdir(parents=True)
            (build_dir / "zephyr" / ".config").write_text("CONFIG_BOARD=demo\n")
            (build_dir / "zephyr" / "zephyr.stat").write_text("\n")
            output_dir.mkdir()
            evidence_path = output_dir / "test-static-layout.json"
            summary_path = output_dir / "test-static-layout.summary.txt"
            evidence_path.write_text(
                json.dumps(
                    {
                        "label": "test-static-layout",
                        "release_target": neuro_cli.RELEASE_TARGET,
                        "build_dir": str(build_dir),
                        "platform": {"board": "demo"},
                        "memory_capability": {"provider": "none"},
                        "section_totals": {"dram0": 16, "iram0": 8},
                        "sections": [{"name": ".dram0.bss", "size_bytes": 16}],
                    }
                )
                + "\n"
            )
            summary_path.write_text("summary\n")
            args = Namespace(
                output="json",
                build_dir=str(build_dir),
                output_dir=str(output_dir),
                label="test-static-layout",
                build_log="",
                run_build=False,
                no_c_style_check=False,
            )
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    f"memory_evidence_json={evidence_path}\n"
                    f"memory_evidence_summary={summary_path}\n"
                ),
                stderr="",
            )

            out = io.StringIO()
            with mock.patch.object(neuro_cli.subprocess, "run", return_value=completed):
                with redirect_stdout(out):
                    code = neuro_cli.handle_memory_layout_dump(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["section_totals"]["dram0"], 16)
        self.assertEqual(payload["section_count"], 1)
        self.assertIn("json", payload["artifacts"])

    def test_llext_memory_config_plan_compares_static_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            baseline_path = temp_path / "baseline.json"
            candidate_path = temp_path / "candidate.json"
            baseline_path.write_text(
                json.dumps(
                    {
                        "label": "baseline",
                        "release_target": neuro_cli.RELEASE_TARGET,
                        "section_totals": {"dram0": 100, "iram0": 50, "flash": 500},
                    }
                )
                + "\n"
            )
            candidate_path.write_text(
                json.dumps(
                    {
                        "label": "candidate",
                        "release_target": neuro_cli.RELEASE_TARGET,
                        "section_totals": {"dram0": 96, "iram0": 50, "flash": 520},
                        "memory_capability": {"provider": "esp-spiram"},
                        "runtime_evidence_gate": {"passed": False},
                    }
                )
                + "\n"
            )
            args = Namespace(
                output="json",
                baseline_json=str(baseline_path),
                candidate_json=str(candidate_path),
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_llext_memory_config_plan(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["section_deltas"]["dram0"]["delta_bytes"], -4)
        self.assertFalse(payload["promotion_allowed"])
        self.assertIn("runtime_evidence_required", payload["promotion_blockers"])

    def test_llext_memory_config_plan_reports_memory_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            baseline_path = temp_path / "baseline.json"
            candidate_path = temp_path / "candidate.json"
            baseline_path.write_text(
                json.dumps({"section_totals": {"dram0": 100, "iram0": 50}}) + "\n"
            )
            candidate_path.write_text(
                json.dumps({"section_totals": {"dram0": 104, "iram0": 48}}) + "\n"
            )
            args = Namespace(
                output="json",
                baseline_json=str(baseline_path),
                candidate_json=str(candidate_path),
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_llext_memory_config_plan(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "memory_regression")
        self.assertEqual(payload["static_regressions"][0]["region"], "dram0")
        self.assertIn("memory_regression", payload["promotion_blockers"])

    def test_llext_memory_config_plan_blocks_dynamic_heap_without_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            baseline_path = temp_path / "baseline.json"
            candidate_path = temp_path / "candidate.json"
            baseline_path.write_text(
                json.dumps({"section_totals": {"dram0": 100, "iram0": 50}}) + "\n"
            )
            candidate_path.write_text(
                json.dumps(
                    {
                        "section_totals": {"dram0": 96, "iram0": 48},
                        "config": {"CONFIG_LLEXT_HEAP_DYNAMIC": "y"},
                        "runtime_evidence_gate": {"passed": False},
                    }
                )
                + "\n"
            )
            args = Namespace(
                output="json",
                baseline_json=str(baseline_path),
                candidate_json=str(candidate_path),
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_llext_memory_config_plan(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "runtime_heap_dynamic_unsafe")
        self.assertTrue(payload["dynamic_heap_enabled"])
        self.assertIn("runtime_heap_dynamic_unsafe", payload["promotion_blockers"])
        self.assertIn("runtime_evidence_required", payload["promotion_blockers"])
        self.assertEqual(
            payload["next_action"],
            "add explicit llext_heap_init wiring before hardware promotion",
        )

    def test_llext_memory_config_plan_reports_missing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            baseline_path = temp_path / "baseline.json"
            candidate_path = temp_path / "missing.json"
            baseline_path.write_text(json.dumps({"section_totals": {}}) + "\n")
            args = Namespace(
                output="json",
                baseline_json=str(baseline_path),
                candidate_json=str(candidate_path),
            )

            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.handle_llext_memory_config_plan(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "candidate_layout_missing")

    def test_release_closure_workflow_plan_lists_gates_without_execution(self) -> None:
        args = Namespace(output="json", workflow="release-closure")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_workflow_plan(None, args)

        payload = json.loads(out.getvalue())
        commands = "\n".join(payload["commands"])

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["workflow"], "release-closure")
        self.assertFalse(payload["executes_commands"])
        self.assertIn("collect_neurolink_memory_evidence.py", commands)
        self.assertIn(f"--label release-{neuro_cli.RELEASE_TARGET}-closure", commands)
        self.assertIn("pytest", commands)
        self.assertIn("run_all_tests.sh", commands)
        self.assertIn("diff --check", commands)
        self.assertIn("preflight_neurolink_linux.sh", commands)
        self.assertIn("smoke_neurolink_linux.sh", commands)

    def test_callback_smoke_workflow_plan_uses_wrapper_contract(self) -> None:
        args = Namespace(output="json", workflow="callback-smoke")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_workflow_plan(None, args)

        payload = json.loads(out.getvalue())
        command = payload["commands"][0]
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertIn("invoke_neuro_cli.py app-callback-smoke", command)
        self.assertNotIn("invoke_neuro_cli.py --output", command)
        self.assertIn("--app-id neuro_unit_app", command)
        self.assertIn(
            f"--expected-app-echo neuro_unit_app-{neuro_cli.RELEASE_TARGET}-cbor-v2",
            command,
        )
        self.assertIn("--trigger-every 1", command)

    def test_workflow_plan_agent_skill_metadata_reports_canonical_and_adapter_paths(self) -> None:
        payload = neuro_cli.build_workflow_plan(
            Namespace(output="json", workflow="app-build")
        )
        agent_skill = payload["agent_skill"]

        self.assertEqual(agent_skill["name"], "neuro-cli")
        self.assertTrue(agent_skill["canonical_exists"])
        self.assertTrue(agent_skill["project_shared_exists"])
        self.assertEqual(agent_skill["source_of_truth"], "canonical")
        self.assertIn("neuro_cli/skill/SKILL.md", agent_skill["canonical_path"])
        self.assertIn(
            ".github/skills/neuro-cli/SKILL.md",
            agent_skill["project_shared_path"],
        )
        self.assertIn(
            ".github/skills/neuro-cli/SKILL.md",
            agent_skill["discovery_adapter_path"],
        )

    def test_workflow_commands_do_not_embed_release_target_literals(self) -> None:
        commands = "\n".join(
            command
            for workflow in neuro_cli.WORKFLOW_PLANS.values()
            for command in workflow["commands"]
        )
        assert neuro_cli.__file__ is not None
        source_text = Path(neuro_cli.__file__).read_text(encoding="utf-8")

        self.assertIn(
            f"release-{neuro_cli.RELEASE_TARGET}-memory-evidence",
            commands,
        )
        self.assertIn(f"release-{neuro_cli.RELEASE_TARGET}-closure", commands)
        self.assertIn(f"neuro_unit_app-{neuro_cli.RELEASE_TARGET}-cbor-v2", commands)
        self.assertNotIn("release-1.1.7-memory-evidence", source_text)
        self.assertNotIn("release-1.1.7-closure", source_text)
        self.assertNotIn("neuro_unit_app-1.1.7-cbor-v2", source_text)

    def test_sample_app_source_identity_matches_release_target(self) -> None:
        project_root = NEURO_CLI_DIR.parent
        sample_app_source = (
            project_root / "subprojects" / "neuro_unit_app" / "src" / "main.c"
        )
        source_text = sample_app_source.read_text(encoding="utf-8")

        self.assertIn(
            f'static const char app_version[] = "{neuro_cli.RELEASE_TARGET}";',
            source_text,
        )
        self.assertIn(
            f'static const char app_build_id[] = "neuro_unit_app-{neuro_cli.RELEASE_TARGET}-cbor-v2";',
            source_text,
        )
        self.assertIn(".major = 1,", source_text)
        self.assertIn(".minor = 2,", source_text)
        self.assertIn(".patch = 6,", source_text)

    def test_canonical_skill_package_contains_required_resources(self) -> None:
        project_root = NEURO_CLI_DIR.parent
        canonical_skill_dir = NEURO_CLI_DIR / "skill"
        shared_skill_dir = project_root / ".github" / "skills" / "neuro-cli"

        required_paths = [
            canonical_skill_dir / "SKILL.md",
            canonical_skill_dir / "references" / "workflows.md",
            canonical_skill_dir / "references" / "setup-linux.md",
            canonical_skill_dir / "references" / "setup-windows.md",
            canonical_skill_dir / "references" / "discovery-and-control.md",
            canonical_skill_dir / "assets" / "neuro_unit_app_template.c",
            canonical_skill_dir / "assets" / "callback_handler.py",
            shared_skill_dir / "SKILL.md",
        ]
        for path in required_paths:
            self.assertTrue(path.is_file(), str(path))

        canonical_skill = (canonical_skill_dir / "SKILL.md").read_text(
            encoding="utf-8"
        )
        shared_skill = (shared_skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: neuro-cli", canonical_skill)
        self.assertIn("canonical Neuro CLI skill contract", canonical_skill)
        self.assertIn("../../../neuro_cli/skill/SKILL.md", shared_skill)

    def test_linux_setup_reference_contains_zero_host_steps(self) -> None:
        setup_linux = (
            NEURO_CLI_DIR / "skill" / "references" / "setup-linux.md"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow plan setup-linux", setup_linux)
        self.assertIn("sudo apt-get install", setup_linux)
        self.assertIn("python3 -m venv .venv", setup_linux)
        self.assertIn("west update", setup_linux)
        self.assertIn("cat zephyr/SDK_VERSION", setup_linux)
        self.assertIn("ZEPHYR_SDK_INSTALL_DIR", setup_linux)
        self.assertIn("serial_device_missing", setup_linux)

    def test_windows_setup_reference_contains_zero_host_steps(self) -> None:
        setup_windows = (
            NEURO_CLI_DIR / "skill" / "references" / "setup-windows.md"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow plan setup-windows", setup_windows)
        self.assertIn("winget install", setup_windows)
        self.assertIn("py -3 -m venv .venv", setup_windows)
        self.assertIn("Set-ExecutionPolicy -Scope Process", setup_windows)
        self.assertIn("Get-Content zephyr/SDK_VERSION", setup_windows)
        self.assertIn("ZEPHYR_SDK_INSTALL_DIR", setup_windows)
        self.assertIn("WSL", setup_windows)
        self.assertIn("perl-or-wsl", setup_windows)

    def test_discovery_reference_contains_workflows_and_json_contracts(self) -> None:
        reference = (
            NEURO_CLI_DIR / "skill" / "references" / "discovery-and-control.md"
        ).read_text(encoding="utf-8")
        workflows = (
            NEURO_CLI_DIR / "skill" / "references" / "workflows.md"
        ).read_text(encoding="utf-8")

        for workflow in (
            "discover-host",
            "discover-router",
            "discover-serial",
            "discover-device",
            "discover-apps",
            "discover-leases",
        ):
            self.assertIn(f"workflow plan {workflow}", reference)
            self.assertIn(f"workflow plan {workflow}", workflows)

        self.assertIn("JSON Contracts", reference)
        self.assertIn("router_not_listening", reference)
        self.assertIn("serial_device_missing", reference)
        self.assertIn("no_reply_board_unreachable", reference)
        self.assertIn("app_not_running", reference)
        self.assertIn("`leases` list", reference)

    def test_control_reference_contains_workflows_and_safety_contracts(self) -> None:
        reference = (
            NEURO_CLI_DIR / "skill" / "references" / "discovery-and-control.md"
        ).read_text(encoding="utf-8")
        workflows = (
            NEURO_CLI_DIR / "skill" / "references" / "workflows.md"
        ).read_text(encoding="utf-8")

        for workflow in (
            "control-health",
            "control-deploy",
            "control-app-invoke",
            "control-callback",
            "control-monitor",
            "control-cleanup",
        ):
            self.assertIn(f"workflow plan {workflow}", reference)
            self.assertIn(f"workflow plan {workflow}", workflows)

        self.assertIn("Protected Control JSON Contracts", reference)
        self.assertIn("update/app/neuro_unit_app/activate", reference)
        self.assertIn("app/neuro_unit_app/control", reference)
        self.assertIn("nested `payload.status: error`", reference)
        self.assertIn("Callback handler execution", reference)
        self.assertIn("query leases", reference)

    def test_demo_workflow_references_include_release_1_2_0_demo_plans(self) -> None:
        project_root = NEURO_CLI_DIR.parent
        canonical_workflows = (
            NEURO_CLI_DIR / "skill" / "references" / "workflows.md"
        ).read_text(encoding="utf-8")
        shared_workflows = (
            project_root
            / ".github"
            / "skills"
            / "neuro-cli"
            / "references"
            / "workflows.md"
        ).read_text(encoding="utf-8")
        discovery_control = (
            NEURO_CLI_DIR / "skill" / "references" / "discovery-and-control.md"
        ).read_text(encoding="utf-8")

        for text in (canonical_workflows, shared_workflows):
            self.assertIn("workflow plan demo-build", text)
            self.assertIn("workflow plan demo-net-event-smoke", text)

        self.assertIn("workflow plan demo-build", discovery_control)
        self.assertIn("workflow plan demo-net-event-smoke", discovery_control)
        self.assertIn("neuro_demo_net_event", discovery_control)

    def test_project_shared_skill_mirrors_canonical_resources(self) -> None:
        project_root = NEURO_CLI_DIR.parent
        canonical_skill_dir = NEURO_CLI_DIR / "skill"
        shared_skill_dir = project_root / ".github" / "skills" / "neuro-cli"
        mirrored_paths = [
            "references/workflows.md",
            "assets/neuro_unit_app_template.c",
            "assets/callback_handler.py",
        ]
        for relative_path in mirrored_paths:
            canonical_text = (canonical_skill_dir / relative_path).read_text(
                encoding="utf-8"
            )
            shared_text = (shared_skill_dir / relative_path).read_text(encoding="utf-8")
            self.assertEqual(canonical_text, shared_text, relative_path)

    def test_skill_workflow_references_only_live_workflow_plans(self) -> None:
        project_root = NEURO_CLI_DIR.parent
        checked_paths = [
            NEURO_CLI_DIR / "skill" / "SKILL.md",
            NEURO_CLI_DIR / "skill" / "references" / "workflows.md",
            NEURO_CLI_DIR / "skill" / "references" / "setup-linux.md",
            NEURO_CLI_DIR / "skill" / "references" / "setup-windows.md",
            NEURO_CLI_DIR / "skill" / "references" / "discovery-and-control.md",
            project_root / ".github" / "skills" / "neuro-cli" / "SKILL.md",
            project_root
            / ".github"
            / "skills"
            / "neuro-cli"
            / "references"
            / "workflows.md",
        ]

        referenced = set()
        for path in checked_paths:
            text = path.read_text(encoding="utf-8")
            referenced.update(extract_workflow_plan_names(text))

        self.assertTrue(referenced)
        self.assertTrue(referenced.issubset(neuro_cli.WORKFLOW_PLANS.keys()))

    def test_skill_wrapper_examples_parse_with_live_cli_parser(self) -> None:
        project_root = NEURO_CLI_DIR.parent
        checked_paths = [
            NEURO_CLI_DIR / "skill" / "SKILL.md",
            NEURO_CLI_DIR / "skill" / "references" / "workflows.md",
            NEURO_CLI_DIR / "skill" / "references" / "setup-linux.md",
            NEURO_CLI_DIR / "skill" / "references" / "setup-windows.md",
            NEURO_CLI_DIR / "skill" / "references" / "discovery-and-control.md",
            project_root / ".github" / "skills" / "neuro-cli" / "SKILL.md",
            project_root
            / ".github"
            / "skills"
            / "neuro-cli"
            / "references"
            / "workflows.md",
        ]
        parser = neuro_cli.build_parser()
        parsed_commands = 0

        for path in checked_paths:
            text = path.read_text(encoding="utf-8")
            for cli_args in extract_wrapper_cli_args(text):
                self.assertNotIn("--output", cli_args, str(path))
                parser.parse_args(["--output", "json"] + cli_args)
                parsed_commands += 1

        self.assertGreater(parsed_commands, len(neuro_cli.WORKFLOW_PLANS))

    def test_monitor_app_events_accepts_handler_options(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            [
                "--output",
                "json",
                "monitor",
                "app-events",
                "--app-id",
                "neuro_unit_app",
                "--handler-command",
                "printf ok",
                "--handler-timeout",
                "2",
                "--handler-max-output-bytes",
                "4",
                "--max-events",
                "1",
            ]
        )

        self.assertIs(args.handler, neuro_cli.handle_app_events)
        self.assertEqual(args.handler_command, "printf ok")
        self.assertEqual(args.handler_timeout, 2)
        self.assertEqual(args.handler_max_output_bytes, 4)
        self.assertEqual(args.max_events, 1)

    def test_execute_event_handler_runs_python_file_with_event_stdin(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".py") as handler:
            handler.write(
                "import json, sys\n"
                "event = json.load(sys.stdin)\n"
                "print(event['keyexpr'])\n"
            )
            handler.flush()
            args = Namespace(
                handler_python=handler.name,
                handler_command="",
                handler_timeout=2.0,
                handler_cwd="",
                handler_max_event_bytes=1024,
                handler_max_output_bytes=1024,
            )

            result = neuro_cli.execute_event_handler(
                args, {"keyexpr": "neuro/unit-01/event/app/demo/callback", "payload": {}}
            )

        self.assertIsNotNone(result)
        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("cwd", result)
        self.assertGreater(result["event_bytes"], 0)
        self.assertFalse(result["stdout_truncated"])
        self.assertIn("neuro/unit-01/event/app/demo/callback", result["stdout"])

    def test_execute_event_handler_bounds_output_and_records_audit(self) -> None:
        args = Namespace(
            handler_python="",
            handler_command="printf abcdef",
            handler_timeout=2.0,
            handler_cwd="",
            handler_max_event_bytes=1024,
            handler_max_output_bytes=3,
        )

        result = neuro_cli.execute_event_handler(
            args, {"keyexpr": "neuro/unit-01/event/demo", "payload": {}}
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stdout"], "abc")
        self.assertEqual(result["stdout_bytes"], 6)
        self.assertTrue(result["stdout_truncated"])
        self.assertEqual(result["max_output_bytes"], 3)

    def test_execute_event_handler_rejects_large_payload(self) -> None:
        args = Namespace(
            handler_python="handler.py",
            handler_command="",
            handler_timeout=2.0,
            handler_cwd="",
            handler_max_event_bytes=8,
            handler_max_output_bytes=1024,
        )

        result = neuro_cli.execute_event_handler(
            args, {"keyexpr": "neuro/unit-01/event/demo", "payload": {"value": "large"}}
        )

        self.assertIsNotNone(result)
        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "payload_too_large")
        self.assertGreater(result["event_bytes"], result["max_event_bytes"])

    def test_app_callback_smoke_accepts_handler_options(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            [
                "app-callback-smoke",
                "--app-id",
                "neuro_demo_app",
                "--handler-command",
                "printf ok",
                "--handler-max-output-bytes",
                "5",
            ]
        )

        self.assertIs(args.handler, neuro_cli.handle_app_callback_smoke)
        self.assertEqual(args.handler_command, "printf ok")
        self.assertEqual(args.handler_max_output_bytes, 5)

    def test_handle_update_rollback_uses_protected_write_mode(self) -> None:
        args = Namespace(
            stage="rollback",
            node="unit-01",
            app_id="neuro_demo_app",
            timeout=10,
            reason="operator requested",
        )
        payload = {
            "request_id": "req-1",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
            "priority": 50,
            "idempotency_key": "idem-1",
            "lease_id": "lease-1",
        }

        with mock.patch.object(neuro_cli, "protected_write_payload", return_value=dict(payload)) as pwp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_update(None, args)

        self.assertEqual(code, 0)
        pwp.assert_called_once_with(args)
        validate.assert_called_once()
        validate_args = validate.call_args[0]
        self.assertEqual(validate_args[1], "protected")
        self.assertEqual(validate_args[0]["reason"], "operator requested")
        send.assert_called_once()
        self.assertEqual(
            send.call_args[0][1],
            "neuro/unit-01/update/app/neuro_demo_app/rollback",
        )

    def test_parser_parses_app_callback_config(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            [
                "app-callback-config",
                "--app-id",
                "neuro_demo_app",
                "--lease-id",
                "lease-1",
                "--mode",
                "on",
                "--trigger-every",
                "2",
                "--event-name",
                "notify",
            ]
        )
        self.assertIs(args.handler, neuro_cli.handle_app_callback_config)
        self.assertEqual(args.mode, "on")
        self.assertEqual(args.trigger_every, 2)
        self.assertEqual(args.event_name, "notify")

    def test_parser_parses_app_callback_smoke(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(
            [
                "app-callback-smoke",
                "--app-id",
                "neuro_demo_app",
                "--event-name",
                "notify",
                "--trigger-every",
                "1",
                "--invoke-count",
                "3",
            ]
        )
        self.assertIs(args.handler, neuro_cli.handle_app_callback_smoke)
        self.assertEqual(args.app_id, "neuro_demo_app")
        self.assertEqual(args.event_name, "notify")
        self.assertEqual(args.trigger_every, 1)
        self.assertEqual(args.invoke_count, 3)

    def test_handle_app_callback_config_uses_invoke_path(self) -> None:
        args = Namespace(
            node="unit-01",
            app_id="neuro_demo_app",
            lease_id="lease-1",
            mode="on",
            trigger_every=3,
            event_name="notify",
            timeout=10,
        )
        payload = {
            "request_id": "req-1",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
            "priority": 50,
            "idempotency_key": "idem-1",
            "lease_id": "lease-1",
        }

        with mock.patch.object(neuro_cli, "protected_write_payload", return_value=dict(payload)) as pwp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_app_callback_config(None, args)

        self.assertEqual(code, 0)
        pwp.assert_called_once_with(args)
        validate.assert_called_once()
        sent_payload = send.call_args[0][2]
        self.assertEqual(send.call_args[0][1], "neuro/unit-01/cmd/app/neuro_demo_app/invoke")
        self.assertTrue(sent_payload["callback_enabled"])
        self.assertEqual(sent_payload["trigger_every"], 3)
        self.assertEqual(sent_payload["event_name"], "notify")

    def test_handle_query_payload_contract(self) -> None:
        args = Namespace(
            node="unit-01",
            kind="device",
            timeout=10,
        )
        payload = {
            "request_id": "req-query",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
        }

        with mock.patch.object(neuro_cli, "base_payload", return_value=dict(payload)) as bp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_query(None, args)

        self.assertEqual(code, 0)
        bp.assert_called_once_with(args)
        validate.assert_called_once_with(payload, "common")
        send.assert_called_once()
        self.assertEqual(send.call_args[0][1], "neuro/unit-01/query/device")
        self.assertEqual(send.call_args[0][2], payload)

    def test_handle_lease_acquire_payload_contract(self) -> None:
        args = Namespace(
            node="unit-01",
            resource="app/neuro_unit_app/control",
            lease_id="lease-1",
            ttl_ms=60000,
            timeout=10,
            priority=70,
        )
        payload = {
            "request_id": "req-lease",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
            "priority": 70,
            "idempotency_key": "idem-lease",
        }

        with mock.patch.object(neuro_cli, "write_payload", return_value=dict(payload)) as wp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_lease_acquire(None, args)

        self.assertEqual(code, 0)
        wp.assert_called_once_with(args)
        validate.assert_called_once()
        validate_args = validate.call_args[0]
        self.assertEqual(validate_args[1], "write")
        sent_payload = send.call_args[0][2]
        self.assertEqual(send.call_args[0][1], "neuro/unit-01/cmd/lease/acquire")
        self.assertEqual(sent_payload["resource"], "app/neuro_unit_app/control")
        self.assertEqual(sent_payload["lease_id"], "lease-1")
        self.assertEqual(sent_payload["ttl_ms"], 60000)
        self.assertEqual(sent_payload["priority"], 70)

    def test_handle_lease_release_payload_contract(self) -> None:
        args = Namespace(
            node="unit-01",
            lease_id="lease-1",
            timeout=10,
        )
        payload = {
            "request_id": "req-release",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
            "priority": 50,
            "idempotency_key": "idem-release",
            "lease_id": "lease-1",
        }

        with mock.patch.object(neuro_cli, "protected_write_payload", return_value=dict(payload)) as pwp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_lease_release(None, args)

        self.assertEqual(code, 0)
        pwp.assert_called_once_with(args)
        validate.assert_called_once_with(payload, "protected")
        send.assert_called_once()
        self.assertEqual(send.call_args[0][1], "neuro/unit-01/cmd/lease/release")
        self.assertEqual(send.call_args[0][2], payload)

    def test_handle_app_invoke_payload_contract_with_args_json(self) -> None:
        args = Namespace(
            node="unit-01",
            app_id="neuro_unit_app",
            command="invoke",
            lease_id="lease-1",
            args_json='{"mode":"pulse","count":2}',
            timeout=10,
        )
        payload = {
            "request_id": "req-app",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
            "priority": 50,
            "idempotency_key": "idem-app",
            "lease_id": "lease-1",
        }

        with mock.patch.object(neuro_cli, "protected_write_payload", return_value=dict(payload)) as pwp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_app_invoke(None, args)

        self.assertEqual(code, 0)
        pwp.assert_called_once_with(args)
        validate.assert_called_once()
        validate_args = validate.call_args[0]
        self.assertEqual(validate_args[1], "protected")
        sent_payload = send.call_args[0][2]
        self.assertEqual(send.call_args[0][1], "neuro/unit-01/cmd/app/neuro_unit_app/invoke")
        self.assertEqual(sent_payload["args"], {"mode": "pulse", "count": 2})

    def test_build_prepare_payload_contract(self) -> None:
        with tempfile.NamedTemporaryFile() as artifact:
            artifact.write(b"abcd")
            artifact.flush()
            args = Namespace(
                node="unit-01",
                app_id="neuro_unit_app",
                file=artifact.name,
                chunk_size=256,
            )
            payload = {"request_id": "req-prepare"}

            updated, provider = neuro_cli.build_prepare_payload(payload, args)

        self.assertIs(updated, payload)
        self.assertIsNotNone(provider)
        self.assertEqual(updated["transport"], "zenoh")
        self.assertEqual(updated["artifact_key"], "neuro/artifact/unit-01/neuro_unit_app")
        self.assertEqual(updated["size"], 4)
        self.assertEqual(updated["chunk_size"], 256)

    def test_handle_update_verify_payload_contract(self) -> None:
        args = Namespace(
            stage="verify",
            node="unit-01",
            app_id="neuro_unit_app",
            timeout=10,
            start_args=None,
            reason=None,
        )
        payload = {
            "request_id": "req-verify",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
        }

        with mock.patch.object(neuro_cli, "base_payload", return_value=dict(payload)) as bp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_update(None, args)

        self.assertEqual(code, 0)
        bp.assert_called_once_with(args)
        validate.assert_called_once_with(payload, "common")
        send.assert_called_once()
        self.assertEqual(
            send.call_args[0][1],
            "neuro/unit-01/update/app/neuro_unit_app/verify",
        )
        self.assertEqual(send.call_args[0][2], payload)

    def test_handle_update_activate_payload_contract(self) -> None:
        args = Namespace(
            stage="activate",
            node="unit-01",
            app_id="neuro_unit_app",
            lease_id="lease-1",
            timeout=10,
            start_args="--demo",
            reason=None,
        )
        payload = {
            "request_id": "req-activate",
            "source_core": "core-cli",
            "source_agent": "rational",
            "target_node": "unit-01",
            "timeout_ms": 10000,
            "priority": 50,
            "idempotency_key": "idem-activate",
            "lease_id": "lease-1",
        }

        with mock.patch.object(neuro_cli, "protected_write_payload", return_value=dict(payload)) as pwp, \
            mock.patch.object(neuro_cli, "validate_payload") as validate, \
            mock.patch.object(neuro_cli, "send_query", return_value=0) as send:
            code = neuro_cli.handle_update(None, args)

        expected_payload = dict(payload)
        expected_payload["start_args"] = "--demo"
        self.assertEqual(code, 0)
        pwp.assert_called_once_with(args)
        validate.assert_called_once_with(expected_payload, "protected")
        send.assert_called_once()
        self.assertEqual(
            send.call_args[0][1],
            "neuro/unit-01/update/app/neuro_unit_app/activate",
        )
        self.assertEqual(send.call_args[0][2], expected_payload)

    def test_handle_app_events_uses_app_scoped_subscription(self) -> None:
        class _Payload:
            def to_string(self) -> str:
                return '{"value":1}'

        class _Sample:
            key_expr = "neuro/unit-01/event/app/neuro_demo_app/callback"
            payload = _Payload()

        class _Subscriber:
            def undeclare(self) -> None:
                return None

        session = mock.Mock()
        def _declare_subscriber(keyexpr, callback):
            callback(_Sample())
            return _Subscriber()

        session.declare_subscriber.side_effect = _declare_subscriber
        args = Namespace(node="unit-01", app_id="neuro_demo_app", duration=1, output="json")

        out = io.StringIO()
        with mock.patch.object(neuro_cli.time, "sleep", return_value=None):
            with mock.patch.object(neuro_cli, "wait_for_callback_events", return_value=None):
                with redirect_stdout(out):
                    code = neuro_cli.handle_app_events(session, args)

        self.assertEqual(code, 0)
        call_args = session.declare_subscriber.call_args[0]
        self.assertEqual(call_args[0], "neuro/unit-01/event/app/neuro_demo_app/**")
        self.assertTrue(callable(call_args[1]))
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["subscription"], "neuro/unit-01/event/app/neuro_demo_app/**")
        self.assertEqual(payload["events"][0]["payload"], {"value": 1})

    def test_handle_app_events_writes_ready_file(self) -> None:
        class _Subscriber:
            def undeclare(self) -> None:
                return None

        session = mock.Mock()
        session.declare_subscriber.return_value = _Subscriber()

        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = f"{tmpdir}/listener-ready.json"
            args = Namespace(
                node="unit-01",
                app_id="neuro_demo_app",
                duration=1,
                output="json",
                ready_file=ready_file,
            )

            out = io.StringIO()
            with mock.patch.object(neuro_cli.time, "sleep", return_value=None):
                with mock.patch.object(neuro_cli, "wait_for_callback_events", return_value=None):
                    with redirect_stdout(out):
                        code = neuro_cli.handle_app_events(session, args)

            self.assertEqual(code, 0)
            self.assertTrue(Path(ready_file).is_file())
            ready_payload = json.loads(Path(ready_file).read_text(encoding="utf-8"))
            self.assertTrue(ready_payload["ready"])
            self.assertEqual(
                ready_payload["subscription"],
                "neuro/unit-01/event/app/neuro_demo_app/**",
            )

    def test_handle_app_events_sets_ready_after_settle_delay(self) -> None:
        class _Subscriber:
            def undeclare(self) -> None:
                return None

        session = mock.Mock()
        session.declare_subscriber.return_value = _Subscriber()

        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = f"{tmpdir}/listener-ready.json"
            args = Namespace(
                node="unit-01",
                app_id="neuro_demo_app",
                duration=1,
                output="json",
                ready_file=ready_file,
            )

            def _sleep(delay: float) -> None:
                self.assertEqual(delay, neuro_cli.EVENT_SUBSCRIPTION_READY_DELAY_SEC)
                self.assertFalse(Path(ready_file).exists())

            out = io.StringIO()
            with mock.patch.object(neuro_cli.time, "sleep", side_effect=_sleep):
                with mock.patch.object(neuro_cli, "wait_for_callback_events", return_value=None) as wait:
                    with mock.patch.object(neuro_cli, "collect_subscriber_events") as collect:
                        with redirect_stdout(out):
                            code = neuro_cli.handle_app_events(session, args)

            self.assertEqual(code, 0)
            collect.assert_not_called()
            wait.assert_called_once_with(session, args)
            self.assertTrue(Path(ready_file).is_file())

    def test_handle_app_events_uses_plain_subscriber_fallback(self) -> None:
        class _Subscriber:
            def undeclare(self) -> None:
                return None

        session = mock.Mock()
        subscriber = _Subscriber()
        args = Namespace(
            node="unit-01",
            app_id="neuro_demo_app",
            duration=1,
            output="json",
            ready_file="",
        )

        out = io.StringIO()
        with mock.patch.object(
            neuro_cli,
            "declare_event_subscriber",
            return_value=(subscriber, False, "plain_subscriber"),
        ) as declare_subscriber, mock.patch.object(
            neuro_cli.time,
            "sleep",
            return_value=None,
        ), mock.patch.object(
            neuro_cli,
            "collect_subscriber_events_threaded",
            return_value=None,
        ) as collect_threaded, redirect_stdout(out):
            code = neuro_cli.handle_app_events(session, args)

        self.assertEqual(code, 0)
        declare_subscriber.assert_called_once_with(
            session,
            "neuro/unit-01/event/app/neuro_demo_app/**",
            [],
            args,
            "APP_EVT",
            prefer_callback=True,
        )
        collect_threaded.assert_called_once_with(
            subscriber,
            [],
            args,
            "APP_EVT",
            session=session,
            pump_session=True,
        )
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["listener_mode"], "plain_subscriber")
        self.assertEqual(payload["events"], [])

    def test_append_event_row_decodes_cbor_payload_for_json_evidence(self) -> None:
        class _Payload:
            def __init__(self) -> None:
                self.raw = neuro_protocol.encode_payload_cbor(
                    {
                        "node_id": "unit-01",
                        "app_id": "neuro_demo_app",
                        "stage": "activate",
                        "status": "ok",
                        "detail": "app running",
                    },
                    "update_event",
                )

            def to_bytes(self) -> bytes:
                return self.raw

            def to_string(self) -> str:
                raise AssertionError("CBOR sample should not be parsed as text")

        sample = Namespace(
            key_expr="neuro/unit-01/event/update",
            payload=_Payload(),
        )
        args = Namespace(output="json")
        event_rows: list[dict] = []

        neuro_cli.append_event_row(event_rows, sample, args, "EVT")

        self.assertEqual(len(event_rows), 1)
        self.assertEqual(event_rows[0]["payload_encoding"], "cbor-v2")
        self.assertTrue(event_rows[0]["payload_hex"])
        self.assertEqual(event_rows[0]["payload"]["message_kind"], "update_event")
        self.assertEqual(event_rows[0]["payload"]["detail"], "app running")

    def test_handle_app_events_undeclares_subscriber_on_keyboard_interrupt(self) -> None:
        class _Subscriber:
            def __init__(self) -> None:
                self.undeclare_calls = 0

            def undeclare(self) -> None:
                self.undeclare_calls += 1

        session = mock.Mock()
        subscriber = _Subscriber()
        args = Namespace(
            node="unit-01",
            app_id="neuro_demo_app",
            duration=1,
            output="json",
            ready_file="",
        )

        out = io.StringIO()
        with mock.patch.object(
            neuro_cli,
            "declare_event_subscriber",
            return_value=(subscriber, False, "plain_subscriber"),
        ), mock.patch.object(
            neuro_cli.time,
            "sleep",
            return_value=None,
        ), mock.patch.object(
            neuro_cli,
            "collect_subscriber_events_threaded",
            side_effect=KeyboardInterrupt,
        ), redirect_stdout(out):
            code = neuro_cli.handle_app_events(session, args)

        self.assertEqual(code, 0)
        self.assertEqual(subscriber.undeclare_calls, 1)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["events"], [])

    def test_handle_app_callback_smoke_returns_failed_result_on_query_error(self) -> None:
        class _Subscriber:
            def __init__(self) -> None:
                self.undeclare_calls = 0

            def undeclare(self) -> None:
                self.undeclare_calls += 1

        session = mock.Mock()
        subscriber = _Subscriber()
        session.declare_subscriber.return_value = subscriber
        args = Namespace(
            node="unit-01",
            app_id="neuro_demo_app",
            lease_id="",
            ttl_ms=60000,
            trigger_every=1,
            event_name="notify",
            invoke_count=2,
            settle_sec=0.0,
            timeout=10.0,
            priority=50,
            output="json",
            request_id="req-1",
            idempotency_key="idem-1",
            source_core="core-cli",
            source_agent="rational",
            query_retries=1,
            query_retry_backoff_ms=0,
            query_retry_backoff_max_ms=0,
        )
        query_failure = {
            "ok": False,
            "status": "no_reply",
            "payload": {"request_id": "req-1"},
            "replies": [],
        }
        release_success = {
            "ok": True,
            "payload": {"status": "ok"},
            "replies": [{"ok": True, "payload": {"status": "ok"}}],
        }

        out = io.StringIO()
        with mock.patch.object(neuro_cli.time, "sleep", return_value=None), \
            mock.patch.object(neuro_cli, "base_payload", return_value={"request_id": "req-1"}), \
            mock.patch.object(neuro_cli, "protected_write_payload", return_value={"lease_id": "lease-1"}), \
            mock.patch.object(neuro_cli, "write_payload", return_value={"request_id": "req-1"}), \
            mock.patch.object(neuro_cli, "validate_payload"), \
            mock.patch.object(
                neuro_cli,
                "collect_query_result_with_retry",
                side_effect=[query_failure, release_success],
            ), \
            redirect_stdout(out):
            code = neuro_cli.handle_app_callback_smoke(session, args)

        self.assertEqual(code, 2)
        self.assertEqual(subscriber.undeclare_calls, 1)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["subscription"], "neuro/unit-01/event/app/neuro_demo_app/**")
        self.assertEqual(payload["steps"][0]["step"], "query_device")
        self.assertEqual(payload["steps"][1]["step"], "lease_release")
        self.assertEqual(payload["events"], [])

    def test_handle_app_callback_smoke_runs_success_sequence(self) -> None:
        class _Payload:
            def to_string(self) -> str:
                return '{"callback":"ok"}'

        class _Sample:
            key_expr = "neuro/unit-01/event/app/neuro_demo_app/callback"
            payload = _Payload()

        class _Subscriber:
            def __init__(self) -> None:
                self.undeclare_calls = 0

            def undeclare(self) -> None:
                self.undeclare_calls += 1

        session = mock.Mock()
        subscriber = _Subscriber()

        def _declare_subscriber(keyexpr, listener):
            listener(_Sample())
            return subscriber

        session.declare_subscriber.side_effect = _declare_subscriber
        args = Namespace(
            node="unit-01",
            app_id="neuro_demo_app",
            lease_id="lease-1",
            ttl_ms=60000,
            trigger_every=1,
            event_name="notify",
            invoke_count=2,
            settle_sec=0.0,
            timeout=10.0,
            priority=50,
            output="json",
            request_id="req-1",
            idempotency_key="idem-1",
            source_core="core-cli",
            source_agent="rational",
            query_retries=1,
            query_retry_backoff_ms=0,
            query_retry_backoff_max_ms=0,
        )
        success = {
            "ok": True,
            "payload": {"status": "ok"},
            "replies": [{"ok": True, "payload": {"status": "ok"}}],
        }

        out = io.StringIO()
        with mock.patch.object(neuro_cli.time, "sleep", return_value=None), \
            mock.patch.object(neuro_cli, "validate_payload"), \
            mock.patch.object(
                neuro_cli,
                "collect_query_result_with_retry",
                side_effect=[success, success, success, success, success, success],
            ), \
            redirect_stdout(out):
            code = neuro_cli.handle_app_callback_smoke(session, args)

        self.assertEqual(code, 0)
        self.assertEqual(subscriber.undeclare_calls, 1)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["subscription"],
            "neuro/unit-01/event/app/neuro_demo_app/**",
        )
        self.assertEqual(payload["events"][0]["payload"], {"callback": "ok"})
        self.assertEqual(
            [step["step"] for step in payload["steps"]],
            [
                "query_device",
                "lease_acquire",
                "app_callback_config",
                "app_invoke_1",
                "app_invoke_2",
                "lease_release",
            ],
        )

class TestNeuroCliQueryResults(unittest.TestCase):
    def test_parse_reply_ok_json_contract(self) -> None:
        class _Payload:
            def to_string(self) -> str:
                return '{"status":"ok","request_id":"req-1"}'

        class _Ok:
            key_expr = "neuro/unit-01/query/device"
            payload = _Payload()

        class _Reply:
            ok = _Ok()

        parsed = neuro_cli.parse_reply(_Reply())

        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["keyexpr"], "neuro/unit-01/query/device")
        self.assertEqual(parsed["payload"], {"status": "ok", "request_id": "req-1"})

    def test_collect_query_result_contract_marks_payload_status_error(self) -> None:
        session = mock.Mock()
        payload = {"request_id": "req-err"}

        with mock.patch.object(
            neuro_cli,
            "parse_reply",
            return_value={
                "ok": True,
                "keyexpr": "neuro/unit-01/cmd/app/neuro_unit_app/invoke",
                "payload": {"status": "error", "status_code": 409},
            },
        ):
            session.get.return_value = [object()]
            result = neuro_cli.collect_query_result_with_retry(
                session,
                "neuro/unit-01/cmd/app/neuro_unit_app/invoke",
                payload,
                10.0,
                neuro_cli.RetryPolicy(1, 0.0, 0.0),
                Namespace(output="json"),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error_reply")
        self.assertEqual(result["replies"][0]["payload"]["status_code"], 409)

    def test_collect_query_result_contract_preserves_parse_failed_status(self) -> None:
        session = mock.Mock()
        payload = {"request_id": "req-parse"}

        with mock.patch.object(
            neuro_cli,
            "parse_reply",
            return_value={
                "ok": False,
                "status": "parse_failed",
                "keyexpr": "neuro/unit-01/query/device",
                "payload": "<unreadable ok payload>",
                "error": "truncated CBOR value",
            },
        ):
            session.get.return_value = [object()]
            result = neuro_cli.collect_query_result_with_retry(
                session,
                "neuro/unit-01/query/device",
                payload,
                10.0,
                neuro_cli.RetryPolicy(3, 0.0, 0.0),
                Namespace(output="json"),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "parse_failed")
        self.assertEqual(result["failure_status"], "parse_failed")
        self.assertEqual(result["attempt"], 1)

    def test_collect_query_result_sends_cbor_payload_bytes(self) -> None:
        session = mock.Mock()
        session.get.return_value = []
        payload = {
            "request_id": "req-1",
            "source_core": "core",
            "source_agent": "agent",
            "target_node": "unit-01",
            "timeout_ms": 1000,
        }

        result = neuro_cli.collect_query_result(
            session, "neuro/unit-01/query/device", payload, 10.0
        )

        sent_payload = session.get.call_args.kwargs["payload"]
        self.assertIsInstance(sent_payload, bytes)
        self.assertEqual(
            neuro_protocol.decode_payload_cbor(sent_payload)["message_kind"],
            "query_request",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "no_reply")

    def test_app_invoke_and_callback_config_use_distinct_cbor_kinds(self) -> None:
        base_payload = {
            "request_id": "req-1",
            "source_core": "core",
            "source_agent": "agent",
            "target_node": "unit-01",
            "timeout_ms": 1000,
            "priority": 60,
            "idempotency_key": "idem-1",
            "lease_id": "lease-1",
        }
        keyexpr = "neuro/unit-01/cmd/app/neuro_unit_app/invoke"

        app_command = neuro_protocol.decode_payload_cbor(
            neuro_protocol.encode_query_payload(keyexpr, dict(base_payload))
        )
        callback_config = neuro_protocol.decode_payload_cbor(
            neuro_protocol.encode_query_payload(
                keyexpr,
                {
                    **base_payload,
                    "callback_enabled": True,
                    "trigger_every": 2,
                    "event_name": "tick",
                },
            )
        )

        self.assertEqual(app_command["message_kind"], "app_command_request")
        self.assertEqual(
            callback_config["message_kind"], "callback_config_request"
        )

    def test_send_query_retries_transient_no_reply(self) -> None:
        session = mock.Mock()
        args = Namespace(
            dry_run=False,
            output="json",
            query_retries=2,
            query_retry_backoff_ms=0,
            query_retry_backoff_max_ms=0,
        )

        transient = {
            "ok": False,
            "status": "no_reply",
            "keyexpr": "neuro/unit-01/query/device",
            "payload": {"request_id": "req-1"},
            "replies": [],
        }
        success = {
            "ok": True,
            "keyexpr": "neuro/unit-01/query/device",
            "payload": {"request_id": "req-1"},
            "replies": [{"ok": True, "keyexpr": "neuro/unit-01/query/device", "payload": {"status": "ok"}}],
        }

        with mock.patch.object(
            neuro_cli,
            "collect_query_result",
            side_effect=[transient, success],
        ) as collect_once:
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.send_query(
                    session,
                    "neuro/unit-01/query/device",
                    {"request_id": "req-1"},
                    10.0,
                    args,
                )

        self.assertEqual(code, 0)
        self.assertEqual(collect_once.call_count, 2)
        payload = json.loads(out.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["retried"])

    def test_send_query_returns_error_when_no_replies(self) -> None:
        session = mock.Mock()
        session.get.return_value = []
        args = Namespace(dry_run=False, output="json")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.send_query(session, "neuro/unit-01/query/device", {"request_id": "req-1"}, 10.0, args)

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no_reply")

    def test_send_query_returns_error_when_reply_contains_error(self) -> None:
        session = mock.Mock()
        args = Namespace(dry_run=False, output="json")

        with mock.patch.object(
            neuro_cli,
            "parse_reply",
            return_value={"ok": False, "payload": "unit error"},
        ):
            session.get.return_value = [object()]
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.send_query(
                    session,
                    "neuro/unit-01/query/device",
                    {"request_id": "req-1"},
                    10.0,
                    args,
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error_reply")

    def test_send_query_returns_error_when_payload_status_is_error(self) -> None:
        session = mock.Mock()
        args = Namespace(dry_run=False, output="json", query_retries=1)

        with mock.patch.object(
            neuro_cli,
            "collect_query_result",
            return_value={
                "ok": True,
                "keyexpr": "neuro/unit-01/cmd/app/neuro_demo_app/invoke",
                "payload": {"request_id": "req-1"},
                "replies": [
                    {
                        "ok": True,
                        "keyexpr": "neuro/unit-01/cmd/app/neuro_demo_app/invoke",
                        "payload": {"status": "error", "status_code": 403},
                    }
                ],
            },
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                code = neuro_cli.send_query(
                    session,
                    "neuro/unit-01/cmd/app/neuro_demo_app/invoke",
                    {"request_id": "req-1"},
                    10.0,
                    args,
                )

        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error_reply")

    def test_capabilities_includes_event_stream(self) -> None:
        args = Namespace(output="json")
        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_capabilities(None, args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        names = {item["name"] for item in payload["capabilities"]}
        self.assertIn("event_stream", names)
        self.assertIn("app_event_stream", names)

    def test_capabilities_reports_release_1_2_6(self) -> None:
        args = Namespace(output="json")
        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_capabilities(None, args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["release_target"], "1.2.6")

    def test_open_session_with_retry_retries_once(self) -> None:
        args = Namespace(
            output="json",
            session_open_retries=2,
            session_open_backoff_ms=0,
        )

        fake_session = mock.Mock()
        with mock.patch.object(
            neuro_cli.zenoh,
            "open",
            side_effect=[RuntimeError("transient open failure"), fake_session],
        ) as open_mock:
            session = neuro_cli.open_session_with_retry(args)

        self.assertIs(session, fake_session)
        self.assertEqual(open_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()