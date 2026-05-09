# NeuroLink

NeuroLink is a Zephyr-based edge runtime and host-control toolkit for managing Neuro Unit devices, deployable LLEXT applications, leases, update flows, and smoke validation.

The project is currently on closed release `1.2.4`, which completed the Core App Build/Deploy Orchestrator and production live event service slice. The canonical host CLI now advertises `RELEASE_TARGET = "1.2.4"`, and release `1.2.5` is the next planned HLD delivery slice.

Release `1.2.0` remains the earlier local AI Core baseline. Release `1.2.1` is now the closed Core-Agent baseline: `neurolink_core` provides a deterministic Microsoft Agent Framework-compatible workflow/Agent adapter seam, persistent perception/execution evidence, guarded real-provider wiring, approval-gated resumable tool execution, and bounded real Neuro CLI control integration validated on the connected DNESP32S3B hardware path. The validated release `1.1.10` Unit/demo platform remains the underlying hardware/runtime baseline for later provider or live-event follow-up work.

Release `1.2.2` is the closed real-LLM Core line. Core can run through a real MAF/OpenAI-compatible Affective Agent call, a modular Rational Agent backend using the Microsoft Agent Framework GitHub Copilot provider, and a Mem0-backed long-term memory path with SQLite fallback while preserving the existing policy, lease, approval, tool-adapter, and audit boundaries.

Release `1.2.3` is the closed autonomous-perception line. Core now has deterministic event replay/daemon evidence, explicit live-ingest provenance, approval-bounded recovery evidence, and real hardware callback/lease/state/update-plane proof through the generic Unit event listener.

Release `1.2.4` is the closed Core App Build/Deploy Orchestrator and production live event service slice. It moved the project from about 64% total HLD completion to about 75% by turning existing script and Neuro CLI paths into Core-owned build, artifact-admission, deploy, activation, recovery, and supervised event-service workflows.

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

The AI Core model and memory dependency set for the release-1.2.2 track is defined separately in:

```bash
applocation/NeuroLink/neurolink_core/requirements.txt
```

The GitHub Copilot Rational backend uses `agent-framework-github-copilot` and
requires the GitHub Copilot CLI to be installed and authenticated. Runtime use is
explicitly gated with `--rational-backend copilot --allow-model-call`; default
Core tests and dry-runs remain deterministic or injected-client based.

The AI Core operator startup and validation guide is documented in:

```bash
applocation/NeuroLink/docs/project/AI_CORE_RUNBOOK.md
applocation/NeuroLink/docs/project/AI_CORE_RUNBOOK_ZH.md
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

For the active release-1.2.4 Core operator paths, including app build/deploy
orchestration, bounded event-service supervision, Affective live model smoke,
Mem0 sidecar smoke, Copilot Rational backend, and the real Neuro CLI adapter
gate, follow `docs/project/AI_CORE_RUNBOOK.md` or the Chinese guide at
`docs/project/AI_CORE_RUNBOOK_ZH.md`.

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
- `docs/project/RELEASE_1.2.4_CORE_ORCHESTRATOR_PLAN.md`
- `docs/project/RELEASE_1.2.3_AUTONOMOUS_PERCEPTION_PLAN.md`
- `docs/project/RELEASE_1.2.2_REAL_LLM_CORE_PLAN.md`
- `docs/project/RELEASE_1.2.1_MAF_CORE_AGENT_PLAN.md`

Release `1.2.3` is closed as the current autonomous-perception and live-ingest baseline. Release `1.2.4` is the next planned HLD slice, focused on Core-owned app build/deploy orchestration and production-shaped live event service behavior. Remaining work after `1.2.4` is planned across `1.2.5`, `1.2.6`, and `1.2.7` so release `2.0.0` can be a stabilization and acceptance release rather than a large feature release.
