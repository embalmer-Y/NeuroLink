# NeuroLink Release 1.0.3 Lease and Recovery Failure-Mode Matrix (Draft)

## 1. Purpose

This matrix defines the initial failure modes for week-1 pre-research execution.
Each mode must map to executable verification and evidence paths.

## 2. Failure-Mode Matrix

| FM ID | Domain | Scenario | Existing coverage | Gap status | Next concrete action |
| --- | --- | --- | --- | --- | --- |
| FM-LEASE-001 | Lease ownership | Protected write request presents lease token owned by another source pair. | `test_release_rejects_holder_mismatch`; `test_require_resource_rejects_mismatch_and_expiry` | Partial | add end-to-end protected-write holder-mismatch UT at request/handler layer (`UT-LEASE-OWNER-001`) |
| FM-LEASE-002 | Lease expiry | Request arrives after lease TTL expiration boundary. | `test_require_resource_rejects_mismatch_and_expiry`; `test_expire_all_clears_active_leases` | Covered | keep as regression guard; no week-1 code change required |
| FM-LEASE-003 | Priority preemption | High-priority request competes with active lower-priority lease. | `test_acquire_preempts_with_higher_priority`; `test_acquire_rejects_conflict_without_higher_priority` | Partial | add deterministic post-preemption state assertion at handler level (`UT-LEASE-PREEMPT-002`) |
| FM-LEASE-004 | Idempotency replay | Duplicate protected-write with same idempotency key under same lease. | request metadata requirement only (`test_validate_write_requires_priority_and_idempotency`) | Missing | add first dedicated replay/idempotency UT slice (`UT-LEASE-IDEM-001`) |
| FM-REC-001 | Corrupted seed file | Recovery seed exists but payload parse fails or schema marker invalid. | `test_decode_rejects_crc_mismatch`; `test_decode_rejects_truncated_payload` | Partial | add invalid-header/magic/schema-path UT (`UT-REC-SEED-HEADER-001`) |
| FM-REC-002 | Missing artifact | Recovery seed references unavailable artifact. | `test_prepared_missing_artifact_fails_after_reboot`; `test_verified_missing_artifact_fails_after_reboot` | Covered | connect to release evidence checklist and smoke trace review |
| FM-REC-003 | Interrupted transition | Power-loss style interruption between seed write and state transition commit. | `test_interrupted_prepare_state_fails_after_reboot`; `test_interrupted_verifying_state_fails_after_reboot`; `test_interrupted_activating_state_fails_after_reboot`; `test_store_load_promotes_valid_tmp_when_primary_missing` | Partial | add tmp corruption/failure-path variant after current promotion-path landing |
| FM-REC-004 | Seed version mismatch | Existing seed version older/newer than supported range. | `test_decode_rejects_version_mismatch`; `test_decode_rejects_older_unsupported_version` | Covered | keep as baseline regression guard |
| FM-REC-005 | Atomic rename edge | Target directory missing or rename path partially unavailable. | `test_store_save_retries_rename_after_existing_target_removed` | Partial | add hard failure branch for unlink/second-rename failure after current fallback-path landing |
| FM-PIPE-001 | Cross-layer gate order | Style/UT/smoke gates executed out of intended order in release flow. | process notes in `TESTING.md`; no machine-checked contract | Missing | define gate-order checklist and script-level pass/fail contract (`PIPE-GATE-001`) |

## 3. Initial Coverage Targets

| Module | Baseline issue | Week-2 target |
| --- | --- | --- |
| `neuro_recovery_seed_store.c` | low branch coverage in corruption/migration edges | branch coverage >= 70% with explicit FM-REC mapping |
| `neuro_artifact_store.c` | medium branch coverage with missing-artifact edges | branch coverage >= 70% and FM-REC-002/003 tests |
| `neuro_lease_manager.c` | lease preemption and expiry edges need stronger UT depth | branch coverage >= 75% with FM-LEASE mapping |

## 4. Evidence Naming Draft

1. UT runtime: `ut-runtime/<timestamp>/...`
2. Failure-mode run note: `fm-<id>-<timestamp>.md`
3. Smoke run evidence: existing `SMOKE-017B-001-<timestamp>.ndjson`

## 5. Next Update

1. Link each FM entry to concrete commands and expected pass/fail signatures.
2. Extend the landed recovery-seed gap tests with negative-path variants for tmp corruption and rename/unlink hard failure.
3. Promote this draft to release checklist input after week-2 gate design landing.
