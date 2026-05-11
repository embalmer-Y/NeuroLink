from __future__ import annotations

from typing import Any

from ..social import MockSocialAdapter, SocialDeliveryRecord, SocialMessageEnvelope


class WeComSocialAdapter:
    adapter_kind = "wecom"

    def envelope_from_event(
        self,
        payload: dict[str, Any],
        *,
        received_at: str = "2026-05-11T12:00:00Z",
    ) -> SocialMessageEnvelope:
        external_user_id = str(
            payload.get("from")
            or payload.get("userid")
            or payload.get("user_id")
            or "unknown-wecom-user"
        )
        conversation_type = str(payload.get("conversation_type") or "single")
        channel_kind = "group" if conversation_type in {"group", "room"} else "direct"
        room_id = str(payload.get("roomid") or payload.get("chatid") or "")
        channel_id = room_id or f"direct-{external_user_id}"
        text = str(payload.get("text") or payload.get("content") or "").strip()
        social_message_id = str(
            payload.get("msgid")
            or payload.get("message_id")
            or f"wecom-{channel_id}-{external_user_id}"
        )
        mention_list = payload.get("mentioned_list") if isinstance(payload.get("mentioned_list"), list) else []
        mentioned_user_ids = [
            str(item).strip()
            for item in mention_list
            if str(item).strip()
        ]
        session_scope = "shared_group" if channel_kind == "group" and mentioned_user_ids else "per_user"
        session_scope_key = channel_id if session_scope == "shared_group" else f"{channel_id}:{external_user_id}"
        policy_tags = (
            "social_ingress",
            "user_input",
            f"channel_{channel_kind}",
            "adapter_wecom",
            "official_enterprise_api",
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
                "source_payload_kind": "wecom_bot",
                "message_id": social_message_id,
                "mentioned_user_ids": mentioned_user_ids,
                "mention_policy": "mention_or_direct",
                "transport_kind": "websocket",
                "session_scope": session_scope,
                "session_scope_key": session_scope_key,
                "group_scene": "group" if channel_kind == "group" else "direct",
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