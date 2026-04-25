#include "neuro_artifact_store.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>

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

static struct neuro_artifact_meta *find_entry_mut(
	struct neuro_artifact_store *store, const char *app_id)
{
	size_t i;

	for (i = 0; i < NEURO_ARTIFACT_STORE_MAX_ENTRIES; i++) {
		if (store->entries[i].used &&
			strcmp(store->entries[i].app_id, app_id) == 0) {
			return &store->entries[i];
		}
	}

	return NULL;
}

static struct neuro_artifact_meta *find_or_alloc_entry(
	struct neuro_artifact_store *store, const char *app_id)
{
	struct neuro_artifact_meta *entry;
	size_t i;

	entry = find_entry_mut(store, app_id);
	if (entry != NULL) {
		return entry;
	}

	for (i = 0; i < NEURO_ARTIFACT_STORE_MAX_ENTRIES; i++) {
		if (!store->entries[i].used) {
			store->entries[i].used = true;
			copy_bounded(store->entries[i].app_id,
				sizeof(store->entries[i].app_id), app_id);
			store->entries[i].state = NEURO_ARTIFACT_NONE;
			return &store->entries[i];
		}
	}

	return NULL;
}

void neuro_artifact_store_init(struct neuro_artifact_store *store)
{
	if (store == NULL) {
		return;
	}

	memset(store, 0, sizeof(*store));
}

int neuro_artifact_store_stage(struct neuro_artifact_store *store,
	const char *app_id, const char *transport, const char *artifact_key,
	const char *path, size_t size_bytes, size_t chunk_size,
	size_t chunks_received)
{
	struct neuro_artifact_meta *entry;

	if (store == NULL || app_id == NULL || app_id[0] == '\0' ||
		path == NULL || path[0] == '\0') {
		return -EINVAL;
	}

	entry = find_or_alloc_entry(store, app_id);
	if (entry == NULL) {
		return -ENOSPC;
	}

	copy_bounded(entry->transport, sizeof(entry->transport), transport);
	copy_bounded(
		entry->artifact_key, sizeof(entry->artifact_key), artifact_key);
	copy_bounded(entry->path, sizeof(entry->path), path);
	entry->size_bytes = size_bytes;
	entry->chunk_size = chunk_size;
	entry->chunks_received = chunks_received;
	entry->state = NEURO_ARTIFACT_STAGED;
	return 0;
}

int neuro_artifact_store_set_state(struct neuro_artifact_store *store,
	const char *app_id, enum neuro_artifact_state state)
{
	struct neuro_artifact_meta *entry;

	if (store == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry_mut(store, app_id);
	if (entry == NULL) {
		return -ENOENT;
	}

	entry->state = state;
	return 0;
}

int neuro_artifact_store_remove(
	struct neuro_artifact_store *store, const char *app_id)
{
	struct neuro_artifact_meta *entry;

	if (store == NULL || app_id == NULL || app_id[0] == '\0') {
		return -EINVAL;
	}

	entry = find_entry_mut(store, app_id);
	if (entry == NULL) {
		return -ENOENT;
	}

	memset(entry, 0, sizeof(*entry));
	return 0;
}

size_t neuro_artifact_store_export_entries(
	const struct neuro_artifact_store *store,
	struct neuro_artifact_meta *entries, size_t max_entries)
{
	size_t i;
	size_t exported = 0U;

	if (store == NULL || entries == NULL || max_entries == 0U) {
		return 0U;
	}

	for (i = 0; i < NEURO_ARTIFACT_STORE_MAX_ENTRIES; i++) {
		if (!store->entries[i].used) {
			continue;
		}

		if (exported >= max_entries) {
			break;
		}

		entries[exported++] = store->entries[i];
	}

	return exported;
}

int neuro_artifact_store_import_entries(struct neuro_artifact_store *store,
	const struct neuro_artifact_meta *entries, size_t entry_count)
{
	size_t i;

	if (store == NULL) {
		return -EINVAL;
	}

	if (entries == NULL && entry_count != 0U) {
		return -EINVAL;
	}

	if (entry_count > NEURO_ARTIFACT_STORE_MAX_ENTRIES) {
		return -ENOSPC;
	}

	memset(store, 0, sizeof(*store));
	for (i = 0; i < entry_count; i++) {
		store->entries[i] = entries[i];
		store->entries[i].used = entries[i].used;
	}

	return 0;
}

const struct neuro_artifact_meta *neuro_artifact_store_get(
	const struct neuro_artifact_store *store, const char *app_id)
{
	size_t i;

	if (store == NULL || app_id == NULL || app_id[0] == '\0') {
		return NULL;
	}

	for (i = 0; i < NEURO_ARTIFACT_STORE_MAX_ENTRIES; i++) {
		if (store->entries[i].used &&
			strcmp(store->entries[i].app_id, app_id) == 0) {
			return &store->entries[i];
		}
	}

	return NULL;
}
