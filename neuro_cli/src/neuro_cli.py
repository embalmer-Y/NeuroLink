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
RELEASE_TARGET = "1.1.8"
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
CANONICAL_SKILL_RELATIVE_PATH = "neuro_cli/skill/SKILL.md"
PROJECT_SHARED_SKILL_RELATIVE_PATH = ".github/skills/neuro-cli/SKILL.md"
PROJECT_SKILL_RELATIVE_PATH = PROJECT_SHARED_SKILL_RELATIVE_PATH
NEURO_CLI_WRAPPER_RELATIVE_PATH = "neuro_cli/scripts/invoke_neuro_cli.py"
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
}
WORKFLOW_PLAN_SCHEMA_VERSION = "1.1.8-workflow-plan-v1"


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


def resolve_neurolink_path(
    neurolink_root: Path | None, relative_path: str
) -> Path:
    return neurolink_root / relative_path if neurolink_root else Path(relative_path)


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
            "cbor_v2_enabled": protocol.DEFAULT_WIRE_ENCODING == "cbor-v2",
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
        "agent_workflows": [
            "system capabilities --output json",
            "system init --output json",
            "workflow plan setup-linux --output json",
            "workflow plan setup-windows --output json",
            "workflow plan discover-host --output json",
            "workflow plan discover-router --output json",
            "workflow plan discover-serial --output json",
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


WORKFLOW_PLANS = {
    "setup-linux": {
        "category": "setup",
        "description": "construct and validate a Linux NeuroLink build/test/control host",
        "commands": [
            "sudo apt-get update",
            "sudo apt-get install -y git python3 python3-venv python3-pip cmake ninja-build gperf ccache dfu-util device-tree-compiler wget curl xz-utils file make gcc gcc-multilib g++-multilib libsdl2-dev libmagic1 clang-format perl usbutils",
            "python3 -m venv .venv",
            "source .venv/bin/activate && python3 -m pip install --upgrade pip wheel west",
            "source .venv/bin/activate && python3 -m pip install -r zephyr/scripts/requirements.txt -r applocation/NeuroLink/neuro_cli/requirements.txt",
            "source .venv/bin/activate && west update",
            "cat zephyr/SDK_VERSION",
            "export ZEPHYR_SDK_INSTALL_DIR=${HOME}/zephyr-sdk-$(cat zephyr/SDK_VERSION)",
            "source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-neuro-cli-deps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-tests",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight",
        ],
        "artifacts": [
            ".venv",
            "build/neurolink_unit",
            "build/neurolink_unit_ut_check",
            "build/neurolink_unit_app",
        ],
    },
    "setup-windows": {
        "category": "setup",
        "description": "construct and validate a Windows NeuroLink build/test/control host",
        "commands": [
            "winget install --id Git.Git -e --source winget",
            "winget install --id Python.Python.3.12 -e --source winget",
            "winget install --id Kitware.CMake -e --source winget",
            "winget install --id Ninja-build.Ninja -e --source winget",
            "winget install --id Microsoft.PowerShell -e --source winget",
            "py -3 -m venv .venv",
            ". .venv/Scripts/Activate.ps1",
            "python -m pip install --upgrade pip wheel west",
            "python -m pip install -r zephyr/scripts/requirements.txt -r applocation/NeuroLink/neuro_cli/requirements.txt",
            "west update",
            "Get-Content zephyr/SDK_VERSION",
            "$env:ZEPHYR_SDK_INSTALL_DIR = \"$HOME/zephyr-sdk-$(Get-Content zephyr/SDK_VERSION)\"",
            ". applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Strict",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan cli-tests",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight",
        ],
        "artifacts": [
            ".venv",
            "build/neurolink_unit",
            "build/neurolink_unit_app",
            "applocation/NeuroLink/smoke-evidence",
        ],
    },
    "discover-host": {
        "category": "discovery",
        "description": "read local NeuroLink workspace and CLI capability state",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "status": "ready",
                "release_target": RELEASE_TARGET,
                "agent_skill": {
                    "name": "neuro-cli",
                    "source_of_truth": "canonical",
                },
                "protocol": {
                    "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
                },
            },
            "failure_statuses": ["workspace_not_found", "handler_failed"],
        },
    },
    "discover-router": {
        "category": "discovery",
        "description": "classify Linux Zenoh router listener state without app control",
        "commands": [
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --install-missing-cli-deps --output json",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "status": "ready",
                "ready": True,
                "router": {
                    "listening": True,
                    "port": 7447,
                    "auto_started": False,
                },
            },
            "failure_statuses": [
                "router_not_listening",
                "router_failed_to_start",
                "no_reply_board_not_attached",
                "no_reply_board_unreachable",
            ],
        },
    },
    "discover-serial": {
        "category": "discovery",
        "description": "classify Linux USB serial visibility before hardware evidence",
        "commands": [
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --require-serial --output json",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "serial": {
                    "present": True,
                    "devices": ["/dev/ttyACM0"],
                },
            },
            "failure_statuses": ["serial_device_missing"],
        },
    },
    "discover-device": {
        "category": "discovery",
        "description": "query Unit reachability and device state through the router",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query device",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "replies": [
                    {
                        "ok": True,
                        "payload": {
                            "status": "ok",
                            "node_id": "unit-01",
                            "session_ready": True,
                        },
                    }
                ],
            },
            "failure_statuses": [
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "discover-apps": {
        "category": "discovery",
        "description": "query deployed Unit apps and runtime/update state",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query apps",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "replies": [
                    {
                        "ok": True,
                        "payload": {
                            "status": "ok",
                            "node_id": "unit-01",
                            "app_count": 0,
                            "running_count": 0,
                            "suspended_count": 0,
                            "apps": [],
                        },
                    }
                ],
            },
            "failure_statuses": [
                "app_not_running",
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "discover-leases": {
        "category": "discovery",
        "description": "query active Unit leases before protected control",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "ok": True,
                "replies": [
                    {
                        "ok": True,
                        "payload": {
                            "status": "ok",
                            "node_id": "unit-01",
                            "leases": [],
                        },
                    }
                ],
            },
            "failure_statuses": [
                "lease_conflict",
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "control-health": {
        "category": "control",
        "description": "run read-only health queries before protected control",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py --query-retries 3 query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "device": {"status": "ok", "node_id": "unit-01"},
                "apps": {"status": "ok", "apps": []},
                "leases": {"status": "ok", "leases": []},
            },
            "failure_statuses": [
                "session_open_failed",
                "no_reply",
                "parse_failed",
                "error_reply",
                "payload.status:error",
            ],
        },
    },
    "control-deploy": {
        "category": "control",
        "description": "protected deploy prepare/verify/activate sequence with lease cleanup",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource update/app/neuro_unit_app/activate --lease-id "
            f"{release_label('deploy')}-lease --ttl-ms 120000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy prepare --app-id neuro_unit_app --file build/neurolink_unit/llext/neuro_unit_app.llext",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy verify --app-id neuro_unit_app",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py deploy activate --app-id neuro_unit_app --lease-id "
            f"{release_label('deploy')}-lease --start-args release={RELEASE_TARGET}",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('deploy')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [
            "build/neurolink_unit/llext/neuro_unit_app.llext",
            "applocation/NeuroLink/smoke-evidence",
        ],
        "json_contract": {
            "success": {
                "lease_acquire": {"status": "ok", "lease_id": f"{release_label('deploy')}-lease"},
                "deploy_prepare": {"status": "ok", "app_id": "neuro_unit_app"},
                "deploy_verify": {"status": "ok", "app_id": "neuro_unit_app"},
                "deploy_activate": {"status": "ok", "app_id": "neuro_unit_app"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "lease_conflict",
                "artifact_missing",
                "artifact_stale",
                "prepare_failed",
                "verify_failed",
                "activate_failed",
                "payload.status:error",
            ],
        },
    },
    "control-app-invoke": {
        "category": "control",
        "description": "protected app command invocation with app-control lease cleanup",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource app/neuro_unit_app/control --lease-id "
            f"{release_label('app-control')}-lease --ttl-ms 60000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app invoke --app-id neuro_unit_app --lease-id "
            f"{release_label('app-control')}-lease --command invoke --args-json '{{\"echo\": \"{default_app_echo()}\"}}'",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('app-control')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "lease_acquire": {"status": "ok", "resource": "app/neuro_unit_app/control"},
                "app_invoke": {"status": "ok", "app_id": "neuro_unit_app"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "app_not_running",
                "lease_conflict",
                "invalid_input",
                "handler_failed",
                "payload.status:error",
            ],
        },
    },
    "control-callback": {
        "category": "control",
        "description": "protected callback configuration and same-session callback smoke",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource app/neuro_unit_app/control --lease-id "
            f"{release_label('callback')}-lease --ttl-ms 60000",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app callback-config --app-id neuro_unit_app --lease-id "
            f"{release_label('callback')}-lease --mode on --trigger-every 1 --event-name callback",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app invoke --app-id neuro_unit_app --lease-id "
            f"{release_label('callback')}-lease --command invoke --args-json '{{\"echo\": \"{default_app_echo()}\"}}'",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_unit_app --duration 5 --max-events 1",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py app callback-config --app-id neuro_unit_app --lease-id "
            f"{release_label('callback')}-lease --mode off --event-name callback",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('callback')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke",
        ],
        "artifacts": ["applocation/NeuroLink/smoke-evidence"],
        "json_contract": {
            "success": {
                "callback_config": {"status": "ok", "callback_enabled": True},
                "app_invoke": {"status": "ok", "app_id": "neuro_unit_app"},
                "event": {"keyexpr": "neuro/unit-01/event/app/neuro_unit_app/callback"},
                "lease_cleanup": {"leases": []},
            },
            "failure_statuses": [
                "callback_timeout",
                "handler_failed",
                "lease_conflict",
                "app_not_running",
                "payload.status:error",
            ],
        },
    },
    "control-monitor": {
        "category": "control",
        "description": "monitor app-scoped events with explicit optional handler audit",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_unit_app --duration 10 --max-events 1",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py monitor app-events --app-id neuro_unit_app --duration 10 --max-events 1 --handler-python applocation/NeuroLink/neuro_cli/skill/assets/callback_handler.py --handler-timeout 5",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {
                "subscription": {"status": "ok", "app_id": "neuro_unit_app"},
                "handler_audit": {
                    "runner": "explicit",
                    "returncode": 0,
                    "max_output_bytes": 16384,
                },
            },
            "failure_statuses": [
                "callback_timeout",
                "handler_failed",
                "handler_timeout",
                "handler_output_truncated",
            ],
        },
    },
    "control-cleanup": {
        "category": "control",
        "description": "release known workflow leases and confirm clean lease state",
        "commands": [
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('deploy')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('app-control')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease release --lease-id "
            f"{release_label('callback')}-lease",
            "python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases",
        ],
        "artifacts": [],
        "json_contract": {
            "success": {"leases": []},
            "failure_statuses": [
                "lease_not_found",
                "session_open_failed",
                "no_reply",
                "payload.status:error",
            ],
        },
    },
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
    "memory-evidence": {
        "category": "verification",
        "description": "collect build-time Neuro Unit memory evidence",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py "
            f"--run-build --no-c-style-check --label {release_label('memory-evidence')}",
        ],
        "artifacts": ["applocation/NeuroLink/memory-evidence"],
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
    "callback-smoke": {
        "category": "board_operation",
        "description": "run the app callback smoke path through the CLI wrapper",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py "
            "app-callback-smoke --app-id neuro_unit_app "
            f"--expected-app-echo {default_app_echo()} --trigger-every 1 "
            "--invoke-count 2",
        ],
        "artifacts": [],
    },
    "release-closure": {
        "category": "verification",
        "description": "review the release closure gate sequence without executing it",
        "commands": [
            "/home/emb/project/zephyrproject/.venv/bin/python "
            "applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py "
            f"--run-build --no-c-style-check --label {release_label('closure')}",
            "/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py",
            "/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q",
            "bash applocation/NeuroLink/tests/scripts/run_all_tests.sh",
            "git -C applocation/NeuroLink diff --check",
            "bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text",
            "bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5",
        ],
        "artifacts": [
            "applocation/NeuroLink/memory-evidence",
            "applocation/NeuroLink/smoke-evidence",
        ],
    },
}


WORKFLOW_METADATA_DEFAULTS = {
    "host_support": ["linux", "wsl"],
    "requires_hardware": False,
    "requires_serial": False,
    "requires_router": False,
    "requires_network": True,
    "destructive": False,
    "preconditions": [
        "west workspace contains applocation/NeuroLink",
        "NeuroLink Python environment is active or wrapper Python is explicit",
    ],
    "expected_success": [
        "process exit code is 0",
        "no JSON payload field reports ok=false or status=error",
    ],
    "failure_statuses": [
        {
            "status": "process_nonzero",
            "next_action": "inspect stderr and command-specific logs",
        },
        {
            "status": "json_parse_failed",
            "next_action": "treat stdout contract as broken for Agent automation",
        },
    ],
    "cleanup": [],
}


WORKFLOW_PLAN_METADATA = {
    "setup-linux": {
        "host_support": ["linux"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": True,
        "destructive": False,
        "preconditions": [
            "network access is available",
            "operator approves sudo package installation commands before running them",
            "workspace root contains zephyr and applocation/NeuroLink",
            "Zephyr SDK version from zephyr/SDK_VERSION is installed or will be installed before build commands",
        ],
        "expected_success": [
            "required system commands are available",
            "repository-local .venv exists and has west plus Neuro CLI dependencies",
            "ZEPHYR_SDK_INSTALL_DIR points at the SDK version recorded in zephyr/SDK_VERSION",
            "setup_neurolink_env.sh strict validation exits 0",
            "system init and system capabilities return ok=true JSON",
        ],
        "failure_statuses": [
            {
                "status": "missing_required_command",
                "next_action": "install the named system package and rerun setup validation",
            },
            {
                "status": "zephyr_sdk_missing",
                "next_action": "install Zephyr SDK or export ZEPHYR_SDK_INSTALL_DIR",
            },
            {
                "status": "python_dependency_missing",
                "next_action": "run pip install for Zephyr and Neuro CLI requirements",
            },
        ],
        "cleanup": [],
    },
    "setup-windows": {
        "host_support": ["windows", "wsl"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": True,
        "destructive": False,
        "preconditions": [
            "network access is available",
            "operator approves winget or manual installer prompts before running them",
            "PowerShell execution policy allows activating the local virtual environment",
            "workspace root contains zephyr and applocation/NeuroLink",
            "Zephyr SDK version from zephyr/SDK_VERSION is installed or will be installed before build commands",
        ],
        "expected_success": [
            "required commands are available from PowerShell",
            "repository-local .venv exists and has west plus Neuro CLI dependencies",
            "ZEPHYR_SDK_INSTALL_DIR points at the SDK version recorded in zephyr/SDK_VERSION",
            "setup_neurolink_env.ps1 strict validation exits 0",
            "system init and system capabilities return ok=true JSON",
        ],
        "failure_statuses": [
            {
                "status": "missing_required_command",
                "next_action": "install the named Windows tool and rerun setup validation",
            },
            {
                "status": "execution_policy_blocked",
                "next_action": "approve a process-scoped PowerShell execution policy change before activating .venv",
            },
            {
                "status": "zephyr_sdk_missing",
                "next_action": "install Zephyr SDK or set ZEPHYR_SDK_INSTALL_DIR",
            },
            {
                "status": "wsl_usb_required",
                "next_action": "switch to WSL USB/IP attach flow for Linux-canonical hardware evidence",
            },
        ],
        "cleanup": [],
    },
    "discover-host": {
        "host_support": ["linux", "windows", "wsl"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "workspace root contains zephyr and applocation/NeuroLink",
            "Neuro CLI wrapper can import the local source tree",
        ],
        "expected_success": [
            "system init reports ok=true and status=ready",
            "system capabilities reports protocol and release metadata",
            "agent_skill paths identify the canonical skill package",
        ],
        "failure_statuses": [
            {
                "status": "workspace_not_found",
                "next_action": "run from the west workspace root or pass an explicit project path in the Agent context",
            },
            {
                "status": "handler_failed",
                "next_action": "inspect CLI traceback-safe JSON error and Python environment",
            },
        ],
        "cleanup": [],
    },
    "discover-router": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": False,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "Linux shell can run the preflight helper",
            "operator approves auto-starting a local zenoh router if none is listening",
        ],
        "expected_success": [
            "preflight JSON includes router.listening=true",
            "router.port is 7447 unless overridden by the operator",
            "Unit no-reply is reported separately from router listener state",
        ],
        "failure_statuses": [
            {
                "status": "router_not_listening",
                "next_action": "start the router or rerun with --auto-start-router after operator approval",
            },
            {
                "status": "router_failed_to_start",
                "next_action": "inspect zenohd install/log output and port binding conflicts",
            },
            {
                "status": "no_reply_board_unreachable",
                "next_action": "router is reachable locally; check board network readiness or UART logs",
            },
        ],
        "cleanup": ["stop only router processes started by this workflow"],
    },
    "discover-serial": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": False,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "target Unit USB cable is attached",
            "Linux user has permission to read /dev/ttyACM* or /dev/ttyUSB*",
        ],
        "expected_success": [
            "preflight JSON includes serial.present=true",
            "serial.devices lists at least one /dev/ttyACM* or /dev/ttyUSB* path",
        ],
        "failure_statuses": [
            {
                "status": "serial_device_missing",
                "next_action": "check USB cable, dialout permissions, or WSL USB attach state",
            }
        ],
        "cleanup": [],
    },
    "discover-device": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "Zenoh router is listening on the expected endpoint",
            "target Unit has joined the router network",
        ],
        "expected_success": [
            "query device returns ok=true",
            "reply payload reports status=ok and node_id for the target Unit",
            "session_ready and network_state are captured when provided by firmware",
        ],
        "failure_statuses": [
            {
                "status": "session_open_failed",
                "next_action": "check router availability and Zenoh configuration",
            },
            {
                "status": "no_reply",
                "next_action": "run discover-router and discover-serial to split router, USB, and board-network causes",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as discovery failure and inspect payload message/status_code",
            },
        ],
        "cleanup": [],
    },
    "discover-apps": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "Unit query apps route is supported by firmware",
        ],
        "expected_success": [
            "query apps returns ok=true",
            "reply payload includes app_count, running_count, suspended_count, and apps list",
            "app_not_running is reported as a state classification before app invoke/control",
        ],
        "failure_statuses": [
            {
                "status": "app_not_running",
                "next_action": "deploy or activate the app only through protected control workflows",
            },
            {
                "status": "no_reply",
                "next_action": "rerun discover-device before app-specific diagnosis",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as discovery failure and inspect payload message/status_code",
            },
        ],
        "cleanup": [],
    },
    "discover-leases": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "Unit query leases route is supported by firmware",
        ],
        "expected_success": [
            "query leases returns ok=true",
            "reply payload includes leases list",
            "empty leases list is required before starting release smoke/control closure",
        ],
        "failure_statuses": [
            {
                "status": "lease_conflict",
                "next_action": "release owned stale leases or wait for TTL expiry before protected control",
            },
            {
                "status": "no_reply",
                "next_action": "rerun discover-device before lease-specific diagnosis",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as discovery failure and inspect payload message/status_code",
            },
        ],
        "cleanup": [],
    },
    "control-health": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-apps and discover-leases are available for the target Unit",
        ],
        "expected_success": [
            "query device, query apps, and query leases all return ok=true",
            "nested reply payloads report status=ok",
            "lease list is empty or only contains leases intentionally owned by the operator",
        ],
        "failure_statuses": [
            {
                "status": "no_reply",
                "next_action": "rerun discover-router and discover-device before control",
            },
            {
                "status": "payload.status:error",
                "next_action": "stop control flow and inspect nested Unit status_code/message",
            },
        ],
        "cleanup": [],
    },
    "control-deploy": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-leases shows no conflicting update/app lease",
            "fresh LLEXT artifact exists at build/neurolink_unit/llext/neuro_unit_app.llext",
        ],
        "expected_success": [
            "lease acquire returns status=ok for update/app/neuro_unit_app/activate",
            "deploy prepare, verify, and activate return status=ok in order",
            "post-activate query apps reports neuro_unit_app active or running",
            "cleanup releases the deploy lease and query leases is empty",
        ],
        "failure_statuses": [
            {
                "status": "lease_conflict",
                "next_action": "release owned stale update lease or wait for TTL expiry",
            },
            {
                "status": "artifact_missing",
                "next_action": "run workflow plan app-build and rebuild the LLEXT artifact",
            },
            {
                "status": "payload.status:error",
                "next_action": "stop deploy flow and preserve prepare/verify/activate payload evidence",
            },
        ],
        "cleanup": [
            f"release lease {release_label('deploy')}-lease",
            "query leases until update/app/neuro_unit_app/activate lease is absent",
        ],
    },
    "control-app-invoke": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-apps reports neuro_unit_app running or ready for invoke",
            "discover-leases shows no conflicting app control lease",
        ],
        "expected_success": [
            "lease acquire returns status=ok for app/neuro_unit_app/control",
            "app invoke returns status=ok and app_id=neuro_unit_app",
            "cleanup releases the app control lease and query leases is empty",
        ],
        "failure_statuses": [
            {
                "status": "app_not_running",
                "next_action": "run control-deploy before app invoke",
            },
            {
                "status": "lease_conflict",
                "next_action": "release owned stale app control lease or wait for TTL expiry",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as command failure",
            },
        ],
        "cleanup": [
            f"release lease {release_label('app-control')}-lease",
            "query leases until app/neuro_unit_app/control lease is absent",
        ],
    },
    "control-callback": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": True,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "discover-apps reports neuro_unit_app running",
            "callback handler execution is explicitly enabled if a handler is used",
        ],
        "expected_success": [
            "callback config on returns status=ok",
            "app invoke returns status=ok and publishes the callback event",
            "monitor app-events captures a fresh app-scoped callback event",
            "callback config off and lease release complete during cleanup",
        ],
        "failure_statuses": [
            {
                "status": "callback_timeout",
                "next_action": "check app callback config, event name, and app-scoped subscription path",
            },
            {
                "status": "handler_failed",
                "next_action": "inspect explicit handler audit stdout/stderr/returncode",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit error as callback control failure",
            },
        ],
        "cleanup": [
            "turn callback mode off when the workflow enabled it",
            f"release lease {release_label('callback')}-lease",
            "undeclare event subscribers and query leases",
        ],
    },
    "control-monitor": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "discover-device succeeds for the target Unit",
            "operator explicitly approves any local handler command or handler Python file",
        ],
        "expected_success": [
            "monitor app-events subscribes to the app-scoped callback key expression",
            "optional handler audit reports runner, cwd, timeout, returncode, stdout, and stderr",
            "event collection stops on max-events or duration without leaking non-JSON stdout",
        ],
        "failure_statuses": [
            {
                "status": "handler_failed",
                "next_action": "inspect handler audit fields and do not retry blindly",
            },
            {
                "status": "callback_timeout",
                "next_action": "verify callback is enabled and event name matches monitor path",
            },
        ],
        "cleanup": ["undeclare subscriber and stop local handler execution"],
    },
    "control-cleanup": {
        "host_support": ["linux", "wsl"],
        "requires_hardware": True,
        "requires_serial": False,
        "requires_router": True,
        "requires_network": False,
        "destructive": False,
        "preconditions": [
            "one or more known release workflow lease ids may still be active",
            "target Unit is reachable enough to query leases",
        ],
        "expected_success": [
            "owned workflow leases are released or already absent",
            "final query leases returns ok=true with an empty leases list for closure",
        ],
        "failure_statuses": [
            {
                "status": "lease_not_found",
                "next_action": "treat as already-clean for the named workflow lease and continue final query leases",
            },
            {
                "status": "payload.status:error",
                "next_action": "inspect lease payload and avoid claiming cleanup closure",
            },
        ],
        "cleanup": ["repeat query leases after each release attempt"],
    },
    "app-build": {
        "preconditions": [
            "Unit EDK headers and LLEXT support output are available or buildable",
            "Zephyr toolchain and west workspace are configured",
        ],
        "expected_success": [
            "build command exits 0",
            "build/neurolink_unit_app/neuro_unit_app.llext exists",
        ],
    },
    "unit-build": {
        "preconditions": [
            "Zephyr SDK or compatible toolchain is installed",
            "west workspace modules are initialized",
        ],
        "expected_success": [
            "build command exits 0",
            "build/neurolink_unit/zephyr/zephyr.elf exists",
        ],
    },
    "unit-edk": {
        "preconditions": [
            "Zephyr SDK or compatible toolchain is installed",
            "Unit firmware build configuration can generate LLEXT EDK output",
        ],
        "expected_success": [
            "build command exits 0",
            "build/neurolink_unit/zephyr/llext-edk exists",
        ],
    },
    "unit-tests": {
        "preconditions": [
            "native_sim toolchain support is available",
            "west workspace modules are initialized",
        ],
        "expected_success": [
            "west build exits 0",
            "native_sim Unit tests report success",
        ],
    },
    "cli-tests": {
        "host_support": ["linux", "windows", "wsl"],
        "requires_network": False,
        "preconditions": [
            "Neuro CLI Python test dependencies are installed",
            "zenoh import is available or tests install a fake module where expected",
        ],
        "expected_success": [
            "pytest exits 0",
            "CLI JSON and wrapper contract regressions pass",
        ],
    },
    "memory-evidence": {
        "preconditions": [
            "Zephyr SDK or compatible toolchain is installed",
            "memory evidence collector can run a Unit build",
        ],
        "expected_success": [
            "collector exits 0",
            "memory evidence JSON and summary artifacts are written",
        ],
    },
    "preflight": {
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "preconditions": [
            "target Unit USB serial device is visible to the host",
            "Zenoh router can be started or is already reachable",
            "Neuro CLI Python dependencies are installed or installable",
        ],
        "expected_success": [
            "preflight exits 0",
            "serial, router, and Unit query checks pass",
        ],
        "failure_statuses": [
            {
                "status": "serial_device_missing",
                "next_action": "check USB cable, permissions, or WSL USB attach",
            },
            {
                "status": "no_reply_board_unreachable",
                "next_action": "check board network readiness and UART logs",
            },
        ],
        "cleanup": ["stop only router processes started by this workflow"],
    },
    "smoke": {
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "preflight passes for the target Unit",
            "fresh Unit app artifact is buildable",
        ],
        "expected_success": [
            "smoke script exits 0",
            "fresh smoke evidence is written",
            "post-smoke lease query is empty",
        ],
        "cleanup": ["release any acquired app/update leases"],
    },
    "callback-smoke": {
        "requires_hardware": True,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "target Unit is reachable through query device",
            "neuro_unit_app is deployed and activated",
            "callback handler execution is explicitly enabled if a handler is used",
        ],
        "expected_success": [
            "wrapper exits 0",
            "callback events are fresh and app-scoped",
            "nested Unit reply payloads do not report status=error",
        ],
        "failure_statuses": [
            {
                "status": "handler_failed",
                "next_action": "inspect audited handler stderr/stdout and return code",
            },
            {
                "status": "payload.status:error",
                "next_action": "treat nested Unit reply as command failure",
            },
        ],
        "cleanup": ["release callback smoke lease when acquired"],
    },
    "release-closure": {
        "requires_hardware": True,
        "requires_serial": True,
        "requires_router": True,
        "destructive": True,
        "preconditions": [
            "local CLI, wrapper, script, build, and skill gates are green",
            "hardware preflight and smoke can run against the target Unit",
            "release identity has not been promoted prematurely",
        ],
        "expected_success": [
            "all listed gates exit 0",
            "memory and smoke evidence are fresh",
            "release identity remains controlled until final promotion slice",
        ],
        "cleanup": ["release any acquired leases", "capture final evidence paths"],
    },
}


def workflow_agent_metadata(workflow_name: str) -> dict:
    metadata = dict(WORKFLOW_METADATA_DEFAULTS)
    metadata.update(WORKFLOW_PLAN_METADATA.get(workflow_name, {}))
    return metadata


def build_workflow_surface() -> dict:
    plans = []
    for workflow_name in sorted(WORKFLOW_PLANS.keys()):
        workflow = WORKFLOW_PLANS[workflow_name]
        metadata = workflow_agent_metadata(workflow_name)
        plans.append(
            {
                "workflow": workflow_name,
                "category": workflow["category"],
                "description": workflow["description"],
                "host_support": metadata["host_support"],
                "requires_hardware": metadata["requires_hardware"],
                "requires_serial": metadata["requires_serial"],
                "requires_router": metadata["requires_router"],
                "requires_network": metadata["requires_network"],
                "destructive": metadata["destructive"],
                "plan_command": f"workflow plan {workflow_name}",
            }
        )

    return {
        "schema_version": WORKFLOW_PLAN_SCHEMA_VERSION,
        "plan_command": "workflow plan <name>",
        "system_plan_command": "system workflow plan <name>",
        "categories": sorted({plan["category"] for plan in plans}),
        "plans": plans,
    }


def build_workflow_plan(args: argparse.Namespace) -> dict:
    workflow = WORKFLOW_PLANS[args.workflow]
    metadata = workflow_agent_metadata(args.workflow)
    neurolink_root = find_neurolink_root(Path.cwd())
    workspace_root = neurolink_root.parent.parent if neurolink_root else Path.cwd()
    return {
        "ok": True,
        "workflow": args.workflow,
        "schema_version": WORKFLOW_PLAN_SCHEMA_VERSION,
        "category": workflow["category"],
        "description": workflow["description"],
        "release_target": RELEASE_TARGET,
        "host_support": metadata["host_support"],
        "requires_hardware": metadata["requires_hardware"],
        "requires_serial": metadata["requires_serial"],
        "requires_router": metadata["requires_router"],
        "requires_network": metadata["requires_network"],
        "destructive": metadata["destructive"],
        "preconditions": metadata["preconditions"],
        "expected_success": metadata["expected_success"],
        "failure_statuses": metadata["failure_statuses"],
        "cleanup": metadata["cleanup"],
        "protocol": {
            "version": protocol.DEFAULT_PROTOCOL_VERSION,
            "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
            "supported_wire_encodings": protocol.SUPPORTED_WIRE_ENCODINGS,
            "planned_wire_encodings": protocol.PLANNED_WIRE_ENCODINGS,
            "cbor_v2_enabled": protocol.DEFAULT_WIRE_ENCODING == "cbor-v2",
        },
        "executes_commands": False,
        "workspace_root": str(workspace_root),
        "agent_skill": build_agent_skill_metadata(neurolink_root),
        "commands": workflow["commands"],
        "artifacts": workflow["artifacts"],
        "json_contract": workflow.get("json_contract", {}),
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
                "protocol": {
                    "version": protocol.DEFAULT_PROTOCOL_VERSION,
                    "wire_encoding": protocol.DEFAULT_WIRE_ENCODING,
                    "supported_wire_encodings": protocol.SUPPORTED_WIRE_ENCODINGS,
                    "planned_wire_encodings": protocol.PLANNED_WIRE_ENCODINGS,
                    "cbor_v2_enabled": protocol.DEFAULT_WIRE_ENCODING == "cbor-v2",
                },
                "agent_skill": {
                    **build_agent_skill_metadata(neurolink_root),
                    "init_diagnostics_command": "system init --output json",
                },
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
