from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .common import PerceptionEvent


EventSubscriber = Callable[[PerceptionEvent], None]


@dataclass
class PerceptionEventRouter:
    subscribers: list[EventSubscriber] = field(default_factory=lambda: [])
    seen_dedupe_keys: set[str] = field(default_factory=lambda: set())

    def subscribe(self, subscriber: EventSubscriber) -> None:
        self.subscribers.append(subscriber)

    def normalize(self, raw_events: Iterable[dict[str, Any]]) -> list[PerceptionEvent]:
        events: list[PerceptionEvent] = []
        for raw_event in raw_events:
            event = PerceptionEvent.from_payload(self._normalize_payload(raw_event))
            dedupe_key = event.dedupe_key or event.event_id
            if dedupe_key in self.seen_dedupe_keys:
                continue
            self.seen_dedupe_keys.add(dedupe_key)
            events.append(event)
        events.sort(
            key=lambda item: (
                -item.priority,
                item.timestamp_wall,
                item.event_id,
            )
        )
        return events

    def publish(self, events: Iterable[PerceptionEvent]) -> None:
        for event in events:
            for subscriber in self.subscribers:
                subscriber(event)

    def route(self, raw_events: Iterable[dict[str, Any]]) -> list[PerceptionEvent]:
        events = self.normalize(raw_events)
        self.publish(events)
        return events

    @staticmethod
    def _normalize_payload(raw_event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(raw_event)
        payload.setdefault("source_kind", "external")
        payload.setdefault("event_type", payload.get("semantic_topic") or "unknown")
        payload.setdefault("semantic_topic", payload.get("event_type") or "unknown")
        payload.setdefault("priority", 50)
        payload.setdefault("policy_tags", [])
        if not payload.get("dedupe_key"):
            payload["dedupe_key"] = payload.get("event_id")
        if not payload.get("causality_id"):
            payload["causality_id"] = payload.get("dedupe_key") or payload.get("event_id")
        if "payload" not in payload:
            payload["payload"] = {}
        return payload
