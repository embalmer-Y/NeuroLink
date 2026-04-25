#ifndef NEURO_LEASE_MANAGER_H
#define NEURO_LEASE_MANAGER_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#include "neuro_request_envelope.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_LEASE_MANAGER_MAX_ENTRIES 4

struct neuro_lease_entry {
	bool active;
	char lease_id[32];
	char resource[48];
	char source_core[24];
	char source_agent[24];
	int priority;
	int64_t expires_at_ms;
};

struct neuro_lease_manager {
	struct neuro_lease_entry entries[NEURO_LEASE_MANAGER_MAX_ENTRIES];
};

struct neuro_lease_acquire_result {
	struct neuro_lease_entry acquired;
	bool preempted;
	struct neuro_lease_entry preempted_entry;
};

void neuro_lease_manager_init(struct neuro_lease_manager *manager);

int neuro_lease_manager_expire_all(struct neuro_lease_manager *manager);

void neuro_lease_manager_prune_expired(
	struct neuro_lease_manager *manager, int64_t now_ms);

int neuro_lease_manager_acquire(struct neuro_lease_manager *manager,
	const char *resource, const struct neuro_request_metadata *metadata,
	int ttl_ms, int64_t now_ms, struct neuro_lease_acquire_result *result);

int neuro_lease_manager_release(struct neuro_lease_manager *manager,
	const struct neuro_request_metadata *metadata, int64_t now_ms,
	struct neuro_lease_entry *released);

int neuro_lease_manager_require_resource(struct neuro_lease_manager *manager,
	const char *resource, const struct neuro_request_metadata *metadata,
	int64_t now_ms);

const struct neuro_lease_entry *neuro_lease_manager_entry_at(
	const struct neuro_lease_manager *manager, size_t index);

#ifdef __cplusplus
}
#endif

#endif
