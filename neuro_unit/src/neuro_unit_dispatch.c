#include "neuro_unit_dispatch.h"

#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>

#include <string.h>

#include "neuro_protocol.h"
#include "neuro_request_policy.h"
#include "neuro_unit_diag.h"

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

static void route_reset(struct neuro_unit_dispatch_route *route)
{
	if (route == NULL) {
		return;
	}

	memset(route, 0, sizeof(*route));
	route->kind = NEURO_UNIT_DISPATCH_ROUTE_INVALID;
}

static bool key_matches_query_route(const char *key, const char *node_id,
	enum neuro_protocol_query_kind kind)
{
	char route[NEURO_PROTOCOL_ROUTE_LEN];

	return neuro_protocol_build_query_route(
		       route, sizeof(route), node_id, kind) == 0 &&
	       strcmp(key, route) == 0;
}

static bool key_matches_lease_route(const char *key, const char *node_id,
	enum neuro_protocol_lease_action action)
{
	char route[NEURO_PROTOCOL_ROUTE_LEN];

	return neuro_protocol_build_lease_route(
		       route, sizeof(route), node_id, action) == 0 &&
	       strcmp(key, route) == 0;
}

static bool extract_scoped_app_route(const char *key, const char *node_id,
	const char *scope, char *app_id, size_t app_id_len, const char **action)
{
	char prefix[NEURO_PROTOCOL_ROUTE_LEN];
	const char *start;
	const char *sep;
	size_t prefix_len;
	size_t app_id_size;
	int ret;

	if (key == NULL || !neuro_protocol_token_is_valid(node_id) ||
		scope == NULL || app_id == NULL || app_id_len == 0U ||
		action == NULL) {
		return false;
	}

	ret = snprintk(
		prefix, sizeof(prefix), "neuro/%s/%s/app/", node_id, scope);
	if (ret < 0 || (size_t)ret >= sizeof(prefix)) {
		return false;
	}

	prefix_len = strlen(prefix);
	if (strncmp(key, prefix, prefix_len) != 0) {
		return false;
	}

	start = key + prefix_len;
	sep = strchr(start, '/');
	if (sep == NULL) {
		return false;
	}

	app_id_size = (size_t)(sep - start);
	if (app_id_size == 0U || app_id_size >= app_id_len) {
		return false;
	}

	memcpy(app_id, start, app_id_size);
	app_id[app_id_size] = '\0';
	*action = sep + 1;
	return neuro_protocol_token_is_valid(app_id) &&
	       neuro_protocol_token_is_valid(*action);
}

bool neuro_unit_dispatch_classify_command_route(const char *key,
	const char *node_id, struct neuro_unit_dispatch_route *route)
{
	route_reset(route);
	if (key == NULL || route == NULL) {
		return false;
	}

	if (key_matches_lease_route(
		    key, node_id, NEURO_PROTOCOL_LEASE_ACQUIRE)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_LEASE_ACQUIRE;
		return true;
	}

	if (key_matches_lease_route(
		    key, node_id, NEURO_PROTOCOL_LEASE_RELEASE)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_LEASE_RELEASE;
		return true;
	}

	if (extract_scoped_app_route(key, node_id, "cmd", route->app_id,
		    sizeof(route->app_id), &route->action)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_APP_ACTION;
		return true;
	}

	return false;
}

bool neuro_unit_dispatch_classify_query_route(const char *key,
	const char *node_id, struct neuro_unit_dispatch_route *route)
{
	route_reset(route);
	if (key == NULL || route == NULL) {
		return false;
	}

	if (key_matches_query_route(
		    key, node_id, NEURO_PROTOCOL_QUERY_DEVICE)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_QUERY_DEVICE;
		return true;
	}

	if (key_matches_query_route(key, node_id, NEURO_PROTOCOL_QUERY_APPS)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_QUERY_APPS;
		return true;
	}

	if (key_matches_query_route(
		    key, node_id, NEURO_PROTOCOL_QUERY_LEASES)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_QUERY_LEASES;
		return true;
	}

	return false;
}

bool neuro_unit_dispatch_classify_update_route(const char *key,
	const char *node_id, struct neuro_unit_dispatch_route *route)
{
	route_reset(route);
	if (key == NULL || route == NULL) {
		return false;
	}

	if (extract_scoped_app_route(key, node_id, "update", route->app_id,
		    sizeof(route->app_id), &route->action)) {
		route->kind = NEURO_UNIT_DISPATCH_ROUTE_UPDATE_ACTION;
		return true;
	}

	return false;
}

void neuro_unit_dispatch_command_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_request_fields *request_fields,
	const struct neuro_unit_dispatch_ops *ops)
{
	struct neuro_unit_dispatch_route route;
	uint32_t required_fields;

	if (!ops_are_valid(ops) || key == NULL || payload == NULL ||
		metadata == NULL) {
		reply_bad_dispatch_contract(query, metadata, ops);
		return;
	}

	LOG_DBG("cmd query: key=%s request_id=%s payload_len=%zu", key,
		metadata->request_id, strlen(payload));
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

	if (!neuro_unit_dispatch_classify_command_route(
		    key, ops->node_id, &route)) {
		neuro_unit_diag_dispatch_result(
			"cmd", key, metadata->request_id, "unsupported", 404);
		ops->reply_error(query, metadata->request_id,
			"unsupported command path", 404);
		return;
	}

	if (route.kind == NEURO_UNIT_DISPATCH_ROUTE_LEASE_ACQUIRE) {
		neuro_unit_diag_dispatch_result(
			"cmd", key, metadata->request_id, "lease_acquire", 0);
		if (ops->handle_lease_acquire != NULL) {
			ops->handle_lease_acquire(
				query, payload, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"lease acquire handler unavailable", 500);
		return;
	}

	if (route.kind == NEURO_UNIT_DISPATCH_ROUTE_LEASE_RELEASE) {
		neuro_unit_diag_dispatch_result(
			"cmd", key, metadata->request_id, "lease_release", 0);
		if (ops->handle_lease_release != NULL) {
			ops->handle_lease_release(
				query, payload, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"lease release handler unavailable", 500);
		return;
	}

	if (route.kind == NEURO_UNIT_DISPATCH_ROUTE_APP_ACTION) {
		neuro_unit_diag_dispatch_result(
			"cmd", key, metadata->request_id, "app_action", 0);
		if (ops->handle_app_action != NULL) {
			ops->handle_app_action(query, route.app_id,
				route.action, payload, metadata->request_id,
				metadata, request_fields);
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
	struct neuro_unit_dispatch_route route;
	uint32_t required_fields;

	if (!ops_are_valid(ops) || key == NULL || payload == NULL ||
		metadata == NULL) {
		reply_bad_dispatch_contract(query, metadata, ops);
		return;
	}

	LOG_DBG("state query: key=%s request_id=%s payload_len=%zu", key,
		metadata->request_id, strlen(payload));
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

	if (!neuro_unit_dispatch_classify_query_route(
		    key, ops->node_id, &route)) {
		neuro_unit_diag_dispatch_result(
			"query", key, metadata->request_id, "unsupported", 404);
		ops->reply_error(query, metadata->request_id,
			"unsupported query path", 404);
		return;
	}

	if (route.kind == NEURO_UNIT_DISPATCH_ROUTE_QUERY_DEVICE) {
		neuro_unit_diag_dispatch_result(
			"query", key, metadata->request_id, "device", 0);
		if (ops->handle_query_device != NULL) {
			ops->handle_query_device(query, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"query device handler unavailable", 500);
		return;
	}

	if (route.kind == NEURO_UNIT_DISPATCH_ROUTE_QUERY_APPS) {
		neuro_unit_diag_dispatch_result(
			"query", key, metadata->request_id, "apps", 0);
		if (ops->handle_query_apps != NULL) {
			ops->handle_query_apps(query, metadata->request_id);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"query apps handler unavailable", 500);
		return;
	}

	if (route.kind == NEURO_UNIT_DISPATCH_ROUTE_QUERY_LEASES) {
		neuro_unit_diag_dispatch_result(
			"query", key, metadata->request_id, "leases", 0);
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
	const struct neuro_unit_request_fields *request_fields,
	const struct neuro_unit_dispatch_ops *ops)
{
	struct neuro_unit_dispatch_route route;
	uint32_t required_fields;
	bool lifecycle_action;

	if (!ops_are_valid(ops) || key == NULL || payload == NULL ||
		metadata == NULL) {
		reply_bad_dispatch_contract(query, metadata, ops);
		return;
	}

	LOG_DBG("update query: key=%s request_id=%s payload_len=%zu", key,
		metadata->request_id, strlen(payload));
	if (!ops->transport_healthy()) {
		ops->log_transport_health_snapshot(
			"update_gate", key, metadata->request_id);
		ops->reply_error(query, metadata->request_id,
			"session transport unstable", 503);
		return;
	}

	if (!neuro_unit_dispatch_classify_update_route(
		    key, ops->node_id, &route)) {
		neuro_unit_diag_dispatch_result(
			"update", key, metadata->request_id, "invalid", 400);
		ops->reply_error(query, metadata->request_id,
			"invalid update path", 400);
		return;
	}

	required_fields =
		neuro_request_policy_required_fields_for_update_action(
			route.action);
	if (required_fields != 0U &&
		!ops->validate_request_metadata_or_reply(
			query, payload, metadata, required_fields)) {
		return;
	}

	lifecycle_action = strcmp(route.action, "prepare") == 0 ||
			   strcmp(route.action, "verify") == 0 ||
			   strcmp(route.action, "activate") == 0 ||
			   strcmp(route.action, "rollback") == 0 ||
			   strcmp(route.action, "recover") == 0;

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
		neuro_unit_diag_dispatch_result(
			"update", key, metadata->request_id, route.action, 0);
		if (ops->handle_update_action != NULL) {
			ops->handle_update_action(query, route.app_id,
				route.action, payload, metadata->request_id,
				metadata, request_fields);
			return;
		}
		ops->reply_error(query, metadata->request_id,
			"update command handler unavailable", 500);
		return;
	}

	neuro_unit_diag_dispatch_result(
		"update", key, metadata->request_id, "unsupported", 404);
	ops->reply_error(
		query, metadata->request_id, "unsupported update path", 404);
}
