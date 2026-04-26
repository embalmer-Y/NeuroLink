import io
import json
from pathlib import Path
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
    fake.open = lambda config=None: None
    fake.init_log_from_env_or = lambda level: None
    sys.modules["zenoh"] = fake


_install_fake_zenoh()

THIS_DIR = Path(__file__).resolve().parent
NEURO_CLI_DIR = THIS_DIR.parent
SRC_DIR = NEURO_CLI_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import neuro_cli
import neuro_protocol


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


class TestNeuroCliParserAndPlaceholders(unittest.TestCase):
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
        self.assertEqual(payload["release_target"], "1.1.5")
        self.assertEqual(payload["protocol"]["version"], "2.0")
        self.assertEqual(payload["protocol"]["wire_encoding"], "json-v2")
        self.assertEqual(payload["protocol"]["supported_wire_encodings"], ["json-v2"])
        self.assertEqual(payload["protocol"]["planned_wire_encodings"], ["cbor-v2"])
        self.assertFalse(payload["protocol"]["cbor_v2_enabled"])
        self.assertTrue(payload["agent_skill"]["structured_stdout"])
        self.assertEqual(
            payload["agent_skill"]["callback_handler_execution"],
            "opt_in_subprocess",
        )
        self.assertIn("capabilities", payload)

    def test_parser_parses_system_init_without_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "system", "init"])

        self.assertIs(args.handler, neuro_cli.handle_init)
        self.assertFalse(args.requires_session)

    def test_init_diagnostics_reports_workspace_scripts(self) -> None:
        args = Namespace(output="json")

        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_init(None, args)

        payload = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["protocol"]["wire_encoding"], "json-v2")
        self.assertFalse(payload["shell_setup"]["can_modify_parent_shell"])
        self.assertTrue(payload["scripts"]["setup_neurolink_env.sh"]["exists"])

    def test_parser_parses_workflow_plan_without_session(self) -> None:
        parser = neuro_cli.build_parser()
        args = parser.parse_args(["--output", "json", "workflow", "plan", "app-build"])

        self.assertIs(args.handler, neuro_cli.handle_workflow_plan)
        self.assertFalse(args.requires_session)
        self.assertEqual(args.workflow, "app-build")

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
        self.assertIn("preflight_neurolink_linux.sh", payload["commands"][0])

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
                "--max-events",
                "1",
            ]
        )

        self.assertIs(args.handler, neuro_cli.handle_app_events)
        self.assertEqual(args.handler_command, "printf ok")
        self.assertEqual(args.handler_timeout, 2)
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
            )

            result = neuro_cli.execute_event_handler(
                args, {"keyexpr": "neuro/unit-01/event/app/demo/callback", "payload": {}}
            )

        self.assertIsNotNone(result)
        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["returncode"], 0)
        self.assertIn("neuro/unit-01/event/app/demo/callback", result["stdout"])

    def test_execute_event_handler_rejects_large_payload(self) -> None:
        args = Namespace(
            handler_python="handler.py",
            handler_command="",
            handler_timeout=2.0,
            handler_cwd="",
            handler_max_event_bytes=8,
        )

        result = neuro_cli.execute_event_handler(
            args, {"keyexpr": "neuro/unit-01/event/demo", "payload": {"value": "large"}}
        )

        self.assertIsNotNone(result)
        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "payload_too_large")

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
        declare_subscriber.assert_called_once()
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

    def test_capabilities_reports_release_1_1_5(self) -> None:
        args = Namespace(output="json")
        out = io.StringIO()
        with redirect_stdout(out):
            code = neuro_cli.handle_capabilities(None, args)

        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["release_target"], "1.1.5")

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