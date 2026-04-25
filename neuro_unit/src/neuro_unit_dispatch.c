#include "neuro_unit_dispatch.h"

#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>

#include <string.h>

#include "neuro_request_policy.h"

#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_MODE) &&                               \
	CONFIG_NEUROLINK_UNIT_DEBUG_MODE
#define NEURO_UNIT_DISPATCH_LOG_LEVEL LOG_LEVEL_DBG
#else
#define NEURO_UNIT_DISPATCH_LOG_LEVEL LOG_LEVEL_INF
#endif

LOG_MODULE_REGISTER(neuro_unit_dispatch, NEURO_UNIT_DISPATCH_LOG_LEVEL);

static bool ops_are_valid(const struct neuro_unit_dispatch_ops *ops)
{
	return ops != NULL && ops->node_id != NULL &&
	       ops->transport_healthy != NULL &&
	       ops->log_transport_health_snapshot != NULL &&
	       ops->validate_request_metadata_or_reply != NULL &&
	       ops->reply_error != NULL;
}

static void reply_bad_dispatch_contract(const z_loaned_query_t *query,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops)
{
	const char *request_id = "-";

	if (metadata != NULL && metadata->request_id[0] != '\0') {
		request_id = metadata->request_id;
	}

	if (ops != NULL && ops->reply_error != NULL) {
		ops->reply_error(query, request_id,
			"dispatch contract unavailable", 500);
	}
}

bool neuro_unit_dispatch_extract_app_route(const char *key, const char *prefix,
	char *app_id, size_t app_id_len, const char **action)
{
	const char *start;
	const char *sep;
	size_t len;

	if (key == NULL || prefix == NULL || app_id == NULL || action == NULL ||
		app_id_len == 0U) {
		return false;
	}

	start = strstr(key, prefix);
	if (start == NULL) {
		return false;
	}

	start += strlen(prefix);
	sep = strchr(start, '/');
	if (sep == NULL) {
		return false;
	}

	len = (size_t)(sep - start);
	if (len == 0U || len >= app_id_len) {
		return false;
	}

	memcpy(app_id, start, len);
	app_id[len] = '\0';
	*action = sep + 1;
	return true;
}

void neuro_unit_dispatch_command_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops)
{
	char app_id[32];
	const char *action;
	char route_lease_acquire[96];
	char route_lease_release[96];
	uint32_t required_fields;

	if (!ops_are_valid(ops) || key == NULL || payload == NULL ||
		metadata == NULL) {
		reply_bad_dispatch_contract(query, metadata, ops);
		return;
	}

	LOG_INF("cmd query: %s payload=%s", key, payload[0] ? payload : "-");
	if (!ops->transport_healthy()) {
		ops->log_transport_health_snapshot(
			"cmd_gate", key, metadata->request_id);
		ops->reply_error(query, metadata->request_id,
			"session transport unstable", 503);
		return;
	}

	required_fields = neuro_request_policy_required_fields_for_command(key);
	if (required_fields != 0U &&
		!ops->validate_request_metadata_or_reply(
			query, payload, metadata, required_fields)) {
		return;
	}

	snprintk(route_lease_acquire, sizeof(route_lease_acquire),
		"neuro/%s/cmd/lease/acquire", ops->node_id);
	snprintk(route_lease_release, sizeof(route_lease_release),
		"neuro/%s/cmd/lease/release", ops->node_id);

	if (strcmp(key, route_lease_acquire) == 0) {
		if (ops->handle_lease_acquire != NULL) {
			ops->handle_lease_acquire(
				query, payload, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"lease acquire handler unavailable", 500);
		return;
	}

	if (strcmp(key, route_lease_release) == 0) {
		if (ops->handle_lease_release != NULL) {
			ops->handle_lease_release(
				query, payload, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"lease release handler unavailable", 500);
		return;
	}

	if (neuro_unit_dispatch_extract_app_route(
		    key, "/cmd/app/", app_id, sizeof(app_id), &action)) {
		if (ops->handle_app_action != NULL) {
			ops->handle_app_action(query, app_id, action, payload,
				metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"app command handler unavailable", 500);
		return;
	}

	ops->reply_error(
		query, metadata->request_id, "unsupported command path", 404);
}

void neuro_unit_dispatch_query_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops)
{
	char route_device[96];
	char route_apps[96];
	char route_leases[96];
	uint32_t required_fields;

	if (!ops_are_valid(ops) || key == NULL || payload == NULL ||
		metadata == NULL) {
		reply_bad_dispatch_contract(query, metadata, ops);
		return;
	}

	LOG_INF("state query: %s", key);
	if (!ops->transport_healthy()) {
		ops->log_transport_health_snapshot(
			"query_gate", key, metadata->request_id);
		ops->reply_error(query, metadata->request_id,
			"session transport unstable", 503);
		return;
	}

	required_fields = neuro_request_policy_required_fields_for_query(key);
	if (required_fields != 0U &&
		!ops->validate_request_metadata_or_reply(
			query, payload, metadata, required_fields)) {
		return;
	}

	snprintk(route_device, sizeof(route_device), "neuro/%s/query/device",
		ops->node_id);
	snprintk(route_apps, sizeof(route_apps), "neuro/%s/query/apps",
		ops->node_id);
	snprintk(route_leases, sizeof(route_leases), "neuro/%s/query/leases",
		ops->node_id);

	if (strcmp(key, route_device) == 0) {
		if (ops->handle_query_device != NULL) {
			ops->handle_query_device(query, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"query device handler unavailable", 500);
		return;
	}

	if (strcmp(key, route_apps) == 0) {
		if (ops->handle_query_apps != NULL) {
			ops->handle_query_apps(query, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"query apps handler unavailable", 500);
		return;
	}

	if (strcmp(key, route_leases) == 0) {
		if (ops->handle_query_leases != NULL) {
			ops->handle_query_leases(query, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"query leases handler unavailable", 500);
		return;
	}

	ops->reply_error(
		query, metadata->request_id, "unsupported query path", 404);
}

void neuro_unit_dispatch_update_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops)
{
	char app_id[32];
	const char *action;
	uint32_t required_fields;
	bool lifecycle_action;

	if (!ops_are_valid(ops) || key == NULL || payload == NULL ||
		metadata == NULL) {
		reply_bad_dispatch_contract(query, metadata, ops);
		return;
	}

	LOG_INF("update query: %s payload=%s", key, payload[0] ? payload : "-");
	if (!ops->transport_healthy()) {
		ops->log_transport_health_snapshot(
			"update_gate", key, metadata->request_id);
		ops->reply_error(query, metadata->request_id,
			"session transport unstable", 503);
		return;
	}

	if (!neuro_unit_dispatch_extract_app_route(
		    key, "/update/app/", app_id, sizeof(app_id), &action)) {
		ops->reply_error(query, metadata->request_id,
			"invalid update path", 400);
		return;
	}

	required_fields =
		neuro_request_policy_required_fields_for_update_action(action);
	if (required_fields != 0U &&
		!ops->validate_request_metadata_or_reply(
			query, payload, metadata, required_fields)) {
		return;
	}

	lifecycle_action = strcmp(action, "prepare") == 0 ||
			   strcmp(action, "verify") == 0 ||
			   strcmp(action, "activate") == 0 ||
			   strcmp(action, "rollback") == 0 ||
			   strcmp(action, "recover") == 0;

	if (lifecycle_action) {
		if (ops->ensure_recovery_seed_initialized == NULL) {
			ops->reply_error(query, metadata->request_id,
				"recovery seed gate unavailable", 500);
			return;
		}

		if (ops->ensure_recovery_seed_initialized() != 0) {
			ops->reply_error(query, metadata->request_id,
				"recovery seed storage not ready", 503);
			return;
		}
	}

	if (lifecycle_action) {
		if (ops->handle_update_action != NULL) {
			ops->handle_update_action(query, app_id, action,
				payload, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"update command handler unavailable", 500);
		return;
	}

	ops->reply_error(
		query, metadata->request_id, "unsupported update path", 404);
}
