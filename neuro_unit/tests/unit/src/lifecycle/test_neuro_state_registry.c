#include <zephyr/sys/printk.h>
#include <zephyr/ztest.h>

#include <string.h>

#include "neuro_state_registry.h"

static struct neuro_state_registry g_registry;

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	neuro_state_registry_init(&g_registry, "unit-01");
}

ZTEST(neuro_state_registry, test_session_ready_transition_updates_version_once)
{
	uint64_t version;

	version = neuro_state_registry_version(&g_registry);
	zassert_equal(version, 0U, "initial version should be zero");

	neuro_state_registry_set_session_ready(&g_registry, true);
	version = neuro_state_registry_version(&g_registry);
	zassert_equal(
		version, 1U, "session_ready semantic change must bump version");

	neuro_state_registry_set_session_ready(&g_registry, true);
	version = neuro_state_registry_version(&g_registry);
	zassert_equal(
		version, 1U, "same session_ready value must not bump version");
}

ZTEST(neuro_state_registry, test_network_transition_updates_snapshot)
{
	struct neuro_network_status status = { 0 };
	struct neuro_state_snapshot snapshot;
	uint64_t version;

	status.state = NEURO_NETWORK_READY;
	snprintk(status.ipv4_addr, sizeof(status.ipv4_addr), "192.168.2.69");

	neuro_state_registry_set_network(&g_registry, &status);
	version = neuro_state_registry_version(&g_registry);
	zassert_equal(version, 1U, "network semantic change must bump version");

	neuro_state_registry_get_snapshot(&g_registry, &snapshot);
	zassert_equal(snapshot.network_state, NEURO_NETWORK_READY,
		"network state should be updated");
	zassert_equal(snapshot.health, NEURO_STATE_HEALTH_OK,
		"health should follow network readiness");
	zassert_true(strcmp(snapshot.ipv4_addr, "192.168.2.69") == 0,
		"ipv4 address should round-trip into snapshot");

	neuro_state_registry_set_network(&g_registry, &status);
	version = neuro_state_registry_version(&g_registry);
	zassert_equal(
		version, 1U, "same network snapshot must not bump version");
}

ZTEST(neuro_state_registry, test_runtime_lease_update_transitions_are_semantic)
{
	struct neuro_state_snapshot snapshot;
	uint64_t version;

	neuro_state_registry_set_runtime_counters(&g_registry, 2U, 1U);
	neuro_state_registry_set_lease_count(&g_registry, 3U);
	neuro_state_registry_set_update_state(
		&g_registry, "neuro_unit_app", "verify", "in_progress");

	version = neuro_state_registry_version(&g_registry);
	zassert_equal(version, 3U,
		"three semantic updates should bump version three times");

	neuro_state_registry_set_runtime_counters(&g_registry, 2U, 1U);
	neuro_state_registry_set_lease_count(&g_registry, 3U);
	neuro_state_registry_set_update_state(
		&g_registry, "neuro_unit_app", "verify", "in_progress");

	version = neuro_state_registry_version(&g_registry);
	zassert_equal(version, 3U,
		"repeating the same values should not bump version");

	neuro_state_registry_get_snapshot(&g_registry, &snapshot);
	zassert_equal(snapshot.app_count, 2U,
		"app_count should be reflected in snapshot");
	zassert_equal(snapshot.running_count, 1U,
		"running_count should be reflected in snapshot");
	zassert_equal(snapshot.lease_count, 3U,
		"lease_count should be reflected in snapshot");
	zassert_true(strcmp(snapshot.update_app_id, "neuro_unit_app") == 0,
		"update_app_id should be reflected in snapshot");
	zassert_true(strcmp(snapshot.update_stage, "verify") == 0,
		"update_stage should be reflected in snapshot");
	zassert_true(strcmp(snapshot.update_status, "in_progress") == 0,
		"update_status should be reflected in snapshot");
}

ZTEST_SUITE(neuro_state_registry, NULL, NULL, test_reset, NULL, NULL);
