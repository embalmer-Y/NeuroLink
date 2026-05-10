from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _normalize_channel_kind(channel_kind: str) -> str:
    normalized = channel_kind.strip().lower()
    if normalized not in {"group", "direct", "channel"}:
        raise ValueError(f"unsupported social channel kind: {channel_kind}")
    return normalized


@dataclass(frozen=True)
class SocialMessageEnvelope:
    social_message_id: str
    adapter_kind: str
    channel_id: str
    channel_kind: str
    external_user_id: str
    principal_id: str
    message_kind: str
    text: str
    received_at: str
    rate_limit_class: str
    policy_tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SocialMessageEnvelope":
        return cls(
            social_message_id=str(payload.get("social_message_id") or "social-unknown"),
            adapter_kind=str(payload.get("adapter_kind") or "mock_social"),
            channel_id=str(payload.get("channel_id") or "unknown-channel"),
            channel_kind=_normalize_channel_kind(str(payload.get("channel_kind") or "direct")),
            external_user_id=str(payload.get("external_user_id") or "unknown-user"),
            principal_id=str(payload.get("principal_id") or "user-unknown"),
            message_kind=str(payload.get("message_kind") or "text"),
            text=str(payload.get("text") or ""),
            received_at=str(payload.get("received_at") or ""),
            rate_limit_class=str(payload.get("rate_limit_class") or "normal_user"),
            policy_tags=tuple(str(item) for item in (payload.get("policy_tags") or [])),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "social_message_id": self.social_message_id,
            "adapter_kind": self.adapter_kind,
            "channel_id": self.channel_id,
            "channel_kind": self.channel_kind,
            "external_user_id": self.external_user_id,
            "principal_id": self.principal_id,
            "message_kind": self.message_kind,
            "text": self.text,
            "received_at": self.received_at,
            "rate_limit_class": self.rate_limit_class,
            "policy_tags": list(self.policy_tags),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SocialDeliveryRecord:
    delivery_id: str
    adapter_kind: str
    channel_id: str
    principal_id: str
    speaker: str
    delivery_status: str
    delivered_text: str
    audit_tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "adapter_kind": self.adapter_kind,
            "channel_id": self.channel_id,
            "principal_id": self.principal_id,
            "speaker": self.speaker,
            "delivery_status": self.delivery_status,
            "delivered_text": self.delivered_text,
            "audit_tags": list(self.audit_tags),
        }


@dataclass(frozen=True)
class SocialApprovalEnvelope:
    approval_request_id: str
    adapter_kind: str
    channel_id: str
    channel_kind: str
    external_user_id: str
    principal_id: str
    decision_text: str
    received_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_request_id": self.approval_request_id,
            "adapter_kind": self.adapter_kind,
            "channel_id": self.channel_id,
            "channel_kind": self.channel_kind,
            "external_user_id": self.external_user_id,
            "principal_id": self.principal_id,
            "decision_text": self.decision_text,
            "received_at": self.received_at,
        }


def build_social_approval_summary(
    approval_request: dict[str, Any],
    approval_context: dict[str, Any],
) -> dict[str, Any]:
    request_payload = dict(approval_request.get("payload") or {})
    requested_args = dict(request_payload.get("requested_args") or {})
    operator_requirements = dict(approval_context.get("operator_requirements") or {})
    required_resources = list(operator_requirements.get("required_resources") or [])
    missing_resources = list(
        operator_requirements.get("missing_required_resources") or []
    )
    return {
        "approval_request_id": approval_request.get("approval_request_id"),
        "status": approval_request.get("status"),
        "tool_name": approval_request.get("tool_name"),
        "requested_args": requested_args,
        "required_resources": required_resources,
        "missing_required_resources": missing_resources,
        "human_summary": (
            f"Pending approval for {approval_request.get('tool_name')} "
            f"with args {requested_args or {}}. "
            f"Required resources: {required_resources or ['none']}. "
            f"Missing resources: {missing_resources or ['none']}."
        ),
    }


class MockSocialAdapter:
    def bind_principal(
        self,
        *,
        adapter_kind: str,
        channel_id: str,
        channel_kind: str,
        external_user_id: str,
        text: str,
        received_at: str,
        is_admin: bool = False,
    ) -> SocialMessageEnvelope:
        resolved_channel_kind = _normalize_channel_kind(channel_kind)
        if is_admin:
            rate_limit_class = "admin"
        elif resolved_channel_kind == "group":
            rate_limit_class = "group_user"
        else:
            rate_limit_class = "normal_user"
        principal_id = f"{adapter_kind}:{external_user_id}"
        policy_tags = ("social_ingress", "user_input", f"channel_{resolved_channel_kind}")
        return SocialMessageEnvelope(
            social_message_id=f"social-{adapter_kind}-{channel_id}-{external_user_id}",
            adapter_kind=adapter_kind,
            channel_id=channel_id,
            channel_kind=resolved_channel_kind,
            external_user_id=external_user_id,
            principal_id=principal_id,
            message_kind="text",
            text=text,
            received_at=received_at,
            rate_limit_class=rate_limit_class,
            policy_tags=policy_tags,
            metadata={
                "is_admin": is_admin,
                "channel_kind": resolved_channel_kind,
            },
        )

    def to_perception_event(self, envelope: SocialMessageEnvelope) -> dict[str, Any]:
        semantic_topic = "user.input.social.direct"
        if envelope.channel_kind == "group":
            semantic_topic = "user.input.social.group"
        elif envelope.channel_kind == "channel":
            semantic_topic = "user.input.social.channel"
        return {
            "event_id": envelope.social_message_id,
            "source_kind": "social",
            "source_node": envelope.adapter_kind,
            "event_type": "user.input.social",
            "semantic_topic": semantic_topic,
            "timestamp_wall": envelope.received_at,
            "priority": 70 if envelope.rate_limit_class == "admin" else 55,
            "dedupe_key": envelope.social_message_id,
            "policy_tags": list(envelope.policy_tags),
            "payload": {
                "text": envelope.text,
                "channel_id": envelope.channel_id,
                "channel_kind": envelope.channel_kind,
                "external_user_id": envelope.external_user_id,
                "principal_id": envelope.principal_id,
                "rate_limit_class": envelope.rate_limit_class,
                "social_adapter": envelope.adapter_kind,
            },
        }

    def deliver_affective_response(
        self,
        envelope: SocialMessageEnvelope,
        response: dict[str, Any],
    ) -> SocialDeliveryRecord:
        speaker = str(response.get("speaker") or "")
        if speaker != "affective":
            raise ValueError("social_delivery_requires_affective_speaker")
        delivered_text = str(response.get("text") or "")
        return SocialDeliveryRecord(
            delivery_id=f"delivery-{envelope.social_message_id}",
            adapter_kind=envelope.adapter_kind,
            channel_id=envelope.channel_id,
            principal_id=envelope.principal_id,
            speaker=speaker,
            delivery_status="delivered",
            delivered_text=delivered_text,
            audit_tags=("social_egress", "affective_only"),
        )

    def bind_approval_principal(
        self,
        *,
        approval_request_id: str,
        adapter_kind: str,
        channel_id: str,
        channel_kind: str,
        external_user_id: str,
        decision_text: str,
        received_at: str,
    ) -> SocialApprovalEnvelope:
        return SocialApprovalEnvelope(
            approval_request_id=approval_request_id,
            adapter_kind=adapter_kind,
            channel_id=channel_id,
            channel_kind=_normalize_channel_kind(channel_kind),
            external_user_id=external_user_id,
            principal_id=f"{adapter_kind}:{external_user_id}",
            decision_text=decision_text,
            received_at=received_at,
        )

    def social_approval_metadata(
        self,
        envelope: SocialApprovalEnvelope,
    ) -> dict[str, Any]:
        return {
            "approval_channel": "social",
            "social_adapter": envelope.adapter_kind,
            "channel_id": envelope.channel_id,
            "channel_kind": envelope.channel_kind,
            "external_user_id": envelope.external_user_id,
            "principal_id": envelope.principal_id,
            "decision_text": envelope.decision_text,
            "received_at": envelope.received_at,
        }