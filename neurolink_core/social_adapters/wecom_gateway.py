from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
from pathlib import Path
import time
from typing import Any

import websockets

from .wecom import WeComSocialAdapter
from ..social import SocialMessageEnvelope


WECOM_GATEWAY_CLIENT_SCHEMA_VERSION = "2.2.3-wecom-gateway-client-v1"


def run_wecom_gateway_client(
    *,
    access_token: str,
    gateway_url: str,
    ingest_callback: Callable[[SocialMessageEnvelope, str], dict[str, Any]],
    duration: int = 30,
    max_events: int = 1,
    ready_file: str = "",
) -> dict[str, Any]:
    adapter = WeComSocialAdapter()

    async def _run() -> dict[str, Any]:
        deadline = time.monotonic() + max(duration, 1)
        state: dict[str, Any] = {
            "auth_sent": False,
            "ready_event_count": 0,
            "dispatch_event_count": 0,
            "ignored_event_count": 0,
            "listener_ready": False,
            "bot_user_id": "",
            "events": [],
            "core_results": [],
        }

        async with websockets.connect(gateway_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "op": "auth",
                        "d": {
                            "token": access_token,
                            "client": "neurolink_core",
                        },
                    },
                    sort_keys=True,
                )
            )
            state["auth_sent"] = True
            state["listener_ready"] = True
            if ready_file:
                ready_path = Path(ready_file)
                ready_path.parent.mkdir(parents=True, exist_ok=True)
                ready_path.write_text(
                    json.dumps(
                        {
                            "gateway_url": gateway_url,
                            "transport_kind": "websocket",
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            while time.monotonic() < deadline:
                if max_events > 0 and int(state["dispatch_event_count"]) >= max_events:
                    break
                timeout_seconds = max(deadline - time.monotonic(), 0.1)
                try:
                    raw_message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=timeout_seconds,
                    )
                except TimeoutError:
                    break
                payload = json.loads(raw_message)
                event_type = str(payload.get("event") or payload.get("type") or "")
                if event_type == "READY":
                    state["ready_event_count"] = int(state["ready_event_count"]) + 1
                    state["bot_user_id"] = str(payload.get("bot_user_id") or "")
                    continue
                if event_type not in {"message", "MESSAGE"}:
                    state["ignored_event_count"] = int(state["ignored_event_count"]) + 1
                    continue
                event_payload = (
                    payload.get("data") if isinstance(payload.get("data"), dict) else {}
                )
                envelope = adapter.envelope_from_event(event_payload)
                core_result = ingest_callback(envelope, event_type)
                state["dispatch_event_count"] = int(state["dispatch_event_count"]) + 1
                state["events"].append(
                    {
                        "event_type": event_type,
                        "channel_kind": envelope.channel_kind,
                        "principal_id": envelope.principal_id,
                        "social_message_id": envelope.social_message_id,
                    }
                )
                state["core_results"].append(
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

        closure_gates = {
            "gateway_connected": bool(state["listener_ready"]),
            "auth_sent": bool(state["auth_sent"]),
            "ready_recorded": int(state["ready_event_count"]) > 0,
            "dispatch_processed": int(state["dispatch_event_count"]) > 0,
            "core_ingress_recorded": any(
                bool(item.get("events_persisted")) for item in state["core_results"]
            ),
            "bounded_runtime": True,
        }
        status = "ready" if all(closure_gates.values()) else "incomplete"
        return {
            "schema_version": WECOM_GATEWAY_CLIENT_SCHEMA_VERSION,
            "command": "wecom-gateway-client",
            "status": status,
            "reason": "wecom_gateway_dispatch_processed"
            if status == "ready"
            else "wecom_gateway_timeout",
            "gateway": {
                "url": gateway_url,
                "transport_kind": "websocket",
            },
            "duration_seconds": max(duration, 1),
            "max_events": max_events,
            "ready_event_count": int(state["ready_event_count"]),
            "dispatch_event_count": int(state["dispatch_event_count"]),
            "ignored_event_count": int(state["ignored_event_count"]),
            "bot_user_id": str(state["bot_user_id"]),
            "events": list(state["events"]),
            "core_results": list(state["core_results"]),
            "closure_gates": closure_gates,
            "ok": all(closure_gates.values()),
        }

    return asyncio.run(_run())