# NeuroLink Release 1.1.10 Pre-Research Baseline

## 1. Scope

Release 1.1.10 starts from the closed release-1.1.9 Linux/hardware baseline and
focuses on a cross-board LLEXT app demo platform for `neuro_unit`. The release
will add a family of standalone demo apps that exercise hardware interfaces,
network/event behavior, and one integrated scenario while keeping the app API
portable across future boards.

Primary objectives:

1. Add a first-class multi-app LLEXT build and staging path so demos are built,
   deployed, and validated as separate artifacts instead of overloading the
   existing `neuro_unit_app` sample.
2. Define a demo catalog with stable app ids, commands, replies, event names,
   capability flags, resource budgets, and hardware requirements.
3. Extend the public LLEXT app API conservatively so demos can discover board
   capabilities and report unsupported hardware cleanly.
4. Implement hardware interface demos for I2C/IIC, SPI, GPIO, UART, ADC, and
   PWM where the board exposes safe capability mappings.
5. Implement network demos through the existing Unit event/Zenoh bridge first,
   with raw TCP/UDP kept behind an explicit capability gate.
6. Implement callback event behavior in every demo where the stable callback
   app API can be used without unsafe board assumptions. Demos that cannot
   support callback events must document the blocking reason in their slice.
7. Implement an integrated demo that combines hardware sampling or simulated
   input with app events and safe output behavior.
8. Close the release on DNESP32S3B hardware while preserving cross-board
   behavior through capability discovery and graceful unsupported responses.

Architecture boundary:

1. `neuro_unit` remains the framework and platform layer: communication,
   protected update/deploy, app loading, app lifecycle management, command
   dispatch, event transport, and stable app ABI helpers.
2. Hardware demos own their hardware dependencies. They must use Zephyr driver
   APIs, devicetree aliases, overlays, and compile-time capability checks from
   inside the app subproject to stay portable across boards.
3. Do not add Unit-side hardware helper APIs such as GPIO/I2C/SPI/UART wrappers
   to make demo apps smaller. Artifact size or loader pressure must be solved
   through app build structure, app-side device-tree contracts, LLEXT loader
   evidence, or general platform resource policy, not by moving hardware
   responsibility into Unit.

Out of scope for kickoff:

1. Promoting `RELEASE_TARGET` from `1.1.9` to `1.1.10` before local and hardware
   closure evidence is complete.
2. Requiring a second physical board before the demo API and DNESP32S3B evidence
   path are stable.
3. Adding Unit-side board-specific hardware wrappers for demos. Hardware
   portability belongs in each app's Zephyr devicetree usage and graceful
   unsupported responses.
4. Changing the release-1.1.9 conservative LLEXT memory/staging policy unless a
   candidate passes the existing memory evidence gates.

## 2. Current Baseline

Release-1.1.9 is closed in `PROJECT_PROGRESS.md`. Release-1.1.10 is now closed
at the completed demo-platform cutoff: GPIO, UART, SPI, ADC/PWM, I2C/AP3216C,
and net-event are included; UDP and integrated demo work are deferred to the
next release. The CLI release marker is promoted to `RELEASE_TARGET = "1.1.10"`.

Current implementation facts:

1. `subprojects/neuro_unit_app` is the only standalone LLEXT app subproject.
2. `scripts/build_neurolink.sh` builds and stages only `neuro_unit_app.llext`
   through the `unit-app` / `unit-ext` presets.
3. `neuro_unit_app_api.h` exposes stable app helpers for JSON extraction,
   callback events, app events, and standard command replies.
4. Unit-side exported app symbols are intentionally small: event helpers,
   callback/reply helpers, JSON helpers, and `snprintf`.
5. The manifest already contains capability flags for storage, network, sensor,
   actuator, UI, and crypto demos.
6. DNESP32S3B is the current real-hardware closure board; future boards require
   explicit capability mapping instead of implicit device-name assumptions.

## 3. Demo Catalog Draft

Initial demo app ids and release intent:

1. `neuro_demo_i2c`: I2C/IIC scanner plus optional sensor-style read behavior.
2. `neuro_demo_spi`: SPI transfer and loopback/selftest behavior where wiring is
   available; otherwise safe readiness probing.
3. `neuro_demo_gpio`: LED/button-style read, write, and toggle behavior through
   board-safe aliases.
4. `neuro_demo_uart`: UART readiness and echo/probe behavior where a safe test
   UART is configured.
5. `neuro_demo_adc_pwm`: bounded ADC read plus PWM output behavior using safe
   ranges and explicit board metadata.
6. `neuro_demo_net_event`: Unit event/Zenoh bridge publish/subscribe demo.
7. `neuro_demo_net_udp`: TCP/UDP candidate demo, gated on deliberate Unit-side
   network helper support.
8. `neuro_demo_integrated`: combined hardware sampling or simulated input,
   optional output action, and structured app event publishing.

The existing `neuro_unit_app` remains the lifecycle and callback reference app.

## 4. Execution Plan

### EXEC-198 Kickoff and Multi-App Build Foundation

1. Add this release planning document and record the 1.1.10 kickoff in the
   progress ledger.
2. Extend `build_neurolink.sh` so LLEXT app presets can select an app id and
   source directory while preserving the legacy default `neuro_unit_app` path.
3. Add script regressions for app id validation, source directory validation,
   and legacy default behavior.
4. Keep firmware behavior, app ABI, hardware state, and release identity
   unchanged.

### EXEC-199 Demo Catalog and App API Capability Contracts

1. Add a small source-of-truth catalog for demo app ids, command names, expected
   events, and capability requirements.
2. Add app API DTOs for board capability discovery and unsupported results.
3. Add Unit native_sim coverage for the public API helpers and exported symbol
   boundary before any hardware demo depends on them.

Status update:

1. Added `subprojects/demo_catalog.json` as the machine-readable demo catalog for
   the first 1.1.10 app family.
2. Added public app API JSON writers for capability discovery and unsupported
   result replies through `neuro_unit_app_api.h` and the Unit event helper
   module.
3. Extended the public app API native_sim test suite with capability and
   unsupported-result contract coverage.
4. Added `tests/scripts/test_demo_catalog.sh` and promoted the script suite to a
   10-test baseline.
5. Fixed `build_neurolink.sh` so `--pristine-always` now applies even when the
   build directory is already configured; this keeps future EDK/demo-export
   refresh flows honest.

### EXEC-200 Demo Template and First Event Demo

1. Add a minimal demo app template that reuses the manifest, lifecycle, command,
   reply, and event patterns from `neuro_unit_app`.
2. Implement `neuro_demo_net_event` first because it can reuse the existing
   app-event bridge without new hardware driver dependencies.
3. Add selected-app build tests and a wrapper workflow plan for demo build and
   event smoke.

Status update:

1. Added the first real demo subproject at `subprojects/neuro_demo_net_event`.
2. The demo reuses the stable app ABI and supports `action=capability`,
   `action=publish`, and `action=selftest` through the existing `invoke`
   command contract.
3. The demo publishes through `neuro_unit_publish_app_event()` and returns the
   new capability/unsupported JSON reply contracts where appropriate.
4. Validated selected-app artifact generation through
   `build_neurolink.sh --preset unit-app --app neuro_demo_net_event` and
   confirmed the built artifact contains
   `neuro_demo_net_event-1.1.10-dev-cbor-v1`.
5. The selected-app build flow now also avoids CMake cache collisions by using
   app-specific external build directories for non-default app ids.

### EXEC-201 Hardware Demo API and I2C/GPIO First Slice

1. Add app-side devicetree alias and capability contracts for safe DNESP32S3B
   I2C and GPIO demo behavior.
2. Implement `neuro_demo_i2c` and `neuro_demo_gpio` with graceful unsupported
   responses where the board lacks configured aliases or safe wiring.
3. Implement callback event support for these demos when the existing public
   callback API is sufficient; treat callback omission as a documented blocker,
   not as a silent deferral.
4. Validate command JSON behavior locally and run bounded DNESP32S3B hardware
   proof for supported or unsupported classifications.

Status update:

1. Added `subprojects/neuro_demo_gpio` as the first hardware-facing demo
   subproject for release-1.1.10.
2. The demo reuses the stable `invoke` app command surface and supports
   `action=capability`, `action=read`, `action=write`, and `action=toggle`.
3. GPIO behavior is gated by safe devicetree aliases: `sw0` for input and
   `led0` for output. When those aliases are missing or not ready, the demo
   returns stable capability/unsupported JSON instead of assuming board-local
   pin numbers.
4. Updated `subprojects/demo_catalog.json` so `neuro_demo_gpio` is marked
   `implemented_local`.
5. Callback event support is required for this demo because the existing public
   app callback API is sufficient and does not require board-specific wiring.
6. Local validation passed for catalog-backed artifact generation through
   `build_neurolink_demo.sh --demo neuro_demo_gpio`; DNESP32S3B hardware proof
   remains pending because the current board baseline has no declared tested
   `sw0` / `led0` alias mapping in-tree.

Hardware closure update:

1. DNESP32S3B preflight reached `ready` with `/dev/ttyACM0`, router port
   `7447`, `NETWORK_READY`, and IPv4 `192.168.2.67`.
2. Current Unit firmware was flashed successfully and board prepare evidence was
   captured at
   `smoke-evidence/serial-diag/serial-capture-20260501T035809Z.log`.
3. Protected deploy must use short lease ids because the CBOR metadata DTO has
   `lease_id[32]`; long ids failed before dispatch with `CBOR request decode
   failed`. `l-gpio-deploy` acquired successfully.
4. `neuro_demo_gpio.llext` prepared and verified successfully at 54472 bytes,
   but activation failed at `runtime/load_file RESOURCE_LIMIT cause=-12
   ret=-20486` before invoke/callback smoke could run.
5. A debug-stripped 21852-byte artifact and a compile-time `-g0` 22016-byte
   artifact both avoided the staging resource limit but failed
   `runtime/llext_load LOAD_FAILURE cause=-2 ret=-20490`; these are not valid
   fixes for the current Xtensa LLEXT loader shape.
6. A temporary 25596-byte artifact preserving `.debug_frame` while removing
   larger debug sections caused `deploy prepare` to time out with `no_reply`.
   The board was recovered by reflashing the current Unit firmware, then
   `prepare_dnesp32s3b_wsl.sh` restored `NETWORK_READY`; recovery evidence is
   `smoke-evidence/serial-diag/serial-capture-20260501T042622Z.log`.
7. Final board state after recovery is clean: `query apps` reports `app_count=0`
   and `query leases` reports `leases=[]`.
8. `EXEC-201` hardware closure remains blocked by the interaction between GPIO
   LLEXT artifact shape and the current 24576-byte static ELF staging limit.
   Do not remove debug/unwind sections as a release fix until the loader
   requirements are characterized in Unit-side tests or hardware evidence.
9. The blocker must not be resolved by moving GPIO access into `neuro_unit`.
   GPIO, I2C, SPI, UART, ADC, and PWM demos remain responsible for their own
   Zephyr devicetree/driver dependencies; Unit remains the app management and
   communication framework.

PSRAM staging candidate update:

1. Memory pressure is now being addressed directly through the existing Unit
   port memory provider and LLEXT staging policy, not by moving hardware access
   out of apps.
2. DNESP32S3B already exposes an `esp-spiram` external memory provider through
   `shared_multi_heap_aligned_alloc(SMH_REG_ATTR_EXTERNAL, 32, size)` and
   `shared_multi_heap_free()`.
3. `neuro_unit/overlays/external_staging_candidate.conf` enables
   `CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=y` while keeping the
   existing 24576-byte internal static ELF staging buffer as fallback. The
   candidate also enables `CONFIG_LLEXT_EXPORT_DEVICES=y` and
   `CONFIG_LLEXT_EXPORT_SYMBOL_GROUP_DEVICE=y` so app-owned hardware demos can
   resolve Zephyr `DEVICE_DT_GET()` dependencies at load time without adding
   Unit-side GPIO/I2C/SPI/UART wrappers.
4. Local candidate build passed in
   `build/neurolink_unit_external_staging_candidate`; static layout remained
   stable with `dram0_0_seg` at 379976 / 399108 bytes and PSRAM/external heap
   available through `CONFIG_ESP_SPIRAM_HEAP_SIZE=2097152`.
5. `neuro_demo_gpio` was rebuilt against the candidate EDK and preserved build
   identity `neuro_demo_gpio-1.1.10-dev-cbor-v1`; candidate artifact size is
   54692 bytes.
6. Hardware validation after WSL USB attach and board preparation proved the
   PSRAM staging path moves the 54692-byte artifact past the previous
   `runtime/load_file RESOURCE_LIMIT` failure. Without device exports, activate
   reached Zephyr LLEXT link and failed with `runtime/llext_load LOAD_FAILURE
   cause=-2`; symbol inspection showed `__device_dts_ord_8` was discarded while
   the GPIO demo had it as an undefined dependency.
7. After enabling generic LLEXT device exports, the rebuilt candidate exported
   `__llext_sym___device_dts_ord_8`, internal DRAM changed only from 379976 to
   379992 bytes, and the candidate flashed/prepared successfully. The next
   activate attempt no longer returned `llext_load` error, but the board became
   `no_reply`; UART capture after the fact was empty, so the remaining blocker
   is now post-load/app-init runtime stability rather than ELF staging capacity
   or missing device export.
8. The board was restored to default Unit firmware and confirmed
   `NETWORK_READY`; the stale staged GPIO artifact was deleted from SD via
   protected `app delete` (`/SD:/apps/neuro_demo_gpio.llext`) and leases were
   confirmed empty.

Hardware debug freshness rule:

1. Before every real-board app debug/deploy attempt, delete the old app artifact
   from SD using the protected delete path before `deploy prepare`, even if the
   local LLEXT was just rebuilt.
2. Use short delete lease ids to avoid CBOR metadata length issues, for example:
   acquire `update/app/<app_id>/delete` with `l-<short>-del`, run
   `app delete --app-id <app_id> --lease-id <lease>`, release the lease, and
   confirm `query leases` is empty.
3. Treat `artifact missing` as a documented clean-start condition only after
   confirming `query apps` has no active/running app for that id. Do not proceed
   to hardware debug if an old artifact remains deleteable on SD.
4. For `neuro_demo_gpio`, the current confirmed cleanup command deleted
   `/SD:/apps/neuro_demo_gpio.llext` successfully with lease `l-gpio-del`.

Memory analysis update:

1. The current DNESP32S3B memory pressure is concentrated in a few internal RAM
   reservations rather than in the app artifact alone. The largest measured
   symbols in the GPIO internal-staging candidate are `thread_stack_area=73728`,
   `kheap_llext_heap=65536`, `_system_heap=53340`, `g_static_elf_buf=28672`,
   and `z_main_stack=18432`.
2. `CONFIG_LLEXT_HEAP_SIZE=64` is expressed in KiB and reserves one total LLEXT
   extension-region heap. It is not a per-app allocation. The app count policy
   previously had `max_loaded_apps` unbounded and `max_running_apps=2`, so low
   memory boards could accumulate loaded apps until heap pressure failed at
   runtime.
3. `neuro_unit` now exposes `CONFIG_NEUROLINK_APP_MAX_LOADED` and
   `CONFIG_NEUROLINK_APP_MAX_RUNNING`. The default Unit policy is `2/2`; the
   GPIO low-memory candidates use `1/1`.
4. `gpio_llext_heap_trim_candidate.conf` keeps LLEXT staging internal, keeps
   generic device exports enabled, limits loaded/running GPIO demos to one, and
   trims the total LLEXT heap from 64 KiB to 32 KiB. It builds successfully with
   `dram0_0_seg=351320 / 399108`; memory evidence records `dram0=348536`.
5. The earlier `CONFIG_LLEXT_HEAP_DYNAMIC=y` candidate measured `dram0=311672`,
   but the existing `memory config-plan` gate still reports
   `runtime_heap_dynamic_unsafe` because NeuroLink has no `llext_heap_init()`
   wiring or runtime proof. For this Xtensa target, a single PSRAM-backed LLEXT
   heap is also unsafe unless executable text placement is proven, because
   hardware logs already show instruction-fetch exceptions when LLEXT execution
   paths land in non-executable memory.
6. The internal-staging activation attempt proved `app_runtime_load ok` and then
   crashed during `app_start` with `EXCCAUSE 2 (instr fetch error)` at PC
   `0x3fcdb650`. The 32 KiB heap-trim hardware attempt then deployed and
   verified a 25468-byte GPIO artifact, but activation still failed with
   `no_reply`; UART evidence
   `smoke-evidence/serial-diag/exec-201-gpio-heap-trim-activate-20260502T061127Z.log`
   shows `app_runtime_load ok`, `app_runtime_start: invoking app_start`, and
   `EXCCAUSE 2` with PC/VADDR `0x3fcd3650`.
7. Heap-trim symbol inspection places `kheap_llext_heap` at `0x3fcc61e8` with
   size `0x8000`, and places `g_static_elf_buf` at `0x3fcd30a0`. The fatal PC is
   therefore inside the writable static ELF staging buffer, not inside the
   LLEXT heap. Heap trimming is still useful RAM relief, but it does not solve
   the current activation crash.
8. The refined blocker is Xtensa executable address placement under writable
   LLEXT storage. Zephyr accepts writable staging as instruction-fetchable on
   this non-HARVARD config, and NeuroLink's exported callback symbol fixup maps
   app entry pointers to the IRAM alias, but app-internal relocations/calls can
   still target the DRAM alias of `g_static_elf_buf`.
9. Current preferred candidate direction is: keep Zephyr LLEXT source untouched,
   keep loader-sensitive input internal, prevent app text and app-internal calls
   from executing through the DRAM staging alias, and only move independently
   allocated non-executable buffers to PSRAM after runtime evidence proves
   safety. Hardware activation should wait until the candidate plausibly avoids
   the DRAM instruction-fetch path.

Executable staging guard update:

1. Added a NeuroLink-owned diagnostic guard rather than modifying Zephyr LLEXT
   source. `CONFIG_NEUROLINK_APP_REJECT_STAGING_TEXT_EXEC` makes
   `app_runtime_load()` inspect `ext->mem[LLEXT_MEM_TEXT]` after `llext_load()`
   and reject the app before symbol binding or callback execution when text
   points inside the current ELF staging buffer.
2. Added `gpio_exec_guard_candidate.conf`, combining internal 28672-byte ELF
   staging, `CONFIG_LLEXT_HEAP_SIZE=32`, app policy `1/1`, generic device
   exports, and `CONFIG_NEUROLINK_APP_REJECT_STAGING_TEXT_EXEC=y`.
3. Local candidate build passed in
   `build/neurolink_unit_gpio_exec_guard_candidate`; memory stayed at
   `dram0_0_seg=351320 / 399108`, and the staged GPIO artifact size is 25468
   bytes.
4. Hardware validation flashed the candidate, restored `NETWORK_READY`, passed
   serial-required preflight, deployed and verified the 25468-byte GPIO
   artifact, then failed activation cleanly with
   `runtime/llext_text_guard LOAD_FAILURE cause=-8 ret=-20490` instead of
   crashing during `app_start`.
5. Final board state after the guarded activation attempt stayed healthy:
   `query device` reports `NETWORK_READY`, `query apps` reports `app_count=0`,
   and `query leases` reports `leases=[]`.
6. This guard is not the final GPIO execution fix. It is a safety and evidence
   gate proving that the next implementation must make app text and
   app-internal relocations resolve to an instruction-fetchable alias or region,
   rather than executing from `g_static_elf_buf`.

Executable alias fixup update:

1. Added isolated candidate `gpio_exec_alias_candidate.conf` with internal
   28672-byte staging, one loaded/running app, 32 KiB LLEXT heap, generic
   device exports, `CONFIG_NEUROLINK_APP_REJECT_STAGING_TEXT_EXEC=y`, and
   `CONFIG_NEUROLINK_APP_FIXUP_STAGING_TEXT_ALIAS=y`.
2. Kept Zephyr LLEXT source untouched. The NeuroLink runtime now only applies
   executable alias fixups when the loaded LLEXT text region points inside the
   current ELF staging buffer and the target architecture exposes a verified
   alias range.
3. ESP32-S3 aliasing is constrained to `0x3FC88000..0x3FCF0000` with offset
   `0x006F0000`. Function/text symbols are rewritten to the executable alias;
   data and rodata symbols such as `app_runtime_manifest` and
   `app_runtime_priority` remain on their raw data aliases.
4. The final candidate also patches 32-bit words inside the staged text region
   that point back into the original text range. This closes the observed
   `app_init` / `app_start` illegal-instruction path where app-internal Xtensa
   literal references still targeted the writable DRAM staging alias.
5. Local validation passed for `test_build_neurolink.sh`, catalog-backed
   `neuro_demo_gpio` build with `--strip-llext-debug`, and `git diff --check`.
   The final candidate firmware flashed at 809612 bytes with
   `dram0_0_seg=351320 / 399108`.
6. Hardware validation on DNESP32S3B passed deploy prepare/verify for the
   25468-byte GPIO artifact and activation returned `status: ok` using lease
   `l-gpio-alias`. UART evidence
   `smoke-evidence/serial-diag/exec-201-gpio-exec-alias-literal-fix-activate-20260502T090008Z.log`
   shows `app_runtime_start: invoking app_start`, `start:post_app_start`,
   `app_runtime_start: app running`, and no fatal exception.
7. Post-activation `query apps` reports `neuro_demo_gpio` as `RUNNING` /
   `ACTIVE` with `app_count=1`, app-control capability/read command smoke
   returned `status: ok`, and final `query leases` returned `leases=[]` after
   explicit activation/control lease cleanup.
8. Callback event observation is now closed for the cross-board safe path. The
   first callback smoke exposed that app invoke `--args-json` was being dropped
   by the Unit CBOR-to-internal-JSON bridge and that empty invokes could not
   trigger GPIO-only actions on boards without safe aliases.
9. The Unit request-field bridge now preserves simple `args` maps as JSON, so
   demo apps can read CLI-provided `action` and option fields. Native_sim covers
   `args={"action":"read","value":true}` in the CBOR request-fields
   decoder.
10. `neuro_demo_gpio` now publishes callback events for callback-enabled
   `capability` invokes as well as hardware actions, giving boards without safe
   `sw0` / `led0` wiring a real callback proof path.
11. Rebuilt GPIO artifact size is 25536 bytes. Protected deploy/verify/activate
   passed, and `app-callback-smoke --app-id neuro_demo_gpio --trigger-every 1
   --invoke-count 2` captured three CBOR callback events on
   `neuro/unit-01/event/app/neuro_demo_gpio/callback` with `invoke_count` 1, 2,
   and 3 and `start_count=1`. Final `query apps` reports `RUNNING` / `ACTIVE`,
   and final `query leases` reports `leases=[]`.
12. DNESP32S3B red-LED control is now proven. The board DTS maps `led0` to the
   blue LED and `led1` to the red LED, so `neuro_demo_gpio` now drives
   `DT_ALIAS(led1)` for output and reports the output interface as `led1`.
   The demo also reads CLI app invoke fields from the nested `args` object
   emitted by the Unit CBOR bridge. After rebuilding/flashing the Unit reply
   buffer fix and redeploying the 27944-byte GPIO artifact, `write true`,
   `write false`, and `toggle` replies reported `command=write`,
   `command=write`, and `command=toggle` with `invoke_count=1/2/3`; the board
   red LED was physically observed lighting during the control command.
13. JSON `gpio_state` event publication is now closed. The Unit event module is
   configured with only the binary event sink in the live firmware, so
   `neuro_unit_publish_app_event()` now falls back to publishing UTF-8 JSON
   payload bytes when the JSON sink is absent. Native_sim covers this fallback,
   and DNESP32S3B hardware proof captured three `gpio_state` events through
   `monitor app-events --app-id neuro_demo_gpio` with `payload_encoding=json-v2`,
   `interface=led1`, values `1/0/1`, and `invoke_count=1/2/3`. The matching
   `write true`, `write false`, and `toggle` replies all report `publish_ret=0`.

### EXEC-202 SPI/UART/ADC/PWM Demo Slice

1. Add capability mapping and command contracts for SPI, UART, ADC, and PWM.
2. Implement `neuro_demo_spi`, `neuro_demo_uart`, and `neuro_demo_adc_pwm` with
   bounded side effects and wiring documented separately from portable behavior.
3. Implement callback event support wherever the existing public callback app
   API can be used; document any callback omission with a concrete blocker.
4. Add hardware evidence only for safe configured paths; otherwise close with
   explicit unsupported evidence.

Initial execution plan:

1. Start with `neuro_demo_uart` because DNESP32S3B exposes
   `zephyr,shell-uart = &uart0`, but keep the first demo read-only so it does
   not disturb the Unit control/log console.
2. Implement `capability`, `probe`, and `echo` contracts. `probe` reports device
   readiness and publishes `uart_probe`; `echo` echoes through app reply/event
   only and deliberately does not write bytes to the physical UART.
3. Wire callback events for successful capability/probe/echo actions using the
   stable public callback API.
4. Validate local artifact build first, then decide whether to run hardware
   proof as a non-invasive readiness/event observation on the current
   executable-alias Unit candidate.

Local UART implementation update:

1. Added `subprojects/neuro_demo_uart` as the first `EXEC-202` demo. It uses
   `DT_CHOSEN(zephyr_shell_uart)` / Zephyr UART readiness from inside the app
   subproject and does not add Unit-side UART wrappers.
2. The demo supports `action=capability`, `action=probe`, and `action=echo`.
   `probe` and `echo` publish `uart_probe` app events when the selected UART is
   ready; `echo` returns the message through the app reply/event payload only
   and deliberately avoids physical UART transmission.
3. Callback events are wired for successful capability/probe/echo actions via
   the stable public callback app API, matching the release rule that demos
   implement callback behavior whenever technically feasible.
4. Updated `subprojects/demo_catalog.json` so `neuro_demo_uart` is marked
   `implemented_local`.
5. Local validation passed for the catalog-backed alias-candidate build,
   `test_demo_catalog.sh`, `test_build_neurolink_demo.sh`, artifact build-id
   inspection for `neuro_demo_uart-1.1.10-dev-cbor-v1`, VS Code diagnostics on
   the new UART source/catalog files, Unit native_sim (`PROJECT EXECUTION
   SUCCESSFUL`), and `git diff --check`.

UART hardware proof update:

1. DNESP32S3B hardware proof for `neuro_demo_uart` passed on the executable-
   alias Unit candidate after protected cleanup of the previously active GPIO
   demo. GPIO was stopped, unloaded, and deleted first so the low-memory `1/1`
   app policy did not block UART activation.
2. Serial-required preflight initially reported `serial_device_missing`; WSL USB
   pass-through was restored with `prepare_dnesp32s3b_wsl.sh --attach-only`,
   reattaching `/dev/ttyACM0`. The rerun preflight returned `status=ready` for
   `build/neurolink_unit_gpio_exec_alias_candidate/llext/neuro_demo_uart.llext`.
3. Protected deploy with lease `l-uart-dep` transferred the 18364-byte artifact
   to `/SD:/apps/neuro_demo_uart.llext`; `deploy prepare`, `deploy verify`, and
   `deploy activate` all returned `status: ok`, and `query apps` reported
   `neuro_demo_uart` `RUNNING` / `ACTIVE`.
4. Protected control smoke for `capability`, `probe`, and `echo` returned ok.
   `probe` and `echo` reported `publish_ret=0`; `echo` remained read-only and
   did not transmit bytes on the physical shell UART.
5. Callback smoke passed with `trigger_every=1` and captured three CBOR callback
   events on `neuro/unit-01/event/app/neuro_demo_uart/callback` with
   `start_count=1`.
6. Standalone `monitor app-events --app-id neuro_demo_uart` did not capture the
   fresh events even after app-scoped monitoring was adjusted to prefer callback
   subscribers, matching the known separate-listener/session limitation from
   earlier callback work. A same-session event probe using the Neuro CLI
   subscriber and invoke path captured both callback events and JSON `uart_probe`
   events for `probe` and `echo` on
   `neuro/unit-01/event/app/neuro_demo_uart/uart_probe`, with
   `interface=zephyr_shell_uart`, `ready=true`, and `payload_encoding=json-v2`.
7. Focused Neuro CLI regression coverage passed for the app-event monitor
   callback-preference change (`10 passed`). Final cleanup stopped, unloaded,
   and deleted the UART app, then final queries showed Unit `NETWORK_READY`,
   `app_count=0`, and `leases=[]`.
8. The UART demo now also has DNESP32S3B J3 physical loopback proof. The Unit
   board overlay declares `neurolink,uart-loopback = &uart1` and maps J3 IO5 as
   `UART1_TX_GPIO5` and J3 IO6 as `UART1_RX_GPIO6`, keeping console/shell on
   `uart0`. `neuro_demo_uart` prefers this chosen UART when present and exposes
   `action=loopback`, which sends bytes with `uart_poll_out()` and reads them
   back with `uart_poll_in()`.
9. Local generated devicetree resolved `DT_CHOSEN_neurolink_uart_loopback` to
   `/soc/uart@60010000` (`uart1`), and the rebuilt UART artifact preserved
   `neuro_demo_uart-1.1.10-dev-cbor-v1`. After flashing the updated candidate,
   deploying the 25408-byte UART artifact, and activating it successfully, the
   user shorted J3 TX/RX and `action=loopback,message=J3` returned
   `publish_ret=0`. `monitor app-events --app-id neuro_demo_uart` captured a
   JSON `uart_probe` event with `interface=j3_uart1_gpio5_tx_gpio6_rx`,
   `ok=true`, `tx=2`, `rx=2`, `mm=-1`, `message=J3`, and `received=J3`, proving
   the physical J3 UART path is correct. Final cleanup again left Unit
   `NETWORK_READY`, `app_count=0`, and `leases=[]`.

SPI local implementation update:

1. Started the next `EXEC-202` hardware demo after UART closure by adding
   `subprojects/neuro_demo_spi`. The first SPI slice is deliberately probe-only
   because DNESP32S3B currently uses `spi3` for SD storage with SCLK GPIO7, MISO
   GPIO15, MOSI GPIO16, and CS GPIO17; the demo must not perform arbitrary SPI
   transfers on that shared bus without a dedicated loopback device/chip-select
   contract.
2. The demo supports `action=capability`, `action=probe`, and `action=transfer`.
   `capability` and `probe` report `spi3` device readiness, `probe` publishes a
   `spi_probe` app event, and callback events are wired through the stable
   public callback API. `transfer` currently returns a graceful unsupported
   result with detail `shared_sd_spi_no_loopback_target` rather than touching the
   SD-card SPI bus.
3. Updated `subprojects/demo_catalog.json` so `neuro_demo_spi` is marked
   `implemented_local` and advertises `spi_probe` plus `callback` events.
4. Hardware smoke on DNESP32S3B passed after WSL restart recovery through the
   existing project scripts. `run_zenoh_router_wsl.sh` confirmed `0.0.0.0:7447`
   was already owned by the router, `prepare_dnesp32s3b_wsl.sh --attach-only`
   restored `/dev/ttyACM0`, and the full prepare script restored Unit
   `NETWORK_READY` with IPv4 `192.168.2.67`. The rebuilt 18708-byte SPI artifact
   passed `smoke_neurolink_linux.sh` preflight, deploy prepare, verify, and
   activate. Protected control calls proved `capability` and `probe` return
   `echo=neuro_demo_spi-1.1.10-dev-cbor-v1`, `probe` returned `publish_ret=0`,
   and `transfer` returned `echo=shared_sd_spi_no_loopback_target`, confirming no
   SPI transfer was attempted on the shared SD-card bus. Callback smoke captured
   three CBOR callback events on `neuro/unit-01/event/app/neuro_demo_spi/callback`
   with `invoke_count=3/4/5` and `start_count=1`. Final cleanup stopped,
   unloaded, and deleted `/SD:/apps/neuro_demo_spi.llext`; artifact delete uses
   lease resource `update/app/neuro_demo_spi/delete`. Final queries showed
   `app_count=0` and `leases=[]`.

ADC/IO8 local implementation update:

1. Started the ADC/PWM part of `EXEC-202` by implementing the requested IO8 ADC
   voltage read path in `subprojects/neuro_demo_adc_pwm`. On ESP32-S3, GPIO8 is
   ADC1 channel 7, exposed through Zephyr as `adc0` channel 7.
2. Updated the DNESP32S3B Unit board overlay to enable `adc0`, declare
   `channel@7` with `ADC_GAIN_1_4`, `ADC_REF_INTERNAL`, 12-bit resolution, and
   bind `zephyr,user` `io-channels = <&adc0 7>`. This keeps the hardware mapping
   explicit and avoids reusing any current UART1 J3, SPI3 SD, I2C0, LCD, LED, or
   button pins.
3. `neuro_demo_adc_pwm` supports `action=capability`, `action=adc_read`, and a
   graceful unsupported `action=pwm_set` result because this slice is scoped to
   IO8 ADC validation. The app-owned JSON reply includes `gpio=8`, `channel=7`,
   raw sample, millivolts, bounded sample count, min/max mV, `publish_ret`, and
   `echo=io8_adc1_ch7`; the current CBOR app-command reply surface preserves
   the common fields, while the `adc_sample` app event carries the raw/mV proof.
4. Callback event support is wired through the stable callback API, and each
   successful ADC read publishes a compact `adc_sample` app event. The JSON event
   stays below the 256-byte app-event limit learned during UART validation.
5. Updated `subprojects/demo_catalog.json` so `neuro_demo_adc_pwm` is marked
   `implemented_local` and advertises `adc_sample` plus `callback` events.
6. Local validation passed: `test_demo_catalog.sh`, catalog-backed build through
   `build_neurolink_demo.sh --demo neuro_demo_adc_pwm --build-dir
   build/neurolink_unit_adc_io8_candidate --overlay-config
   applocation/NeuroLink/neuro_unit/overlays/gpio_exec_alias_candidate.conf
   --strip-llext-debug --no-c-style-check`, artifact string inspection for
   `neuro_demo_adc_pwm-1.1.10-dev-cbor-v1`, `adc_sample`, and `io8_adc1_ch7`,
   and `git -C applocation/NeuroLink diff --check`.
7. Hardware proof passed on DNESP32S3B after narrowing the app's LLEXT runtime
   dependencies. The first hardware activate failed with
   `runtime/llext_load LOAD_FAILURE cause=-2 ret=-20490`; symbol inspection
   showed non-exported helper references from `adc_raw_to_millivolts_dt`,
   `adc_is_ready_dt`, and `k_busy_wait`. The demo now avoids those helpers,
   keeps ADC reads inside the LLEXT app, and uses the IO8 overlay contract to
   compute millivolts from the 12-bit raw value with the ESP32 default 1100 mV
   internal reference and `ADC_GAIN_1_4` scale.
8. The rebuilt 23672-byte artifact prepared, verified, and activated
   successfully through `smoke_neurolink_linux.sh` with app id
   `neuro_demo_adc_pwm`. `query apps` reports `neuro_demo_adc_pwm` as
   `RUNNING` / `ACTIVE`.
9. With IO8 connected to GND, protected `app invoke --args-json
   '{"action":"adc_read","samples":4}'` returned `command=adc_read`,
   `echo=io8_adc1_ch7`, and `publish_ret=0`. `monitor app-events --app-id
   neuro_demo_adc_pwm` captured `neuro/unit-01/event/app/neuro_demo_adc_pwm/adc_sample`
   with JSON payload `gpio=8`, `channel=7`, `raw=0`, `mv=0`, `count=4`, and
   `invoke_count=2`. Final `query leases` reports `leases=[]`; the ADC demo is
   intentionally left running for additional IO8 voltage reads.

I2C/AP3216C hardware closure update:

1. Implemented `subprojects/neuro_demo_i2c` as an app-owned AP3216C demo using
   Zephyr `i2c0`, AP3216C address `0x1e`, and the reset/enable sequence
   `0x00=0x04`, 10 ms delay, `0x00=0x03`, then 120 ms conversion delay.
2. The app supports `action=capability`, `action=scan`, and
   `action=ap3216c_read`, publishes compact `scan_result` and
   `ap3216c_sample` JSON events, and keeps all hardware-specific logic inside
   the app subproject.
3. Local build, deploy prepare/verify, activation, scan, and sample read passed
   on DNESP32S3B. The I2C scan found AP3216C at `0x1e` and XL9555 at `0x20`;
   sample evidence reported `sys=3`, valid IR/ALS/PS raw data, and
   `ps_near=false`.
4. Final live state for the cutoff had `neuro_demo_i2c` `RUNNING` / `ACTIVE`
   and `query leases` returning `leases=[]`.

### EXEC-203 TCP/UDP Candidate and Integrated Demo

Release-1.1.10 cutoff decision: this slice is deferred to the next release. The
current release closes with the proven hardware-demo family and net-event bridge;
`neuro_demo_net_udp` and `neuro_demo_integrated` remain catalogued as
`deferred_next_release` rather than being implemented under a long-running
release branch.

1. In the next release, decide whether TCP/UDP can be implemented through a tested Unit-side helper
   in this release. If not, keep `neuro_demo_net_udp` as a capability-reporting
   candidate and close network scope through `neuro_demo_net_event`.
2. In the next release, implement `neuro_demo_integrated` with real hardware behavior where available
   and simulated mode where not.
3. Include callback event behavior when the integrated demo can use the stable
   callback app API safely.
4. Validate integrated app event emission and memory impact.

### EXEC-204 Demo Workflow and Documentation Closure

1. Add non-executing CLI workflow plans for demo build, hardware smoke, network
   smoke, integrated smoke, and cleanup.
2. Update canonical and project-shared Neuro CLI skill workflow references.
3. Document DNESP32S3B wiring assumptions and cross-board unsupported behavior.

Status update:

1. Added `scripts/build_neurolink_demo.sh` as the first operator-facing demo
   build wrapper on top of `build_neurolink.sh`.
2. The wrapper resolves demo source/artifact metadata from
   `subprojects/demo_catalog.json`, forwards the supported build options, and
   prints the resolved staged artifact path for downstream workflow chaining.
3. Added focused script regressions for catalog-backed demo selection and
   raised the script suite baseline from `10` to `11` tests.
4. This slice intentionally does not add new CLI `workflow plan` entries,
   hardware smoke automation, or reference-skill updates yet.

Follow-on update:

1. Added non-executing CLI `workflow plan demo-build` and
   `workflow plan demo-net-event-smoke` in `neuro_cli/src/neuro_cli.py`.
2. `demo-build` points Agents at the catalog-backed
   `build_neurolink_demo.sh` wrapper for the first implemented demo,
   `neuro_demo_net_event`.
3. `demo-net-event-smoke` documents the first reviewable end-to-end demo path:
   build, preflight with explicit artifact path, protected deploy, capability
   invoke, publish invoke, app-event monitoring, and lease cleanup.
4. This follow-on slice still does not add skill-reference updates or execute
   hardware smoke commands; it only exposes the supported plan JSON surface.

Closure update:

1. Updated the canonical Neuro CLI workflow references and the project-shared
   mirror so `workflow plan demo-build` and
   `workflow plan demo-net-event-smoke` are documented alongside the existing
   build and control workflow surfaces.
2. Updated `neuro_cli/skill/references/discovery-and-control.md` so the first
   demo smoke sequence is described in the same protected deploy / invoke /
   cleanup safety model as the core control plans.
3. Added focused Neuro CLI regression coverage to keep the canonical/shared
   workflow references aligned with the live demo workflow plans.
4. Hardware smoke execution remains part of `EXEC-205`; `EXEC-204` now closes
   with wrapper support, live plan JSON, and aligned operator references.

### EXEC-205 Local and Hardware Closure

Release-1.1.10 closure decision: completed for the current cutoff scope. Closure
is based on the already-passed local gates and DNESP32S3B hardware proofs for
GPIO, UART loopback, SPI probe, IO8 ADC, LEDB PWM, I2C/AP3216C, and the
net-event demo path. Full release-wide reruns beyond the changed metadata were
not required for the user-requested cutoff; the remaining UDP and integrated
work moves to the next release.

1. Run local Python, CLI, wrapper, script, Unit native_sim, memory evidence, and
   whitespace gates.
2. Build each selected demo artifact and verify expected build ids.
3. Run serial-required preflight, per-demo deploy/activate/invoke/event checks,
   unload/delete cleanup, explicit lease release, and final queries.
4. CLI, reference app, and demo app identities are promoted to 1.1.10 for the
   closed cutoff.

## 5. Validation Gates

Local gates:

1. Python compile for CLI, wrapper, protocol, and tests.
2. Focused CLI and wrapper pytest suites.
3. Script regression suite.
4. Native Unit tests for touched app API, event, port, and runtime behavior.
5. Build each selected demo LLEXT artifact and verify non-empty staged output.
6. Memory layout dump and config-plan evidence when Unit symbols or config grow.
7. `git diff --check`.

Hardware gates:

1. Serial-required DNESP32S3B preflight.
2. Fresh Unit firmware and fresh selected demo artifacts.
3. Per-demo deploy, activate, invoke, event observation, unload, delete, and
   lease cleanup.
4. Event bridge/callback smoke for network and integrated demos.
5. Final `query device`, `query apps`, and `query leases` showing Unit ready,
   no stale demo state, and empty leases.

## 6. Decisions

1. DNESP32S3B is the required real-hardware closure target for 1.1.10.
2. Cross-board portability is expressed through capability discovery and
   graceful unsupported responses, not through untested board assumptions.
3. The first stable network demo uses the existing app event/Zenoh bridge.
4. TCP/UDP remains gated on explicit Unit-side API support and tests and is
   deferred to the next release.
5. `neuro_unit_app` remains the reference lifecycle/callback app and is not
   repurposed as the hardware demo container.
6. Release identity is promoted to `1.1.10` for the closed cutoff slice.

## 7. Execution Ledger

### EXEC-199 Demo Catalog and App API Capability Contracts

`EXEC-199` established the first demo-facing runtime contract for release-1.1.10
without changing firmware behavior or adding real demo runtime logic yet.

Evidence summary:

1. `subprojects/demo_catalog.json` defines the first machine-readable catalog for
   `neuro_demo_i2c`, `neuro_demo_spi`, `neuro_demo_gpio`, `neuro_demo_uart`,
   `neuro_demo_adc_pwm`, `neuro_demo_net_event`, `neuro_demo_net_udp`, and
   `neuro_demo_integrated`.
2. `neuro_unit_app_api.h` now exposes DTOs and helper writers for
   cross-board capability replies and graceful unsupported results.
3. `neuro_unit/tests/unit/src/app/test_neuro_unit_app_api.c` now covers the new
   JSON contract helpers in native_sim.
4. `tests/scripts/test_demo_catalog.sh` validates the catalog schema/entries and
   `tests/scripts/run_all_tests.sh` now includes it.
5. `build_neurolink.sh` now honors `--pristine-always` even when a build
   directory is already configured.
6. Validation passed for focused build-script regression, demo catalog test,
   full script regression suite (`10/10`), native_sim Unit tests (`PROJECT
   EXECUTION SUCCESSFUL`), and `git diff --check`.

### EXEC-200 First Event Demo Subproject

`EXEC-200` started the first actual demo implementation while staying inside the
existing safe LLEXT app API boundary.

Evidence summary:

1. Added `subprojects/neuro_demo_net_event` with its own `CMakeLists.txt`,
   `toolchain.cmake`, and `src/main.c`.
2. The demo supports capability discovery and event publishing without any new
   board driver dependency.
3. The demo catalog marks `neuro_demo_net_event` as `implemented_local`.
4. The selected-app build flow now uses app-specific external build directories
   for non-default app ids, preventing cache conflicts between demo apps.
5. Validation passed for `test_demo_catalog.sh`, `test_build_neurolink.sh`,
   `build_neurolink.sh --preset unit-app --app neuro_demo_net_event`, artifact
   build-id inspection, and `git diff --check`.

### EXEC-204 Demo Build Wrapper Workflow Support

`EXEC-204` started the operator-facing demo workflow surface without widening
scope into new firmware or hardware behavior.

Evidence summary:

1. Added `scripts/build_neurolink_demo.sh` as a catalog-backed wrapper around
   `build_neurolink.sh --preset unit-app --app <demo>`.
2. The wrapper resolves `source_dir`, default `artifact`, and current catalog
   `status` from `subprojects/demo_catalog.json` before invoking the build.
3. The wrapper supports the current safe build-time options: board override,
   build-dir override, pristine rebuild, overlay configs, extra west/cmake
   args, c-style bypass, and artifact-path printing.
4. Added `tests/scripts/test_build_neurolink_demo.sh`, wired it into
   `run_all_tests.sh`, and exposed the wrapper through
   `test_linux_scripts_help.sh`.
5. Validation passed for the focused wrapper regression, help-surface
   regression, real `build_neurolink_demo.sh --demo neuro_demo_net_event`
   artifact build, build-id inspection, full script regression suite
   (`11/11`), and `git diff --check`.

### EXEC-204 Demo Workflow Plan Surface

`EXEC-204` continued by exposing the first release-1.1.10 demo workflow plans
through the live Neuro CLI without executing any new host or hardware actions.

Evidence summary:

1. Added `workflow plan demo-build` so Agents can discover the supported
   catalog-backed demo build command before running it.
2. Added `workflow plan demo-net-event-smoke` so Agents can inspect the first
   event-demo deploy/invoke/event-monitor/cleanup sequence as structured JSON.
3. Both plans use the existing workflow metadata schema, so they report host
   support, hardware/router/serial requirements, destructive state,
   preconditions, expected success, failure classifications, cleanup, and a
   `json_contract` where appropriate.
4. Added focused CLI regressions for parser support plus the build/smoke plan
   command contracts.
5. Validation passed for the focused Neuro CLI pytest subset covering the new
   workflow plans.

### EXEC-204 Demo Workflow Reference Alignment

`EXEC-204` closed the documentation side of the demo workflow surface so
Agents, local references, and the project-shared skill mirror all describe the
same supported demo plan entrypoints.

Evidence summary:

1. Updated `neuro_cli/skill/references/workflows.md` and the mirrored
   `.github/skills/neuro-cli/references/workflows.md` to include
   `workflow plan demo-build` and `workflow plan demo-net-event-smoke`.
2. Updated `neuro_cli/skill/references/discovery-and-control.md` to describe
   the first reviewable demo smoke sequence, explicit artifact-path preflight,
   and blocking failure classifications for demo control.
3. Added focused Neuro CLI regression coverage so the canonical/shared
   references must continue to mention the release-1.1.10 demo workflow plans.
4. Validation passed for the focused Neuro CLI pytest subset covering the new
   reference assertions and shared-resource mirroring.

### EXEC-201 First GPIO Demo Subproject

`EXEC-201` started the hardware-facing demo family with the lowest-risk first
runtime slice: a GPIO app that only uses safe board aliases and otherwise
reports capability gaps explicitly.

Evidence summary:

1. Added `subprojects/neuro_demo_gpio` with its own `CMakeLists.txt`,
   `toolchain.cmake`, and `src/main.c`.
2. The demo reuses the public app ABI and supports `action=capability`,
   `action=read`, `action=write`, and `action=toggle` through the existing
   `invoke` command surface.
3. `read` is gated on `DT_ALIAS(sw0)` and `write` / `toggle` are gated on
   `DT_ALIAS(led1)` for the DNESP32S3B red LED. Missing or unready aliases return stable
   `capability_missing` / `io_error` JSON instead of unsafe board-specific pin
   assumptions.
4. Successful GPIO actions publish `gpio_state` app events and can also publish
   callback events through the stable public callback API when the invoke
   payload enables `callback_enabled` with a positive `trigger_every`.
5. The demo catalog now lists both `gpio_state` and `callback` events and marks
   `neuro_demo_gpio` as `implemented_local`.
6. Local validation passed for the catalog-backed wrapper build of
   `neuro_demo_gpio`.

### EXEC-201 GPIO ESP32-S3 LLEXT Activation Closure

`EXEC-201` then closed the main hardware activation blocker for the GPIO demo by
converting the ESP32-S3 writable-staging text path into a NeuroLink-owned
executable-alias candidate.

Evidence summary:

1. Memory analysis proved the fatal PC/VADDR landed inside `g_static_elf_buf`,
   not the LLEXT heap, so heap trimming alone was insufficient.
2. The diagnostic staging-text guard first converted the crash into a clean
   `runtime/llext_text_guard LOAD_FAILURE cause=-8 ret=-20490`, proving the
   text region was being executed through the writable staging alias.
3. The final alias candidate kept Zephyr LLEXT source unchanged, mapped only
   executable text/function addresses to the ESP32-S3 IRAM alias, left app data
   symbols raw, and patched text-local 32-bit literals before app callbacks ran.
4. Validation passed for local build/script gates, final candidate flash, board
   prepare to `NETWORK_READY`, protected deploy prepare/verify, and protected
   activation of the 25468-byte `neuro_demo_gpio` artifact.
5. UART evidence for the final activation shows `app_start` completed and the
   runtime reported `app running`, with no instruction-fetch or illegal-
   instruction fatal exception.
6. Post-activation `query apps` reports `neuro_demo_gpio` `RUNNING` / `ACTIVE`,
   app-control capability/read smoke returned `status: ok`, and final lease
   cleanup returned `leases=[]`.
7. Callback event hardware observation is closed through the safe capability
   path after preserving CBOR `args` in the internal JSON bridge and allowing
   callback-enabled `capability` invokes to publish events. The final smoke
   captured three `neuro_demo_gpio/callback` CBOR events and left leases empty.
8. Red LED hardware action observation is closed on DNESP32S3B through `led1`:
   protected app invokes for `write true`, `write false`, and `toggle` drove the
   visible red LED and returned action-specific command replies.
9. JSON `gpio_state` app-event observation is also closed. The Unit event layer
   now falls back from JSON publishing to the configured bytes sink by sending
   the JSON payload unchanged as UTF-8 bytes. Native_sim covers the fallback, and
   hardware monitor proof captured three `gpio_state` events for the same
   `write true`, `write false`, and `toggle` sequence with `payload_encoding=json-v2`;
   all action replies report `publish_ret=0` and final lease cleanup returned
   `leases=[]`.