# Release 1.1.6 CBOR-v2 Schema

This document defines the first release-1.1.6 CBOR-v2 schema contract. It is a
schema and fixture-structure slice only: runtime Unit and CLI payloads remain
JSON-v2 until later cutover slices enable zcbor, Python CBOR encoding, and
cross-language golden vectors.

## Encoding Shape

Every framework-owned CBOR-v2 control-plane payload is a CBOR map with compact
integer keys. The first two keys are reserved across all message families:

1. key `0`: schema version, currently integer `2`
2. key `1`: message kind, using the message-kind table below

Common metadata and family-specific fields use stable integer keys. CLI stdout
and evidence records keep human-readable JSON field names after decode.

## Message Kinds

| Kind | Name | Direction |
| --- | --- | --- |
| 1 | `query_request` | CLI to Unit |
| 2 | `lease_acquire_request` | CLI to Unit |
| 3 | `lease_release_request` | CLI to Unit |
| 4 | `app_command_request` | CLI to Unit |
| 5 | `callback_config_request` | CLI to Unit |
| 6 | `update_prepare_request` | CLI to Unit |
| 7 | `update_verify_request` | CLI to Unit |
| 8 | `update_activate_request` | CLI to Unit |
| 9 | `update_rollback_request` | CLI to Unit |
| 20 | `error_reply` | Unit to CLI |
| 21 | `lease_reply` | Unit to CLI |
| 22 | `query_device_reply` | Unit to CLI |
| 23 | `query_apps_reply` | Unit to CLI |
| 24 | `query_leases_reply` | Unit to CLI |
| 25 | `update_prepare_reply` | Unit to CLI |
| 26 | `update_verify_reply` | Unit to CLI |
| 27 | `update_activate_reply` | Unit to CLI |
| 28 | `update_rollback_reply` | Unit to CLI |
| 29 | `app_command_reply` | Unit or app callback bridge to CLI |
| 40 | `callback_event` | Unit to CLI subscriber |
| 41 | `update_event` | Unit to CLI subscriber |
| 42 | `state_event` | Unit to CLI subscriber |
| 43 | `lease_event` | Unit to CLI subscriber |

## Key Ranges

| Range | Purpose |
| --- | --- |
| 0-12 | schema, message kind, status, request metadata |
| 20-21 | error classification |
| 30-32 | lease resource and lease timing |
| 40-44 | device and network state |
| 50-59 | app, update, artifact, command arguments |
| 60-71 | query-apps and query-leases aggregate payloads |
| 80-87 | callback config, callback event, app command reply |
| 90-93 | framework event and state diagnostics |

The machine-readable mirror for the current key map and initial golden vectors is
`applocation/NeuroLink/neuro_cli/tests/fixtures/protocol_cbor_v2_schema.json`.
The C constants live in `neuro_protocol.h`; the Python mirror lives in
`neuro_protocol.py`. Tests must keep all three synchronized.

## Required Fixture Progression

The fixture manifest started as schema-only in `EXEC-155`. `EXEC-157` adds the
first Unit-validated vectors for the common envelope header and error reply.
Later slices must continue adding golden vectors in this order:

1. common metadata request
2. error reply
3. lease acquire/release replies
4. query-device reply
5. callback event
6. app command reply
7. query-apps and query-leases replies
8. update prepare/verify/activate/rollback requests and replies
9. update, state, and lease framework events

Each vector must include:

1. vector name
2. message kind name and numeric value
3. logical JSON-style DTO used by CLI stdout and evidence tools
4. expected CBOR bytes as lowercase hex
5. required-key list
6. optional-key list
7. negative decode cases for missing keys, wrong types, oversized text, and
   truncated payloads

## Compatibility Rules

1. Key values are append-only after the first CBOR runtime cutover. New fields
   get new keys; existing keys are not reused for different semantics.
2. Required-key changes are protocol-breaking and require a release note plus
   Unit and CLI golden-vector updates.
3. CLI may pretty-print decoded payloads using JSON field names, but Unit wire
   payloads use integer CBOR keys.
4. App custom event payloads remain app-owned until the framework defines a
   typed app-event schema. Framework-owned callback/update/state/lease events
   must use the message kinds above.
5. Host artifact-provider payloads are separate from Unit runtime control-plane
   payloads and should not be folded into the first CBOR-only Unit cutover
   unless separately tested.