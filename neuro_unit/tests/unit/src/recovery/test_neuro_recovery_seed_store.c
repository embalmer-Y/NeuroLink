#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_artifact_store.h"
#include "neuro_recovery_seed_store.h"
#include "neuro_update_manager.h"

struct fake_seed_file {
	bool exists;
	bool is_dir;
	uint8_t data[1024];
	size_t len;
};

struct fake_seed_fs_state {
	struct fake_seed_file parent_dir;
	struct fake_seed_file primary;
	struct fake_seed_file tmp;
	struct fake_seed_file legacy;
	const char *open_path;
	int rename_conflicts_remaining;
	int rename_calls;
};

static struct fake_seed_fs_state g_fake_fs;
static struct neuro_recovery_seed_store g_test_store;

static struct fake_seed_file *fake_file_for_path(const char *path)
{
	if (strcmp(path, "/SD:") == 0) {
		return &g_fake_fs.parent_dir;
	}

	if (strcmp(path, g_test_store.path) == 0) {
		return &g_fake_fs.primary;
	}

	if (strcmp(path, g_test_store.tmp_path) == 0) {
		return &g_fake_fs.tmp;
	}

	if (strcmp(path, g_test_store.legacy_path) == 0) {
		return &g_fake_fs.legacy;
	}

	return NULL;
}

static int fake_fs_stat(const char *path, struct fs_dirent *entry)
{
	struct fake_seed_file *file = fake_file_for_path(path);

	if (file == NULL || !file->exists) {
		return -ENOENT;
	}

	if (entry != NULL) {
		memset(entry, 0, sizeof(*entry));
		entry->type =
			file->is_dir ? FS_DIR_ENTRY_DIR : FS_DIR_ENTRY_FILE;
		entry->size = file->len;
	}

	return 0;
}

static int fake_fs_mkdir(const char *path)
{
	struct fake_seed_file *file = fake_file_for_path(path);

	if (file == NULL) {
		return -ENOENT;
	}

	file->exists = true;
	file->is_dir = true;
	file->len = 0U;
	return 0;
}

static int fake_fs_open(
	struct fs_file_t *file, const char *path, fs_mode_t flags)
{
	struct fake_seed_file *slot = fake_file_for_path(path);

	ARG_UNUSED(file);

	if (slot == NULL) {
		return -ENOENT;
	}

	if ((flags & FS_O_CREATE) != 0) {
		slot->exists = true;
		slot->is_dir = false;
	}

	if (!slot->exists) {
		return -ENOENT;
	}

	if ((flags & FS_O_TRUNC) != 0) {
		slot->len = 0U;
	}

	g_fake_fs.open_path = path;
	return 0;
}

static ssize_t fake_fs_read(struct fs_file_t *file, void *ptr, size_t size)
{
	struct fake_seed_file *slot;

	ARG_UNUSED(file);

	slot = fake_file_for_path(g_fake_fs.open_path);
	if (slot == NULL || !slot->exists) {
		return -ENOENT;
	}

	if (size < slot->len) {
		return -EIO;
	}

	memcpy(ptr, slot->data, slot->len);
	return (ssize_t)slot->len;
}

static ssize_t fake_fs_write(
	struct fs_file_t *file, const void *ptr, size_t size)
{
	struct fake_seed_file *slot;

	ARG_UNUSED(file);

	slot = fake_file_for_path(g_fake_fs.open_path);
	if (slot == NULL) {
		return -ENOENT;
	}

	if (size > sizeof(slot->data)) {
		return -ENOSPC;
	}

	memcpy(slot->data, ptr, size);
	slot->len = size;
	slot->exists = true;
	slot->is_dir = false;
	return (ssize_t)size;
}

static int fake_fs_sync(struct fs_file_t *file)
{
	ARG_UNUSED(file);
	return 0;
}

static int fake_fs_close(struct fs_file_t *file)
{
	ARG_UNUSED(file);
	g_fake_fs.open_path = NULL;
	return 0;
}

static int fake_fs_unlink(const char *path)
{
	struct fake_seed_file *slot = fake_file_for_path(path);

	if (slot == NULL || !slot->exists) {
		return -ENOENT;
	}

	memset(slot, 0, sizeof(*slot));
	return 0;
}

static int fake_fs_rename(const char *from, const char *to)
{
	struct fake_seed_file *src = fake_file_for_path(from);
	struct fake_seed_file *dst = fake_file_for_path(to);

	g_fake_fs.rename_calls++;
	if (g_fake_fs.rename_conflicts_remaining > 0 &&
		strcmp(from, g_test_store.tmp_path) == 0 &&
		strcmp(to, g_test_store.path) == 0) {
		g_fake_fs.rename_conflicts_remaining--;
		return -EEXIST;
	}

	if (src == NULL || dst == NULL || !src->exists) {
		return -ENOENT;
	}

	*dst = *src;
	memset(src, 0, sizeof(*src));
	return 0;
}

static const struct neuro_recovery_seed_store_fs_ops fake_fs_ops = {
	.stat = fake_fs_stat,
	.mkdir = fake_fs_mkdir,
	.rename = fake_fs_rename,
	.unlink = fake_fs_unlink,
	.open = fake_fs_open,
	.read = fake_fs_read,
	.write = fake_fs_write,
	.sync = fake_fs_sync,
	.close = fake_fs_close,
};

int fs_stat(const char *path, struct fs_dirent *entry)
{
	return fake_fs_stat(path, entry);
}

int fs_mkdir(const char *path) { return fake_fs_mkdir(path); }

int fs_rename(const char *from, const char *to)
{
	return fake_fs_rename(from, to);
}

int fs_unlink(const char *path) { return fake_fs_unlink(path); }

int fs_open(struct fs_file_t *file, const char *path, fs_mode_t flags)
{
	return fake_fs_open(file, path, flags);
}

ssize_t fs_read(struct fs_file_t *file, void *ptr, size_t size)
{
	return fake_fs_read(file, ptr, size);
}

ssize_t fs_write(struct fs_file_t *file, const void *ptr, size_t size)
{
	return fake_fs_write(file, ptr, size);
}

int fs_sync(struct fs_file_t *file) { return fake_fs_sync(file); }

int fs_close(struct fs_file_t *file) { return fake_fs_close(file); }

static void reset_fake_fs(void *fixture)
{
	ARG_UNUSED(fixture);
	memset(&g_fake_fs, 0, sizeof(g_fake_fs));
	g_fake_fs.parent_dir.exists = true;
	g_fake_fs.parent_dir.is_dir = true;
	neuro_recovery_seed_store_init(&g_test_store, NULL);
	neuro_recovery_seed_store_reset_fs_ops();
}

ZTEST(neuro_recovery_seed_store, test_encode_decode_roundtrip_success)
{
	struct neuro_recovery_seed_snapshot snapshot;
	struct neuro_recovery_seed_snapshot decoded;
	uint8_t buf[1024];
	size_t encoded_len = 0U;
	int ret;

	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");
	snapshot.entries[0].update_state = NEURO_UPDATE_STATE_VERIFIED;
	snprintk(snapshot.entries[0].artifact_path,
		sizeof(snapshot.entries[0].artifact_path), "%s",
		"/SD:/apps/demo.llext");
	snapshot.entries[0].artifact_state = NEURO_ARTIFACT_STAGED;

	ret = neuro_recovery_seed_encode(
		&snapshot, buf, sizeof(buf), &encoded_len);
	zassert_equal(ret, 0, "encode should succeed");
	zassert_true(encoded_len > 0U, "encoded length should be positive");

	ret = neuro_recovery_seed_decode(buf, encoded_len, &decoded);
	zassert_equal(ret, 0, "decode should succeed");
	zassert_equal(decoded.entry_count, 1U, "entry count should roundtrip");
	zassert_true(strcmp(decoded.entries[0].app_id, "demo") == 0,
		"app id should roundtrip");
	zassert_equal(decoded.entries[0].update_state,
		NEURO_UPDATE_STATE_VERIFIED, "update state should roundtrip");
	zassert_equal(decoded.entries[0].artifact_state, NEURO_ARTIFACT_STAGED,
		"artifact state should roundtrip");
}

ZTEST(neuro_recovery_seed_store, test_decode_rejects_crc_mismatch)
{
	struct neuro_recovery_seed_snapshot snapshot;
	uint8_t buf[1024];
	size_t encoded_len = 0U;
	int ret;

	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");

	ret = neuro_recovery_seed_encode(
		&snapshot, buf, sizeof(buf), &encoded_len);
	zassert_equal(ret, 0, "encode should succeed");

	buf[encoded_len - 1U] ^= 0x5AU;
	ret = neuro_recovery_seed_decode(buf, encoded_len, &snapshot);
	zassert_equal(ret, -EBADMSG, "crc mismatch must be rejected");
}

ZTEST(neuro_recovery_seed_store, test_decode_rejects_version_mismatch)
{
	struct neuro_recovery_seed_snapshot snapshot;
	uint8_t buf[1024];
	size_t encoded_len = 0U;
	uint32_t unsupported_version;
	int ret;

	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");

	ret = neuro_recovery_seed_encode(
		&snapshot, buf, sizeof(buf), &encoded_len);
	zassert_equal(ret, 0, "encode should succeed");

	unsupported_version = NEURO_RECOVERY_SEED_MAX_SUPPORTED_VERSION + 1U;
	memcpy(&buf[4], &unsupported_version, sizeof(unsupported_version));
	ret = neuro_recovery_seed_decode(buf, encoded_len, &snapshot);
	zassert_equal(ret, -ENOTSUP, "unsupported version must be rejected");
}

ZTEST(neuro_recovery_seed_store, test_decode_rejects_older_unsupported_version)
{
	struct neuro_recovery_seed_snapshot snapshot;
	uint8_t buf[1024];
	size_t encoded_len = 0U;
	uint32_t unsupported_version;
	int ret;

	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");

	ret = neuro_recovery_seed_encode(
		&snapshot, buf, sizeof(buf), &encoded_len);
	zassert_equal(ret, 0, "encode should succeed");

	unsupported_version = NEURO_RECOVERY_SEED_MIN_SUPPORTED_VERSION - 1U;
	memcpy(&buf[4], &unsupported_version, sizeof(unsupported_version));
	ret = neuro_recovery_seed_decode(buf, encoded_len, &snapshot);
	zassert_equal(
		ret, -ENOTSUP, "older unsupported version must be rejected");
}

ZTEST(neuro_recovery_seed_store, test_decode_rejects_truncated_payload)
{
	struct neuro_recovery_seed_snapshot snapshot;
	uint8_t buf[1024];
	size_t encoded_len = 0U;
	int ret;

	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");

	ret = neuro_recovery_seed_encode(
		&snapshot, buf, sizeof(buf), &encoded_len);
	zassert_equal(ret, 0, "encode should succeed");
	zassert_true(
		encoded_len > 1U, "encoded payload should be large enough");

	ret = neuro_recovery_seed_decode(buf, encoded_len - 1U, &snapshot);
	zassert_equal(ret, -EBADMSG, "truncated payload must be rejected");
}

ZTEST(neuro_recovery_seed_store, test_build_and_apply_snapshot_roundtrip)
{
	struct neuro_update_manager update_manager;
	struct neuro_artifact_store artifact_store;
	struct neuro_recovery_seed_snapshot snapshot;
	struct neuro_update_manager restored_update_manager;
	struct neuro_artifact_store restored_artifact_store;
	const struct neuro_artifact_meta *meta;
	int ret;

	neuro_update_manager_init(&update_manager);
	neuro_artifact_store_init(&artifact_store);

	ret = neuro_update_manager_prepare_begin(&update_manager, "demo");
	zassert_equal(ret, 0, "prepare begin should succeed");
	ret = neuro_update_manager_prepare_complete(&update_manager, "demo");
	zassert_equal(ret, 0, "prepare complete should succeed");
	ret = neuro_update_manager_verify_begin(&update_manager, "demo");
	zassert_equal(ret, 0, "verify begin should succeed");
	ret = neuro_update_manager_verify_complete(&update_manager, "demo");
	zassert_equal(ret, 0, "verify complete should succeed");

	ret = neuro_artifact_store_stage(&artifact_store, "demo", "zenoh",
		"neuro/artifact/unit-01/demo", "/SD:/apps/demo.llext", 1024,
		256, 4);
	zassert_equal(ret, 0, "artifact stage should succeed");
	ret = neuro_artifact_store_set_state(
		&artifact_store, "demo", NEURO_ARTIFACT_VERIFIED);
	zassert_equal(ret, 0, "artifact state update should succeed");

	ret = neuro_recovery_seed_build_snapshot(
		&update_manager, &artifact_store, &snapshot);
	zassert_equal(ret, 0, "snapshot build should succeed");
	zassert_equal(snapshot.entry_count, 1U, "single app snapshot expected");

	ret = neuro_recovery_seed_apply_snapshot(
		&snapshot, &restored_update_manager, &restored_artifact_store);
	zassert_equal(ret, 0, "snapshot apply should succeed");

	zassert_equal(neuro_update_manager_state_for(
			      &restored_update_manager, "demo"),
		NEURO_UPDATE_STATE_VERIFIED,
		"restored update state should match source");

	meta = neuro_artifact_store_get(&restored_artifact_store, "demo");
	zassert_not_null(meta, "restored artifact metadata should exist");
	zassert_equal(meta->state, NEURO_ARTIFACT_VERIFIED,
		"restored artifact state should match source");
	zassert_true(strcmp(meta->path, "/SD:/apps/demo.llext") == 0,
		"restored path should match source");
}

ZTEST(neuro_recovery_seed_store,
	test_store_load_promotes_valid_tmp_when_primary_missing)
{
	struct neuro_recovery_seed_snapshot snapshot;
	struct neuro_recovery_seed_snapshot loaded;
	size_t encoded_len = 0U;
	int ret;

	neuro_recovery_seed_store_set_fs_ops(&fake_fs_ops);
	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");
	snapshot.entries[0].update_state = NEURO_UPDATE_STATE_PREPARED;

	ret = neuro_recovery_seed_encode(&snapshot, g_fake_fs.tmp.data,
		sizeof(g_fake_fs.tmp.data), &encoded_len);
	zassert_equal(ret, 0, "encode should succeed");
	g_fake_fs.tmp.exists = true;
	g_fake_fs.tmp.len = encoded_len;

	ret = neuro_recovery_seed_store_load(&g_test_store, &loaded);
	zassert_equal(ret, 0, "load should promote valid tmp seed");
	zassert_true(g_fake_fs.primary.exists,
		"primary seed should exist after tmp recovery");
	zassert_true(!g_fake_fs.tmp.exists,
		"tmp seed should be consumed after promotion");
	zassert_equal(loaded.entry_count, 1U,
		"loaded snapshot should preserve entry count");
	zassert_true(strcmp(loaded.entries[0].app_id, "demo") == 0,
		"loaded app id should match tmp snapshot");
}

ZTEST(neuro_recovery_seed_store,
	test_store_save_retries_rename_after_existing_target_removed)
{
	struct neuro_recovery_seed_snapshot snapshot;
	struct neuro_recovery_seed_snapshot loaded;
	int ret;

	neuro_recovery_seed_store_set_fs_ops(&fake_fs_ops);
	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.entry_count = 1U;
	snapshot.entries[0].used = true;
	snprintk(snapshot.entries[0].app_id, sizeof(snapshot.entries[0].app_id),
		"%s", "demo");
	snapshot.entries[0].artifact_state = NEURO_ARTIFACT_STAGED;
	g_fake_fs.primary.exists = true;
	g_fake_fs.primary.is_dir = false;
	g_fake_fs.primary.len = 3U;
	g_fake_fs.primary.data[0] = 'o';
	g_fake_fs.primary.data[1] = 'l';
	g_fake_fs.primary.data[2] = 'd';
	g_fake_fs.rename_conflicts_remaining = 1;

	ret = neuro_recovery_seed_store_save(&g_test_store, &snapshot);
	zassert_equal(ret, 0,
		"save should recover from existing-target rename conflict");
	zassert_equal(g_fake_fs.rename_calls, 2,
		"rename should be retried after removing old target");
	zassert_true(g_fake_fs.primary.exists,
		"primary seed should remain present after save");
	zassert_true(!g_fake_fs.tmp.exists,
		"tmp seed should not remain after successful save");

	ret = neuro_recovery_seed_store_load(&g_test_store, &loaded);
	zassert_equal(ret, 0,
		"saved seed should remain readable after rename fallback");
	zassert_true(strcmp(loaded.entries[0].app_id, "demo") == 0,
		"loaded app id should match saved snapshot");
	zassert_equal(loaded.entries[0].artifact_state, NEURO_ARTIFACT_STAGED,
		"loaded artifact state should match saved snapshot");
}

ZTEST_SUITE(neuro_recovery_seed_store, NULL, NULL, reset_fake_fs, NULL, NULL);
