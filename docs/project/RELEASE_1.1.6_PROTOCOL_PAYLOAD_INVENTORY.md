# Release 1.1.6 Protocol Payload Inventory

This inventory records the release-1.1.5 JSON-v2 request, reply, and event
payload families that must be represented by CBOR-v2 fixtures before the
release-1.1.6 runtime cutover. It is a guardrail document: the goal is to make
every current wire payload explicit before changing its encoding.

## Runtime Boundary

The release-1.1.6 target keeps Zenoh key expressions stable while replacing the
payload bytes carried over those keys. CLI stdout and script evidence remain
JSON/NDJSON after the CLI decodes board replies and events.

Current runtime payload assumptions:

1. Neuro CLI sends JSON text payloads to Unit query/update/command key
   expressions.
2. Neuro Unit replies with JSON text payloads.
3. Neuro Unit app events publish JSON text payloads.
4. Artifact chunk payloads are already binary and are not part of the JSON to
   CBOR control-plane migration.

## Request Payload Families

| Family | Route | Current JSON fields | Guardrail status |
| --- | --- | --- | --- |
| Query device | `neuro/<node>/query/device` | `request_id`, `source_core`, `source_agent`, `target_node`, `timeout_ms` | CLI `test_handle_query_payload_contract`; Unit metadata validation tests |
| Query apps | `neuro/<node>/query/apps` | common query metadata | covered by common metadata decode and dispatch route guardrails |
| Query leases | `neuro/<node>/query/leases` | common query metadata | covered by common metadata decode and dispatch route guardrails |
| Lease acquire | `neuro/<node>/cmd/lease/acquire` | common write metadata, `priority`, `idempotency_key`, `resource`, `lease_id`, `ttl_ms` | CLI `test_handle_lease_acquire_payload_contract` |
| Lease release | `neuro/<node>/cmd/lease/release` | protected metadata, `lease_id` | CLI `test_handle_lease_release_payload_contract` |
| App control | `neuro/<node>/cmd/app/<app-id>/<action>` | protected metadata, optional `start_args` | parser and service guardrails exist; CBOR fixture still needed |
| App invoke args | `neuro/<node>/cmd/app/<app-id>/<command>` | protected metadata, optional `args` object | CLI `test_handle_app_invoke_payload_contract_with_args_json` |
| App callback config | `neuro/<node>/cmd/app/<app-id>/invoke` | protected metadata, `callback_enabled`, `trigger_every`, `event_name` | CLI `test_payload_builders_match_protocol_contract`; Unit `test_decode_callback_config_json_contract` |
| Update prepare | `neuro/<node>/update/app/<app-id>/prepare` | write metadata, `transport`, `artifact_key`, `size`, `chunk_size` | CLI `test_build_prepare_payload_contract`; Unit prepare reply guardrail |
| Update verify | `neuro/<node>/update/app/<app-id>/verify` | common metadata | CLI `test_handle_update_verify_payload_contract`; Unit verify reply guardrail |
| Update activate | `neuro/<node>/update/app/<app-id>/activate` | protected metadata, optional `start_args` | CLI `test_handle_update_activate_payload_contract`; Unit activate reply guardrail |
| Update rollback | `neuro/<node>/update/app/<app-id>/rollback` | protected metadata, optional `reason` | CLI `test_handle_update_rollback_uses_protected_write_mode`; Unit rollback reply guardrail |
| Artifact chunk request | `neuro/artifact/<node>/<app-id>` | `offset`, `chunk_size` JSON request to host provider | not part of Unit runtime CBOR cutover, but should be revisited when CLI transport helpers become binary-aware |

## Reply Payload Families

| Family | Current JSON fields | Guardrail status |
| --- | --- | --- |
| Error reply | `status`, `request_id`, `node_id`, `status_code`, `message` | Unit codec and response exact JSON tests |
| Lease acquire reply | `status`, `request_id`, `node_id`, `lease_id`, `resource`, `expires_at_ms` | Unit codec and response exact JSON tests |
| Lease release reply | `status`, `request_id`, `node_id`, `lease_id`, `resource` | Unit codec and response exact JSON tests |
| Query device reply | `status`, `request_id`, `node_id`, `board`, `zenoh_mode`, `session_ready`, `network_state`, `ipv4` | Unit codec and response exact JSON tests |
| Query apps reply | `status`, `request_id`, `node_id`, `app_count`, `running_count`, `suspended_count`, `apps[]` with runtime/update/artifact fields | Unit response exact JSON tests |
| Query leases reply | `status`, `request_id`, `node_id`, `leases[]` with lease metadata | Unit response exact JSON tests |
| Update prepare reply | `status`, `request_id`, `node_id`, `app_id`, `path`, `transport` | Unit update service exact JSON test |
| Update verify reply | `status`, `request_id`, `node_id`, `app_id`, `size` | Unit update service exact JSON test |
| Update activate reply | `status`, `request_id`, `node_id`, `app_id`, `path` | Unit update service exact JSON test |
| Update rollback reply | `status`, `request_id`, `node_id`, `app_id`, `reason` | Unit update service exact JSON test |
| App command reply | `echo`, `command`, `invoke_count`, `callback_enabled`, `trigger_every`, `event_name`, `config_changed`, `publish_ret` | Unit codec and event exact JSON tests |
| Zenoh error reply from host artifact provider | `message` | host-provider local error path; not Unit CBOR runtime payload |

## Event Payload Families

| Family | Route | Current JSON fields | Guardrail status |
| --- | --- | --- | --- |
| App callback event | `neuro/<node>/event/app/<app-id>/<event-name>` | `app_id`, `event_name`, `invoke_count`, `start_count` | Unit codec and event exact JSON tests; CLI app-event decode test |
| App custom event | `neuro/<node>/event/app/<app-id>/<event-name>` | app-provided JSON string | route/publish forwarding covered; schema is app-owned |
| Update state event | framework update event route | app id, stage, status, detail as service-published fields | service stage/status guardrails exist; CBOR fixture still needed once event DTO is formalized |
| State snapshot event | framework state event route | state snapshot fields | current tests cover diagnostics/state behavior; CBOR fixture still needed once event DTO is formalized |

## CBOR Fixture Requirements

Before runtime cutover, each control-plane family above needs:

1. A named logical DTO fixture.
2. Expected CBOR bytes or a deterministic hex string.
3. Unit encode and decode tests.
4. Python encode and decode tests.
5. Cross-language fixture equality checks.
6. Negative decode tests for wrong type, missing required fields, oversized
   strings, truncated payloads, and unsupported version or message kind.

## Open Inventory Items

1. App custom events intentionally remain app-owned. The framework can encode
   callback events and known framework events, but arbitrary app event schemas
   need a documented payload policy rather than forced framework DTOs.
2. Update and state framework events need explicit DTO names before CBOR vector
   work starts.
3. Host artifact provider requests are JSON today but are not MCU Unit runtime
   payloads. They should be kept out of the first CBOR-only Unit cutover unless
   the Python transport abstraction makes unifying them cheap and well tested.
4. Error replies from Zenoh host artifact provider are host-local and should be
   classified separately from Unit error replies in CLI diagnostics.