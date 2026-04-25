#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

try:
    import serial
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "pyserial is required; activate the NeuroLink .venv first "
        "or install it into the active interpreter"
    ) from exc


@dataclass
class ScheduledCommand:
    when_sec: float
    command: bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture NeuroLink UART output into a timestamped evidence log"
    )
    parser.add_argument(
        "--device",
        default="/dev/ttyACM0",
        help="serial device path (default: /dev/ttyACM0)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="baud rate (default: 115200)",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=150.0,
        help="capture duration in seconds (default: 150)",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=0.5,
        help="serial read timeout in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--output-base",
        default="applocation/NeuroLink/smoke-evidence/serial-diag",
        help="evidence-relative log directory",
    )
    parser.add_argument(
        "--log-prefix",
        default="serial-capture",
        help="prefix used for the generated log filename",
    )
    parser.add_argument(
        "--wake-after-sec",
        type=float,
        default=5.0,
        help="send a newline after this delay to wake the shell (default: 5)",
    )
    parser.add_argument(
        "--no-wake",
        action="store_true",
        help="disable automatic newline wake-up",
    )
    parser.add_argument(
        "--status-command",
        default="app status",
        help="command to send once a prompt is detected (default: app status)",
    )
    parser.add_argument(
        "--no-status-on-prompt",
        action="store_true",
        help="disable automatic status command when prompt is detected",
    )
    parser.add_argument(
        "--prompt-token",
        action="append",
        default=["uart:", "shell", ">"],
        help="substring that indicates a shell prompt; may be repeated",
    )
    parser.add_argument(
        "--send-after",
        action="append",
        default=[],
        metavar="SECONDS:COMMAND",
        help="schedule a command to send after a relative delay; may be repeated",
    )
    return parser


def parse_scheduled_command(spec: str) -> ScheduledCommand:
    delay_text, separator, command_text = spec.partition(":")
    if separator == "" or command_text.strip() == "":
        raise ValueError(
            f"invalid --send-after value '{spec}', expected SECONDS:COMMAND"
        )
    return ScheduledCommand(float(delay_text), (command_text + "\n").encode("utf-8"))


def resolve_output_dir(repo_root: Path, output_base: str) -> Path:
    output_dir = Path(output_base)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    output_dir = resolve_output_dir(repo_root, args.output_base)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = output_dir / f"{args.log_prefix}-{timestamp}.log"
    scheduled = [parse_scheduled_command(spec) for spec in args.send_after]
    scheduled.sort(key=lambda item: item.when_sec)

    prompt_tokens = [token.lower() for token in args.prompt_token]
    status_command = (args.status_command.rstrip("\n") + "\n").encode("utf-8")
    sent_wake = args.no_wake
    sent_status = args.no_status_on_prompt
    scheduled_index = 0
    bytes_written = 0

    print(f"log_path={log_path}")
    print(f"device={args.device}")
    print(f"baud={args.baud}")

    with serial.Serial(args.device, args.baud, timeout=args.timeout_sec) as ser:
        with log_path.open("wb") as log_file:
            start_time = time.monotonic()
            while time.monotonic() - start_time < args.duration_sec:
                elapsed = time.monotonic() - start_time

                if not sent_wake and elapsed >= args.wake_after_sec:
                    ser.write(b"\n")
                    ser.flush()
                    sent_wake = True

                while scheduled_index < len(scheduled):
                    item = scheduled[scheduled_index]
                    if elapsed < item.when_sec:
                        break
                    ser.write(item.command)
                    ser.flush()
                    scheduled_index += 1

                chunk = ser.read(4096)
                if chunk:
                    log_file.write(chunk)
                    log_file.flush()
                    bytes_written += len(chunk)
                    if not sent_status:
                        decoded = chunk.decode("utf-8", errors="ignore").lower()
                        if any(token in decoded for token in prompt_tokens):
                            ser.write(status_command)
                            ser.flush()
                            sent_status = True

                time.sleep(0.1)

    print(f"bytes_written={bytes_written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
