from __future__ import annotations

from dataclasses import dataclass, field
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .common import new_id
from .policy import SideEffectLevel


TOOL_MANIFEST_SCHEMA_VERSION = "1.2.0-tool-manifest-v1"
STATE_SYNC_SCHEMA_VERSION = "1.2.0-state-sync-v1"


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
    output_contract: dict[str, Any] = field(default_factory=dict)

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
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=tool_name,
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "mode": "fake_no_model",
                "side_effect_level": "read_only",
                "event_ids": list(args.get("event_ids") or []),
                "state_sync": self.build_state_sync_snapshot(args).to_dict(),
            },
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
            payload = json.loads(command_result.stdout)
        except json.JSONDecodeError as exc:
            if command_result.exit_code != 0:
                raise ValueError(f"command_exit_{command_result.exit_code}") from exc
            raise ValueError("parse_failed") from exc
        if not isinstance(payload, dict):
            raise ValueError("parse_failed")
        return payload

    @staticmethod
    def _parse_jsonl_stdout(command_result: CommandExecutionResult) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in command_result.stdout.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("parse_failed")
            rows.append(payload)
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

        if tool_name != "system_state_sync":
            return ToolExecutionResult(
                tool_result_id=new_id("tool"),
                tool_name=tool_name,
                status="error",
                payload={
                    "failure_status": "unsupported_tool",
                    "failure_class": "adapter_contract_missing",
                },
            )

        argv = [*self._base_command(), "system", "state-sync"]
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

        snapshot = StateSyncSnapshot.from_dict(payload)
        return ToolExecutionResult(
            tool_result_id=new_id("tool"),
            tool_name=tool_name,
            status="ok",
            payload={
                "contract": contract.to_dict(),
                "state_sync": snapshot.to_dict(),
            },
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
