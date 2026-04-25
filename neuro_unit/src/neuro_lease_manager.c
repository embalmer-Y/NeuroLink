#include "neuro_lease_manager.h"

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

static bool lease_holder_matches_request(const struct neuro_lease_entry *lease,
	const struct neuro_request_metadata *metadata)
{
	if (lease == NULL || metadata == NULL) {
		return false;
	}

	return strcmp(lease->source_core, metadata->source_core) == 0 &&
	       strcmp(lease->source_agent, metadata->source_agent) == 0;
}

static struct neuro_lease_entry *find_lease_by_id(
	struct neuro_lease_manager *manager, const char *lease_id)
{
	size_t i;

	for (i = 0; i < NEURO_LEASE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].active &&
			strcmp(manager->entries[i].lease_id, lease_id) == 0) {
			return &manager->entries[i];
		}
	}

	return NULL;
}

static struct neuro_lease_entry *find_lease_by_resource(
	struct neuro_lease_manager *manager, const char *resource)
{
	size_t i;

	for (i = 0; i < NEURO_LEASE_MANAGER_MAX_ENTRIES; i++) {
		if (manager->entries[i].active &&
			strcmp(manager->entries[i].resource, resource) == 0) {
			return &manager->entries[i];
		}
	}

	return NULL;
}

static struct neuro_lease_entry *find_free_lease(
	struct neuro_lease_manager *manager)
{
	size_t i;

	for (i = 0; i < NEURO_LEASE_MANAGER_MAX_ENTRIES; i++) {
		if (!manager->entries[i].active) {
			return &manager->entries[i];
		}
	}

	return NULL;
}

static void ensure_generated_lease_id(
	char *lease_id, size_t lease_id_len, int64_t now_ms)
{
	if (lease_id[0] != '\0') {
		return;
	}

	snprintf(lease_id, lease_id_len, "lease-%lld", now_ms);
}

void neuro_lease_manager_init(struct neuro_lease_manager *manager)
{
	if (manager == NULL) {
		return;
	}

	memset(manager, 0, sizeof(*manager));
}

int neuro_lease_manager_expire_all(struct neuro_lease_manager *manager)
{
	size_t i;
	int expired = 0;

	if (manager == NULL) {
		return -EINVAL;
	}

	for (i = 0; i < NEURO_LEASE_MANAGER_MAX_ENTRIES; i++) {
		if (!manager->entries[i].active) {
			continue;
		}

		manager->entries[i].active = false;
		expired++;
	}

	return expired;
}

void neuro_lease_manager_prune_expired(
	struct neuro_lease_manager *manager, int64_t now_ms)
{
	size_t i;

	if (manager == NULL) {
		return;
	}

	for (i = 0; i < NEURO_LEASE_MANAGER_MAX_ENTRIES; i++) {
		if (!manager->entries[i].active) {
			continue;
		}

		if (manager->entries[i].expires_at_ms <= now_ms) {
			manager->entries[i].active = false;
		}
	}
}

int neuro_lease_manager_acquire(struct neuro_lease_manager *manager,
	const char *resource, const struct neuro_request_metadata *metadata,
	int ttl_ms, int64_t now_ms, struct neuro_lease_acquire_result *result)
{
	struct neuro_lease_entry *current;
	struct neuro_lease_entry *slot;
	char lease_id[sizeof(((struct neuro_lease_entry *)0)->lease_id)] = "";

	if (manager == NULL || resource == NULL || metadata == NULL ||
		result == NULL) {
		return -EINVAL;
	}

	if (resource[0] == '\0' || ttl_ms <= 0) {
		return -EINVAL;
	}

	memset(result, 0, sizeof(*result));
	copy_bounded(lease_id, sizeof(lease_id), metadata->lease_id);
	ensure_generated_lease_id(lease_id, sizeof(lease_id), now_ms);
	neuro_lease_manager_prune_expired(manager, now_ms);

	current = find_lease_by_resource(manager, resource);
	if (current != NULL) {
		if (strcmp(current->lease_id, lease_id) == 0) {
			if (!lease_holder_matches_request(current, metadata)) {
				return -EACCES;
			}
		} else if (metadata->priority > current->priority) {
			result->preempted = true;
			result->preempted_entry = *current;
		} else {
			return -EEXIST;
		}
	}

	if (current == NULL) {
		slot = find_free_lease(manager);
		if (slot == NULL) {
			return -ENOSPC;
		}

		current = slot;
	}

	current->active = true;
	copy_bounded(current->lease_id, sizeof(current->lease_id), lease_id);
	copy_bounded(current->resource, sizeof(current->resource), resource);
	copy_bounded(current->source_core, sizeof(current->source_core),
		metadata->source_core);
	copy_bounded(current->source_agent, sizeof(current->source_agent),
		metadata->source_agent);
	current->priority = metadata->priority;
	current->expires_at_ms = now_ms + ttl_ms;
	result->acquired = *current;

	return 0;
}

int neuro_lease_manager_release(struct neuro_lease_manager *manager,
	const struct neuro_request_metadata *metadata, int64_t now_ms,
	struct neuro_lease_entry *released)
{
	struct neuro_lease_entry *lease;

	if (manager == NULL || metadata == NULL || released == NULL) {
		return -EINVAL;
	}

	if (metadata->lease_id[0] == '\0') {
		return -EINVAL;
	}

	neuro_lease_manager_prune_expired(manager, now_ms);
	lease = find_lease_by_id(manager, metadata->lease_id);
	if (lease == NULL) {
		return -ENOENT;
	}

	if (!lease_holder_matches_request(lease, metadata)) {
		return -EACCES;
	}

	*released = *lease;
	lease->active = false;
	return 0;
}

int neuro_lease_manager_require_resource(struct neuro_lease_manager *manager,
	const char *resource, const struct neuro_request_metadata *metadata,
	int64_t now_ms)
{
	struct neuro_lease_entry *lease;

	if (manager == NULL || resource == NULL || metadata == NULL) {
		return -EINVAL;
	}

	neuro_lease_manager_prune_expired(manager, now_ms);
	lease = find_lease_by_resource(manager, resource);
	if (lease == NULL || strcmp(lease->lease_id, metadata->lease_id) != 0) {
		return -EPERM;
	}

	if (!lease_holder_matches_request(lease, metadata)) {
		return -EACCES;
	}

	return 0;
}

const struct neuro_lease_entry *neuro_lease_manager_entry_at(
	const struct neuro_lease_manager *manager, size_t index)
{
	if (manager == NULL || index >= NEURO_LEASE_MANAGER_MAX_ENTRIES) {
		return NULL;
	}

	return &manager->entries[index];
}
