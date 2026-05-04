# Neuro CLI Workflow Reference

## Setup

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan setup-linux
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan setup-windows
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-neuro-cli-deps
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities
```

## Build Plans

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-edk
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan demo-build
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan cli-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-layout-dump
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan llext-memory-config
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan llext-lifecycle
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan release-closure
```

## Memory Evidence

Ask the CLI for the supported memory evidence command before changing Unit
memory defaults:

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence
```

The generated JSON and summary record the release target, firmware build
configuration, stack/heap/network buffer settings, static ELF staging settings,
and any build-log memory summary available from the Unit build.

For release 1.1.9 static layout work, ask for `workflow plan
memory-layout-dump`, then run `memory layout-dump` to collect section-level
board layout evidence. Use `workflow plan llext-memory-config`, then run
`memory config-plan` to compare baseline and candidate layout evidence before
any runtime or hardware promotion step. For dynamic heap candidates, review
`docs/project/RELEASE_1.1.9_LLEXT_MEMORY_BOUNDARIES.md` first; static layout
evidence alone cannot promote `CONFIG_LLEXT_HEAP_DYNAMIC=y`.

## Board Gates

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-host
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-router
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-serial
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan serial-discover
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan serial-zenoh-config
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan serial-zenoh-recover
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-device
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-apps
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-leases
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-health
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-deploy
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-app-invoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-callback
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-monitor
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan control-cleanup
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan smoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan demo-net-event-smoke
```

Run discovery in order before protected control: host, router, serial, device,
apps, then leases. Discovery plans are read-only for Unit state; router discovery
may start only a local router when the operator approves the listed command.
Use the serial Zenoh workflows only when endpoint drift or first-boot router
configuration must be corrected through the Unit UART shell.

Run protected control only after discovery succeeds. Control plans cover
read-only health, protected deploy, app invoke, callback configuration, event
monitoring, and lease cleanup. Destructive plans declare `destructive: true` and
include lease cleanup commands.

For release 1.2.0 demo or AI Core integration work, ask for `workflow plan demo-build` before
building a selected demo artifact through the catalog-backed wrapper. Then use
`workflow plan demo-net-event-smoke` to inspect the first end-to-end demo
sequence for `neuro_demo_net_event`: build, preflight with explicit artifact
path, protected deploy, capability/publish invoke, app-event monitoring, and
lease cleanup.

## Deploy Order

1. Acquire a lease for the update/app resource.
2. Run deploy prepare with the local LLEXT artifact.
3. Run deploy verify.
4. Run deploy activate with the lease id.
5. Query device/apps to confirm state.
6. Capture event or smoke evidence.

## Release Closure

Review the final gate sequence without executing it:

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan release-closure
```

Release closure must keep `RELEASE_TARGET` unchanged until the release-specific
evidence has passed. For release 1.2.0 local AI Core closure, that evidence is
Core tests, Neuro CLI tests, Core dry-run smoke, MAF provider smoke, Problems,
and whitespace checks. Hardware preflight/smoke remains required only for
hardware-targeted follow-up integration tracks.

## Failure Classification

- Process nonzero: command transport, argument, or runtime failure.
- JSON parse failure: wrapper/CLI contract failure.
- `ok: false`: payload-level command failure.
- `status: not_implemented`: planned capability gap.
- `status: parse_failed`: unreadable OK reply payload.
- `status: session_open_failed`: dependency/session-open failure after retries.
- `status: handler_failed`: CLI handler failure after session open.
- `status: serial_device_missing`: Unit UART is not visible to the host.
- `status: serial_timeout`: UART shell did not reply before timeout.
- `status: endpoint_verify_failed`: UART shell output did not confirm the requested Zenoh endpoint.
- `payload.status: error`: Unit-level error reply.
