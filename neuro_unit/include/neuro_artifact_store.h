#ifndef NEURO_ARTIFACT_STORE_H
#define NEURO_ARTIFACT_STORE_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_ARTIFACT_STORE_MAX_ENTRIES 4

enum neuro_artifact_state {
	NEURO_ARTIFACT_NONE = 0,
	NEURO_ARTIFACT_STAGED,
	NEURO_ARTIFACT_VERIFIED,
	NEURO_ARTIFACT_ACTIVE,
	NEURO_ARTIFACT_INVALID,
};

struct neuro_artifact_meta {
	bool used;
	char app_id[32];
	char transport[16];
	char artifact_key[128];
	char path[128];
	size_t size_bytes;
	size_t chunk_size;
	size_t chunks_received;
	enum neuro_artifact_state state;
};

struct neuro_artifact_store {
	struct neuro_artifact_meta entries[NEURO_ARTIFACT_STORE_MAX_ENTRIES];
};

void neuro_artifact_store_init(struct neuro_artifact_store *store);
int neuro_artifact_store_stage(struct neuro_artifact_store *store,
	const char *app_id, const char *transport, const char *artifact_key,
	const char *path, size_t size_bytes, size_t chunk_size,
	size_t chunks_received);
int neuro_artifact_store_set_state(struct neuro_artifact_store *store,
	const char *app_id, enum neuro_artifact_state state);
int neuro_artifact_store_remove(
	struct neuro_artifact_store *store, const char *app_id);
size_t neuro_artifact_store_export_entries(
	const struct neuro_artifact_store *store,
	struct neuro_artifact_meta *entries, size_t max_entries);
int neuro_artifact_store_import_entries(struct neuro_artifact_store *store,
	const struct neuro_artifact_meta *entries, size_t entry_count);
const struct neuro_artifact_meta *neuro_artifact_store_get(
	const struct neuro_artifact_store *store, const char *app_id);

#ifdef __cplusplus
}
#endif

#endif
