import argparse
import json
import uuid


DEFAULT_PROTOCOL_VERSION = "2.0"
DEFAULT_WIRE_ENCODING = "json-v2"
SUPPORTED_WIRE_ENCODINGS = ["json-v2"]
PLANNED_WIRE_ENCODINGS = ["cbor-v2"]

CAPABILITY_MATRIX = {
    "query_device": {
        "resource": "neuro/<node>/query/device",
        "implemented": True,
    },
    "query_apps": {
        "resource": "neuro/<node>/query/apps",
        "implemented": True,
    },
    "query_leases": {
        "resource": "neuro/<node>/query/leases",
        "implemented": True,
    },
    "cmd_lease_acquire": {
        "resource": "neuro/<node>/cmd/lease/acquire",
        "implemented": True,
    },
    "cmd_lease_release": {
        "resource": "neuro/<node>/cmd/lease/release",
        "implemented": True,
    },
    "cmd_app": {
        "resource": "neuro/<node>/cmd/app/<app-id>/<command-name>",
        "implemented": True,
    },
    "update_prepare": {
        "resource": "neuro/<node>/update/app/<app-id>/prepare",
        "implemented": True,
    },
    "update_verify": {
        "resource": "neuro/<node>/update/app/<app-id>/verify",
        "implemented": True,
    },
    "update_activate": {
        "resource": "neuro/<node>/update/app/<app-id>/activate",
        "implemented": True,
    },
    "update_rollback": {
        "resource": "neuro/<node>/update/app/<app-id>/rollback",
        "implemented": True,
    },
    "event_stream": {
        "resource": "neuro/<node>/event/**",
        "implemented": True,
    },
    "app_event_stream": {
        "resource": "neuro/<node>/event/app/<app-id>/**",
        "implemented": True,
    },
    "recovery": {
        "resource": "recovery lifecycle",
        "implemented": False,
        "note": "LLD defined, Unit runtime not implemented yet",
    },
    "gateway": {
        "resource": "gateway route and relay",
        "implemented": False,
        "note": "LLD defined, Unit runtime not implemented yet",
    },
    "state_registry": {
        "resource": "state registry management",
        "implemented": False,
        "note": "LLD defined, Unit runtime not implemented yet",
    },
}


def make_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


def make_idempotency_key() -> str:
    return f"idem-{uuid.uuid4().hex[:12]}"


def query_route(node: str, kind: str) -> str:
    return f"neuro/{node}/query/{kind}"


def lease_route(node: str, action: str) -> str:
    return f"neuro/{node}/cmd/lease/{action}"


def app_command_route(node: str, app_id: str, command: str) -> str:
    return f"neuro/{node}/cmd/app/{app_id}/{command}"


def update_route(node: str, app_id: str, stage: str) -> str:
    return f"neuro/{node}/update/app/{app_id}/{stage}"


def event_subscription_route(node: str) -> str:
    return f"neuro/{node}/event/**"


def app_event_subscription_route(node: str, app_id: str) -> str:
    return f"neuro/{node}/event/app/{app_id}/**"


def artifact_route(node: str, app_id: str) -> str:
    return f"neuro/artifact/{node}/{app_id}"


def validate_payload(payload: dict, mode: str) -> None:
    common_fields = [
        "request_id",
        "source_core",
        "source_agent",
        "target_node",
        "timeout_ms",
    ]
    for field in common_fields:
        if field not in payload or payload[field] in ("", None, 0):
            raise ValueError(f"missing required common metadata: {field}")

    if mode in ("write", "protected"):
        if payload.get("priority", None) is None:
            raise ValueError("missing required write metadata: priority")
        if not payload.get("idempotency_key", ""):
            raise ValueError("missing required write metadata: idempotency_key")

    if mode == "protected":
        if not payload.get("lease_id", ""):
            raise ValueError("missing required protected metadata: lease_id")


def base_payload(args: argparse.Namespace) -> dict:
    request_id = args.request_id if args.request_id else make_request_id()
    return {
        "request_id": request_id,
        "source_core": args.source_core,
        "source_agent": args.source_agent,
        "target_node": args.node,
        "timeout_ms": int(args.timeout * 1000),
    }


def write_payload(args: argparse.Namespace) -> dict:
    payload = base_payload(args)
    payload["priority"] = args.priority
    payload["idempotency_key"] = args.idempotency_key or make_idempotency_key()
    return payload


def protected_write_payload(args: argparse.Namespace) -> dict:
    payload = write_payload(args)
    payload["lease_id"] = args.lease_id
    return payload


def build_app_callback_config_payload(
    args: argparse.Namespace, enabled: bool | None = None
) -> dict:
    payload = protected_write_payload(args)
    callback_enabled = args.mode == "on" if enabled is None else enabled
    payload["callback_enabled"] = callback_enabled
    payload["trigger_every"] = max(0, int(args.trigger_every))
    payload["event_name"] = args.event_name
    return payload


def parse_reply(reply) -> dict:
    try:
        payload = reply.ok.payload.to_string()
        try:
            parsed_payload = json.loads(payload)
        except json.JSONDecodeError:
            parsed_payload = payload
        return {
            "ok": True,
            "keyexpr": str(reply.ok.key_expr),
            "payload": parsed_payload,
        }
    except Exception:
        error_payload = "<unreadable error payload>"
        try:
            error_payload = reply.err.payload.to_string()
        except Exception:
            pass
        return {
            "ok": False,
            "payload": error_payload,
        }
