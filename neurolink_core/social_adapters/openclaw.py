from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..social import SocialMessageEnvelope


OPENCLAW_SOCIAL_CONTRACT_SCHEMA_VERSION = "2.2.3-openclaw-social-contract-v1"


def _first_text(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _text_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


@dataclass(frozen=True)
class OpenClawAdapterDefaults:
    platform_kind: str
    plugin_id: str
    plugin_package: str
    installer_package: str
    plugin_compliance_class: str


def build_openclaw_social_envelope(
    *,
    adapter_kind: str,
    payload: dict[str, Any],
    defaults: OpenClawAdapterDefaults,
    received_at: str = "2026-05-11T12:00:00Z",
) -> SocialMessageEnvelope:
    external_user_id = _first_text(
        payload,
        "from_user",
        "openid",
        "user_id",
        default="unknown-openclaw-user",
    )
    scene = _first_text(payload, "scene", default="direct").lower()
    channel_kind = "group" if scene == "group" else "direct"
    room_id = _first_text(payload, "room_id", "chatroom")
    channel_id = room_id or f"direct-{external_user_id}"
    text = _first_text(payload, "text", "content")
    social_message_id = _first_text(
        payload,
        "msg_id",
        "message_id",
        default=f"openclaw-{adapter_kind}-{channel_id}-{external_user_id}",
    )
    mentioned_user_ids = _text_list(payload, "mentioned_list")
    share_session_in_group = bool(payload.get("share_session_in_group"))
    session_scope = (
        "shared_group"
        if channel_kind == "group" and share_session_in_group
        else "per_user"
    )
    session_scope_key = (
        channel_id
        if session_scope == "shared_group"
        else f"{channel_id}:{external_user_id}"
    )
    plugin_id = _first_text(payload, "plugin_id", default=defaults.plugin_id)
    plugin_package = _first_text(
        payload, "plugin_package", default=defaults.plugin_package
    )
    installer_package = _first_text(
        payload, "installer_package", default=defaults.installer_package
    )
    host_version = _first_text(payload, "host_version")
    plugin_version = _first_text(payload, "plugin_version")
    raw_event_type = _first_text(payload, "event_type", "raw_event_type", default="message")
    policy_tags = (
        "social_ingress",
        "user_input",
        f"channel_{channel_kind}",
        f"adapter_{adapter_kind}",
        "runtime_openclaw",
        "hosted_plugin_bridge",
        "mention_or_direct" if channel_kind == "group" else "direct_access",
    )
    return SocialMessageEnvelope(
        social_message_id=social_message_id,
        adapter_kind=adapter_kind,
        channel_id=channel_id,
        channel_kind=channel_kind,
        external_user_id=external_user_id,
        principal_id=f"{adapter_kind}:{external_user_id}",
        message_kind="text",
        text=text,
        received_at=received_at,
        rate_limit_class="group_user" if channel_kind == "group" else "normal_user",
        policy_tags=policy_tags,
        metadata={
            "source_payload_kind": "openclaw",
            "social_contract_schema_version": OPENCLAW_SOCIAL_CONTRACT_SCHEMA_VERSION,
            "message_id": social_message_id,
            "mentioned_user_ids": mentioned_user_ids,
            "mention_policy": "mention_or_direct",
            "runtime_host": "openclaw",
            "transport_kind": "openclaw_gateway",
            "platform_kind": defaults.platform_kind,
            "plugin_id": plugin_id,
            "plugin_package": plugin_package,
            "plugin_version": plugin_version,
            "installer_package": installer_package,
            "host_version": host_version,
            "plugin_compliance_class": defaults.plugin_compliance_class,
            "share_session_in_group": share_session_in_group,
            "session_scope": session_scope,
            "session_scope_key": session_scope_key,
            "group_scene": "group" if channel_kind == "group" else "direct",
            "raw_event_type": raw_event_type,
            "live_network_executed": False,
        },
    )