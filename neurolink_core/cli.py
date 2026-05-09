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
from .tools import observe_activation_health
from .data import CoreDataStore
from .workflow import (
    apply_approval_decision,
    build_app_artifact_admission,
    build_app_build_plan,
    persist_app_deploy_activate_evidence,
    persist_app_deploy_rollback_evidence,
    run_app_deploy_activate,
    run_app_deploy_rollback,
    build_app_deploy_plan,
    run_app_deploy_prepare_verify,
    build_approval_context,
    build_user_prompt_event,
    run_event_daemon_replay,
    run_event_replay,
    run_live_event_service,
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

    event_replay = subparsers.add_parser("event-replay")
    event_replay.add_argument("--db", default=":memory:", help="SQLite database path")
    event_replay.add_argument("--events-file", required=True, help="Path to a JSON event replay fixture")
    event_replay.add_argument("--output", choices=("json",), default="json")
    event_replay.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    event_replay.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    event_replay.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    event_replay.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for replay lookup and candidate commit behavior",
    )
    event_replay.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    event_replay.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    event_replay.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    event_daemon = subparsers.add_parser("event-daemon")
    event_daemon.add_argument("--db", default=":memory:", help="SQLite database path")
    event_daemon.add_argument("--events-file", required=True, help="Path to a JSON daemon replay fixture")
    event_daemon.add_argument("--output", choices=("json",), default="json")
    event_daemon.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    event_daemon.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    event_daemon.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    event_daemon.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for daemon replay lookup and candidate commit behavior",
    )
    event_daemon.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )
    event_daemon.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )
    event_daemon.add_argument(
        "--require-real-tool-adapter",
        action="store_true",
        help="Require the Neuro CLI adapter in release-gate evidence; fails closed with the fake adapter",
    )

    live_event_smoke = subparsers.add_parser("live-event-smoke")
    live_event_smoke.add_argument("--db", default=":memory:", help="SQLite database path")
    live_event_smoke.add_argument(
        "--event-source",
        choices=("app", "unit"),
        default="app",
        help="Subscribe to app callback events or unit-wide operational events",
    )
    live_event_smoke.add_argument("--app-id", default="", help="Target app identifier for app-scoped live callback subscriptions")
    live_event_smoke.add_argument("--duration", type=int, default=5, help="Subscription duration in seconds")
    live_event_smoke.add_argument("--max-events", type=int, default=1, help="Stop after this many events if non-zero")
    live_event_smoke.add_argument("--ready-file", default="", help="Optional file path written once the live event subscription is ready")
    live_event_smoke.add_argument("--output", choices=("json",), default="json")
    live_event_smoke.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    live_event_smoke.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    live_event_smoke.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    live_event_smoke.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for live-ingest lookup and candidate commit behavior",
    )
    live_event_smoke.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )

    event_service = subparsers.add_parser("event-service")
    event_service.add_argument("--db", default=":memory:", help="SQLite database path")
    event_service.add_argument(
        "--event-source",
        choices=("app", "unit"),
        default="app",
        help="Subscribe to app callback events or unit-wide operational events",
    )
    event_service.add_argument("--app-id", default="", help="Target app identifier for app-scoped live callback subscriptions")
    event_service.add_argument("--duration", type=int, default=5, help="Subscription duration in seconds")
    event_service.add_argument("--max-events", type=int, default=1, help="Stop after this many events if non-zero")
    event_service.add_argument("--cycles", type=int, default=1, help="Run this many bounded service supervision cycles")
    event_service.add_argument("--ready-file", default="", help="Optional file path written once the live event subscription is ready")
    event_service.add_argument("--output", choices=("json",), default="json")
    event_service.add_argument(
        "--session-id",
        default=None,
        help="Optional session identifier to continue a prior local Core session",
    )
    event_service.add_argument(
        "--maf-provider-mode",
        choices=(
            MafProviderMode.DETERMINISTIC_FAKE.value,
            MafProviderMode.PROVIDER_AVAILABLE_NO_CALL.value,
            MafProviderMode.REAL_PROVIDER.value,
        ),
        default=MafProviderMode.DETERMINISTIC_FAKE.value,
        help="Select deterministic fake, provider-availability-only, or guarded real-provider runtime behavior",
    )
    event_service.add_argument(
        "--allow-model-call",
        action="store_true",
        help="Required together with --maf-provider-mode real_provider to allow an actual MAF model call",
    )
    event_service.add_argument(
        "--memory-backend",
        choices=("fake", "local", "mem0"),
        default="fake",
        help="Select the long-term memory backend for live event service lookup and candidate commit behavior",
    )
    event_service.add_argument(
        "--rational-backend",
        choices=("auto", "deterministic", "provider", "copilot"),
        default="auto",
        help="Select the Rational planning backend; copilot requires --allow-model-call",
    )

    activation_health = subparsers.add_parser("activation-health-guard")
    activation_health.add_argument("--db", default=":memory:", help="SQLite database path")
    activation_health.add_argument("--app-id", required=True, help="Activated app identifier to observe")
    activation_health.add_argument("--output", choices=("json",), default="json")
    activation_health.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation used for read-only health observation",
    )

    app_build_plan = subparsers.add_parser("app-build-plan")
    app_build_plan.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_build_plan.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the build plan",
    )
    app_build_plan.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_build_plan.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_build_plan.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_build_plan.add_argument("--output", choices=("json",), default="json")
    app_build_plan.add_argument(
        "--check-c-style",
        action="store_true",
        help="Record a build plan that keeps the C style gate enabled",
    )

    app_artifact_admission = subparsers.add_parser("app-artifact-admission")
    app_artifact_admission.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_artifact_admission.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the admission check",
    )
    app_artifact_admission.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_artifact_admission.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_artifact_admission.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_artifact_admission.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to admit; defaults to the canonical source artifact path",
    )
    app_artifact_admission.add_argument("--output", choices=("json",), default="json")

    app_deploy_plan = subparsers.add_parser("app-deploy-plan")
    app_deploy_plan.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_deploy_plan.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the deploy plan",
    )
    app_deploy_plan.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_deploy_plan.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_deploy_plan.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_deploy_plan.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to deploy; defaults to the admitted source artifact path",
    )
    app_deploy_plan.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_plan.add_argument(
        "--source-agent",
        default="rational",
        help="Deploy-plan source_agent metadata for lease and deploy commands",
    )
    app_deploy_plan.add_argument(
        "--lease-ttl-ms",
        type=int,
        default=120000,
        help="Suggested activate-lease TTL in milliseconds",
    )
    app_deploy_plan.add_argument(
        "--start-args",
        default="",
        help="Optional start-args string to include in the activate plan step",
    )
    app_deploy_plan.add_argument("--output", choices=("json",), default="json")

    app_deploy_prepare_verify = subparsers.add_parser("app-deploy-prepare-verify")
    app_deploy_prepare_verify.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_deploy_prepare_verify.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the prepare/verify execution slice",
    )
    app_deploy_prepare_verify.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_deploy_prepare_verify.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_deploy_prepare_verify.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_deploy_prepare_verify.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to deploy; defaults to the admitted source artifact path",
    )
    app_deploy_prepare_verify.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_prepare_verify.add_argument(
        "--source-agent",
        default="rational",
        help="Execution source_agent metadata for lease and deploy commands",
    )
    app_deploy_prepare_verify.add_argument(
        "--lease-ttl-ms",
        type=int,
        default=120000,
        help="Activate-lease TTL in milliseconds",
    )
    app_deploy_prepare_verify.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Command timeout in seconds for preflight and Neuro CLI calls",
    )
    app_deploy_prepare_verify.add_argument("--output", choices=("json",), default="json")

    app_deploy_activate = subparsers.add_parser("app-deploy-activate")
    app_deploy_activate.add_argument(
        "--preset",
        choices=("unit-app", "unit-ext"),
        default="unit-app",
        help="Select the external app build preset",
    )
    app_deploy_activate.add_argument(
        "--app-id",
        default="neuro_unit_app",
        help="Target app identifier for the activation execution slice",
    )
    app_deploy_activate.add_argument(
        "--app-source-dir",
        default="",
        help="Optional workspace-relative app source directory override",
    )
    app_deploy_activate.add_argument(
        "--board",
        default="dnesp32s3b/esp32s3/procpu",
        help="Target board identifier for the Unit host build",
    )
    app_deploy_activate.add_argument(
        "--build-dir",
        default="build/neurolink_unit",
        help="Workspace-relative Unit host build directory",
    )
    app_deploy_activate.add_argument(
        "--artifact-file",
        default="",
        help="Explicit artifact file to deploy; defaults to the admitted source artifact path",
    )
    app_deploy_activate.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_activate.add_argument(
        "--source-agent",
        default="rational",
        help="Execution source_agent metadata for lease and deploy commands",
    )
    app_deploy_activate.add_argument(
        "--lease-ttl-ms",
        type=int,
        default=120000,
        help="Activate-lease TTL in milliseconds",
    )
    app_deploy_activate.add_argument(
        "--start-args",
        default="",
        help="Optional start-args string passed to deploy activate",
    )
    app_deploy_activate.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Command timeout in seconds for preflight and Neuro CLI calls",
    )
    app_deploy_activate.add_argument(
        "--approval-decision",
        choices=("pending", "approve", "deny"),
        default="pending",
        help="Explicit activation approval decision required before activation executes",
    )
    app_deploy_activate.add_argument(
        "--approval-note",
        default="",
        help="Optional operator approval note recorded in the activation decision payload",
    )
    app_deploy_activate.add_argument("--db", default="", help="Optional SQLite database path for persisting activation release-gate evidence")
    app_deploy_activate.add_argument("--output", choices=("json",), default="json")

    app_deploy_rollback = subparsers.add_parser("app-deploy-rollback")
    app_deploy_rollback.add_argument(
        "--app-id",
        required=True,
        help="Target app identifier for the rollback execution slice",
    )
    app_deploy_rollback.add_argument(
        "--node",
        default="unit-01",
        help="Target Unit node identifier",
    )
    app_deploy_rollback.add_argument(
        "--source-agent",
        default="rational",
        help="Execution source_agent metadata for rollback commands",
    )
    app_deploy_rollback.add_argument(
        "--lease-id",
        default="",
        help="Optional explicit rollback lease id; defaults to adapter lease resolution",
    )
    app_deploy_rollback.add_argument(
        "--reason",
        default="guarded_rollback_after_activation_health_failure",
        help="Rollback reason recorded in the resumed rollback request",
    )
    app_deploy_rollback.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Command timeout in seconds for Neuro CLI calls",
    )
    app_deploy_rollback.add_argument(
        "--approval-decision",
        choices=("pending", "approve", "deny", "expire"),
        default="pending",
        help="Explicit rollback approval decision required before rollback executes",
    )
    app_deploy_rollback.add_argument(
        "--approval-note",
        default="",
        help="Optional operator approval note recorded in the rollback decision payload",
    )
    app_deploy_rollback.add_argument("--db", default="", help="Optional SQLite database path for persisting rollback release-gate evidence")
    app_deploy_rollback.add_argument("--output", choices=("json",), default="json")

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

    def load_event_replay_fixture(events_file: str) -> list[dict[str, Any]]:
        payload = json.loads(Path(events_file).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
            events = cast(list[dict[str, Any]], payload["events"])
        else:
            raise ValueError("event_replay_fixture_must_be_list_or_object_with_events")
        normalized_events: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("event_replay_fixture_contains_non_object_event")
            normalized_events.append(dict(event))
        return normalized_events

    def load_event_daemon_fixture(events_file: str) -> list[list[dict[str, Any]]]:
        payload = json.loads(Path(events_file).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            if not payload:
                return []
            if all(isinstance(item, dict) for item in payload):
                return [cast(list[dict[str, Any]], [dict(item) for item in payload])]
            if all(isinstance(item, list) for item in payload):
                batches = cast(list[list[Any]], payload)
            else:
                raise ValueError("event_daemon_fixture_must_be_event_list_or_batch_list")
        elif isinstance(payload, dict) and isinstance(payload.get("batches"), list):
            batches = cast(list[list[Any]], payload["batches"])
        else:
            raise ValueError("event_daemon_fixture_must_be_event_list_or_object_with_batches")
        normalized_batches: list[list[dict[str, Any]]] = []
        for batch in batches:
            if not isinstance(batch, list):
                raise ValueError("event_daemon_fixture_contains_non_list_batch")
            normalized_batch: list[dict[str, Any]] = []
            for event in batch:
                if not isinstance(event, dict):
                    raise ValueError("event_daemon_fixture_contains_non_object_event")
                normalized_batch.append(dict(event))
            normalized_batches.append(normalized_batch)
        return normalized_batches

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
                event_source_label=(
                    "neuro_cli_agent_events"
                    if args.event_source == "neuro-cli-agent-events"
                    else None
                ),
            )
        except (MafProviderNotReadyError, ValueError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "event-replay":
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
        try:
            events = load_event_replay_fixture(args.events_file)
            payload = run_event_replay(
                events,
                args.db,
                tool_adapter=tool_adapter,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
                replay_label=str(args.events_file),
            )
        except (MafProviderNotReadyError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "event-daemon":
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
        try:
            event_batches = load_event_daemon_fixture(args.events_file)
            payload = run_event_daemon_replay(
                event_batches,
                args.db,
                tool_adapter=tool_adapter,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=args.require_real_tool_adapter,
                replay_label=str(args.events_file),
            )
        except (MafProviderNotReadyError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "live-event-smoke":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = NeuroCliToolAdapter()
        try:
            if args.event_source == "app":
                if not args.app_id:
                    raise ValueError("live_event_smoke_requires_app_id")
                live_event_payload = tool_adapter.collect_app_events(
                    args.app_id,
                    duration=args.duration,
                    max_events=args.max_events,
                    ready_file=args.ready_file,
                )
                event_source_label = "neuro_cli_app_events_live"
                live_event_ingest = {
                    "schema_version": "1.2.3-live-event-ingest-v1",
                    "event_source_kind": "app",
                    "monitor_command": "app-events",
                    "app_id": args.app_id,
                    "duration": args.duration,
                    "max_events": args.max_events,
                    "subscription": live_event_payload.get("subscription"),
                    "listener_mode": live_event_payload.get("listener_mode"),
                    "handler_audit": live_event_payload.get("handler_audit"),
                }
            else:
                live_event_payload = tool_adapter.collect_live_events(
                    duration=args.duration,
                    max_events=args.max_events,
                    ready_file=args.ready_file,
                )
                event_source_label = "neuro_cli_events_live"
                live_event_ingest = {
                    "schema_version": "1.2.3-live-event-ingest-v1",
                    "event_source_kind": "unit",
                    "monitor_command": "events",
                    "duration": args.duration,
                    "max_events": args.max_events,
                    "subscription": live_event_payload.get("subscription"),
                    "listener_mode": live_event_payload.get("listener_mode"),
                    "handler_audit": live_event_payload.get("handler_audit"),
                }
            events = [
                dict(event)
                for event in cast(list[Any], live_event_payload.get("events") or [])
                if isinstance(event, dict)
            ]
            if not events:
                print(
                    json.dumps(
                        {
                            "ok": False,
                            "status": "live_event_ingest_empty",
                            "command": "live-event-smoke",
                            "failure_class": "live_event_monitor_empty",
                            "failure_status": "no_events_collected",
                            "event_source": event_source_label,
                            "tool_adapter_runtime": tool_adapter.runtime_metadata(),
                            "live_event_ingest": {
                                **live_event_ingest,
                                "collected_event_count": 0,
                            },
                        },
                        sort_keys=True,
                    )
                )
                return 2
            payload = run_no_model_dry_run(
                args.db,
                tool_adapter=tool_adapter,
                events=events,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                require_real_tool_adapter=True,
                event_source_label=event_source_label,
            )
        except (MafProviderNotReadyError, ValueError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        payload["command"] = "live-event-smoke"
        payload["live_event_ingest"] = {
            **live_event_ingest,
            "collected_event_count": len(events),
        }
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "event-service":
        if args.db != ":memory:":
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
        tool_adapter = NeuroCliToolAdapter()
        try:
            payload = run_live_event_service(
                args.db,
                event_source=args.event_source,
                app_id=args.app_id,
                duration=args.duration,
                max_events=args.max_events,
                cycles=args.cycles,
                ready_file=args.ready_file,
                session_id=args.session_id,
                maf_provider_mode=args.maf_provider_mode,
                allow_model_call=args.allow_model_call,
                memory_backend=args.memory_backend,
                rational_backend=args.rational_backend,
                tool_adapter=tool_adapter,
            )
        except (MafProviderNotReadyError, ValueError) as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok", False) else 2
    if args.command == "activation-health-guard":
        tool_adapter = (
            NeuroCliToolAdapter()
            if args.tool_adapter == "neuro-cli"
            else FakeUnitToolAdapter()
        )
        try:
            observation = observe_activation_health(
                tool_adapter,
                app_id=args.app_id,
            )
            payload = {
                "ok": True,
                "status": "ok",
                "command": "activation-health-guard",
                "health_observation": observation.to_dict(),
                "tool_adapter_runtime": tool_adapter.runtime_metadata(),
            }
        except ValueError as exc:
            print(json.dumps(provider_error_payload(args.command, exc), sort_keys=True))
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-build-plan":
        try:
            payload = build_app_build_plan(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                check_c_style=args.check_c_style,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_build_plan_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-artifact-admission":
        try:
            payload = build_app_artifact_admission(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
            )
        except ValueError as exc:
            failure_status = str(exc)
            failure_class = (
                "app_artifact_admission_failed"
                if failure_status.startswith("artifact_") or failure_status.startswith("source_")
                else "app_artifact_admission_invalid"
            )
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": failure_class,
                        "failure_status": failure_status,
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-deploy-plan":
        try:
            payload = build_app_deploy_plan(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_ttl_ms=args.lease_ttl_ms,
                start_args=args.start_args or None,
            )
        except ValueError as exc:
            failure_status = str(exc)
            failure_class = (
                "app_deploy_plan_failed"
                if failure_status.startswith("artifact_") or failure_status.startswith("source_")
                else "app_deploy_plan_invalid"
            )
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": failure_class,
                        "failure_status": failure_status,
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0
    if args.command == "app-deploy-prepare-verify":
        try:
            tool_adapter = NeuroCliToolAdapter(
                node=args.node,
                source_agent=args.source_agent,
                timeout_seconds=args.timeout_seconds,
            )
            payload = run_app_deploy_prepare_verify(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_ttl_ms=args.lease_ttl_ms,
                timeout_seconds=args.timeout_seconds,
                tool_adapter=tool_adapter,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_deploy_prepare_verify_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok") else 2
    if args.command == "app-deploy-activate":
        try:
            if args.db:
                Path(args.db).parent.mkdir(parents=True, exist_ok=True)
            tool_adapter = NeuroCliToolAdapter(
                node=args.node,
                source_agent=args.source_agent,
                timeout_seconds=args.timeout_seconds,
            )
            payload = run_app_deploy_activate(
                preset=args.preset,
                app_id=args.app_id,
                app_source_dir=args.app_source_dir or None,
                board=args.board,
                build_dir=args.build_dir,
                artifact_file=args.artifact_file or None,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_ttl_ms=args.lease_ttl_ms,
                start_args=args.start_args or None,
                timeout_seconds=args.timeout_seconds,
                activation_approval_decision=args.approval_decision,
                activation_approval_note=args.approval_note,
                tool_adapter=tool_adapter,
            )
            if args.db:
                payload["release_gate_evidence"] = persist_app_deploy_activate_evidence(
                    args.db,
                    payload,
                )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_deploy_activate_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok") else 2
    if args.command == "app-deploy-rollback":
        try:
            if args.db:
                Path(args.db).parent.mkdir(parents=True, exist_ok=True)
            tool_adapter = NeuroCliToolAdapter(
                node=args.node,
                source_agent=args.source_agent,
                timeout_seconds=args.timeout_seconds,
            )
            payload = run_app_deploy_rollback(
                app_id=args.app_id,
                node_id=args.node,
                source_agent=args.source_agent,
                lease_id=args.lease_id or None,
                rollback_reason=args.reason,
                timeout_seconds=args.timeout_seconds,
                rollback_approval_decision=args.approval_decision,
                rollback_approval_note=args.approval_note,
                tool_adapter=tool_adapter,
            )
            if args.db:
                payload["release_gate_evidence"] = persist_app_deploy_rollback_evidence(
                    args.db,
                    payload,
                )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": "error",
                        "command": args.command,
                        "failure_class": "app_deploy_rollback_invalid",
                        "failure_status": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload.get("ok") else 2
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
                event_source_label=(
                    "neuro_cli_agent_events"
                    if args.event_source == "neuro-cli-agent-events"
                    else None
                ),
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
