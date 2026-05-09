import unittest

from neurolink_core.federation import (
    DELEGATED_EXECUTION_SCHEMA_VERSION,
    FEDERATION_ROUTE_SMOKE_SCHEMA_VERSION,
    FEDERATION_ROUTE_SCHEMA_VERSION,
    UNIT_CAPABILITY_SCHEMA_VERSION,
    CorePeerDescriptor,
    FederationTopologyRegistry,
    UnitCapabilityDescriptor,
    build_delegated_execution_proposal,
    federation_route_smoke,
)


class TestFederationTopologyRegistry(unittest.TestCase):
    def test_plan_route_returns_direct_for_local_unit(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_local_unit(
            UnitCapabilityDescriptor(
                node_id="unit-local-01",
                architecture="xtensa",
                abi="zephyr-llext-v1",
                board_family="esp32s3-class",
                llext_supported=True,
                network_transports=("wifi",),
            )
        )

        route = registry.plan_route("unit-local-01", now="2026-05-09T12:00:00Z")

        self.assertTrue(route.ok)
        self.assertEqual(route.schema_version, FEDERATION_ROUTE_SCHEMA_VERSION)
        self.assertEqual(route.route_kind, "direct")
        self.assertEqual(route.status, "route_ready")
        self.assertEqual(route.target_core, None)

    def test_plan_route_returns_relay_for_local_unit_with_relay_path(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_local_unit(
            UnitCapabilityDescriptor(
                node_id="unit-relay-01",
                architecture="arm",
                abi="zephyr-llext-v1",
                board_family="cortex-m-class",
                relay_capable=True,
                relay_path=("gateway-01",),
                network_transports=("ethernet", "serial_bridge"),
            )
        )

        route = registry.plan_route("unit-relay-01", now="2026-05-09T12:00:00Z")

        self.assertTrue(route.ok)
        self.assertEqual(route.route_kind, "relay")
        self.assertEqual(route.relay_path, ("gateway-01",))

    def test_plan_route_rejects_relay_path_without_relay_capability(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_local_unit(
            UnitCapabilityDescriptor(
                node_id="unit-relay-01",
                architecture="arm",
                abi="zephyr-llext-v1",
                board_family="cortex-m-class",
                relay_capable=False,
                relay_path=("gateway-01",),
                network_transports=("ethernet", "serial_bridge"),
            )
        )

        route = registry.plan_route("unit-relay-01", now="2026-05-09T12:00:00Z")

        self.assertFalse(route.ok)
        self.assertEqual(route.route_kind, "relay")
        self.assertEqual(route.status, "route_rejected")
        self.assertEqual(route.failure_reason, "relay_capability_mismatch")
        self.assertEqual(route.relay_path, ("gateway-01",))

    def test_plan_route_rejects_local_relay_when_required_transport_is_missing(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_local_unit(
            UnitCapabilityDescriptor(
                node_id="unit-relay-01",
                architecture="arm",
                abi="zephyr-llext-v1",
                board_family="cortex-m-class",
                relay_capable=True,
                relay_path=("gateway-01",),
                network_transports=("ethernet", "serial_bridge"),
            )
        )

        route = registry.plan_route(
            "unit-relay-01",
            now="2026-05-09T12:00:00Z",
            required_transport="wifi",
        )

        self.assertFalse(route.ok)
        self.assertEqual(route.route_kind, "relay")
        self.assertEqual(route.status, "route_rejected")
        self.assertEqual(route.failure_reason, "transport_mismatch")
        self.assertEqual(route.relay_path, ("gateway-01",))

    def test_plan_route_returns_delegated_core_for_fresh_trusted_peer(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="lab-federation",
                remote_units=("unit-remote-01",),
                capabilities=("delegated_execution",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at="2026-05-09T12:30:00Z",
                reachable=True,
            )
        )

        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        self.assertTrue(route.ok)
        self.assertEqual(route.route_kind, "delegated_core")
        self.assertEqual(route.target_core, "core-b")
        self.assertEqual(route.trust_scope, "lab-federation")

    def test_plan_route_preserves_peer_relay_attachment_metadata(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="lab-federation",
                remote_units=("unit-remote-01",),
                remote_unit_attachments=(
                    {
                        "node_id": "unit-remote-01",
                        "relay_path": ["gateway-b-01"],
                        "network_transports": ["ethernet", "serial_bridge"],
                    },
                ),
                capabilities=("delegated_execution",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at="2026-05-09T12:30:00Z",
                reachable=True,
            )
        )

        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        self.assertTrue(route.ok)
        self.assertEqual(route.route_kind, "delegated_core")
        self.assertEqual(route.target_core, "core-b")
        self.assertEqual(route.relay_path, ("gateway-b-01",))

    def test_plan_route_rejects_peer_relay_when_required_transport_is_missing(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="lab-federation",
                remote_units=("unit-remote-01",),
                remote_unit_attachments=(
                    {
                        "node_id": "unit-remote-01",
                        "relay_path": ["gateway-b-01"],
                        "network_transports": ["ethernet", "serial_bridge"],
                    },
                ),
                capabilities=("delegated_execution",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at="2026-05-09T12:30:00Z",
                reachable=True,
            )
        )

        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
            required_transport="wifi",
        )

        self.assertFalse(route.ok)
        self.assertEqual(route.route_kind, "delegated_core")
        self.assertEqual(route.status, "route_rejected")
        self.assertEqual(route.failure_reason, "transport_mismatch")
        self.assertEqual(route.relay_path, ("gateway-b-01",))

    def test_plan_route_rejects_peer_with_trust_scope_mismatch(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="other-scope",
                remote_units=("unit-remote-01",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at="2026-05-09T12:30:00Z",
                reachable=True,
            )
        )

        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        self.assertFalse(route.ok)
        self.assertEqual(route.status, "route_rejected")
        self.assertEqual(route.failure_reason, "trust_scope_mismatch")

    def test_plan_route_marks_stale_peer_as_stale_route(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="lab-federation",
                remote_units=("unit-remote-01",),
                advertised_at="2026-05-09T10:00:00Z",
                expires_at="2026-05-09T11:59:59Z",
                reachable=True,
            )
        )

        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        self.assertFalse(route.ok)
        self.assertEqual(route.status, "stale_route")
        self.assertEqual(route.failure_reason, "peer_advertisement_stale")

    def test_plan_route_marks_unreachable_fresh_peer_as_route_failed(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="lab-federation",
                remote_units=("unit-remote-01",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at="2026-05-09T12:30:00Z",
                reachable=False,
            )
        )

        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        self.assertFalse(route.ok)
        self.assertEqual(route.status, "route_failed")
        self.assertEqual(route.failure_reason, "peer_unreachable")

    def test_build_delegated_execution_proposal_requires_ready_delegated_route(self) -> None:
        registry = FederationTopologyRegistry(local_core_id="core-a")
        registry.register_peer(
            CorePeerDescriptor(
                core_id="core-b",
                trust_scope="lab-federation",
                remote_units=("unit-remote-01",),
                capabilities=("delegated_execution",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at="2026-05-09T12:30:00Z",
                reachable=True,
            )
        )
        route = registry.plan_route(
            "unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        proposal = build_delegated_execution_proposal(
            delegation_id="fed-del-01",
            route=route,
            resource="neuro/unit-remote-01/query/device",
            policy_scope="read_only",
            timeout_ms=5000,
            cleanup_required=False,
            audit_correlation_id="audit-corr-01",
        )

        payload = proposal.to_dict()
        self.assertEqual(payload["schema_version"], DELEGATED_EXECUTION_SCHEMA_VERSION)
        self.assertEqual(payload["target_core"], "core-b")
        self.assertEqual(payload["route_kind"], "delegated_core")

    def test_unit_capability_descriptor_serializes_transport_and_budget_fields(self) -> None:
        descriptor = UnitCapabilityDescriptor(
            node_id="unit-local-01",
            architecture="xtensa",
            abi="zephyr-llext-v1",
            board_family="esp32s3-class",
            llext_supported=True,
            storage_class="removable_or_flash",
            network_transports=("wifi", "serial_bridge"),
            relay_capable=False,
            signing_enforced=False,
            resource_budget={"heap_free_bytes": 8192, "app_slot_bytes": 65536},
        )

        payload = descriptor.to_dict()

        self.assertEqual(payload["schema_version"], UNIT_CAPABILITY_SCHEMA_VERSION)
        self.assertEqual(payload["network_transports"], ["wifi", "serial_bridge"])
        self.assertEqual(payload["resource_budget"]["heap_free_bytes"], 8192)

    def test_federation_route_smoke_emits_delegated_execution_payload_for_ready_peer(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
        )

        self.assertEqual(payload["schema_version"], FEDERATION_ROUTE_SMOKE_SCHEMA_VERSION)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["route_decision"]["route_kind"], "delegated_core")
        self.assertIsNotNone(payload["delegated_execution"])
        self.assertTrue(payload["closure_gates"]["delegated_execution_contract_ready"])

    def test_federation_route_smoke_emits_peer_relay_attachment_metadata(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-remote-01",
            now="2026-05-10T12:00:00Z",
            required_trust_scope="lab-federation",
            peer_expires_at="2026-05-10T12:30:00Z",
            peer_relay_via=("gateway-b-01",),
            peer_network_transports=("ethernet", "serial_bridge"),
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["route_decision"]["route_kind"], "delegated_core")
        self.assertEqual(payload["route_decision"]["relay_path"], ["gateway-b-01"])
        self.assertEqual(payload["evidence_summary"]["relay_path"], ["gateway-b-01"])
        self.assertEqual(
            payload["evidence_summary"]["supported_transports"],
            ["ethernet", "serial_bridge"],
        )

    def test_federation_route_smoke_rejects_peer_transport_mismatch(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-remote-01",
            now="2026-05-10T12:00:00Z",
            required_trust_scope="lab-federation",
            required_transport="wifi",
            peer_expires_at="2026-05-10T12:30:00Z",
            peer_relay_via=("gateway-b-01",),
            peer_network_transports=("ethernet", "serial_bridge"),
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "route_rejected")
        self.assertEqual(payload["reason"], "transport_mismatch")
        self.assertEqual(payload["route_decision"]["relay_path"], ["gateway-b-01"])

    def test_federation_route_smoke_reports_stale_route_without_delegation_payload(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-remote-01",
            now="2026-05-09T12:00:00Z",
            required_trust_scope="lab-federation",
            peer_expires_at="2026-05-09T11:59:59Z",
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "stale_route")
        self.assertIsNone(payload["delegated_execution"])
        self.assertFalse(payload["closure_gates"]["delegated_execution_contract_ready"])

    def test_federation_route_smoke_emits_relay_attachment_metadata_for_valid_local_relay(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-relay-01",
            now="2026-05-09T12:00:00Z",
            local_unit=True,
            relay_via=("gateway-01",),
            network_transports=("ethernet", "serial_bridge"),
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["route_decision"]["route_kind"], "relay")
        self.assertEqual(payload["route_decision"]["relay_path"], ["gateway-01"])
        self.assertEqual(payload["evidence_summary"]["relay_path"], ["gateway-01"])
        self.assertEqual(
            payload["evidence_summary"]["supported_transports"],
            ["ethernet", "serial_bridge"],
        )

    def test_federation_route_smoke_rejects_local_relay_capability_mismatch(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-relay-01",
            now="2026-05-09T12:00:00Z",
            local_unit=True,
            relay_via=("gateway-01",),
            relay_capable=False,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "route_rejected")
        self.assertEqual(payload["reason"], "relay_capability_mismatch")
        self.assertEqual(payload["route_decision"]["route_kind"], "relay")
        self.assertEqual(payload["route_decision"]["relay_path"], ["gateway-01"])

    def test_federation_route_smoke_rejects_local_relay_transport_mismatch(self) -> None:
        payload = federation_route_smoke(
            target_node="unit-relay-01",
            now="2026-05-09T12:00:00Z",
            local_unit=True,
            relay_via=("gateway-01",),
            network_transports=("ethernet", "serial_bridge"),
            required_transport="wifi",
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "route_rejected")
        self.assertEqual(payload["reason"], "transport_mismatch")
        self.assertEqual(payload["route_decision"]["route_kind"], "relay")
        self.assertEqual(payload["evidence_summary"]["required_transport"], "wifi")


if __name__ == "__main__":
    unittest.main()