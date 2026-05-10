# NeuroLink Unit LLD

## 1. Overview

This document is the formal low-level design for the NeuroLink Unit runtime and control plane.

It replaces the mixed old LLD as the authoritative source for:

1. Unit-side architecture layers.
2. zenoh resource model and request metadata.
3. Unit state machines.
4. Unit data structures.
5. Runtime hardening and rollback behavior.
6. Unit-test requirements and production traceability.

The design is grounded in the already validated Unit baseline:

1. `prepare -> verify -> activate -> query apps`
2. `app-stop -> app-start`
3. LLEXT-based runtime lifecycle management
4. lease-aware control and update flows

## 2. Scope and Constraints

### 2.1 Fixed Constraints

1. Unit implementation language is C on Zephyr RTOS.
2. Unit C and headers must follow Linux Kernel code style.
3. Dynamic application lifecycle is based on Zephyr LLEXT and the existing `app_runtime_llext` framework.
4. Core-facing messaging is carried through zenoh/zenoh-pico semantics.
5. Phase 1 production scope targets direct attach and minimum multi-Core visibility.

### 2.2 Runtime Baseline

The validated baseline already proves:

1. `prepare` with Zenoh chunk transfer.
2. `verify` on SD-backed artifacts.
3. `activate` using `load + start`.
4. `app-stop` and `app-start` on an activated app.
5. lease acquisition and release.

This LLD formalizes that baseline and extends it into production-hardening rules.

## 3. Internal Architecture

### 3.1 Layered View

The Unit runtime is divided into the following layers:

1. `Board Support and Device Layer`
  - storage, Wi-Fi/Ethernet, GPIO, sensors, board diagnostics.
2. `Network Adaptation Layer`
  - chip-specific network driver binding, physical-link adaptation, link readiness checks, address acquisition, transport prerequisites.
3. `Comm and Session Layer`
  - zenoh session setup, reconnect, queryable registration, publishers.
4. `Control Plane Layer`
  - command, query, event, and update dispatch.
5. `Governance Layer`
  - lease manager, policy hooks, request validation.
6. `App Integration Layer`
  - app-exposed command registration, callback dispatch, app-to-framework event/callback bridge.
7. `Runtime Layer`
  - app runtime, manifest parsing, exception model, budget checks.
8. `State Layer`
  - state registry, versioning, event payload generation.
9. `Gateway Layer`
  - relay registry, route cache, forwarded metadata.

Layering rules:

1. `Network Adaptation Layer` is the prerequisite for `Comm and Session Layer`.
2. `Comm and Session Layer` must not attempt zenoh session establishment until network readiness state is satisfied.
3. `App Integration Layer` is the only framework-owned ingress path by which a loaded App may expose externally callable capabilities.
4. `Runtime Layer` owns lifecycle and symbol safety; it does not own network attachment policy.
5. `State Layer` is the single source of truth for externally visible Unit state.

### 3.2 Module Inventory

Recommended internal module map:

1. `comm_session_manager`
2. `network_adapter_manager`
3. `attachment_manager`
4. `command_service`
5. `query_service`
6. `event_publisher`
7. `update_service`
8. `lease_manager`
9. `app_command_registry`
10. `app_callback_bridge`
11. `state_registry`
12. `app_lifecycle_service`
13. `artifact_store`
14. `gateway_forwarder`
15. `diag_health_service`

### 3.3 Existing Code Anchors

1. `app_runtime_llext/include/app_runtime.h`
2. `app_runtime_llext/src/app_runtime.c`
3. `app_runtime_llext/include/app_runtime_manifest.h`
4. `app_runtime_llext/include/app_runtime_exception.h`
5. `NeuroLink/demo_unit/src/neuro_demo.c`

These are the primary seeds for production implementation and must be evolved rather than bypassed.

### 3.4 Network Adaptation Model

The network subsystem must be explicitly split away from the Unit control plane and runtime core.

Responsibilities:

1. bind chip-specific network drivers
2. abstract physical attachment types such as Wi-Fi, Ethernet, Thread, Serial bridge, or vendor-specific modem paths
3. evaluate link readiness before zenoh session bring-up
4. acquire or validate local addressing and transport prerequisites
5. publish network capability and readiness state into the state registry

Design rules:

1. transport-specific code must not be embedded into `command_service`, `update_service`, or `app_lifecycle_service`
2. per-board and per-chip implementations belong in adapter modules injected through the board/runtime port layer
3. the network adapter must expose a uniform readiness contract regardless of whether the underlying medium is Wi-Fi, Ethernet, or another supported transport

### 3.5 App Exposure Model

Loaded Apps are allowed to expose framework-governed outward capabilities through two controlled mechanisms:

1. `App Commands`
  - externally invocable operations routed through the Unit command plane
2. `App Callbacks`
  - framework callbacks for lifecycle, command handling, state notification, and optional asynchronous event emission

Hard boundaries:

1. Apps do not publish arbitrary queryables or publishers directly into the network fabric
2. Apps register descriptors with the framework, and the framework owns external exposure, metadata validation, lease checks, and auditing
3. an App command is not reachable until registration succeeds and the App is in an externally callable state

## 4. Communication Model

### 4.1 Messaging Planes

Unit communication uses four planes:

1. `cmd`
  - side-effecting operations.
2. `query`
  - snapshots and capability reads.
3. `event`
  - asynchronous state and fault publication.
4. `update`
  - staged deployment operations.

### 4.2 Resource Naming

Canonical prefix:

`neuro/<node-id>/<plane>/...`

Required resources:

1. `neuro/<node-id>/cmd/lease/acquire`
2. `neuro/<node-id>/cmd/lease/release`
3. `neuro/<node-id>/cmd/app/<app-id>/<command-name>`
4. `neuro/<node-id>/cmd/app/<app-id>/start`
5. `neuro/<node-id>/cmd/app/<app-id>/stop`
6. `neuro/<node-id>/query/device`
7. `neuro/<node-id>/query/apps`
8. `neuro/<node-id>/query/leases`
9. `neuro/<node-id>/event/state`
10. `neuro/<node-id>/event/update`
11. `neuro/<node-id>/event/lease/<lease-id>`
12. `neuro/<node-id>/update/app/<app-id>/prepare`
13. `neuro/<node-id>/update/app/<app-id>/verify`
14. `neuro/<node-id>/update/app/<app-id>/activate`
15. `neuro/<node-id>/update/app/<app-id>/rollback`

### 4.3 Request Metadata Contract

All command, query, and update requests must carry a common metadata prefix:

```json
{
  "request_id": "req-20260408-0001",
  "source_core": "core-a",
  "source_agent": "rational",
  "target_node": "unit-01",
  "timeout_ms": 5000
}
```

Write operations must also carry:

```json
{
  "lease_id": "lease-01",
  "priority": 60,
  "idempotency_key": "idem-01"
}
```

Forwarded operations must also carry:

```json
{
  "forwarded": true,
  "relay_path": ["gateway-01"]
}
```

### 4.4 App Command Exposure Contract

App-exposed commands must be projected into the command plane under a governed namespace:

1. `neuro/<node-id>/cmd/app/<app-id>/<command-name>`

Rules:

1. command exposure is opt-in through framework registration
2. command-name must be stable, ASCII-only, and bounded in length
3. every app command must declare whether it is lease-protected, idempotent, and externally visible
4. the framework may reject registration if the command collides with a reserved name or violates policy

Minimum request shape:

```json
{
  "request_id": "app-cmd-001",
  "source_core": "core-a",
  "source_agent": "rational",
  "lease_id": "lease-app-01",
  "args": {
    "mode": "sample"
  }
}
```

Minimum reply shape:

```json
{
  "request_id": "app-cmd-001",
  "ok": true,
  "code": 0,
  "message": "success",
  "data": {}
}
```

### 4.5 App Callback Exposure Contract

The framework-owned callback bridge must support the following callback classes:

1. lifecycle callbacks
  - init, start, suspend, resume, stop, deinit
2. command callback
  - handles an externally routed app command
3. state callback
  - allows the framework to request app-owned state fragments for query composition
4. notify callback
  - allows the app to ask the framework to emit an event or mark state dirty
  - release-1.1.1 baseline uses framework-owned event topics under `neuro/<node>/event/app/<app-id>/<event-name>` for app-originated notifications

Rules:

1. callbacks are discovered or registered through the runtime-controlled ABI surface
2. callback invocation always goes through runtime symbol validation and exception mapping
3. callback failures must never corrupt the framework state registry
4. app-originated notify/event emission must stay framework-mediated; Apps do not publish directly to transport-specific APIs

## 5. State Machines

### 5.1 Network Access Lifecycle

States:

1. `DOWN`
2. `ADAPTER_READY`
3. `LINK_READY`
4. `ADDRESS_READY`
5. `TRANSPORT_READY`
6. `NETWORK_READY`
7. `DEGRADED`
8. `FAILED`

Transitions:

1. `DOWN -> ADAPTER_READY`
  - Trigger: chip-specific adapter initialized.
2. `ADAPTER_READY -> LINK_READY`
  - Trigger: physical link ready or association succeeds.
3. `LINK_READY -> ADDRESS_READY`
  - Trigger: address acquisition or equivalent local transport identity succeeds.
4. `ADDRESS_READY -> TRANSPORT_READY`
  - Trigger: transport prerequisites for zenoh are satisfied.
5. `TRANSPORT_READY -> NETWORK_READY`
  - Trigger: readiness contract published to session manager.
6. `NETWORK_READY -> DEGRADED`
  - Trigger: link drop, IP loss, or adapter instability.
7. `DEGRADED -> NETWORK_READY`
  - Trigger: readiness restored.
8. `ADAPTER_READY|LINK_READY|ADDRESS_READY|TRANSPORT_READY|DEGRADED -> FAILED`
  - Trigger: unrecoverable adapter or medium error.

Rules:

1. `Comm and Session Layer` may only enter session connect when state is `NETWORK_READY`.
2. `prepare`, remote `query`, and remote `cmd` surfaces are unavailable unless both network lifecycle and session lifecycle are ready.
3. local shell or board diagnostics may still operate while network is below `NETWORK_READY`.

UT anchor: `UT-UNIT-NET-*`

### 5.2 zenoh Session Lifecycle

States:

1. `UNINITIALIZED`
2. `CONFIGURED`
3. `CONNECTING`
4. `CONNECTED`
5. `DEGRADED`
6. `RECONNECTING`
7. `STOPPED`

Transitions:

1. `UNINITIALIZED -> CONFIGURED`
  - Trigger: configuration loaded.
2. `CONFIGURED -> CONNECTING`
  - Trigger: start request.
3. `CONNECTING -> CONNECTED`
  - Trigger: session established and queryables registered.
4. `CONNECTED -> DEGRADED`
  - Trigger: transport instability, partial publisher failure, or repeated timeout.
5. `DEGRADED -> RECONNECTING`
  - Trigger: reconnect threshold reached.
6. `RECONNECTING -> CONNECTED`
  - Trigger: session restored.
7. `CONNECTED|DEGRADED|RECONNECTING -> STOPPED`
  - Trigger: shutdown.

UT anchor: `UT-UNIT-SESSION-*`

### 5.3 Attachment Lifecycle

States:

1. `DETACHED`
2. `DIRECT_ATTACHED`
3. `MULTI_CORE_VISIBLE`
4. `RELAYED_ATTACHED`
5. `FEDERATED_VISIBLE`
6. `ATTACHMENT_DEGRADED`

Rules:

1. Attachment mode is observable state and must be queryable.
2. A degraded relay path must not be reported as a direct attach.

UT anchor: `UT-UNIT-ATTACH-*`

### 5.4 Lease Lifecycle

States:

1. `UNOWNED`
2. `PENDING`
3. `ACTIVE`
4. `RENEWING`
5. `EXPIRED`
6. `RELEASED`
7. `REVOKED`

Transitions:

1. `UNOWNED -> PENDING`
  - Trigger: acquire request accepted for evaluation.
2. `PENDING -> ACTIVE`
  - Trigger: arbitration grants lease.
3. `ACTIVE -> RENEWING`
  - Trigger: renew request accepted.
4. `RENEWING -> ACTIVE`
  - Trigger: renewed successfully.
5. `ACTIVE -> EXPIRED`
  - Trigger: TTL reached.
6. `ACTIVE -> RELEASED`
  - Trigger: holder releases lease.
7. `ACTIVE -> REVOKED`
  - Trigger: administrative or emergency preemption.

UT anchor: `UT-UNIT-LEASE-*`

### 5.5 App Runtime Lifecycle

States:

1. `UNLOADED`
2. `LOADED`
3. `INITIALIZED`
4. `RUNNING`
5. `SUSPENDED`
6. `FAILED`

Rules:

1. `load` transitions `UNLOADED -> LOADED -> INITIALIZED` when init succeeds.
2. `start` transitions `INITIALIZED|SUSPENDED -> RUNNING`.
3. `stop` transitions `RUNNING -> INITIALIZED`.
4. `unload` transitions any loaded state to `UNLOADED` after stop and deinit.

UT anchor: `UT-UNIT-APP-*`

### 5.6 App Command Registration Lifecycle

States:

1. `UNREGISTERED`
2. `REGISTERING`
3. `REGISTERED`
4. `ENABLED`
5. `DISABLED`
6. `FAILED`
7. `REMOVED`

Transitions:

1. `UNREGISTERED -> REGISTERING`
  - Trigger: App manifest or callback table requests outward command exposure.
2. `REGISTERING -> REGISTERED`
  - Trigger: descriptor validation succeeds.
3. `REGISTERED -> ENABLED`
  - Trigger: App reaches externally callable runtime state.
4. `ENABLED -> DISABLED`
  - Trigger: App stop, suspend, policy block, or dependency loss.
5. `DISABLED -> ENABLED`
  - Trigger: runtime state restored and policy allows exposure.
6. `REGISTERING|REGISTERED|ENABLED|DISABLED -> FAILED`
  - Trigger: collision, invalid descriptor, or callback bind failure.
7. `REGISTERED|ENABLED|DISABLED|FAILED -> REMOVED`
  - Trigger: App unload or registration teardown.

Rules:

1. registered commands do not become callable before `ENABLED`
2. a failed registration must expose structured reason for audit and debugging
3. unload must remove all registered commands atomically before runtime object release

UT anchor: `UT-UNIT-APPCMD-*`

### 5.7 App Command Dispatch Lifecycle

States:

1. `RECEIVED`
2. `VALIDATING`
3. `AUTHORIZED`
4. `DISPATCHING`
5. `CALLBACK_RUNNING`
6. `REPLYING`
7. `SUCCEEDED`
8. `FAILED`

Rules:

1. app command dispatch must perform the same request metadata and lease validation as built-in framework commands when the command is marked lease-protected
2. callback execution must be wrapped by runtime exception capture
3. the framework owns reply serialization and version bumping behavior

UT anchor: `UT-UNIT-APPDISPATCH-*`

### 5.8 Update Transaction Lifecycle

States:

1. `NONE`
2. `PREPARE_REQUESTED`
3. `PREPARING`
4. `PREPARED`
5. `VERIFYING`
6. `VERIFIED`
7. `ACTIVATING`
8. `ACTIVE`
9. `ROLLBACK_PENDING`
10. `ROLLING_BACK`
11. `ROLLED_BACK`
12. `FAILED`

Rules:

1. `verify` is illegal before `PREPARED`.
2. `activate` is illegal before `VERIFIED`.
3. `rollback` must preserve reason and previous stable reference.

UT anchor: `UT-UNIT-UPDATE-*`

### 5.9 Artifact Download Lifecycle

States:

1. `IDLE`
2. `OPENING`
3. `FETCHING`
4. `FLUSHING`
5. `COMPLETED`
6. `FAILED`
7. `CLEANUP`

Rules:

1. Partial files must be either resumable or cleaned up deterministically.
2. Chunk counters must be observable in debug logs.

UT anchor: `UT-UNIT-ARTIFACT-*`

### 5.10 Gateway Child Registration Lifecycle

States:

1. `UNKNOWN`
2. `DISCOVERED`
3. `REACHABLE`
4. `STALE`
5. `UNREACHABLE`
6. `REMOVED`

Rules:

1. A child Unit record must expose attachment metadata without assuming the
  gateway uses Wi-Fi, Ethernet, Thread, serial bridge, or any single physical
  transport.
2. A relay route must carry forwarded metadata, source Core, target child,
  route freshness, and trust scope so the Core can distinguish direct, relayed,
  stale, and no-route outcomes.
3. Gateway forwarding must not grant new authority by reachability alone; lease,
  policy, and source metadata checks still apply at the controlling Core and at
  the target Unit surface where applicable.
4. Gateway route cache records must expire deterministically and emit stale-child
  evidence instead of silently forwarding through unknown routes.

UT anchor: `UT-UNIT-GW-*`

### 5.11 Reboot Recovery Lifecycle

States:

1. `BOOTING`
2. `STATE_RESTORE`
3. `LEASE_CLEANUP`
4. `APP_RECONCILE`
5. `READY`
6. `RECOVERY_FAILED`

Rules:

1. In-memory leases must be treated as expired after reboot unless a persistent lease store is later introduced.
2. Update state must reconcile staged artifact presence versus runtime state.

UT anchor: `UT-UNIT-RECOVERY-*`

### 5.12 Update/Artifact/Recovery Persistence Contract (UNIT-LLD-UPDATE-MANAGER, UNIT-LLD-ARTIFACT-STORE, UNIT-LLD-RECOVERY-SEED)

This section binds the lifecycle model to the runtime modules already used by the Unit baseline.

Module ownership:

1. `neuro_update_manager`
  - owns update phase transitions, stable reference tracking, rollback reason retention, and reboot reconcile decision input.
2. `neuro_artifact_store`
  - owns staged and active artifact metadata, staged-path tracking, and activation/rollback path handoff.
3. `neuro_recovery_seed_store`
  - owns durable snapshot encode/decode (`magic/version/crc`) and boot-time state import/export.

Contract rules:

1. `prepare`, `verify`, `activate`, and `rollback` must checkpoint update state through `neuro_update_manager` before terminal reply.
2. artifact path decisions used by update transitions must come from runtime config and artifact-store records, not hardcoded framework constants.
3. boot reconcile must hydrate update/artifact in-memory state from recovery seed snapshot before declaring `READY`.
4. unsupported recovery-seed versions must be treated as deterministic incompatibility (`-ENOTSUP`) rather than generic corruption.
5. recovery mismatch policy remains conservative in this baseline: unresolved runtime/artifact inconsistency transitions to `FAILED` and emits recovery error event.

UT anchors:

1. `UT-UNIT-UPDATE-*`
2. `UT-UNIT-ARTIFACT-*`
3. `UT-UNIT-RECOVERY-*`

## 6. Data Structures

### 6.1 Command Request

```json
{
  "request_id": "cmd-001",
  "source_core": "core-a",
  "source_agent": "affective",
  "lease_id": "lease-app-cmd-001",
  "args": {
    "mode": "sample"
  }
}
```

### 6.2 Command Reply

```json
{
  "request_id": "cmd-001",
  "ok": true,
  "code": 0,
  "message": "success",
  "version": 43,
  "data": {}
}
```

### 6.3 Query Reply

```json
{
  "ok": true,
  "node_id": "unit-01",
  "version": 43,
  "device": {
    "fw_version": "1.2.0",
    "overall_health": "ok"
  }
}
```

### 6.4 Event Payload

```json
{
  "event_id": "evt-01",
  "node_id": "unit-01",
  "kind": "update",
  "target": "neuro_demo_app",
  "state": "ACTIVE",
  "version": 44,
  "timestamp": 1712188800
}
```

### 6.5 App Command Descriptor

```c
struct neuro_app_command_desc {
  char app_id[32];
  char command_name[32];
  uint8_t visibility;
  bool lease_required;
  bool idempotent;
  uint32_t timeout_ms;
  uint8_t state;
};
```

### 6.6 App Callback Table

```c
struct neuro_app_callback_ops {
  int (*on_command)(const char *command_name, const char *request_json,
       char *reply_buf, size_t reply_buf_len);
  int (*on_state_pull)(char *state_buf, size_t state_buf_len);
  int (*on_notify)(uint32_t notify_reason, const void *payload,
       size_t payload_len);
};
```

### 6.7 Lease Table Entry

```c
struct neuro_lease_record {
	char lease_id[32];
	char resource[96];
	char holder_core[32];
	char holder_agent[16];
	uint32_t priority;
	int64_t expires_at_ms;
	uint8_t state;
	uint8_t conflict_policy;
};
```

### 6.8 State Registry Record

```c
struct neuro_state_registry {
	char node_id[32];
	uint64_t version;
	uint8_t attach_mode;
	uint8_t session_state;
	uint8_t overall_health;
	struct neuro_app_record apps[CONFIG_NEURO_MAX_APPS];
	struct neuro_lease_record leases[CONFIG_NEURO_MAX_LEASES];
  uint8_t network_access_state;
	struct neuro_update_record update;
};
```

### 6.9 Network Adapter Record

```c
struct neuro_network_adapter_record {
  char adapter_name[32];
  char medium[16];
  uint8_t state;
  bool link_up;
  bool address_ready;
  bool transport_ready;
};
```

### 6.10 App Runtime Record

```c
struct neuro_app_record {
	char app_id[32];
	char path[128];
	uint8_t state;
	bool manifest_present;
	bool auto_suspended;
	int priority;
	int last_exception;
  struct neuro_app_command_desc commands[CONFIG_NEURO_MAX_APP_COMMANDS];
  struct neuro_app_callback_ops callbacks;
	struct app_runtime_manifest manifest;
};
```

### 6.11 Artifact Metadata

```c
struct neuro_artifact_meta {
	char app_id[32];
	char transport[16];
	char artifact_key[128];
	char path[128];
	uint32_t size;
	uint32_t chunk_size;
	uint32_t chunks_received;
	uint8_t state;
};
```

### 6.12 Update Transaction Record

```c
struct neuro_update_record {
	char deployment_id[32];
	char app_id[32];
	uint8_t phase;
	bool verify_ok;
	bool rollback_available;
	char previous_stable_path[128];
	char staged_path[128];
	uint64_t updated_at_ms;
};
```

### 6.13 Memory Snapshot Record

```c
struct neuro_memory_snapshot {
	uint32_t heap_free_bytes;
	uint32_t heap_allocated_bytes;
	uint32_t heap_max_allocated_bytes;
	uint32_t current_stack_unused;
	uint32_t neuro_connect_stack_unused;
};
```

### 6.14 Release 1.2.6 Hardware Capability Descriptor

```c
struct neuro_unit_capability_desc {
  char node_id[32];
  char architecture[24];
  char abi[32];
  char board_family[32];
  bool llext_supported;
  char storage_class[24];
  uint32_t network_transport_mask;
  bool relay_capable;
  bool signing_enforced;
  uint32_t heap_free_bytes;
  uint32_t app_slot_bytes;
  uint32_t stack_margin_bytes;
};
```

Rules:

1. Capability fields must describe compatibility classes, not a single lab
   board identity.
2. Board-specific discovery belongs in the port provider or board support layer;
   shared query serialization must consume the normalized descriptor.
3. Artifact verification must reject incompatible architecture, ABI, board
   family, LLEXT support, storage class, signing state, or resource budget before
   activation.

### 6.15 Release 1.2.6 Gateway Route Record

```c
struct neuro_gateway_route_record {
  char child_node_id[32];
  char relay_node_id[32];
  uint32_t transport_mask;
  uint8_t state;
  uint8_t trust_scope;
  int64_t last_seen_ms;
  int64_t expires_at_ms;
};
```

Rules:

1. The route record is transport-neutral and must not encode Wi-Fi-only state.
2. Stale or incompatible routes must be returned as explicit route failure
   evidence instead of being hidden behind generic timeout behavior.
3. Forwarded command, query, update, and event metadata must preserve the relay
   path for Core audit correlation.

### 6.14 Gateway Route Record

```c
struct neuro_gateway_route {
	char child_node_id[32];
	char upstream_path[96];
	uint8_t state;
	uint64_t last_seen_ms;
};
```

### 6.15 Recovery Seed Snapshot Record

```c
struct neuro_recovery_seed_snapshot {
  uint32_t magic;
  uint16_t version;
  uint16_t header_size;
  uint32_t payload_size;
  uint32_t crc32;
  uint32_t app_count;
};
```

Notes:

1. Snapshot payload is versioned and decode is dispatched by supported-version window.
2. Recovery persistence path is board-provider configurable through runtime command configuration.
3. The framework default path is generic and must not embed board-specific mount naming.

## 7. Governance and Arbitration

### 7.1 Lease Scope

Leases are granted at resource granularity, not whole-node granularity.

Typical resources:

1. `app/<app-id>/command/<command-name>`
2. `app/<app-id>/control`
3. `update/app/<app-id>/activate`

### 7.2 Network Prerequisite Rules

Before a Unit is considered remotely reachable, the following must be true:

1. a network adapter is initialized and selected
2. the physical link or equivalent medium is up
3. local addressing or transport identity is ready
4. the comm/session manager has consumed the network readiness signal

This makes network readiness a formal precondition, not an incidental side effect of board bring-up.

### 7.3 Arbitration Order

Conflicts are resolved in the following order:

1. explicit deny policy on current holder
2. higher priority requester
3. emergency policy override
4. same-priority first-come-first-served

### 7.4 Enforcement Rules

Before any write operation, the Unit must verify:

1. request metadata completeness
2. policy validity
3. lease validity
4. runtime state compatibility
5. resource budget compatibility for update operations

Before any app-exposed command callback is invoked, the Unit must also verify:

1. command descriptor is in `ENABLED` state
2. callback table is bound and validated
3. app runtime state allows external callback execution

## 8. Error Model

Unit replies must always include:

1. `ok`
2. `code`
3. `message`
4. `details`

Error families:

1. `1000+`
  - invalid arguments
2. `1100+`
  - not found
3. `1200+`
  - execution failure
4. `1300+`
  - resource exhaustion
5. `1400+`
  - policy or lease failure
6. `1500+`
  - state conflict
7. `1600+`
  - network or relay failure
8. `1700+`
  - internal corruption or invalid runtime symbol
9. `1800+`
  - update failure

Production additions to existing runtime exception model:

1. `LEASE_CONFLICT`
2. `LEASE_EXPIRED`
3. `GATEWAY_UNREACHABLE`
4. `MANIFEST_INVALID`
5. `RESOURCE_BUDGET_EXCEEDED`
6. `ROLLBACK_NOT_AVAILABLE`

## 9. Production Hardening Rules

1. `prepare` must never block the query callback thread with nested blocking fetch calls.
2. `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE` must remain explicitly sized for async prepare flow.
3. callback addresses obtained from LLEXT symbol resolution must be guarded before invocation.
4. manifest and dependency checks must execute before `activate` enters runtime start.
5. rollback semantics must be defined before update is marked production-complete.
6. partial downloads must not be treated as verified artifacts.

### 9.1 Release 1.2.7 Multi-Hardware And Real-Scenario Contracts

Release-1.2.7 closes the remaining Unit-side HLD development work before
release-2.0.0 stabilization. Unit contracts must support capability-class
acceptance and real Core/Unit scenario validation without becoming tied to the
current validation board.

Capability classes:

1. `EXTENSIBLE_UNIT`
  - supports dynamic LLEXT app lifecycle and full artifact admission.
2. `RESTRICTED_UNIT`
  - does not support full dynamic LLEXT or lacks enough resources; exposes
    explicit degraded deploy, update, query, and event outcomes.
3. `RELAY_CAPABLE_UNIT`
  - can preserve relay path metadata and report route health for child Units.
4. `FEDERATED_ACCESS_UNIT`
  - can be accessed through policy-bounded Core federation.
5. `STORAGE_CONSTRAINED_UNIT`
  - requires storage and staging admission limits before load or activation.
6. `SIGNING_REQUIRED_UNIT`
  - rejects artifacts that do not satisfy the target signing policy.

Rules:

1. Board providers may map concrete boards into capability classes, but shared
   Unit serialization and Core-facing contracts must expose normalized
   capability fields rather than board-specific assumptions.
2. Restricted Unit behavior must be explicit. Unsupported dynamic app actions
   return compatibility decisions, not generic runtime failures.
3. Resource budgets must include heap, stack, staging, app-slot, and relevant
   transport or relay buffers. Unsafe artifacts must be rejected before load or
   activation.
4. Signing and provenance decisions must include artifact identity, source
   manifest identity, build provenance, signing state, target policy, and
   rejection reason when applicable.
5. Relay and gateway metadata must remain transport-neutral and preserve route
   path evidence for Core audit correlation.
6. Real-scene validation must exercise query, event, prepare, verify, activate,
   rollback, relay/federation route evidence, and restart recovery across the
   representative capability classes selected for release-1.2.7.

UT anchors: `UT-UNIT-HLD127-*`, `UT-UNIT-HWCAP-*`, `UT-UNIT-BUDGET-*`,
`UT-UNIT-GW-*`, `UT-UNIT-E2E-*`

## 10. Unit-Test Design

### 10.1 Test Families

1. `UT-UNIT-SESSION-*`
  - session init, reconnect, degraded transitions.
2. `UT-UNIT-NET-*`
  - adapter init, link-ready gating, address-ready gating, transport prerequisite gating.
3. `UT-UNIT-LEASE-*`
  - acquire, renew, release, expire, conflict arbitration.
4. `UT-UNIT-APP-*`
  - load, start, suspend, resume, stop, unload, invalid transition rejection.
5. `UT-UNIT-APPCMD-*`
  - registration, collision rejection, enable/disable transitions.
6. `UT-UNIT-APPDISPATCH-*`
  - callback dispatch, lease-aware routing, callback error mapping.
7. `UT-UNIT-UPDATE-*`
  - prepare, verify, activate, rollback, interrupted transaction recovery.
8. `UT-UNIT-ARTIFACT-*`
  - chunk ordering, partial failure, cleanup, size mismatch.
9. `UT-UNIT-QUERY-*`
  - snapshot formatting, version increment rules, since_version behavior.
10. `UT-UNIT-EVENT-*`
  - event emission on lease, update, and state changes.
11. `UT-UNIT-BUDGET-*`
  - manifest budget enforcement and rejection behavior.
12. `UT-UNIT-GW-*`
  - route cache, relay forwarding metadata, child stale detection.
13. `UT-UNIT-RECOVERY-*`
  - reboot reconciliation, stale lease cleanup, staged artifact recovery.
14. `UT-UNIT-HWCAP-*`
  - capability descriptor normalization, board-provider injection, artifact compatibility rejection.
15. `UT-UNIT-HLD127-*`
  - capability-class mapping, Restricted Unit outcomes, signing/provenance policy, and release-2.0.0 entry readiness.
16. `UT-UNIT-E2E-*`
  - real-scenario query, event, update, rollback, relay, and restart recovery evidence contracts.

### 10.2 Mandatory Traceability Rules

1. Every state machine transition in Section 5 must map to at least one UT.
2. Every externally visible request and reply shape in Section 6 must map to a serializer/parser or contract UT.
3. Every hardening rule in Section 9 must map to one failure-injection test or defensive unit test.

## 11. Initial Implementation Order

1. Split and formalize network adapter interface and readiness contract.
2. Normalize request metadata parsing and validation.
3. Formalize lease manager and arbitration.
4. Add app command registry and callback bridge.
5. Formalize update transaction record and state machine.
6. Add rollback path and rollback state.
7. Add manifest dependency and budget enforcement.
8. Add recovery reconciliation.
9. Add gateway route record and query surface.
10. Add release-1.2.6 capability descriptor and artifact compatibility rejection surface.
11. Add release-1.2.7 capability-class acceptance and Restricted Unit outcomes.
12. Add resource-governance, signing/provenance, and admission policy evidence.
13. Add real Core/Unit scenario evidence hooks for release-1.2.7 acceptance and release-2.0.0 rerun.

## 12. Traceability Prefixes

1. `UNIT-LLD-ARCH-*`
2. `UNIT-LLD-SM-*`
3. `UNIT-LLD-DATA-*`
4. `UNIT-LLD-UT-*`
