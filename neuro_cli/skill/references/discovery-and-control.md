# Neuro CLI Discovery And Control Reference

Agents should use read-only discovery workflows before running protected or
destructive control workflows. Each discovery workflow is exposed as a
non-executing plan so smaller Agents can inspect commands, requirements, and
JSON contracts before running anything on a Linux host.

## Discovery Order

1. Host: `workflow plan discover-host` then run `system init` and
	`system capabilities` through the wrapper.
2. Router: `workflow plan discover-router` then classify `router.listening` and
	router failure statuses before any Unit query diagnosis.
3. Serial: `workflow plan discover-serial` then require explicit
	`/dev/ttyACM*` or `/dev/ttyUSB*` visibility for hardware evidence.
4. Device: `workflow plan discover-device` then query the target node with
	`query device` or `system query device`.
5. Apps: `workflow plan discover-apps` then inspect `app_count`,
	`running_count`, `suspended_count`, and each app runtime/update state.
6. Leases: `workflow plan discover-leases` then ensure stale leases are absent
	before protected deploy or app control.

## Discovery Workflow Plans

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-host
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-router
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-serial
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases
```

All discovery plans report `executes_commands: false`, `category: discovery`,
host support, hardware/serial/router requirements, expected success fields,
failure statuses, cleanup rules, and a `json_contract` object for the listed
commands. Agents must review the plan first and only run the listed command
explicitly after checking the requirements.

## JSON Contracts

Host discovery succeeds when `system init` returns `ok: true`, `status: ready`,
the current `release_target`, protocol metadata with `wire_encoding: cbor-v2`,
and `agent_skill.source_of_truth: canonical`. `workspace_not_found` means the
Agent is outside the west workspace or cannot locate `applocation/NeuroLink`.

Router discovery uses the Linux preflight JSON shape. A successful router check
contains `status: ready`, `ready: true`, and `router.listening: true` with
`router.port: 7447` unless the operator supplied a different port. Router
failure states include `router_not_listening` and `router_failed_to_start`.
Board no-reply states must remain separate as `no_reply_board_not_attached` or
`no_reply_board_unreachable`.

Serial discovery uses the Linux preflight JSON shape. Success contains
`serial.present: true` and a non-empty `serial.devices` list. Failure is
`serial_device_missing`; treat this as USB attachment, host permissions, or WSL
USB pass-through state, not a CLI protocol failure.

Device discovery uses wrapper JSON around `query device`. Success contains
`ok: true` and at least one OK reply whose payload reports `status: ok`,
`node_id`, and, when firmware provides it, `session_ready`, `network_state`, and
`ipv4`. Failure states include `session_open_failed`, `no_reply`,
`parse_failed`, `error_reply`, and nested `payload.status: error`.

App discovery uses wrapper JSON around `query apps`. Success contains
`app_count`, `running_count`, `suspended_count`, and an `apps` list. If the
target app is absent or not running, classify that as `app_not_running` before
running deploy or app-control recipes.

Lease discovery uses wrapper JSON around `query leases`. Success contains a
`leases` list; an empty list is the expected clean state before smoke/control
closure. Existing active leases are not automatically destructive, but control
recipes must either own and release them or wait for TTL expiry.

## Protected Control Order

1. Ask for `workflow plan control-health` and run it first as a read-only gate.
2. For deploy, ask for `workflow plan control-deploy`, acquire the update lease,
	run deploy prepare, verify, and activate in order, then release the lease.
3. For app commands, ask for `workflow plan control-app-invoke`, acquire the app
	control lease, invoke the command, then release the lease.
4. For callback configuration, ask for `workflow plan control-callback`, enable
	callback mode, invoke the app, monitor app-scoped events, disable callback
	mode, and release the lease.
5. For passive event collection, ask for `workflow plan control-monitor` and use
	handler execution only when it is explicitly approved and audited.
6. If any protected flow exits early, ask for `workflow plan control-cleanup`
	and verify final `query leases` state.

## Protected Control Workflow Plans

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-health
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-deploy
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-app-invoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-callback
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-monitor
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-cleanup
```

Every protected control plan reports whether it is destructive, what leases it
requires, expected success fields, failure statuses, and cleanup commands.
Agents must treat nested `payload.status: error` as a command failure even when
the transport-level reply is OK.

## Protected Control JSON Contracts

Health control is read-only and succeeds when `query device`, `query apps`, and
`query leases` all return wrapper JSON with `ok: true` and nested payload
`status: ok`. Any `no_reply`, `session_open_failed`, `parse_failed`,
`error_reply`, or nested `payload.status: error` stops protected control.

Deploy control is destructive because it changes the active app image. It must
acquire an update lease for `update/app/neuro_unit_app/activate`, run deploy
prepare with `build/neurolink_unit/llext/neuro_unit_app.llext`, run deploy
verify, run deploy activate with the same lease id, query device/apps after
activation, release the lease, and query leases. Success requires each deploy
step to report `status: ok` and final lease cleanup to show no stale update
lease.

App invoke control is destructive because it sends an app command. It must
acquire `app/neuro_unit_app/control`, run `app invoke`, release the app-control
lease, and query leases. If app discovery reports `app_not_running`, deploy or
activate the app through the deploy control recipe before invoking.

Callback control is destructive because it changes callback configuration and
triggers app events. It must acquire the app-control lease, enable callback
configuration, invoke the app, monitor app-scoped events, disable callback
configuration, and release the lease. Callback handler execution is optional and
must be explicit; audit output must capture runner, cwd, timeout, return code,
stdout, stderr, and truncation fields.

Monitor control is non-destructive unless an approved handler performs local
side effects. Use `monitor app-events` for app-scoped event evidence and include
handler options only after operator approval. Handler failures are workflow
failures, not warnings.

Cleanup control releases known workflow lease ids and then queries leases. A
missing known lease may mean it was already cleaned up, but final closure still
requires a successful `query leases` response with no unexpected active leases.

## Current Wrapper Examples

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query device
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query apps
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py query leases
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke
```

## Failure States To Preserve

1. `serial_device_missing`
2. `no_reply_board_unreachable`
3. `session_open_failed`
4. `parse_failed`
5. `handler_failed`
6. nested `payload.status: error`
