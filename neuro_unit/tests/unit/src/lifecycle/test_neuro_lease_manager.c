#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_lease_manager.h"

static void build_metadata(struct neuro_request_metadata *metadata,
	const char *source_core, const char *source_agent, const char *lease_id,
	int priority)
{
	neuro_request_metadata_init(metadata);
	snprintk(metadata->request_id, sizeof(metadata->request_id), "%s",
		"req-lease");
	snprintk(metadata->source_core, sizeof(metadata->source_core), "%s",
		source_core);
	snprintk(metadata->source_agent, sizeof(metadata->source_agent), "%s",
		source_agent);
	snprintk(metadata->target_node, sizeof(metadata->target_node), "%s",
		"unit-01");
	metadata->timeout_ms = 5000U;
	metadata->priority = priority;
	if (lease_id != NULL) {
		snprintk(metadata->lease_id, sizeof(metadata->lease_id), "%s",
			lease_id);
	}
}

ZTEST(neuro_lease_manager, test_acquire_require_release_success)
{
	struct neuro_lease_manager manager;
	struct neuro_request_metadata metadata;
	struct neuro_lease_acquire_result acquire_result;
	struct neuro_lease_entry released;
	int ret;

	neuro_lease_manager_init(&manager);
	build_metadata(&metadata, "core-a", "agent-a", "lease-a", 60);

	ret = neuro_lease_manager_acquire(&manager, "app/demo/command/invoke",
		&metadata, 30000, 1000, &acquire_result);
	zassert_equal(ret, 0, "acquire should succeed");
	zassert_equal(strcmp(acquire_result.acquired.lease_id, "lease-a"), 0,
		"acquired lease id must match request");

	ret = neuro_lease_manager_require_resource(
		&manager, "app/demo/command/invoke", &metadata, 1500);
	zassert_equal(ret, 0, "resource should be accessible by holder");

	ret = neuro_lease_manager_release(&manager, &metadata, 1600, &released);
	zassert_equal(ret, 0, "release should succeed");
	zassert_equal(strcmp(released.resource, "app/demo/command/invoke"), 0,
		"released resource must match");
}

ZTEST(neuro_lease_manager,
	test_acquire_rejects_conflict_without_higher_priority)
{
	struct neuro_lease_manager manager;
	struct neuro_request_metadata owner_a;
	struct neuro_request_metadata owner_b;
	struct neuro_lease_acquire_result result;
	int ret;

	neuro_lease_manager_init(&manager);
	build_metadata(&owner_a, "core-a", "agent-a", "lease-a", 70);
	build_metadata(&owner_b, "core-b", "agent-b", "lease-b", 50);

	ret = neuro_lease_manager_acquire(
		&manager, "app/demo/control", &owner_a, 20000, 1000, &result);
	zassert_equal(ret, 0, "first acquire should succeed");

	ret = neuro_lease_manager_acquire(
		&manager, "app/demo/control", &owner_b, 20000, 1200, &result);
	zassert_equal(ret, -EEXIST,
		"lower-priority competing acquire must be rejected");
}

ZTEST(neuro_lease_manager, test_acquire_preempts_with_higher_priority)
{
	struct neuro_lease_manager manager;
	struct neuro_request_metadata owner_a;
	struct neuro_request_metadata owner_b;
	struct neuro_lease_acquire_result result;
	int ret;

	neuro_lease_manager_init(&manager);
	build_metadata(&owner_a, "core-a", "agent-a", "lease-a", 20);
	build_metadata(&owner_b, "core-b", "agent-b", "lease-b", 90);

	ret = neuro_lease_manager_acquire(&manager, "update/app/demo/activate",
		&owner_a, 30000, 1000, &result);
	zassert_equal(ret, 0, "first acquire should succeed");

	ret = neuro_lease_manager_acquire(&manager, "update/app/demo/activate",
		&owner_b, 30000, 2000, &result);
	zassert_equal(ret, 0, "higher-priority acquire should succeed");
	zassert_true(result.preempted, "preemption must be reported");
	zassert_equal(strcmp(result.preempted_entry.lease_id, "lease-a"), 0,
		"preempted lease id must identify old owner");
	zassert_equal(strcmp(result.acquired.lease_id, "lease-b"), 0,
		"acquired lease id must identify new owner");
}

ZTEST(neuro_lease_manager, test_release_rejects_holder_mismatch)
{
	struct neuro_lease_manager manager;
	struct neuro_request_metadata owner;
	struct neuro_request_metadata intruder;
	struct neuro_lease_acquire_result result;
	struct neuro_lease_entry released;
	int ret;

	neuro_lease_manager_init(&manager);
	build_metadata(&owner, "core-a", "agent-a", "lease-a", 60);
	build_metadata(&intruder, "core-b", "agent-b", "lease-a", 60);

	ret = neuro_lease_manager_acquire(&manager, "app/demo/command/invoke",
		&owner, 30000, 1000, &result);
	zassert_equal(ret, 0, "owner acquire should succeed");

	ret = neuro_lease_manager_release(&manager, &intruder, 1500, &released);
	zassert_equal(ret, -EACCES,
		"release with mismatched holder must be rejected");
}

ZTEST(neuro_lease_manager, test_require_resource_rejects_mismatch_and_expiry)
{
	struct neuro_lease_manager manager;
	struct neuro_request_metadata owner;
	struct neuro_request_metadata wrong_id;
	struct neuro_lease_acquire_result result;
	int ret;

	neuro_lease_manager_init(&manager);
	build_metadata(&owner, "core-a", "agent-a", "lease-a", 60);
	build_metadata(&wrong_id, "core-a", "agent-a", "lease-other", 60);

	ret = neuro_lease_manager_acquire(&manager, "app/demo/command/invoke",
		&owner, 100, 1000, &result);
	zassert_equal(ret, 0, "owner acquire should succeed");

	ret = neuro_lease_manager_require_resource(
		&manager, "app/demo/command/invoke", &wrong_id, 1050);
	zassert_equal(
		ret, -EPERM, "mismatched lease id must fail lease requirement");

	ret = neuro_lease_manager_require_resource(
		&manager, "app/demo/command/invoke", &owner, 1200);
	zassert_equal(ret, -EPERM, "expired lease must no longer grant access");
}

ZTEST(neuro_lease_manager, test_expire_all_clears_active_leases)
{
	struct neuro_lease_manager manager;
	struct neuro_request_metadata owner_a;
	struct neuro_request_metadata owner_b;
	struct neuro_lease_acquire_result result;
	int ret;
	int expired;

	neuro_lease_manager_init(&manager);
	build_metadata(&owner_a, "core-a", "agent-a", "lease-a", 60);
	build_metadata(&owner_b, "core-b", "agent-b", "lease-b", 60);

	ret = neuro_lease_manager_acquire(&manager, "app/demo/command/invoke",
		&owner_a, 30000, 1000, &result);
	zassert_equal(ret, 0, "first acquire should succeed");
	ret = neuro_lease_manager_acquire(&manager, "update/app/demo/activate",
		&owner_b, 30000, 1000, &result);
	zassert_equal(ret, 0, "second acquire should succeed");

	expired = neuro_lease_manager_expire_all(&manager);
	zassert_equal(
		expired, 2, "all active leases must be expired on reboot");

	ret = neuro_lease_manager_require_resource(
		&manager, "app/demo/command/invoke", &owner_a, 1100);
	zassert_equal(
		ret, -EPERM, "expired lease must no longer authorize resource");
}

ZTEST_SUITE(neuro_lease_manager, NULL, NULL, NULL, NULL, NULL);
