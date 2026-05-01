#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_update_manager.h"

ZTEST(neuro_update_manager, test_prepare_verify_activate_success_order)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");

	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed after prepare");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");

	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, 0, "activate begin should succeed after verify");
	ret = neuro_update_manager_activate_complete(&manager, "demo");
	zassert_equal(ret, 0, "activate complete should succeed");

	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_ACTIVE, "final state should be ACTIVE");
}

ZTEST(neuro_update_manager, test_verify_before_prepare_rejected)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, -EPERM, "verify before prepare must be rejected");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_NONE, "state should remain NONE");
}

ZTEST(neuro_update_manager, test_activate_before_verify_rejected)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");

	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, -EPERM, "activate before verify must be rejected");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_PREPARED, "state should remain PREPARED");
}

ZTEST(neuro_update_manager, test_remove_deletes_entry)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);
	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should create entry");
	zassert_not_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_NONE, "entry should exist before remove");

	ret = neuro_update_manager_remove(&manager, "demo");
	zassert_equal(ret, 0, "remove should delete existing entry");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_NONE, "removed entry should report NONE");
	zassert_equal(neuro_update_manager_remove(&manager, "demo"), -ENOENT,
		"removing a missing entry should report ENOENT");
}

ZTEST(neuro_update_manager, test_prepare_fail_marks_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_fail(
		&manager, "demo", "download failed");
	zassert_equal(ret, 0, "prepare fail should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"prepare failure should transition to FAILED");
}

ZTEST(neuro_update_manager, test_verify_fail_marks_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_fail(
		&manager, "demo", "artifact missing");
	zassert_equal(ret, 0, "verify fail should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"verify failure should transition to FAILED");
}

ZTEST(neuro_update_manager, test_activate_fail_marks_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");
	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, 0, "activate begin should succeed");
	ret = neuro_update_manager_activate_fail(
		&manager, "demo", "start failed");
	zassert_equal(ret, 0, "activate fail should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"activate failure should transition to FAILED");
}

ZTEST(neuro_update_manager, test_prepare_rejected_while_in_progress)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "first prepare begin should succeed");
	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(
		ret, -EBUSY, "second prepare begin should be rejected as busy");
}

ZTEST(neuro_update_manager, test_rollback_success_marks_rolled_back)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");
	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, 0, "activate begin should succeed");
	ret = neuro_update_manager_activate_complete(&manager, "demo");
	zassert_equal(ret, 0, "activate complete should succeed");

	ret = neuro_update_manager_record_stable_ref(
		&manager, "demo", "/SD:/apps/demo.llext");
	zassert_equal(ret, 0, "stable ref record should succeed");
	ret = neuro_update_manager_rollback_begin(
		&manager, "demo", "operator requested");
	zassert_equal(ret, 0, "rollback begin should succeed from ACTIVE");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_ROLLBACK_PENDING,
		"rollback begin should checkpoint into ROLLBACK_PENDING");
	ret = neuro_update_manager_rollback_mark_in_progress(&manager, "demo");
	zassert_equal(ret, 0, "rollback mark in progress should succeed");
	ret = neuro_update_manager_rollback_complete(&manager, "demo");
	zassert_equal(ret, 0, "rollback complete should succeed");

	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_ROLLED_BACK,
		"final state should be ROLLED_BACK");
	zassert_true(
		strcmp(neuro_update_manager_stable_ref_for(&manager, "demo"),
			"/SD:/apps/demo.llext") == 0,
		"stable ref should be retained");
	zassert_true(strcmp(neuro_update_manager_rollback_reason_for(
				    &manager, "demo"),
			     "operator requested") == 0,
		"rollback reason should be retained");
}

ZTEST(neuro_update_manager, test_rollback_requires_active_or_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_rollback_begin(
		&manager, "demo", "too early");
	zassert_equal(
		ret, -EPERM, "rollback before ACTIVE/FAILED must be rejected");
}

ZTEST(neuro_update_manager, test_rollback_fail_returns_failed_state)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");
	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, 0, "activate begin should succeed");
	ret = neuro_update_manager_activate_complete(&manager, "demo");
	zassert_equal(ret, 0, "activate complete should succeed");

	ret = neuro_update_manager_rollback_begin(
		&manager, "demo", "rollback trial");
	zassert_equal(ret, 0, "rollback begin should succeed");
	ret = neuro_update_manager_rollback_mark_in_progress(&manager, "demo");
	zassert_equal(ret, 0, "rollback mark in progress should succeed");
	ret = neuro_update_manager_rollback_fail(
		&manager, "demo", "rollback failed");
	zassert_equal(ret, 0, "rollback fail should be accepted");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"rollback failure should transition to FAILED");
}

ZTEST(neuro_update_manager, test_rollback_pending_can_fail_before_unload)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");
	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, 0, "activate begin should succeed");
	ret = neuro_update_manager_activate_complete(&manager, "demo");
	zassert_equal(ret, 0, "activate complete should succeed");

	ret = neuro_update_manager_rollback_begin(
		&manager, "demo", "checkpoint pending");
	zassert_equal(ret, 0, "rollback begin should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_ROLLBACK_PENDING,
		"state should be rollback pending after begin");

	ret = neuro_update_manager_rollback_fail(
		&manager, "demo", "checkpoint save failed");
	zassert_equal(ret, 0,
		"rollback fail should accept pending checkpoint failure");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"checkpoint failure should transition to FAILED");
}

ZTEST(neuro_update_manager,
	test_reconcile_boot_marks_interrupted_transition_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");

	ret = neuro_update_manager_reconcile_after_boot(
		&manager, "demo", false, false);
	zassert_equal(ret, 0, "boot reconcile should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"interrupted transitional state must become FAILED after reboot");
}

ZTEST(neuro_update_manager,
	test_reconcile_boot_prepared_without_artifact_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");

	ret = neuro_update_manager_reconcile_after_boot(
		&manager, "demo", false, false);
	zassert_equal(ret, 0, "boot reconcile should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"prepared state without artifact must fail during reboot reconcile");
}

ZTEST(neuro_update_manager, test_reconcile_boot_active_without_runtime_failed)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");
	ret = neuro_update_manager_activate_begin(&manager, "demo");
	zassert_equal(ret, 0, "activate begin should succeed");
	ret = neuro_update_manager_activate_complete(&manager, "demo");
	zassert_equal(ret, 0, "activate complete should succeed");

	ret = neuro_update_manager_reconcile_after_boot(
		&manager, "demo", false, true);
	zassert_equal(ret, 0, "boot reconcile should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_FAILED,
		"active state with inactive runtime must fail during reboot reconcile");
}

ZTEST(neuro_update_manager,
	test_reconcile_boot_verified_with_artifact_keeps_state)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);

	ret = neuro_update_manager_prepare_begin(&manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");

	ret = neuro_update_manager_reconcile_after_boot(
		&manager, "demo", false, true);
	zassert_equal(ret, 0, "boot reconcile should succeed");
	zassert_equal(neuro_update_manager_state_for(&manager, "demo"),
		NEURO_UPDATE_STATE_VERIFIED,
		"verified state with available artifact should be retained");
}

ZTEST_SUITE(neuro_update_manager, NULL, NULL, NULL, NULL, NULL);
