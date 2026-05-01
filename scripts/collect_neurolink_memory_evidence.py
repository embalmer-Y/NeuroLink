#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast


JsonObject = dict[str, Any]


CONFIG_KEYS = [
    "CONFIG_BOARD",
    "CONFIG_BOARD_TARGET",
    "CONFIG_BOARD_QUALIFIERS",
    "CONFIG_SOC",
    "CONFIG_SOC_SERIES_ESP32S3",
    "CONFIG_HEAP_MEM_POOL_SIZE",
    "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE",
    "CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER",
    "CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER",
    "CONFIG_MAIN_STACK_SIZE",
    "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE",
    "CONFIG_SHELL_STACK_SIZE",
    "CONFIG_NET_PKT_RX_COUNT",
    "CONFIG_NET_PKT_TX_COUNT",
    "CONFIG_NET_BUF_RX_COUNT",
    "CONFIG_NET_BUF_TX_COUNT",
    "CONFIG_ESP_SPIRAM",
    "CONFIG_ESP_SPIRAM_HEAP_SIZE",
    "CONFIG_ESP_WIFI_HEAP_SPIRAM",
    "CONFIG_ESP32_WIFI_NET_ALLOC_SPIRAM",
    "CONFIG_SHARED_MULTI_HEAP",
    "CONFIG_LLEXT_HEAP_DYNAMIC",
    "CONFIG_LLEXT_HEAP_SIZE",
    "CONFIG_LLEXT_LOG_LEVEL_DBG",
    "CONFIG_NEUROLINK_ZENOH_PICO_DEBUG",
    "CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL",
    "CONFIG_SYS_HEAP_RUNTIME_STATS",
    "CONFIG_ZENOH_PICO_MULTI_THREAD",
]

SECTION_PREFIXES = {
    "dram0": ".dram0",
    "iram0": ".iram0",
    "flash": ".flash",
    "ext_ram": ".ext_ram",
}

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def neurolink_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_config(config_path: Path) -> JsonObject:
    values: JsonObject = {}
    if not config_path.is_file():
        return values

    wanted = set(CONFIG_KEYS)
    unset_pattern = re.compile(r"^# (CONFIG_[A-Za-z0-9_]+) is not set$")
    set_pattern = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=(.*)$")

    for line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
        unset_match = unset_pattern.match(line)
        if unset_match and unset_match.group(1) in wanted:
            values[unset_match.group(1)] = "n"
            continue

        set_match = set_pattern.match(line)
        if not set_match or set_match.group(1) not in wanted:
            continue

        raw_value = set_match.group(2).strip()
        if raw_value == "y":
            values[set_match.group(1)] = "y"
        elif raw_value == "n":
            values[set_match.group(1)] = "n"
        elif raw_value.isdigit():
            values[set_match.group(1)] = int(raw_value)
        else:
            values[set_match.group(1)] = raw_value.strip('"')

    return values


def display_path(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    return str(path.relative_to(root)) if path.is_relative_to(root) else str(path)


def clean_log_line(line: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", line)


def parse_release_target(cli_path: Path) -> str | None:
    if not cli_path.is_file():
        return None

    pattern = re.compile(r'^RELEASE_TARGET\s*=\s*["\']([^"\']+)["\']')
    for line in cli_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1)
    return None


def parse_build_info(build_info_path: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    if not build_info_path.is_file():
        return info

    text = build_info_path.read_text(encoding="utf-8", errors="replace")
    for key, pattern in {
        "board": r"\n\s+name:\s+'?([^'\n]+)'?",
        "board_qualifiers": r"\n\s+qualifiers:\s+'?([^'\n]*)'?",
        "west_command": r"\n\s+command:\s+'?([^'\n]+)'?",
        "zephyr_version": r"\n\s+version:\s+'?([^'\n]+)'?",
    }.items():
        match = re.search(pattern, text)
        if match:
            info[key] = match.group(1)
    return info


def infer_platform(config: Mapping[str, Any], build_info: Mapping[str, str]) -> JsonObject:
    return {
        "board": config.get("CONFIG_BOARD") or build_info.get("board"),
        "board_target": config.get("CONFIG_BOARD_TARGET"),
        "board_qualifiers": config.get("CONFIG_BOARD_QUALIFIERS")
        or build_info.get("board_qualifiers"),
        "soc": config.get("CONFIG_SOC"),
    }


def infer_memory_capability(
    config: Mapping[str, Any], memory_provider: str | None
) -> JsonObject:
    esp_spiram_enabled = config.get("CONFIG_ESP_SPIRAM") == "y"
    shared_multi_heap_enabled = config.get("CONFIG_SHARED_MULTI_HEAP") == "y"
    external_heap_size = config.get("CONFIG_ESP_SPIRAM_HEAP_SIZE")
    external_heap_size_bytes = external_heap_size if isinstance(external_heap_size, int) else 0

    if memory_provider:
        provider = memory_provider
    elif esp_spiram_enabled:
        provider = "esp-spiram"
    elif shared_multi_heap_enabled:
        provider = "zephyr-shared-multi-heap"
    else:
        provider = "none"

    prefer_external_staging = config.get(
        "CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER"
    ) == "y" or config.get("CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER") == "y"
    external_memory_configured = (
        esp_spiram_enabled or shared_multi_heap_enabled or external_heap_size_bytes > 0
    )

    return {
        "provider": provider,
        "external_memory_configured": external_memory_configured,
        "external_heap_size_bytes": external_heap_size_bytes,
        "shared_multi_heap_enabled": shared_multi_heap_enabled,
        "esp_spiram_enabled": esp_spiram_enabled,
        "wifi_heap_external_enabled": config.get("CONFIG_ESP_WIFI_HEAP_SPIRAM") == "y",
        "network_alloc_external_enabled": config.get("CONFIG_ESP32_WIFI_NET_ALLOC_SPIRAM")
        == "y",
        "external_elf_staging_preferred": prefer_external_staging,
        "static_elf_staging_size_bytes": config.get(
            "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE", 0
        ),
        "policy_note": (
            "external staging preferred by config"
            if prefer_external_staging
            else "external staging not preferred; static or malloc fallback remains active"
        ),
    }


def parse_stat_sections(stat_path: Path) -> tuple[list[JsonObject], dict[str, int]]:
    sections: list[JsonObject] = []
    totals = {name: 0 for name in SECTION_PREFIXES}
    if not stat_path.is_file():
        return sections, totals

    section_pattern = re.compile(
        r"^\s*\[\s*(\d+)\]\s+(\S+)\s+\S+\s+"
        r"[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)\s+"
    )
    for line in stat_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = section_pattern.match(line)
        if not match:
            continue
        section_name = match.group(2)
        section_size = int(match.group(3), 16)
        section: JsonObject = {
            "index": int(match.group(1)),
            "name": section_name,
            "size_bytes": section_size,
        }
        sections.append(section)
        for total_name, prefix in SECTION_PREFIXES.items():
            if section_name.startswith(prefix):
                totals[total_name] += section_size
    return sections, totals


def parse_build_log(log_path: Path | None) -> list[JsonObject]:
    if log_path is None or not log_path.is_file():
        return []

    rows: list[JsonObject] = []
    normalized_pattern = re.compile(
        r"^\s*([A-Za-z0-9_. -]+):\s+([0-9]+)\s+B\s+"
        r"\(([0-9.]+)%\)\s+of\s+([0-9]+)\s+B"
    )
    zephyr_table_pattern = re.compile(
        r"^\s*([A-Za-z0-9_. -]+):\s+([0-9]+)\s+B\s+"
        r"([0-9]+)\s+B\s+([0-9.]+)%"
    )
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = normalized_pattern.match(line)
        if match:
            rows.append(
                {
                    "region": match.group(1).strip(),
                    "used_bytes": int(match.group(2)),
                    "used_percent": float(match.group(3)),
                    "capacity_bytes": int(match.group(4)),
                }
            )
            continue

        match = zephyr_table_pattern.match(line)
        if not match:
            continue
        rows.append(
            {
                "region": match.group(1).strip(),
                "used_bytes": int(match.group(2)),
                "used_percent": float(match.group(4)),
                "capacity_bytes": int(match.group(3)),
            }
        )
    return rows


def parse_runtime_heap_snapshots(log_paths: Sequence[Path | None]) -> list[JsonObject]:
    snapshots: list[JsonObject] = []
    pattern = re.compile(
        r"(?:<[^>]+>\s*)?"
        r"(?P<scope>update|app-runtime) heap snapshot "
        r"stage=(?P<stage>\S+)"
        r"(?: path=(?P<path>\S+))? "
        r"free=(?P<free>[0-9]+) "
        r"allocated=(?P<allocated>[0-9]+) "
        r"max_allocated=(?P<max_allocated>[0-9]+)"
    )

    seen: set[tuple[str, str | None, str, int, int, int]] = set()
    for log_path in log_paths:
        if log_path is None or not log_path.is_file():
            continue
        for raw_line in log_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            line = clean_log_line(raw_line)
            match = pattern.search(line)
            if not match:
                continue
            scope = match.group("scope")
            stage = match.group("stage")
            path = match.group("path")
            free_bytes = int(match.group("free"))
            allocated_bytes = int(match.group("allocated"))
            max_allocated_bytes = int(match.group("max_allocated"))
            item: JsonObject = {
                "scope": scope,
                "stage": stage,
                "path": path,
                "free_bytes": free_bytes,
                "allocated_bytes": allocated_bytes,
                "max_allocated_bytes": max_allocated_bytes,
                "source_log": str(log_path),
            }
            dedupe_key = (
                scope,
                path,
                stage,
                free_bytes,
                allocated_bytes,
                max_allocated_bytes,
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            snapshots.append(item)
    return snapshots


def parse_runtime_staging_allocations(log_paths: Sequence[Path | None]) -> list[JsonObject]:
    allocations: list[JsonObject] = []
    pattern = re.compile(
        r"(?:<[^>]+>\s*)?"
        r"app-runtime ELF staging allocation "
        r"path=(?P<path>\S+) "
        r"bytes=(?P<bytes>[0-9]+) "
        r"source=(?P<source>\S+) "
        r"provider=(?P<provider>\S+)"
    )

    seen: set[tuple[str, int, str, str]] = set()
    for log_path in log_paths:
        if log_path is None or not log_path.is_file():
            continue
        for raw_line in log_path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            line = clean_log_line(raw_line)
            match = pattern.search(line)
            if not match:
                continue
            path = match.group("path")
            size_bytes = int(match.group("bytes"))
            source = match.group("source")
            provider = match.group("provider")
            dedupe_key = (path, size_bytes, source, provider)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            allocations.append(
                {
                    "path": path,
                    "size_bytes": size_bytes,
                    "source": source,
                    "provider": provider,
                    "source_log": str(log_path),
                }
            )
    return allocations


def parse_runtime_drop_notices(log_paths: Sequence[Path | None]) -> list[JsonObject]:
    notices: list[JsonObject] = []
    pattern = re.compile(r"---\s*(?P<count>[0-9]+)\s+messages dropped\s*---")

    for log_path in log_paths:
        if log_path is None or not log_path.is_file():
            continue
        for line_no, raw_line in enumerate(
            log_path.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            line = clean_log_line(raw_line)
            match = pattern.search(line)
            if not match:
                continue
            notices.append(
                {
                    "count": int(match.group("count")),
                    "line": line_no,
                    "source_log": str(log_path),
                    "interpretation": "zenoh_runtime_pressure_notice_not_evidence_loss",
                }
            )
    return notices


def parse_runtime_fatal_exceptions(log_paths: Sequence[Path | None]) -> list[JsonObject]:
    fatals: list[JsonObject] = []
    fatal_pattern = re.compile(r"FATAL EXCEPTION")
    cause_pattern = re.compile(r"EXCCAUSE\s+(?P<cause>[0-9]+)\s+\((?P<detail>[^)]+)\)")
    pc_pattern = re.compile(r"PC\s+(?P<pc>0x[0-9A-Fa-f]+)\s+VADDR\s+(?P<vaddr>0x[0-9A-Fa-f]+)")

    for log_path in log_paths:
        if log_path is None or not log_path.is_file():
            continue
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for index, raw_line in enumerate(lines):
            line = clean_log_line(raw_line)
            if not fatal_pattern.search(line):
                continue
            window = [clean_log_line(item) for item in lines[index : index + 8]]
            cause: int | None = None
            cause_detail: str | None = None
            pc: str | None = None
            vaddr: str | None = None

            for item in window:
                cause_match = cause_pattern.search(item)
                if cause_match:
                    cause = int(cause_match.group("cause"))
                    cause_detail = cause_match.group("detail")
                pc_match = pc_pattern.search(item)
                if pc_match:
                    pc = pc_match.group("pc")
                    vaddr = pc_match.group("vaddr")

            fatals.append(
                {
                    "line": index + 1,
                    "source_log": str(log_path),
                    "cause": cause,
                    "cause_detail": cause_detail,
                    "pc": pc,
                    "vaddr": vaddr,
                }
            )
    return fatals


def evaluate_runtime_evidence_gate(
    heap_snapshots: Sequence[Mapping[str, Any]],
    staging_allocations: Sequence[Mapping[str, Any]],
    required: bool,
) -> JsonObject:
    has_update_heap_snapshot = any(
        snapshot.get("scope") == "update" for snapshot in heap_snapshots
    )
    has_app_runtime_heap_snapshot = any(
        snapshot.get("scope") == "app-runtime" for snapshot in heap_snapshots
    )
    has_staging_allocation = len(staging_allocations) > 0
    missing: list[str] = []

    if not has_update_heap_snapshot:
        missing.append("update_heap_snapshot")
    if not has_app_runtime_heap_snapshot:
        missing.append("app_runtime_heap_snapshot")
    if not has_staging_allocation:
        missing.append("staging_allocation")

    return {
        "required": required,
        "passed": len(missing) == 0,
        "missing": missing,
        "has_update_heap_snapshot": has_update_heap_snapshot,
        "has_app_runtime_heap_snapshot": has_app_runtime_heap_snapshot,
        "has_staging_allocation": has_staging_allocation,
    }


def runtime_gate_missing_values(runtime_gate: Mapping[str, Any]) -> list[str]:
    missing = runtime_gate.get("missing", [])

    if not isinstance(missing, list):
        return [str(missing)]

    return [str(item) for item in cast(Sequence[object], missing)]


def evaluate_external_staging_candidate_gate(
    memory_capability: Mapping[str, Any],
    staging_allocations: Sequence[Mapping[str, Any]],
    required: bool,
) -> JsonObject:
    external_memory_configured = bool(
        memory_capability.get("external_memory_configured")
    )
    external_staging_preferred = bool(
        memory_capability.get("external_elf_staging_preferred")
    )
    external_allocations = [
        row for row in staging_allocations if row.get("source") == "external"
    ]
    has_external_staging_allocation = len(external_allocations) > 0
    providers = sorted(
        {
            str(row.get("provider", "missing"))
            for row in external_allocations
            if row.get("provider") is not None
        }
    )
    missing: list[str] = []

    if not external_memory_configured:
        missing.append("external_memory_configured")
    if not external_staging_preferred:
        missing.append("external_staging_preference")
    if not has_external_staging_allocation:
        missing.append("external_staging_allocation")

    return {
        "required": required,
        "passed": len(missing) == 0,
        "missing": missing,
        "external_memory_configured": external_memory_configured,
        "external_staging_preferred": external_staging_preferred,
        "has_external_staging_allocation": has_external_staging_allocation,
        "providers": providers,
    }


def write_summary(summary_path: Path, evidence: Mapping[str, Any]) -> None:
    config = cast(Mapping[str, Any], evidence.get("config", {}))
    platform = cast(Mapping[str, Any], evidence.get("platform", {}))
    memory_capability = cast(
        Mapping[str, Any], evidence.get("memory_capability", {})
    )
    totals = cast(Mapping[str, int], evidence.get("section_totals", {}))
    build_rows = cast(Sequence[Mapping[str, Any]], evidence.get("build_memory_summary", []))
    runtime_snapshots = cast(
        Sequence[Mapping[str, Any]], evidence.get("runtime_heap_snapshots", [])
    )
    staging_allocations = cast(
        Sequence[Mapping[str, Any]], evidence.get("runtime_staging_allocations", [])
    )
    drop_notices = cast(
        Sequence[Mapping[str, Any]], evidence.get("runtime_drop_notices", [])
    )
    fatal_exceptions = cast(
        Sequence[Mapping[str, Any]], evidence.get("runtime_fatal_exceptions", [])
    )
    runtime_gate = cast(Mapping[str, Any], evidence.get("runtime_evidence_gate", {}))
    external_staging_gate = cast(
        Mapping[str, Any], evidence.get("external_staging_candidate_gate", {})
    )

    lines = [
        f"label={evidence.get('label')}",
        f"release_target={evidence.get('release_target')}",
        f"build_dir={evidence.get('build_dir')}",
        "",
        "[platform]",
        f"board={platform.get('board', 'missing')}",
        f"board_target={platform.get('board_target', 'missing')}",
        f"board_qualifiers={platform.get('board_qualifiers', 'missing')}",
        f"soc={platform.get('soc', 'missing')}",
        "",
        "[memory_capability]",
        f"provider={memory_capability.get('provider', 'missing')}",
        "external_memory_configured="
        f"{memory_capability.get('external_memory_configured', 'missing')}",
        "external_heap_size_bytes="
        f"{memory_capability.get('external_heap_size_bytes', 'missing')}",
        "external_elf_staging_preferred="
        f"{memory_capability.get('external_elf_staging_preferred', 'missing')}",
        "static_elf_staging_size_bytes="
        f"{memory_capability.get('static_elf_staging_size_bytes', 'missing')}",
        "",
        "[config]",
    ]
    for key in CONFIG_KEYS:
        lines.append(f"{key}={config.get(key, 'missing')}")

    lines.extend(["", "[section_totals_bytes]"])
    for key in sorted(totals):
        lines.append(f"{key}={totals[key]}")

    lines.extend(["", "[build_memory_summary]"])
    if build_rows:
        for row in build_rows:
            lines.append(
                f"{row['region']}={row['used_bytes']}B/"
                f"{row['capacity_bytes']}B ({row['used_percent']:.2f}%)"
            )
    else:
        lines.append("not_available=provide --build-log or collect with --run-build")

    lines.extend(["", "[runtime_heap_snapshots]"])
    if runtime_snapshots:
        for row in runtime_snapshots:
            path = row.get("path") or "-"
            lines.append(
                f"{row['scope']}:{row['stage']}:path={path}:"
                f"free={row['free_bytes']}:allocated={row['allocated_bytes']}:"
                f"max_allocated={row['max_allocated_bytes']}"
            )
    else:
        lines.append("not_available=provide --runtime-log or a build log with heap snapshots")

    lines.extend(["", "[runtime_staging_allocations]"])
    if staging_allocations:
        for row in staging_allocations:
            lines.append(
                f"path={row['path']}:bytes={row['size_bytes']}:"
                f"source={row['source']}:provider={row['provider']}"
            )
    else:
        lines.append("not_available=provide --runtime-log or a build log with staging allocation lines")

    lines.extend(["", "[runtime_drop_notices]"])
    if drop_notices:
        total_dropped_messages = sum(
            int(row.get("count", 0)) for row in drop_notices
        )
        lines.append(f"count={len(drop_notices)}")
        lines.append(f"total_dropped_messages={total_dropped_messages}")
        lines.append("interpretation=zenoh_runtime_pressure_notice_not_evidence_loss")
        for row in drop_notices:
            lines.append(
                f"line={row['line']}:messages={row['count']}:"
                f"source_log={row['source_log']}"
            )
    else:
        lines.append("not_available=no dropped-message notices found in supplied logs")

    lines.extend(["", "[runtime_fatal_exceptions]"])
    if fatal_exceptions:
        lines.append(f"count={len(fatal_exceptions)}")
        for row in fatal_exceptions:
            lines.append(
                f"line={row['line']}:cause={row.get('cause')}:"
                f"detail={row.get('cause_detail')}:pc={row.get('pc')}:"
                f"vaddr={row.get('vaddr')}:source_log={row['source_log']}"
            )
    else:
        lines.append("not_available=no fatal exceptions found in supplied logs")

    lines.extend(["", "[runtime_evidence_gate]"])
    lines.append(f"required={runtime_gate.get('required', 'missing')}")
    lines.append(f"passed={runtime_gate.get('passed', 'missing')}")
    missing_values = runtime_gate_missing_values(runtime_gate)
    lines.append(f"missing={','.join(missing_values) or '-'}")
    lines.append(
        "has_update_heap_snapshot="
        f"{runtime_gate.get('has_update_heap_snapshot', 'missing')}"
    )
    lines.append(
        "has_app_runtime_heap_snapshot="
        f"{runtime_gate.get('has_app_runtime_heap_snapshot', 'missing')}"
    )
    lines.append(
        "has_staging_allocation="
        f"{runtime_gate.get('has_staging_allocation', 'missing')}"
    )

    lines.extend(["", "[external_staging_candidate_gate]"])
    lines.append(f"required={external_staging_gate.get('required', 'missing')}")
    lines.append(f"passed={external_staging_gate.get('passed', 'missing')}")
    lines.append(
        "missing="
        f"{','.join(runtime_gate_missing_values(external_staging_gate)) or '-'}"
    )
    lines.append(
        "external_memory_configured="
        f"{external_staging_gate.get('external_memory_configured', 'missing')}"
    )
    lines.append(
        "external_staging_preferred="
        f"{external_staging_gate.get('external_staging_preferred', 'missing')}"
    )
    lines.append(
        "has_external_staging_allocation="
        f"{external_staging_gate.get('has_external_staging_allocation', 'missing')}"
    )
    providers = external_staging_gate.get("providers", [])
    if isinstance(providers, list):
        lines.append(f"providers={','.join(str(item) for item in providers) or '-'}")
    else:
        lines.append(f"providers={providers}")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_build(args: argparse.Namespace, root: Path, log_path: Path) -> None:
    cmd: list[str] = [
        "bash",
        "applocation/NeuroLink/scripts/build_neurolink.sh",
        "--preset",
        args.preset,
        "--build-dir",
        args.build_dir,
    ]
    if args.no_c_style_check:
        cmd.append("--no-c-style-check")
    if args.pristine_always:
        cmd.append("--pristine-always")
    for overlay_config in args.overlay_config:
        cmd.extend(["--overlay-config", overlay_config])

    proc = subprocess.run(
        cmd,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr, end="")
        raise SystemExit(proc.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect NeuroLink Unit firmware memory evidence from a Zephyr build."
    )
    parser.add_argument("--build-dir", default="build/neurolink_unit")
    parser.add_argument("--output-dir", default="applocation/NeuroLink/memory-evidence")
    parser.add_argument("--label", default="baseline-1.1.6")
    parser.add_argument("--preset", default="unit")
    parser.add_argument("--build-log")
    parser.add_argument(
        "--runtime-log",
        action="append",
        default=[],
        help="Runtime log file containing update/app-runtime heap snapshot lines; may be repeated.",
    )
    parser.add_argument("--run-build", action="store_true")
    parser.add_argument("--pristine-always", action="store_true")
    parser.add_argument("--no-c-style-check", action="store_true")
    parser.add_argument(
        "--overlay-config",
        action="append",
        default=[],
        help="Kconfig overlay forwarded to build_neurolink.sh when --run-build is used.",
    )
    parser.add_argument(
        "--memory-provider",
        help="Optional provider label for the candidate memory policy, e.g. esp-spiram or none.",
    )
    parser.add_argument(
        "--require-runtime-evidence",
        action="store_true",
        help="Fail unless runtime/build logs contain update heap, app-runtime heap, and staging allocation evidence.",
    )
    parser.add_argument(
        "--require-external-staging-evidence",
        action="store_true",
        help="Fail unless evidence proves external ELF staging was preferred and used at runtime.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = workspace_root()
    neuro_root = neurolink_root()
    build_dir = (root / args.build_dir).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", args.label).strip("-") or "evidence"
    log_path = output_dir / f"{safe_label}.build.log"
    if args.run_build:
        run_build(args, root, log_path)

    config_path = build_dir / "zephyr" / ".config"
    stat_path = build_dir / "zephyr" / "zephyr.stat"
    build_info_path = build_dir / "build_info.yml"
    build_log_path = Path(args.build_log).resolve() if args.build_log else log_path
    if not build_log_path.is_file() and not args.run_build:
        build_log_path = None
    runtime_log_paths: list[Path | None] = [
        Path(path).resolve() for path in args.runtime_log
    ]
    if build_log_path is not None:
        runtime_log_paths.append(build_log_path)

    sections, totals = parse_stat_sections(stat_path)
    build_info = parse_build_info(build_info_path)
    config = parse_config(config_path)
    runtime_heap_snapshots = parse_runtime_heap_snapshots(runtime_log_paths)
    runtime_staging_allocations = parse_runtime_staging_allocations(runtime_log_paths)
    runtime_drop_notices = parse_runtime_drop_notices(runtime_log_paths)
    runtime_fatal_exceptions = parse_runtime_fatal_exceptions(runtime_log_paths)
    runtime_evidence_gate = evaluate_runtime_evidence_gate(
        runtime_heap_snapshots,
        runtime_staging_allocations,
        args.require_runtime_evidence,
    )
    memory_capability = infer_memory_capability(config, args.memory_provider)
    external_staging_candidate_gate = evaluate_external_staging_candidate_gate(
        memory_capability,
        runtime_staging_allocations,
        args.require_external_staging_evidence,
    )

    evidence: JsonObject = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "label": args.label,
        "release_target": parse_release_target(neuro_root / "neuro_cli" / "src" / "neuro_cli.py"),
        "build_dir": display_path(build_dir, root),
        "paths": {
            "config": display_path(config_path, root),
            "zephyr_stat": display_path(stat_path, root),
            "build_info": display_path(build_info_path, root),
            "build_log": display_path(build_log_path, root),
            "runtime_logs": [display_path(path, root) for path in runtime_log_paths],
        },
        "build_info": build_info,
        "platform": infer_platform(config, build_info),
        "memory_capability": memory_capability,
        "config": config,
        "section_totals": totals,
        "sections": sections,
        "build_memory_summary": parse_build_log(build_log_path),
        "runtime_heap_snapshots": runtime_heap_snapshots,
        "runtime_staging_allocations": runtime_staging_allocations,
        "runtime_drop_notices": runtime_drop_notices,
        "runtime_fatal_exceptions": runtime_fatal_exceptions,
        "runtime_evidence_gate": runtime_evidence_gate,
        "external_staging_candidate_gate": external_staging_candidate_gate,
    }

    json_path = output_dir / f"{safe_label}.json"
    summary_path = output_dir / f"{safe_label}.summary.txt"
    json_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary(summary_path, evidence)

    print(f"memory_evidence_json={json_path}")
    print(f"memory_evidence_summary={summary_path}")
    print(f"release_target={evidence['release_target']}")
    print(f"section_total_dram0={totals.get('dram0', 0)}")
    if args.require_runtime_evidence and not runtime_evidence_gate["passed"]:
        print(
            "runtime_evidence_gate=failed missing="
            f"{','.join(runtime_gate_missing_values(runtime_evidence_gate))}",
            file=sys.stderr,
        )
        return 2
    if (
        args.require_external_staging_evidence
        and not external_staging_candidate_gate["passed"]
    ):
        print(
            "external_staging_candidate_gate=failed missing="
            f"{','.join(runtime_gate_missing_values(external_staging_candidate_gate))}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
