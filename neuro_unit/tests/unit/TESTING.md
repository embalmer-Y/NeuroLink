# Neuro Unit Module Testing Guide (UT + Hardware)

## 1. Scope and Goal

This document defines how to validate the Unit-side modules and board-side hardware replay path:
1. neuro_app_command_registry
2. neuro_app_callback_bridge
3. neuro_unit_app_command
4. neuro_request_envelope
5. neuro_request_policy
6. neuro_update_manager
7. neuro_lease_manager
8. neuro_recovery_seed_store
9. app_runtime_cmd capability gate
10. neuro_recovery_reconcile
11. neuro_unit_event
12. neuro_unit_diag
13. neuro_unit_update_service
14. neuro_unit_port filesystem contract
15. neuro_network_manager port status bridge
16. board-side update/control replay and evidence capture

Goal:
1. Verify registry behavior for command lifecycle transitions and boundary conditions.
2. Verify callback bridge request/reply forwarding contract and default-value handling.
3. Verify app command service reply-context dispatch, lease boundary, unsupported command errors, and runtime start success behavior.
4. Verify request metadata parsing and validation rules for common, write, and protected-write paths.
5. Verify metadata requirement policy mapping for command/query/update routes.
6. Verify update state-machine order and reboot reconciliation fallback behavior.
7. Verify lease arbitration and reboot-time lease cleanup semantics.
8. Verify recovery seed encode/decode integrity and snapshot restore behavior.
9. Verify runtime command capability gating behavior for generic command IDs and hooks.
10. Verify framework-owned app event topic construction and app-originated publish contract behavior.
11. Verify diagnostic context formatting and shared update transaction logging entry points.
12. Verify update-service entry behavior for prepare, recovery aliasing, unsupported actions, and release-1.1.4 service boundary guardrails.
13. Verify response JSON compatibility for externally visible query, lease, and error payload builders.
14. Verify port filesystem op registration, reset, and path validation behavior.
15. Verify network manager status mapping through the port network status hook.
16. Provide the single canonical testing procedure for UT, WSL runtime evidence, and board-side replay evidence.

## 2. Test Artifacts

1. Test app root: applocation/NeuroLink/neuro_unit/tests/unit
2. App module tests: src/app/test_neuro_app_command_registry.c, src/app/test_neuro_app_callback_bridge.c, src/app/test_neuro_unit_app_command.c
3. Request module tests: src/request/test_neuro_request_envelope.c, src/request/test_neuro_request_policy.c
4. Lifecycle module tests: src/lifecycle/test_neuro_update_manager.c, src/lifecycle/test_neuro_lease_manager.c
5. Response module tests: src/lifecycle/test_neuro_unit_response.c
6. Diagnostics module tests: src/lifecycle/test_neuro_unit_diag.c
7. Update service module tests: src/lifecycle/test_neuro_unit_update_service.c
8. Recovery module tests: src/recovery/test_neuro_recovery_seed_store.c, src/recovery/test_neuro_recovery_reconcile.c
9. Runtime module tests: src/runtime/test_app_runtime_cmd_capability.c
10. Event module tests: src/app/test_neuro_unit_event.c
11. Port module tests: src/port/test_neuro_unit_port_fs_contract.c, src/port/test_neuro_network_manager_port.c
12. Twister metadata: testcase.yaml
13. Build config: prj.conf

## 3. Test Method

Method type:
1. White-box module unit test using Zephyr ztest.
2. Pure in-process validation, no network dependency.

Isolation strategy:
1. Registry tests call real registry APIs and reset state via neuro_app_command_registry_init().
2. Callback bridge tests replace app_runtime_dispatch_command() with a local mock implementation.

Assertion strategy:
1. Return code assertions (success and failure paths).
2. State assertions for registry state machine outputs.
3. Data-path assertions for forwarded arguments and reply buffer behavior.

## 4. Test Case Matrix

Registry UT set:
1. test_register_and_find_success
2. test_register_rejects_reserved_or_invalid_name
3. test_set_enabled_single_command
4. test_set_app_enabled_updates_all_commands
5. test_remove_app_deletes_commands
6. test_registry_capacity_limit

Callback bridge UT set:
1. test_dispatch_forwards_arguments
2. test_dispatch_uses_default_json_when_null
3. test_dispatch_clears_reply_buffer_before_runtime

App command service UT set:
1. test_unsupported_action_replies_404_through_reply_context
2. test_start_action_replies_ok_through_reply_context
3. test_registered_callback_command_dispatches_through_bridge
4. test_registered_callback_command_dispatch_failure_replies_500
5. test_disabled_registered_callback_command_replies_409

Request envelope UT set:
1. test_parse_extracts_all_supported_fields
2. test_parse_with_null_json_or_metadata_fails
3. test_parse_defaults_priority_and_forwarded
4. test_validate_accepts_common_fields
5. test_validate_rejects_missing_common_field
6. test_validate_rejects_target_node_mismatch
7. test_validate_accepts_when_expected_target_empty
8. test_validate_write_requires_priority_and_idempotency
9. test_validate_protected_write_requires_lease_id
10. test_validate_null_metadata_reports_error
11. test_json_extract_helpers_return_defaults_on_missing_key

Request policy UT set:
1. test_command_lease_acquire_requires_write_fields
2. test_command_protected_paths_require_lease
3. test_command_unknown_path_has_no_policy
4. test_query_standard_paths_require_common_fields
5. test_query_unknown_path_has_no_policy
6. test_update_prepare_requires_write_fields
7. test_update_verify_requires_common_fields
8. test_update_activate_requires_protected_write_fields
9. test_update_unknown_action_has_no_policy
10. test_null_input_has_no_policy

Update manager UT set:
1. test_prepare_verify_activate_success_order
2. test_verify_before_prepare_rejected
3. test_activate_before_verify_rejected
4. test_prepare_fail_marks_failed
5. test_verify_fail_marks_failed
6. test_activate_fail_marks_failed
7. test_prepare_rejected_while_in_progress
8. test_rollback_success_marks_rolled_back
9. test_rollback_requires_active_or_failed
10. test_rollback_fail_returns_failed_state
11. test_reconcile_boot_marks_interrupted_transition_failed
12. test_reconcile_boot_prepared_without_artifact_failed
13. test_reconcile_boot_active_without_runtime_failed
14. test_reconcile_boot_verified_with_artifact_keeps_state
15. test_rollback_pending_can_fail_before_unload

Update service UT set:
1. test_prepare_action_stages_artifact_and_replies
2. test_repeated_prepare_preserves_existing_state_machine_semantics
3. test_verify_action_marks_artifact_verified
4. test_activate_action_marks_app_active
5. test_rollback_action_completes_recovery_flow
6. test_recover_alias_is_preserved
7. test_unsupported_action_replies_404
8. test_recovery_seed_gate_bubbles_storage_not_ready

Lease manager UT set:
1. test_acquire_require_release_success
2. test_acquire_rejects_conflict_without_higher_priority
3. test_acquire_preempts_with_higher_priority
4. test_release_rejects_holder_mismatch
5. test_require_resource_rejects_mismatch_and_expiry
6. test_expire_all_clears_active_leases

Recovery seed store UT set:
1. test_encode_decode_roundtrip_success
2. test_decode_rejects_crc_mismatch
3. test_decode_rejects_version_mismatch
4. test_decode_rejects_older_unsupported_version
5. test_decode_rejects_truncated_payload
6. test_build_and_apply_snapshot_roundtrip
7. test_store_load_promotes_valid_tmp_when_primary_missing
8. test_store_save_retries_rename_after_existing_target_removed

Recovery reconcile UT set:
1. test_interrupted_prepare_state_fails_after_reboot
2. test_interrupted_verifying_state_fails_after_reboot
3. test_interrupted_activating_state_fails_after_reboot
4. test_prepared_missing_artifact_fails_after_reboot
5. test_verified_missing_artifact_fails_after_reboot
6. test_active_runtime_mismatch_fails_after_reboot

Runtime command capability UT set:
1. test_generic_provider_reports_unsupported_ops
2. test_storage_mount_requires_port_hook
3. test_storage_commands_use_port_fs_ops
4. test_supported_op_requires_arguments
5. test_generic_hooks_execute_generic_enum_ids
6. test_generic_hooks_require_explicit_generic_registration
7. test_supported_disconnect_requires_hook

Port filesystem contract UT set:
1. test_null_fs_ops_reset_to_empty_table
2. test_fs_ops_forward_registered_callbacks
3. test_paths_reject_invalid_values

Network manager port bridge UT set:
1. test_collect_status_uses_port_ready_state
2. test_collect_status_rejects_bad_transport
3. test_collect_status_propagates_port_error
4. test_network_ops_forward_probe_endpoint

Event module UT set:
1. test_publish_app_event_forwards_topic_and_payload
2. test_publish_app_event_requires_valid_contract
3. test_build_key_accepts_framework_suffixes

Diagnostics UT set:
1. test_format_context_uses_safe_defaults
2. test_update_transaction_accepts_null_fields

Response UT set:
1. test_build_error_response_contract
2. test_build_lease_responses_contract
3. test_build_query_device_response_contract
4. test_build_query_apps_response_contract
5. test_build_query_apps_snapshot_response_contract
6. test_build_query_leases_response_contract
7. test_validate_request_metadata_payload

## 5. Approximate UT Coverage

Coverage note:
1. Current environment does not provide gcov/lcov runtime report for this UT target, so coverage below is a test-case to code-path estimation.
2. Estimation basis is function-path coverage against current module sources under the tests/unit CMake target.
3. This section is a temporary fallback until quantified Linux coverage evidence is produced by `run_ut_coverage_linux.sh`.

Estimated coverage (rough):
1. neuro_app_command_registry: about 80% to 90% of key functional paths (register/find/enable/remove/capacity and invalid-name checks).
2. neuro_app_callback_bridge: about 90% to 100% of key functional paths (argument forwarding, null request fallback, reply buffer handling).
3. neuro_unit_app_command: about 65% to 78% of key service-entry paths (reply-context forwarding, lease gate invocation, unsupported command error, runtime start success reply, registered callback success, callback dispatch failure, and disabled callback command handling).
4. neuro_request_envelope: about 85% to 95% of key functional paths (parse + validate for common/write/protected-write, target mismatch, null-input and extractor default paths).
5. neuro_request_policy: about 95% to 100% of key functional paths (command/query/update requirement mapping and null-input handling).
6. neuro_update_manager: about 85% to 95% of key functional paths (ordered transitions, rollback, and reboot reconcile failure/retention paths).
7. neuro_lease_manager: about 85% to 95% of key functional paths (acquire/release/conflict/preemption/expiry).
8. neuro_recovery_seed_store: about 84% to 93% of key functional paths (encode/decode integrity, supported-version window enforcement, corrupted-seed rejection, and snapshot build/apply path).
9. neuro_recovery_reconcile: about 90% to 100% of key reboot reconcile decision paths (interrupted transition, missing artifact, runtime mismatch).
10. app_runtime_cmd capability gate: about 85% to 94% of key capability and argument-validation paths (unsupported contract, storage/network port dispatch, argument guardrail, connect/disconnect hook registration contract).
11. neuro_unit_port filesystem contract: about 80% to 90% of key contract paths (ops registration/reset and path validation behavior).
12. neuro_network_manager port bridge: about 82% to 92% of key port-status/probe contract paths (ready state, unsupported transport, provider error propagation, and probe callback forwarding).
13. neuro_unit_event: about 85% to 95% of key topic-build and app-event publish contract paths (runtime configuration, app-topic construction, invalid-token rejection).
14. neuro_unit_diag: about 55% to 70% of key diagnostic helper paths (context formatting default behavior and update transaction log entry-point tolerance).
15. neuro_unit_response: about 75% to 88% of key response-builder paths (exact JSON compatibility for error, lease, query-device, query-apps, query-apps snapshot DTO, query-leases, and metadata validation).
16. neuro_unit_update_service: about 80% to 90% of key service-entry paths (prepare/verify/activate/rollback success flow, recovery aliasing, unsupported action mapping, recovery seed init failure, repeated prepare semantics, and recovery seed checkpoint persistence in rollback).
17. Overall for this UT bundle: about 87% to 94% of key module logic paths.

## 6. Execution Procedure

### 6.0 Canonical Host Execution Policy (Linux)

Policy:
1. For release-1.1.0 migration work, Linux is the canonical host path for local evidence and CI evidence.
2. Start the Linux host session with:
	- `source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate --strict`
3. Linux canonical execution uses the repository-local `.venv` activated by `setup_neurolink_env.sh`; Linux does not use conda for NeuroLink build or test flows.
4. `--strict` validates required build tools and reports optional capabilities separately; missing `qemu-system-x86_64` or `gcovr` must not block the base `unit-ut` build command.
5. Board-oriented builds that depend on `zenoh-pico` require `zephyr/submanifests/zenoh-pico.yaml` plus a materialized `modules/lib/zenoh-pico`; run `west update zenoh-pico` or `west update` before invoking the board presets.
6. If the repository was copied from Windows, preview and clear `Zone.Identifier` leftovers before running build/test commands:
	- `bash applocation/NeuroLink/scripts/clean_zone_identifier.sh`
	- if needed, `bash applocation/NeuroLink/scripts/clean_zone_identifier.sh --execute`

7. Primary Linux style commands are:
	- `bash applocation/NeuroLink/scripts/format_neurolink_c_style.sh --check-only`
	- if needed, `bash applocation/NeuroLink/scripts/format_neurolink_c_style.sh --fix`
	- `bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
	- `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-ut --pristine-always`
8. Primary Linux UT commands are:
	- `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
	- `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh`
9. The Linux UT and coverage scripts self-bootstrap through `setup_neurolink_env.sh`, so they remain runnable from a fresh shell; the session bootstrap above remains the canonical host-start sequence.
10. `run_ut_linux.sh` must always execute the `native_sim` path; the `qemu_x86_64` path is additional validation that runs only when `qemu-system-x86_64` is available on the host.
11. Repository CI for this path is tracked in `.github/workflows/neurolink_unit_ut_linux.yml`.
12. Windows and WSL helper scripts remain allowed for compatibility, but they do not replace Linux-native release evidence when a Linux path is available.

### 6.0.1 Windows Compatibility Policy

Policy:
1. Windows compile and test execution in this project must use PowerShell terminal sessions.
2. Start the session with:
	- `. applocation/NeuroLink/scripts/setup_neurolink_env.ps1 -Activate -Strict`
3. If repository content carries Windows Zone.Identifier ADS or copied literal files, preview or clear them with:
	- `pwsh applocation/NeuroLink/scripts/clean_zone_identifier.ps1`
	- if needed, `pwsh applocation/NeuroLink/scripts/clean_zone_identifier.ps1 -Execute`
4. Every compile/test command must start with environment switch:
	- `& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"`
	- `D:/Compiler/anaconda/Scripts/activate`
	- `conda activate zephyr`
5. Do not replace this requirement with `conda run -n zephyr ...` for primary evidence commands on Windows.
6. Command evidence in logs/runbooks should include the explicit activation pre-step.
7. C code style is mandatory and must pass before build/test evidence is accepted:
	- `pwsh applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -CheckOnly`
	- if failed, run `pwsh applocation/NeuroLink/scripts/format_neurolink_c_style.ps1 -Fix` and re-run check.
	- `pwsh applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1`
	- current gate must remain clean; do not accept new Linux-style warnings into the active Unit baseline.

Activation note:
1. Do not use only `D:/Compiler/anaconda/Scripts/activate ; conda activate zephyr` in fresh `pwsh` sessions; that sequence is known to fail intermittently without the hook script.
2. If `conda activate zephyr` does not change `CONDA_DEFAULT_ENV`, re-run the hook script in the same session, then run `D:/Compiler/anaconda/Scripts/activate` and `conda activate zephyr` again.
2. On Windows hosts without native `perl`, the Linux-style check uses WSL to run `zephyr/scripts/checkpatch.pl`; ensure WSL is available in the same machine policy baseline.

### 6.1 Build-Only Validation on Project Board

Command:

```powershell
& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west build -p always -b dnesp32s3b/esp32s3/procpu applocation/NeuroLink/neuro_unit/tests/unit -d build/neurolink_unit_ut
```

Pass criteria:
1. Build completes without compile/link errors.
2. ELF image is generated at build/neurolink_unit_ut/zephyr/zephyr.elf.

### 6.2 Host/Simulator Test Execution Attempt with Twister

Attempt A:

```powershell
& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west twister -T applocation/NeuroLink/neuro_unit/tests/unit -p native_sim -v
```

Observed result:
1. Scenario discovered.
2. 0 configurations selected for execution in current environment.

Attempt B (qualified platform name):

```powershell
& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west twister -T applocation/NeuroLink/neuro_unit/tests/unit -p native_sim/native/64 -v
```

Observed result:
1. Same as Attempt A, still 0 executable configurations.

Attempt C (unit testing platform):

```powershell
& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west twister -T applocation/NeuroLink/neuro_unit/tests/unit -p unit_testing -v
```

Observed result:
1. Twister selected one configuration, then failed in CMake.
2. Failure reason: No board named unit_testing found in current workspace board set.

Resolution:
1. Kept testcase type as unit (required by current Twister schema in this workspace).
2. Removed unit_testing from platform_allow to avoid selecting an unavailable board.

Current runnable command:

```powershell
& "D:/Compiler/anaconda/shell/condabin/conda-hook.ps1"
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west twister -T applocation/NeuroLink/neuro_unit/tests/unit -p native_sim -v
```

Current observed behavior:
1. Test suite is discovered.
2. No executable configuration is selected on this Windows host setup for native_sim unit-test flow.

Attempt D (direct native_sim build without Twister):

```powershell
(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west build -p always -b native_sim applocation/NeuroLink/neuro_unit/tests/unit -d build/neurolink_unit_ut_native_sim
```

Observed result:
1. Build failed during devicetree preprocessing for `native_sim.dts`.
2. Runtime execution path could not be reached because configure stage failed.

Attempt E (qemu fallback build path):

```powershell
(& conda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
D:/Compiler/anaconda/Scripts/activate
conda activate zephyr
west build -p always -b qemu_x86 applocation/NeuroLink/neuro_unit/tests/unit -d build/neurolink_unit_ut_qemu_x86
west build -p always -b qemu_x86_64 applocation/NeuroLink/neuro_unit/tests/unit -d build/neurolink_unit_ut_qemu_x86_64
```

Observed result:
1. Both qemu targets compile and link successfully.
2. Runtime `-t run` failed due host environment dependencies:
	- qemu binary unresolved (`QEMU:FILEPATH=QEMU-NOTFOUND`)
	- Windows run helper command uses `grep`, which is unavailable in cmd run path.

### 6.3 Quantified Coverage Execution on Linux (Canonical) and Windows/WSL (Compatibility)

Purpose:
1. Produce quantified UT coverage for the `tests/unit` target using `native_sim/native/64` host coverage.
2. Generate reproducible lcov HTML artifacts and a machine-readable summary file.
3. Treat the Linux invocation as canonical for release-1.1.0 migration evidence; use the Windows trigger only when bridging into WSL.

Mandatory Linux prerequisites:
1. `gcc`, `west`, `cmake`, `ninja`, `timeout`
2. Zephyr SDK / host toolchain already resolvable in WSL.
3. `gcovr` available either in PATH or at the west pipx venv path (`~/.local/share/pipx/venvs/west/bin/gcovr`).

Linux command:

```bash
bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh
```

Windows trigger for WSL:

```powershell
pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_from_windows.ps1 -Distro Ubuntu
```

Script behavior:
1. Builds `applocation/NeuroLink/neuro_unit/tests/unit` for `native_sim/native/64` with `CONFIG_COVERAGE=y`.
2. Runs `build/neurolink_unit_ut_native_sim_64_cov/zephyr/zephyr.exe` under timeout control.
3. Uses `gcovr` on the generated `.gcda/.gcno` data under the build directory.
4. Filters coverage to `applocation/NeuroLink/neuro_unit/src/*` so the report focuses on Unit source-under-test rather than test files.
5. Generates HTML coverage output plus a summary file with line/function/branch metrics.

Current validated status on 2026-04-14:
1. `native_sim/native/64` coverage build succeeds in WSL with `CONFIG_COVERAGE=y`.
2. Host-native UT executable runs successfully and emits `.gcda` files under `build/neurolink_unit_ut_native_sim_64_cov`.
3. Quantified summary generation succeeds through `gcovr` against the 64-bit host-native build.

Coverage artifacts:
1. `applocation/NeuroLink/smoke-evidence/ut-coverage/<timestamp>/summary.txt`
2. `native_sim_build.log`
3. `native_sim_run.log`
4. `coverage_gcovr_summary.txt`
6. `coverage_html/index.html`

## 7. Current Validation Status

Completed evidence:
1. Source-level UT suite implemented with 71 test cases.
2. Recovery seed version-window policy now has dedicated UT rejection coverage for unsupported older/newer versions.
3. Board-target build validation succeeded.
4. Twister platform mismatch root cause was identified and unsupported unit_testing platform was removed from testcase metadata.
5. Twister after recovery-seed/update/lease test integration still discovers 1 scenario and selects 0 configurations on this Windows host.
6. Direct native_sim build path was executed and failed at devicetree preprocess stage.
7. qemu_x86 and qemu_x86_64 fallback builds were executed and link successfully.
8. qemu runtime execution blocker is now concrete and reproducible (`QEMU-NOTFOUND` plus missing `grep` in Windows run helper command path).
9. On-device integration smoke rerun (2026-04-10) confirms update control-plane stability after async dispatch change:
	- board-side prep: `app mount_storage` and `app network_connect` succeeded
	- zenoh readiness observed: `queryables ready on node 'unit-01'`
	- Core flow succeeded end-to-end: `query device -> lease acquire -> deploy prepare -> deploy verify -> deploy activate -> query apps -> query device`
	- `query apps` returned `neuro_unit_app` in `RUNNING` state after activate
10. Architecture-level persistence redesign validated on device:
	- recovery seed default path migrated to SD root (`/SD:/recovery.seed`) to reduce nested-directory FS operations
	- seed save flow simplified to tmp-to-primary atomic replacement (with existing-target replacement fallback)
	- residual FS noise `mkdir -17` / `unlink -2` was not observed in latest prepare/activate cycle
11. Quantified coverage script entry point is now added for Linux/WSL execution:
	- `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh`
	- `pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_from_windows.ps1 -Distro Ubuntu`
12. Quantified coverage execution path is now validated on host-native 64-bit simulator:
	- `native_sim/native/64` coverage build succeeds under WSL
	- UT executable runs and writes `.gcda` artifacts for Unit source files

Remaining gap:
1. Runtime pass/fail execution evidence remains pending because current Windows host lacks a runnable simulator chain for this suite (`native_sim` devicetree preprocess failure and missing qemu runtime dependencies).
2. Boot stage may still print `mount point not found` before SD mount command is issued; this is currently treated as initialization-timing noise, not update-flow failure.
3. Quantified coverage evidence still needs one scripted artifact capture run under `smoke-evidence/ut-coverage` for release-ledger indexing.

Decision note:
1. Final executable UT pass/fail evidence for release will be produced in a Linux environment.
2. Linux runtime evidence track is resumed by owner direction; current Windows host can trigger local WSL Ubuntu execution for runtime evidence.

## 8. Recommended Next Actions for Full Execution Evidence

1. Keep testcase platform list aligned with actually available runnable platforms in this workspace.
2. If host runtime evidence is mandatory, resolve native_sim devicetree preprocess issue first, then rerun Twister.
3. Install and bind qemu binary for Zephyr run targets (cache must not keep `QEMU-NOTFOUND`) or execute this suite in a Linux CI image that already provides qemu + grep.
4. Keep CI command that always builds this UT target, even when runtime execution is temporarily skipped on Windows host.
5. Prefer the scripted Linux evidence path:
	- Linux host: `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
	- Windows trigger for WSL: `pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1 [-Distro <name>]`
6. Prefer the scripted Linux coverage path for quantified closure:
	- Linux host: `bash applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh`
	- Windows trigger for WSL: `pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_from_windows.ps1 [-Distro <name>]`
7. Prefer CI-hosted Linux runtime evidence when local Linux host is unavailable:
	- GitHub Actions workflow: `.github/workflows/neurolink_unit_ut_linux.yml`
	- trigger mode: `workflow_dispatch` or code push under `applocation/NeuroLink/neuro_unit/**`
	- expected artifact name: `neurolink-unit-ut-runtime-evidence`
8. For release evidence closure, append runtime `summary.txt` plus the three raw logs (`twister_native_sim.log`, `qemu_x86_64_build.log`, `qemu_x86_64_run.log`) into project ledger references.
9. For quantified coverage closure, append coverage `summary.txt`, `coverage_lcov_summary.txt`, and `coverage_html/index.html` path into project ledger references.
10. Current workstation readiness refresh on 2026-04-12:
	- `wsl -l -v` now reports `Ubuntu` on WSL2.
	- local WSL Ubuntu was provisioned and can execute `run_ut_linux.sh`.
	- runtime result quality now depends on qemu run behavior and test outcomes, not missing host prerequisites.

## 10. Linux Real-Board Serial Method (Release 1.1.0)

Use this method when validating the physical `dnesp32s3b/esp32s3/procpu` board from Linux or WSL.

Validated serial tool:
1. `python3 -m serial.tools.miniterm`
2. wrapper helper: `bash applocation/NeuroLink/scripts/monitor_neurolink_uart.sh --device /dev/ttyACM0`

Validated bring-up sequence on 2026-04-19:
1. board was attached into WSL through `usbipd-win` and appeared as `/dev/ttyACM0`
2. Linux flash succeeded with `bash applocation/NeuroLink/scripts/build_neurolink.sh --preset flash-unit --esp-device /dev/ttyACM0`
3. `miniterm` session showed a stable Zephyr shell prompt (`uart:~$`)
4. `app status` succeeded on-device through the serial shell
5. device-side network readiness was observed repeatedly with IPv4 assignment (`192.168.2.69`)

Observed blocker:
1. device-side zenoh connect attempts to `tcp/192.168.2.95:7447` timed out during WSL-hosted router testing even though `zenohd` was running in WSL
2. this is currently treated as a Windows/WSL inbound networking policy issue, not a board serial or flash issue
3. before changing firmware defaults, verify Windows firewall approval for TCP `7447`

Evidence:
1. `applocation/NeuroLink/smoke-evidence/serial-diag/miniterm-20260419T063813Z.log`
2. `applocation/NeuroLink/smoke-evidence/serial-diag/session.log`
3. `applocation/NeuroLink/smoke-evidence/zenoh-router/20260419T062211Z/zenohd.log`

## 9. WSL Ubuntu Setup and Runtime Method (China Network Profile)

Use this method when operating in domestic network conditions and local Windows host must drive Linux UT evidence.

### 9.1 Ubuntu mirror + dependency bootstrap

1. In WSL Ubuntu, switch apt mirror to a domestic source (for example TUNA) and verify update:
	- backup current source file first
	- run `sudo apt-get update` after switching
2. Install required base packages:
	- `sudo apt-get install -y python3-pip python3-venv python3-setuptools python3-wheel git cmake ninja-build gperf ccache dfu-util device-tree-compiler wget xz-utils file make gcc g++ libsdl2-dev libmagic1 qemu-system-x86 qemu-utils`
3. Install `west` in user space (Ubuntu 24.04 PEP668-safe path):
	- `sudo apt-get install -y pipx`
	- `pipx ensurepath`
	- `pipx install west`
4. Install Zephyr python requirements into west venv:
	- `~/.local/share/pipx/venvs/west/bin/pip install -r /mnt/d/Software/project/zephyrproject/zephyr/scripts/requirements.txt`
5. Install Zephyr SDK and x86 toolchain:
	- `~/.local/bin/west sdk install -b /home/<user> -t x86_64-zephyr-elf`
	- verify: `~/.local/bin/west sdk list`

### 9.2 Runtime evidence execution from Windows

1. Trigger Linux script from PowerShell:
	- `pwsh applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1 -Distro Ubuntu`
2. Script behavior:
	- auto-detects and exports `ZEPHYR_SDK_INSTALL_DIR`
	- streams `qemu_x86_64_build` and `qemu_x86_64_run` logs in real time via `tee`
	- enforces run timeout via `RUN_TIMEOUT_SEC` (default `900`)
	- detects ztest PASS markers and auto-terminates qemu run to avoid manual Ctrl+C
	- records `qemu_run_rc=0` on successful auto-termination path
3. Evidence artifacts:
	- `applocation/NeuroLink/smoke-evidence/ut-runtime/<timestamp>/summary.txt`
	- `twister_native_sim.log`
	- `qemu_x86_64_build.log`
	- `qemu_x86_64_run.log`

Note:
1. Numbering in this section is append-only in spirit; historical entries are retained. Current actionable order is items 1, 2, 3, 4, 5, 6, and 7.
2. qemu logs may include `terminating on signal 2` when script-controlled auto-stop is triggered after PASS markers; this is expected for the current runtime harness method.

