#include "neuro_state_registry.h"

#include <string.h>

#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>

#include "neuro_unit_diag.h"

#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_MODE) &&                               \
	CONFIG_NEUROLINK_UNIT_DEBUG_MODE
#define NEURO_STATE_REGISTRY_LOG_LEVEL LOG_LEVEL_DBG
#else
#define NEURO_STATE_REGISTRY_LOG_LEVEL LOG_LEVEL_INF
#endif

LOG_MODULE_REGISTER(neuro_state_registry, NEURO_STATE_REGISTRY_LOG_LEVEL);

const char *neuro_state_health_to_str(enum neuro_state_health health);

static struct k_mutex *registry_lock(
	const struct neuro_state_registry *registry)
{
	return (struct k_mutex *)&registry->lock;
}

static void copy_bounded(char *dst, size_t dst_len, const char *src)
{
	if (dst_len == 0U) {
		return;
	}

	if (src == NULL) {
		dst[0] = '\0';
		return;
	}

	snprintk(dst, dst_len, "%s", src);
}

static bool update_bool(bool *dst, bool value)
{
	if (*dst == value) {
		return false;
	}

	*dst = value;
	return true;
}

static bool update_size(size_t *dst, size_t value)
{
	if (*dst == value) {
		return false;
	}

	*dst = value;
	return true;
}

static bool update_str(char *dst, size_t dst_len, const char *value)
{
	if (value == NULL) {
		value = "";
	}

	if (strncmp(dst, value, dst_len) == 0) {
		return false;
	}

	copy_bounded(dst, dst_len, value);
	return true;
}

static bool update_network_state(
	enum neuro_network_state *dst, enum neuro_network_state value)
{
	if (*dst == value) {
		return false;
	}

	*dst = value;
	return true;
}

static bool update_health(
	enum neuro_state_health *dst, enum neuro_state_health value)
{
	if (*dst == value) {
		return false;
	}

	*dst = value;
	return true;
}

static enum neuro_state_health health_from_network(
	enum neuro_network_state state)
{
	switch (state) {
	case NEURO_NETWORK_READY:
		return NEURO_STATE_HEALTH_OK;
	case NEURO_NETWORK_DEGRADED:
		return NEURO_STATE_HEALTH_DEGRADED;
	case NEURO_NETWORK_FAILED:
		return NEURO_STATE_HEALTH_FAILED;
	default:
		return NEURO_STATE_HEALTH_UNKNOWN;
	}
}

static const char *state_network_to_str(enum neuro_network_state state)
{
	switch (state) {
	case NEURO_NETWORK_DOWN:
		return "DOWN";
	case NEURO_NETWORK_ADAPTER_READY:
		return "ADAPTER_READY";
	case NEURO_NETWORK_LINK_READY:
		return "LINK_READY";
	case NEURO_NETWORK_ADDRESS_READY:
		return "ADDRESS_READY";
	case NEURO_NETWORK_TRANSPORT_READY:
		return "TRANSPORT_READY";
	case NEURO_NETWORK_READY:
		return "NETWORK_READY";
	case NEURO_NETWORK_DEGRADED:
		return "DEGRADED";
	case NEURO_NETWORK_FAILED:
		return "FAILED";
	default:
		return "UNKNOWN";
	}
}

static void bump_version_if_changed(
	struct neuro_state_registry *registry, bool changed)
{
	/*
	 * Version is monotonically incremented only for semantic snapshot
	 * changes so query-side pollers can treat it as a stable change token.
	 */
	if (changed) {
		registry->snapshot.version++;
	}
}

static void log_snapshot_if_changed(
	struct neuro_state_registry *registry, bool changed, const char *reason)
{
	if (!changed) {
		return;
	}

	neuro_unit_diag_state_snapshot(reason, registry->snapshot.node_id,
		registry->snapshot.version, registry->snapshot.session_ready,
		state_network_to_str(registry->snapshot.network_state),
		neuro_state_health_to_str(registry->snapshot.health));
}

void neuro_state_registry_init(
	struct neuro_state_registry *registry, const char *node_id)
{
	if (registry == NULL) {
		return;
	}

	memset(registry, 0, sizeof(*registry));
	k_mutex_init(&registry->lock);

	copy_bounded(registry->snapshot.node_id,
		sizeof(registry->snapshot.node_id), node_id);
	copy_bounded(registry->snapshot.ipv4_addr,
		sizeof(registry->snapshot.ipv4_addr), "no-ipv4");
	copy_bounded(registry->snapshot.update_status,
		sizeof(registry->snapshot.update_status), "idle");
	registry->snapshot.network_state = NEURO_NETWORK_DOWN;
	registry->snapshot.health = NEURO_STATE_HEALTH_UNKNOWN;

	neuro_unit_diag_state_snapshot("init", registry->snapshot.node_id,
		registry->snapshot.version, registry->snapshot.session_ready,
		state_network_to_str(registry->snapshot.network_state),
		neuro_state_health_to_str(registry->snapshot.health));
}

void neuro_state_registry_set_session_ready(
	struct neuro_state_registry *registry, bool ready)
{
	bool changed;
	bool old_ready;

	if (registry == NULL) {
		return;
	}

	k_mutex_lock(&registry->lock, K_FOREVER);
	old_ready = registry->snapshot.session_ready;
	changed = update_bool(&registry->snapshot.session_ready, ready);
	bump_version_if_changed(registry, changed);
	if (changed) {
		neuro_unit_diag_state_transition_bool("session_ready",
			old_ready, registry->snapshot.session_ready,
			registry->snapshot.version);
	}
	log_snapshot_if_changed(registry, changed, "session_ready");
	k_mutex_unlock(&registry->lock);
}

void neuro_state_registry_set_network(struct neuro_state_registry *registry,
	const struct neuro_network_status *status)
{
	bool changed_network;
	bool changed_ipv4;
	bool changed_health;
	bool changed;
	enum neuro_state_health health;
	enum neuro_network_state old_network_state;
	enum neuro_state_health old_health;
	char old_ipv4_addr[NET_IPV4_ADDR_LEN];

	if (registry == NULL || status == NULL) {
		return;
	}

	health = health_from_network(status->state);
	k_mutex_lock(&registry->lock, K_FOREVER);
	old_network_state = registry->snapshot.network_state;
	old_health = registry->snapshot.health;
	copy_bounded(old_ipv4_addr, sizeof(old_ipv4_addr),
		registry->snapshot.ipv4_addr);

	changed_network = update_network_state(
		&registry->snapshot.network_state, status->state);
	changed_ipv4 = update_str(registry->snapshot.ipv4_addr,
		sizeof(registry->snapshot.ipv4_addr), status->ipv4_addr);
	changed_health = update_health(&registry->snapshot.health, health);
	changed = changed_network || changed_ipv4 || changed_health;
	bump_version_if_changed(registry, changed);

	if (changed_network) {
		neuro_unit_diag_state_transition_enum("network_state",
			state_network_to_str(old_network_state),
			state_network_to_str(registry->snapshot.network_state),
			registry->snapshot.version);
	}
	if (changed_ipv4) {
		neuro_unit_diag_state_transition_text("ipv4_addr",
			old_ipv4_addr, registry->snapshot.ipv4_addr,
			registry->snapshot.version);
	}
	if (changed_health) {
		neuro_unit_diag_state_transition_enum("health",
			neuro_state_health_to_str(old_health),
			neuro_state_health_to_str(registry->snapshot.health),
			registry->snapshot.version);
	}
	log_snapshot_if_changed(registry, changed, "network");
	k_mutex_unlock(&registry->lock);
}

void neuro_state_registry_set_runtime_counters(
	struct neuro_state_registry *registry, size_t app_count,
	size_t running_count)
{
	bool changed_app_count;
	bool changed_running_count;
	bool changed;
	size_t old_app_count;
	size_t old_running_count;

	if (registry == NULL) {
		return;
	}

	k_mutex_lock(&registry->lock, K_FOREVER);
	old_app_count = registry->snapshot.app_count;
	old_running_count = registry->snapshot.running_count;
	changed_app_count =
		update_size(&registry->snapshot.app_count, app_count);
	changed_running_count =
		update_size(&registry->snapshot.running_count, running_count);
	changed = changed_app_count || changed_running_count;
	bump_version_if_changed(registry, changed);
	if (changed_app_count) {
		neuro_unit_diag_state_transition_size("app_count",
			old_app_count, registry->snapshot.app_count,
			registry->snapshot.version);
	}
	if (changed_running_count) {
		neuro_unit_diag_state_transition_size("running_count",
			old_running_count, registry->snapshot.running_count,
			registry->snapshot.version);
	}
	log_snapshot_if_changed(registry, changed, "runtime_counters");
	k_mutex_unlock(&registry->lock);
}

void neuro_state_registry_set_lease_count(
	struct neuro_state_registry *registry, size_t lease_count)
{
	bool changed;
	size_t old_lease_count;

	if (registry == NULL) {
		return;
	}

	k_mutex_lock(&registry->lock, K_FOREVER);
	old_lease_count = registry->snapshot.lease_count;
	changed = update_size(&registry->snapshot.lease_count, lease_count);
	bump_version_if_changed(registry, changed);
	if (changed) {
		neuro_unit_diag_state_transition_size("lease_count",
			old_lease_count, registry->snapshot.lease_count,
			registry->snapshot.version);
	}
	log_snapshot_if_changed(registry, changed, "lease_count");
	k_mutex_unlock(&registry->lock);
}

void neuro_state_registry_set_update_state(
	struct neuro_state_registry *registry, const char *app_id,
	const char *stage, const char *status)
{
	bool changed_app_id;
	bool changed_stage;
	bool changed_status;
	bool changed;
	char old_app_id[NEURO_STATE_UPDATE_APP_ID_MAX_LEN + 1];
	char old_stage[NEURO_STATE_UPDATE_STAGE_MAX_LEN + 1];
	char old_status[NEURO_STATE_UPDATE_STATUS_MAX_LEN + 1];

	if (registry == NULL) {
		return;
	}

	k_mutex_lock(&registry->lock, K_FOREVER);
	copy_bounded(old_app_id, sizeof(old_app_id),
		registry->snapshot.update_app_id);
	copy_bounded(
		old_stage, sizeof(old_stage), registry->snapshot.update_stage);
	copy_bounded(old_status, sizeof(old_status),
		registry->snapshot.update_status);

	changed_app_id = update_str(registry->snapshot.update_app_id,
		sizeof(registry->snapshot.update_app_id), app_id);
	changed_stage = update_str(registry->snapshot.update_stage,
		sizeof(registry->snapshot.update_stage), stage);
	changed_status = update_str(registry->snapshot.update_status,
		sizeof(registry->snapshot.update_status), status);
	changed = changed_app_id || changed_stage || changed_status;
	bump_version_if_changed(registry, changed);

	if (changed_app_id) {
		neuro_unit_diag_state_transition_text("update_app_id",
			old_app_id, registry->snapshot.update_app_id,
			registry->snapshot.version);
	}
	if (changed_stage) {
		neuro_unit_diag_state_transition_text("update_stage", old_stage,
			registry->snapshot.update_stage,
			registry->snapshot.version);
	}
	if (changed_status) {
		neuro_unit_diag_state_transition_text("update_status",
			old_status, registry->snapshot.update_status,
			registry->snapshot.version);
	}
	log_snapshot_if_changed(registry, changed, "update_state");
	k_mutex_unlock(&registry->lock);
}

uint64_t neuro_state_registry_version(
	const struct neuro_state_registry *registry)
{
	uint64_t version = 0U;

	if (registry == NULL) {
		return 0U;
	}

	/* Reader path uses the same lock so version and snapshot stay coherent.
	 */
	k_mutex_lock(registry_lock(registry), K_FOREVER);
	version = registry->snapshot.version;
	k_mutex_unlock(registry_lock(registry));

	return version;
}

void neuro_state_registry_get_snapshot(
	const struct neuro_state_registry *registry,
	struct neuro_state_snapshot *snapshot)
{
	if (registry == NULL || snapshot == NULL) {
		return;
	}

	k_mutex_lock(registry_lock(registry), K_FOREVER);
	*snapshot = registry->snapshot;
	k_mutex_unlock(registry_lock(registry));
}

const char *neuro_state_health_to_str(enum neuro_state_health health)
{
	switch (health) {
	case NEURO_STATE_HEALTH_OK:
		return "ok";
	case NEURO_STATE_HEALTH_DEGRADED:
		return "degraded";
	case NEURO_STATE_HEALTH_FAILED:
		return "failed";
	default:
		return "unknown";
	}
}
