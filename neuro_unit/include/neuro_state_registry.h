#ifndef NEURO_STATE_REGISTRY_H
#define NEURO_STATE_REGISTRY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/kernel.h>
#include <zephyr/net/net_ip.h>

#include "neuro_network_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_STATE_NODE_ID_MAX_LEN 31
#define NEURO_STATE_UPDATE_APP_ID_MAX_LEN 31
#define NEURO_STATE_UPDATE_STAGE_MAX_LEN 31
#define NEURO_STATE_UPDATE_STATUS_MAX_LEN 15

enum neuro_state_health {
	NEURO_STATE_HEALTH_UNKNOWN = 0,
	NEURO_STATE_HEALTH_OK,
	NEURO_STATE_HEALTH_DEGRADED,
	NEURO_STATE_HEALTH_FAILED,
};

struct neuro_state_snapshot {
	char node_id[NEURO_STATE_NODE_ID_MAX_LEN + 1];
	uint64_t version;
	bool session_ready;
	enum neuro_network_state network_state;
	char ipv4_addr[NET_IPV4_ADDR_LEN];
	enum neuro_state_health health;
	size_t app_count;
	size_t running_count;
	size_t lease_count;
	char update_app_id[NEURO_STATE_UPDATE_APP_ID_MAX_LEN + 1];
	char update_stage[NEURO_STATE_UPDATE_STAGE_MAX_LEN + 1];
	char update_status[NEURO_STATE_UPDATE_STATUS_MAX_LEN + 1];
};

struct neuro_state_registry {
	struct k_mutex lock;
	struct neuro_state_snapshot snapshot;
};

void neuro_state_registry_init(
	struct neuro_state_registry *registry, const char *node_id);

void neuro_state_registry_set_session_ready(
	struct neuro_state_registry *registry, bool ready);
void neuro_state_registry_set_network(struct neuro_state_registry *registry,
	const struct neuro_network_status *status);
void neuro_state_registry_set_runtime_counters(
	struct neuro_state_registry *registry, size_t app_count,
	size_t running_count);
void neuro_state_registry_set_lease_count(
	struct neuro_state_registry *registry, size_t lease_count);
void neuro_state_registry_set_update_state(
	struct neuro_state_registry *registry, const char *app_id,
	const char *stage, const char *status);

uint64_t neuro_state_registry_version(
	const struct neuro_state_registry *registry);
void neuro_state_registry_get_snapshot(
	const struct neuro_state_registry *registry,
	struct neuro_state_snapshot *snapshot);
const char *neuro_state_health_to_str(enum neuro_state_health health);

#ifdef __cplusplus
}
#endif

#endif
