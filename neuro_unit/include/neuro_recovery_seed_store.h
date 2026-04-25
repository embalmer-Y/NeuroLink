#ifndef NEURO_RECOVERY_SEED_STORE_H
#define NEURO_RECOVERY_SEED_STORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/fs/fs.h>

#include "neuro_artifact_store.h"
#include "neuro_update_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_RECOVERY_SEED_MAGIC 0x4E525344U
#define NEURO_RECOVERY_SEED_VERSION 1U
#define NEURO_RECOVERY_SEED_MIN_SUPPORTED_VERSION 1U
#define NEURO_RECOVERY_SEED_MAX_SUPPORTED_VERSION NEURO_RECOVERY_SEED_VERSION
#define NEURO_RECOVERY_SEED_MAX_ENTRIES 4U
#define NEURO_RECOVERY_SEED_PATH_DEFAULT "/SD:/recovery.seed"
#define NEURO_RECOVERY_SEED_PATH_LEGACY "/SD:/neuro/recovery.seed"

struct neuro_recovery_seed_entry {
	bool used;
	char app_id[32];
	enum neuro_update_state update_state;
	char update_last_error[64];
	char rollback_reason[64];
	char stable_ref[96];
	enum neuro_artifact_state artifact_state;
	char artifact_transport[16];
	char artifact_key[128];
	char artifact_path[128];
	uint32_t size_bytes;
	uint32_t chunk_size;
	uint32_t chunks_received;
};

struct neuro_recovery_seed_snapshot {
	size_t entry_count;
	struct neuro_recovery_seed_entry
		entries[NEURO_RECOVERY_SEED_MAX_ENTRIES];
};

struct neuro_recovery_seed_store {
	char path[128];
	char tmp_path[128];
	char bak_path[128];
	char legacy_path[128];
};

struct neuro_recovery_seed_store_fs_ops {
	int (*stat)(const char *path, struct fs_dirent *entry);
	int (*mkdir)(const char *path);
	int (*rename)(const char *from, const char *to);
	int (*unlink)(const char *path);
	int (*open)(struct fs_file_t *file, const char *path, fs_mode_t flags);
	ssize_t (*read)(struct fs_file_t *file, void *ptr, size_t size);
	ssize_t (*write)(struct fs_file_t *file, const void *ptr, size_t size);
	int (*sync)(struct fs_file_t *file);
	int (*close)(struct fs_file_t *file);
};

void neuro_recovery_seed_store_init(
	struct neuro_recovery_seed_store *store, const char *path);

void neuro_recovery_seed_store_set_fs_ops(
	const struct neuro_recovery_seed_store_fs_ops *ops);
void neuro_recovery_seed_store_reset_fs_ops(void);

int neuro_recovery_seed_build_snapshot(
	const struct neuro_update_manager *update_manager,
	const struct neuro_artifact_store *artifact_store,
	struct neuro_recovery_seed_snapshot *snapshot);
int neuro_recovery_seed_apply_snapshot(
	const struct neuro_recovery_seed_snapshot *snapshot,
	struct neuro_update_manager *update_manager,
	struct neuro_artifact_store *artifact_store);

int neuro_recovery_seed_encode(
	const struct neuro_recovery_seed_snapshot *snapshot, uint8_t *buf,
	size_t buf_len, size_t *out_len);
int neuro_recovery_seed_decode(const uint8_t *buf, size_t buf_len,
	struct neuro_recovery_seed_snapshot *snapshot);

int neuro_recovery_seed_store_save(
	const struct neuro_recovery_seed_store *store,
	const struct neuro_recovery_seed_snapshot *snapshot);
int neuro_recovery_seed_store_load(
	const struct neuro_recovery_seed_store *store,
	struct neuro_recovery_seed_snapshot *snapshot);

#ifdef __cplusplus
}
#endif

#endif
