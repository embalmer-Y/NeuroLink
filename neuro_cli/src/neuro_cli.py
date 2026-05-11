import argparse
from dataclasses import dataclass
import glob
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, cast

import zenoh

from neuro_agent_contracts import (
    AGENT_EVENTS_SCHEMA_VERSION,
    AGENT_RUNTIME_SCHEMA_VERSION,
    CANONICAL_SKILL_RELATIVE_PATH,
    NEURO_CLI_WRAPPER_RELATIVE_PATH,
    PROJECT_SHARED_SKILL_RELATIVE_PATH,
    PROJECT_SKILL_RELATIVE_PATH,
    STATE_SYNC_SCHEMA_VERSION,
    TOOL_MANIFEST_SCHEMA_VERSION,
    build_agent_event_rows,
    build_agent_runtime_metadata,
    build_protocol_metadata,
    build_tool_manifest_payload,
    resolve_neurolink_path,
)
from neuro_workflow_contracts import (
    build_workflow_plan_payload,
    build_workflow_surface as build_workflow_surface_payload,
    workflow_agent_metadata as build_workflow_agent_metadata,
)
from neuro_workflow_catalog import (
    WORKFLOW_METADATA_DEFAULTS,
    WORKFLOW_PLAN_METADATA,
    WORKFLOW_PLANS,
)
import neuro_protocol as protocol


DEFAULT_CHUNK_SIZE = 1024
DEFAULT_PRIORITY = 50
RELEASE_TARGET = "2.2.2"
EVENT_SUBSCRIPTION_READY_DELAY_SEC = 1.0
EVENT_SUBSCRIPTION_PUMP_INTERVAL_SEC = 1.0
DEFAULT_SESSION_OPEN_RETRIES = 3
DEFAULT_SESSION_OPEN_BACKOFF_MS = 500
DEFAULT_QUERY_RETRIES = 3
DEFAULT_QUERY_RETRY_BACKOFF_MS = 250
DEFAULT_QUERY_RETRY_BACKOFF_MAX_MS = 2000
DEFAULT_HANDLER_TIMEOUT_SEC = 5.0
DEFAULT_HANDLER_MAX_EVENT_BYTES = 65536
DEFAULT_HANDLER_MAX_OUTPUT_BYTES = 16384
PAYLOAD_FAILURE_STATUSES = {
    "error",
    "not_implemented",
    "invalid_input",
    "query_failed",
    "no_reply",
    "error_reply",
    "parse_failed",
    "session_open_failed",
    "handler_failed",
    "serial_dependency_missing",
    "serial_device_missing",
    "serial_open_failed",
    "serial_timeout",
    "shell_error",
    "endpoint_verify_failed",
}
WORKFLOW_PLAN_SCHEMA_VERSION = "1.1.8-workflow-plan-v1"
DEFAULT_SERIAL_BAUDRATE = 115200
DEFAULT_SERIAL_TIMEOUT_SEC = 5.0
DEFAULT_SERIAL_SETTLE_SEC = 0.2


def release_label(suffix: str) -> str:
    return f"release-{RELEASE_TARGET}-{suffix}"


def default_app_echo() -> str:
    return f"neuro_unit_app-{RELEASE_TARGET}-cbor-v2"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    initial_backoff_sec: float
    max_backoff_sec: float


def compute_backoff(policy: RetryPolicy, attempt_index: int) -> float:
    if policy.max_attempts <= 1:
        return 0.0

    attempt_index = max(0, attempt_index)
    backoff = policy.initial_backoff_sec * (2 ** attempt_index)
    return min(policy.max_backoff_sec, backoff)


def query_retry_policy_from_args(args: argparse.Namespace) -> RetryPolicy:
    max_attempts = max(1, int(getattr(args, "query_retries", 1)))
    initial_backoff_sec = max(
        0.0, float(getattr(args, "query_retry_backoff_ms", 0)) / 1000.0
    )
    max_backoff_sec = max(
        initial_backoff_sec,
        float(getattr(args, "query_retry_backoff_max_ms", 0)) / 1000.0,
    )
    return RetryPolicy(
        max_attempts=max_attempts,
        initial_backoff_sec=initial_backoff_sec,
        max_backoff_sec=max_backoff_sec,
    )


def session_open_retry_policy_from_args(args: argparse.Namespace) -> RetryPolicy:
    max_attempts = max(1, int(getattr(args, "session_open_retries", 1)))
    initial_backoff_sec = max(
        0.0, float(getattr(args, "session_open_backoff_ms", 0)) / 1000.0
    )
    return RetryPolicy(
        max_attempts=max_attempts,
        initial_backoff_sec=initial_backoff_sec,
        max_backoff_sec=initial_backoff_sec,
    )


def open_session_with_retry(args: argparse.Namespace) -> zenoh.Session:
    policy = session_open_retry_policy_from_args(args)
    output_mode = getattr(args, "output", "human")
    last_exc: Exception | None = None

    for attempt in range(policy.max_attempts):
        try:
            return zenoh.open(zenoh.Config())
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= policy.max_attempts:
                break
            backoff = compute_backoff(policy, attempt)
            if output_mode == "human":
                print(
                    ".. zenoh session open failed "
                    f"(attempt {attempt + 1}/{policy.max_attempts}): {exc}; "
                    f"retrying in {backoff:.2f}s"
                )
            if backoff > 0:
                time.sleep(backoff)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("failed to open zenoh session")


CAPABILITY_MATRIX = protocol.CAPABILITY_MATRIX


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def print_jsonl(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


def emit_result(
    args: argparse.Namespace, result: dict[str, Any], success_message: str
) -> int:
    if args.output == "json":
        print_json(result)
    elif result.get("ok"):
        print(success_message)
    else:
        print(f"error: {result.get('status', 'error')}: {result.get('error', '')}")
    return 0 if result.get("ok", False) else 2


def make_request_id() -> str:
    return protocol.make_request_id()


def make_idempotency_key() -> str:
    return protocol.make_idempotency_key()


def import_serial_module() -> tuple[Any | None, str]:
    try:
        import serial  # type: ignore[import-not-found]
    except Exception as exc:
        return None, str(exc)

    return serial, ""


def discover_serial_devices() -> list[dict[str, str]]:
    serial_module, _error = import_serial_module()
    devices: list[dict[str, str]] = []

    tools = getattr(serial_module, "tools", None) if serial_module is not None else None
    list_ports = getattr(tools, "list_ports", None) if tools is not None else None
    comports: Any = getattr(list_ports, "comports", None) if list_ports is not None else None
    if comports is None and serial_module is not None:
        try:
            from serial.tools import list_ports as imported_list_ports  # type: ignore[import-not-found]

            comports = imported_list_ports.comports
        except Exception:
            comports = None
    if callable(comports):
        try:
            for port in cast(Any, comports)():
                device = getattr(port, "device", "")
                if device:
                    devices.append(
                        {
                            "device": device,
                            "description": getattr(port, "description", ""),
                            "hwid": getattr(port, "hwid", ""),
                            "source": "pyserial",
                        }
                    )
        except Exception:
            devices = []

    if not devices:
        for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
            for device in glob.glob(pattern):
                devices.append(
                    {
                        "device": device,
                        "description": "",
                        "hwid": "",
                        "source": "glob",
                    }
                )

    unique: dict[str, dict[str, str]] = {}
    for device in devices:
        unique[str(device["device"])] = device
    return [unique[name] for name in sorted(unique)]


def resolve_serial_port(args: argparse.Namespace) -> tuple[str, dict[str, Any] | None]:
    configured = getattr(args, "port", "")
    if configured:
        return configured, None

    devices = discover_serial_devices()
    if not devices:
        return "", {
            "ok": False,
            "status": "serial_device_missing",
            "error": "no serial device found; pass --port or attach a Unit UART device",
            "devices": [],
        }

    return str(devices[0]["device"]), None


def serial_read_text(serial_port: Any, timeout_sec: float) -> str:
    deadline = time.monotonic() + max(0.1, timeout_sec)
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        chunk = serial_port.read(256)
        if chunk:
            chunks.append(bytes(chunk))
            continue
        time.sleep(0.05)

    return b"".join(chunks).decode("utf-8", errors="replace")


def run_serial_shell_command(args: argparse.Namespace, command: str) -> dict[str, Any]:
    serial_module, import_error = import_serial_module()
    if serial_module is None:
        return {
            "ok": False,
            "status": "serial_dependency_missing",
            "error": f"pyserial is required for serial commands: {import_error}",
        }

    port, error = resolve_serial_port(args)
    if error is not None:
        return error

    baudrate = int(getattr(args, "baudrate", DEFAULT_SERIAL_BAUDRATE))
    timeout_sec = float(getattr(args, "serial_timeout", DEFAULT_SERIAL_TIMEOUT_SEC))
    settle_sec = float(getattr(args, "serial_settle_sec", DEFAULT_SERIAL_SETTLE_SEC))

    try:
        serial_port = serial_module.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.1,
            write_timeout=timeout_sec,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "serial_open_failed",
            "port": port,
            "baudrate": baudrate,
            "error": str(exc),
        }

    try:
        with serial_port:
            reset_input = getattr(serial_port, "reset_input_buffer", None)
            if callable(reset_input):
                reset_input()
            if settle_sec > 0:
                time.sleep(settle_sec)
            serial_port.write((command + "\r\n").encode("utf-8"))
            flush = getattr(serial_port, "flush", None)
            if callable(flush):
                flush()
            output = serial_read_text(serial_port, timeout_sec)
    except Exception as exc:
        return {
            "ok": False,
            "status": "serial_open_failed",
            "port": port,
            "baudrate": baudrate,
            "command": command,
            "error": str(exc),
        }

    if not output.strip():
        return {
            "ok": False,
            "status": "serial_timeout",
            "port": port,
            "baudrate": baudrate,
            "command": command,
            "timeout_sec": timeout_sec,
            "error": "no shell output received before timeout",
        }

    lowered = output.lower()
    if "error" in lowered or "failed" in lowered:
        return {
            "ok": False,
            "status": "shell_error",
            "port": port,
            "baudrate": baudrate,
            "command": command,
            "output": output,
            "error": "serial shell reported an error",
        }

    return {
        "ok": True,
        "status": "ok",
        "port": port,
        "baudrate": baudrate,
        "command": command,
        "output": output,
    }


def parse_zenoh_endpoint_from_shell(output: str) -> str:
    patterns = (
        "zenoh connect endpoint:",
        "zenoh connect override applied:",
        "zenoh connect override cleared:",
    )
    for line in output.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        for pattern in patterns:
            if pattern in lowered:
                return stripped.split(":", 1)[1].strip()
    return ""


def dump_reply(reply) -> None:
    try:
        payload = reply.ok.payload.to_string()
        print(f"<< OK  {reply.ok.key_expr}")
        try:
            print(json.dumps(json.loads(payload), indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(payload)
    except Exception:
        print("<< ERR")
        try:
            print(reply.err.payload.to_string())
        except Exception as exc:
            print(f"unreadable error payload: {exc}")


def parse_reply(reply) -> dict:
    return protocol.parse_reply(reply)


def query_payload_bytes(query: zenoh.Query) -> bytes:
    payload = query.payload
    if payload is None:
        return b""
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)

    to_bytes = getattr(payload, "to_bytes", None)
    if callable(to_bytes):
        return to_bytes()

    try:
        return bytes(payload)
    except TypeError:
        return str(payload).encode("utf-8")


def query_payload_json(query: zenoh.Query) -> dict:
    payload = query_payload_bytes(query)
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def build_artifact_key(node: str, app_id: str) -> str:
    return protocol.artifact_route(node, app_id)


class ArtifactProvider:
    def __init__(self, keyexpr: str, file_path: Path, chunk_size: int):
        self.session = None
        self.keyexpr = keyexpr
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.queryable = None

    def __enter__(self):
        self.session = zenoh.open(zenoh.Config())
        self.queryable = self.session.declare_queryable(self.keyexpr, self.handle_query)
        print(f">> PROVIDER READY {self.keyexpr}")
        time.sleep(1.0)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.queryable is not None:
            self.queryable.undeclare()
            self.queryable = None
        if self.session is not None:
            self.session.close()
            self.session = None
        return False

    def handle_query(self, query: zenoh.Query) -> None:
        try:
            request = query_payload_json(query)
            offset = int(request.get("offset", 0))
            requested = int(request.get("chunk_size", self.chunk_size))
            print(f">> ARTIFACT GET {self.keyexpr} offset={offset} requested={requested}")
            if offset < 0 or requested <= 0:
                query.reply_err(json.dumps({"message": "invalid offset or chunk_size"}))
                return

            total_size = self.file_path.stat().st_size
            if offset > total_size:
                query.reply_err(json.dumps({"message": "offset out of range"}))
                return

            length = min(requested, total_size - offset)
            with self.file_path.open("rb") as fp:
                fp.seek(offset)
                data = fp.read(length)

            query.reply(self.keyexpr, data)
            print(f"<< ARTIFACT CHUNK {self.keyexpr} offset={offset} bytes={len(data)}")
        except Exception as exc:
            print(f"<< ARTIFACT ERR {self.keyexpr}: {exc}")
            query.reply_err(json.dumps({"message": str(exc)}))


def build_prepare_payload(
    payload: dict, args: argparse.Namespace
) -> tuple[dict, ArtifactProvider | None]:
    file_path = Path(args.file).expanduser()
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()

    if not file_path.is_file():
        raise FileNotFoundError(f"artifact file not found: {file_path}")

    chunk_size = max(1, int(args.chunk_size))
    keyexpr = build_artifact_key(args.node, args.app_id)
    payload.update(
        {
            "transport": "zenoh",
            "artifact_key": keyexpr,
            "size": file_path.stat().st_size,
            "chunk_size": chunk_size,
        }
    )
    return payload, ArtifactProvider(keyexpr, file_path, chunk_size)


def emit_placeholder(args: argparse.Namespace, capability: str, command_name: str) -> int:
    item = CAPABILITY_MATRIX.get(capability, {})
    message = item.get("note", "not implemented on Unit yet")
    result = {
        "ok": False,
        "status": "not_implemented",
        "command": command_name,
        "capability": capability,
        "resource": item.get("resource", "unknown"),
        "message": message,
    }
    if args.output == "json":
        print_json(result)
    else:
        print(f"!! {command_name} not implemented")
        print_json(result)
    return 3


def find_neurolink_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (candidate / "neuro_cli" / "src" / "neuro_cli.py").is_file() and (
            candidate / "scripts" / "setup_neurolink_env.sh"
        ).is_file():
            return candidate
        nested = candidate / "applocation" / "NeuroLink"
        if (nested / "neuro_cli" / "src" / "neuro_cli.py").is_file() and (
            nested / "scripts" / "setup_neurolink_env.sh"
        ).is_file():
            return nested
    return None


def build_agent_skill_metadata(neurolink_root: Path | None) -> dict:
    canonical_path = resolve_neurolink_path(
        neurolink_root, CANONICAL_SKILL_RELATIVE_PATH
    )
    project_shared_path = resolve_neurolink_path(
        neurolink_root, PROJECT_SHARED_SKILL_RELATIVE_PATH
    )
    wrapper_path = resolve_neurolink_path(
        neurolink_root, NEURO_CLI_WRAPPER_RELATIVE_PATH
    )
    return {
        "name": "neuro-cli",
        "canonical_path": str(canonical_path),
        "canonical_exists": canonical_path.is_file(),
        "project_shared_path": str(project_shared_path),
        "project_shared_exists": project_shared_path.is_file(),
        "discovery_adapter_path": str(project_shared_path),
        "wrapper": str(wrapper_path),
        "wrapper_exists": wrapper_path.is_file(),
        "structured_stdout": True,
        "source_of_truth": "canonical",
        "callback_handler_execution": "explicit_audited_runner",
    }


def extract_first_reply_payload(result: dict[str, Any]) -> dict[str, Any]:
    for reply in result.get("replies", []):
        if not isinstance(reply, dict):
            continue
        payload = reply.get("payload")
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def summarize_state_sync_query(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(result.get("ok", False)),
        "status": str(result.get("status", "unknown")),
        "attempt": int(result.get("attempt", 1)),
        "max_attempts": int(result.get("max_attempts", 1)),
        "retried": bool(result.get("retried", False)),
        "failure_status": result.get("failure_status", ""),
        "payload": extract_first_reply_payload(result),
    }


def build_state_sync_recommendations(state: dict[str, dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    device = state["device"]
    apps = state["apps"]
    leases = state["leases"]

    if not device["ok"]:
        actions.append("rerun query device and verify router or Unit reachability before delegated control")
    elif device["payload"].get("network_state") not in (None, "", "NETWORK_READY"):
        actions.append("wait for NETWORK_READY before any side-effecting Unit workflow")

    if not apps["ok"]:
        actions.append("rerun query apps before app lifecycle or invoke operations")

    if not leases["ok"]:
        actions.append("rerun query leases before any lease-aware side-effecting command")
    elif leases["payload"].get("leases"):
        actions.append("review and release active leases before destructive or approval-required commands")

    if not actions:
        actions.append("state sync is clean; read-only delegated reasoning may continue")
    return actions


def collect_state_sync_query(
    session: zenoh.Session,
    args: argparse.Namespace,
    kind: str,
) -> dict[str, Any]:
    payload = base_payload(args)
    validate_payload(payload, "common")
    return collect_query_result_with_retry(
        session,
        protocol.query_route(args.node, kind),
        payload,
        args.timeout,
        query_retry_policy_from_args(args),
        args,
    )


def build_init_diagnostics(args: argparse.Namespace) -> dict:
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    scripts = {}
    script_names = [
        "setup_neurolink_env.sh",
        "build_neurolink.sh",
        "preflight_neurolink_linux.sh",
        "smoke_neurolink_linux.sh",
    ]
    for name in script_names:
        path = neurolink_root / "scripts" / name if neurolink_root else Path(name)
        scripts[name] = {
            "path": str(path),
            "exists": path.is_file(),
        }

    return {
        "ok": neurolink_root is not None,
        "status": "ready" if neurolink_root is not None else "workspace_not_found",
        "release_target": RELEASE_TARGET,
        "protocol": {
            **build_protocol_metadata(),
        },
        "workspace_root": str(workspace_root),
        "neurolink_root": str(neurolink_root) if neurolink_root else "",
        "python": sys.executable,
        "scripts": scripts,
        "shell_setup": {
            "can_modify_parent_shell": False,
            "recommended_command": "source applocation/NeuroLink/scripts/setup_neurolink_env.sh",
        },
        "agent_skill": build_agent_skill_metadata(neurolink_root),
        "agent_runtime": build_agent_runtime_metadata(neurolink_root),
        "agent_workflows": [
            "system tool-manifest --output json",
            "system state-sync --output json",
            "system capabilities --output json",
            "system init --output json",
            "monitor agent-events --output jsonl",
            "workflow plan setup-linux --output json",
            "workflow plan setup-windows --output json",
            "workflow plan discover-host --output json",
            "workflow plan discover-router --output json",
            "workflow plan discover-serial --output json",
            "workflow plan serial-discover --output json",
            "workflow plan serial-zenoh-config --output json",
            "workflow plan serial-zenoh-recover --output json",
            "workflow plan discover-device --output json",
            "workflow plan discover-apps --output json",
            "workflow plan discover-leases --output json",
            "workflow plan control-health --output json",
            "workflow plan control-deploy --output json",
            "workflow plan control-app-invoke --output json",
            "workflow plan control-callback --output json",
            "workflow plan control-monitor --output json",
            "workflow plan control-cleanup --output json",
            "workflow plan app-build --output json",
            "workflow plan preflight --output json",
            "deploy prepare --app-id <app> --file <artifact>",
            "lease acquire --resource app/<app>/control",
            "app invoke --app-id <app> --lease-id <lease>",
            "monitor app-events --app-id <app> --output json",
        ],
        "checks": {
            "run_unit_tests": "west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run",
            "run_cli_tests": "/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q",
            "build_unit_app": "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check",
            "preflight": "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text",
        },
    }


def handle_init(session: zenoh.Session | None, args: argparse.Namespace) -> int:
    del session
    result = build_init_diagnostics(args)
    if args.output == "json":
        print_json(result)
    else:
        print(f"NeuroLink workspace: {result['neurolink_root'] or 'not found'}")
        print(f"status: {result['status']}")
        print_json(result)
    return 0 if result.get("ok", False) else 2


def workflow_agent_metadata(workflow_name: str) -> dict:
    return build_workflow_agent_metadata(
        workflow_name,
        WORKFLOW_METADATA_DEFAULTS,
        WORKFLOW_PLAN_METADATA,
    )


def build_workflow_surface() -> dict:
    return build_workflow_surface_payload(
        WORKFLOW_PLANS,
        WORKFLOW_METADATA_DEFAULTS,
        WORKFLOW_PLAN_METADATA,
        WORKFLOW_PLAN_SCHEMA_VERSION,
    )


def build_workflow_plan(args: argparse.Namespace) -> dict:
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    return build_workflow_plan_payload(
        workflow_name=args.workflow,
        workflow_plans=WORKFLOW_PLANS,
        metadata_defaults=WORKFLOW_METADATA_DEFAULTS,
        plan_metadata=WORKFLOW_PLAN_METADATA,
        schema_version=WORKFLOW_PLAN_SCHEMA_VERSION,
        release_target=RELEASE_TARGET,
        protocol_metadata=build_protocol_metadata(),
        workspace_root=workspace_root,
        agent_skill=build_agent_skill_metadata(neurolink_root),
    )


def handle_workflow_plan(
    session: zenoh.Session | None, args: argparse.Namespace
) -> int:
    del session
    result = build_workflow_plan(args)
    if args.output == "json":
        print_json(result)
    else:
        print(f"workflow: {result['workflow']} ({result['category']})")
        for command in result["commands"]:
            print(command)
    return 0


def resolve_workspace_path(workspace_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return workspace_root / path


def relative_workspace_path(workspace_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


def handle_memory_layout_dump(
    session: zenoh.Session | None, args: argparse.Namespace
) -> int:
    del session
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    build_dir = resolve_workspace_path(workspace_root, args.build_dir).resolve()
    output_dir = resolve_workspace_path(workspace_root, args.output_dir).resolve()
    collector = neurolink_root / "scripts" / "collect_neurolink_memory_evidence.py"

    if not build_dir.is_dir() and not args.run_build:
        result = {
            "ok": False,
            "status": "build_dir_missing",
            "build_dir": relative_workspace_path(workspace_root, build_dir),
            "next_action": "run workflow plan unit-build before dumping static layout",
        }
        if args.output == "json":
            print_json(result)
        else:
            print(result["next_action"])
        return 2

    missing_inputs = []
    for status, path in (
        ("config_missing", build_dir / "zephyr" / ".config"),
        ("zephyr_stat_missing", build_dir / "zephyr" / "zephyr.stat"),
    ):
        if not path.is_file() and not args.run_build:
            missing_inputs.append(
                {"status": status, "path": relative_workspace_path(workspace_root, path)}
            )
    if missing_inputs:
        result = {
            "ok": False,
            "status": missing_inputs[0]["status"],
            "missing_inputs": missing_inputs,
            "build_dir": relative_workspace_path(workspace_root, build_dir),
            "next_action": "inspect the Unit build output and rebuild if needed",
        }
        if args.output == "json":
            print_json(result)
        else:
            print(result["next_action"])
        return 2

    command = [
        sys.executable,
        str(collector),
        "--build-dir",
        relative_workspace_path(workspace_root, build_dir),
        "--output-dir",
        relative_workspace_path(workspace_root, output_dir),
        "--label",
        args.label,
    ]
    if args.build_log:
        command.extend(["--build-log", args.build_log])
    if args.run_build:
        command.append("--run-build")
    if args.no_c_style_check:
        command.append("--no-c-style-check")

    proc = subprocess.run(
        command,
        cwd=workspace_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        result = {
            "ok": False,
            "status": "collector_failed",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        if args.output == "json":
            print_json(result)
        else:
            print(proc.stderr or proc.stdout)
        return proc.returncode

    artifact_paths: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        key, _, value = line.partition("=")
        if key == "memory_evidence_json":
            artifact_paths["json"] = value
        elif key == "memory_evidence_summary":
            artifact_paths["summary"] = value

    json_path_value = artifact_paths.get("json")
    if not json_path_value:
        result = {"ok": False, "status": "collector_output_missing", "stdout": proc.stdout}
        if args.output == "json":
            print_json(result)
        else:
            print("collector did not report memory_evidence_json")
        return 2

    json_path = Path(json_path_value)
    evidence = json.loads(json_path.read_text(encoding="utf-8"))
    result = {
        "ok": True,
        "status": "ok",
        "label": evidence.get("label"),
        "release_target": evidence.get("release_target"),
        "build_dir": evidence.get("build_dir"),
        "platform": evidence.get("platform", {}),
        "memory_capability": evidence.get("memory_capability", {}),
        "section_totals": evidence.get("section_totals", {}),
        "section_count": len(evidence.get("sections", [])),
        "artifacts": {
            name: relative_workspace_path(workspace_root, Path(path))
            for name, path in artifact_paths.items()
        },
    }
    if args.output == "json":
        print_json(result)
    else:
        print(f"memory layout: {result['status']}")
        print(f"json: {result['artifacts'].get('json')}")
        print(f"summary: {result['artifacts'].get('summary')}")
    return 0


def load_memory_evidence_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"parse_failed:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"parse_failed:{path}:expected object")
    return payload


def memory_section_deltas(
    baseline_totals: dict[str, Any], candidate_totals: dict[str, Any]
) -> dict[str, dict[str, int]]:
    deltas: dict[str, dict[str, int]] = {}
    for region in sorted(set(baseline_totals) | set(candidate_totals)):
        baseline_value = int(baseline_totals.get(region, 0) or 0)
        candidate_value = int(candidate_totals.get(region, 0) or 0)
        deltas[region] = {
            "baseline_bytes": baseline_value,
            "candidate_bytes": candidate_value,
            "delta_bytes": candidate_value - baseline_value,
        }
    return deltas


def build_llext_memory_config_plan(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    baseline_totals = baseline.get("section_totals", {})
    candidate_totals = candidate.get("section_totals", {})
    if not isinstance(baseline_totals, dict) or not isinstance(candidate_totals, dict):
        raise ValueError("parse_failed:section_totals must be objects")

    deltas = memory_section_deltas(baseline_totals, candidate_totals)
    internal_regions = ("dram0", "iram0")
    regressions = [
        {
            "region": region,
            "delta_bytes": deltas[region]["delta_bytes"],
            "status": "memory_regression",
        }
        for region in internal_regions
        if deltas.get(region, {}).get("delta_bytes", 0) > 0
    ]
    runtime_gate = candidate.get("runtime_evidence_gate", {})
    runtime_gate_passed = (
        isinstance(runtime_gate, dict) and runtime_gate.get("passed") is True
    )
    candidate_config = candidate.get("config", {})
    if not isinstance(candidate_config, dict):
        candidate_config = {}
    dynamic_heap_enabled = candidate_config.get("CONFIG_LLEXT_HEAP_DYNAMIC") == "y"
    static_layout_ok = len(regressions) == 0
    dynamic_heap_safe = not dynamic_heap_enabled or runtime_gate_passed
    promotion_allowed = static_layout_ok and runtime_gate_passed and dynamic_heap_safe
    status = "ok"
    if not static_layout_ok:
        status = "memory_regression"
    elif dynamic_heap_enabled and not runtime_gate_passed:
        status = "runtime_heap_dynamic_unsafe"

    if dynamic_heap_enabled and not runtime_gate_passed:
        next_action = "add explicit llext_heap_init wiring before hardware promotion"
    elif static_layout_ok:
        next_action = "candidate can proceed to hardware runtime validation"
    else:
        next_action = "reject or revise the candidate before hardware runtime validation"

    return {
        "ok": True,
        "status": status,
        "baseline_layout": {
            "status": "ok",
            "label": baseline.get("label"),
            "release_target": baseline.get("release_target"),
        },
        "candidate_layout": {
            "status": "ok",
            "label": candidate.get("label"),
            "release_target": candidate.get("release_target"),
        },
        "section_deltas": deltas,
        "static_regressions": regressions,
        "memory_capability": candidate.get("memory_capability", {}),
        "config": candidate_config,
        "dynamic_heap_enabled": dynamic_heap_enabled,
        "runtime_evidence_gate": runtime_gate,
        "promotion_allowed": promotion_allowed,
        "promotion_blockers": [] if promotion_allowed else [
            blocker
            for blocker in (
                None if static_layout_ok else "memory_regression",
                None if dynamic_heap_safe else "runtime_heap_dynamic_unsafe",
                None if runtime_gate_passed else "runtime_evidence_required",
            )
            if blocker is not None
        ],
        "next_action": next_action,
    }


def handle_llext_memory_config_plan(
    session: zenoh.Session | None, args: argparse.Namespace
) -> int:
    del session
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    baseline_path = resolve_workspace_path(workspace_root, args.baseline_json).resolve()
    candidate_path = resolve_workspace_path(workspace_root, args.candidate_json).resolve()

    for status, path in (
        ("baseline_layout_missing", baseline_path),
        ("candidate_layout_missing", candidate_path),
    ):
        if not path.is_file():
            result = {
                "ok": False,
                "status": status,
                "path": relative_workspace_path(workspace_root, path),
                "next_action": "run memory layout-dump for the missing layout evidence",
            }
            if args.output == "json":
                print_json(result)
            else:
                print(result["next_action"])
            return 2

    try:
        baseline = load_memory_evidence_json(baseline_path)
        candidate = load_memory_evidence_json(candidate_path)
        result = build_llext_memory_config_plan(baseline, candidate)
    except ValueError as exc:
        result = {"ok": False, "status": "parse_failed", "error": str(exc)}
        if args.output == "json":
            print_json(result)
        else:
            print(f"parse failed: {exc}")
        return 2

    result["artifacts"] = {
        "baseline_json": relative_workspace_path(workspace_root, baseline_path),
        "candidate_json": relative_workspace_path(workspace_root, candidate_path),
    }
    if args.output == "json":
        print_json(result)
    else:
        print(f"llext memory config: {result['status']}")
        print(f"promotion_allowed: {result['promotion_allowed']}")
    return 0 if result["status"] == "ok" else 2


def validate_payload(payload: dict, mode: str) -> None:
    protocol.validate_payload(payload, mode)


def collect_query_result(
    session: zenoh.Session,
    keyexpr: str,
    payload: dict,
    timeout: float,
) -> dict:
    payload_bytes = protocol.encode_query_payload(keyexpr, payload)

    try:
        replies = session.get(keyexpr, payload=payload_bytes, timeout=timeout)
        parsed_replies = [parse_reply(reply) for reply in replies]
    except Exception as exc:
        return {
            "ok": False,
            "status": "query_failed",
            "keyexpr": keyexpr,
            "error": str(exc),
        }

    if not parsed_replies:
        return {
            "ok": False,
            "status": "no_reply",
            "keyexpr": keyexpr,
            "payload": payload,
            "replies": [],
        }

    result = {
        "ok": all(item["ok"] for item in parsed_replies),
        "keyexpr": keyexpr,
        "payload": payload,
        "replies": parsed_replies,
    }
    if not result["ok"]:
        if any(item.get("status") == "parse_failed" for item in parsed_replies):
            result["status"] = "parse_failed"
        else:
            result["status"] = "error_reply"
    return result


def collect_query_result_with_retry(
    session: zenoh.Session,
    keyexpr: str,
    payload: dict,
    timeout: float,
    retry_policy: RetryPolicy,
    args: argparse.Namespace,
) -> dict:
    output_mode = getattr(args, "output", "human")
    attempts = max(1, retry_policy.max_attempts)
    last_result: dict | None = None

    for attempt in range(attempts):
        result = collect_query_result(session, keyexpr, payload, timeout)
        result["attempt"] = attempt + 1
        result["max_attempts"] = attempts
        last_result = result

        failure_status = result_failure_status(result)
        if failure_status is not None and result.get("status") not in (
            "no_reply",
            "query_failed",
            "parse_failed",
        ):
            result["ok"] = False
            result["status"] = "error_reply"
            result["failure_status"] = failure_status
            result["retried"] = attempt > 0
            return result

        if result.get("ok", False):
            result["retried"] = attempt > 0
            return result

        status = result.get("status", "")
        retryable = status in ("no_reply", "query_failed")
        if not retryable or attempt + 1 >= attempts:
            if failure_status is not None:
                result["failure_status"] = failure_status
            result["retried"] = attempt > 0
            return result

        backoff = compute_backoff(retry_policy, attempt)
        if output_mode == "human":
            print(
                ".. query retry due to transient status "
                f"'{status}' ({attempt + 1}/{attempts}) for {keyexpr}; "
                f"backoff={backoff:.2f}s"
            )
        if backoff > 0:
            time.sleep(backoff)

    return last_result or {
        "ok": False,
        "status": "query_failed",
        "keyexpr": keyexpr,
        "payload": payload,
        "error": "retry logic exhausted without result",
        "attempt": attempts,
        "max_attempts": attempts,
        "retried": attempts > 1,
    }


def result_has_reply_error(result: dict) -> bool:
    return result_failure_status(result) is not None


def result_failure_status(result: dict) -> str | None:
    if not result.get("ok", False):
        status = result.get("status")
        if payload_status_is_failure(status):
            return str(status)
        return "payload_not_ok"

    for reply in result.get("replies", []):
        if not reply.get("ok", True):
            return "error_reply"
        payload = reply.get("payload")
        if isinstance(payload, dict):
            status = payload.get("status")
            if payload_status_is_failure(status):
                return str(status)

    return None


def payload_status_is_failure(status: object) -> bool:
    if status is None:
        return False

    return str(status) in PAYLOAD_FAILURE_STATUSES


def result_has_expected_app_echo(result: dict, expected_echo: str) -> bool:
    if not expected_echo:
        return True

    for reply in result.get("replies", []):
        payload = reply.get("payload")
        if isinstance(payload, dict) and payload.get("echo") == expected_echo:
            return True

    result["expected_app_echo"] = expected_echo
    result["app_echo_match"] = False
    return False


def send_query(
    session: zenoh.Session,
    keyexpr: str,
    payload: dict,
    timeout: float,
    args: argparse.Namespace,
) -> int:
    if args.dry_run:
        dry_run_data = {
            "ok": True,
            "dry_run": True,
            "keyexpr": keyexpr,
            "payload": payload,
            "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
            "encoded_payload_hex": protocol.encode_query_payload(
                keyexpr, payload
            ).hex(),
            "timeout": timeout,
        }
        if args.output == "json":
            print_json(dry_run_data)
        else:
            print(f">> DRY-RUN GET {keyexpr}")
            print_json(payload)
        return 0

    if args.output == "human":
        print(f">> GET {keyexpr}")
        print_json(payload)

    retry_policy = query_retry_policy_from_args(args)
    result = collect_query_result_with_retry(
        session,
        keyexpr,
        payload,
        timeout,
        retry_policy,
        args,
    )

    if not result.get("ok", False) and result.get("status") == "query_failed":
        if args.output == "json":
            print_json(result)
        else:
            print(f"<< ERR query failed: {result['error']}")
        return 2

    if result.get("status") == "no_reply":
        if args.output == "json":
            print_json(result)
        else:
            print(f"<< ERR no reply for {keyexpr}")
            print_json(payload)
        return 2

    if args.output == "json":
        print_json(result)
        return 0 if result.get("ok", False) else 2

    for item in result.get("replies", []):
        if item["ok"]:
            print(f"<< OK  {item['keyexpr']}")
            if isinstance(item["payload"], (dict, list)):
                print_json(item["payload"])
            else:
                print(item["payload"])
        else:
            print("<< ERR")
            print(item["payload"])
    return 0 if result.get("ok", False) else 2


def base_payload(args: argparse.Namespace) -> dict:
    return protocol.base_payload(args)


def write_payload(args: argparse.Namespace) -> dict:
    return protocol.write_payload(args)


def protected_write_payload(args: argparse.Namespace) -> dict:
    return protocol.protected_write_payload(args)


def handle_query(session: zenoh.Session, args: argparse.Namespace) -> int:
    payload = base_payload(args)
    validate_payload(payload, "common")
    return send_query(
        session,
        protocol.query_route(args.node, args.kind),
        payload,
        args.timeout,
        args,
    )


def handle_lease_acquire(session: zenoh.Session, args: argparse.Namespace) -> int:
    payload = write_payload(args)
    payload.update(
        {
            "resource": args.resource,
            "lease_id": args.lease_id,
            "priority": args.priority,
            "ttl_ms": args.ttl_ms,
        }
    )
    validate_payload(payload, "write")
    return send_query(
        session,
        protocol.lease_route(args.node, "acquire"),
        payload,
        args.timeout,
        args,
    )


def handle_lease_release(session: zenoh.Session, args: argparse.Namespace) -> int:
    payload = protected_write_payload(args)
    validate_payload(payload, "protected")
    return send_query(
        session,
        protocol.lease_route(args.node, "release"),
        payload,
        args.timeout,
        args,
    )


def handle_app_control(session: zenoh.Session, args: argparse.Namespace) -> int:
    payload = protected_write_payload(args)
    start_args = getattr(args, "start_args", "")
    if start_args:
        payload["start_args"] = start_args
    validate_payload(payload, "protected")
    return send_query(
        session,
        protocol.app_command_route(args.node, args.app_id, args.action),
        payload,
        args.timeout,
        args,
    )


def handle_app_invoke(session: zenoh.Session, args: argparse.Namespace) -> int:
    payload = protected_write_payload(args)
    if args.args_json:
        try:
            payload["args"] = json.loads(args.args_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--args-json is not valid JSON: {exc}") from exc

    validate_payload(payload, "protected")
    return send_query(
        session,
        protocol.app_command_route(args.node, args.app_id, args.command),
        payload,
        args.timeout,
        args,
    )


def handle_app_callback_config(
    session: zenoh.Session, args: argparse.Namespace
) -> int:
    payload = build_app_callback_config_payload(args)

    validate_payload(payload, "protected")
    return send_query(
        session,
        app_callback_invoke_key(args.node, args.app_id),
        payload,
        args.timeout,
        args,
    )


def app_callback_invoke_key(node: str, app_id: str) -> str:
    return protocol.app_command_route(node, app_id, "invoke")


def args_with_lease_id(args: argparse.Namespace, lease_id: str) -> argparse.Namespace:
    values = vars(args).copy()
    values.pop("lease_id", None)
    return argparse.Namespace(**values, lease_id=lease_id)


def build_app_callback_config_payload(
    args: argparse.Namespace, enabled: bool | None = None
) -> dict:
    payload = protected_write_payload(args)
    callback_enabled = args.mode == "on" if enabled is None else enabled
    payload["callback_enabled"] = callback_enabled
    payload["trigger_every"] = max(0, int(args.trigger_every))
    payload["event_name"] = args.event_name
    return payload


def build_app_callback_lease_payload(
    args: argparse.Namespace, lease_id: str
) -> tuple[argparse.Namespace, dict]:
    lease_args = args_with_lease_id(args, lease_id)
    payload = write_payload(lease_args)
    payload.update(
        {
            "resource": f"app/{args.app_id}/control",
            "lease_id": lease_id,
            "priority": args.priority,
            "ttl_ms": args.ttl_ms,
        }
    )
    return lease_args, payload


def collect_app_callback_smoke_step(
    session: zenoh.Session,
    args: argparse.Namespace,
    step_results: list[dict],
    name: str,
    keyexpr: str,
    payload: dict,
) -> dict:
    result = collect_query_result_with_retry(
        session,
        keyexpr,
        payload,
        args.timeout,
        query_retry_policy_from_args(args),
        args,
    )
    step_results.append({"step": name, "result": result})
    return result


def release_app_callback_smoke_lease(
    session: zenoh.Session,
    args: argparse.Namespace,
    lease_args: argparse.Namespace,
    step_results: list[dict],
) -> None:
    release_payload = protected_write_payload(lease_args)
    validate_payload(release_payload, "protected")
    collect_app_callback_smoke_step(
        session,
        args,
        step_results,
        "lease_release",
        protocol.lease_route(args.node, "release"),
        release_payload,
    )


def handle_update(session: zenoh.Session, args: argparse.Namespace) -> int:
    provider = None
    mode = "common"
    if args.stage == "prepare":
        mode = "write"
    elif args.stage in ("activate", "rollback", "delete"):
        mode = "protected"

    if mode == "write":
        payload = write_payload(args)
    elif mode == "protected":
        payload = protected_write_payload(args)
    else:
        payload = base_payload(args)

    if args.stage == "prepare":
        payload, provider = build_prepare_payload(payload, args)

    if getattr(args, "start_args", None):
        payload["start_args"] = args.start_args

    if getattr(args, "reason", None):
        payload["reason"] = args.reason

    validate_payload(payload, mode)

    if provider is not None:
        if args.output == "human":
            print(
                f">> PROVIDE {provider.keyexpr} from {provider.file_path} "
                f"chunk={provider.chunk_size}"
            )
        with provider:
            return send_query(
                session,
                protocol.update_route(args.node, args.app_id, args.stage),
                payload,
                args.timeout,
                args,
            )
    return send_query(
        session,
        protocol.update_route(args.node, args.app_id, args.stage),
        payload,
        args.timeout,
        args,
    )
def handle_placeholder(session: zenoh.Session, args: argparse.Namespace) -> int:
    del session
    return emit_placeholder(args, args.placeholder_capability, args.placeholder_name)


def wait_for_subscription_window(duration: int) -> None:
    time.sleep(EVENT_SUBSCRIPTION_READY_DELAY_SEC)

    if duration > 0:
        time.sleep(duration)
        return

    while True:
        time.sleep(1)


def write_subscription_ready(args: argparse.Namespace, keyexpr: str) -> None:
    ready_file = getattr(args, "ready_file", "")
    if not ready_file:
        return

    ready_path = Path(ready_file)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.write_text(
        json.dumps({"subscription": keyexpr, "ready": True}, ensure_ascii=False),
        encoding="utf-8",
    )


def event_limit_reached(event_rows: list[dict], args: argparse.Namespace) -> bool:
    max_events = int(getattr(args, "max_events", 0) or 0)
    return max_events > 0 and len(event_rows) >= max_events


def resolve_handler_cwd(args: argparse.Namespace) -> Path:
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    configured = getattr(args, "handler_cwd", "") or str(workspace_root)
    cwd = Path(configured).expanduser()
    if not cwd.is_absolute():
        cwd = (workspace_root / cwd).resolve()
    else:
        cwd = cwd.resolve()

    try:
        cwd.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ValueError("handler cwd must stay within workspace root") from exc

    return cwd


def build_handler_argv(args: argparse.Namespace) -> list[str]:
    handler_python = getattr(args, "handler_python", "")
    handler_command = getattr(args, "handler_command", "")
    if handler_python:
        return [sys.executable, handler_python]
    if handler_command:
        return shlex.split(handler_command)
    return []


def bounded_text(value: str | bytes | None, max_bytes: int) -> tuple[str, bool, int]:
    if value is None:
        return "", False, 0
    if isinstance(value, bytes):
        raw = value
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
        raw = value.encode("utf-8")

    if len(raw) <= max_bytes:
        return text, False, len(raw)

    truncated = raw[:max(0, max_bytes)]
    return truncated.decode("utf-8", errors="replace"), True, len(raw)


def execute_event_handler(args: argparse.Namespace, event: dict) -> dict | None:
    argv = build_handler_argv(args)
    if not argv:
        return None

    event_text = json.dumps(event, ensure_ascii=False)
    event_bytes = len(event_text.encode("utf-8"))
    max_bytes = int(
        getattr(args, "handler_max_event_bytes", DEFAULT_HANDLER_MAX_EVENT_BYTES)
    )
    max_output_bytes = int(
        getattr(args, "handler_max_output_bytes", DEFAULT_HANDLER_MAX_OUTPUT_BYTES)
    )
    timeout_sec = float(getattr(args, "handler_timeout", DEFAULT_HANDLER_TIMEOUT_SEC))
    try:
        cwd = resolve_handler_cwd(args)
    except Exception as exc:
        return {
            "enabled": True,
            "executed": False,
            "status": "handler_error",
            "argv": argv,
            "cwd": "",
            "error": str(exc),
        }

    if event_bytes > max_bytes:
        return {
            "enabled": True,
            "executed": False,
            "status": "payload_too_large",
            "argv": argv,
            "cwd": str(cwd),
            "event_bytes": event_bytes,
            "max_event_bytes": max_bytes,
        }

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            input=event_text,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            cwd=str(cwd),
            shell=False,
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_truncated, stdout_bytes = bounded_text(
            completed.stdout, max_output_bytes
        )
        stderr, stderr_truncated, stderr_bytes = bounded_text(
            completed.stderr, max_output_bytes
        )
        return {
            "enabled": True,
            "executed": True,
            "status": "ok" if completed.returncode == 0 else "nonzero_exit",
            "argv": argv,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "duration_ms": duration_ms,
            "event_bytes": event_bytes,
            "max_event_bytes": max_bytes,
            "timeout_sec": timeout_sec,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "max_output_bytes": max_output_bytes,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_truncated, stdout_bytes = bounded_text(exc.stdout, max_output_bytes)
        stderr, stderr_truncated, stderr_bytes = bounded_text(exc.stderr, max_output_bytes)
        return {
            "enabled": True,
            "executed": True,
            "status": "timeout",
            "argv": argv,
            "cwd": str(cwd),
            "returncode": None,
            "duration_ms": duration_ms,
            "event_bytes": event_bytes,
            "max_event_bytes": max_bytes,
            "timeout_sec": timeout_sec,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_bytes": stdout_bytes,
            "stderr_bytes": stderr_bytes,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "max_output_bytes": max_output_bytes,
            "timeout": True,
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "enabled": True,
            "executed": False,
            "status": "handler_error",
            "argv": argv,
            "cwd": str(cwd),
            "duration_ms": duration_ms,
            "event_bytes": event_bytes,
            "max_event_bytes": max_bytes,
            "error": str(exc),
        }


def build_handler_audit(event_rows: list[dict]) -> dict:
    rows = [row.get("handler") for row in event_rows if isinstance(row.get("handler"), dict)]
    if not rows:
        return {"enabled": False, "executions": 0, "failures": 0, "statuses": {}}

    statuses: dict[str, int] = {}
    failures = 0
    for row in rows:
        status = str(row.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
        if status != "ok":
            failures += 1

    return {
        "enabled": True,
        "executions": len(rows),
        "failures": failures,
        "statuses": statuses,
    }


def append_event_row(
    event_rows: list[dict], sample: zenoh.Sample, args: argparse.Namespace, label: str
) -> None:
    parsed_payload, payload_encoding, payload_hex = protocol.parse_wire_payload(
        sample.payload
    )

    if args.output == "json":
        row = {
            "keyexpr": str(sample.key_expr),
            "payload": parsed_payload,
            "payload_encoding": payload_encoding,
        }
        if payload_encoding == "cbor-v2":
            row["payload_hex"] = payload_hex
        handler = execute_event_handler(args, row)
        if handler is not None:
            row["handler"] = handler
        event_rows.append(row)
        return

    print(f"<< {label} {sample.key_expr}")
    if isinstance(parsed_payload, (dict, list)):
        print(json.dumps(parsed_payload, indent=2, ensure_ascii=False))
    else:
        print(parsed_payload)
    handler = execute_event_handler(
        args,
        {
            "keyexpr": str(sample.key_expr),
            "payload": parsed_payload,
            "payload_encoding": payload_encoding,
        },
    )
    if handler is not None:
        print_json({"handler": handler})


def collect_subscriber_events(
    subscriber, event_rows: list[dict], args: argparse.Namespace, label: str
) -> None:
    if args.duration > 0:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            sample = None
            try_recv = getattr(subscriber, "try_recv", None)
            if callable(try_recv):
                sample = try_recv()
            if sample is None:
                time.sleep(0.05)
                continue
            append_event_row(event_rows, sample, args, label)
            if event_limit_reached(event_rows, args):
                return
        return

    recv = getattr(subscriber, "recv", None)
    while True:
        if callable(recv):
            sample = recv()
            if sample is not None:
                append_event_row(event_rows, sample, args, label)
                if event_limit_reached(event_rows, args):
                    return
            continue

        time.sleep(1)


def collect_subscriber_events_threaded(
    subscriber,
    event_rows: list[dict],
    args: argparse.Namespace,
    label: str,
    session: zenoh.Session | None = None,
    pump_session: bool = False,
) -> None:
    stop_event = threading.Event()
    worker_error: list[Exception] = []

    def worker() -> None:
        try_recv = getattr(subscriber, "try_recv", None)
        recv = getattr(subscriber, "recv", None)

        try:
            while not stop_event.is_set():
                sample = None
                if callable(try_recv):
                    sample = try_recv()
                    if sample is None:
                        time.sleep(0.05)
                        continue
                elif callable(recv):
                    sample = recv()
                    if sample is None:
                        time.sleep(0.05)
                        continue
                else:
                    time.sleep(0.05)
                    continue

                append_event_row(event_rows, sample, args, label)
                if event_limit_reached(event_rows, args):
                    stop_event.set()
                    return
        except Exception as exc:
            worker_error.append(exc)
            stop_event.set()

    thread = threading.Thread(
        target=worker,
        name="neurolink-event-listener",
        daemon=True,
    )
    thread.start()

    pump_interval_sec = max(
        0.1,
        float(
            getattr(
                args,
                "event_pump_interval_sec",
                EVENT_SUBSCRIPTION_PUMP_INTERVAL_SEC,
            )
        ),
    )
    next_pump_deadline = time.monotonic() + pump_interval_sec

    def maybe_pump() -> None:
        nonlocal next_pump_deadline
        if not pump_session or session is None:
            return

        now = time.monotonic()
        if now < next_pump_deadline:
            return

        next_pump_deadline = now + pump_interval_sec
        try:
            pump_event_listener_session(session, args)
        except Exception:
            # Listener capture must remain available even if the side-band pump fails.
            pass

    try:
        if args.duration > 0:
            deadline = time.monotonic() + args.duration
            while time.monotonic() < deadline and not stop_event.is_set():
                maybe_pump()
                time.sleep(0.05)

            if worker_error:
                raise worker_error[0]
            return

        while True:
            if stop_event.is_set() and worker_error:
                raise worker_error[0]
            maybe_pump()
            time.sleep(0.2)
    finally:
        stop_event.set()
        thread.join(timeout=1.0)


def pump_event_listener_session(
    session: zenoh.Session, args: argparse.Namespace
) -> None:
    try:
        query_args = argparse.Namespace(**vars(args))
        payload = base_payload(query_args)
        validate_payload(payload, "common")
        collect_query_result(
            session,
            protocol.query_route(args.node, "device"),
            payload,
            args.timeout,
        )
    except Exception:
        pass


def wait_for_callback_events(
    session: zenoh.Session, args: argparse.Namespace
) -> None:
    pump_interval_sec = max(
        0.1,
        float(
            getattr(
                args,
                "event_pump_interval_sec",
                EVENT_SUBSCRIPTION_PUMP_INTERVAL_SEC,
            )
        ),
    )

    if args.duration > 0:
        deadline = time.monotonic() + args.duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return

            time.sleep(min(pump_interval_sec, remaining))
            pump_event_listener_session(session, args)

    while True:
        time.sleep(pump_interval_sec)
        pump_event_listener_session(session, args)


def declare_event_subscriber(
    session: zenoh.Session,
    keyexpr: str,
    event_rows: list[dict],
    args: argparse.Namespace,
    label: str,
    prefer_callback: bool = False,
) -> tuple[object, bool, str]:
    handlers = getattr(zenoh, "handlers", None)
    fifo_cls = getattr(handlers, "FifoChannel", None) if handlers is not None else None
    callback_cls = getattr(handlers, "Callback", None) if handlers is not None else None

    if not prefer_callback and fifo_cls is not None:
        try:
            return session.declare_subscriber(keyexpr, fifo_cls(64)), False, "fifo_channel"
        except TypeError:
            pass

    subscriber_listener = lambda sample: append_event_row(event_rows, sample, args, label)
    callback_handler = subscriber_listener
    listener_mode = "callback"

    if callback_cls is not None:
        try:
            callback_handler = callback_cls(subscriber_listener, indirect=False)
            listener_mode = "callback_indirect_false"
        except TypeError:
            callback_handler = subscriber_listener
            listener_mode = "callback"

    try:
        return (
            session.declare_subscriber(keyexpr, callback_handler),
            True,
            listener_mode,
        )
    except TypeError:
        return session.declare_subscriber(keyexpr), False, "plain_subscriber"


def run_event_subscription(
    session: zenoh.Session,
    subscriber,
    use_callback_collection: bool,
    keyexpr: str,
    event_rows: list[dict],
    args: argparse.Namespace,
    label: str,
) -> None:
    time.sleep(EVENT_SUBSCRIPTION_READY_DELAY_SEC)
    write_subscription_ready(args, keyexpr)

    if use_callback_collection:
        wait_for_callback_events(session, args)
        return

    collect_subscriber_events_threaded(
        subscriber,
        event_rows,
        args,
        label,
        session=session,
        pump_session=True,
    )


def emit_event_subscription_result(
    args: argparse.Namespace,
    keyexpr: str,
    listener_mode: str,
    event_rows: list[dict],
) -> None:
    if args.output != "json":
        return

    print_json(
        {
            "ok": True,
            "subscription": keyexpr,
            "listener_mode": listener_mode,
            "handler_audit": build_handler_audit(event_rows),
            "events": event_rows,
        }
    )


def build_app_callback_smoke_result(
    subscription: str,
    event_rows: list[dict],
    step_results: list[dict],
    ok: bool | None = None,
) -> dict:
    if ok is None:
        ok = len(event_rows) > 0 and not any(
            result_has_reply_error(step["result"]) for step in step_results
        )

    return {
        "ok": ok,
        "subscription": subscription,
        "handler_audit": build_handler_audit(event_rows),
        "events": event_rows,
        "steps": step_results,
    }


def emit_app_callback_smoke_result(
    subscription: str,
    event_rows: list[dict],
    step_results: list[dict],
    ok: bool | None = None,
) -> int:
    result = build_app_callback_smoke_result(
        subscription,
        event_rows,
        step_results,
        ok=ok,
    )
    print_json(result)
    return 0 if result["ok"] else 2

def subscribe_to_events(
    session: zenoh.Session,
    keyexpr: str,
    args: argparse.Namespace,
    label: str,
    prefer_callback: bool = False,
) -> int:
    event_rows: list[dict] = []
    listener_mode = "unknown"

    if args.output == "human":
        print(f">> SUB {keyexpr} for {args.duration}s")

    subscriber = None
    use_callback_collection = False
    try:
        subscriber, use_callback_collection, listener_mode = declare_event_subscriber(
            session,
            keyexpr,
            event_rows,
            args,
            label,
            prefer_callback=prefer_callback,
        )
        run_event_subscription(
            session,
            subscriber,
            use_callback_collection,
            keyexpr,
            event_rows,
            args,
            label,
        )
    except KeyboardInterrupt:
        pass
    finally:
        if subscriber is not None:
            subscriber.undeclare()

    emit_event_subscription_result(args, keyexpr, listener_mode, event_rows)
    return 0


def handle_events(session: zenoh.Session, args: argparse.Namespace) -> int:
    return subscribe_to_events(
        session, protocol.event_subscription_route(args.node), args, "EVT"
    )


def handle_app_events(session: zenoh.Session, args: argparse.Namespace) -> int:
    return subscribe_to_events(
        session,
        protocol.app_event_subscription_route(args.node, args.app_id),
        args,
        "APP_EVT",
        prefer_callback=True,
    )


def handle_app_callback_smoke(
    session: zenoh.Session, args: argparse.Namespace
) -> int:
    subscription = protocol.app_event_subscription_route(args.node, args.app_id)
    event_rows: list[dict] = []
    lease_id = args.lease_id or f"smoke-{uuid.uuid4().hex[:8]}"
    lease_args = args_with_lease_id(args, lease_id)
    subscriber = None
    use_callback_collection = False
    step_results: list[dict] = []
    forced_ok: bool | None = None

    subscriber, use_callback_collection, _listener_mode = declare_event_subscriber(
        session,
        subscription,
        event_rows,
        args,
        "APP_EVT",
        prefer_callback=True,
    )
    try:
        time.sleep(EVENT_SUBSCRIPTION_READY_DELAY_SEC + args.settle_sec)

        query_args = argparse.Namespace(**vars(args))
        query_payload = base_payload(query_args)
        validate_payload(query_payload, "common")
        if result_has_reply_error(
            collect_app_callback_smoke_step(
                session,
                args,
                step_results,
                "query_device",
                protocol.query_route(args.node, "device"),
                query_payload,
            )
        ):
            forced_ok = False

        lease_args, lease_payload = build_app_callback_lease_payload(args, lease_id)
        if forced_ok is None:
            validate_payload(lease_payload, "write")
            if result_has_reply_error(
                collect_app_callback_smoke_step(
                    session,
                    args,
                    step_results,
                    "lease_acquire",
                    protocol.lease_route(args.node, "acquire"),
                    lease_payload,
                )
            ):
                forced_ok = False

        if forced_ok is None:
            config_payload = build_app_callback_config_payload(
                lease_args, enabled=True
            )
            validate_payload(config_payload, "protected")
            config_result = collect_app_callback_smoke_step(
                session,
                args,
                step_results,
                "app_callback_config",
                app_callback_invoke_key(args.node, args.app_id),
                config_payload,
            )
            if result_has_reply_error(config_result) or not result_has_expected_app_echo(
                config_result, getattr(args, "expected_app_echo", "")
            ):
                forced_ok = False

        if forced_ok is None:
            invoke_payload = protected_write_payload(lease_args)
            invoke_payload["args"] = {}
            validate_payload(invoke_payload, "protected")
            for index in range(args.invoke_count):
                invoke_result = collect_app_callback_smoke_step(
                    session,
                    args,
                    step_results,
                    f"app_invoke_{index + 1}",
                    app_callback_invoke_key(args.node, args.app_id),
                    invoke_payload,
                )
                if result_has_reply_error(
                    invoke_result
                ) or not result_has_expected_app_echo(
                    invoke_result, getattr(args, "expected_app_echo", "")
                ):
                    forced_ok = False
                    break

        if forced_ok is None:
            collect_args = argparse.Namespace(**vars(args))
            collect_args.duration = max(
                EVENT_SUBSCRIPTION_READY_DELAY_SEC, float(args.settle_sec)
            )
            if use_callback_collection:
                wait_for_callback_events(session, collect_args)
            else:
                collect_subscriber_events_threaded(
                    subscriber,
                    event_rows,
                    collect_args,
                    "APP_EVT",
                    session=session,
                    pump_session=True,
                )
    finally:
        try:
            release_app_callback_smoke_lease(
                session, args, lease_args, step_results
            )
        except Exception:
            pass

        if subscriber is not None:
            subscriber.undeclare()

    return emit_app_callback_smoke_result(
        subscription,
        event_rows,
        step_results,
        ok=forced_ok,
    )


def handle_capabilities(session: zenoh.Session, args: argparse.Namespace) -> int:
    del session
    neurolink_root = find_neurolink_root(Path.cwd())
    capabilities = []
    for name, item in CAPABILITY_MATRIX.items():
        capabilities.append(
            {
                "name": name,
                "resource": item.get("resource", ""),
                "implemented": bool(item.get("implemented", False)),
                "note": item.get("note", ""),
            }
        )

    if args.output == "json":
        print_json(
            {
                "ok": True,
                "release_target": RELEASE_TARGET,
                "protocol": {**build_protocol_metadata()},
                "agent_skill": {
                    **build_agent_skill_metadata(neurolink_root),
                    "init_diagnostics_command": "system init --output json",
                },
                "agent_runtime": build_agent_runtime_metadata(neurolink_root),
                "workflow_surface": build_workflow_surface(),
                "capabilities": capabilities,
            }
        )
    else:
        print(f"## NeuroLink Unit capability map (release {RELEASE_TARGET})")
        for item in capabilities:
            status = "implemented" if item["implemented"] else "planned"
            print(f"- {item['name']}: {status} ({item['resource']})")
            if item["note"]:
                print(f"  note: {item['note']}")
    return 0


def handle_tool_manifest(
    session: zenoh.Session | None, args: argparse.Namespace
) -> int:
    del session
    neurolink_root = find_neurolink_root(Path.cwd())
    payload = build_tool_manifest_payload(neurolink_root)
    if args.output == "json":
        print_json(payload)
    else:
        print_json(payload)
    return 0


def handle_state_sync(session: zenoh.Session, args: argparse.Namespace) -> int:
    if getattr(args, "dry_run", False):
        payload = {
            "ok": True,
            "status": "dry_run",
            "schema_version": STATE_SYNC_SCHEMA_VERSION,
            "queries": [
                "query device --output json",
                "query apps --output json",
                "query leases --output json",
            ],
        }
        print_json(payload)
        return 0

    state = {
        "device": summarize_state_sync_query(collect_state_sync_query(session, args, "device")),
        "apps": summarize_state_sync_query(collect_state_sync_query(session, args, "apps")),
        "leases": summarize_state_sync_query(collect_state_sync_query(session, args, "leases")),
    }
    failures = [
        {
            "surface": name,
            "status": result["status"],
            "failure_status": result.get("failure_status", ""),
        }
        for name, result in state.items()
        if not result["ok"]
    ]
    ok = not failures
    payload = {
        "ok": ok,
        "status": "ok" if ok else "partial_failure",
        "schema_version": STATE_SYNC_SCHEMA_VERSION,
        "release_target": RELEASE_TARGET,
        "protocol": build_protocol_metadata(),
        "agent_runtime": build_agent_runtime_metadata(find_neurolink_root(Path.cwd())),
        "state": state,
        "failures": failures,
        "recommended_next_actions": build_state_sync_recommendations(state),
    }
    if args.output == "json":
        print_json(payload)
    else:
        print_json(payload)
    return 0 if ok else 2


def handle_agent_events(
    session: zenoh.Session | None, args: argparse.Namespace
) -> int:
    del session
    rows = build_agent_event_rows(args)
    if args.output == "jsonl":
        print_jsonl(rows)
        return 0

    print_json(
        {
            "ok": True,
            "status": "bounded_equivalent",
            "schema_version": AGENT_EVENTS_SCHEMA_VERSION,
            "mode": "bounded_equivalent",
            "live_subscription": False,
            "events": rows,
        }
    )
    return 0


def handle_serial_list(session: zenoh.Session | None, args: argparse.Namespace) -> int:
    del session
    devices = discover_serial_devices()
    result = {
        "ok": bool(devices),
        "status": "ok" if devices else "serial_device_missing",
        "devices": devices,
    }
    if not devices:
        result["error"] = "no serial devices found"
    return emit_result(args, result, "\n".join(device["device"] for device in devices))


def handle_serial_zenoh(session: zenoh.Session | None, args: argparse.Namespace) -> int:
    del session
    action = args.serial_zenoh_command
    if action == "show":
        command = "app zenoh_connect_show"
    elif action == "set":
        command = f"app zenoh_connect_set {args.endpoint}"
    elif action == "clear":
        command = "app zenoh_connect_clear"
    else:
        raise ValueError(f"unsupported serial zenoh action: {action}")

    result = run_serial_shell_command(args, command)
    output = str(result.get("output", ""))
    endpoint = parse_zenoh_endpoint_from_shell(output)
    if endpoint:
        result["endpoint"] = endpoint

    if not result.get("ok") and result.get("status") == "shell_error" and endpoint:
        result.update(
            {
                "ok": True,
                "status": "ok",
            }
        )

    if result.get("ok"):
        if action == "set" and endpoint != args.endpoint:
            result.update(
                {
                    "ok": False,
                    "status": "endpoint_verify_failed",
                    "expected_endpoint": args.endpoint,
                    "error": "serial shell output did not confirm the requested endpoint",
                }
            )
        elif action in ("show", "clear") and not endpoint:
            result.update(
                {
                    "ok": False,
                    "status": "endpoint_verify_failed",
                    "error": "serial shell output did not include a Zenoh endpoint",
                }
            )

    message = str(result.get("endpoint") or result.get("output") or "ok")
    return emit_result(args, result, message)


def add_serial_parser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port",
        default="",
        help="serial device path, for example /dev/ttyACM0 or COM3; defaults to first discovered port",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_SERIAL_BAUDRATE,
        help="serial baud rate for the Unit shell",
    )
    parser.add_argument(
        "--serial-timeout",
        type=float,
        default=DEFAULT_SERIAL_TIMEOUT_SEC,
        help="seconds to wait for shell output",
    )
    parser.add_argument(
        "--serial-settle-sec",
        type=float,
        default=DEFAULT_SERIAL_SETTLE_SEC,
        help="seconds to wait after opening the serial port before writing",
    )


def add_common_parser_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--node", default="unit-01", help="target NeuroLink node id")
    parser.add_argument("--source-core", default="core-cli", help="source_core metadata")
    parser.add_argument("--source-agent", default="rational", help="source_agent metadata")
    parser.add_argument("--timeout", type=float, default=10.0, help="query timeout in seconds")
    parser.add_argument("--request-id", default="", help="optional fixed request_id")
    parser.add_argument(
        "--priority",
        type=int,
        default=DEFAULT_PRIORITY,
        help="write/protected-write metadata priority",
    )
    parser.add_argument(
        "--idempotency-key",
        default="",
        help="optional idempotency key for write/protected-write requests",
    )
    parser.add_argument(
        "--output",
        choices=["human", "json", "jsonl"],
        default="human",
        help="output format",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print request payload without sending query",
    )
    parser.add_argument(
        "--zenoh-log-level",
        default="",
        help="explicit zenoh log level passed to init_log_from_env_or",
    )
    parser.add_argument(
        "--session-open-retries",
        type=int,
        default=DEFAULT_SESSION_OPEN_RETRIES,
        help="zenoh session open retry attempts",
    )
    parser.add_argument(
        "--session-open-backoff-ms",
        type=int,
        default=DEFAULT_SESSION_OPEN_BACKOFF_MS,
        help="backoff in milliseconds between session open retries",
    )
    parser.add_argument(
        "--query-retries",
        type=int,
        default=DEFAULT_QUERY_RETRIES,
        help="retry attempts for transient query failures (no_reply/query_failed)",
    )
    parser.add_argument(
        "--query-retry-backoff-ms",
        type=int,
        default=DEFAULT_QUERY_RETRY_BACKOFF_MS,
        help="initial retry backoff in milliseconds for transient query failures",
    )
    parser.add_argument(
        "--query-retry-backoff-max-ms",
        type=int,
        default=DEFAULT_QUERY_RETRY_BACKOFF_MAX_MS,
        help="maximum retry backoff in milliseconds for transient query failures",
    )
    parser.add_argument(
        "--event-pump-interval-sec",
        type=float,
        default=EVENT_SUBSCRIPTION_PUMP_INTERVAL_SEC,
        help="listener session keepalive pump interval in seconds",
    )


def add_event_handler_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--handler-command",
        default="",
        help="optional local command executed for each event; parsed without a shell",
    )
    parser.add_argument(
        "--handler-python",
        default="",
        help="optional Python handler file executed for each event with event JSON on stdin",
    )
    parser.add_argument(
        "--handler-timeout",
        type=float,
        default=DEFAULT_HANDLER_TIMEOUT_SEC,
        help="handler timeout in seconds",
    )
    parser.add_argument(
        "--handler-cwd",
        default="",
        help="handler working directory, constrained to the workspace root",
    )
    parser.add_argument(
        "--handler-max-event-bytes",
        type=int,
        default=DEFAULT_HANDLER_MAX_EVENT_BYTES,
        help="maximum UTF-8 event JSON bytes passed to a handler",
    )
    parser.add_argument(
        "--handler-max-output-bytes",
        type=int,
        default=DEFAULT_HANDLER_MAX_OUTPUT_BYTES,
        help="maximum UTF-8 stdout/stderr bytes retained per handler stream",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="stop event collection after this many events; 0 means duration/unbounded",
    )


def add_legacy_commands(subparsers: argparse._SubParsersAction) -> None:
    query = subparsers.add_parser("query", help="query device/apps/leases")
    query.add_argument("kind", choices=["device", "apps", "leases"])
    query.set_defaults(handler=handle_query)

    lease_acquire = subparsers.add_parser("lease-acquire", help="acquire a demo lease")
    lease_acquire.add_argument("--resource", required=True)
    lease_acquire.add_argument("--lease-id", default="")
    lease_acquire.add_argument("--priority", type=int, default=50)
    lease_acquire.add_argument("--ttl-ms", type=int, default=30000)
    lease_acquire.set_defaults(handler=handle_lease_acquire)

    lease_release = subparsers.add_parser("lease-release", help="release an existing lease")
    lease_release.add_argument("--lease-id", required=True)
    lease_release.add_argument(
        "--resource",
        default="",
        help="deprecated compatibility argument; ignored by release command",
    )
    lease_release.set_defaults(handler=handle_lease_release)

    app_start = subparsers.add_parser("app-start", help="start a loaded app through command plane")
    app_start.add_argument("--app-id", required=True)
    app_start.add_argument("--lease-id", required=True)
    app_start.add_argument("--start-args", default="")
    app_start.set_defaults(handler=handle_app_control, action="start")

    app_stop = subparsers.add_parser("app-stop", help="stop a running app through command plane")
    app_stop.add_argument("--app-id", required=True)
    app_stop.add_argument("--lease-id", required=True)
    app_stop.set_defaults(handler=handle_app_control, action="stop")

    prepare = subparsers.add_parser("prepare", help="download a llext artifact through update plane")
    prepare.add_argument("--app-id", required=True)
    prepare.add_argument("--file", required=True, help="local llext file served over zenoh")
    prepare.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    prepare.set_defaults(handler=handle_update, stage="prepare")

    verify = subparsers.add_parser("verify", help="verify a prepared llext artifact")
    verify.add_argument("--app-id", required=True)
    verify.set_defaults(handler=handle_update, stage="verify")

    activate = subparsers.add_parser("activate", help="activate a prepared llext artifact")
    activate.add_argument("--app-id", required=True)
    activate.add_argument("--lease-id", required=True)
    activate.add_argument("--start-args", default="")
    activate.set_defaults(handler=handle_update, stage="activate")

    rollback = subparsers.add_parser("rollback", help="rollback staged app update (placeholder)")
    rollback.add_argument("--app-id", required=True)
    rollback.add_argument("--lease-id", required=True)
    rollback.add_argument("--reason", default="")
    rollback.set_defaults(handler=handle_update, stage="rollback")

    events = subparsers.add_parser("events", help="subscribe to NeuroLink demo events")
    events.add_argument("--duration", type=int, default=30)
    events.add_argument("--ready-file", default="")
    add_event_handler_arguments(events)
    events.set_defaults(handler=handle_events)

    app_invoke = subparsers.add_parser("app-invoke", help="invoke app command callback path")
    app_invoke.add_argument("--app-id", required=True)
    app_invoke.add_argument("--lease-id", required=True)
    app_invoke.add_argument("--command", default="invoke")
    app_invoke.add_argument("--args-json", default="{}")
    app_invoke.set_defaults(handler=handle_app_invoke)

    app_callback_config = subparsers.add_parser(
        "app-callback-config", help="configure app callback event publishing"
    )
    app_callback_config.add_argument("--app-id", required=True)
    app_callback_config.add_argument("--lease-id", required=True)
    app_callback_config.add_argument("--mode", choices=["on", "off"], required=True)
    app_callback_config.add_argument("--trigger-every", type=int, default=0)
    app_callback_config.add_argument("--event-name", default="callback")
    app_callback_config.set_defaults(handler=handle_app_callback_config)

    app_events = subparsers.add_parser("app-events", help="listen for app callback events")
    app_events.add_argument("--app-id", required=True)
    app_events.add_argument("--duration", type=int, default=0)
    app_events.add_argument("--ready-file", default="")
    add_event_handler_arguments(app_events)
    app_events.set_defaults(handler=handle_app_events)

    app_callback_smoke = subparsers.add_parser(
        "app-callback-smoke",
        help="capture app callback events within one Zenoh session",
    )
    app_callback_smoke.add_argument("--app-id", required=True)
    app_callback_smoke.add_argument("--lease-id", default="")
    app_callback_smoke.add_argument("--ttl-ms", type=int, default=60000)
    app_callback_smoke.add_argument("--trigger-every", type=int, default=2)
    app_callback_smoke.add_argument("--event-name", default="callback")
    app_callback_smoke.add_argument("--invoke-count", type=int, default=2)
    app_callback_smoke.add_argument("--settle-sec", type=float, default=1.0)
    app_callback_smoke.add_argument("--expected-app-echo", default="")
    add_event_handler_arguments(app_callback_smoke)
    app_callback_smoke.set_defaults(handler=handle_app_callback_smoke)

    capability = subparsers.add_parser("capabilities", help="show Unit capability map")
    capability.set_defaults(handler=handle_capabilities, requires_session=False)

    init = subparsers.add_parser(
        "init", help="show Agent-facing workspace initialization diagnostics"
    )
    init.set_defaults(handler=handle_init, requires_session=False)

    workflow = subparsers.add_parser(
        "workflow", help="show structured app-development and board-operation plans"
    )
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_plan = workflow_sub.add_parser("plan", help="print a workflow command plan")
    workflow_plan.add_argument("workflow", choices=sorted(WORKFLOW_PLANS.keys()))
    workflow_plan.set_defaults(handler=handle_workflow_plan, requires_session=False)

    memory_layout_dump = subparsers.add_parser(
        "memory-layout-dump", help="dump static memory layout from Unit build artifacts"
    )
    memory_layout_dump.add_argument("--build-dir", default="build/neurolink_unit")
    memory_layout_dump.add_argument(
        "--output-dir", default="applocation/NeuroLink/memory-evidence"
    )
    memory_layout_dump.add_argument(
        "--label", default=release_label("static-layout-baseline")
    )
    memory_layout_dump.add_argument("--build-log", default="")
    memory_layout_dump.add_argument("--run-build", action="store_true")
    memory_layout_dump.add_argument("--no-c-style-check", action="store_true")
    memory_layout_dump.set_defaults(
        handler=handle_memory_layout_dump, requires_session=False
    )

    memory_config_plan = subparsers.add_parser(
        "llext-memory-config-plan",
        help="compare LLEXT memory candidate layout evidence against a baseline",
    )
    memory_config_plan.add_argument("--baseline-json", required=True)
    memory_config_plan.add_argument("--candidate-json", required=True)
    memory_config_plan.set_defaults(
        handler=handle_llext_memory_config_plan, requires_session=False
    )

    recovery = subparsers.add_parser("recovery", help="recovery operation placeholder")
    recovery.set_defaults(
        handler=handle_placeholder,
        placeholder_capability="recovery",
        placeholder_name="recovery",
    )

    gateway = subparsers.add_parser("gateway", help="gateway operation placeholder")
    gateway.set_defaults(
        handler=handle_placeholder,
        placeholder_capability="gateway",
        placeholder_name="gateway",
    )

    tool_manifest = subparsers.add_parser("tool-manifest", help="emit Agent-facing tool manifest")
    tool_manifest.set_defaults(handler=handle_tool_manifest, requires_session=False)

    state_sync = subparsers.add_parser("state-sync", help="aggregate device/apps/leases into a read-only state sync snapshot")
    state_sync.set_defaults(handler=handle_state_sync)


def add_grouped_alias_commands(subparsers: argparse._SubParsersAction) -> None:
    system = subparsers.add_parser("system", help="system commands")
    system_sub = system.add_subparsers(dest="system_command", required=True)
    system_query = system_sub.add_parser("query", help="query device/apps/leases")
    system_query.add_argument("kind", choices=["device", "apps", "leases"])
    system_query.set_defaults(handler=handle_query)
    system_cap = system_sub.add_parser("capabilities", help="show capability map")
    system_cap.set_defaults(handler=handle_capabilities, requires_session=False)
    system_tool_manifest = system_sub.add_parser(
        "tool-manifest", help="emit Agent-facing tool manifest"
    )
    system_tool_manifest.set_defaults(
        handler=handle_tool_manifest, requires_session=False
    )
    system_state_sync = system_sub.add_parser(
        "state-sync", help="aggregate device/apps/leases into a read-only state sync snapshot"
    )
    system_state_sync.set_defaults(handler=handle_state_sync)
    system_init = system_sub.add_parser(
        "init", help="show Agent-facing workspace initialization diagnostics"
    )
    system_init.set_defaults(handler=handle_init, requires_session=False)

    system_workflow = system_sub.add_parser(
        "workflow", help="show structured workflow plans"
    )
    system_workflow_sub = system_workflow.add_subparsers(
        dest="system_workflow_command", required=True
    )
    system_workflow_plan = system_workflow_sub.add_parser(
        "plan", help="print a workflow command plan"
    )
    system_workflow_plan.add_argument(
        "workflow", choices=sorted(WORKFLOW_PLANS.keys())
    )
    system_workflow_plan.set_defaults(
        handler=handle_workflow_plan, requires_session=False
    )

    lease = subparsers.add_parser("lease", help="lease management")
    lease_sub = lease.add_subparsers(dest="lease_command", required=True)
    lease_acquire_v2 = lease_sub.add_parser("acquire", help="acquire lease")
    lease_acquire_v2.add_argument("--resource", required=True)
    lease_acquire_v2.add_argument("--lease-id", default="")
    lease_acquire_v2.add_argument("--ttl-ms", type=int, default=30000)
    lease_acquire_v2.set_defaults(handler=handle_lease_acquire)
    lease_release_v2 = lease_sub.add_parser("release", help="release lease")
    lease_release_v2.add_argument("--lease-id", required=True)
    lease_release_v2.add_argument(
        "--resource",
        default="",
        help="deprecated compatibility argument; ignored by release command",
    )
    lease_release_v2.set_defaults(handler=handle_lease_release)

    app = subparsers.add_parser("app", help="application control")
    app_sub = app.add_subparsers(dest="app_command", required=True)
    app_start_v2 = app_sub.add_parser("start", help="start app")
    app_start_v2.add_argument("--app-id", required=True)
    app_start_v2.add_argument("--lease-id", required=True)
    app_start_v2.add_argument("--start-args", default="")
    app_start_v2.set_defaults(handler=handle_app_control, action="start")
    app_stop_v2 = app_sub.add_parser("stop", help="stop app")
    app_stop_v2.add_argument("--app-id", required=True)
    app_stop_v2.add_argument("--lease-id", required=True)
    app_stop_v2.set_defaults(handler=handle_app_control, action="stop")
    app_unload_v2 = app_sub.add_parser("unload", help="unload app runtime")
    app_unload_v2.add_argument("--app-id", required=True)
    app_unload_v2.add_argument("--lease-id", required=True)
    app_unload_v2.set_defaults(handler=handle_app_control, action="unload")
    app_delete_v2 = app_sub.add_parser("delete", help="delete inactive app artifact")
    app_delete_v2.add_argument("--app-id", required=True)
    app_delete_v2.add_argument("--lease-id", required=True)
    app_delete_v2.set_defaults(handler=handle_update, stage="delete")
    app_invoke_v2 = app_sub.add_parser("invoke", help="invoke app callback command")
    app_invoke_v2.add_argument("--app-id", required=True)
    app_invoke_v2.add_argument("--lease-id", required=True)
    app_invoke_v2.add_argument("--command", default="invoke")
    app_invoke_v2.add_argument("--args-json", default="{}")
    app_invoke_v2.set_defaults(handler=handle_app_invoke)
    app_callback_config_v2 = app_sub.add_parser(
        "callback-config", help="configure app callback event publishing"
    )
    app_callback_config_v2.add_argument("--app-id", required=True)
    app_callback_config_v2.add_argument("--lease-id", required=True)
    app_callback_config_v2.add_argument("--mode", choices=["on", "off"], required=True)
    app_callback_config_v2.add_argument("--trigger-every", type=int, default=0)
    app_callback_config_v2.add_argument("--event-name", default="callback")
    app_callback_config_v2.set_defaults(handler=handle_app_callback_config)

    deploy = subparsers.add_parser("deploy", help="update/deploy flow")
    deploy_sub = deploy.add_subparsers(dest="deploy_command", required=True)
    prepare_v2 = deploy_sub.add_parser("prepare", help="prepare artifact")
    prepare_v2.add_argument("--app-id", required=True)
    prepare_v2.add_argument("--file", required=True, help="local llext file served over zenoh")
    prepare_v2.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    prepare_v2.set_defaults(handler=handle_update, stage="prepare")
    verify_v2 = deploy_sub.add_parser("verify", help="verify artifact")
    verify_v2.add_argument("--app-id", required=True)
    verify_v2.set_defaults(handler=handle_update, stage="verify")
    activate_v2 = deploy_sub.add_parser("activate", help="activate app")
    activate_v2.add_argument("--app-id", required=True)
    activate_v2.add_argument("--lease-id", required=True)
    activate_v2.add_argument("--start-args", default="")
    activate_v2.set_defaults(handler=handle_update, stage="activate")
    rollback_v2 = deploy_sub.add_parser("rollback", help="rollback placeholder")
    rollback_v2.add_argument("--app-id", required=True)
    rollback_v2.add_argument("--lease-id", required=True)
    rollback_v2.add_argument("--reason", default="")
    rollback_v2.set_defaults(handler=handle_update, stage="rollback")

    monitor = subparsers.add_parser("monitor", help="event monitoring")
    monitor_sub = monitor.add_subparsers(dest="monitor_command", required=True)
    monitor_events = monitor_sub.add_parser("events", help="subscribe events")
    monitor_events.add_argument("--duration", type=int, default=30)
    monitor_events.add_argument("--ready-file", default="")
    add_event_handler_arguments(monitor_events)
    monitor_events.set_defaults(handler=handle_events)
    monitor_app_events = monitor_sub.add_parser(
        "app-events", help="subscribe app callback events"
    )
    monitor_app_events.add_argument("--app-id", required=True)
    monitor_app_events.add_argument("--duration", type=int, default=0)
    monitor_app_events.add_argument("--ready-file", default="")
    add_event_handler_arguments(monitor_app_events)
    monitor_app_events.set_defaults(handler=handle_app_events)
    monitor_agent_events = monitor_sub.add_parser(
        "agent-events", help="emit bounded Agent-facing event envelopes as JSONL"
    )
    monitor_agent_events.add_argument("--max-events", type=int, default=0)
    monitor_agent_events.set_defaults(
        handler=handle_agent_events,
        requires_session=False,
    )

    serial_parser = subparsers.add_parser("serial", help="UART serial recovery")
    serial_sub = serial_parser.add_subparsers(dest="serial_command", required=True)
    serial_list = serial_sub.add_parser("list", help="list candidate Unit serial ports")
    serial_list.set_defaults(handler=handle_serial_list, requires_session=False)
    serial_zenoh = serial_sub.add_parser(
        "zenoh", help="configure Unit Zenoh endpoint over UART"
    )
    serial_zenoh_sub = serial_zenoh.add_subparsers(
        dest="serial_zenoh_command", required=True
    )
    serial_zenoh_show = serial_zenoh_sub.add_parser(
        "show", help="show Unit Zenoh endpoint"
    )
    add_serial_parser_arguments(serial_zenoh_show)
    serial_zenoh_show.set_defaults(handler=handle_serial_zenoh, requires_session=False)
    serial_zenoh_set = serial_zenoh_sub.add_parser(
        "set", help="set Unit Zenoh endpoint"
    )
    serial_zenoh_set.add_argument(
        "endpoint", help="Zenoh locator, for example tcp/192.168.2.94:7447"
    )
    add_serial_parser_arguments(serial_zenoh_set)
    serial_zenoh_set.set_defaults(handler=handle_serial_zenoh, requires_session=False)
    serial_zenoh_clear = serial_zenoh_sub.add_parser(
        "clear", help="clear Unit Zenoh endpoint override"
    )
    add_serial_parser_arguments(serial_zenoh_clear)
    serial_zenoh_clear.set_defaults(handler=handle_serial_zenoh, requires_session=False)

    memory = subparsers.add_parser("memory", help="memory evidence commands")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_layout_dump_v2 = memory_sub.add_parser(
        "layout-dump", help="dump static memory layout from Unit build artifacts"
    )
    memory_layout_dump_v2.add_argument("--build-dir", default="build/neurolink_unit")
    memory_layout_dump_v2.add_argument(
        "--output-dir", default="applocation/NeuroLink/memory-evidence"
    )
    memory_layout_dump_v2.add_argument(
        "--label", default=release_label("static-layout-baseline")
    )
    memory_layout_dump_v2.add_argument("--build-log", default="")
    memory_layout_dump_v2.add_argument("--run-build", action="store_true")
    memory_layout_dump_v2.add_argument("--no-c-style-check", action="store_true")
    memory_layout_dump_v2.set_defaults(
        handler=handle_memory_layout_dump, requires_session=False
    )
    memory_config_plan_v2 = memory_sub.add_parser(
        "config-plan",
        help="compare LLEXT memory candidate layout evidence against a baseline",
    )
    memory_config_plan_v2.add_argument("--baseline-json", required=True)
    memory_config_plan_v2.add_argument("--candidate-json", required=True)
    memory_config_plan_v2.set_defaults(
        handler=handle_llext_memory_config_plan, requires_session=False
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NeuroLink Zenoh Neuro CLI")
    add_common_parser_arguments(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    add_legacy_commands(sub)
    add_grouped_alias_commands(sub)
    return parser


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        return int(exc.code)

    log_level = args.zenoh_log_level.strip()
    if not log_level:
        log_level = os.getenv("NEUROLINK_ZENOH_LOG", "").strip()
    if log_level:
        zenoh.init_log_from_env_or(log_level)

    session = None
    try:
        if not getattr(args, "requires_session", True):
            return int(args.handler(None, args) or 0)
        session = open_session_with_retry(args)
        return int(args.handler(session, args) or 0)
    except ValueError as exc:
        output_mode = getattr(args, "output", "human")
        if output_mode == "json":
            print_json({"ok": False, "status": "invalid_input", "error": str(exc)})
        else:
            print(f"invalid input: {exc}")
        return 2
    except Exception as exc:
        output_mode = getattr(args, "output", "human")
        status = "handler_failed" if session is not None else "session_open_failed"
        if output_mode == "json":
            print_json({"ok": False, "status": status, "error": str(exc)})
        else:
            print(f"{status}: {exc}")
        return 2
    finally:
        if session is not None:
            close = getattr(session, "close", None)
            if callable(close):
                close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
