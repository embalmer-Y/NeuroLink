import argparse
from dataclasses import dataclass
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import zenoh

import neuro_protocol as protocol


DEFAULT_CHUNK_SIZE = 1024
DEFAULT_PRIORITY = 50
RELEASE_TARGET = "1.1.5"
EVENT_SUBSCRIPTION_READY_DELAY_SEC = 1.0
EVENT_SUBSCRIPTION_PUMP_INTERVAL_SEC = 1.0
DEFAULT_SESSION_OPEN_RETRIES = 3
DEFAULT_SESSION_OPEN_BACKOFF_MS = 500
DEFAULT_QUERY_RETRIES = 3
DEFAULT_QUERY_RETRY_BACKOFF_MS = 250
DEFAULT_QUERY_RETRY_BACKOFF_MAX_MS = 2000
DEFAULT_HANDLER_TIMEOUT_SEC = 5.0
DEFAULT_HANDLER_MAX_EVENT_BYTES = 65536


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


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def make_request_id() -> str:
    return protocol.make_request_id()


def make_idempotency_key() -> str:
    return protocol.make_idempotency_key()


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
            "version": protocol.DEFAULT_PROTOCOL_VERSION,
            "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
            "supported_wire_encodings": protocol.SUPPORTED_WIRE_ENCODINGS,
            "planned_wire_encodings": protocol.PLANNED_WIRE_ENCODINGS,
            "cbor_v2_enabled": False,
        },
        "workspace_root": str(workspace_root),
        "neurolink_root": str(neurolink_root) if neurolink_root else "",
        "python": sys.executable,
        "scripts": scripts,
        "shell_setup": {
            "can_modify_parent_shell": False,
            "recommended_command": "source applocation/NeuroLink/scripts/setup_neurolink_env.sh",
        },
        "agent_workflows": [
            "system capabilities --output json",
            "system init --output json",
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


WORKFLOW_PLANS = {
    "app-build": {
        "category": "app_development",
        "description": "build the sample LLEXT app artifact",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check",
        ],
        "artifacts": ["build/neurolink_unit_app/neuro_unit_app.llext"],
    },
    "unit-build": {
        "category": "board_operation",
        "description": "build Neuro Unit firmware",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check",
        ],
        "artifacts": ["build/neurolink_unit/zephyr/zephyr.elf"],
    },
    "unit-edk": {
        "category": "app_development",
        "description": "build the Unit EDK headers and LLEXT support output",
        "commands": [
            "bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check",
        ],
        "artifacts": ["build/neurolink_unit/zephyr/llext-edk"],
    },
    "unit-tests": {
        "category": "verification",
        "description": "run native_sim Neuro Unit tests",
        "commands": [
            "west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run",
        ],
        "artifacts": ["build/neurolink_unit_ut_check"],
    },
    "cli-tests": {
        "category": "verification",
        "description": "run Neuro CLI regression tests",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q",
        ],
        "artifacts": [],
    },
    "preflight": {
        "category": "board_operation",
        "description": "run Linux host and board preflight checks",
        "commands": [
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text",
        ],
        "artifacts": [],
    },
    "smoke": {
        "category": "board_operation",
        "description": "run the Linux NeuroLink smoke path",
        "commands": [
            "bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence"],
    },
}


def build_workflow_plan(args: argparse.Namespace) -> dict:
    workflow = WORKFLOW_PLANS[args.workflow]
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    return {
        "ok": True,
        "workflow": args.workflow,
        "category": workflow["category"],
        "description": workflow["description"],
        "release_target": RELEASE_TARGET,
        "protocol": {
            "version": protocol.DEFAULT_PROTOCOL_VERSION,
            "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
            "supported_wire_encodings": protocol.SUPPORTED_WIRE_ENCODINGS,
            "planned_wire_encodings": protocol.PLANNED_WIRE_ENCODINGS,
            "cbor_v2_enabled": False,
        },
        "executes_commands": False,
        "workspace_root": str(workspace_root),
        "commands": workflow["commands"],
        "artifacts": workflow["artifacts"],
        "next_step": "run the listed command explicitly after reviewing it",
    }


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


def validate_payload(payload: dict, mode: str) -> None:
    protocol.validate_payload(payload, mode)


def collect_query_result(
    session: zenoh.Session,
    keyexpr: str,
    payload: dict,
    timeout: float,
) -> dict:
    payload_text = json.dumps(payload, ensure_ascii=False)

    try:
        replies = session.get(keyexpr, payload=payload_text, timeout=timeout)
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

        if result_has_reply_error(result) and result.get("status") not in (
            "no_reply",
            "query_failed",
        ):
            result["ok"] = False
            result["status"] = "error_reply"
            result["retried"] = attempt > 0
            return result

        if result.get("ok", False):
            result["retried"] = attempt > 0
            return result

        status = result.get("status", "")
        retryable = status in ("no_reply", "query_failed")
        if not retryable or attempt + 1 >= attempts:
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
    if not result.get("ok", False):
        return True

    for reply in result.get("replies", []):
        payload = reply.get("payload")
        if isinstance(payload, dict) and payload.get("status") == "error":
            return True

    return False


def send_query(
    session: zenoh.Session,
    keyexpr: str,
    payload: dict,
    timeout: float,
    args: argparse.Namespace,
) -> int:
    payload_text = json.dumps(payload, ensure_ascii=False)
    if args.dry_run:
        dry_run_data = {
            "ok": True,
            "dry_run": True,
            "keyexpr": keyexpr,
            "payload": payload,
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
    elif args.stage in ("activate", "rollback"):
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


def execute_event_handler(args: argparse.Namespace, event: dict) -> dict | None:
    argv = build_handler_argv(args)
    if not argv:
        return None

    event_text = json.dumps(event, ensure_ascii=False)
    max_bytes = int(
        getattr(args, "handler_max_event_bytes", DEFAULT_HANDLER_MAX_EVENT_BYTES)
    )
    if len(event_text.encode("utf-8")) > max_bytes:
        return {
            "enabled": True,
            "executed": False,
            "status": "payload_too_large",
            "max_event_bytes": max_bytes,
        }

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            input=event_text,
            text=True,
            capture_output=True,
            timeout=float(getattr(args, "handler_timeout", DEFAULT_HANDLER_TIMEOUT_SEC)),
            cwd=str(resolve_handler_cwd(args)),
            shell=False,
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "enabled": True,
            "executed": True,
            "status": "ok" if completed.returncode == 0 else "nonzero_exit",
            "argv": argv,
            "returncode": completed.returncode,
            "duration_ms": duration_ms,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "enabled": True,
            "executed": True,
            "status": "timeout",
            "argv": argv,
            "returncode": None,
            "duration_ms": duration_ms,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timeout": True,
        }
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "enabled": True,
            "executed": False,
            "status": "handler_error",
            "argv": argv,
            "duration_ms": duration_ms,
            "error": str(exc),
        }


def append_event_row(
    event_rows: list[dict], sample: zenoh.Sample, args: argparse.Namespace, label: str
) -> None:
    payload = sample.payload.to_string()
    parsed_payload: object = payload
    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError:
        pass

    if args.output == "json":
        row = {
            "keyexpr": str(sample.key_expr),
            "payload": parsed_payload,
        }
        handler = execute_event_handler(args, row)
        if handler is not None:
            row["handler"] = handler
        event_rows.append(row)
        return

    print(f"<< {label} {sample.key_expr}")
    try:
        print(json.dumps(json.loads(payload), indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(payload)
    handler = execute_event_handler(
        args, {"keyexpr": str(sample.key_expr), "payload": parsed_payload}
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
) -> tuple[object, bool, str]:
    handlers = getattr(zenoh, "handlers", None)
    fifo_cls = getattr(handlers, "FifoChannel", None) if handlers is not None else None
    callback_cls = getattr(handlers, "Callback", None) if handlers is not None else None

    if fifo_cls is not None:
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
    )


def handle_app_callback_smoke(
    session: zenoh.Session, args: argparse.Namespace
) -> int:
    subscription = protocol.app_event_subscription_route(args.node, args.app_id)
    event_rows: list[dict] = []
    lease_id = args.lease_id or f"smoke-{uuid.uuid4().hex[:8]}"
    lease_args = args_with_lease_id(args, lease_id)
    subscriber = None
    step_results: list[dict] = []
    forced_ok: bool | None = None

    def listener(sample: zenoh.Sample) -> None:
        payload = sample.payload.to_string()
        parsed_payload: object = payload
        try:
            parsed_payload = json.loads(payload)
        except json.JSONDecodeError:
            pass

        event_rows.append(
            {
                "keyexpr": str(sample.key_expr),
                "payload": parsed_payload,
            }
        )

    subscriber = session.declare_subscriber(subscription, listener)
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
            if result_has_reply_error(
                collect_app_callback_smoke_step(
                    session,
                    args,
                    step_results,
                    "app_callback_config",
                    app_callback_invoke_key(args.node, args.app_id),
                    config_payload,
                )
            ):
                forced_ok = False

        if forced_ok is None:
            invoke_payload = protected_write_payload(lease_args)
            invoke_payload["args"] = {}
            validate_payload(invoke_payload, "protected")
            for index in range(args.invoke_count):
                if result_has_reply_error(
                    collect_app_callback_smoke_step(
                        session,
                        args,
                        step_results,
                        f"app_invoke_{index + 1}",
                        app_callback_invoke_key(args.node, args.app_id),
                        invoke_payload,
                    )
                ):
                    forced_ok = False
                    break

        if forced_ok is None:
            time.sleep(args.settle_sec)
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
                "protocol": {
                    "version": protocol.DEFAULT_PROTOCOL_VERSION,
                    "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
                    "supported_wire_encodings": protocol.SUPPORTED_WIRE_ENCODINGS,
                    "planned_wire_encodings": protocol.PLANNED_WIRE_ENCODINGS,
                    "cbor_v2_enabled": False,
                },
                "agent_skill": {
                    "structured_stdout": True,
                    "init_diagnostics_command": "system init --output json",
                    "callback_handler_execution": "opt_in_subprocess",
                },
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
        choices=["human", "json"],
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

    state_sync = subparsers.add_parser("state-sync", help="state registry operation placeholder")
    state_sync.set_defaults(
        handler=handle_placeholder,
        placeholder_capability="state_registry",
        placeholder_name="state-sync",
    )


def add_grouped_alias_commands(subparsers: argparse._SubParsersAction) -> None:
    system = subparsers.add_parser("system", help="system commands")
    system_sub = system.add_subparsers(dest="system_command", required=True)
    system_query = system_sub.add_parser("query", help="query device/apps/leases")
    system_query.add_argument("kind", choices=["device", "apps", "leases"])
    system_query.set_defaults(handler=handle_query)
    system_cap = system_sub.add_parser("capabilities", help="show capability map")
    system_cap.set_defaults(handler=handle_capabilities, requires_session=False)
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
    finally:
        if session is not None:
            close = getattr(session, "close", None)
            if callable(close):
                close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
