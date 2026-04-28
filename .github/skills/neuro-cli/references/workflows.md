# Neuro CLI Workflow Reference

## Setup

```bash
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
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan smoke
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke
```

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