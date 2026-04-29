#!/usr/bin/env python3
import json
import sys


def main() -> int:
    event = json.load(sys.stdin)
    audit = {
        "ok": True,
        "handler": "callback_handler.py",
        "keyexpr": event.get("keyexpr", ""),
        "payload_encoding": event.get("payload_encoding", ""),
        "payload_size": len(json.dumps(event.get("payload", {}))),
    }
    print(json.dumps(audit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
