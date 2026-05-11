from __future__ import annotations

from typing import Any

from ..social import MockSocialAdapter, SocialDeliveryRecord, SocialMessageEnvelope
from .openclaw import OpenClawAdapterDefaults
from .openclaw import build_openclaw_social_envelope


QQ_OPENCLAW_DEFAULTS = OpenClawAdapterDefaults(
    platform_kind="qq",
    plugin_id="qq_openclaw",
    plugin_package="",
    installer_package="",
    plugin_compliance_class="lab_compatibility",
)


class QQOpenClawSocialAdapter:
    adapter_kind = "qq_openclaw"

    def envelope_from_event(
        self,
        payload: dict[str, Any],
        *,
        received_at: str = "2026-05-11T12:00:00Z",
    ) -> SocialMessageEnvelope:
        return build_openclaw_social_envelope(
            adapter_kind=self.adapter_kind,
            payload=payload,
            defaults=QQ_OPENCLAW_DEFAULTS,
            received_at=received_at,
        )

    def to_perception_event(self, envelope: SocialMessageEnvelope) -> dict[str, Any]:
        return MockSocialAdapter().to_perception_event(envelope)

    def deliver_affective_response(
        self,
        envelope: SocialMessageEnvelope,
        response: dict[str, Any],
    ) -> SocialDeliveryRecord:
        return MockSocialAdapter().deliver_affective_response(envelope, response)