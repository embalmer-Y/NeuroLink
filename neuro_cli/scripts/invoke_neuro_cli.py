import argparse
import json
import subprocess
import sys
from pathlib import Path


EXIT_COMMAND_FAILED = 2
EXIT_NOT_IMPLEMENTED = 3
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


def payload_status_is_failure(status: object) -> bool:
    if status is None:
        return False

    return str(status) in PAYLOAD_FAILURE_STATUSES


def classify_payload(payload: object, process_returncode: int) -> tuple[int, str]:
    if not isinstance(payload, dict):
        return EXIT_COMMAND_FAILED, "json_payload_not_object"

    status = str(payload.get("status", ""))
    if status == "not_implemented":
        return EXIT_NOT_IMPLEMENTED, status

    for reply in payload.get("replies", []) if isinstance(payload.get("replies"), list) else []:
        reply_payload = reply.get("payload", {}) if isinstance(reply, dict) else {}
        if isinstance(reply_payload, dict):
            reply_status = str(reply_payload.get("status", ""))
            if reply_status == "not_implemented":
                return EXIT_NOT_IMPLEMENTED, reply_status
            if payload_status_is_failure(reply_status):
                return EXIT_COMMAND_FAILED, f"reply_status_{reply_status}"

    if payload.get("ok") is False:
        return EXIT_COMMAND_FAILED, status or "payload_not_ok"

    if payload_status_is_failure(status):
        return EXIT_COMMAND_FAILED, status

    if process_returncode != 0:
        return int(process_returncode), status or "process_failed"

    return 0, status or "ok"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoke NeuroLink neuro_cli.py for skills")
    parser.add_argument("--python", default=sys.executable, help="python executable path")
    parser.add_argument("--node", default="unit-01")
    parser.add_argument("--source-core", default="core-cli")
    parser.add_argument("--source-agent", default="skills")
    parser.add_argument("--timeout", type=float, default=None, help="forwarded query timeout")
    parser.add_argument(
        "--query-retries", type=int, default=None, help="forwarded query retry count"
    )
    parser.add_argument(
        "--query-retry-backoff-ms",
        type=int,
        default=None,
        help="forwarded initial query retry backoff",
    )
    parser.add_argument(
        "--query-retry-backoff-max-ms",
        type=int,
        default=None,
        help="forwarded maximum query retry backoff",
    )
    parser.add_argument(
        "cli_args",
        nargs=argparse.REMAINDER,
        help="arguments passed to neuro_cli.py, for example: query device",
    )
    return parser


def build_forwarded_global_args(args: argparse.Namespace) -> list[str]:
    forwarded = []
    for option_name in (
        "timeout",
        "query_retries",
        "query_retry_backoff_ms",
        "query_retry_backoff_max_ms",
    ):
        value = getattr(args, option_name)
        if value is not None:
            forwarded.extend([f"--{option_name.replace('_', '-')}", str(value)])
    return forwarded


def main() -> int:
    args = build_parser().parse_args()
    if not args.cli_args:
        print("missing CLI command arguments", file=sys.stderr)
        return 2

    cli_path = Path(__file__).resolve().parents[1] / "src" / "neuro_cli.py"

    cmd = [
        args.python,
        str(cli_path),
        "--output",
        "json",
        "--node",
        args.node,
        "--source-core",
        args.source_core,
        "--source-agent",
        args.source_agent,
    ] + build_forwarded_global_args(args) + args.cli_args

    proc = subprocess.run(cmd, capture_output=True, text=True)

    stdout = proc.stdout.strip()
    payload = None
    if stdout:
        try:
            payload = json.loads(stdout)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            failure = {
                "ok": False,
                "status": "invalid_json_stdout",
                "returncode": proc.returncode,
                "stdout": stdout,
            }
            print(json.dumps(failure, ensure_ascii=False, indent=2))
            payload = failure
    else:
        payload = {
            "ok": proc.returncode == 0,
            "status": "empty_stdout" if proc.returncode != 0 else "ok",
            "returncode": proc.returncode,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    stderr = proc.stderr.strip()
    if stderr:
        print(stderr, file=sys.stderr)

    exit_code, classification = classify_payload(payload, proc.returncode)
    if exit_code != 0:
        print(f"neuro_cli wrapper failure: {classification}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
