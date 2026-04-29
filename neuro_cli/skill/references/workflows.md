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
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan unit-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan cli-tests
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence
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

## Board Gates

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-host
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-router
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan discover-serial
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
```

Run discovery in order before protected control: host, router, serial, device,
apps, then leases. Discovery plans are read-only for Unit state; router discovery
may start only a local router when the operator approves the listed command.

Run protected control only after discovery succeeds. Control plans cover
read-only health, protected deploy, app invoke, callback configuration, event
monitoring, and lease cleanup. Destructive plans declare `destructive: true` and
include lease cleanup commands.

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

Release closure must keep `RELEASE_TARGET` unchanged until memory evidence,
CLI regressions, script regressions, whitespace checks, preflight, and smoke
evidence have all passed.

## Failure Classification

- Process nonzero: command transport, argument, or runtime failure.
- JSON parse failure: wrapper/CLI contract failure.
- `ok: false`: payload-level command failure.
- `status: not_implemented`: planned capability gap.
- `status: parse_failed`: unreadable OK reply payload.
- `status: session_open_failed`: dependency/session-open failure after retries.
- `status: handler_failed`: CLI handler failure after session open.
- `payload.status: error`: Unit-level error reply.
