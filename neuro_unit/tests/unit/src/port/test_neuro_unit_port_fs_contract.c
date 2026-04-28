#include <zephyr/fs/fs.h>
#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_unit_port.h"

static int g_mount_calls;
static int g_alloc_external_calls;
static int g_free_external_calls;
static int g_unmount_calls;
static int g_stat_calls;
static uint8_t g_external_buffer[32];

static int mock_mount(void)
{
	g_mount_calls++;
	return 0;
}

static int mock_unmount(void)
{
	g_unmount_calls++;
	return 0;
}

static int mock_stat(const char *path, struct fs_dirent *entry)
{
	zassert_not_null(path, "stat path must be forwarded");
	zassert_not_null(entry, "stat entry must be forwarded");
	g_stat_calls++;
	memset(entry, 0, sizeof(*entry));
	entry->type = FS_DIR_ENTRY_FILE;
	entry->size = 42U;
	return 0;
}

static void *mock_alloc_external(size_t size, size_t align)
{
	g_alloc_external_calls++;
	zassert_equal(size, 16U, "external allocation size mismatch");
	zassert_equal(align, 32U, "external allocation align mismatch");
	return g_external_buffer;
}

static void mock_free_external(void *ptr)
{
	g_free_external_calls++;
	zassert_equal(ptr, g_external_buffer, "external free pointer mismatch");
}

static void port_fs_contract_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	g_mount_calls = 0;
	g_alloc_external_calls = 0;
	g_free_external_calls = 0;
	g_unmount_calls = 0;
	g_stat_calls = 0;
	(void)neuro_unit_port_set_fs_ops(NULL);
	(void)neuro_unit_port_set_memory_ops(NULL);
	(void)neuro_unit_port_set_paths("/apps", "/recovery.seed");
}

ZTEST(neuro_unit_port_fs_contract, test_null_fs_ops_reset_to_empty_table)
{
	const struct neuro_unit_port_fs_ops fs_ops = {
		.mount = mock_mount,
	};
	const struct neuro_unit_port_fs_ops *active_ops;

	zassert_equal(neuro_unit_port_set_fs_ops(&fs_ops), 0,
		"set fs ops should succeed");
	zassert_equal(neuro_unit_port_get_fs_ops(), &fs_ops,
		"active fs ops should be caller-provided table");

	zassert_equal(neuro_unit_port_set_fs_ops(NULL), 0,
		"reset fs ops should succeed");
	active_ops = neuro_unit_port_get_fs_ops();
	zassert_not_null(active_ops, "reset fs ops must leave non-null table");
	zassert_is_null(
		active_ops->mount, "empty fs ops must not expose mount");
	zassert_is_null(active_ops->stat, "empty fs ops must not expose stat");
}

ZTEST(neuro_unit_port_fs_contract, test_fs_ops_forward_registered_callbacks)
{
	const struct neuro_unit_port_fs_ops fs_ops = {
		.mount = mock_mount,
		.unmount = mock_unmount,
		.stat = mock_stat,
	};
	const struct neuro_unit_port_fs_ops *active_ops;
	struct fs_dirent entry = { 0 };

	zassert_equal(neuro_unit_port_set_fs_ops(&fs_ops), 0,
		"set fs ops should succeed");
	active_ops = neuro_unit_port_get_fs_ops();
	zassert_equal(active_ops, &fs_ops,
		"active fs ops should be caller-provided table");

	zassert_equal(active_ops->mount(), 0, "mount callback should run");
	zassert_equal(active_ops->unmount(), 0, "unmount callback should run");
	zassert_equal(active_ops->stat("/apps/main.llext", &entry), 0,
		"stat callback should run");
	zassert_equal(g_mount_calls, 1, "mount callback count mismatch");
	zassert_equal(g_unmount_calls, 1, "unmount callback count mismatch");
	zassert_equal(g_stat_calls, 1, "stat callback count mismatch");
	zassert_equal(entry.type, FS_DIR_ENTRY_FILE,
		"stat callback should fill file type");
	zassert_equal(entry.size, 42U, "stat callback should fill size");
}

ZTEST(neuro_unit_port_fs_contract, test_paths_reject_invalid_values)
{
	zassert_equal(neuro_unit_port_set_paths("/custom/apps", "/custom.seed"),
		0, "valid paths should be accepted");
	zassert_equal(strcmp(neuro_unit_port_apps_dir(), "/custom/apps"), 0,
		"apps path mismatch");
	zassert_equal(strcmp(neuro_unit_port_seed_path(), "/custom.seed"), 0,
		"seed path mismatch");

	zassert_equal(neuro_unit_port_set_paths(NULL, "/next.seed"), -EINVAL,
		"null apps path should be rejected");
	zassert_equal(neuro_unit_port_set_paths("", "/next.seed"), -EINVAL,
		"empty apps path should be rejected");
	zassert_equal(neuro_unit_port_set_paths("/next/apps", NULL), -EINVAL,
		"null seed path should be rejected");
	zassert_equal(neuro_unit_port_set_paths("/next/apps", ""), -EINVAL,
		"empty seed path should be rejected");
	zassert_equal(strcmp(neuro_unit_port_apps_dir(), "/custom/apps"), 0,
		"invalid paths must not change apps path");
	zassert_equal(strcmp(neuro_unit_port_seed_path(), "/custom.seed"), 0,
		"invalid paths must not change seed path");
}

ZTEST(neuro_unit_port_fs_contract, test_null_memory_ops_reset_to_empty_table)
{
	const struct neuro_unit_port_memory_ops memory_ops = {
		.provider = "mock-external",
		.alloc_external = mock_alloc_external,
	};
	const struct neuro_unit_port_memory_ops *active_ops;

	zassert_equal(neuro_unit_port_set_memory_ops(&memory_ops), 0,
		"set memory ops should succeed");
	zassert_equal(neuro_unit_port_get_memory_ops(), &memory_ops,
		"active memory ops should be caller-provided table");

	zassert_equal(neuro_unit_port_set_memory_ops(NULL), 0,
		"reset memory ops should succeed");
	active_ops = neuro_unit_port_get_memory_ops();
	zassert_not_null(
		active_ops, "reset memory ops must leave non-null table");
	zassert_is_null(active_ops->provider,
		"empty memory ops must not expose provider label");
	zassert_is_null(active_ops->alloc_external,
		"empty memory ops must not expose external allocator");
	zassert_is_null(active_ops->free_external,
		"empty memory ops must not expose external free hook");
}

ZTEST(neuro_unit_port_fs_contract, test_memory_ops_forward_external_callbacks)
{
	const struct neuro_unit_port_memory_ops memory_ops = {
		.provider = "mock-external",
		.alloc_external = mock_alloc_external,
		.free_external = mock_free_external,
	};
	const struct neuro_unit_port_memory_ops *active_ops;
	void *ptr;

	zassert_equal(neuro_unit_port_set_memory_ops(&memory_ops), 0,
		"set memory ops should succeed");
	active_ops = neuro_unit_port_get_memory_ops();
	zassert_equal(active_ops, &memory_ops,
		"active memory ops should be caller-provided table");
	zassert_equal(strcmp(active_ops->provider, "mock-external"), 0,
		"provider label should be forwarded");

	ptr = active_ops->alloc_external(16U, 32U);
	zassert_equal(ptr, g_external_buffer,
		"external allocation result should be forwarded");
	active_ops->free_external(ptr);
	zassert_equal(g_alloc_external_calls, 1,
		"external allocation callback count mismatch");
	zassert_equal(g_free_external_calls, 1,
		"external free callback count mismatch");
}

ZTEST_SUITE(neuro_unit_port_fs_contract, NULL, NULL, port_fs_contract_reset,
	NULL, NULL);
