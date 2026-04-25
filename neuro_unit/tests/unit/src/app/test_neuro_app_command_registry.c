#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <string.h>

#include "neuro_app_command_registry.h"

static void neuro_registry_reset(void)
{
	zassert_equal(neuro_app_command_registry_init(), 0,
		"registry init must succeed");
}

static struct neuro_app_command_desc make_desc(
	const char *app_id, const char *command_name, uint32_t timeout_ms)
{
	struct neuro_app_command_desc desc = { 0 };

	snprintk(desc.app_id, sizeof(desc.app_id), "%s", app_id);
	snprintk(desc.command_name, sizeof(desc.command_name), "%s",
		command_name);
	desc.visibility = 1U;
	desc.lease_required = true;
	desc.idempotent = false;
	desc.timeout_ms = timeout_ms;
	desc.state = NEURO_APPCMD_STATE_REGISTERING;

	return desc;
}

ZTEST(neuro_app_command_registry, test_register_and_find_success)
{
	struct neuro_app_command_desc desc =
		make_desc("app_a", "invoke", 1200U);
	struct neuro_app_command_desc found = { 0 };

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register(&desc), 0,
		"register must succeed");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "invoke", &found), 0,
		"find must succeed");
	zassert_true(found.state == NEURO_APPCMD_STATE_REGISTERED,
		"new command state must be REGISTERED");
	zassert_equal(found.timeout_ms, 1200U, "timeout must be copied");
}

ZTEST(neuro_app_command_registry,
	test_register_rejects_reserved_or_invalid_name)
{
	struct neuro_app_command_desc reserved =
		make_desc("app_a", "start", 1U);
	struct neuro_app_command_desc invalid =
		make_desc("app_a", "bad/name", 1U);

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register(&reserved), -EINVAL,
		"reserved command name must fail");
	zassert_equal(neuro_app_command_registry_register(&invalid), -EINVAL,
		"non-ascii-safe command name must fail");
}

ZTEST(neuro_app_command_registry, test_set_enabled_single_command)
{
	struct neuro_app_command_desc desc = make_desc("app_a", "invoke", 300U);
	struct neuro_app_command_desc found = { 0 };

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register(&desc), 0,
		"register must succeed");
	zassert_equal(
		neuro_app_command_registry_set_enabled("app_a", "invoke", true),
		0, "enable must succeed");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "invoke", &found), 0,
		"find after enable must succeed");
	zassert_true(found.state == NEURO_APPCMD_STATE_ENABLED,
		"command must be enabled");

	zassert_equal(neuro_app_command_registry_set_enabled(
			      "app_a", "invoke", false),
		0, "disable must succeed");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "invoke", &found), 0,
		"find after disable must succeed");
	zassert_true(found.state == NEURO_APPCMD_STATE_DISABLED,
		"command must be disabled");
}

ZTEST(neuro_app_command_registry, test_set_app_enabled_updates_all_commands)
{
	struct neuro_app_command_desc one = make_desc("app_a", "invoke", 100U);
	struct neuro_app_command_desc two = make_desc("app_a", "status", 200U);
	struct neuro_app_command_desc found = { 0 };

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register(&one), 0,
		"first register must succeed");
	zassert_equal(neuro_app_command_registry_register(&two), 0,
		"second register must succeed");

	zassert_equal(neuro_app_command_registry_set_app_enabled("app_a", true),
		0, "app enable must succeed");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "invoke", &found), 0,
		"find first must succeed");
	zassert_true(found.state == NEURO_APPCMD_STATE_ENABLED,
		"first command must be enabled");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "status", &found), 0,
		"find second must succeed");
	zassert_true(found.state == NEURO_APPCMD_STATE_ENABLED,
		"second command must be enabled");
}

ZTEST(neuro_app_command_registry, test_remove_app_deletes_commands)
{
	struct neuro_app_command_desc one = make_desc("app_a", "invoke", 100U);
	struct neuro_app_command_desc two = make_desc("app_a", "status", 200U);
	struct neuro_app_command_desc found = { 0 };

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register(&one), 0,
		"first register must succeed");
	zassert_equal(neuro_app_command_registry_register(&two), 0,
		"second register must succeed");

	zassert_equal(neuro_app_command_registry_remove_app("app_a"), 0,
		"remove must succeed");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "invoke", &found),
		-ENOENT, "removed command must not be found");
	zassert_equal(
		neuro_app_command_registry_find("app_a", "status", &found),
		-ENOENT, "all app commands must be removed");
}

ZTEST(neuro_app_command_registry, test_registry_capacity_limit)
{
	char app_id[16];
	char command_name[16];
	int i;
	struct neuro_app_command_desc overflow;

	neuro_registry_reset();

	for (i = 0; i < 16; i++) {
		struct neuro_app_command_desc desc;

		snprintk(app_id, sizeof(app_id), "app%d", i);
		snprintk(command_name, sizeof(command_name), "cmd%d", i);
		desc = make_desc(app_id, command_name, (uint32_t)(100 + i));
		zassert_equal(neuro_app_command_registry_register(&desc), 0,
			"slot %d register must succeed", i);
	}

	overflow = make_desc("overflow", "invoke", 999U);
	zassert_equal(neuro_app_command_registry_register(&overflow), -ENOSPC,
		"register beyond capacity must fail");
}

ZTEST(neuro_app_command_registry,
	test_register_descriptors_registers_multiple_commands)
{
	struct neuro_app_command_desc descs[2] = {
		make_desc("ignored", "invoke", 111U),
		make_desc("ignored", "status", 222U),
	};
	struct neuro_app_command_desc found = { 0 };

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register_descriptors(
			      "app_multi", descs, 2U),
		0, "bulk descriptor registration must succeed");

	zassert_equal(
		neuro_app_command_registry_find("app_multi", "invoke", &found),
		0, "first command must be discoverable");
	zassert_equal(found.timeout_ms, 111U,
		"first command metadata must be retained");
	zassert_equal(
		neuro_app_command_registry_find("app_multi", "status", &found),
		0, "second command must be discoverable");
	zassert_equal(found.timeout_ms, 222U,
		"second command metadata must be retained");
}

ZTEST(neuro_app_command_registry,
	test_register_descriptors_rejects_duplicate_command_names)
{
	struct neuro_app_command_desc descs[2] = {
		make_desc("ignored", "invoke", 111U),
		make_desc("ignored", "invoke", 222U),
	};
	struct neuro_app_command_desc found = { 0 };

	neuro_registry_reset();
	zassert_equal(neuro_app_command_registry_register_descriptors(
			      "app_multi", descs, 2U),
		-EEXIST, "duplicate command names must be rejected");
	zassert_equal(
		neuro_app_command_registry_find("app_multi", "invoke", &found),
		-ENOENT,
		"failed bulk registration must not leave partial entries");
}

ZTEST_SUITE(neuro_app_command_registry, NULL, NULL, NULL, NULL, NULL);
