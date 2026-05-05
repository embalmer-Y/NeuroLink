from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from .maf import (
    MafProviderMode,
    MafProviderNotReadyError,
    build_maf_runtime_profile,
    maf_provider_smoke_status,
)
from .session import CoreSessionManager
from .tools import FakeUnitToolAdapter, NeuroCliToolAdapter
from .data import CoreDataStore
from .workflow import (
    apply_approval_decision,
    build_approval_context,
    build_user_prompt_event,
    run_no_model_dry_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="neurolink-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("no-model-dry-run")
    dry_run.add_argument("--db", default=":memory:", help="SQLite database path")
    dry_run.add_argument("--output", choices=("json",), default="json")
    dry_run.add_argument("--use-db-events", action="store_true", help="Rebuild the reasoning frame from persisted events")
    dry_run.add_argument("--query-limit", type=int, default=100, help="Maximum persisted events to query when --use-db-events is set")
    dry_run.add_argument("--min-priority", type=int, default=0, help="Minimum persisted event priority to include when --use-db-events is set")
    dry_run.add_argument("--topic", default=None, help="Optional semantic topic filter when --use-db-events is set")
    dry_run.add_argument(
        "--event-source",
        choices=("sample", "neuro-cli-agent-events"),
        default="sample",
        help="Select perception event source for the dry run",
    )
    dry_run.add_argument("--max-events", type=int, default=0, help="Maximum agent-events rows to ingest when using neuro-cli-agent-events")
    dry_run.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    dry_run.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    dry_run.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    dry_run.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for dry-run lookup and candidate commit behavior",
    )
    dry_run.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    dry_run.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    dry_run.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    agent_run = subparsers.add_parser("agent-run")
    agent_run.add_argument("--db", default=":memory:", help="SQLite database path")
    agent_run.add_argument("--output", choices=("json",), default="json")
    agent_run.add_argument("--input-text", default=None, help="Optional user input text to synthesize into a perception event")
    agent_run.add_argument(
        "--event-source",
        choices=("sample", "neuro-cli-agent-events"),
        default="sample",
        help="Select perception event source when --input-text is not provided",
    )
    agent_run.add_argument("--max-events", type=int, default=0, help="Maximum agent-events rows to ingest when using neuro-cli-agent-events")
    agent_run.add_argument("--session-id", default=None, help="Optional session identifier to continue a prior local Core session")
    agent_run.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    agent_run.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    agent_run.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for agent-run lookup and candidate commit behavior",
    )
    agent_run.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    agent_run.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    agent_run.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    tool_manifest = subparsers.add_parser("tool-manifest")
    tool_manifest.add_argument("--output", choices=("json",), default="json")
    tool_manifest.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for manifest discovery",
    )

    session_inspect = subparsers.add_parser("session-inspect")
    session_inspect.add_argument("--db", default=":memory:", help="SQLite database path")
    session_inspect.add_argument("--session-id", required=True, help="Session identifier to inspect")
    session_inspect.add_argument("--output", choices=("json",), default="json")

    approval_inspect = subparsers.add_parser("approval-inspect")
    approval_inspect.add_argument("--db", default=":memory:", help="SQLite database path")
    approval_inspect.add_argument("--approval-request-id", required=True, help="Approval request identifier to inspect")
    approval_inspect.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for live lease/state operator evidence",
    )
    approval_inspect.add_argument("--output", choices=("json",), default="json")

    approval_decision = subparsers.add_parser("approval-decision")
    approval_decision.add_argument("--db", default=":memory:", help="SQLite database path")
    approval_decision.add_argument("--approval-request-id", required=True, help="Approval request identifier to resolve")
    approval_decision.add_argument("--decision", choices=("approve", "deny", "expire"), required=True, help="Decision to apply to the pending approval request")
    approval_decision.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for resumed execution when approving a request",
    )
    approval_decision.add_argument("--output", choices=("json",), default="json")

    maf_smoke = subparsers.add_parser("maf-provider-smoke")
    maf_smoke.add_argument("--output", choices=("json",), default="json")
    maf_smoke.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Opt in to a future real-provider smoke call when package and model configuration are available",
    )
    maf_smoke.add_argument(
        "--execute-model-call",
        action="store_true",
        help="Actually execute the provider smoke model call; requires --allow-model-call",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    def provider_error_payload(command: str, exc: Exception) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "error",
            "command": command,
            "failure_class": (
                "maf_provider_not_ready"
                if isinstance(exc, MafProviderNotReadyError)
                else "maf_provider_request_invalid"
            ),
            "failure_status": str(exc),
            "maf_runtime": build_maf_runtime_profile(
                provider_mode=getattr(args, "maf_provider_mode", MafProviderMode.DETERMINISTIC_FAKE.value)
            ).to_dict(),
        }

    if args.command == "no-model-dry-run":
        if args.require_real_tool_adapter and args.tool_adapter != "neuro-cli":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_gate_request_invalid",
                        "failure_status": "require_real_tool_adapter_requires_neuro_cli_adapter",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        events: list[dict[str, Any]] | None = None
        if args.event_source == "neuro-cli-agent-events":
            event_adapter = (
                cast(NeuroCliToolAdapter, tool_adapter)
                if args.tool_adapter == "neuro-cli"
                else NeuroCliToolAdapter()
            )
            events = event_adapter.collect_agent_events(max_events=args.max_events)
        try:
            payload = run_no_model_dry_run(
                args.db,
                use_db_events=args.use_db_events,
                query_limit=args.query_limit,
                min_priority=args.min_priority,
                topic=args.topic,
                tool_adapter=tool_adapter,
                events=events,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "agent-run":
        if args.require_real_tool_adapter and args.tool_adapter != "neuro-cli":
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "release_gate_request_invalid",
                        "failure_status": "require_real_tool_adapter_requires_neuro_cli_adapter",
                    },
                    sort_keys=True,
                )
            )
            return 2
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        events: list[dict[str, Any]] | None = None
        if args.input_text:
            events = build_user_prompt_event(args.input_text)
        elif args.event_source == "neuro-cli-agent-events":
            event_adapter = (
                cast(NeuroCliToolAdapter, tool_adapter)
                if args.tool_adapter == "neuro-cli"
                else NeuroCliToolAdapter()
            )
            events = event_adapter.collect_agent_events(max_events=args.max_events)
        try:
            payload = run_no_model_dry_run(
                args.db,
                tool_adapter=tool_adapter,
                events=events,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        payload["command"] = "agent-run"
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "tool-manifest":
        if args.tool_adapter == "neuro-cli":
            adapter = NeuroCliToolAdapter()
            payload = adapter.tool_manifest_payload()
        else:
            adapter = FakeUnitToolAdapter()
            payload = adapter.tool_manifest_payload()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "session-inspect":
        data_store = CoreDataStore(args.db)
        try:
            manager = CoreSessionManager(data_store)
            payload = manager.load_snapshot(args.session_id, limit=10).to_dict()
        finally:
            data_store.close()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "approval-inspect":
        data_store = CoreDataStore(args.db)
        try:
            tool_adapter = (
                NeuroCliToolAdapter()
                if args.tool_adapter == "neuro-cli"
                else FakeUnitToolAdapter()
            )
            approval_request = data_store.get_approval_request(args.approval_request_id)
            if approval_request is None:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "status": "error",
                            "failure_class": "approval_request_not_found",
                            "failure_status": "approval_request_not_found",
                        },
                        sort_keys=True,
                    )
                )
                return 2
            payload: dict[str, Any] = {
                "ok": True,
                "status": "ok",
                "approval_request": approval_request,
                "approval_decisions": data_store.get_approval_decisions(
                    args.approval_request_id
                ),
                "approval_context": build_approval_context(
                    data_store,
                    approval_request,
                    tool_adapter=tool_adapter,
                ),
            }
        finally:
            data_store.close()
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "approval-decision":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        try:
            payload = apply_approval_decision(
                args.db,
                approval_request_id=args.approval_request_id,
                decision=args.decision,
                tool_adapter=tool_adapter,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "failure_class": "approval_request_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "maf-provider-smoke":
        payload = maf_provider_smoke_status(
            allow_model_call=args.allow_model_call,
            execute_model_call=args.execute_model_call,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
