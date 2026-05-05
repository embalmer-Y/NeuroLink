from __future__ import annotations

from dataclasses import dataclass, field
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from .common import new_id
from .policy import SideEffectLevel


TOOL_MANIFEST_SCHEMA_VERSION = "1.2.0-tool-manifest-v1"
STATE_SYNC_SCHEMA_VERSION = "1.2.0-state-sync-v1"
APP_CONTROL_TOOL_ACTIONS = {
    "system_start_app": "start",
    "system_stop_app": "stop",
    "system_unload_app": "unload",
}


@dataclass(frozen=True)
class ToolContract:
    tool_name: str
    description: str
    side_effect_level: SideEffectLevel
    argv_template: tuple[str, ...] = ()
    resource: str = ""
    required_arguments: tuple[str, ...] = ()
    required_resources: tuple[str, ...] = ()
    timeout_seconds: int = 10
    retryable: bool = False
    approval_required: bool = False
    cleanup_hint: str | None = None
    output_contract: dict[str, Any] = field(
        default_factory=lambda: cast(dict[str, Any], {})
    )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolContract":
        return cls(
            tool_name=str(payload.get("name") or payload.get("tool_name") or ""),
            description=str(payload.get("description") or ""),
            side_effect_level=SideEffectLevel(str(payload.get("side_effect_level") or "read_only")),
            argv_template=tuple(str(item) for item in payload.get("argv_template") or ()),
            resource=str(payload.get("resource") or ""),
            required_arguments=tuple(str(item) for item in payload.get("required_arguments") or ()),
            required_resources=tuple(str(item) for item in payload.get("lease_requirements") or payload.get("required_resources") or ()),
            timeout_seconds=int(payload.get("timeout_seconds", 10)),
            retryable=bool(payload.get("retryable", False)),
            approval_required=bool(payload.get("approval_required", False)),
            cleanup_hint=(payload.get("cleanup_hints") or [payload.get("cleanup_hint") or None])[0],
            output_contract=dict(payload.get("output_contract") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.tool_name,
            "description": self.description,
            "argv_template": list(self.argv_template),
            "resource": self.resource,
            "required_arguments": list(self.required_arguments),
            "side_effect_level": self.side_effect_level.value,
            "lease_requirements": list(self.required_resources),
            "timeout_seconds": self.timeout_seconds,
            "retryable": self.retryable,
            "approval_required": self.approval_required,
            "cleanup_hints": [self.cleanup_hint] if self.cleanup_hint else [],
            "output_contract": dict(self.output_contract),
        }


@dataclass(frozen=True)
class StateSyncSurface:
    ok: bool
    status: str
    payload: dict[str, Any]
    attempt: int = 1
    max_attempts: int = 1
    retried: bool = False
    failure_status: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StateSyncSurface":
        return cls(
            ok=bool(payload.get("ok", False)),
            status=str(payload.get("status") or "unknown"),
            payload=dict(payload.get("payload") or {}),
            attempt=int(payload.get("attempt", 1)),
            max_attempts=int(payload.get("max_attempts", 1)),
            retried=bool(payload.get("retried", False)),
            failure_status=str(payload.get("failure_status") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "payload": dict(self.payload),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "retried": self.retried,
            "failure_status": self.failure_status,
        }


@dataclass(frozen=True)
class StateSyncSnapshot:
    status: str
    state: dict[str, StateSyncSurface]
    recommended_next_actions: tuple[str, ...]
    schema_version: str = STATE_SYNC_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StateSyncSnapshot":
        state_payload = dict(payload.get("state") or {})
        return cls(
            status=str(payload.get("status") or "unknown"),
            state={
                name: StateSyncSurface.from_dict(dict(surface_payload))
                for name, surface_payload in state_payload.items()
            },
            recommended_next_actions=tuple(
                str(item) for item in payload.get("recommended_next_actions") or ()
            ),
            schema_version=str(payload.get("schema_version") or STATE_SYNC_SCHEMA_VERSION),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.status == "ok",
            "status": self.status,
            "schema_version": self.schema_version,
            "state": {
                name: surface.to_dict() for name, surface in self.state.items()
            },
            "recommended_next_actions": list(self.recommended_next_actions),
        }


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_result_id: str
    tool_name: str
    status: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_result_id": self.tool_result_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class CommandExecutionResult:
    exit_code: int
    stdout: str
    stderr: str = ""


class FakeUnitToolAdapter:
    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "adapter_kind": "fake",
            "runtime_source": "fake_no_model",
            "wrapper_path": "neuro_cli/scripts/invoke_neuro_cli.py",
            "node": "unit-01",
            "source_core": "core-cli",
            "source_agent": "rational",
            "supports_real_process": False,
        }

    def tool_manifest(self) -> tuple[ToolContract, ...]:
        return (
            ToolContract(
                tool_name="system_query_device",
                description="Read current Unit device/network state through the query plane.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "query",
                    "device",
                    "--output",
                    "json",
                ),
                resource="device query plane",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_query_apps",
                description="Read current Unit application lifecycle state through the query plane.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "query",
                    "apps",
                    "--output",
                    "json",
                ),
                resource="app query plane",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_query_leases",
                description="Read current active leases before any side-effecting action.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "query",
                    "leases",
                    "--output",
                    "json",
                ),
                resource="lease query plane",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_state_sync",
                description="Aggregate device, apps, leases, protocol, and agent runtime metadata into one read-only sync snapshot.",
                side_effect_level=SideEffectLevel.READ_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "system",
                    "state-sync",
                    "--output",
                    "json",
                ),
                resource="state sync aggregate",
                required_arguments=("--node",),
                timeout_seconds=10,
                retryable=True,
                cleanup_hint="review active leases before side-effecting commands",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "partial_failure",
                        "no_reply",
                        "query_failed",
                        "error_reply",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_capabilities",
                description="Read stable Neuro CLI protocol, workflow, and agent runtime metadata.",
                side_effect_level=SideEffectLevel.OBSERVE_ONLY,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "system",
                    "capabilities",
                    "--output",
                    "json",
                ),
                resource="capability map",
                timeout_seconds=5,
                retryable=False,
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": ["parse_failed"],
                },
            ),
            ToolContract(
                tool_name="system_restart_app",
                description="Restart a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "control",
                    "app-restart",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before restart",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_start_app",
                description="Start a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "app",
                    "start",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before start",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_stop_app",
                description="Stop a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "app",
                    "stop",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before stop",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
            ToolContract(
                tool_name="system_unload_app",
                description="Unload a Unit application through the control plane after explicit approval.",
                side_effect_level=SideEffectLevel.APPROVAL_REQUIRED,
                argv_template=(
                    "python",
                    "neuro_cli/scripts/invoke_neuro_cli.py",
                    "app",
                    "unload",
                    "--output",
                    "json",
                ),
                resource="app control plane",
                required_arguments=("--node", "--app-id", "--lease-id"),
                required_resources=("app_control_lease",),
                timeout_seconds=15,
                retryable=False,
                approval_required=True,
                cleanup_hint="confirm target app identity and active leases before unload",
                output_contract={
                    "format": "json",
                    "top_level_ok": True,
                    "failure_statuses": [
                        "approval_required",
                        "lease_missing",
                        "control_failed",
                        "parse_failed",
                    ],
                },
            ),
        )

    def tool_manifest_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
            "tools": [contract.to_dict() for contract in self.tool_manifest()],
        }

    def parse_tool_manifest_payload(
        self, payload: dict[str, Any]
    ) -> tuple[ToolContract, ...]:
        return tuple(
            ToolContract.from_dict(dict(item)) for item in payload.get("tools") or ()
        )

    def parse_state_sync_payload(self, payload: dict[str, Any]) -> StateSyncSnapshot:
        return StateSyncSnapshot.from_dict(payload)

    def describe_tool(self, tool_name: str) -> ToolContract | None:
        for contract in self.tool_manifest():
            if contract.tool_name == tool_name:
                return contract
        return None

    def build_state_sync_snapshot(self, args: dict[str, Any]) -> StateSyncSnapshot:
        event_ids = list(args.get("event_ids") or [])
        device = StateSyncSurface(
            ok=True,
            status="ok",
            payload={
                "status": "ok",
                "network_state": "NETWORK_READY",
                "ipv4": "192.168.2.67",
            },
        )
        apps = StateSyncSurface(
            ok=True,
            status="ok",
            payload={
                "status": "ok",
                "app_count": 0,
                "apps": [],
                "observed_event_ids": event_ids,
            },
        )
        leases = StateSyncSurface(
            ok=True,
            status="ok",
            payload={
                "status": "ok",
                "leases": [],
            },
        )
        return StateSyncSnapshot(
            status="ok",
            state={"device": device, "apps": apps, "leases": leases},
            recommended_next_actions=(
                "state sync is clean; read-only delegated reasoning may continue",
            ),
        )

    def _fake_query_payload(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        event_ids = list(args.get("event_ids") or [])
        reply_payload: dict[str, Any]
        if tool_name == "system_query_device":
            reply_payload = {
                "status": "ok",
                "network_state": "NETWORK_READY",
                "ipv4": "192.168.2.67",
            }
        elif tool_name == "system_query_apps":
            reply_payload = {
                "status": "ok",
                "app_count": 0,
                "apps": [],
                "observed_event_ids": event_ids,
            }
        elif tool_name == "system_query_leases":
            reply_payload = {
                "status": "ok",
                "leases": [],
            }
        elif tool_name == "system_capabilities":
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "agent_runtime": "1.2.0-agent-runtime-v1",
                    "tool_manifest_command": "system tool-manifest --output json",
                    "state_sync_command": "system state-sync --output json",
                },
            }
        elif tool_name == "system_restart_app":
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "status": "ok",
                    "requested_action": "restart_app",
                    "requested_app": str(args.get("app") or "default-app"),
                },
            }
        elif tool_name in APP_CONTROL_TOOL_ACTIONS:
            action = APP_CONTROL_TOOL_ACTIONS[tool_name]
            return {
                "ok": True,
                "status": "ok",
                "payload": {
                    "status": "ok",
                    "requested_action": action,
                    "requested_app": str(
                        args.get("app_id") or args.get("app") or "default-app"
                    ),
                },
            }
        else:
            raise ValueError(f"unsupported fake tool: {tool_name}")
        return {
            "ok": True,
            "status": "ok",
            "payload": {"request_id": new_id("req")},
            "replies": [{"ok": True, "payload": reply_payload}],
        }

    def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
        contract = self.describe_tool(tool_name)
        if contract is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": "unknown_tool",
                    "failure_class": "manifest_lookup_failed",
                },
            )
        payload: dict[str, Any] = {
            "contract": contract.to_dict(),
            "mode": "fake_no_model",
            "side_effect_level": contract.side_effect_level.value,
            "event_ids": list(args.get("event_ids") or []),
        }
        if tool_name == "system_state_sync":
            payload["state_sync"] = self.build_state_sync_snapshot(args).to_dict()
        else:
            payload["result"] = self._fake_query_payload(tool_name, args)
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=tool_name,
            status="ok",
            payload=payload,
        )


class NeuroCliToolAdapter:
    def __init__(
        self,
        *,
        node: str = "unit-01",
        source_core: str = "core-cli",
        source_agent: str = "rational",
        timeout_seconds: int = 10,
        python_executable: str | None = None,
        wrapper_path: str | Path | None = None,
        runner: Any | None = None,
    ) -> None:
        self.node = node
        self.source_core = source_core
        self.source_agent = source_agent
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable or sys.executable
        self.wrapper_path = Path(wrapper_path) if wrapper_path else self._default_wrapper_path()
        self.runner = runner or self._run_subprocess
        self._manifest_cache: tuple[ToolContract, ...] | None = None

    @staticmethod
    def _default_wrapper_path() -> Path:
        return Path(__file__).resolve().parent.parent / "neuro_cli" / "scripts" / "invoke_neuro_cli.py"

    def _base_command(self, output: str = "json") -> list[str]:
        return [
            self.python_executable,
            str(self.wrapper_path),
            "--output",
            output,
            "--node",
            self.node,
            "--source-core",
            self.source_core,
            "--source-agent",
            self.source_agent,
            "--timeout",
            str(self.timeout_seconds),
        ]

    @staticmethod
    def _run_subprocess(argv: list[str], timeout_seconds: int) -> CommandExecutionResult:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandExecutionResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @staticmethod
    def _parse_json_stdout(command_result: CommandExecutionResult) -> dict[str, Any]:
        try:
            payload: Any = json.loads(command_result.stdout)
        except json.JSONDecodeError as exc:
            if command_result.exit_code != 0:
                raise ValueError(f"command_exit_{command_result.exit_code}") from exc
            raise ValueError("parse_failed") from exc
        if not isinstance(payload, dict):
            raise ValueError("parse_failed")
        return cast(dict[str, Any], payload)

    @staticmethod
    def _parse_jsonl_stdout(command_result: CommandExecutionResult) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in command_result.stdout.splitlines():
            if not line.strip():
                continue
            payload: Any = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("parse_failed")
            rows.append(cast(dict[str, Any], payload))
        if command_result.exit_code != 0:
            raise ValueError(f"command_exit_{command_result.exit_code}")
        return rows

    def tool_manifest(self) -> tuple[ToolContract, ...]:
        if self._manifest_cache is not None:
            return self._manifest_cache

        argv = [*self._base_command(), "system", "tool-manifest"]
        command_result = self.runner(argv, self.timeout_seconds)
        payload = self._parse_json_stdout(command_result)
        if not payload.get("ok", False):
            raise ValueError(str(payload.get("status") or "tool_manifest_failed"))
        self._manifest_cache = tuple(
            ToolContract.from_dict(dict(item)) for item in payload.get("tools") or ()
        )
        return self._manifest_cache

    def runtime_metadata(self) -> dict[str, Any]:
        return {
            "adapter_kind": "neuro-cli",
            "runtime_source": "neuro_cli_wrapper",
            "wrapper_path": str(self.wrapper_path),
            "node": self.node,
            "source_core": self.source_core,
            "source_agent": self.source_agent,
            "supports_real_process": self.runner is self._run_subprocess,
            "timeout_seconds": self.timeout_seconds,
        }

    def tool_manifest_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "schema_version": TOOL_MANIFEST_SCHEMA_VERSION,
            "tools": [contract.to_dict() for contract in self.tool_manifest()],
        }

    def describe_tool(self, tool_name: str) -> ToolContract | None:
        for contract in self.tool_manifest():
            if contract.tool_name == tool_name:
                return contract
        return None

    @staticmethod
    def _contract_command_suffix(contract: ToolContract) -> list[str]:
        argv = list(contract.argv_template)
        if len(argv) >= 2:
            argv = argv[2:]
        suffix: list[str] = []
        skip_next = False
        for token in argv:
            if skip_next:
                skip_next = False
                continue
            if token == "--output":
                skip_next = True
                continue
            suffix.append(token)
        return suffix

    @staticmethod
    def _extract_apps_payload(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
        replies = cast(list[Any] | None, result_payload.get("replies"))
        if not isinstance(replies, list):
            return []
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            reply_dict = cast(dict[str, Any], reply)
            reply_payload = cast(dict[str, Any] | None, reply_dict.get("payload"))
            if not isinstance(reply_payload, dict):
                continue
            apps = cast(list[Any] | None, reply_payload.get("apps"))
            if not isinstance(apps, list):
                continue
            resolved_apps: list[dict[str, Any]] = []
            for app in apps:
                if isinstance(app, dict):
                    resolved_apps.append(cast(dict[str, Any], app))
            return resolved_apps
        return []

    @staticmethod
    def _extract_lease_rows(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
        replies = cast(list[Any] | None, result_payload.get("replies"))
        if not isinstance(replies, list):
            return []
        for reply in replies:
            if not isinstance(reply, dict):
                continue
            reply_dict = cast(dict[str, Any], reply)
            reply_payload = cast(dict[str, Any] | None, reply_dict.get("payload"))
            if not isinstance(reply_payload, dict):
                continue
            leases = cast(list[Any] | None, reply_payload.get("leases"))
            if not isinstance(leases, list):
                continue
            rows: list[dict[str, Any]] = []
            for lease in leases:
                if isinstance(lease, dict):
                    rows.append(cast(dict[str, Any], lease))
            return rows
        return []

    def _build_contract_command_with_args(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> list[str]:
        argv = [*self._base_command(), *self._contract_command_suffix(contract)]
        for argument_name in contract.required_arguments:
            if argument_name == "--node":
                continue
            candidate_keys = [argument_name.lstrip("-").replace("-", "_")]
            if argument_name == "--app-id":
                candidate_keys.extend(["app", "app_id"])
            if argument_name == "--lease-id":
                candidate_keys.append("lease_id")
            if argument_name == "--start-args":
                candidate_keys.append("start_args")
            value = None
            for key in candidate_keys:
                candidate = args.get(key)
                if candidate not in (None, ""):
                    value = candidate
                    break
            if value not in (None, ""):
                argv.extend([argument_name, str(value)])
        optional_start_args = args.get("start_args")
        if optional_start_args not in (None, "") and "--start-args" not in argv:
            argv.extend(["--start-args", str(optional_start_args)])
        return argv

    def _execute_raw_contract_command(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> tuple[CommandExecutionResult, dict[str, Any] | None, str | None]:
        argv = self._build_contract_command_with_args(contract, args)
        command_result = self.runner(argv, contract.timeout_seconds)
        try:
            payload = self._parse_json_stdout(command_result)
        except ValueError as exc:
            return command_result, None, str(exc)
        return command_result, payload, None

    def _resolve_control_app_args(self, args: dict[str, Any]) -> dict[str, Any] | None:
        resolved_args = dict(args)
        app_id = str(args.get("app_id") or args.get("app") or "")
        if not app_id:
            apps_contract = self.describe_tool("system_query_apps")
            if apps_contract is not None:
                _command_result, apps_payload, apps_error = self._execute_raw_contract_command(
                    apps_contract,
                    {},
                )
                if apps_payload is not None and apps_error is None:
                    observed_apps = self._extract_apps_payload(apps_payload)
                    if len(observed_apps) == 1:
                        observed_app = observed_apps[0]
                        app_id = str(
                            observed_app.get("app_id")
                            or observed_app.get("name")
                            or observed_app.get("app")
                            or ""
                        )
        if not app_id:
            return None

        lease_id = str(args.get("lease_id") or "")
        if not lease_id:
            leases_contract = self.describe_tool("system_query_leases")
            if leases_contract is not None:
                _command_result, leases_payload, leases_error = self._execute_raw_contract_command(
                    leases_contract,
                    {},
                )
                if leases_payload is not None and leases_error is None:
                    target_resource = f"app/{app_id}/control"
                    for lease in self._extract_lease_rows(leases_payload):
                        resource = str(lease.get("resource") or "")
                        if resource != target_resource:
                            continue
                        lease_id = str(lease.get("lease_id") or "")
                        if lease_id:
                            break
        if not lease_id:
            return None

        resolved_args.setdefault("app_id", app_id)
        resolved_args.setdefault("app", app_id)
        resolved_args.setdefault("lease_id", lease_id)
        return resolved_args

    def _execute_single_app_control(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        resolved_args = self._resolve_control_app_args(args)
        if resolved_args is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": "control_args_unresolved",
                    "failure_class": "dynamic_argument_resolution_failed",
                    "contract": contract.to_dict(),
                    "requested_args": dict(args),
                },
            )

        command_result, payload, command_error = self._execute_raw_contract_command(
            contract,
            resolved_args,
        )
        if command_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": command_error,
                    "failure_class": "control_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stderr": command_result.stderr,
                },
            )
        assert payload is not None
        payload_status = str(payload.get("status") or "unknown")
        nested_failure_status = self._extract_nested_failure_status(payload)
        if not payload.get("ok", False) or nested_failure_status:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=contract.tool_name,
                status="error",
                payload={
                    "failure_status": nested_failure_status or payload_status,
                    "failure_class": "control_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "result": payload,
                },
            )
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=contract.tool_name,
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "resolved_args": resolved_args,
                "result": payload,
            },
        )

    def _execute_restart_app(
        self,
        contract: ToolContract,
        args: dict[str, Any],
    ) -> ToolExecutionResult:
        resolved_args = self._resolve_control_app_args(args)
        if resolved_args is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": "restart_args_unresolved",
                    "failure_class": "dynamic_argument_resolution_failed",
                    "contract": contract.to_dict(),
                    "requested_args": dict(args),
                },
            )

        stop_contract = ToolContract(
            tool_name="system_restart_app.stop",
            description="stop app as first half of restart",
            side_effect_level=contract.side_effect_level,
            argv_template=(
                "python",
                "neuro_cli/scripts/invoke_neuro_cli.py",
                "app",
                "stop",
                "--output",
                "json",
            ),
            required_arguments=("--node", "--app-id", "--lease-id"),
            timeout_seconds=contract.timeout_seconds,
        )
        start_contract = ToolContract(
            tool_name="system_restart_app.start",
            description="start app as second half of restart",
            side_effect_level=contract.side_effect_level,
            argv_template=(
                "python",
                "neuro_cli/scripts/invoke_neuro_cli.py",
                "app",
                "start",
                "--output",
                "json",
            ),
            required_arguments=("--node", "--app-id", "--lease-id"),
            timeout_seconds=contract.timeout_seconds,
        )

        stop_command_result, stop_payload, stop_error = self._execute_raw_contract_command(
            stop_contract,
            resolved_args,
        )
        if stop_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": stop_error,
                    "failure_class": "restart_stop_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stderr": stop_command_result.stderr,
                },
            )
        assert stop_payload is not None
        stop_status = str(stop_payload.get("status") or "unknown")
        if not stop_payload.get("ok", False) or self._extract_nested_failure_status(stop_payload):
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": self._extract_nested_failure_status(stop_payload)
                    or stop_status,
                    "failure_class": "restart_stop_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stop_result": stop_payload,
                },
            )

        start_command_result, start_payload, start_error = self._execute_raw_contract_command(
            start_contract,
            resolved_args,
        )
        if start_error is not None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": start_error,
                    "failure_class": "restart_start_cli_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stop_result": stop_payload,
                    "stderr": start_command_result.stderr,
                },
            )
        assert start_payload is not None
        start_status = str(start_payload.get("status") or "unknown")
        if not start_payload.get("ok", False) or self._extract_nested_failure_status(start_payload):
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name="system_restart_app",
                status="error",
                payload={
                    "failure_status": self._extract_nested_failure_status(start_payload)
                    or start_status,
                    "failure_class": "restart_start_failed",
                    "contract": contract.to_dict(),
                    "resolved_args": resolved_args,
                    "stop_result": stop_payload,
                    "start_result": start_payload,
                },
            )

        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name="system_restart_app",
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "resolved_args": resolved_args,
                "stop_result": stop_payload,
                "start_result": start_payload,
            },
        )

    @staticmethod
    def _extract_nested_failure_status(payload: dict[str, Any]) -> str:
        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            nested_payload_dict = cast(dict[str, Any], nested_payload)
            nested_status = str(nested_payload_dict.get("status") or "")
            if nested_status and nested_status != "ok":
                return nested_status
        replies = payload.get("replies")
        if isinstance(replies, list):
            for reply in cast(list[Any], replies):
                if not isinstance(reply, dict):
                    continue
                reply_dict = cast(dict[str, Any], reply)
                reply_payload = reply_dict.get("payload")
                if isinstance(reply_payload, dict):
                    reply_payload_dict = cast(dict[str, Any], reply_payload)
                    reply_status = str(reply_payload_dict.get("status") or "")
                    if reply_status and reply_status != "ok":
                        return reply_status
        return ""

    def execute(self, tool_name: str, args: dict[str, Any]) -> ToolExecutionResult:
        contract = self.describe_tool(tool_name)
        if contract is None:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": "unknown_tool",
                    "failure_class": "manifest_lookup_failed",
                },
            )

        if tool_name == "system_restart_app":
            return self._execute_restart_app(contract, args)
        if tool_name in APP_CONTROL_TOOL_ACTIONS:
            return self._execute_single_app_control(contract, args)

        argv = [*self._base_command(), *self._contract_command_suffix(contract)]
        command_result = self.runner(argv, contract.timeout_seconds)
        try:
            payload = self._parse_json_stdout(command_result)
        except ValueError as exc:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": str(exc),
                    "failure_class": "cli_execution_failed",
                    "stderr": command_result.stderr,
                },
            )

        status = str(payload.get("status") or "unknown")
        if not payload.get("ok", False):
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": status,
                    "failure_class": "top_level_status_failure",
                    "payload": payload,
                },
            )

        nested_failure_status = self._extract_nested_failure_status(payload)
        if nested_failure_status:
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": nested_failure_status,
                    "failure_class": "nested_payload_status_failure",
                    "payload": payload,
                },
            )

        result_payload: dict[str, Any] = {"contract": contract.to_dict()}
        if tool_name == "system_state_sync":
            result_payload["state_sync"] = StateSyncSnapshot.from_dict(payload).to_dict()
        else:
            result_payload["result"] = payload
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=tool_name,
            status="ok",
            payload=result_payload,
        )

    def collect_agent_events(self, max_events: int = 0) -> list[dict[str, Any]]:
        argv = [
            *self._base_command(output="jsonl"),
            "monitor",
            "agent-events",
            "--max-events",
            str(max(0, int(max_events))),
        ]
        command_result = self.runner(argv, self.timeout_seconds)
        return self._parse_jsonl_stdout(command_result)
