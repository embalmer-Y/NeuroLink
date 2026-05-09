from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


FEDERATION_ROUTE_SCHEMA_VERSION = "1.2.6-federation-route-v1"
UNIT_CAPABILITY_SCHEMA_VERSION = "1.2.6-unit-capability-v1"
DELEGATED_EXECUTION_SCHEMA_VERSION = "1.2.6-delegated-execution-v1"
FEDERATION_ROUTE_SMOKE_SCHEMA_VERSION = "1.2.6-federation-route-smoke-v1"


def _parse_utc(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


@dataclass(frozen=True)
class UnitCapabilityDescriptor:
    node_id: str
    architecture: str = "unknown"
    abi: str = "unknown"
    board_family: str = "unknown"
    llext_supported: bool = False
    storage_class: str = "unknown"
    network_transports: tuple[str, ...] = ()
    relay_capable: bool = False
    signing_enforced: bool = False
    resource_budget: dict[str, int] = field(default_factory=lambda: {})
    relay_path: tuple[str, ...] = ()
    schema_version: str = UNIT_CAPABILITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["network_transports"] = list(self.network_transports)
        data["relay_path"] = list(self.relay_path)
        data["resource_budget"] = dict(self.resource_budget)
        return data


@dataclass(frozen=True)
class CorePeerDescriptor:
    core_id: str
    trust_scope: str
    remote_units: tuple[str, ...] = ()
    remote_unit_attachments: tuple[dict[str, Any], ...] = ()
    capabilities: tuple[str, ...] = ()
    advertised_at: str = "1970-01-01T00:00:00Z"
    expires_at: str = "1970-01-01T00:00:00Z"
    reachable: bool = True

    def is_fresh(self, now: str) -> bool:
        return _parse_utc(self.expires_at) >= _parse_utc(now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["remote_units"] = list(self.remote_units)
        data["remote_unit_attachments"] = [dict(item) for item in self.remote_unit_attachments]
        data["capabilities"] = list(self.capabilities)
        return data

    def attachment_for(self, node_id: str) -> dict[str, Any] | None:
        for attachment in self.remote_unit_attachments:
            if str(attachment.get("node_id") or "") == node_id:
                return dict(attachment)
        return None


@dataclass(frozen=True)
class RouteDecision:
    source_core: str
    target_node: str
    route_kind: str
    status: str
    trust_scope: str
    target_core: str | None = None
    relay_path: tuple[str, ...] = ()
    failure_reason: str = ""
    evidence_refs: tuple[str, ...] = ()
    schema_version: str = FEDERATION_ROUTE_SCHEMA_VERSION

    @property
    def ok(self) -> bool:
        return self.status == "route_ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "source_core": self.source_core,
            "target_node": self.target_node,
            "target_core": self.target_core,
            "route_kind": self.route_kind,
            "status": self.status,
            "trust_scope": self.trust_scope,
            "relay_path": list(self.relay_path),
            "failure_reason": self.failure_reason,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class DelegatedExecutionProposal:
    delegation_id: str
    source_core: str
    target_core: str
    target_node: str
    resource: str
    policy_scope: str
    route_kind: str
    timeout_ms: int
    cleanup_required: bool
    audit_correlation_id: str
    schema_version: str = DELEGATED_EXECUTION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FederationTopologyRegistry:
    def __init__(self, local_core_id: str, local_trust_scope: str = "local") -> None:
        self.local_core_id = local_core_id
        self.local_trust_scope = local_trust_scope
        self._local_units: dict[str, UnitCapabilityDescriptor] = {}
        self._peers: dict[str, CorePeerDescriptor] = {}

    def register_local_unit(self, descriptor: UnitCapabilityDescriptor) -> None:
        self._local_units[descriptor.node_id] = descriptor

    def register_peer(self, peer: CorePeerDescriptor) -> None:
        self._peers[peer.core_id] = peer

    def list_peers(self) -> list[CorePeerDescriptor]:
        return sorted(self._peers.values(), key=lambda item: item.core_id)

    def plan_route(
        self,
        target_node: str,
        now: str,
        required_trust_scope: str | None = None,
        required_transport: str | None = None,
    ) -> RouteDecision:
        local_descriptor = self._local_units.get(target_node)
        if local_descriptor is not None:
            if required_trust_scope and required_trust_scope != self.local_trust_scope:
                return RouteDecision(
                    source_core=self.local_core_id,
                    target_node=target_node,
                    route_kind="local",
                    status="route_rejected",
                    trust_scope=self.local_trust_scope,
                    failure_reason="trust_scope_mismatch",
                    evidence_refs=(target_node,),
                )
            if (
                required_transport
                and required_transport not in local_descriptor.network_transports
            ):
                return RouteDecision(
                    source_core=self.local_core_id,
                    target_node=target_node,
                    route_kind="relay" if local_descriptor.relay_path else "direct",
                    status="route_rejected",
                    trust_scope=self.local_trust_scope,
                    relay_path=local_descriptor.relay_path,
                    failure_reason="transport_mismatch",
                    evidence_refs=(target_node, *local_descriptor.relay_path),
                )
            if local_descriptor.relay_path and not local_descriptor.relay_capable:
                return RouteDecision(
                    source_core=self.local_core_id,
                    target_node=target_node,
                    route_kind="relay",
                    status="route_rejected",
                    trust_scope=self.local_trust_scope,
                    relay_path=local_descriptor.relay_path,
                    failure_reason="relay_capability_mismatch",
                    evidence_refs=(target_node, *local_descriptor.relay_path),
                )
            route_kind = "relay" if local_descriptor.relay_path else "direct"
            return RouteDecision(
                source_core=self.local_core_id,
                target_node=target_node,
                route_kind=route_kind,
                status="route_ready",
                trust_scope=self.local_trust_scope,
                relay_path=local_descriptor.relay_path,
                evidence_refs=(target_node,),
            )

        peers = [
            peer
            for peer in self._peers.values()
            if target_node in peer.remote_units or peer.attachment_for(target_node) is not None
        ]
        if not peers:
            return RouteDecision(
                source_core=self.local_core_id,
                target_node=target_node,
                route_kind="none",
                status="no_route",
                trust_scope=required_trust_scope or "",
                failure_reason="target_node_not_advertised",
            )

        trusted_peers = peers
        if required_trust_scope:
            trusted_peers = [peer for peer in peers if peer.trust_scope == required_trust_scope]
            if not trusted_peers:
                return RouteDecision(
                    source_core=self.local_core_id,
                    target_node=target_node,
                    route_kind="delegated_core",
                    status="route_rejected",
                    trust_scope=required_trust_scope,
                    failure_reason="trust_scope_mismatch",
                    evidence_refs=tuple(sorted(peer.core_id for peer in peers)),
                )

        fresh_peers = [peer for peer in trusted_peers if peer.is_fresh(now)]
        if not fresh_peers:
            return RouteDecision(
                source_core=self.local_core_id,
                target_node=target_node,
                route_kind="delegated_core",
                status="stale_route",
                trust_scope=required_trust_scope or trusted_peers[0].trust_scope,
                failure_reason="peer_advertisement_stale",
                evidence_refs=tuple(sorted(peer.core_id for peer in trusted_peers)),
            )

        reachable_peers = [peer for peer in fresh_peers if peer.reachable]
        if not reachable_peers:
            return RouteDecision(
                source_core=self.local_core_id,
                target_node=target_node,
                route_kind="delegated_core",
                status="route_failed",
                trust_scope=required_trust_scope or fresh_peers[0].trust_scope,
                failure_reason="peer_unreachable",
                evidence_refs=tuple(sorted(peer.core_id for peer in fresh_peers)),
            )

        selected = sorted(reachable_peers, key=lambda item: item.core_id)[0]
        selected_attachment = selected.attachment_for(target_node) or {}
        selected_relay_path = tuple(
            str(item)
            for item in (selected_attachment.get("relay_path") or ())
            if str(item)
        )
        selected_transports = tuple(
            str(item)
            for item in (selected_attachment.get("network_transports") or ())
            if str(item)
        )
        if required_transport and selected_transports and required_transport not in selected_transports:
            return RouteDecision(
                source_core=self.local_core_id,
                target_node=target_node,
                target_core=selected.core_id,
                route_kind="delegated_core",
                status="route_rejected",
                trust_scope=selected.trust_scope,
                relay_path=selected_relay_path,
                failure_reason="transport_mismatch",
                evidence_refs=(selected.core_id, target_node, *selected_relay_path),
            )
        return RouteDecision(
            source_core=self.local_core_id,
            target_node=target_node,
            target_core=selected.core_id,
            route_kind="delegated_core",
            status="route_ready",
            trust_scope=selected.trust_scope,
            relay_path=selected_relay_path,
            evidence_refs=(selected.core_id, target_node, *selected_relay_path),
        )


def build_delegated_execution_proposal(
    delegation_id: str,
    route: RouteDecision,
    resource: str,
    policy_scope: str,
    timeout_ms: int,
    cleanup_required: bool,
    audit_correlation_id: str,
) -> DelegatedExecutionProposal:
    if route.route_kind != "delegated_core" or route.target_core is None or not route.ok:
        raise ValueError("delegated_execution_requires_ready_delegated_core_route")
    return DelegatedExecutionProposal(
        delegation_id=delegation_id,
        source_core=route.source_core,
        target_core=route.target_core,
        target_node=route.target_node,
        resource=resource,
        policy_scope=policy_scope,
        route_kind=route.route_kind,
        timeout_ms=timeout_ms,
        cleanup_required=cleanup_required,
        audit_correlation_id=audit_correlation_id,
    )


def federation_route_smoke(
    *,
    target_node: str,
    now: str,
    required_trust_scope: str = "",
    required_transport: str = "",
    local_unit: bool = False,
    network_transports: tuple[str, ...] = ("wifi", "serial_bridge"),
    relay_via: tuple[str, ...] = (),
    relay_capable: bool | None = None,
    peer_core_id: str = "core-b",
    peer_trust_scope: str = "lab-federation",
    peer_network_transports: tuple[str, ...] = (),
    peer_relay_via: tuple[str, ...] = (),
    peer_expires_at: str = "2026-05-09T12:30:00Z",
    peer_reachable: bool = True,
    include_delegation_proposal: bool = True,
) -> dict[str, Any]:
    registry = FederationTopologyRegistry(local_core_id="core-a")
    if local_unit:
        registry.register_local_unit(
            UnitCapabilityDescriptor(
                node_id=target_node,
                architecture="xtensa",
                abi="zephyr-llext-v1",
                board_family="generic-unit-class",
                llext_supported=True,
                storage_class="removable_or_flash",
                network_transports=network_transports,
                relay_capable=bool(relay_via)
                if relay_capable is None
                else relay_capable,
                relay_path=relay_via,
            )
        )
    else:
        registry.register_peer(
            CorePeerDescriptor(
                core_id=peer_core_id,
                trust_scope=peer_trust_scope,
                remote_units=(target_node,),
                remote_unit_attachments=(
                    {
                        "node_id": target_node,
                        "relay_path": list(peer_relay_via),
                        "network_transports": list(peer_network_transports),
                    },
                )
                if peer_relay_via or peer_network_transports
                else (),
                capabilities=("delegated_execution",),
                advertised_at="2026-05-09T11:00:00Z",
                expires_at=peer_expires_at,
                reachable=peer_reachable,
            )
        )

    route = registry.plan_route(
        target_node,
        now=now,
        required_trust_scope=required_trust_scope or None,
        required_transport=required_transport or None,
    )

    proposal_payload: dict[str, Any] | None = None
    if include_delegation_proposal and route.ok and route.route_kind == "delegated_core":
        proposal_payload = build_delegated_execution_proposal(
            delegation_id="fed-del-smoke-001",
            route=route,
            resource=f"neuro/{target_node}/query/device",
            policy_scope="read_only",
            timeout_ms=5000,
            cleanup_required=False,
            audit_correlation_id="audit-fed-smoke-001",
        ).to_dict()

    return {
        "schema_version": FEDERATION_ROUTE_SMOKE_SCHEMA_VERSION,
        "command": "federation-route-smoke",
        "ok": route.ok,
        "status": route.status,
        "reason": route.failure_reason if not route.ok else "route_ready",
        "route_decision": route.to_dict(),
        "delegated_execution": proposal_payload,
        "closure_gates": {
            "route_decision_recorded": True,
            "route_ready": route.ok,
            "direct_or_relay_route_recorded": route.route_kind in {"direct", "relay"}
            and route.ok,
            "delegated_route_recorded": route.route_kind == "delegated_core",
            "delegated_execution_contract_ready": proposal_payload is not None,
            "trust_scope_checked": bool(required_trust_scope) or route.route_kind in {"direct", "relay"},
        },
        "evidence_summary": {
            "target_node": target_node,
            "route_kind": route.route_kind,
            "target_core": route.target_core,
            "relay_path": list(route.relay_path),
            "trust_scope": route.trust_scope,
            "required_transport": required_transport,
            "supported_transports": list(network_transports)
            if local_unit
            else list(peer_network_transports),
            "failure_reason": route.failure_reason,
        },
    }