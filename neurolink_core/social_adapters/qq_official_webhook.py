from __future__ import annotations

from binascii import Error as BinasciiError, unhexlify
from collections.abc import Callable
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any

from .qq_official import QQOfficialSocialAdapter
from ..social import SocialMessageEnvelope


QQ_OFFICIAL_WEBHOOK_SERVER_SCHEMA_VERSION = "2.2.2-qq-official-webhook-server-v1"
QQ_OFFICIAL_DISPATCH_EVENT_TYPES = {
    "AT_MESSAGE_CREATE",
    "GROUP_AT_MESSAGE_CREATE",
    "DIRECT_MESSAGE_CREATE",
    "C2C_MESSAGE_CREATE",
}


def qq_official_validation_response(
    *,
    app_secret: str,
    plain_token: str,
    event_ts: str,
) -> dict[str, str]:
    if not app_secret:
        raise ValueError("qq_official_app_secret_missing")
    seed = app_secret
    while len(seed) < 32:
        seed = seed + seed
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed[:32].encode("utf-8"))
    signature = private_key.sign(f"{event_ts}{plain_token}".encode("utf-8")).hex()
    return {
        "plain_token": plain_token,
        "signature": signature,
    }


def qq_official_verify_request_signature(
    *,
    app_secret: str,
    signature_hex: str,
    signature_timestamp: str,
    body: bytes,
) -> bool:
    if not app_secret or not signature_hex or not signature_timestamp:
        return False
    seed = app_secret
    while len(seed) < 32:
        seed = seed + seed
    public_key = ed25519.Ed25519PrivateKey.from_private_bytes(
        seed[:32].encode("utf-8")
    ).public_key()
    try:
        signature = unhexlify(signature_hex)
    except (BinasciiError, ValueError):
        return False
    try:
        public_key.verify(signature, signature_timestamp.encode("utf-8") + body)
    except InvalidSignature:
        return False
    return True


def qq_official_extract_dispatch_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if int(payload.get("op") or 0) != 0:
        return None
    event_type = str(payload.get("t") or "").strip()
    if event_type not in QQ_OFFICIAL_DISPATCH_EVENT_TYPES:
        return None
    data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
    event_payload = dict(data)
    event_payload["event_type"] = event_type
    if event_type in {"DIRECT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE"}:
        if not event_payload.get("direct_message_id"):
            event_payload["direct_message_id"] = str(
                event_payload.get("id")
                or event_payload.get("message_id")
                or event_payload.get("user_id")
                or (event_payload.get("author") or {}).get("id")
                or "qq-direct-message"
            )
        event_payload.pop("group_id", None)
    elif not event_payload.get("group_id"):
        group_openid = str(event_payload.get("group_openid") or "").strip()
        if group_openid:
            event_payload["group_id"] = group_openid
    return event_type, event_payload


def run_qq_official_webhook_server(
    *,
    app_secret: str,
    ingest_callback: Callable[[SocialMessageEnvelope, str], dict[str, Any]],
    host: str = "127.0.0.1",
    port: int = 8091,
    path: str = "/",
    duration: int = 30,
    max_events: int = 1,
    ready_file: str = "",
) -> dict[str, Any]:
    adapter = QQOfficialSocialAdapter()
    normalized_path = path if path.startswith("/") else f"/{path}"
    deadline = time.monotonic() + max(duration, 1)
    state: dict[str, Any] = {
        "received_request_count": 0,
        "validation_request_count": 0,
        "validation_requests": [],
        "dispatch_event_count": 0,
        "ignored_event_count": 0,
        "events": [],
        "core_results": [],
        "listener_ready": False,
    }
    state_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            response = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            if self.path != normalized_path:
                self._write_json(404, {"ok": False, "reason": "path_not_found"})
                return
            body_length = int(self.headers.get("Content-Length") or "0")
            raw_body = self.rfile.read(body_length)
            with state_lock:
                state["received_request_count"] = int(state["received_request_count"]) + 1
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._write_json(400, {"ok": False, "reason": "invalid_json_payload"})
                return
            if not isinstance(payload, dict):
                self._write_json(400, {"ok": False, "reason": "invalid_payload_shape"})
                return
            if int(payload.get("op") or 0) == 13:
                data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
                plain_token = str(data.get("plain_token") or "")
                event_ts = str(data.get("event_ts") or "")
                request_signature = str(self.headers.get("X-Signature-Ed25519") or "")
                request_signature_timestamp = str(
                    self.headers.get("X-Signature-Timestamp") or ""
                )
                response = qq_official_validation_response(
                    app_secret=app_secret,
                    plain_token=plain_token,
                    event_ts=event_ts,
                )
                with state_lock:
                    state["validation_request_count"] = int(state["validation_request_count"]) + 1
                    cast_validation_requests = state["validation_requests"]
                    validation_request = {
                        "path": self.path,
                        "x_bot_appid": str(self.headers.get("X-Bot-Appid") or ""),
                        "user_agent": str(self.headers.get("User-Agent") or ""),
                        "x_signature_timestamp": request_signature_timestamp,
                        "x_signature_ed25519_present": bool(request_signature),
                        "request_signature_valid": qq_official_verify_request_signature(
                            app_secret=app_secret,
                            signature_hex=request_signature,
                            signature_timestamp=request_signature_timestamp,
                            body=raw_body,
                        ),
                        "plain_token": plain_token,
                        "event_ts": event_ts,
                        "response_signature": str(response.get("signature") or ""),
                    }
                    cast_validation_requests.append(validation_request)
                print(
                    json.dumps(
                        {
                            "command": "qq-official-webhook-server",
                            "diagnostic_event": "validation_request_received",
                            "validation_request": validation_request,
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                    flush=True,
                    )
                self._write_json(200, response)
                return
            dispatch = qq_official_extract_dispatch_payload(payload)
            if dispatch is None:
                with state_lock:
                    state["ignored_event_count"] = int(state["ignored_event_count"]) + 1
                self._write_json(202, {"ok": True, "reason": "ignored_event_type"})
                return
            event_type, event_payload = dispatch
            try:
                envelope = adapter.envelope_from_event(event_payload)
                core_result = ingest_callback(envelope, event_type)
            except Exception as exc:
                self._write_json(
                    500,
                    {
                        "ok": False,
                        "reason": "qq_official_dispatch_failed",
                        "error": str(exc),
                    },
                )
                return
            with state_lock:
                state["dispatch_event_count"] = int(state["dispatch_event_count"]) + 1
                cast_events = state["events"]
                cast_core_results = state["core_results"]
                cast_events.append(
                    {
                        "event_type": event_type,
                        "channel_kind": envelope.channel_kind,
                        "principal_id": envelope.principal_id,
                        "social_message_id": envelope.social_message_id,
                    }
                )
                cast_core_results.append(
                    {
                        "ok": bool(core_result.get("ok", False)),
                        "status": str(core_result.get("status") or ""),
                        "events_persisted": int(core_result.get("events_persisted") or 0),
                        "final_response_speaker": str(
                            (core_result.get("final_response") or {}).get("speaker")
                            if isinstance(core_result.get("final_response"), dict)
                            else ""
                        ),
                    }
                )
            self._write_json(200, {"op": 12})

    server = ThreadingHTTPServer((host, port), Handler)
    server.timeout = 0.25
    actual_host, actual_port = server.server_address[:2]
    if ready_file:
        ready_path = Path(ready_file)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_text(
            json.dumps(
                {
                    "host": actual_host,
                    "port": actual_port,
                    "path": normalized_path,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    state["listener_ready"] = True
    try:
        while time.monotonic() < deadline:
            if max_events > 0 and int(state["dispatch_event_count"]) >= max_events:
                break
            server.handle_request()
    finally:
        server.server_close()
    closure_gates = {
        "listener_ready": bool(state["listener_ready"]),
        "dispatch_processed": int(state["dispatch_event_count"]) > 0,
        "core_ingress_recorded": any(
            bool(item.get("events_persisted")) for item in state["core_results"]
        ),
        "bounded_runtime": True,
    }
    status = "ready" if all(closure_gates.values()) else "incomplete"
    reason = "qq_official_webhook_dispatch_processed" if status == "ready" else "qq_official_webhook_timeout"
    return {
        "schema_version": QQ_OFFICIAL_WEBHOOK_SERVER_SCHEMA_VERSION,
        "command": "qq-official-webhook-server",
        "status": status,
        "reason": reason,
        "listen_address": {
            "host": str(actual_host),
            "port": int(actual_port),
            "path": normalized_path,
        },
        "duration_seconds": max(duration, 1),
        "max_events": max_events,
        "received_request_count": int(state["received_request_count"]),
        "validation_request_count": int(state["validation_request_count"]),
        "validation_requests": list(state["validation_requests"]),
        "dispatch_event_count": int(state["dispatch_event_count"]),
        "ignored_event_count": int(state["ignored_event_count"]),
        "events": list(state["events"]),
        "core_results": list(state["core_results"]),
        "closure_gates": closure_gates,
        "ok": all(closure_gates.values()),
    }