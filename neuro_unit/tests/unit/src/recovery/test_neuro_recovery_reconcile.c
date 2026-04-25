#include <zephyr/ztest.h>

#include <string.h>

#include "neuro_update_manager.h"

static void reach_prepare_state(
	struct neuro_update_manager *manager, const char *app_id)
{
	int ret;

	ret = neuro_update_manager_prepare_begin(manager, app_id);
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(manager, app_id);
	zassert_equal(ret, 0, "prepare complete should succeed");
}

static void reach_verifying_state(
	struct neuro_update_manager *manager, const char *app_id)
{
	reach_prepare_state(manager, app_id);
	zassert_equal(neuro_update_manager_verify_begin(manager, app_id), 0,
		"verify begin should succeed");
}

static void reach_activating_state(
	struct neuro_update_manager *manager, const char *app_id)
{
	reach_verifying_state(manager, app_id);
	zassert_equal(neuro_update_manager_verify_complete(manager, app_id), 0,
		"verify complete should succeed");
	zassert_equal(neuro_update_manager_activate_begin(manager, app_id), 0,
		"activate begin should succeed");
}

static void assert_reconcile_failed_with_error(
	struct neuro_update_manager *manager, const char *app_id,
	bool runtime_active, bool artifact_available, const char *expect_error)
{
	int ret;

	ret = neuro_update_manager_reconcile_after_boot(
		manager, app_id, runtime_active, artifact_available);
	zassert_equal(ret, 0, "reconcile should complete");
	zassert_equal(neuro_update_manager_state_for(manager, app_id),
		NEURO_UPDATE_STATE_FAILED, "state should transition to FAILED");
	zassert_true(
		strcmp(neuro_update_manager_last_error_for(manager, app_id),
			expect_error) == 0,
		"last_error mismatch");
}

ZTEST(neuro_recovery_reconcile,
	test_interrupted_prepare_state_fails_after_reboot)
{
	struct neuro_update_manager manager;

	neuro_update_manager_init(&manager);
	zassert_equal(neuro_update_manager_prepare_begin(&manager, "demo"), 0,
		"prepare begin should succeed");
	assert_reconcile_failed_with_error(&manager, "demo", false, false,
		"recovery interrupted transition");
}

ZTEST(neuro_recovery_reconcile,
	test_interrupted_verifying_state_fails_after_reboot)
{
	struct neuro_update_manager manager;

	neuro_update_manager_init(&manager);
	reach_verifying_state(&manager, "demo");
	assert_reconcile_failed_with_error(&manager, "demo", false, false,
		"recovery interrupted transition");
}

ZTEST(neuro_recovery_reconcile,
	test_interrupted_activating_state_fails_after_reboot)
{
	struct neuro_update_manager manager;

	neuro_update_manager_init(&manager);
	reach_activating_state(&manager, "demo");
	assert_reconcile_failed_with_error(&manager, "demo", false, true,
		"recovery interrupted transition");
}

ZTEST(neuro_recovery_reconcile,
	test_prepared_missing_artifact_fails_after_reboot)
{
	struct neuro_update_manager manager;

	neuro_update_manager_init(&manager);
	reach_prepare_state(&manager, "demo");
	assert_reconcile_failed_with_error(
		&manager, "demo", false, false, "recovery artifact missing");
}

ZTEST(neuro_recovery_reconcile,
	test_verified_missing_artifact_fails_after_reboot)
{
	struct neuro_update_manager manager;
	int ret;

	neuro_update_manager_init(&manager);
	reach_verifying_state(&manager, "demo");
	ret = neuro_update_manager_verify_complete(&manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");

	assert_reconcile_failed_with_error(
		&manager, "demo", false, false, "recovery artifact missing");
}

ZTEST(neuro_recovery_reconcile, test_active_runtime_mismatch_fails_after_reboot)
{
	struct neuro_update_manager manager;

	neuro_update_manager_init(&manager);
	reach_activating_state(&manager, "demo");
	zassert_equal(neuro_update_manager_activate_complete(&manager, "demo"),
		0, "activate complete should succeed");

	assert_reconcile_failed_with_error(&manager, "demo", false, true,
		"recovery runtime state mismatch");
}

ZTEST_SUITE(neuro_recovery_reconcile, NULL, NULL, NULL, NULL, NULL);
