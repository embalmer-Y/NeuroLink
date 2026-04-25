# NeuroLink Release 1.1.0 Linux Migration Audit and Remediation Plan

## 1. Objective

This document defines the executable plan for Release 1.1.0 Linux migration audit and remediation.
The goal is to make Linux the canonical host path for NeuroLink build, UT, style gate,
and evidence generation, while retaining Windows and WSL only as compatibility entrypoints.

## 2. Scope Decision

### 2.1 In scope

1. Audit all NeuroLink-owned build, test, style, and evidence scripts for Windows-specific assumptions.
2. Remove or isolate platform-dependent path, shell, and environment activation logic from canonical flows.
3. Establish Linux-native CI entrypoints for Unit build, UT runtime, coverage, and style gates.
4. Align project documentation and progress ledger with the actual Linux-first execution path.
5. Define release acceptance criteria and archived evidence requirements for Linux-native validation.

### 2.2 Out of scope

1. Upstream Zephyr or external SDK redesign outside the minimum required integration boundary.
2. New business features unrelated to build/test portability, release governance, or evidence quality.
3. Forcing full behavioral parity across every developer workstation before the Linux canonical path is green.

## 3. Confirmed Baseline Gaps

1. `applocation/NeuroLink/scripts/build_neurolink.ps1` is still a Windows compatibility wrapper that hard-requires PowerShell, `conda activate zephyr`, and `pwsh` re-entry for style checks, while the Linux canonical path uses `setup_neurolink_env.sh` plus the repository-local `.venv`.
2. `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1` is intentionally WSL-only and currently acts as a primary entrypoint for canonical UT evidence.
3. `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md` still defines Windows PowerShell activation as the mandatory host execution policy, which does not match the 1.1.0 Linux-first target.
4. The repository references `.github/workflows/neurolink_unit_ut_linux.yml` in historical records, but no current workflow file exists in the workspace.
5. Several PowerShell scripts still normalize or derive paths in Windows-oriented forms and need an explicit Linux-native replacement or a compatibility-only designation.

## 4. Risk-Driven Workstreams

### WS-A: Script and toolchain portability

Targets:

1. Inventory every NeuroLink-owned script that participates in build, test, style, smoke, or evidence flows.
2. Classify each script as Linux-native, Windows compatibility, WSL bridge, or migration-required.
3. Move canonical flows to shell-agnostic or Linux-native entrypoints where practical.
4. Keep PowerShell wrappers only where they provide compatibility value rather than defining the primary path.

Primary files:

1. `applocation/NeuroLink/scripts/build_neurolink.ps1`
2. `applocation/NeuroLink/scripts/build_neurolink.sh`
3. `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.ps1`
4. `applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh`
5. `applocation/NeuroLink/scripts/format_neurolink_c_style.ps1`
6. `applocation/NeuroLink/scripts/format_neurolink_c_style.sh`
7. `applocation/NeuroLink/scripts/setup_neurolink_env.ps1`
8. `applocation/NeuroLink/scripts/setup_neurolink_env.sh`
9. `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_linux.sh`
10. `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_linux.sh`
11. `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_from_windows.ps1`
12. `applocation/NeuroLink/neuro_unit/tests/unit/run_ut_coverage_from_windows.ps1`
13. `applocation/NeuroLink/scripts/smoke_neurolink_windows.ps1`

### WS-B: Linux CI restoration and evidence flow

Targets:

1. Restore a repository-tracked Linux CI workflow for style check, Unit build, UT runtime, and coverage.
2. Make CI evidence paths match the documented canonical local Linux commands.
3. Remove undocumented dependence on Windows-triggered evidence for release completion.

Primary files:

1. `.github/workflows/neurolink_unit_ut_linux.yml`
2. `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
3. `applocation/NeuroLink/PROJECT_PROGRESS.md`

### WS-C: Documentation and governance realignment

Targets:

1. Replace stale Windows-first or WSL-first wording in active documentation.
2. Explicitly separate current-state compatibility paths from target-state canonical paths.
3. Require each migration slice to record touched scripts, verified Linux commands, evidence path, and rollback notes.

Primary files:

1. `applocation/NeuroLink/PROJECT_PROGRESS.md`
2. `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
3. `applocation/NeuroLink/neuro_unit/README.md`
4. `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_MIGRATION_PLAN.md`
5. `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`

### WS-D: Backlog burn-down and release gate hardening

Targets:

1. Create a prioritized remediation backlog by impact: build/CI first, UT evidence second, smoke/evidence helpers third.
2. Convert undocumented host assumptions into explicit checks or parameters.
3. Raise the 1.1.0 release gate so Linux-native execution is required before closeout.

## 5. Four-Phase Implementation Plan

### Phase 1: Audit baseline and classification

1. Inventory all NeuroLink-owned scripts and release documents in scope.
2. Tag every platform-specific dependency: PowerShell, WSL, conda hook, Windows drive path conversion, `pwsh` recursion, and missing CI entrypoints.
3. Produce the first remediation backlog with severity, owner, and acceptance evidence per item.

### Phase 2: Canonical build and style path migration

1. Define Linux-native build entrypoint(s) for `neuro_unit` and `tests/unit`.
2. Remove mandatory PowerShell-only activation from the canonical path.
3. Make style gate runnable from Linux without PowerShell indirection.
4. Preserve compatibility wrappers only after the Linux-native path is verified.

### Phase 3: UT, coverage, and CI completion

1. Make `run_ut_linux.sh` and `run_ut_coverage_linux.sh` the documented primary execution path.
2. Restore the Linux CI workflow and align it with the local commands.
3. Archive CI and local Linux evidence using the same path conventions.
4. Demote Windows-to-WSL scripts to compatibility helpers in documentation.

### Phase 4: Documentation closure and release hardening

1. Rewrite testing and release docs to distinguish current state, compatibility path, and canonical Linux path.
2. Close or reclassify all high-severity migration backlog items.
3. Record release signoff criteria and final evidence bundle for 1.1.0.

## 6. Initial Remediation Backlog

### P0: Must land before 1.1.0 release closeout

1. Create and verify `.github/workflows/neurolink_unit_ut_linux.yml`.
2. Define a Linux-native canonical build entrypoint for Unit and Unit UT.
3. Define a Linux-native canonical style-check entrypoint with no required PowerShell wrapper.
4. Update `TESTING.md` so Linux is the primary host policy and Windows/WSL is compatibility-only.
5. Standardize Linux and Windows bootstrap scripts so dependency validation is explicit before build/test entry.

### P1: Should land during main migration window

1. Refactor `build_neurolink.ps1` so environment activation is optional or delegated to a cross-platform contract.
2. Classify and document each PowerShell script as compatibility-only or still canonical.
3. Remove stale references to non-existent workflow files from active docs unless the workflow is restored in the same slice.
4. Parameterize path handling where scripts still assume Windows drive or separator semantics.

### P2: Can follow after primary path is stable

1. Normalize smoke and evidence helper scripts so Linux-host execution is first-class where feasible.
2. Add lint or grep-based policy checks to block reintroduction of Windows-only host assumptions in canonical docs.
3. Add a periodic migration audit checklist for future release planning.

## 7. Acceptance Criteria

1. A repository-tracked Linux workflow exists and passes style, build, UT runtime, and coverage steps for NeuroLink Unit scope.
2. The canonical local commands in documentation run on Linux without requiring PowerShell, WSL, or Windows path translation.
3. Windows-specific scripts remain only as compatibility helpers and are marked as such in documentation.
4. `PROJECT_PROGRESS.md` records each migration slice with evidence paths and rollback notes.
5. No active release documentation claims a Linux CI path or canonical flow that is absent from the repository.

## 8. Evidence Conventions

1. Keep Linux UT runtime evidence under `applocation/NeuroLink/smoke-evidence/ut-runtime/`.
2. Keep Linux coverage evidence under `applocation/NeuroLink/smoke-evidence/ut-coverage/` or a documented successor path.
3. For each completed migration slice, record the exact Linux command lines, results, and artifact paths.
4. If a compatibility-only Windows or WSL path is exercised, record it separately and do not treat it as canonical Linux evidence.

## 9. Immediate Next Actions

1. Add a formal execution ledger entry for the 1.1.0 Linux migration plan and first audit slice.
2. Implement the repository Linux CI workflow file.
3. Refactor the active testing guide so the Linux-native path is the primary path.
4. Start the first P0 script migration slice with the build/style entrypoints.
5. Land a deployment standard document and Zone.Identifier cleanup path for Windows-to-Linux repo copies.

## 10. Closure Review (2026-04-20)

This migration plan is now executable and closed against the repository state plus
the archived evidence gathered during the implementation slices.

Acceptance criteria review:

1. Linux workflow present in repository: satisfied.
	- file: `.github/workflows/neurolink_unit_ut_linux.yml`
	- scope now includes style gate, UT runtime, and coverage artifact upload.
2. Canonical local Linux commands run without PowerShell/WSL path translation: satisfied.
	- host bootstrap: `applocation/NeuroLink/scripts/setup_neurolink_env.sh`
	- local evidence: `applocation/NeuroLink/smoke-evidence/ut-runtime/20260419T054456Z/summary.txt`
	- local coverage: `applocation/NeuroLink/smoke-evidence/ut-coverage/20260419T060308Z/summary.txt`
3. Windows scripts demoted to compatibility helpers in documentation: satisfied.
	- active docs: `applocation/NeuroLink/neuro_unit/tests/unit/TESTING.md`
	- deployment contract: `applocation/NeuroLink/docs/project/DEPLOYMENT_STANDARD.md`
4. Migration slices recorded in the progress ledger with evidence paths: satisfied.
	- ledger: `applocation/NeuroLink/PROJECT_PROGRESS.md`
5. Active release documentation now matches repository reality: satisfied.
	- board-smoke/runbook path: `applocation/NeuroLink/docs/project/RELEASE_1.1.0_LINUX_BOARD_SMOKE_RUNBOOK.md`
	- successful Linux smoke evidence: `applocation/NeuroLink/smoke-evidence/SMOKE-017B-LINUX-001-20260420-122723.summary.txt`

Residual operational notes:

1. WSL-hosted `zenohd` remains a compatibility-layer runtime and must be running when real-board smoke is executed.
2. Windows firewall profile alignment and WSL USB attach state remain operational preconditions, not release-documentation gaps.
3. These residuals do not reopen the Linux migration plan because the canonical Linux build/test/doc path and archived evidence are now in place.
