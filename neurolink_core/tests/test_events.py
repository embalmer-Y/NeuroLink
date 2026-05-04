import unittest

from neurolink_core.events import PerceptionEventRouter
from neurolink_core.workflow import NoModelCoreWorkflow
from neurolink_core.data import CoreDataStore


class TestPerceptionEventRouter(unittest.TestCase):
    def test_router_sorts_dedupes_and_assigns_causality(self) -> None:
        router = PerceptionEventRouter()
        observed = []
        router.subscribe(observed.append)

        events = router.route(
            [
                {
                    "event_id": "evt-low",
                    "source_kind": "clock",
                    "event_type": "time.tick",
                    "semantic_topic": "time.tick",
                    "timestamp_wall": "2026-05-04T00:00:02Z",
                    "priority": 10,
                    "dedupe_key": "tick-1",
                },
                {
                    "event_id": "evt-high",
                    "source_kind": "unit_app",
                    "event_type": "callback",
                    "semantic_topic": "unit.callback",
                    "timestamp_wall": "2026-05-04T00:00:01Z",
                    "priority": 90,
                    "dedupe_key": "callback-1",
                },
                {
                    "event_id": "evt-high-duplicate",
                    "source_kind": "unit_app",
                    "event_type": "callback",
                    "semantic_topic": "unit.callback",
                    "timestamp_wall": "2026-05-04T00:00:03Z",
                    "priority": 90,
                    "dedupe_key": "callback-1",
                },
            ]
        )

        self.assertEqual([event.event_id for event in events], ["evt-high", "evt-low"])
        self.assertEqual([event.event_id for event in observed], ["evt-high", "evt-low"])
        self.assertEqual(events[0].causality_id, "callback-1")
        self.assertEqual(events[1].causality_id, "tick-1")

    def test_workflow_uses_router_for_fanout_and_dedupe_before_persistence(self) -> None:
        router = PerceptionEventRouter()
        observed = []
        router.subscribe(observed.append)
        data_store = CoreDataStore()
        workflow = NoModelCoreWorkflow(data_store=data_store, event_router=router)

        result = workflow.run(
            [
                {
                    "event_id": "evt-a",
                    "source_kind": "unit_app",
                    "event_type": "callback",
                    "semantic_topic": "unit.callback",
                    "timestamp_wall": "2026-05-04T00:00:00Z",
                    "priority": 80,
                    "dedupe_key": "same-callback",
                },
                {
                    "event_id": "evt-b",
                    "source_kind": "unit_app",
                    "event_type": "callback",
                    "semantic_topic": "unit.callback",
                    "timestamp_wall": "2026-05-04T00:00:01Z",
                    "priority": 80,
                    "dedupe_key": "same-callback",
                },
            ]
        )

        self.assertEqual(result.events_persisted, 1)
        self.assertEqual(data_store.count("perception_events"), 1)
        self.assertEqual([event.event_id for event in observed], ["evt-a"])
        evidence = data_store.build_execution_evidence(result.execution_span_id, result.audit_id)
        self.assertEqual(evidence["execution_span"]["payload"]["normalized_event_count"], 1)
        data_store.close()


if __name__ == "__main__":
    unittest.main()
