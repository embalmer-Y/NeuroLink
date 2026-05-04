from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from .maf import maf_provider_smoke_status
from .tools import FakeUnitToolAdapter, NeuroCliToolAdapter
from .workflow import run_no_model_dry_run


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
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for delegated tool execution",
    )

    tool_manifest = subparsers.add_parser("tool-manifest")
    tool_manifest.add_argument("--output", choices=("json",), default="json")
    tool_manifest.add_argument(
        "--tool-adapter",
        choices=("fake", "neuro-cli"),
        default="fake",
        help="Select the tool adapter implementation for manifest discovery",
    )

    maf_smoke = subparsers.add_parser("maf-provider-smoke")
    maf_smoke.add_argument("--output", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "no-model-dry-run":
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
        payload = run_no_model_dry_run(
            args.db,
            use_db_events=args.use_db_events,
            query_limit=args.query_limit,
            min_priority=args.min_priority,
            topic=args.topic,
            tool_adapter=tool_adapter,
            events=events,
        )
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
    if args.command == "maf-provider-smoke":
        print(json.dumps(maf_provider_smoke_status(), sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
