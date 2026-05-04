# NeuroLink

NeuroLink is a Zephyr-based edge runtime and host-control toolkit for managing Neuro Unit devices, deployable LLEXT applications, leases, update flows, and smoke validation.

The project is currently closed at release `1.2.0`. The canonical host CLI advertises `RELEASE_TARGET = "1.2.0"`.

Release `1.2.0` closes the local AI Core baseline: `neurolink_core` provides a deterministic Microsoft Agent Framework-compatible workflow/Agent adapter seam, persistent perception/execution evidence, bounded Agent event ingestion, and a credential-safe provider smoke check. The validated release `1.1.10` Unit/demo platform remains the hardware baseline for follow-up provider or live-event integration work.

## Project Layout

```text
NeuroLink/
├── neuro_unit/       # Zephyr firmware, runtime, update service, app command service, and unit tests
├── neuro_cli/        # Python host-control CLI and CLI tests
├── neurolink_core/   # Python AI Core local baseline, event router, MAF adapter seam, and tests
├── scripts/          # Build, preflight, smoke, WSL board preparation, and utility scripts
├── tests/            # Script-level regression tests
├── docs/             # Release plans, architecture notes, and runbooks
├── subprojects/      # Neuro Unit application subprojects
└── smoke-evidence/   # Generated smoke/serial evidence placeholder; evidence files are not committed
```

## Requirements

NeuroLink is developed inside a Zephyr west workspace. From the workspace root, the expected paths are:

- Zephyr base: `zephyr/`
- NeuroLink project: `applocation/NeuroLink/`
- Python virtual environment: `.venv/`
- Zephyr SDK configured for the workspace

The Neuro CLI dependency set is defined in:

```bash
applocation/NeuroLink/neuro_cli/requirements.txt
```

## Environment Setup

From the west workspace root:

```bash
source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict --install-unit-cli-deps
```

For WSL + DNESP32S3B hardware validation, attach the board into WSL first:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --attach-only
```

If the board is visible as `/dev/ttyACM0` but does not answer Zenoh queries yet, prepare it over UART:

```bash
bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh --device /dev/ttyACM0 --capture-duration-sec 30
```

Pass Wi-Fi credentials through command-line options or environment variables when the defaults are not appropriate for the lab.

## Common Validation Gates

Run commands from the west workspace root.

### Neuro Unit native tests

```bash
west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run
```

### Linux Unit wrapper

```bash
bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh
```

### Neuro CLI tests

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py -q
```

### AI Core local baseline tests

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neurolink_core/tests -q
```

### AI Core dry-run and MAF provider smoke

```bash
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli no-model-dry-run --output json
/home/emb/project/zephyrproject/.venv/bin/python -m neurolink_core.cli maf-provider-smoke --output json
```

### C style

```bash
bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh
```

### Script regression

```bash
bash applocation/NeuroLink/tests/scripts/run_all_tests.sh
```

### Firmware and EDK builds

```bash
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check
bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check
```

### Real-board preflight and smoke

```bash
bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh --node unit-01 --auto-start-router --require-serial --install-missing-cli-deps --output text
bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh --install-missing-cli-deps --events-duration-sec 5
```

Generated smoke and serial evidence is written under `smoke-evidence/` and is ignored by Git.

## Neuro CLI

The canonical CLI entrypoint is:

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --help
```

Capability map:

```bash
/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/src/neuro_cli.py --output json capabilities
```

## Release Notes

Release progress and architecture closure notes live in:

- `PROJECT_PROGRESS.md`
- `docs/project/RELEASE_1.2.0_MAF_CORE_AGENT_PLAN.md`

Release `1.2.0` closes the local AI Core baseline after Python compile, Core tests, Neuro CLI tests, Core dry-run smoke, MAF provider smoke, Problems, and whitespace gates passed. Real model-provider calls, long-running live event daemons, and additional hardware smoke are post-baseline integration tracks.
