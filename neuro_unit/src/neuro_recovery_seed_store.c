#include "neuro_recovery_seed_store.h"

#include <zephyr/fs/fs.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>

struct neuro_seed_file_header {
	uint32_t magic;
	uint32_t version;
	uint32_t entry_count;
	uint32_t payload_crc;
};

/* Fixed-layout on-storage entry used by the current v1 recovery snapshot. */
struct neuro_seed_file_entry {
	uint8_t used;
	uint8_t reserved0[3];
	char app_id[32];
	uint32_t update_state;
	char update_last_error[64];
	char rollback_reason[64];
	char stable_ref[96];
	uint32_t artifact_state;
	char artifact_transport[16];
	char artifact_key[128];
	char artifact_path[128];
	uint32_t size_bytes;
	uint32_t chunk_size;
	uint32_t chunks_received;
	uint8_t reserved1[16];
};

static const struct neuro_recovery_seed_store_fs_ops default_fs_ops = {
	.stat = fs_stat,
	.mkdir = fs_mkdir,
	.rename = fs_rename,
	.unlink = fs_unlink,
	.open = fs_open,
	.read = fs_read,
	.write = fs_write,
	.sync = fs_sync,
	.close = fs_close,
};

static const struct neuro_recovery_seed_store_fs_ops *active_fs_ops =
	&default_fs_ops;

static const struct neuro_recovery_seed_store_fs_ops *seed_fs_ops(void)
{
	return active_fs_ops != NULL ? active_fs_ops : &default_fs_ops;
}

static void copy_bounded(char *dst, size_t dst_len, const char *src)
{
	if (dst == NULL || dst_len == 0U) {
		return;
	}

	if (src == NULL) {
		dst[0] = '\0';
		return;
	}

	snprintf(dst, dst_len, "%s", src);
}

static uint32_t neuro_crc32(const uint8_t *data, size_t len)
{
	uint32_t crc = 0xFFFFFFFFU;
	size_t i;
	int bit;

	for (i = 0; i < len; i++) {
		crc ^= data[i];
		for (bit = 0; bit < 8; bit++) {
			if (crc & 1U) {
				crc = (crc >> 1) ^ 0xEDB88320U;
			} else {
				crc >>= 1;
			}
		}
	}

	return ~crc;
}

static bool neuro_recovery_seed_version_supported(uint32_t version)
{
	return version >= NEURO_RECOVERY_SEED_MIN_SUPPORTED_VERSION &&
	       version <= NEURO_RECOVERY_SEED_MAX_SUPPORTED_VERSION;
}

static int neuro_recovery_seed_decode_v1(
	const struct neuro_seed_file_header *header, const uint8_t *buf,
	size_t buf_len, struct neuro_recovery_seed_snapshot *snapshot)
{
	const struct neuro_seed_file_entry *payload;
	size_t payload_size;
	size_t expected_size;
	size_t i;
	uint32_t crc;

	if (header->entry_count > NEURO_RECOVERY_SEED_MAX_ENTRIES) {
		return -EOVERFLOW;
	}

	payload_size =
		header->entry_count * sizeof(struct neuro_seed_file_entry);
	expected_size = sizeof(*header) + payload_size;
	if (buf_len < expected_size) {
		return -EBADMSG;
	}

	payload = (const struct neuro_seed_file_entry *)(buf + sizeof(*header));
	crc = neuro_crc32((const uint8_t *)payload, payload_size);
	if (crc != header->payload_crc) {
		return -EBADMSG;
	}

	/*
	 * Decode into the in-memory neutral snapshot shape so newer versions
	 * can add their own versioned handlers without changing manager-facing
	 * code.
	 */
	memset(snapshot, 0, sizeof(*snapshot));
	snapshot->entry_count = header->entry_count;
	for (i = 0; i < snapshot->entry_count; i++) {
		snapshot->entries[i].used = payload[i].used != 0U;
		copy_bounded(snapshot->entries[i].app_id,
			sizeof(snapshot->entries[i].app_id), payload[i].app_id);
		snapshot->entries[i].update_state =
			(enum neuro_update_state)payload[i].update_state;
		copy_bounded(snapshot->entries[i].update_last_error,
			sizeof(snapshot->entries[i].update_last_error),
			payload[i].update_last_error);
		copy_bounded(snapshot->entries[i].rollback_reason,
			sizeof(snapshot->entries[i].rollback_reason),
			payload[i].rollback_reason);
		copy_bounded(snapshot->entries[i].stable_ref,
			sizeof(snapshot->entries[i].stable_ref),
			payload[i].stable_ref);
		snapshot->entries[i].artifact_state =
			(enum neuro_artifact_state)payload[i].artifact_state;
		copy_bounded(snapshot->entries[i].artifact_transport,
			sizeof(snapshot->entries[i].artifact_transport),
			payload[i].artifact_transport);
		copy_bounded(snapshot->entries[i].artifact_key,
			sizeof(snapshot->entries[i].artifact_key),
			payload[i].artifact_key);
		copy_bounded(snapshot->entries[i].artifact_path,
			sizeof(snapshot->entries[i].artifact_path),
			payload[i].artifact_path);
		snapshot->entries[i].size_bytes = payload[i].size_bytes;
		snapshot->entries[i].chunk_size = payload[i].chunk_size;
		snapshot->entries[i].chunks_received =
			payload[i].chunks_received;
	}

	return 0;
}

static int split_parent_dir(const char *path, char *parent, size_t parent_len)
{
	const char *slash;
	size_t dir_len;

	if (path == NULL || parent == NULL || parent_len == 0U) {
		return -EINVAL;
	}

	slash = strrchr(path, '/');
	if (slash == NULL) {
		return -EINVAL;
	}

	dir_len = (size_t)(slash - path);
	if (dir_len == 0U || dir_len >= parent_len) {
		return -EINVAL;
	}

	memcpy(parent, path, dir_len);
	parent[dir_len] = '\0';
	return 0;
}

static int ensure_parent_dir(const char *path)
{
	const struct neuro_recovery_seed_store_fs_ops *ops = seed_fs_ops();
	char parent[128];
	struct fs_dirent ent;
	int ret;

	ret = split_parent_dir(path, parent, sizeof(parent));
	if (ret < 0) {
		return ret;
	}

	memset(&ent, 0, sizeof(ent));
	ret = ops->stat(parent, &ent);
	if (ret == 0) {
		return ent.type == FS_DIR_ENTRY_DIR ? 0 : -ENOTDIR;
	}

	if (ret != -ENOENT) {
		return ret;
	}

	ret = ops->mkdir(parent);
	if (ret < 0 && ret != -EEXIST) {
		return ret;
	}

	return 0;
}

static int read_snapshot_file(
	const char *path, struct neuro_recovery_seed_snapshot *snapshot)
{
	const struct neuro_recovery_seed_store_fs_ops *ops = seed_fs_ops();
	struct fs_file_t file;
	struct fs_dirent ent;
	uint8_t buf[sizeof(struct neuro_seed_file_header) +
		    NEURO_RECOVERY_SEED_MAX_ENTRIES *
			    sizeof(struct neuro_seed_file_entry)];
	ssize_t read_bytes;
	int ret;

	if (path == NULL || snapshot == NULL || path[0] == '\0') {
		return -EINVAL;
	}

	memset(&ent, 0, sizeof(ent));
	ret = ops->stat(path, &ent);
	if (ret < 0) {
		return ret;
	}

	if (ent.type != FS_DIR_ENTRY_FILE || ent.size == 0U) {
		return -EBADMSG;
	}

	if (ent.size > sizeof(buf)) {
		return -EFBIG;
	}

	fs_file_t_init(&file);
	ret = ops->open(&file, path, FS_O_READ);
	if (ret < 0) {
		return ret;
	}

	read_bytes = ops->read(&file, buf, ent.size);
	(void)ops->close(&file);
	if (read_bytes < 0 || (size_t)read_bytes != ent.size) {
		return -EIO;
	}

	return neuro_recovery_seed_decode(buf, (size_t)ent.size, snapshot);
}

static int migrate_legacy_seed_if_needed(
	const struct neuro_recovery_seed_store *store)
{
	const struct neuro_recovery_seed_store_fs_ops *ops = seed_fs_ops();
	struct fs_dirent ent;
	int ret;

	if (store == NULL || store->legacy_path[0] == '\0') {
		return -EINVAL;
	}

	memset(&ent, 0, sizeof(ent));
	ret = ops->stat(store->path, &ent);
	if (ret == 0) {
		return 0;
	}

	if (ret != -ENOENT) {
		return ret;
	}

	memset(&ent, 0, sizeof(ent));
	ret = ops->stat(store->legacy_path, &ent);
	if (ret < 0) {
		return ret == -ENOENT ? 0 : ret;
	}

	if (ent.type != FS_DIR_ENTRY_FILE || ent.size == 0U) {
		return 0;
	}

	ret = ensure_parent_dir(store->path);
	if (ret < 0) {
		return ret;
	}

	ret = ops->rename(store->legacy_path, store->path);
	if (ret < 0) {
		return ret;
	}

	return 0;
}

static int recover_tmp_seed_if_needed(
	const struct neuro_recovery_seed_store *store)
{
	const struct neuro_recovery_seed_store_fs_ops *ops = seed_fs_ops();
	struct fs_dirent ent;
	struct neuro_recovery_seed_snapshot snapshot;
	int ret;

	memset(&ent, 0, sizeof(ent));
	ret = ops->stat(store->path, &ent);
	if (ret == 0) {
		return 0;
	}

	if (ret != -ENOENT) {
		return ret;
	}

	memset(&ent, 0, sizeof(ent));
	ret = ops->stat(store->tmp_path, &ent);
	if (ret < 0) {
		return ret == -ENOENT ? 0 : ret;
	}

	/*
	 * A surviving .tmp file means the previous save likely finished writing
	 * but not the final rename. Validate it first, then promote it into
	 * place.
	 */
	ret = read_snapshot_file(store->tmp_path, &snapshot);
	if (ret < 0) {
		(void)ops->unlink(store->tmp_path);
		return ret;
	}

	ret = ops->rename(store->tmp_path, store->path);
	if (ret < 0) {
		return ret;
	}

	return 0;
}

static struct neuro_recovery_seed_entry *find_seed_entry(
	struct neuro_recovery_seed_snapshot *snapshot, const char *app_id)
{
	size_t i;

	for (i = 0; i < snapshot->entry_count; i++) {
		if (snapshot->entries[i].used &&
			strcmp(snapshot->entries[i].app_id, app_id) == 0) {
			return &snapshot->entries[i];
		}
	}

	return NULL;
}

static struct neuro_recovery_seed_entry *find_or_add_seed_entry(
	struct neuro_recovery_seed_snapshot *snapshot, const char *app_id)
{
	struct neuro_recovery_seed_entry *entry;

	entry = find_seed_entry(snapshot, app_id);
	if (entry != NULL) {
		return entry;
	}

	if (snapshot->entry_count >= NEURO_RECOVERY_SEED_MAX_ENTRIES) {
		return NULL;
	}

	entry = &snapshot->entries[snapshot->entry_count++];
	memset(entry, 0, sizeof(*entry));
	entry->used = true;
	copy_bounded(entry->app_id, sizeof(entry->app_id), app_id);
	entry->update_state = NEURO_UPDATE_STATE_NONE;
	entry->artifact_state = NEURO_ARTIFACT_NONE;
	return entry;
}

void neuro_recovery_seed_store_set_fs_ops(
	const struct neuro_recovery_seed_store_fs_ops *ops)
{
	active_fs_ops = ops != NULL ? ops : &default_fs_ops;
}

void neuro_recovery_seed_store_reset_fs_ops(void)
{
	active_fs_ops = &default_fs_ops;
}

void neuro_recovery_seed_store_init(
	struct neuro_recovery_seed_store *store, const char *path)
{
	size_t path_len;

	if (store == NULL) {
		return;
	}

	memset(store, 0, sizeof(*store));
	copy_bounded(store->path, sizeof(store->path),
		path != NULL ? path : NEURO_RECOVERY_SEED_PATH_DEFAULT);
	copy_bounded(store->tmp_path, sizeof(store->tmp_path), store->path);
	copy_bounded(store->bak_path, sizeof(store->bak_path), store->path);
	copy_bounded(store->legacy_path, sizeof(store->legacy_path),
		NEURO_RECOVERY_SEED_PATH_LEGACY);
	path_len = strnlen(store->path, sizeof(store->path));
	if ((path_len + 4U) < sizeof(store->tmp_path)) {
		memcpy(&store->tmp_path[path_len], ".tmp", 5U);
	}
	if ((path_len + 4U) < sizeof(store->bak_path)) {
		memcpy(&store->bak_path[path_len], ".bak", 5U);
	}
}

int neuro_recovery_seed_build_snapshot(
	const struct neuro_update_manager *update_manager,
	const struct neuro_artifact_store *artifact_store,
	struct neuro_recovery_seed_snapshot *snapshot)
{
	struct neuro_update_entry
		update_entries[NEURO_UPDATE_MANAGER_MAX_ENTRIES];
	struct neuro_artifact_meta
		artifact_entries[NEURO_ARTIFACT_STORE_MAX_ENTRIES];
	size_t update_count;
	size_t artifact_count;
	size_t i;

	if (update_manager == NULL || artifact_store == NULL ||
		snapshot == NULL) {
		return -EINVAL;
	}

	/*
	 * Merge update and artifact manager state into one boot-recoverable
	 * image.
	 */
	memset(snapshot, 0, sizeof(*snapshot));

	update_count = neuro_update_manager_export_entries(
		update_manager, update_entries, ARRAY_SIZE(update_entries));
	for (i = 0; i < update_count; i++) {
		struct neuro_recovery_seed_entry *entry;

		entry = find_or_add_seed_entry(
			snapshot, update_entries[i].app_id);
		if (entry == NULL) {
			return -ENOSPC;
		}

		entry->update_state = update_entries[i].state;
		copy_bounded(entry->update_last_error,
			sizeof(entry->update_last_error),
			update_entries[i].last_error);
		copy_bounded(entry->rollback_reason,
			sizeof(entry->rollback_reason),
			update_entries[i].rollback_reason);
		copy_bounded(entry->stable_ref, sizeof(entry->stable_ref),
			update_entries[i].stable_ref);
	}

	artifact_count = neuro_artifact_store_export_entries(
		artifact_store, artifact_entries, ARRAY_SIZE(artifact_entries));
	for (i = 0; i < artifact_count; i++) {
		struct neuro_recovery_seed_entry *entry;

		entry = find_or_add_seed_entry(
			snapshot, artifact_entries[i].app_id);
		if (entry == NULL) {
			return -ENOSPC;
		}

		entry->artifact_state = artifact_entries[i].state;
		copy_bounded(entry->artifact_transport,
			sizeof(entry->artifact_transport),
			artifact_entries[i].transport);
		copy_bounded(entry->artifact_key, sizeof(entry->artifact_key),
			artifact_entries[i].artifact_key);
		copy_bounded(entry->artifact_path, sizeof(entry->artifact_path),
			artifact_entries[i].path);
		entry->size_bytes = (uint32_t)artifact_entries[i].size_bytes;
		entry->chunk_size = (uint32_t)artifact_entries[i].chunk_size;
		entry->chunks_received =
			(uint32_t)artifact_entries[i].chunks_received;
	}

	return 0;
}

int neuro_recovery_seed_apply_snapshot(
	const struct neuro_recovery_seed_snapshot *snapshot,
	struct neuro_update_manager *update_manager,
	struct neuro_artifact_store *artifact_store)
{
	struct neuro_update_entry
		update_entries[NEURO_UPDATE_MANAGER_MAX_ENTRIES];
	struct neuro_artifact_meta
		artifact_entries[NEURO_ARTIFACT_STORE_MAX_ENTRIES];
	size_t update_count = 0U;
	size_t artifact_count = 0U;
	size_t i;
	int ret;

	if (snapshot == NULL || update_manager == NULL ||
		artifact_store == NULL) {
		return -EINVAL;
	}

	if (snapshot->entry_count > NEURO_RECOVERY_SEED_MAX_ENTRIES) {
		return -EOVERFLOW;
	}

	/*
	 * Split the persisted composite snapshot back into manager-specific
	 * arrays.
	 */
	for (i = 0; i < snapshot->entry_count; i++) {
		const struct neuro_recovery_seed_entry *entry =
			&snapshot->entries[i];

		if (!entry->used || entry->app_id[0] == '\0') {
			continue;
		}

		if (update_count < ARRAY_SIZE(update_entries) &&
			(entry->update_state != NEURO_UPDATE_STATE_NONE ||
				entry->update_last_error[0] != '\0' ||
				entry->rollback_reason[0] != '\0' ||
				entry->stable_ref[0] != '\0')) {
			memset(&update_entries[update_count], 0,
				sizeof(update_entries[update_count]));
			update_entries[update_count].used = true;
			copy_bounded(update_entries[update_count].app_id,
				sizeof(update_entries[update_count].app_id),
				entry->app_id);
			update_entries[update_count].state =
				entry->update_state;
			copy_bounded(update_entries[update_count].last_error,
				sizeof(update_entries[update_count].last_error),
				entry->update_last_error);
			copy_bounded(
				update_entries[update_count].rollback_reason,
				sizeof(update_entries[update_count]
						.rollback_reason),
				entry->rollback_reason);
			copy_bounded(update_entries[update_count].stable_ref,
				sizeof(update_entries[update_count].stable_ref),
				entry->stable_ref);
			update_count++;
		}

		if (artifact_count < ARRAY_SIZE(artifact_entries) &&
			(entry->artifact_state != NEURO_ARTIFACT_NONE ||
				entry->artifact_path[0] != '\0' ||
				entry->artifact_key[0] != '\0')) {
			memset(&artifact_entries[artifact_count], 0,
				sizeof(artifact_entries[artifact_count]));
			artifact_entries[artifact_count].used = true;
			copy_bounded(artifact_entries[artifact_count].app_id,
				sizeof(artifact_entries[artifact_count].app_id),
				entry->app_id);
			copy_bounded(artifact_entries[artifact_count].transport,
				sizeof(artifact_entries[artifact_count]
						.transport),
				entry->artifact_transport);
			copy_bounded(
				artifact_entries[artifact_count].artifact_key,
				sizeof(artifact_entries[artifact_count]
						.artifact_key),
				entry->artifact_key);
			copy_bounded(artifact_entries[artifact_count].path,
				sizeof(artifact_entries[artifact_count].path),
				entry->artifact_path);
			artifact_entries[artifact_count].size_bytes =
				entry->size_bytes;
			artifact_entries[artifact_count].chunk_size =
				entry->chunk_size;
			artifact_entries[artifact_count].chunks_received =
				entry->chunks_received;
			artifact_entries[artifact_count].state =
				entry->artifact_state;
			artifact_count++;
		}
	}

	ret = neuro_update_manager_import_entries(
		update_manager, update_entries, update_count);
	if (ret) {
		return ret;
	}

	ret = neuro_artifact_store_import_entries(
		artifact_store, artifact_entries, artifact_count);
	if (ret) {
		return ret;
	}

	return 0;
}

int neuro_recovery_seed_encode(
	const struct neuro_recovery_seed_snapshot *snapshot, uint8_t *buf,
	size_t buf_len, size_t *out_len)
{
	struct neuro_seed_file_header header;
	struct neuro_seed_file_entry payload[NEURO_RECOVERY_SEED_MAX_ENTRIES];
	size_t payload_size;
	size_t total_size;
	size_t i;

	if (snapshot == NULL || buf == NULL || out_len == NULL) {
		return -EINVAL;
	}

	if (snapshot->entry_count > NEURO_RECOVERY_SEED_MAX_ENTRIES) {
		return -EOVERFLOW;
	}

	memset(payload, 0, sizeof(payload));
	for (i = 0; i < snapshot->entry_count; i++) {
		payload[i].used = snapshot->entries[i].used ? 1U : 0U;
		copy_bounded(payload[i].app_id, sizeof(payload[i].app_id),
			snapshot->entries[i].app_id);
		payload[i].update_state =
			(uint32_t)snapshot->entries[i].update_state;
		copy_bounded(payload[i].update_last_error,
			sizeof(payload[i].update_last_error),
			snapshot->entries[i].update_last_error);
		copy_bounded(payload[i].rollback_reason,
			sizeof(payload[i].rollback_reason),
			snapshot->entries[i].rollback_reason);
		copy_bounded(payload[i].stable_ref,
			sizeof(payload[i].stable_ref),
			snapshot->entries[i].stable_ref);
		payload[i].artifact_state =
			(uint32_t)snapshot->entries[i].artifact_state;
		copy_bounded(payload[i].artifact_transport,
			sizeof(payload[i].artifact_transport),
			snapshot->entries[i].artifact_transport);
		copy_bounded(payload[i].artifact_key,
			sizeof(payload[i].artifact_key),
			snapshot->entries[i].artifact_key);
		copy_bounded(payload[i].artifact_path,
			sizeof(payload[i].artifact_path),
			snapshot->entries[i].artifact_path);
		payload[i].size_bytes = snapshot->entries[i].size_bytes;
		payload[i].chunk_size = snapshot->entries[i].chunk_size;
		payload[i].chunks_received =
			snapshot->entries[i].chunks_received;
	}

	payload_size =
		snapshot->entry_count * sizeof(struct neuro_seed_file_entry);
	total_size = sizeof(header) + payload_size;
	if (buf_len < total_size) {
		return -ENOSPC;
	}

	header.magic = NEURO_RECOVERY_SEED_MAGIC;
	header.version = NEURO_RECOVERY_SEED_VERSION;
	header.entry_count = (uint32_t)snapshot->entry_count;
	header.payload_crc =
		neuro_crc32((const uint8_t *)payload, payload_size);

	memcpy(buf, &header, sizeof(header));
	if (payload_size > 0U) {
		memcpy(buf + sizeof(header), payload, payload_size);
	}
	*out_len = total_size;
	return 0;
}

int neuro_recovery_seed_decode(const uint8_t *buf, size_t buf_len,
	struct neuro_recovery_seed_snapshot *snapshot)
{
	struct neuro_seed_file_header header;

	if (buf == NULL || snapshot == NULL) {
		return -EINVAL;
	}

	if (buf_len < sizeof(header)) {
		return -EBADMSG;
	}

	memcpy(&header, buf, sizeof(header));
	if (header.magic != NEURO_RECOVERY_SEED_MAGIC) {
		return -EPROTO;
	}

	if (!neuro_recovery_seed_version_supported(header.version)) {
		return -ENOTSUP;
	}

	if (header.version == 1U) {
		return neuro_recovery_seed_decode_v1(
			&header, buf, buf_len, snapshot);
	}

	return -ENOTSUP;
}

int neuro_recovery_seed_store_save(
	const struct neuro_recovery_seed_store *store,
	const struct neuro_recovery_seed_snapshot *snapshot)
{
	const struct neuro_recovery_seed_store_fs_ops *ops = seed_fs_ops();
	struct fs_file_t file;
	uint8_t buf[sizeof(struct neuro_seed_file_header) +
		    NEURO_RECOVERY_SEED_MAX_ENTRIES *
			    sizeof(struct neuro_seed_file_entry)];
	size_t encoded_len = 0U;
	ssize_t written;
	int ret;

	if (store == NULL || snapshot == NULL || store->path[0] == '\0') {
		return -EINVAL;
	}

	if (store->tmp_path[0] == '\0' || store->bak_path[0] == '\0') {
		return -EINVAL;
	}

	ret = ensure_parent_dir(store->path);
	if (ret < 0) {
		return ret;
	}

	ret = neuro_recovery_seed_encode(
		snapshot, buf, sizeof(buf), &encoded_len);
	if (ret) {
		return ret;
	}

	/* Save path is tmp-write + sync + rename so interrupted writes do not
	 * clobber the previously readable seed file.
	 */
	fs_file_t_init(&file);
	ret = ops->open(
		&file, store->tmp_path, FS_O_CREATE | FS_O_WRITE | FS_O_TRUNC);
	if (ret < 0) {
		return ret;
	}

	written = ops->write(&file, buf, encoded_len);
	if (written < 0 || (size_t)written != encoded_len) {
		ret = written < 0 ? (int)written : -EIO;
		(void)ops->close(&file);
		(void)ops->unlink(store->tmp_path);
		return ret;
	}

	ret = ops->sync(&file);
	if (ret < 0) {
		(void)ops->close(&file);
		(void)ops->unlink(store->tmp_path);
		return ret;
	}

	ret = ops->close(&file);
	if (ret < 0) {
		(void)ops->unlink(store->tmp_path);
		return ret;
	}

	ret = ops->rename(store->tmp_path, store->path);
	if (ret == -EEXIST || ret == -ENOTEMPTY) {
		ret = ops->unlink(store->path);
		if (ret < 0) {
			(void)ops->unlink(store->tmp_path);
			return ret;
		}

		ret = ops->rename(store->tmp_path, store->path);
	}

	if (ret < 0) {
		(void)ops->unlink(store->tmp_path);
		return ret;
	}

	return 0;
}

int neuro_recovery_seed_store_load(
	const struct neuro_recovery_seed_store *store,
	struct neuro_recovery_seed_snapshot *snapshot)
{
	int ret;

	if (store == NULL || snapshot == NULL || store->path[0] == '\0') {
		return -EINVAL;
	}

	ret = migrate_legacy_seed_if_needed(store);
	if (ret < 0) {
		return ret;
	}

	ret = recover_tmp_seed_if_needed(store);
	if (ret < 0 && ret != -ENOENT) {
		return ret;
	}

	return read_snapshot_file(store->path, snapshot);
}
