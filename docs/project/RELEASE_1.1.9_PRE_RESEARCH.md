# NeuroLink Release 1.1.9 Pre-Research Baseline

## 1. Scope

Release 1.1.9 starts from the closed release-1.1.8 Linux/hardware baseline and
focuses on `neuro_cli` user interaction, CLI performance, UART-assisted Unit
recovery, LLEXT lifecycle ergonomics, and memory layout evidence for future
LLEXT memory configuration work.

Primary objectives:

1. Add a first-class `neuro_cli` serial/UART path for configuring the Unit Zenoh
   connect endpoint through the existing Zephyr shell commands.
2. Improve LLEXT app install, unload/uninstall, and delete semantics so runtime
   state and artifact state are explicit, lease-protected where destructive,
   and measurable.
3. Add a build-artifact based board static memory layout dump that can guide
   LLEXT app dynamic memory configuration candidates.
4. Preserve release-1.1.8 JSON-first workflow plans, wrapper behavior, and
   Agent-facing contracts while adding the new 1.1.9 workflows.
5. Improve operator UX and performance for common `neuro_cli` paths through
   clearer status output, stable failure classifications, and measured latency
   reductions.

Out of scope for kickoff:

1. Promoting `RELEASE_TARGET` from `1.1.8` to `1.1.9` before closure evidence.
2. Replacing Zenoh, CBOR-v2, the lease model, or the existing Zephyr shell UART
   command surface.
3. Persisting the UART Zenoh endpoint override in NVS/settings before runtime
   recovery behavior is proven on hardware.
4. Enabling runtime LLEXT heap reconfiguration before static layout evidence and
   Zephyr API safety constraints are documented.

## 2. Current Baseline

Release-1.1.8 is closed in `PROJECT_PROGRESS.md`. The current CLI release marker
is still `RELEASE_TARGET = "1.1.8"` in `neuro_cli/src/neuro_cli.py` and must stay
there until the final 1.1.9 promotion slice.

Current implementation facts:

1. The Unit shell already exposes `app zenoh_connect_show`,
   `app zenoh_connect_set <locator>`, and `app zenoh_connect_clear`.
2. `neuro_unit_zenoh_set_connect_override()` stores a runtime override and
   disconnects the active session when the endpoint changes, allowing the main
   Zenoh loop to reconnect without reflashing.
3. `neuro_cli` already has retry-aware Zenoh queries, JSON output, wrapper
   failure classification, and non-executing workflow plans.
4. LLEXT runtime lifecycle entry points are concentrated in `app_runtime_load()`,
   `app_runtime_start()`, `app_runtime_stop()`, and `app_runtime_unload()`.
5. Memory evidence collection already parses Unit build memory data and selected
   runtime heap/staging logs.

## 3. Execution Plan

### EXEC-192 Kickoff and UART CLI Foundation

1. Add this release planning document and record the 1.1.9 kickoff in the
   progress table.
2. Add `pyserial` as the CLI serial dependency.
3. Add `serial list` plus `serial zenoh show/set/clear` commands with JSON
   output and stable error statuses.
4. Add workflow plans for serial discovery, serial Zenoh config, serial Zenoh
   recovery, LLEXT lifecycle, memory layout dump, and LLEXT memory config.
5. Add parser, workflow, and wrapper regressions for the new command surface.

### EXEC-193 Unit Zenoh Override Hardening

1. Add focused Unit tests for endpoint override set/clear edge cases.
2. Confirm changed endpoints disconnect active sessions and unchanged endpoints
   do not cause unnecessary reconnect churn.
3. Improve shell error text only if it helps the CLI classify failures more
   deterministically.

### EXEC-194 LLEXT Lifecycle Semantics

1. Separate runtime unload from artifact delete in command contracts and tests.
2. Make inactive artifact deletion explicit and safe.
3. Add clear classifications for already-unloaded and missing-artifact cases.
4. Add timings and memory snapshots around load/start/stop/unload/delete.

### EXEC-195 Static Memory Layout Dump

1. Extend the memory evidence collector or add a sibling static-layout mode.
2. Emit stable JSON for regions, sections, key Kconfig values, staging policy,
   LLEXT heap configuration, and deltas against a baseline.
3. Add fixture coverage for `.config`, `zephyr.stat`, and map/section snippets.

### EXEC-196 Dynamic LLEXT Memory Candidates

1. Document safe configuration boundaries for `CONFIG_LLEXT_HEAP_DYNAMIC` and
   `llext_heap_init()` in `RELEASE_1.1.9_LLEXT_MEMORY_BOUNDARIES.md`.
2. Add reproducible candidate overlays for LLEXT heap and staging policy changes.
3. Gate promotion on static layout evidence and hardware runtime evidence.

### EXEC-197 Closure and Promotion

1. Run local Python, script, Unit test, memory evidence, and whitespace gates.
2. Run hardware preflight, UART Zenoh recovery/config, LLEXT lifecycle smoke,
   callback smoke where applicable, and final lease cleanup.
3. Promote CLI and sample app identity to 1.1.9 only after evidence is green.

## 4. Validation Gates

Local gates:

1. Python compile for CLI and wrapper sources.
2. Focused CLI and wrapper pytest suites.
3. Script regression suite.
4. Native Unit tests for touched runtime/Zenoh behavior.
5. Memory/static-layout evidence generation.
6. `git diff --check`.

Hardware gates:

1. Serial-required preflight.
2. UART `serial zenoh show/set/clear` against `/dev/ttyACM0` or the operator
   selected port.
3. `query device`, `query apps`, and `query leases` after endpoint recovery.
4. LLEXT deploy, activate, invoke, unload/uninstall, and artifact delete.
5. Final smoke evidence and empty lease query.

## 5. Decisions

1. Linux remains the canonical closure path unless Windows hardware validation
   is explicitly requested.
2. UART recovery uses the existing Zephyr shell command path for 1.1.9.
3. Static memory layout dump is build-artifact based and does not require
   hardware.
4. Runtime LLEXT memory reconfiguration is a candidate only after static layout
   evidence and no-loaded-extension safety rules exist.

## 6. Execution Ledger

### EXEC-197 Closure and Promotion

`EXEC-197` closed release-1.1.9 after the hardware window passed and release
identity was promoted. The final closure kept the dynamic LLEXT heap work as a
candidate-only boundary and closed the requested release scope around UART Zenoh
configuration, LLEXT lifecycle semantics, static memory layout evidence, and the
sample app release identity.

Evidence summary:

1. UART Zenoh `show`, `set`, and `clear` passed on `/dev/ttyACM0` with endpoint
   `tcp/192.168.2.94:7447`.
2. Hardware lifecycle smoke passed after adding CBOR request kind
   `update_delete_request=10` for `update/app/<app>/delete` in both Python and
   Unit protocol contracts.
3. Release identity was promoted to `RELEASE_TARGET = "1.1.9"`; the sample app
   now reports `neuro_unit_app-1.1.9-cbor-v2`.
4. Final memory evidence was captured at
   `applocation/NeuroLink/memory-evidence/release-1.1.9-closure.{json,summary.txt}`
   with `dram0=377188`, `iram0=66216`, `flash=673952`, `ext_ram=2847776`, and
   `section_count=77`.
5. The rebuilt LLEXT artifact contains `neuro_unit_app-1.1.9-cbor-v2`.
6. Local gates passed: Python compile, CLI+wrapper pytest (`123 passed`), script
   regression suite (`9/9`), Unit native_sim (`PROJECT EXECUTION SUCCESSFUL`),
   wrapper release-target checks, and `git diff --check`.
7. Post-promotion hardware smoke passed with evidence
   `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260501-021622.ndjson`.
8. Callback smoke passed with three CBOR callback events and `1.1.9` echo.
9. Final state was Unit `NETWORK_READY` at `192.168.2.67`, `neuro_unit_app`
   running/active, and `leases: []`.
