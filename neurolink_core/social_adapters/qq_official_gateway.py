from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import json
from pathlib import Path
import time
from typing import Any
from urllib import request

import websockets

from .qq_official import QQOfficialSocialAdapter
from .qq_official_webhook import qq_official_extract_dispatch_payload
from ..social import SocialMessageEnvelope


QQ_OFFICIAL_GATEWAY_CLIENT_SCHEMA_VERSION = "2.2.2-qq-official-gateway-client-v1"
QQ_OFFICIAL_DEFAULT_GATEWAY_INTENTS = (1 << 12) | (1 << 25) | (1 << 30)


def _load_gateway_session_state(session_state_file: str) -> dict[str, Any]:
    if not session_state_file:
        return {}
    session_path = Path(session_state_file)
    if not session_path.exists():
        return {}
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_gateway_session_state(
    session_state_file: str,
    *,
    session_id: str,
    sequence: Any,
    gateway_url: str,
    can_resume: bool,
) -> None:
    if not session_state_file:
        return
    session_path = Path(session_state_file)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "sequence": sequence,
                "gateway_url": gateway_url,
                "can_resume": can_resume,
                "updated_at": int(time.time()),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def qq_official_fetch_access_token(*, app_id: str, app_secret: str) -> dict[str, Any]:
    payload = json.dumps(
        {
            "appId": app_id,
            "clientSecret": app_secret,
        }
    ).encode("utf-8")
    api_request = request.Request(
        "https://bots.qq.com/app/getAppAccessToken",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(api_request, timeout=10) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(response_payload, dict):
        raise ValueError("qq_official_access_token_invalid_payload")
    access_token = str(response_payload.get("access_token") or "")
    if not access_token:
        raise ValueError("qq_official_access_token_missing")
    return {
        "access_token": access_token,
        "expires_in": int(response_payload.get("expires_in") or 0),
    }


def qq_official_fetch_gateway_url(*, access_token: str) -> dict[str, Any]:
    api_request = request.Request(
        "https://api.sgroup.qq.com/gateway/bot",
        headers={"Authorization": f"QQBot {access_token}"},
        method="GET",
    )
    with request.urlopen(api_request, timeout=10) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(response_payload, dict):
        raise ValueError("qq_official_gateway_invalid_payload")
    gateway_url = str(response_payload.get("url") or "")
    if not gateway_url:
        raise ValueError("qq_official_gateway_url_missing")
    return {
        "url": gateway_url,
        "shards": int(response_payload.get("shards") or 0),
        "session_start_limit": response_payload.get("session_start_limit")
        if isinstance(response_payload.get("session_start_limit"), dict)
        else {},
    }


def run_qq_official_gateway_client(
    *,
    app_id: str,
    app_secret: str,
    ingest_callback: Callable[[SocialMessageEnvelope, str], dict[str, Any]],
    duration: int = 30,
    max_events: int = 1,
    ready_file: str = "",
    gateway_url: str = "",
    intents: int = QQ_OFFICIAL_DEFAULT_GATEWAY_INTENTS,
    session_state_file: str = "",
    max_resume_attempts: int = 2,
    reconnect_backoff_seconds: float = 1.0,
) -> dict[str, Any]:
    token_payload = qq_official_fetch_access_token(app_id=app_id, app_secret=app_secret)
    access_token = str(token_payload["access_token"])
    gateway_payload = (
        {
            "url": gateway_url,
            "shards": 0,
            "session_start_limit": {},
        }
        if gateway_url
        else qq_official_fetch_gateway_url(access_token=access_token)
    )
    adapter = QQOfficialSocialAdapter()

    async def _run() -> dict[str, Any]:
        resolved_gateway_url = str(gateway_payload.get("url") or "")
        deadline = time.monotonic() + max(duration, 1)
        loaded_session_state = _load_gateway_session_state(session_state_file)
        state: dict[str, Any] = {
            "hello_count": 0,
            "heartbeat_ack_count": 0,
            "ready_event_count": 0,
            "resumed_event_count": 0,
            "dispatch_event_count": 0,
            "ignored_event_count": 0,
            "resume_attempt_count": 0,
            "resume_success_count": 0,
            "reconnect_count": 0,
            "invalid_session_count": 0,
            "events": [],
            "core_results": [],
            "listener_ready": False,
            "session_id": str(loaded_session_state.get("session_id") or ""),
            "sequence": loaded_session_state.get("sequence"),
            "heartbeat_interval_ms": 0,
            "bot_user_id": "",
            "can_resume": bool(loaded_session_state.get("can_resume")),
        }

        def persist_session_state(*, can_resume: bool) -> None:
            _write_gateway_session_state(
                session_state_file,
                session_id=str(state["session_id"]),
                sequence=state["sequence"],
                gateway_url=resolved_gateway_url,
                can_resume=can_resume,
            )

        while time.monotonic() < deadline:
            if max_events > 0 and int(state["dispatch_event_count"]) >= max_events:
                break

            should_resume = bool(state["can_resume"] and state["session_id"] and state["sequence"] is not None)
            if should_resume:
                state["resume_attempt_count"] = int(state["resume_attempt_count"]) + 1

            try:
                async with websockets.connect(resolved_gateway_url) as websocket:
                    hello_raw = await asyncio.wait_for(websocket.recv(), timeout=max(deadline - time.monotonic(), 0.1))
                    hello_payload = json.loads(hello_raw)
                    if int(hello_payload.get("op") or 0) != 10:
                        raise ValueError("qq_official_gateway_hello_missing")
                    hello_data = hello_payload.get("d") if isinstance(hello_payload.get("d"), dict) else {}
                    heartbeat_interval_ms = int(hello_data.get("heartbeat_interval") or 0)
                    if heartbeat_interval_ms <= 0:
                        raise ValueError("qq_official_gateway_heartbeat_interval_missing")
                    state["hello_count"] = int(state["hello_count"]) + 1
                    state["heartbeat_interval_ms"] = heartbeat_interval_ms
                    state["listener_ready"] = True
                    if ready_file and int(state["hello_count"]) == 1:
                        ready_path = Path(ready_file)
                        ready_path.parent.mkdir(parents=True, exist_ok=True)
                        ready_path.write_text(
                            json.dumps(
                                {
                                    "gateway_url": resolved_gateway_url,
                                    "heartbeat_interval_ms": heartbeat_interval_ms,
                                    "intents": intents,
                                },
                                sort_keys=True,
                            )
                            + "\n",
                            encoding="utf-8",
                        )

                    if should_resume:
                        await websocket.send(
                            json.dumps(
                                {
                                    "op": 6,
                                    "d": {
                                        "token": f"QQBot {access_token}",
                                        "session_id": state["session_id"],
                                        "seq": state["sequence"],
                                    },
                                },
                                sort_keys=True,
                            )
                        )
                    else:
                        await websocket.send(
                            json.dumps(
                                {
                                    "op": 2,
                                    "d": {
                                        "token": f"QQBot {access_token}",
                                        "intents": intents,
                                        "shard": [0, 1],
                                        "properties": {
                                            "$os": "linux",
                                            "$browser": "neurolink_core",
                                            "$device": "neurolink_core",
                                        },
                                    },
                                },
                                sort_keys=True,
                            )
                        )

                    async def heartbeat_loop() -> None:
                        interval_seconds = max(heartbeat_interval_ms / 1000.0, 0.1)
                        while time.monotonic() < deadline:
                            await asyncio.sleep(interval_seconds)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "op": 1,
                                        "d": state["sequence"],
                                    },
                                    sort_keys=True,
                                )
                            )

                    heartbeat_task = asyncio.create_task(heartbeat_loop())
                    try:
                        while time.monotonic() < deadline:
                            if max_events > 0 and int(state["dispatch_event_count"]) >= max_events:
                                break
                            timeout_seconds = max(deadline - time.monotonic(), 0.1)
                            try:
                                raw_message = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
                            except TimeoutError:
                                break
                            payload = json.loads(raw_message)
                            if "s" in payload:
                                state["sequence"] = payload.get("s")
                                persist_session_state(can_resume=bool(state["session_id"]))
                            op_code = int(payload.get("op") or 0)
                            if op_code == 7:
                                state["can_resume"] = True
                                persist_session_state(can_resume=True)
                                break
                            if op_code == 9:
                                state["invalid_session_count"] = int(state["invalid_session_count"]) + 1
                                state["can_resume"] = False
                                state["session_id"] = ""
                                persist_session_state(can_resume=False)
                                break
                            if op_code == 11:
                                state["heartbeat_ack_count"] = int(state["heartbeat_ack_count"]) + 1
                                continue
                            if op_code != 0:
                                state["ignored_event_count"] = int(state["ignored_event_count"]) + 1
                                continue
                            event_type = str(payload.get("t") or "")
                            event_data = payload.get("d") if isinstance(payload.get("d"), dict) else {}
                            if event_type == "READY":
                                state["ready_event_count"] = int(state["ready_event_count"]) + 1
                                state["session_id"] = str(event_data.get("session_id") or "")
                                state["can_resume"] = bool(state["session_id"])
                                bot_user = event_data.get("user") if isinstance(event_data.get("user"), dict) else {}
                                state["bot_user_id"] = str(bot_user.get("id") or "")
                                persist_session_state(can_resume=bool(state["session_id"]))
                                continue
                            if event_type == "RESUMED":
                                state["resumed_event_count"] = int(state["resumed_event_count"]) + 1
                                state["resume_success_count"] = int(state["resume_success_count"]) + 1
                                state["can_resume"] = True
                                persist_session_state(can_resume=True)
                                continue
                            dispatch = qq_official_extract_dispatch_payload(payload)
                            if dispatch is None:
                                state["ignored_event_count"] = int(state["ignored_event_count"]) + 1
                                continue
                            normalized_event_type, event_payload = dispatch
                            envelope = adapter.envelope_from_event(event_payload)
                            core_result = ingest_callback(envelope, normalized_event_type)
                            state["dispatch_event_count"] = int(state["dispatch_event_count"]) + 1
                            cast_events = state["events"]
                            cast_core_results = state["core_results"]
                            cast_events.append(
                                {
                                    "event_type": normalized_event_type,
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
                            persist_session_state(can_resume=bool(state["session_id"]))
                    finally:
                        heartbeat_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await heartbeat_task
            except websockets.ConnectionClosed:
                pass

            if max_events > 0 and int(state["dispatch_event_count"]) >= max_events:
                break
            if time.monotonic() >= deadline:
                break
            if should_resume and int(state["resume_attempt_count"]) >= max(max_resume_attempts, 0):
                state["can_resume"] = False
                persist_session_state(can_resume=False)
                break
            if int(state["hello_count"]) > 0:
                state["reconnect_count"] = int(state["reconnect_count"]) + 1
            await asyncio.sleep(max(reconnect_backoff_seconds, 0.0))

        closure_gates = {
            "gateway_connected": bool(state["listener_ready"]),
            "hello_recorded": int(state["hello_count"]) > 0,
            "ready_recorded": int(state["ready_event_count"]) > 0,
            "dispatch_processed": int(state["dispatch_event_count"]) > 0,
            "core_ingress_recorded": any(
                bool(item.get("events_persisted")) for item in state["core_results"]
            ),
            "bounded_runtime": True,
        }
        status = "ready" if all(closure_gates.values()) else "incomplete"
        return {
            "schema_version": QQ_OFFICIAL_GATEWAY_CLIENT_SCHEMA_VERSION,
            "command": "qq-official-gateway-client",
            "status": status,
            "reason": "qq_official_gateway_dispatch_processed"
            if status == "ready"
            else "qq_official_gateway_timeout",
            "gateway": {
                "url": resolved_gateway_url,
                "shards": int(gateway_payload.get("shards") or 0),
                "session_start_limit": dict(gateway_payload.get("session_start_limit") or {}),
            },
            "access_token_expires_in": int(token_payload.get("expires_in") or 0),
            "intents": intents,
            "duration_seconds": max(duration, 1),
            "max_events": max_events,
            "hello_count": int(state["hello_count"]),
            "heartbeat_ack_count": int(state["heartbeat_ack_count"]),
            "ready_event_count": int(state["ready_event_count"]),
            "resumed_event_count": int(state["resumed_event_count"]),
            "resume_attempt_count": int(state["resume_attempt_count"]),
            "resume_success_count": int(state["resume_success_count"]),
            "reconnect_count": int(state["reconnect_count"]),
            "invalid_session_count": int(state["invalid_session_count"]),
            "dispatch_event_count": int(state["dispatch_event_count"]),
            "ignored_event_count": int(state["ignored_event_count"]),
            "heartbeat_interval_ms": int(state["heartbeat_interval_ms"]),
            "session_id": str(state["session_id"]),
            "sequence": state["sequence"],
            "bot_user_id": str(state["bot_user_id"]),
            "session_state_file": session_state_file,
            "session_state_persisted": bool(session_state_file and Path(session_state_file).exists()),
            "events": list(state["events"]),
            "core_results": list(state["core_results"]),
            "closure_gates": closure_gates,
            "ok": all(closure_gates.values()),
        }

    return asyncio.run(_run())