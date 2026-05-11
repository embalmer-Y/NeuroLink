from __future__ import annotations

from typing import Any, cast

from ..social import MockSocialAdapter, SocialDeliveryRecord, SocialMessageEnvelope


def _extract_onebot_text(message: Any) -> str:
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, list):
        parts: list[str] = []
        for raw_segment in message:
            if not isinstance(raw_segment, dict):
                continue
            segment = cast(dict[str, Any], raw_segment)
            if str(segment.get("type") or "") != "text":
                continue
            data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
            text = str(data.get("text") or "").strip()
            if text:
                parts.append(text)
        return " ".join(parts).strip()
    return ""


def _extract_onebot_mentions(message: Any) -> tuple[str, ...]:
    if not isinstance(message, list):
        return ()
    mentions: list[str] = []
    for raw_segment in message:
        if not isinstance(raw_segment, dict):
            continue
        segment = cast(dict[str, Any], raw_segment)
        if str(segment.get("type") or "") != "at":
            continue
        data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
        qq_id = str(data.get("qq") or "").strip()
        if qq_id:
            mentions.append(qq_id)
    return tuple(mentions)


class OneBotQQSocialAdapter:
    adapter_kind = "onebot_qq"

    def envelope_from_event(
        self,
        payload: dict[str, Any],
        *,
        received_at: str = "2026-05-11T12:00:00Z",
    ) -> SocialMessageEnvelope:
        message_type = str(payload.get("message_type") or "private").strip().lower()
        channel_kind = "group" if message_type == "group" else "direct"
        external_user_id = str(payload.get("user_id") or "unknown-onebot-user")
        channel_id = str(
            payload.get("group_id") if channel_kind == "group" else payload.get("user_id")
        )
        if not channel_id or channel_id == "None":
            channel_id = f"direct-{external_user_id}"
        social_message_id = str(
            payload.get("message_id")
            or f"onebot-{channel_id}-{external_user_id}"
        )
        message_payload = payload.get("message") or payload.get("raw_message") or ""
        text = _extract_onebot_text(message_payload)
        mentioned_user_ids = _extract_onebot_mentions(message_payload)
        self_id = str(payload.get("self_id") or "")
        is_self_message = bool(self_id and self_id == external_user_id)
        sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
        sender_role = str(sender.get("role") or "member")
        share_session_in_group = bool(payload.get("share_session_in_group"))
        session_scope = "shared_group" if channel_kind == "group" and share_session_in_group else "per_user"
        session_scope_key = channel_id if session_scope == "shared_group" else f"{channel_id}:{external_user_id}"
        policy_tags = (
            "social_ingress",
            "user_input",
            f"channel_{channel_kind}",
            "adapter_onebot_qq",
            "lab_bridge",
            "mention_or_direct" if channel_kind == "group" else "direct_access",
        )
        return SocialMessageEnvelope(
            social_message_id=social_message_id,
            adapter_kind=self.adapter_kind,
            channel_id=channel_id,
            channel_kind=channel_kind,
            external_user_id=external_user_id,
            principal_id=f"{self.adapter_kind}:{external_user_id}",
            message_kind="text",
            text=text,
            received_at=received_at,
            rate_limit_class="group_user" if channel_kind == "group" else "normal_user",
            policy_tags=policy_tags,
            metadata={
                "source_payload_kind": "onebot_v11",
                "message_type": message_type,
                "self_id": self_id,
                "is_self_message": is_self_message,
                "mentioned_user_ids": list(mentioned_user_ids),
                "mentioned_self": bool(self_id and self_id in mentioned_user_ids),
                "mention_policy": "mention_or_direct",
                "transport_kind": "reverse_websocket",
                "sender_role": sender_role,
                "share_session_in_group": share_session_in_group,
                "session_scope": session_scope,
                "session_scope_key": session_scope_key,
                "live_network_executed": False,
            },
        )

    def to_perception_event(self, envelope: SocialMessageEnvelope) -> dict[str, Any]:
        return MockSocialAdapter().to_perception_event(envelope)

    def deliver_affective_response(
        self,
        envelope: SocialMessageEnvelope,
        response: dict[str, Any],
    ) -> SocialDeliveryRecord:
        return MockSocialAdapter().deliver_affective_response(envelope, response)
