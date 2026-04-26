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
```

## Board Gates

```bash
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan smoke
```

## Deploy Order

1. Acquire a lease for the update/app resource.
2. Run deploy prepare with the local LLEXT artifact.
3. Run deploy verify.
4. Run deploy activate with the lease id.
5. Query device/apps to confirm state.
6. Capture event or smoke evidence.

## Failure Classification

- Process nonzero: command transport, argument, or runtime failure.
- JSON parse failure: wrapper/CLI contract failure.
- `ok: false`: payload-level command failure.
- `status: not_implemented`: planned capability gap.
- `payload.status: error`: Unit-level error reply.