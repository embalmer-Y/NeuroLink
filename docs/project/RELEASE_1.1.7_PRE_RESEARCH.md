# NeuroLink Release 1.1.7 Pre-Research Baseline

## 1. Scope

Release 1.1.7 opens a stabilization and optimization track on top of the
closed release-1.1.6 CBOR runtime baseline. The release has two primary goals:

1. Optimize `neuro_unit` memory behavior and code structure across supported
   chips and devices without weakening the conservative real-board defaults
   that closed release-1.1.6.
2. Make `neuro_cli` work as the dependable operator and Agent control surface
   for setup, query, deploy, callback, evidence, and troubleshooting workflows.

This is not a protocol-replacement release. CBOR-v2 is already the runtime wire
encoding and should remain stable unless tests and hardware evidence justify a
small compatibility fix. The memory target is DRAM-first: the release should
favor safely moving suitable allocations out of scarce internal DRAM into a
proven provider-backed PSRAM/external-memory tier, and only then measured
reductions in total allocation size, heap fragmentation, stack pressure,
repeated buffer use, and operator failure ambiguity.

The memory work is explicitly multi-chip. DNESP32S3B/ESP32-S3 is the current
proof board and first evidence provider, not the architectural boundary. Release
1.1.7 should treat PSRAM as one external-memory backend, introduce a
platform-neutral memory capability/evidence model, and keep unknown or unproven
boards on safe fallback behavior until their provider-specific evidence passes.

Out of scope for the kickoff slice:

1. Promoting `RELEASE_TARGET` from `1.1.6` to `1.1.7` before closure evidence.
2. Enabling external-memory LLEXT ELF staging by default for all platforms. The
   release-1.1.6 ESP32-S3 PSRAM retest proved that lower reported DRAM can still
   fail real-board activation and follow-up `no_reply` checks.
3. Changing Zenoh key expressions, lease semantics, update state-machine
   semantics, callback security policy, or app-runtime lifecycle ordering
   without a focused contract decision and regression tests.
4. Treating lower build-time DRAM numbers as success without real-board smoke,
   deploy activate, query health, and callback freshness evidence.

## 2. Current Baseline

Release-1.1.6 is closed in the current workspace with CBOR-v2 Unit runtime
traffic, JSON/NDJSON CLI evidence, project-shared Neuro CLI skill packaging,
callback handler audit support, and real-board smoke/deploy/callback evidence.

Canonical release marker:

1. `applocation/NeuroLink/neuro_cli/src/neuro_cli.py`
2. `RELEASE_TARGET = "1.1.6"`

Relevant release-1.1.6 closure facts:

1. Unit build reported DRAM at about `395152 B (99.01%)` before final closure.
2. The initial safe default retained `CONFIG_HEAP_MEM_POOL_SIZE=57344` and
   `CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`; `EXEC-175A` later
   promoted `CONFIG_HEAP_MEM_POOL_SIZE=53248` after build, runtime, and
   hardware smoke evidence passed.
3. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n` remains the release default
   because PSRAM-preferred staging caused a hardware deploy activation failure
   and subsequent Unit `no_reply` state.
4. Static LLEXT ELF staging fixed the late activation `RESOURCE_LIMIT` failure
   that came from large heap allocation after Zenoh/network fragmentation.
5. Reducing the general heap to `40960` broke the Zenoh aux artifact path before
   `ARTIFACT GET`; `57344` restored the transfer path.
6. The app callback smoke now proves fresh LLEXT execution with expected app
   echo and live callback subscriber collection.

Current high-size implementation targets from the 1.1.6 baseline:

1. `neuro_unit/src/runtime/app_runtime.c`: about 1184 lines.
2. `neuro_unit/src/neuro_protocol_codec_cbor.c`: about 1123 lines.
3. `neuro_unit/src/neuro_unit_update_service.c`: about 1048 lines.
4. `neuro_unit/src/neuro_unit.c`: about 1048 lines.
5. `neuro_unit/src/zenoh/neuro_unit_zenoh.c`: about 973 lines.
6. `neuro_cli/src/neuro_cli.py`: about 2070 lines.

These sizes are not problems by themselves, but they identify the first modules
where memory instrumentation, focused extraction, and CLI robustness work should
look.

## 3. Release Decisions

### Memory Optimization Decision

Memory optimization must be evidence-led and DRAM-first. The preferred outcome
is not necessarily lower total memory use; it is lower scarce internal DRAM
pressure, including safe relocation of suitable buffers or staging data into a
proven PSRAM/external-memory provider. A change can reduce reported DRAM or
heap use and still be rejected if it weakens deploy activation, query health,
callback freshness, recovery behavior, or provider compatibility. Conversely, a
change that preserves total footprint but moves pressure out of internal DRAM
can be accepted only when the provider-specific hardware gate proves it safe.
The release must not bake a single board or chip family into the Unit runtime
policy.

Memory policy language in this release uses these terms:

1. `Internal memory`: memory that is safe for control structures, LLEXT-required
   internal data, DMA-sensitive buffers, and conservative fallback behavior.
2. `External memory`: board/provider-owned memory such as ESP32-S3 PSRAM or a
   future Zephyr shared multi-heap backend.
3. `Memory provider`: the port/capability implementation that can report and
   allocate from platform memory tiers.
4. `DRAM relief`: any proven reduction of scarce internal DRAM pressure, either
   by reducing allocations or by relocating eligible data to provider-backed
   external memory.
5. `External staging`: transient placement of large artifacts such as LLEXT ELF
   bytes outside scarce internal RAM when a provider proves it is safe.

Release defaults should remain conservative until a candidate passes the generic
local gate and the provider-specific hardware gate:

1. native_sim Unit tests,
2. Unit firmware build with memory deltas captured,
3. evidence capture including board, SoC, memory provider, external-memory
   capability flags, staging policy, and runtime heap snapshots,
4. flash and board preparation for each promoted provider,
5. serial-required preflight,
6. Linux smoke,
7. deploy prepare/verify/activate,
8. post-activate `query device`, `query apps`, and `query leases`,
9. callback freshness smoke.

Unknown boards, boards without external memory, and boards without proven LLEXT
external-staging compatibility must retain safe static/malloc fallback behavior.

### Neuro Unit Code Optimization Decision

Optimization means reducing real resource pressure and making behavior easier to
reason about. File splitting is allowed only when it also narrows ownership,
removes duplicate buffers, lowers stack or heap pressure, improves tests, or
makes diagnostics more actionable.

Primary Unit review themes:

1. LLEXT staging and app runtime memory ownership.
2. Zenoh session, query, artifact-provider, and event memory behavior.
3. CBOR encode/decode buffer sizing and duplicate temporary storage.
4. Update service request/reply buffer lifetime and formatting paths.
5. Shell, diagnostics, and network logging defaults that consume stack or heap.
6. Build-time Kconfig tuning guarded by real-board evidence.

### Neuro CLI Completeness Decision

`neuro_cli` should be treated as the authoritative control plane for operators
and Agents. It should classify failures precisely, preserve stable JSON output,
offer predictable workflow plans, and make setup/deploy/callback paths boring in
the best possible way.

Primary CLI review themes:

1. Command parser consistency and backward-compatible aliases.
2. JSON output schema stability across success, `status: error`, `no_reply`,
   decode failure, dependency failure, and handler failure paths.
3. Retry behavior and timeout reporting for session open and query calls.
4. Evidence records that include enough context to reproduce hardware failures.
5. Wrapper behavior in `invoke_neuro_cli.py`, including payload status checks.
6. Skill/workflow guidance staying aligned with the live CLI implementation.

## 4. Workstreams

### WS-1 Baseline, Measurements, and Guardrails

1. Record this baseline and kickoff ledger entry.
2. Capture current firmware memory numbers from a clean Unit build.
3. Add or confirm script support for extracting DRAM, IRAM, heap, stack, and
   configured buffer values from build outputs.
4. Add memory evidence fields for board, SoC, provider, external-memory
   capability flags, selected staging policy, runtime heap snapshots, and
   candidate labels.
5. Keep `RELEASE_TARGET = "1.1.6"` until final 1.1.7 closure.

### WS-1A Multi-Chip Memory Capability Model

1. Use HLD/LLD only for layering direction: board/chip-specific memory behavior
   belongs under the port/provider layer, while app runtime and update services
   consume uniform contracts.
2. Introduce a platform-neutral memory capability record before changing
   allocation behavior.
3. Treat ESP32-S3 PSRAM as the first provider implementation, not the model.
4. Preserve safe fallback for targets without external memory or without proven
   external LLEXT staging compatibility.
5. Add tests and evidence before any Kconfig default promotes external staging.

### WS-2 LLEXT Staging and App Runtime Memory

1. Review `app_runtime.c` staging allocation, static buffer use, fallback order,
   error classification, and cleanup paths.
2. Add tests for ELF staging size boundaries, static-buffer exhaustion, fallback
   behavior, and activation error reporting where feasible in native_sim.
3. Keep external-memory staging experimental and provider-gated until a
   candidate passes the full hardware gate for that provider.
4. Investigate whether the static ELF buffer can be made conditional, smaller,
   segmented, or reused without reintroducing heap fragmentation risk.
5. Move the staging decision toward a port memory provider/capability contract
   instead of direct ESP-specific assumptions in runtime policy code.
6. Preserve the successful 1.1.6 activate/unload/load/start ordering.

### WS-3 Zenoh, Network, and Artifact Memory Behavior

1. Review Zenoh aux artifact-provider flow for heap pressure and buffer reuse.
2. Measure query, publish, subscriber, and artifact transfer memory snapshots at
   key stages.
3. Avoid reducing `CONFIG_HEAP_MEM_POOL_SIZE` until the artifact path proves it
   can still issue and complete `ARTIFACT GET` under real-board smoke.
4. Add focused diagnostics for memory pressure near session open, artifact
   request, chunk receive, verify, activate, and post-activate query health.
5. Keep existing preflight `no_reply` classifications aligned with board UART
   readiness and router state.

### WS-4 CBOR Codec and Protocol Buffer Review

1. Review `neuro_protocol_codec_cbor.c` for oversized stack locals, duplicate
   temporary buffers, and repeated encode/decode patterns.
2. Preserve the release-1.1.6 CBOR-v2 wire schema and fixture compatibility.
3. Add golden-vector coverage for any DTO path touched during optimization.
4. Keep bounded CBOR hex diagnostics in CLI evidence while avoiding large binary
   dumps in Unit logs.
5. Document any schema-neutral internal helper extraction.

### WS-5 Update Service and Dispatch Simplification

1. Review `neuro_unit_update_service.c`, `neuro_unit_dispatch.c`, and
   `neuro_unit.c` for duplicated payload bridge logic and avoidable temporary
   formatting buffers.
2. Prefer request-field context and typed DTOs over legacy JSON-compatible
   payload parsing where behavior is already guarded.
3. Keep update prepare/verify/activate/rollback externally compatible.
4. Add regression tests before any service-boundary cleanup that touches lease
   validation, artifact metadata, runtime load/start/unload, callback registry,
   state events, or recovery seed persistence.
5. Keep dispatch route matching node-scoped and nested-action rejection intact.

### WS-6 DRAM-First Memory, Stack, Logging, and Kconfig Tuning

1. Audit `CONFIG_MAIN_STACK_SIZE`, `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE`, shell
   stack, connect thread stack, network buffers, and Zenoh debug defaults.
2. Use stack and heap runtime statistics where available rather than guessing.
3. Consider reducing verbose debug defaults only if diagnostics remain useful
   for hardware triage.
4. Prefer proven DRAM relief over raw total-memory reduction: candidates may
   move suitable buffers or staging allocations to PSRAM/external memory when a
   provider contract and hardware evidence prove that placement is safe.
5. Make risky DRAM-relief changes, including external-memory relocation and
   aggressive size reductions, opt-in or staged behind Kconfig switches until
   real-board evidence promotes them.
6. Record every accepted tuning with before/after build, provider placement,
   DRAM/ext-RAM deltas, and smoke evidence.

### WS-7 Neuro CLI Reliability and Output Polish

1. Define expected JSON envelopes for all high-value command families.
2. Add regression tests for capabilities, init, workflow plans, query, lease,
   deploy, update, events, app callback smoke, and wrapper classification.
3. Tighten failure classification for dependency errors, invalid CBOR payloads,
   `status: error`, reply payload status errors, `no_reply`, router absence,
   serial absence, and handler audit failures.
4. Make retry reporting consistent across human and JSON output.
5. Keep operator-friendly aliases, including compatibility flags already used in
   long command chains.

### WS-8 Neuro CLI Workflow and Skill Alignment

1. Ensure `.github/skills/neuro-cli` references exactly match live commands.
2. Add or update workflow references for memory evidence collection and release
   closure gates.
3. Keep `invoke_neuro_cli.py` strict about process exit, JSON stdout, `ok`, and
   nested payload status.
4. Add examples for post-activate health checks and callback freshness evidence.
5. Validate skill frontmatter and resources in CLI tests.

### WS-9 Closure and Release Identity

1. Run local, build, script, memory-evidence, CLI, skill, and hardware gates.
2. Capture final before/after memory numbers and explain accepted tradeoffs.
3. Capture serial-required preflight, Linux smoke, deploy activate, post-activate
   query health, and callback freshness evidence.
4. Promote `RELEASE_TARGET` to `1.1.7` only after all closure gates pass.

## 5. Acceptance Criteria

1. `neuro_unit` has measured memory improvements or clearly documented rejected
   candidates, with no regression in deploy, query, callback, or recovery flows.
2. The default firmware configuration remains hardware-proven. Any
   external-memory ELF staging or aggressive heap/stack reduction remains
   provider-gated and opt-in until proven safe.
3. Unit build output includes a repeatable memory summary for release evidence.
4. Memory evidence records board, SoC, memory provider, external-memory
   capability, static staging size, external staging preference, and runtime heap
   snapshots where available.
5. Native Unit tests cover touched app-runtime, update, dispatch, CBOR, event,
   provider fallback, and diagnostics paths.
6. `neuro_cli` JSON output is stable and complete for common success and failure
   paths, including nested payload status errors.
7. `invoke_neuro_cli.py` and the project-shared skill remain aligned with the
   live CLI behavior.
8. Hardware closure proves preflight, smoke, deploy activate, post-activate
   query health, and callback freshness on real DNESP32S3B hardware, while the
   release notes document fallback safety for unsupported providers.
9. Release identity is promoted to `1.1.7` only after all evidence is recorded.

## 6. Verification Gates

Local gates:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/neuro_cli/src/neuro_protocol.py applocation/NeuroLink/neuro_cli/src/neuro_cli.py applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest applocation/NeuroLink/neuro_cli/tests/test_neuro_cli.py applocation/NeuroLink/neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
4. `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
6. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
7. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check`
8. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-edk --no-c-style-check`

Memory and build gates:

1. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check`
2. Capture DRAM/IRAM/flash build summary from the Unit build.
3. Capture configured heap, stack, network buffer, static ELF buffer,
   external-memory provider/capability, and external staging values from the
   build config.
4. Compare candidate memory deltas against the release-1.1.6 conservative
   baseline.

CLI and skill gates:

1. CLI parser and JSON schema regression tests for high-value workflows.
2. Wrapper classification tests for process failure, invalid stdout, `ok=false`,
   `status: error`, and nested payload status failure.
3. Workflow plan tests for build, preflight, smoke, deploy, callback, and memory
   evidence collection.
4. Skill frontmatter and project-shared resource validation.

Hardware gates:

1. USB attach or serial visibility check.
2. Board preparation with UART capture as needed.
3. Serial-required preflight.
4. Linux smoke.
5. App deploy prepare/verify/activate smoke.
6. Post-activate `query device`, `query apps`, and `query leases`.
7. Callback freshness smoke with expected 1.1.7 app identity.
8. Optional experimental external-memory, heap, stack, or network-buffer
   candidate replay only after the conservative default passes.

## 7. Initial Execution Slices

1. `EXEC-168`: release-1.1.7 kickoff baseline and planning ledger entry.
2. `EXEC-169`: memory measurement tooling and release-1.1.6 baseline capture.
3. `EXEC-170`: app-runtime and LLEXT staging guardrails before optimization.
4. `EXEC-171`: conservative app-runtime memory optimization candidates.
5. `EXEC-172A`: multi-chip memory capability/evidence scaffolding without
   firmware behavior changes.
6. `EXEC-172B`: port-layer memory provider contract and app-runtime staging
   migration toward generic external-memory policy.
7. `EXEC-172`: Zenoh/artifact memory diagnostics and buffer reuse review.
8. `EXEC-173`: CBOR codec buffer and stack review under golden-vector tests.
9. `EXEC-174`: update service, dispatch, and Unit ingress cleanup focused on
   request-field DTO use and reduced temporary storage.
10. `EXEC-175`: Kconfig stack/heap/network tuning candidates with rollback notes.
11. `EXEC-176`: Neuro CLI JSON contract, parser, retry, and failure-classification
   polish.
12. `EXEC-177`: Neuro CLI workflow, wrapper, skill, and evidence alignment.
13. `EXEC-178`: local closure gates and memory-delta review.
14. `EXEC-179`: hardware closure, callback freshness, and release identity
    promotion.

Slice numbering may split if guardrails expose an intermediate defect. Any split
must preserve the release boundary: no risky memory default becomes release
default until real-board closure passes.

## 8. Risks

1. Internal DRAM is already near the limit, so small changes can break firmware
   build, boot, Zenoh session open, artifact transfer, or activate.
2. External-memory staging can look better in build output while failing real
   LLEXT activation, as seen during the release-1.1.6 ESP32-S3 PSRAM retest.
3. Reducing heap can break the artifact-provider path before obvious app-runtime
   code runs.
4. Stack reductions can pass native_sim and still fail on ESP32-S3 hardware if
   logging, networking, or CBOR paths take deeper call chains.
5. A provider that is safe for network or Wi-Fi buffers may still be unsafe for
   LLEXT staging or DMA-sensitive runtime data.
6. Refactoring large modules can accidentally change update ordering, callback
   registration, lease validation, or evidence shape.
7. CLI changes can make automation worse if JSON output drifts or failure status
   is hidden behind a transport-level success.
8. Hardware closure depends on WSL USB pass-through, router readiness, board
   Wi-Fi/network readiness, and serial visibility.

## 9. Rollback Strategy

1. Keep the release-1.1.6 conservative memory defaults as the fallback baseline.
2. Land measurement and tests before changing memory defaults.
3. Keep risky optimizations behind Kconfig switches until real-board evidence
   proves them.
4. If an optimization fails hardware smoke, revert that candidate and record the
   failure evidence rather than tuning around it blindly.
5. Keep CLI output compatibility tests around any parser, retry, wrapper, or
   evidence change.
6. Promote release identity only after the final evidence chain passes.

## 10. Release Identity Policy

`applocation/NeuroLink/neuro_cli/src/neuro_cli.py` must remain at
`RELEASE_TARGET = "1.1.6"` throughout implementation. A final identity-promotion
slice may set it to `1.1.7` only after local gates, memory evidence, CLI/skill
gates, script gates, serial-required preflight, Linux smoke, deploy smoke,
post-activate query health, and callback freshness evidence pass.

## 11. Execution Status

### EXEC-168 Release-1.1.7 Baseline Planning

`EXEC-168` starts the release-1.1.7 track from the closed release-1.1.6 baseline.
The planning focus is conservative `neuro_unit` memory/code optimization plus
`neuro_cli` reliability and workflow completeness.

No source behavior changes are included in this kickoff slice. The next slice
should build the measurement baseline before changing memory defaults or moving
large runtime buffers.

### EXEC-169 Memory Evidence Tooling

`EXEC-169` starts implementation by adding repeatable memory evidence collection
before any Unit memory defaults are changed.

Added tool:

1. `applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py`

The tool can parse an existing Unit Zephyr build directory or run the Unit build
first with `--run-build`. Evidence includes the canonical `RELEASE_TARGET`, key
heap/stack/network/LLEXT/PSRAM configuration values, section totals from
`zephyr.stat`, optional build-log memory summary rows, and JSON plus text
summary outputs under `applocation/NeuroLink/memory-evidence/`.

Focused validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py`
2. `bash applocation/NeuroLink/tests/scripts/test_collect_neurolink_memory_evidence.sh`
3. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py --build-dir build/neurolink_unit --output-dir applocation/NeuroLink/memory-evidence --label baseline-1.1.6-existing-build`

Existing-build evidence was generated at:

1. `applocation/NeuroLink/memory-evidence/baseline-1.1.6-existing-build.json`
2. `applocation/NeuroLink/memory-evidence/baseline-1.1.6-existing-build.summary.txt`

This existing-build capture reported `release_target=1.1.6` and
`section_total_dram0=392376`. It is useful as a parser/evidence smoke, but the
release baseline still needs a clean Unit build capture before optimization
candidates are evaluated.

Clean rebuild baseline capture then passed with:

1. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py --run-build --pristine-always --no-c-style-check --build-dir build/neurolink_unit --output-dir applocation/NeuroLink/memory-evidence --label baseline-1.1.6-clean-build`

Clean evidence outputs:

1. `applocation/NeuroLink/memory-evidence/baseline-1.1.6-clean-build.json`
2. `applocation/NeuroLink/memory-evidence/baseline-1.1.6-clean-build.summary.txt`

The clean baseline preserved `release_target=1.1.6`,
`CONFIG_HEAP_MEM_POOL_SIZE=57344`,
`CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`, and
`CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`. Build memory summary values
were `FLASH=808004B/16776960B (4.82%)`,
`iram0_0_seg=67816B/415492B (16.32%)`, and
`dram0_0_seg=395152B/399108B (99.01%)`. Section totals from `zephyr.stat` were
`dram0=392376`, `iram0=66216`, `flash=673292`, and `ext_ram=2847776`.

### EXEC-170 App Runtime Activate Guardrails

`EXEC-170` adds guardrail coverage around update activation before changing
LLEXT staging or app-runtime memory behavior.

Touched tests:

1. `applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_cmd_capability.c`
2. `applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`

Added guardrails:

1. Activate unloads an already-loaded runtime app before replacement
   `app_runtime_load()` and `app_runtime_start()`.
2. Activate load failure skips start and callback registration, emits a reply
   error, publishes an activate error event, and marks the update state failed.
3. Activate prefers decoded request-field `start_args` over legacy payload JSON.

Validation passed:

1. `clang-format -i applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_cmd_capability.c applocation/NeuroLink/neuro_unit/tests/unit/src/lifecycle/test_neuro_unit_update_service.c`
2. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`

### EXEC-170B LLEXT ELF Staging Guardrails

`EXEC-170B` adds direct native_sim guardrails around the LLEXT ELF staging
buffer allocation policy before any memory-default optimization is attempted.

Added runtime helper:

1. `applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_elf_staging.h`
2. `applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_elf_staging.c`

The helper owns the existing staging source enum, source-string helper,
allocation helper, and release helper. `app_runtime.c` still uses the same
policy ordering: opt-in PSRAM first, static internal ELF staging buffer second,
and malloc last. This is a testability extraction, not a memory-policy change.

Added native_sim test:

1. `applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_elf_staging.c`

Added guardrails:

1. Allocation without a source output pointer is rejected.
2. A static-buffer exact-fit allocation uses the static staging buffer and
   release clears its busy flag.
3. A second static-sized allocation while the static buffer is busy falls back
   to malloc instead of aliasing the static buffer.
4. An oversized allocation falls back to malloc and does not mark the static
   buffer busy.

Validation passed:

1. `clang-format -i applocation/NeuroLink/neuro_unit/include/runtime/app_runtime_elf_staging.h applocation/NeuroLink/neuro_unit/src/runtime/app_runtime_elf_staging.c applocation/NeuroLink/neuro_unit/src/runtime/app_runtime.c applocation/NeuroLink/neuro_unit/tests/unit/src/runtime/test_app_runtime_elf_staging.c`
2. `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit --no-c-style-check`
3. `west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
4. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
5. `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
6. `cd applocation/NeuroLink && git diff --check`

Memory evidence was captured with:

1. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py --run-build --no-c-style-check --build-dir build/neurolink_unit --output-dir applocation/NeuroLink/memory-evidence --label exec-170b-elf-staging-seam`

Evidence outputs:

1. `applocation/NeuroLink/memory-evidence/exec-170b-elf-staging-seam.json`
2. `applocation/NeuroLink/memory-evidence/exec-170b-elf-staging-seam.summary.txt`

The evidence preserved `release_target=1.1.6`,
`CONFIG_HEAP_MEM_POOL_SIZE=57344`,
`CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`, and
`CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`. Section totals were
`dram0=392376`, `iram0=66216`, `flash=673316`, and `ext_ram=2847776`.

### EXEC-171 Runtime Memory Diagnostics

`EXEC-171` starts the conservative optimization phase with measurement rather
than tuning. The first slice adds runtime heap snapshots to the paths that most
directly affected release-1.1.6 stability: Zenoh artifact prepare/download and
app-runtime LLEXT ELF staging.

Implementation points:

1. `neuro_unit.c` now passes a memory snapshot callback into
   `neuro_unit_zenoh_download_artifact()` so prepare/download progress can log
   heap state at start, first chunk, progress intervals, and completion.
2. `app_runtime.c` logs malloc heap snapshots before staging allocation, after
   staging allocation, and after a successful artifact read in `load_file_to_ram()`.
3. Snapshots use `malloc_runtime_stats_get()` under the existing
   `CONFIG_SYS_HEAP_RUNTIME_STATS=y` setting and report `free_bytes`,
   `allocated_bytes`, and `max_allocated_bytes`.
4. No memory default, stack size, Zenoh route, CBOR schema, CLI output, or
   release identity changed in this slice.

Experiment evidence was captured with:

1. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py --build-dir build/neurolink_unit --output-dir applocation/NeuroLink/memory-evidence --build-log applocation/NeuroLink/memory-evidence/exec-171-runtime-memory-diagnostics.build.log --label exec-171-runtime-memory-diagnostics`

Evidence outputs:

1. `applocation/NeuroLink/memory-evidence/exec-171-runtime-memory-diagnostics.json`
2. `applocation/NeuroLink/memory-evidence/exec-171-runtime-memory-diagnostics.summary.txt`
3. `applocation/NeuroLink/memory-evidence/exec-171-runtime-memory-diagnostics.build.log`

Build-memory comparison:

1. Clean 1.1.6 baseline: `FLASH=808004B/16776960B (4.82%)`,
   `iram0_0_seg=67816B/415492B (16.32%)`,
   `dram0_0_seg=395152B/399108B (99.01%)`.
2. EXEC-171 diagnostics: `FLASH=808348B/16776960B (4.82%)`,
   `iram0_0_seg=67816B/415492B (16.32%)`,
   `dram0_0_seg=395152B/399108B (99.01%)`.
3. Section totals after EXEC-171: `dram0=392376`, `iram0=66216`,
   `flash=673636`, and `ext_ram=2847776`.

Interpretation: the diagnostic slice adds about `344B` of reported FLASH and no
reported DRAM/IRAM increase, so it is acceptable as temporary observability for
the next hardware smoke/deploy experiment. The actual tuning decision should be
made only after real-board logs show heap snapshots through prepare, activate,
post-activate query, and callback freshness.

### EXEC-171B Runtime Heap Snapshot Evidence Parser

`EXEC-171B` turns the runtime heap snapshot log lines from `EXEC-171` into
structured experiment data that can be compared across candidate builds.

Collector update:

1. `applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py`

New evidence support:

1. `--runtime-log <path>` may be provided multiple times.
2. Supplied build logs are also scanned for heap snapshot lines.
3. JSON evidence now includes `runtime_heap_snapshots`.
4. Text summaries now include a `[runtime_heap_snapshots]` section.

Recognized log forms:

1. `update heap snapshot stage=<stage> free=<bytes> allocated=<bytes> max_allocated=<bytes>`
2. `app-runtime heap snapshot stage=<stage> path=<path> free=<bytes> allocated=<bytes> max_allocated=<bytes>`

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py`
2. `bash applocation/NeuroLink/tests/scripts/test_collect_neurolink_memory_evidence.sh`
3. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`

Hardware experiment usage:

1. Capture the diagnostic firmware's smoke/deploy/UART log.
2. Run `collect_neurolink_memory_evidence.py --runtime-log <captured-log>` with
   the candidate label.
3. Compare prepare/download heap snapshots against app-runtime staging snapshots
   before changing heap size, static ELF buffer size, PSRAM preference, stack
   sizes, or network buffers.

### EXEC-172A Multi-Chip Memory Capability Evidence Scaffolding

`EXEC-172A` adjusts the release-1.1.7 memory track back to the product goal:
Unit memory optimization must work across multiple chips and devices, with
DNESP32S3B/ESP32-S3 treated as the first proof provider rather than the
architecture.

Implementation boundary:

1. Evidence tooling only.
2. No firmware behavior changes.
3. No heap, stack, network-buffer, static ELF buffer, external-memory staging,
   Zenoh, CBOR, CLI, or release-identity default changes.

Collector update:

1. `applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py`

New evidence fields:

1. `platform.board`
2. `platform.board_target`
3. `platform.board_qualifiers`
4. `platform.soc`
5. `memory_capability.provider`
6. `memory_capability.external_memory_configured`
7. `memory_capability.external_heap_size_bytes`
8. `memory_capability.shared_multi_heap_enabled`
9. `memory_capability.esp_spiram_enabled`
10. `memory_capability.external_elf_staging_preferred`
11. `memory_capability.static_elf_staging_size_bytes`

Command-line support:

1. `--memory-provider <label>` can override the inferred provider label for a
   candidate experiment.

Interpretation:

1. `esp-spiram` is now recorded as a provider label, not a release-wide memory
   architecture.
2. `none` is a valid provider for generic/no-external-memory fallback evidence.
3. Current default behavior remains static/malloc fallback unless a later
   provider-specific candidate proves external staging is safe.

Validation target:

1. Python compile for the collector.
2. Focused memory evidence script test.
3. Full script suite before closing this slice.

### EXEC-172B Port-Layer Memory Provider Contract

`EXEC-172B` starts the implementation migration promised by `EXEC-172A`: the
Unit runtime no longer owns the platform-specific external-memory allocation
detail for LLEXT ELF staging. Instead, external allocation is exposed through a
port memory provider contract, while the current default policy remains
unchanged.

Implementation boundary:

1. No heap, stack, network-buffer, static ELF buffer, external staging default,
   Zenoh, CBOR, CLI, or release-identity default changes.
2. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n` remains the conservative
   default, so runtime staging still uses static/malloc fallback by default.
3. ESP32-S3 PSRAM is represented as the first board memory provider, not as a
   runtime-layer architecture assumption.

New contract:

1. `applocation/NeuroLink/neuro_unit/include/port/neuro_unit_port_memory.h`
2. `neuro_unit_port_set_memory_ops()`
3. `neuro_unit_port_get_memory_ops()`

Provider migration:

1. Generic port provider now installs board memory ops when a board supplies
   them.
2. DNESP32S3B exposes provider label `esp-spiram` and maps external allocation
   to Zephyr shared multi-heap external memory when `CONFIG_SHARED_MULTI_HEAP`
   is available.
3. `app_runtime_elf_staging.c` now requests external staging through port memory
   ops when external staging is explicitly enabled, then falls back to static
   staging and malloc exactly as before.
4. The staging source text is now generic `external`; the legacy PSRAM enum name
   remains an alias for compatibility with existing code.

Validation passed:

1. Native Unit tests: `123/123` passed.
2. ESP32-S3 Unit build passed.
3. C style passed with `0` errors.
4. `git diff --check` passed.
5. Memory evidence generated:
   `memory-evidence/exec-172b-port-memory-provider-contract.json` and
   `.summary.txt`.

Evidence snapshot:

1. `release_target=1.1.6`
2. `board=dnesp32s3b`
3. `soc=esp32s3`
4. `provider=esp-spiram`
5. `dram0=392380`
6. `iram0=66216`
7. `flash=673676`
8. `ext_ram=2847776`

### EXEC-172C Generic External Staging Kconfig Compatibility

`EXEC-172C` continues the migration away from ESP-specific release policy names
by introducing a generic external-memory staging preference symbol while keeping
the legacy PSRAM symbol as a compatibility alias.

Implementation boundary:

1. No firmware behavior change under the release default.
2. No heap, stack, network-buffer, static ELF buffer, Zenoh, CBOR, CLI, or
   release-identity default changes.
3. Existing ESP32-S3 PSRAM experiments can still use the legacy symbol, but new
   runtime policy code uses the generic external-memory symbol.

Kconfig update:

1. `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER`
   - generic experimental preference for provider-backed external LLEXT ELF
     staging
   - default remains `n`
   - explicitly set to `n` in the production Unit `prj.conf`
2. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER`
   - kept as an ESP SPIRAM compatibility alias
   - selects the generic external staging preference when enabled

Runtime update:

1. `app_runtime_elf_staging.c` now gates provider-backed external allocation on
   `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER`.
2. The default build keeps both the generic and legacy symbols disabled, so the
   safe static/malloc fallback remains active.

Evidence update:

1. Memory evidence now captures both generic and legacy staging preference
   symbols.
2. `external_elf_staging_preferred` is true if either the generic or legacy
   compatibility symbol is enabled.

Validation passed:

1. Python compile for the evidence collector.
2. Focused memory evidence script test.
3. Full script suite (`8/8`).
4. Native Unit tests.
5. ESP32-S3 Unit build.
6. C style with `0` errors.
7. `git diff --check`.

Evidence snapshot:

1. `memory-evidence/exec-172c-generic-external-staging-kconfig.json`
2. `memory-evidence/exec-172c-generic-external-staging-kconfig.summary.txt`
3. `release_target=1.1.6`
4. `board=dnesp32s3b`
5. `soc=esp32s3`
6. `provider=esp-spiram`
7. `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
8. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
9. `external_elf_staging_preferred=False`
10. `dram0=392380`
11. `iram0=66216`
12. `flash=673676`
13. `ext_ram=2847776`

### EXEC-172D Staging Provider Runtime Diagnostics

`EXEC-172D` prepares the hardware-evidence step without enabling external
staging by making LLEXT ELF staging allocation decisions visible in runtime
logs and memory evidence.

Implementation boundary:

1. No allocation-policy change under the release default.
2. No heap, stack, network-buffer, static ELF buffer, external staging default,
   Zenoh, CBOR, CLI, or release-identity default changes.
3. This slice adds observability only; external staging remains an opt-in
   experimental path gated by `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER`.

Runtime diagnostic update:

1. Added `app_runtime_elf_staging_provider_str()` so the runtime can report the
   active port memory provider label, or `none` if no provider is installed.
2. `load_file_to_ram()` now emits a stable allocation line after staging buffer
   allocation:

   ```text
   app-runtime ELF staging allocation path=<path> bytes=<size> source=<source> provider=<provider>
   ```

3. The `source` value remains the generic staging source text: `static`,
   `malloc`, or `external`.

Evidence update:

1. The memory evidence collector parses staging allocation lines from build or
   runtime logs.
2. Parsed rows are written under `runtime_staging_allocations` in JSON and
   `[runtime_staging_allocations]` in the summary.
3. The focused collector test covers a fixture line with `source=static` and
   `provider=esp-spiram`.
4. The staging unit test uses a local static-buffer-size constant matching the
   native test config so editor analysis remains clean outside Zephyr's
   generated Kconfig context.

Validation passed:

1. C/H formatting for touched runtime files.
2. Python compile for the evidence collector.
3. Focused memory evidence script test.
4. Native Unit tests.
5. ESP32-S3 Unit build.
6. C style with `0` errors.
7. `git diff --check`.

Evidence snapshot:

1. `memory-evidence/exec-172d-staging-provider-diagnostics.json`
2. `memory-evidence/exec-172d-staging-provider-diagnostics.summary.txt`
3. `release_target=1.1.6`
4. `board=dnesp32s3b`
5. `soc=esp32s3`
6. `provider=esp-spiram`
7. `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
8. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
9. `external_elf_staging_preferred=False`
10. `dram0=392380`
11. `iram0=66216`
12. `flash=673756`
13. `ext_ram=2847776`
14. `runtime_staging_allocations=not_available` until a runtime log is
    supplied to the collector

### EXEC-172E Runtime Evidence Gate

`EXEC-172E` turns runtime evidence parsing into an explicit opt-in gate for the
next hardware smoke/deploy cycle. The collector can now fail a candidate when
the supplied runtime/build logs do not contain the minimum memory evidence
needed to judge staging behavior.

Implementation boundary:

1. Evidence tooling only.
2. No firmware behavior, memory default, staging policy, Zenoh, CBOR, CLI, or
   release-identity changes.
3. The gate is opt-in; normal baseline evidence collection continues to write
   JSON/summary output without failing when runtime logs are absent.

Collector update:

1. Added `--require-runtime-evidence`.
2. Added `runtime_evidence_gate` to JSON and `[runtime_evidence_gate]` to the
   summary.
3. The gate requires all of the following when enabled:
   - at least one `update` heap snapshot,
   - at least one `app-runtime` heap snapshot,
   - at least one `app-runtime ELF staging allocation` row.
4. Missing evidence causes exit code `2` after writing the evidence artifacts,
   so failed hardware attempts still leave inspectable output.

Validation passed:

1. Python compile for the collector.
2. Focused memory evidence test covering both gate pass and gate fail cases.
3. Full script suite (`8/8`).
4. `git diff --check`.

Evidence snapshot:

1. `memory-evidence/exec-172e-runtime-evidence-gate.json`
2. `memory-evidence/exec-172e-runtime-evidence-gate.summary.txt`
3. `release_target=1.1.6`
4. `board=dnesp32s3b`
5. `soc=esp32s3`
6. `provider=esp-spiram`
7. `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
8. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
9. `external_elf_staging_preferred=False`
10. `dram0=392380`
11. `iram0=66216`
12. `flash=673756`
13. `ext_ram=2847776`
14. `runtime_evidence_gate.required=False`
15. `runtime_evidence_gate.passed=False`
16. `runtime_evidence_gate.missing=update_heap_snapshot,app_runtime_heap_snapshot,staging_allocation`

### EXEC-172F Hardware App Version Evidence

`EXEC-172F` moved the conservative-default hardware path forward and added a
board-visible LLEXT app version marker so stale app deployment can be ruled out
during activate/runtime diagnostics.

Implementation boundary:

1. The CLI release marker remains `RELEASE_TARGET = "1.1.6"`.
2. External ELF staging remains disabled by default.
3. The sample LLEXT app now reports its development marker at runtime; this is
   evidence/debug output, not a protocol-schema change.
4. The app manifest patch version is now `1.1.7` for the development artifact.

App marker update:

1. `app_version=1.1.7-dev`.
2. `app_build_id=neuro_unit_app-1.1.7-dev-cbor-v2`.
3. `app_init()` and `app_start()` print:
   `neuro_unit_app version stage=<stage> version=1.1.7-dev build_id=neuro_unit_app-1.1.7-dev-cbor-v2 manifest=1.1.7`.

Hardware findings:

1. A stale/empty staged artifact risk was confirmed during the first smoke
   attempt: `build/neurolink_unit/llext/neuro_unit_app.llext` was `0` bytes
   while `build/neurolink_unit_app/neuro_unit_app.llext` was `20144` bytes.
2. Rebuilding `unit-app` restored the staged artifact.
3. After adding the app version marker, both source and staged LLEXT artifacts
   were `21400` bytes and both contained
   `neuro_unit_app-1.1.7-dev-cbor-v2`.
4. After flash, the board initially sat at `ADAPTER_READY` with no IPv4; rerun
   board prepare restored `NETWORK_READY` at `192.168.2.69` and query `ok`.
5. Hardware smoke passed with deploy prepare, verify, activate, and monitor
   events completing successfully.
6. UART confirmed the board loaded the new app:
   `neuro_unit_app version stage=start version=1.1.7-dev build_id=neuro_unit_app-1.1.7-dev-cbor-v2 manifest=1.1.7`.
7. Activate-time dropped-message notices still occurred with the fresh app, so
   stale LLEXT execution is ruled out as the root cause; these notices are
   treated as Zenoh/runtime pressure signals rather than proof that evidence
   logs are missing.
8. Runtime evidence remained present and parseable for the gate.
9. The gated collector passed with update heap snapshots, an app-runtime heap
   snapshot, and a staging allocation row.

Evidence snapshot:

1. post-flash prepare UART:
   `smoke-evidence/serial-diag/serial-capture-20260427T162833Z.log`
2. smoke NDJSON:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260427-163038.ndjson`
3. smoke summary:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260427-163038.summary.txt`
4. version UART:
   `smoke-evidence/serial-diag/serial-app-version-capture-20260427T163009Z.log`
5. runtime gate UART:
   `smoke-evidence/serial-diag/serial-runtime-gate-capture-20260427T164013Z.log`
6. gated smoke NDJSON:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260427-164055.ndjson`
7. gated smoke summary:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260427-164055.summary.txt`
8. memory evidence:
   `memory-evidence/exec-172f-hardware-runtime-default-staging.json`
9. memory evidence summary:
   `memory-evidence/exec-172f-hardware-runtime-default-staging.summary.txt`

Runtime evidence gate result:

1. `required=True`
2. `passed=True`
3. `has_update_heap_snapshot=True`
4. `has_app_runtime_heap_snapshot=True`
5. `has_staging_allocation=True`
6. staging row: `path=/SD:/apps/neuro_unit_app.llext`, `bytes=21400`,
   `source=static`, `provider=esp-spiram`

### EXEC-172G LLEXT Artifact Freshness Guard

`EXEC-172G` closes the local guardrail gap exposed by `EXEC-172F`: a staged
LLEXT artifact can exist while still being zero bytes, which is too late to
discover inside deploy prepare.

Implementation boundary:

1. Build/preflight/smoke script validation only.
2. No firmware behavior change.
3. No memory default, external staging default, Zenoh behavior, CBOR schema,
   CLI release marker, or hardware release policy change.

Script updates:

1. `build_neurolink.sh --preset unit-app` now checks that the source app
   artifact produced by the EDK build is non-empty before staging it.
2. The same build path verifies that the staged artifact under
   `build/neurolink_unit/llext/` is still non-empty after copy.
3. `preflight_neurolink_linux.sh` treats a missing or zero-byte artifact as
   invalid and reports `artifact_invalid` instead of considering the path ready.
4. `smoke_neurolink_linux.sh` auto-rebuilds the default artifact when it is
   missing or empty, then fails with a clear `missing or empty` message if it
   remains invalid.
5. `test_preflight_neurolink_linux.sh` now uses a non-empty default fixture and
   adds a regression for an empty custom artifact.

Validation passed:

1. `bash tests/scripts/test_preflight_neurolink_linux.sh`
2. `bash tests/scripts/test_build_neurolink.sh`
3. `bash tests/scripts/run_all_tests.sh` (`script_tests_passed=8`,
   `script_tests_failed=0`)
4. `git diff --check`

Next action:

1. Continue WS-3/WS-6 by investigating activate-time Zenoh/runtime pressure notices;
   stale LLEXT and zero-byte staged artifacts are now separately guarded.

### EXEC-172H Runtime Drop Notice Evidence

`EXEC-172H` adds structured evidence for activate-time dropped-message notices
while preserving the corrected interpretation: these lines are Zenoh/runtime
pressure notices, not evidence-log loss.

Implementation boundary:

1. Evidence tooling only.
2. No firmware behavior change.
3. No memory default, external staging default, Zenoh behavior, CBOR schema,
   CLI behavior, release marker, or hardware release policy change.
4. Runtime evidence gate semantics remain unchanged.

Collector updates:

1. Runtime log lines are cleaned of ANSI control sequences before evidence
   fields are parsed.
2. `--- N messages dropped ---` lines are parsed into
   `runtime_drop_notices`.
3. Summaries include `[runtime_drop_notices]` with notice count,
   total dropped-message count, and interpretation
   `zenoh_runtime_pressure_notice_not_evidence_loss`.
4. The runtime evidence gate still depends only on update heap snapshots,
   app-runtime heap snapshots, and staging allocation rows.

Evidence snapshot:

1. generated JSON:
   `memory-evidence/exec-172h-runtime-drop-notice-evidence.json`
2. generated summary:
   `memory-evidence/exec-172h-runtime-drop-notice-evidence.summary.txt`
3. `total_dropped_messages=1571`
4. `interpretation=zenoh_runtime_pressure_notice_not_evidence_loss`
5. staging row remains clean: `provider=esp-spiram`
6. `runtime_evidence_gate.passed=True`

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile scripts/collect_neurolink_memory_evidence.py`
2. `bash tests/scripts/test_collect_neurolink_memory_evidence.sh`
3. `bash tests/scripts/run_all_tests.sh` (`script_tests_passed=8`,
   `script_tests_failed=0`)
4. `git diff --check`

Next action:

1. Continue WS-3/WS-6 with evidence-backed review of activate-time
   Zenoh/runtime pressure notices and logging configuration.

### EXEC-172I Zenoh-Pico Debug Default-Off

`EXEC-172I` applies the first WS-3/WS-6 pressure-tuning change after
`EXEC-172H` made activate-time dropped-message notices measurable.

Change boundary:

1. Unit release-default config now keeps zenoh-pico low-level debug disabled.
2. The diagnostic Kconfig switch remains available for explicit transport
   debug builds.
3. No Zenoh protocol behavior, memory default, external ELF staging default,
   runtime allocation policy, LLEXT debug level, CBOR schema, CLI behavior,
   release marker, or hardware release policy changed.

Implementation:

1. `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG` default changed from `y` to `n`.
2. DNESP32S3B board profile no longer forces zenoh-pico debug level 3.
3. Rebuilt Unit `.config` resolves:
   - `# CONFIG_NEUROLINK_ZENOH_PICO_DEBUG is not set`
   - `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL=0`
4. Memory evidence config capture now includes:
   - `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG`
   - `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL`

Evidence snapshot:

1. generated JSON:
   `memory-evidence/exec-172i-zenoh-debug-default-off.json`
2. generated summary:
   `memory-evidence/exec-172i-zenoh-debug-default-off.summary.txt`
3. summary records `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG=n`
4. summary records `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL=0`
5. summary keeps provider `esp-spiram`

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile scripts/collect_neurolink_memory_evidence.py`
2. `bash tests/scripts/test_collect_neurolink_memory_evidence.sh`
3. `bash tests/scripts/run_all_tests.sh` (`script_tests_passed=8`,
   `script_tests_failed=0`)
4. `bash scripts/build_neurolink.sh --preset unit --no-c-style-check`
5. `git diff --check`

Next action:

1. Run hardware smoke with the debug-off firmware path and compare
   `runtime_drop_notices` against `EXEC-172H` before deciding whether further
   logger buffer or logger mode tuning is needed.

### EXEC-172J Debug-Off Hardware Smoke and LLEXT Freshness Rule

`EXEC-172J` runs one bounded hardware smoke on the debug-off Unit firmware and
adds a smoke-script guardrail to prevent stale default LLEXT app deployment.

Loop-control boundary:

1. This closes the long `EXEC-172` evidence/tuning loop.
2. Future release-1.1.7 development slices should use the next execution
   number instead of extending `EXEC-172` further.
3. The first shortened prepare attempt is recorded as an invalid smoke attempt,
   not as firmware failure: 20 seconds was too short to wait for Wi-Fi ready.

Hardware result:

1. WSL serial was restored with `prepare_dnesp32s3b_wsl.sh --attach-only`.
2. BUSID `8-4` attached as `/dev/ttyACM0`.
3. Debug-off Unit firmware flashed successfully.
4. Board reached `NETWORK_READY`, IPv4 `192.168.2.69`.
5. Hardware smoke passed.
6. Passed smoke steps:
   - `query_device`
   - `lease_acquire_activate`
   - `deploy_prepare`
   - `deploy_verify`
   - `deploy_activate`
   - `monitor_events`

LLEXT freshness rule:

1. Before the successful smoke, the default LLEXT app was rebuilt and verified.
2. Source and staged artifacts were both `21400` bytes.
3. Staged artifact contained build id
   `neuro_unit_app-1.1.7-dev-cbor-v2`.
4. `smoke_neurolink_linux.sh` now rebuilds the default
   `build/neurolink_unit/llext/neuro_unit_app.llext` on every smoke run before
   artifact validation.
5. Custom `--artifact-file` paths remain caller-supplied and must be non-empty.

Evidence:

1. smoke summary:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260428-131827.summary.txt`
2. smoke NDJSON:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260428-131827.ndjson`
3. memory/config JSON:
   `memory-evidence/exec-172j-debug-off-hardware-smoke.json`
4. memory/config summary:
   `memory-evidence/exec-172j-debug-off-hardware-smoke.summary.txt`
5. config confirms `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG=n`
6. config confirms `CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL=0`

Evidence limitation:

1. The smoke command evidence proves deploy/activate passed with the fresh
   LLEXT artifact.
2. The prepare UART capture did not include activation runtime heap/staging or
   app-version lines, so `EXEC-172J` is a smoke/config proof rather than a new
   runtime evidence gate comparison.

Validation passed:

1. `bash -n scripts/smoke_neurolink_linux.sh`
2. `bash tests/scripts/run_all_tests.sh` (`script_tests_passed=8`,
   `script_tests_failed=0`)
3. `git diff --check`

### EXEC-173A Neuro CLI Status Classification

`EXEC-173A` closes the `EXEC-172` loop and starts the next release-1.1.7
mainline slice: `neuro_cli` reliability.

Goal:

1. Do not infer command success from process return code or transport-level
   reply success alone.
2. Treat nested Unit reply payload failure statuses as command failures.
3. Preserve non-failure operational statuses such as `ready`.

Implementation:

1. Added explicit payload failure status sets in core CLI and the skill wrapper.
2. Core `result_has_reply_error()` now treats nested reply failure statuses as
   command failures.
3. Wrapper nested `status=not_implemented` maps to capability-gap exit `3`.
4. Wrapper nested `status=error` maps to command failure exit `2`, even when
   the subprocess return code is zero.

Failure statuses currently classified:

1. `error`
2. `not_implemented`
3. `invalid_input`
4. `query_failed`
5. `no_reply`
6. `error_reply`

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
2. focused CLI result: `67 passed`

Next action:

1. Continue `EXEC-173B` with broader CLI command-path tests and script
   integration coverage for query/deploy/lease workflows.

### EXEC-173B Neuro CLI Command-Path Tests

`EXEC-173B` expands command-path regression coverage for high-frequency
operator workflows without changing runtime CLI behavior.

Goal:

1. Exercise grouped command paths through `main()` rather than only testing
   individual handlers.
2. Keep `EXEC-173` focused on `neuro_cli` reliability.
3. Avoid hardware, firmware config, smoke behavior, or release-marker churn.

Coverage added:

1. `query device` fails when the nested reply payload reports `status=error`.
2. `lease acquire` sends expected `resource`, `lease_id`, and `ttl_ms` through
   the grouped path.
3. `deploy activate` sends expected `lease_id` and `start_args` through the
   grouped path.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile neuro_cli/src/neuro_cli.py neuro_cli/scripts/invoke_neuro_cli.py neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. focused CLI result: `70 passed`
4. `bash tests/scripts/run_all_tests.sh` (`script_tests_passed=8`,
   `script_tests_failed=0`)
5. `git diff --check`

Next action:

1. Continue `EXEC-173C` with CLI/script integration polish around
   operator-facing smoke/preflight output and failure summaries.

### EXEC-173C Smoke Failure Summary

`EXEC-173C` improves the Linux smoke operator failure summary without changing
hardware state, firmware config, runtime memory defaults, external staging
defaults, or release identity.

Goal:

1. Preserve the `EXEC-173A` rule that command success must inspect nested Unit
   payload status, not only transport/process success.
2. Make bounded smoke failures identify the first failed operator step in the
   summary file.
3. Keep the change script-only and avoid reopening the closed `EXEC-172`
   hardware/debug loop.

Implementation:

1. Added `failed_step` and `failure_exit_code` to smoke summary output.
2. Added `run_smoke_step()` to centralize first-failure recording for
   query/lease/deploy/monitor smoke steps.
3. Expanded smoke nested reply status classification to fail on:
   `error`, `not_implemented`, `invalid_input`, `query_failed`, `no_reply`, and
   `error_reply`.
4. Added lightweight script regression coverage for smoke syntax, summary
   fields, and nested failure-status sentinels.
5. Wired the new smoke script check into `tests/scripts/run_all_tests.sh`.

Validation passed:

1. `bash -n applocation/NeuroLink/scripts/smoke_neurolink_linux.sh`
2. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
3. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
4. `git -C applocation/NeuroLink diff --check`

Next action:

1. Continue `EXEC-173D` with remaining CLI/operator workflow polish before
   returning to memory optimization and external staging candidate evaluation.

### EXEC-173D CLI Nested Failure Diagnostics

`EXEC-173D` closes another CLI reliability gap: when core CLI compatibility
keeps top-level `status=error_reply`, the concrete nested Unit payload status
must still be visible to operators and wrappers.

Goal:

1. Preserve compatibility for callers that already key on `status=error_reply`.
2. Expose the concrete nested failure status in machine-readable CLI JSON.
3. Keep wrapper exit classification accurate for nested capability gaps.

Implementation:

1. Added `result_failure_status()` in core CLI to extract the concrete failure
   status from top-level or nested reply payloads.
2. Query retry classification now writes `failure_status` when a nested Unit
   reply forces top-level `status=error_reply`.
3. Wrapper classification now inspects nested reply statuses before top-level
   `error_reply`, so nested `not_implemented` maps to exit `3` even when the
   core CLI process returned a generic command failure.
4. Added regressions for nested `error`, nested `not_implemented`, and wrapped
   `error_reply` containing nested `not_implemented`.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile neuro_cli/src/neuro_cli.py neuro_cli/scripts/invoke_neuro_cli.py neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. focused CLI result: `72 passed`
4. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
5. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
6. `git -C applocation/NeuroLink diff --check`

Next action:

1. Return to release-1.1.7 memory optimization with a bounded external staging
   candidate comparison, keeping external/PSRAM staging opt-in until hardware
   evidence supports changing defaults.

### EXEC-174A External Staging Candidate Gate

`EXEC-174A` returns to the memory optimization track by making external-staging
candidate evidence machine-checkable before any provider-specific default can be
considered.

Goal:

1. Keep external/PSRAM staging opt-in under current release defaults.
2. Add an explicit evidence gate for future provider-specific external staging
   trials.
3. Avoid a hardware smoke or default promotion in this slice.

Implementation:

1. Added `external_staging_candidate_gate` to memory evidence JSON and summary
   output.
2. Added `--require-external-staging-evidence` to fail collection unless:
   external memory is configured, external ELF staging is preferred by config,
   and runtime logs prove `source=external` staging allocation.
3. Added focused collector tests for both the conservative static/default path
   and a mocked passing `esp-spiram` external-staging candidate.
4. Generated current build evidence with the new gate fields.

Current default evidence:

1. `memory-evidence/exec-174a-external-staging-candidate-gate.summary.txt`
2. `provider=esp-spiram`
3. `external_memory_configured=True`
4. `external_elf_staging_preferred=False`
5. `has_external_staging_allocation=False`

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile scripts/collect_neurolink_memory_evidence.py`
2. `bash applocation/NeuroLink/tests/scripts/test_collect_neurolink_memory_evidence.sh`
3. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
4. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
5. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
6. focused CLI result: `72 passed`
7. `git -C applocation/NeuroLink diff --check`

Next action:

1. Use the new gate for a bounded hardware external-staging candidate run before
   considering any memory-default or static-buffer-size change.

### EXEC-174B External Staging Hardware Candidate

`EXEC-174B` uses the `EXEC-174A` gate on real DNESP32S3B hardware. The result
rejects external ELF staging as a release-default candidate for the current
evidence path.

Goal:

1. Build an external-staging candidate without editing `prj.conf`.
2. Run a bounded hardware candidate and stop after a decisive pass/fail signal.
3. Restore and revalidate the conservative default path after the candidate.

Implementation:

1. Added Linux `--overlay-config` support to `build_neurolink.sh`.
2. Added collector `--overlay-config` forwarding when `--run-build` is used.
3. Added `neuro_unit/overlays/external_staging_candidate.conf` with:
   - `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=y`
   - `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
4. Added collector parsing for `runtime_fatal_exceptions` from Zephyr fatal logs.
5. Added script tests for overlay support and fatal parsing.

Candidate build evidence:

1. build dir: `build/neurolink_unit_ext_staging_candidate`
2. evidence: `memory-evidence/exec-174b-external-staging-build-candidate.summary.txt`
3. config: `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=y`
4. config: `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
5. candidate gate before runtime: `passed=False`, missing `external_staging_allocation`

Hardware candidate result:

1. candidate firmware flash to `/dev/ttyACM0`: PASS
2. candidate board prepare: PASS, `NETWORK_READY`, IPv4 `192.168.2.69`
3. candidate smoke evidence: `smoke-evidence/exec-174b-external-staging/SMOKE-017B-LINUX-001-20260428-152441.summary.txt`
4. smoke failed at `deploy_activate`, `failure_exit_code=2`
5. UART evidence: `smoke-evidence/serial-diag/exec-174b-external-staging-runtime-20260428T152424Z.log`
6. fatal evidence: `FATAL EXCEPTION`, `EXCCAUSE 2 (instr fetch error)`, `PC 0x3c0c7718`, `VADDR 0x3c0c7718`
7. structured evidence: `memory-evidence/exec-174b-external-staging-hardware-candidate.summary.txt`
8. structured gate: `external_staging_candidate_gate.passed=False`, missing `external_staging_allocation`

Recovery result:

1. conservative default firmware reflashed to `/dev/ttyACM0`: PASS
2. board prepared back to `NETWORK_READY`: PASS
3. restored-default smoke: `smoke-evidence/exec-174b-restored-default/SMOKE-017B-LINUX-001-20260428-153134.summary.txt`
4. restored-default smoke result: PASS

Validation passed:

1. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
2. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
4. focused CLI result: `72 passed`
5. `git -C applocation/NeuroLink diff --check`

Decision:

1. Do not promote external/PSRAM ELF staging defaults in release-1.1.7 on the
   current DNESP32S3B evidence path.
2. Keep the safe release defaults:
   - `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
   - `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
   - `CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`

### EXEC-175A Conservative Heap Trim Promotion

`EXEC-175A` starts Kconfig tuning with a single isolated general-heap candidate.
It intentionally leaves stack sizes, network buffer counts, static ELF staging,
and external/PSRAM staging defaults unchanged.

Goal:

1. Reduce internal DRAM pressure without repeating the `40960` heap regression.
2. Prove the candidate through build evidence, runtime heap/staging evidence,
   and bounded hardware smoke.
3. Promote only after the default build path reproduces the candidate result.

Implementation:

1. Added `neuro_unit/overlays/heap_trim_candidate.conf`:
   - `CONFIG_HEAP_MEM_POOL_SIZE=53248`
   - `CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`
   - `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
   - `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
2. Added script-test sentinels for the heap-trim overlay.
3. Built `build/neurolink_unit_heap_trim_candidate` and collected candidate
   evidence.
4. Built a fresh candidate LLEXT from the candidate EDK before hardware smoke.
5. Promoted `CONFIG_HEAP_MEM_POOL_SIZE=53248` into `neuro_unit/prj.conf` after
   the candidate runtime gate and hardware smoke passed.
6. Rebuilt `build/neurolink_unit`, rebuilt a fresh default LLEXT, flashed the
   promoted default, prepared the board, and ran default smoke.

Evidence:

1. default build reference: `memory-evidence/exec-175a-default-build-reference.summary.txt`
2. heap-trim build candidate: `memory-evidence/exec-175a-heap-trim-build-candidate.summary.txt`
3. heap-trim hardware candidate: `memory-evidence/exec-175a-heap-trim-hardware-candidate.summary.txt`
4. promoted default build: `memory-evidence/exec-175a-promoted-default-build.summary.txt`
5. candidate smoke: `smoke-evidence/exec-175a-heap-trim-candidate/SMOKE-017B-LINUX-001-20260428-161027.summary.txt`
6. candidate runtime smoke: `smoke-evidence/exec-175a-heap-trim-candidate-runtime/SMOKE-017B-LINUX-001-20260428-161142.summary.txt`
7. candidate UART runtime log: `smoke-evidence/serial-diag/exec-175a-heap-trim-runtime-20260428T161116Z.log`
8. promoted default smoke: `smoke-evidence/exec-175a-promoted-default/SMOKE-017B-LINUX-001-20260428-161722.summary.txt`

Measured result:

1. `CONFIG_HEAP_MEM_POOL_SIZE`: `57344` -> `53248`
2. build `dram0`: `392548` -> `388452` (`-4096B`)
3. promoted build summary: `dram0_0_seg=391240B/399108B (98.03%)`
4. runtime gate: PASS with update heap, app-runtime heap, and staging allocation
5. runtime staging allocation: `bytes=21500`, `source=static`, `provider=esp-spiram`
6. no fatal exception found in supplied runtime log
7. candidate hardware smoke: PASS
8. promoted default hardware smoke: PASS

Validation passed:

1. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
2. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
4. focused CLI result: `72 passed`
5. `git -C applocation/NeuroLink diff --check`

Decision:

1. Promote `CONFIG_HEAP_MEM_POOL_SIZE=53248` as the release-1.1.7 default.
2. Keep stack sizes and network buffer counts unchanged until their own isolated
   candidates pass the same evidence gates.
3. Keep external/PSRAM ELF staging disabled and static internal staging as the
   release path.

### EXEC-175B Main Stack Trim Promotion

`EXEC-175B` continues Kconfig tuning with two isolated candidates. The
network-buffer candidate was rejected because it did not reduce internal DRAM.
The main-stack candidate passed build, runtime, and hardware gates and was
promoted.

Goal:

1. Test whether network buffer count reductions help internal DRAM before taking
   hardware risk.
2. Test a bounded main stack reduction with no workqueue, shell, heap, network,
   or staging changes.
3. Promote only after the default path reproduces the candidate result and
   hardware smoke passes.

Rejected network-buffer candidate:

1. Added `neuro_unit/overlays/net_buf_trim_candidate.conf`:
   - `CONFIG_NET_BUF_RX_COUNT=44`
   - `CONFIG_NET_BUF_TX_COUNT=44`
   - `CONFIG_NET_PKT_RX_COUNT=20`
   - `CONFIG_NET_PKT_TX_COUNT=20`
2. Evidence: `memory-evidence/exec-175b-net-buf-trim-build-candidate.summary.txt`
3. Kconfig accepted the values.
4. Internal DRAM did not change: `dram0_delta=0`.
5. Only external RAM changed: `ext_ram_delta=-1248`.
6. Decision: reject; do not trade network headroom for no internal DRAM gain.

Promoted main-stack candidate:

1. Added `neuro_unit/overlays/main_stack_trim_candidate.conf`:
   - `CONFIG_MAIN_STACK_SIZE=18432`
   - `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=6144`
   - `CONFIG_SHELL_STACK_SIZE=4096`
   - `CONFIG_HEAP_MEM_POOL_SIZE=53248`
   - external/PSRAM ELF staging disabled
   - static ELF staging `24576`
2. Built `build/neurolink_unit_main_stack_trim_candidate` and collected build
   evidence.
3. Built a fresh candidate LLEXT from the candidate EDK before hardware smoke.
4. Ran candidate hardware smoke and a second candidate smoke under UART capture.
5. Promoted `CONFIG_MAIN_STACK_SIZE=18432` into `neuro_unit/prj.conf` after the
   runtime gate and hardware smoke passed.
6. Rebuilt `build/neurolink_unit`, rebuilt a fresh default LLEXT, flashed the
   promoted default, prepared the board, and ran default smoke.

Evidence:

1. main-stack build candidate: `memory-evidence/exec-175b-main-stack-trim-build-candidate.summary.txt`
2. main-stack hardware candidate: `memory-evidence/exec-175b-main-stack-trim-hardware-candidate.summary.txt`
3. promoted default build: `memory-evidence/exec-175b-promoted-default-build.summary.txt`
4. candidate smoke: `smoke-evidence/exec-175b-main-stack-candidate/SMOKE-017B-LINUX-001-20260428-162942.summary.txt`
5. candidate runtime smoke: `smoke-evidence/exec-175b-main-stack-candidate-runtime/SMOKE-017B-LINUX-001-20260428-163039.summary.txt`
6. candidate UART runtime log: `smoke-evidence/serial-diag/exec-175b-main-stack-runtime-20260428T163024Z.log`
7. promoted default smoke: `smoke-evidence/exec-175b-promoted-default/SMOKE-017B-LINUX-001-20260428-163547.summary.txt`

Measured result:

1. `CONFIG_MAIN_STACK_SIZE`: `20480` -> `18432`
2. build `dram0`: `388452` -> `378212` (`-10240B`)
3. promoted build summary: `dram0_0_seg=381000B/399108B (95.46%)`
4. runtime gate: PASS with update heap, app-runtime heap, and staging allocation
5. runtime staging allocation: `bytes=21528`, `source=static`, `provider=esp-spiram`
6. no fatal exception found in supplied runtime log
7. candidate hardware smoke: PASS
8. promoted default hardware smoke: PASS

Validation passed:

1. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
2. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
4. focused CLI result: `72 passed`
5. `git -C applocation/NeuroLink diff --check`

Decision:

1. Promote `CONFIG_MAIN_STACK_SIZE=18432` as the release-1.1.7 default.
2. Keep `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=6144`, `CONFIG_SHELL_STACK_SIZE=4096`,
   and network buffer counts unchanged.
3. Keep `CONFIG_HEAP_MEM_POOL_SIZE=53248`, external/PSRAM ELF staging disabled,
   and static internal staging as the release path.

### EXEC-175C Workqueue Stack Trim Promotion

`EXEC-175C` closes the remaining isolated stack candidate before moving to
`EXEC-176`. The candidate keeps the LLD hardening rule intact by leaving the
system workqueue stack explicitly sized, but tests one bounded reduction after
heap and main-stack tuning had already passed hardware proof.

Goal:

1. Test `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120` as the only functional
   Kconfig change in the candidate.
2. Preserve heap, main stack, shell stack, network-buffer counts, staging
   preferences, and release identity.
3. Promote only after build evidence, runtime evidence, candidate hardware
   smoke, and promoted-default smoke all pass with fresh LLEXT artifacts.

Promoted workqueue-stack candidate:

1. Added `neuro_unit/overlays/workqueue_stack_trim_candidate.conf`:
   - `CONFIG_MAIN_STACK_SIZE=18432`
   - `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120`
   - `CONFIG_SHELL_STACK_SIZE=4096`
   - `CONFIG_HEAP_MEM_POOL_SIZE=53248`
   - external/PSRAM ELF staging disabled
   - static ELF staging `24576`
2. Built `build/neurolink_unit_workqueue_stack_trim_candidate` and collected
   build evidence.
3. Built a fresh candidate LLEXT from the candidate EDK before hardware smoke.
4. Ran candidate hardware smoke and a second candidate smoke under UART capture.
5. Promoted `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120` into `neuro_unit/prj.conf`
   after the runtime gate and hardware smoke passed.
6. Rebuilt `build/neurolink_unit`, rebuilt a fresh default LLEXT, flashed the
   promoted default, prepared the board, and ran default smoke.

Evidence:

1. workqueue-stack build candidate: `memory-evidence/exec-175c-workqueue-stack-trim-build-candidate.summary.txt`
2. workqueue-stack hardware candidate: `memory-evidence/exec-175c-workqueue-stack-trim-hardware-candidate.summary.txt`
3. promoted default build: `memory-evidence/exec-175c-promoted-default-build.summary.txt`
4. candidate smoke: `smoke-evidence/exec-175c-workqueue-stack-candidate/SMOKE-017B-LINUX-001-20260428-165905.summary.txt`
5. candidate runtime smoke: `smoke-evidence/exec-175c-workqueue-stack-candidate-runtime/SMOKE-017B-LINUX-001-20260428-170039.summary.txt`
6. candidate UART runtime log: `smoke-evidence/serial-diag/exec-175c-workqueue-stack-runtime-20260428T170013Z.log`
7. promoted default smoke: `smoke-evidence/exec-175c-promoted-default/SMOKE-017B-LINUX-001-20260428-170806.summary.txt`

Measured result:

1. `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE`: `6144` -> `5120`
2. build `dram0`: `378212` -> `377188` (`-1024B`)
3. promoted build summary: `dram0_0_seg=379976B/399108B (95.21%)`
4. runtime gate: PASS with update heap, app-runtime heap, and staging allocation
5. runtime staging allocation: `bytes=21556`, `source=static`, `provider=esp-spiram`
6. no fatal, assert, or stack-overflow evidence found in supplied runtime log
7. candidate hardware smoke: PASS
8. promoted default hardware smoke: PASS

Validation passed:

1. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
2. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
4. focused CLI result: `72 passed`
5. `git -C applocation/NeuroLink diff --check`

Decision:

1. Promote `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120` as the release-1.1.7 default.
2. Keep `CONFIG_MAIN_STACK_SIZE=18432`, `CONFIG_SHELL_STACK_SIZE=4096`, and
   network buffer counts unchanged.
3. Keep `CONFIG_HEAP_MEM_POOL_SIZE=53248`, external/PSRAM ELF staging disabled,
   and static internal staging as the release path.
4. Move next to `EXEC-176` CLI/release-readiness work.

### EXEC-176 CLI Parse-Failure JSON Contract

`EXEC-176` starts the CLI JSON contract, parser, retry, and
failure-classification polish after the memory tuning slices. The first slice
focuses on unreadable OK reply payloads, especially invalid or truncated CBOR,
so operators and Agent wrappers get a stable machine-readable failure instead
of a generic reply error.

Goal:

1. Preserve stable JSON output when a Zenoh OK reply carries an unreadable
   payload.
2. Classify parse failures separately from `no_reply`, `query_failed`, and
   nested Unit `status: error` replies.
3. Keep parse failures non-transient so retry reporting does not imply a router
   or board reachability issue.
4. Keep wrapper exit behavior strict for Agent/skill callers.

Implemented behavior:

1. `neuro_protocol.parse_reply()` now returns `status=parse_failed` with the
   reply key expression and parse error for OK replies whose payload cannot be
   decoded.
2. Actual Zenoh error replies still use the existing error-payload fallback.
3. `neuro_cli.collect_query_result()` preserves top-level `parse_failed` rather
   than collapsing it to `error_reply`.
4. `collect_query_result_with_retry()` records `failure_status=parse_failed` and
   treats the parse failure as non-retryable.
5. `invoke_neuro_cli.py` treats top-level `parse_failed` as command-failed exit
   `2`.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile neuro_cli/src/neuro_protocol.py neuro_cli/src/neuro_cli.py neuro_cli/scripts/invoke_neuro_cli.py neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. focused CLI result: `75 passed`
4. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
5. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
6. `git -C applocation/NeuroLink diff --check`

Decision:

1. Keep `parse_failed` as a stable CLI JSON contract status for unreadable OK
   reply payloads.
2. Keep release identity at `1.1.6` until final closure.
3. Continue `EXEC-176` with any remaining high-value JSON envelope and retry
   reporting gaps before `EXEC-177` workflow/skill alignment.

### EXEC-176B CLI Session and Handler Failure Envelopes

`EXEC-176B` continues the CLI JSON contract work by covering dependency and
handler failures around the top-level `main()` path. These failures previously
risked escaping as process exceptions instead of stable JSON, which is awkward
for operators and brittle for Agent/skill wrappers.

Goal:

1. Keep JSON output stable when Zenoh session open fails after retries.
2. Keep JSON output stable when a command handler raises after the session opens.
3. Preserve the existing session close behavior on handler failures.
4. Keep wrapper exit behavior strict for these new failure statuses.

Implemented behavior:

1. Final session-open failures now emit `status=session_open_failed` under
   `--output json`.
2. Handler exceptions after session open now emit `status=handler_failed` under
   `--output json`.
3. The existing `finally` path still closes an opened session after handler
   failure.
4. `invoke_neuro_cli.py` treats `session_open_failed` and `handler_failed` as
   command-failed exit `2`.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile neuro_cli/src/neuro_protocol.py neuro_cli/src/neuro_cli.py neuro_cli/scripts/invoke_neuro_cli.py neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. focused CLI result: `77 passed`
4. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
5. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
6. `git -C applocation/NeuroLink diff --check`

Decision:

1. Keep `session_open_failed` and `handler_failed` as stable CLI JSON contract
   statuses for top-level dependency/handler failures.
2. Keep release identity at `1.1.6` until final closure.
3. Move to `EXEC-177` if no further high-value CLI JSON/retry gaps are found.

### EXEC-177 Workflow, Skill, and Evidence Alignment

`EXEC-177` aligns the live CLI workflow plans with the project-shared
`neuro-cli` skill so Agents can discover supported evidence and release closure
commands through structured JSON instead of hand-assembling command lines from
static prose.

Goal:

1. Expose memory evidence collection through `workflow plan` JSON.
2. Expose callback smoke through `workflow plan` JSON using the wrapper's real
   argument contract.
3. Expose the final release closure gate sequence as a non-executing plan.
4. Keep skill references synchronized with live CLI command names and failure
   classifications.

Implemented behavior:

1. Added `workflow plan memory-evidence` for the build-time memory evidence
   collector and `applocation/NeuroLink/memory-evidence` artifact path.
2. Added `workflow plan callback-smoke` for the CLI wrapper callback smoke path.
3. Added `workflow plan release-closure` listing memory evidence, Python
   compile, focused CLI tests, script tests, whitespace check, preflight, and
   smoke gates without executing them.
4. Updated `.github/skills/neuro-cli/SKILL.md` and
   `.github/skills/neuro-cli/references/workflows.md` to point Agents at live
   workflow plans for memory evidence, callback smoke, and release closure.
5. Captured the wrapper contract detail that `invoke_neuro_cli.py` injects
   `--output json` into `neuro_cli.py`; workflow plans should not put
   `--output` at the wrapper layer.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile neuro_cli/src/neuro_protocol.py neuro_cli/src/neuro_cli.py neuro_cli/scripts/invoke_neuro_cli.py neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
2. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
3. focused CLI result: `81 passed`
4. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence`
5. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke`
6. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan release-closure`
7. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
8. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
9. `git -C applocation/NeuroLink diff --check`

Decision:

1. Keep the new workflow plan names as the Agent-facing interface for memory
   evidence, callback smoke, and release closure discovery.
2. Keep release identity at `1.1.6` until final closure evidence passes.
3. Move next to `EXEC-178` operator polish or release closure dry-run planning.

### EXEC-178 Local Closure Gates and Memory Delta Review

`EXEC-178` runs the local closure gates and compares the current release-1.1.7
defaults against the original release-1.1.6 memory baseline and the promoted
`EXEC-175C` default. This slice intentionally avoids hardware smoke and release
identity promotion; those remain `EXEC-179` work.

Goal:

1. Capture fresh build-time memory evidence for the current default.
2. Confirm current defaults have not drifted from the promoted `EXEC-175C`
   values.
3. Quantify internal DRAM delta against the original release-1.1.6 baseline.
4. Re-run local Python, shell, wrapper-plan, and native_sim Unit gates.

Evidence:

1. `applocation/NeuroLink/memory-evidence/exec-178-local-closure.json`
2. `applocation/NeuroLink/memory-evidence/exec-178-local-closure.summary.txt`

Memory result:

1. Current default `dram0=377188`, `iram0=66216`, `flash=673780`,
   `ext_ram=2847776`.
2. Original `baseline-1.1.6-clean-build` was `dram0=392376`, `iram0=66216`,
   `flash=673292`, `ext_ram=2847776`.
3. Delta versus original baseline: `dram0=-15188`, `iram0=0`, `flash=+488`,
   `ext_ram=0`.
4. Delta versus `EXEC-175C` promoted default: `dram0=0`, `iram0=0`, `flash=0`,
   `ext_ram=0`.

Preserved defaults:

1. `CONFIG_HEAP_MEM_POOL_SIZE=53248`
2. `CONFIG_MAIN_STACK_SIZE=18432`
3. `CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120`
4. `CONFIG_SHELL_STACK_SIZE=4096`
5. `CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576`
6. `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n`
7. `CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n`
8. Network buffer counts unchanged.

Validation passed:

1. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py --run-build --no-c-style-check --label exec-178-local-closure`
2. memory evidence result: `section_total_dram0=377188`
3. `/home/emb/project/zephyrproject/.venv/bin/python -m py_compile neuro_cli/src/neuro_protocol.py neuro_cli/src/neuro_cli.py neuro_cli/scripts/invoke_neuro_cli.py neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py`
4. `/home/emb/project/zephyrproject/.venv/bin/python -m pytest neuro_cli/tests/test_neuro_cli.py neuro_cli/tests/test_invoke_neuro_cli.py -q`
5. focused CLI result: `81 passed`
6. `bash applocation/NeuroLink/tests/scripts/run_all_tests.sh`
7. script suite result: `script_tests_passed=9`, `script_tests_failed=0`
8. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan memory-evidence`
9. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan callback-smoke`
10. `/home/emb/project/zephyrproject/.venv/bin/python applocation/NeuroLink/neuro_cli/scripts/invoke_neuro_cli.py workflow plan release-closure`
11. `source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate && west build -b native_sim applocation/NeuroLink/neuro_unit/tests/unit --build-dir build/neurolink_unit_ut_check -p always -t run`
12. native_sim Unit result: `PROJECT EXECUTION SUCCESSFUL`
13. `git -C applocation/NeuroLink diff --check`

Decision:

1. Accept the local closure state as stable for the current default.
2. Keep `RELEASE_TARGET = "1.1.6"` until hardware closure passes.
3. Move next to `EXEC-179` hardware closure, fresh LLEXT, callback freshness,
   and release identity promotion only if all hardware gates pass.

### EXEC-179 Hardware Closure Attempt Blocked by Serial Enumeration

`EXEC-179` started the hardware closure path, but the serial-required gate
blocked before smoke/deploy closure could be accepted.

Observed blocker:

1. Serial-required preflight result: `status=serial_device_missing`, `ready=0`,
   `serial_present=0`.
2. No `/dev/ttyACM*` or `/dev/ttyUSB*` device is visible on the Linux host.
3. Kernel log shows prior `cdc_acm ... ttyACM0` enumeration followed by
   `usb 1-1: USB disconnect`.
4. Linux smoke also stopped in its preflight step with the same serial blocker.

Still healthy:

1. Router port `7447` is listening.
2. `query device` over Zenoh returns `status=ok`, `session_ready=true`,
   `network_state=NETWORK_READY`, and `ipv4=192.168.2.69`.
3. `query apps` returns one running `neuro_unit_app` with active artifact state.

Freshness action:

1. Rebuilt/copied the canonical LLEXT after the blocked attempt.
2. `build/neurolink_unit/llext/neuro_unit_app.llext` is non-empty at `21400`
   bytes.
3. A later full smoke must still rebuild fresh LLEXT again after serial
   visibility is restored.

Decision:

1. Do not accept hardware closure while serial-required preflight is blocked.
2. Do not promote `RELEASE_TARGET`; it remains `1.1.6`.
3. Resume `EXEC-179` after `/dev/ttyACM*` or `/dev/ttyUSB*` visibility returns,
   then rerun serial-required preflight, fresh-LLEXT smoke, callback freshness,
   deploy/query closure, and release identity promotion only if all gates pass.

### EXEC-179B Hardware Closure and Release Identity Promotion

`EXEC-179B` resumed after USB was reconnected and closes release-1.1.7 against
current hardware and local evidence.

Hardware restoration:

1. `prepare_dnesp32s3b_wsl.sh --attach-only` restored BUSID `8-4` as
   `/dev/ttyACM0`.
2. Full board preparation restored `unit-01` to `NETWORK_READY` with IPv4
   `192.168.2.69`.
3. Serial-required preflight returned `status=ready`.

Fresh LLEXT and smoke evidence:

1. Final LLEXT artifact: `build/neurolink_unit/llext/neuro_unit_app.llext`.
2. Final artifact size: `21520` bytes.
3. Final artifact build id: `neuro_unit_app-1.1.7-cbor-v2`.
4. Full Linux smoke PASS:
   `smoke-evidence/SMOKE-017B-LINUX-001-20260428-184958.ndjson`.

Callback freshness root cause and fix:

1. UART capture showed Unit published callback events at
   `neuro/unit-01/event/app//callback`.
2. The CLI was correctly subscribed to
   `neuro/unit-01/event/app/neuro_unit_app/**`, so it received no events from
   the malformed app-event route.
3. The sample LLEXT app now publishes callback events with a stable local
   `app_id` value instead of reading `app_runtime_manifest.app_name` from the
   LLEXT manifest during event construction.
4. Final callback smoke passed with
   `--expected-app-echo neuro_unit_app-1.1.7-cbor-v2 --trigger-every 1 --invoke-count 2`.
5. The final callback smoke captured three CBOR `callback_event` payloads on
   `neuro/unit-01/event/app/neuro_unit_app/callback`, each with
   `app_id=neuro_unit_app`.

Release identity:

1. `RELEASE_TARGET` promoted from `1.1.6` to `1.1.7`.
2. Sample app version promoted to `1.1.7`.
3. Sample app build id promoted to `neuro_unit_app-1.1.7-cbor-v2`.
4. Live capabilities JSON reports `release_target: 1.1.7`.

Memory closure evidence:

1. `memory-evidence/exec-179-release-closure.json`.
2. `memory-evidence/exec-179-release-closure.summary.txt`.
3. Final closure evidence reports `release_target=1.1.7` and `dram0=377188`.
4. This preserves the `15188B` internal DRAM improvement against the
   release-1.1.6 clean baseline.

Final validation:

1. Final LLEXT rebuild and embedded build-id check PASS.
2. Python compile PASS.
3. Focused CLI suite PASS: `81 passed`.
4. Clean-environment script suite PASS: `9/9`.
5. Full Linux smoke PASS.
6. Callback freshness PASS.
7. Smoke lease cleanup PASS: `query leases` returned an empty list.
8. `git diff --check` PASS.

Decision:

1. Accept release-1.1.7 hardware and local closure evidence.
2. Keep external/PSRAM ELF staging disabled by default.
3. Preserve the promoted DRAM-first defaults.
4. Treat release-1.1.7 as closed against the current workspace state.


