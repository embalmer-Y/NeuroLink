from __future__ import annotations

from typing import Any

from ..social import MockSocialAdapter, SocialDeliveryRecord, SocialMessageEnvelope


class QQOfficialSocialAdapter:
    adapter_kind = "qq_official"

    def envelope_from_event(
        self,
        payload: dict[str, Any],
        *,
        received_at: str = "2026-05-11T12:00:00Z",
    ) -> SocialMessageEnvelope:
        author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
        member = payload.get("member") if isinstance(payload.get("member"), dict) else {}
        member_user = member.get("user") if isinstance(member.get("user"), dict) else {}
        external_user_id = str(
            payload.get("user_id")
            or author.get("id")
            or member_user.get("id")
            or payload.get("openid")
            or "unknown-qq-user"
        )
        group_id = str(
            payload.get("group_id")
            or payload.get("guild_id")
            or payload.get("channel_id")
            or ""
        )
        direct_id = str(payload.get("direct_message_id") or external_user_id)
        channel_kind = "group" if group_id else "direct"
        channel_id = group_id or f"direct-{direct_id}"
        text = str(payload.get("content") or payload.get("message") or "").strip()
        mentions = payload.get("mentions") if isinstance(payload.get("mentions"), list) else []
        mentioned_user_ids = [
            str(item.get("id") or "")
            for item in mentions
            if isinstance(item, dict) and str(item.get("id") or "")
        ]
        social_message_id = str(
            payload.get("id")
            or payload.get("message_id")
            or f"qq-official-{channel_id}-{external_user_id}"
        )
        is_admin = bool(payload.get("is_admin") or payload.get("operator_override"))
        session_scope_key = channel_id if channel_kind == "group" and mentioned_user_ids else f"{channel_id}:{external_user_id}"
        rate_limit_class = "admin" if is_admin else "group_user" if channel_kind == "group" else "normal_user"
        policy_tags = (
            "social_ingress",
            "user_input",
            f"channel_{channel_kind}",
            "adapter_qq_official",
            "official_api",
            "mention_required" if channel_kind == "group" else "direct_access",
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
            rate_limit_class=rate_limit_class,
            policy_tags=policy_tags,
            metadata={
                "source_payload_kind": "qq_official_bot",
                "message_id": social_message_id,
                "mentions_present": bool(mentioned_user_ids),
                "mentioned_user_ids": mentioned_user_ids,
                "mention_policy": "mention_or_direct",
                "transport_kind": "https",
                "session_scope": "shared_group" if channel_kind == "group" and mentioned_user_ids else "per_user",
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
