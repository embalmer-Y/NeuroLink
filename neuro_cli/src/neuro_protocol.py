import argparse
import json
import uuid
from collections.abc import Mapping, Sequence


DEFAULT_PROTOCOL_VERSION = "2.0"
DEFAULT_WIRE_ENCODING = "cbor-v2"
SUPPORTED_WIRE_ENCODINGS = ["cbor-v2"]
PLANNED_WIRE_ENCODINGS = []

CBOR_V2_MESSAGE_KINDS = {
    "query_request": 1,
    "lease_acquire_request": 2,
    "lease_release_request": 3,
    "app_command_request": 4,
    "callback_config_request": 5,
    "update_prepare_request": 6,
    "update_verify_request": 7,
    "update_activate_request": 8,
    "update_rollback_request": 9,
    "update_delete_request": 10,
    "error_reply": 20,
    "lease_reply": 21,
    "query_device_reply": 22,
    "query_apps_reply": 23,
    "query_leases_reply": 24,
    "update_prepare_reply": 25,
    "update_verify_reply": 26,
    "update_activate_reply": 27,
    "update_rollback_reply": 28,
    "app_command_reply": 29,
    "callback_event": 40,
    "update_event": 41,
    "state_event": 42,
    "lease_event": 43,
}

CBOR_V2_KEYS = {
    "schema_version": 0,
    "message_kind": 1,
    "status": 2,
    "request_id": 3,
    "node_id": 4,
    "source_core": 5,
    "source_agent": 6,
    "target_node": 7,
    "timeout_ms": 8,
    "priority": 9,
    "idempotency_key": 10,
    "lease_id": 11,
    "forwarded": 12,
    "status_code": 20,
    "message": 21,
    "resource": 30,
    "expires_at_ms": 31,
    "ttl_ms": 32,
    "board": 40,
    "zenoh_mode": 41,
    "session_ready": 42,
    "network_state": 43,
    "ipv4": 44,
    "app_id": 50,
    "command": 51,
    "args": 52,
    "start_args": 53,
    "reason": 54,
    "path": 55,
    "transport": 56,
    "artifact_key": 57,
    "size": 58,
    "chunk_size": 59,
    "app_count": 60,
    "running_count": 61,
    "suspended_count": 62,
    "apps": 63,
    "runtime_state": 64,
    "manifest_present": 65,
    "update_state": 66,
    "artifact_state": 67,
    "stable_ref": 68,
    "last_error": 69,
    "rollback_reason": 70,
    "leases": 71,
    "callback_enabled": 80,
    "trigger_every": 81,
    "event_name": 82,
    "invoke_count": 83,
    "start_count": 84,
    "config_changed": 85,
    "publish_ret": 86,
    "echo": 87,
    "stage": 90,
    "detail": 91,
    "state_version": 92,
    "action": 93,
}

CBOR_V2_KEY_NAMES = {value: key for key, value in CBOR_V2_KEYS.items()}
CBOR_V2_MESSAGE_KIND_NAMES = {
    value: key for key, value in CBOR_V2_MESSAGE_KINDS.items()
}


class CborDecodeError(ValueError):
    pass


def _cbor_encode_uint(major: int, value: int) -> bytes:
    if value < 0:
        raise ValueError("CBOR unsigned value must be non-negative")
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")


def cbor_encode(value) -> bytes:
    if isinstance(value, bool):
        return b"\xf5" if value else b"\xf4"
    if isinstance(value, int):
        if value >= 0:
            return _cbor_encode_uint(0, value)
        return _cbor_encode_uint(1, -1 - value)
    if isinstance(value, str):
        data = value.encode("utf-8")
        return _cbor_encode_uint(3, len(data)) + data
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda item: item[0])
        encoded = bytearray(_cbor_encode_uint(5, len(items)))
        for key, item_value in items:
            encoded.extend(cbor_encode(key))
            encoded.extend(cbor_encode(item_value))
        return bytes(encoded)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        encoded = bytearray(_cbor_encode_uint(4, len(value)))
        for item in value:
            encoded.extend(cbor_encode(item))
        return bytes(encoded)
    raise TypeError(f"unsupported CBOR value type: {type(value).__name__}")


def _cbor_read_arg(data: bytes, offset: int, additional: int) -> tuple[int, int]:
    if additional < 24:
        return additional, offset
    if additional == 24:
        end = offset + 1
    elif additional == 25:
        end = offset + 2
    elif additional == 26:
        end = offset + 4
    elif additional == 27:
        end = offset + 8
    else:
        raise CborDecodeError("unsupported indefinite or reserved CBOR length")
    if end > len(data):
        raise CborDecodeError("truncated CBOR value")
    return int.from_bytes(data[offset:end], "big"), end


def _cbor_decode_at(data: bytes, offset: int = 0):
    if offset >= len(data):
        raise CborDecodeError("empty or truncated CBOR payload")
    initial = data[offset]
    offset += 1
    major = initial >> 5
    additional = initial & 0x1F

    if major == 0:
        return _cbor_read_arg(data, offset, additional)
    if major == 1:
        value, offset = _cbor_read_arg(data, offset, additional)
        return -1 - value, offset
    if major == 3:
        length, offset = _cbor_read_arg(data, offset, additional)
        end = offset + length
        if end > len(data):
            raise CborDecodeError("truncated CBOR text string")
        return data[offset:end].decode("utf-8"), end
    if major == 4:
        length, offset = _cbor_read_arg(data, offset, additional)
        items = []
        for _ in range(length):
            item, offset = _cbor_decode_at(data, offset)
            items.append(item)
        return items, offset
    if major == 5:
        length, offset = _cbor_read_arg(data, offset, additional)
        result = {}
        for _ in range(length):
            key, offset = _cbor_decode_at(data, offset)
            value, offset = _cbor_decode_at(data, offset)
            result[key] = value
        return result, offset
    if major == 7 and additional in (20, 21):
        return additional == 21, offset
    raise CborDecodeError(f"unsupported CBOR major type: {major}")


def cbor_decode(data: bytes):
    value, offset = _cbor_decode_at(bytes(data), 0)
    if offset != len(data):
        raise CborDecodeError("trailing CBOR bytes")
    return value


def cbor_map_to_logical(value: dict) -> dict:
    logical: dict = {}
    for key, item in value.items():
        name = CBOR_V2_KEY_NAMES.get(key, key)
        if name == "message_kind" and isinstance(item, int):
            logical[name] = CBOR_V2_MESSAGE_KIND_NAMES.get(item, item)
        elif isinstance(item, dict):
            logical[name] = cbor_map_to_logical(item)
        elif isinstance(item, list):
            logical[name] = [
                cbor_map_to_logical(entry) if isinstance(entry, dict) else entry
                for entry in item
            ]
        else:
            logical[name] = item
    return logical


def logical_to_cbor_map(payload: dict, message_kind: str) -> dict:
    result = {
        CBOR_V2_KEYS["schema_version"]: 2,
        CBOR_V2_KEYS["message_kind"]: CBOR_V2_MESSAGE_KINDS[message_kind],
    }
    for name, value in payload.items():
        key = CBOR_V2_KEYS.get(name)
        if key is not None:
            result[key] = value
    return result


def encode_payload_cbor(payload: dict, message_kind: str) -> bytes:
    return cbor_encode(logical_to_cbor_map(payload, message_kind))


def decode_payload_cbor(data: bytes) -> dict:
    decoded = cbor_decode(data)
    if not isinstance(decoded, dict):
        raise CborDecodeError("CBOR payload root must be a map")
    return cbor_map_to_logical(decoded)


def payload_obj_to_bytes(payload_obj) -> bytes:
    if payload_obj is None:
        return b""
    if isinstance(payload_obj, (bytes, bytearray, memoryview)):
        return bytes(payload_obj)
    to_bytes = getattr(payload_obj, "to_bytes", None)
    if callable(to_bytes):
        return to_bytes()
    to_string = getattr(payload_obj, "to_string", None)
    if callable(to_string):
        return to_string().encode("utf-8")
    return str(payload_obj).encode("utf-8")


def parse_wire_payload(payload_obj) -> tuple[object, str, str]:
    raw_payload = payload_obj_to_bytes(payload_obj)
    if raw_payload and raw_payload[:1] not in (b"{", b"["):
        return decode_payload_cbor(raw_payload), "cbor-v2", raw_payload.hex()

    payload_text = raw_payload.decode("utf-8")
    try:
        return json.loads(payload_text), "json-v2", raw_payload.hex()
    except json.JSONDecodeError:
        return payload_text, "text", raw_payload.hex()


def message_kind_for_keyexpr(keyexpr: str, payload: dict | None = None) -> str:
    parts = keyexpr.split("/")
    if len(parts) >= 4 and parts[2] == "query":
        return "query_request"
    if len(parts) >= 5 and parts[2:4] == ["cmd", "lease"]:
        if parts[4] == "acquire":
            return "lease_acquire_request"
        if parts[4] == "release":
            return "lease_release_request"
    if len(parts) >= 5 and parts[2:4] == ["cmd", "app"]:
        callback_config_fields = {"callback_enabled", "trigger_every", "event_name"}
        if parts[-1] == "invoke" and payload is not None:
            if callback_config_fields.intersection(payload.keys()):
                return "callback_config_request"
        return "app_command_request"
    if len(parts) >= 6 and parts[2:4] == ["update", "app"]:
        action = parts[5]
        mapping = {
            "prepare": "update_prepare_request",
            "verify": "update_verify_request",
            "activate": "update_activate_request",
            "rollback": "update_rollback_request",
            "delete": "update_delete_request",
        }
        if action in mapping:
            return mapping[action]
    raise ValueError(f"unsupported CBOR route: {keyexpr}")


def encode_query_payload(keyexpr: str, payload: dict) -> bytes:
    return encode_payload_cbor(payload, message_kind_for_keyexpr(keyexpr, payload))

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
        payload_obj = reply.ok.payload
        keyexpr = str(reply.ok.key_expr)
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

    try:
        parsed_payload, payload_encoding, payload_hex = parse_wire_payload(payload_obj)
        return {
            "ok": True,
            "keyexpr": keyexpr,
            "payload": parsed_payload,
            "payload_encoding": payload_encoding,
            "payload_hex": payload_hex if payload_encoding == "cbor-v2" else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "parse_failed",
            "keyexpr": keyexpr,
            "payload": "<unreadable ok payload>",
            "error": str(exc),
        }
