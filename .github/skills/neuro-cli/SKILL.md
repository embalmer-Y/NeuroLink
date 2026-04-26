---
name: neuro-cli
description: "Use when: operating NeuroLink Unit boards with neuro_cli; setting up Zephyr/NeuroLink environment; building Unit firmware, Unit EDK, or LLEXT apps; running preflight, smoke, deploy prepare/verify/activate, lease, app invoke, callback registration, event monitoring, or evidence collection workflows."
argument-hint: "workflow or command goal, for example: preflight, deploy app, monitor callbacks"
---

# Neuro CLI Orchestration

## When To Use

Use this skill for NeuroLink board and app-development workflows that should go
through the supported Neuro CLI and scripts instead of improvised Zenoh calls.
It covers environment checks, workflow planning, Unit/App/EDK builds, board
preflight, smoke, deploy, lease operations, app command invocation, callback
configuration, callback event monitoring, and evidence collection.

## Ground Rules

1. Keep CLI stdout and automation evidence JSON-readable. Use `--output json`
   or the wrapper at `./../../../neuro_cli/scripts/invoke_neuro_cli.py`.
2. Treat both process exit code and JSON payload status as authoritative.
   `ok: false`, `status: error`, `status: not_implemented`, unreadable JSON,
   and nonzero process exits are failures for Agent workflows.
3. Runtime Unit board traffic is CBOR-v2. CLI output and evidence remain JSON.
4. Do not promote `RELEASE_TARGET` until release closure evidence has passed.
5. Callback handler execution must be explicit and audited. Never silently run
   local code from MCU-originated events.

## First Checks

1. Run environment diagnostics:

   ```bash
   python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system init
   ```

2. Read capabilities:

   ```bash
   python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py system capabilities
   ```

3. Ask for workflow commands before running build or board operations:

   ```bash
   python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan preflight
   python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan app-build
   ```

## Common Workflows

### Unit And CLI Verification

1. Use `workflow plan unit-tests` for the native_sim Unit test command.
2. Use `workflow plan cli-tests` for the Python CLI regression command.
3. Run `git diff --check` in `applocation/NeuroLink` before recording evidence.

### App Build And Deploy

1. Build the app artifact from `workflow plan app-build`.
2. Acquire a protected update lease:

   ```bash
   python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py lease acquire --resource update/app/neuro_unit_app/activate
   ```

3. Run deploy steps in order: prepare, verify, activate.
4. Release the lease after the workflow or use the app callback smoke helper
   that releases it automatically.

### Callback Smoke

1. Configure callback behavior only with explicit CLI arguments.
2. Use JSON event evidence. CBOR event payloads are decoded into logical JSON by
   the CLI.
3. If a local handler is used, ensure audit output captures runner, cwd,
   timeout, duration, return code, stdout, stderr, and payload size.

## References

- [Workflow reference](./references/workflows.md)
- [App template](./assets/neuro_unit_app_template.c)
- [Callback handler template](./assets/callback_handler.py)