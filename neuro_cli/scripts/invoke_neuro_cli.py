import argparse
import json
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoke NeuroLink neuro_cli.py for skills")
    parser.add_argument("--python", default=sys.executable, help="python executable path")
    parser.add_argument("--node", default="unit-01")
    parser.add_argument("--source-core", default="core-cli")
    parser.add_argument("--source-agent", default="skills")
    parser.add_argument(
        "cli_args",
        nargs=argparse.REMAINDER,
        help="arguments passed to neuro_cli.py, for example: query device",
    )
    return parser


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
    ] + args.cli_args

    proc = subprocess.run(cmd, capture_output=True, text=True)

    stdout = proc.stdout.strip()
    if stdout:
        try:
            payload = json.loads(stdout)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print(stdout)

    stderr = proc.stderr.strip()
    if stderr:
        print(stderr, file=sys.stderr)

    return int(proc.returncode)


if __name__ == "__main__":
    sys.exit(main())
