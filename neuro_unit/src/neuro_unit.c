#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "app_runtime.h"
#include "app_runtime_cmd.h"
#include "app_runtime_exception.h"
#include "neuro_artifact_store.h"
#include "neuro_app_callback_bridge.h"
#include "neuro_app_command_registry.h"
#include "neuro_lease_manager.h"
#include "neuro_recovery_seed_store.h"
#include "neuro_unit.h"
#include "neuro_unit_diag.h"
#include "neuro_unit_dispatch.h"
#include "neuro_network_manager.h"
#include "neuro_request_envelope.h"
#include "neuro_request_policy.h"
#include "neuro_unit_response.h"
#include "neuro_unit_app_command.h"
#include "neuro_unit_event.h"
#include "neuro_unit_update_service.h"
#include "neuro_unit_zenoh.h"
#include "neuro_update_manager.h"

LOG_MODULE_REGISTER(neurolink_unit, LOG_LEVEL_INF);

#define NEURO_MAX_KEY_LEN 128
#define NEURO_MAX_JSON_LEN 1024
#define NEURO_MAX_FIELD_LEN 96
#define NEURO_DEFAULT_LEASE_TTL_MS 30000
#define NEURO_CONNECT_STACK_SIZE 6144
#define NEURO_CONNECT_THREAD_PRIO 8
#define NEURO_ARTIFACT_KEY_LEN 128
#define NEURO_APP_CMD_DEFAULT_TIMEOUT_MS 5000
#define NEURO_APP_CMD_DEFAULT_NAME "invoke"
#define NEUROLINK_NODE_ID CONFIG_NEUROLINK_NODE_ID
#define NEUROLINK_ZENOH_MODE CONFIG_NEUROLINK_ZENOH_MODE

static struct neuro_unit_zenoh_transport g_demo;
static struct neuro_lease_manager g_lease_manager;
static struct neuro_update_manager g_update_manager;
static struct neuro_artifact_store g_artifact_store;
static struct neuro_recovery_seed_store g_recovery_seed_store;
static struct neuro_unit_update_service g_update_service;
K_THREAD_STACK_DEFINE(g_neuro_connect_stack, NEURO_CONNECT_STACK_SIZE);
static struct k_thread g_neuro_connect_thread;

static void reply_error(const z_loaned_query_t *query, const char *request_id,
	const char *message, int status_code);
static void query_reply_json(const z_loaned_query_t *query, const char *json);
static void publish_state_event(void);
static void publish_update_event(const char *app_id, const char *stage,
	const char *status, const char *message);
static bool require_resource_lease_or_reply(const z_loaned_query_t *query,
	const char *request_id, const char *resource,
	const struct neuro_request_metadata *metadata);
static void reply_context_reply_error(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *message, int status_code);
static bool reply_context_require_resource_lease_or_reply(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *resource,
	const struct neuro_request_metadata *metadata);
static void reply_context_query_reply_json(
	const struct neuro_unit_reply_context *reply_ctx, const char *json);
static int ensure_recovery_seed_initialized(void);
static bool runtime_app_is_loaded(const char *app_id);
static void neuro_register_app_callback_command(const char *app_id);
static void log_update_transaction(const char *app_id, const char *action,
	const char *request_id, const char *phase, int code,
	const char *detail);

static const struct neuro_unit_app_command_ops g_app_command_ops = {
	.node_id = NEUROLINK_NODE_ID,
	.reply_error = reply_context_reply_error,
	.require_resource_lease_or_reply =
		reply_context_require_resource_lease_or_reply,
	.query_reply_json = reply_context_query_reply_json,
	.publish_state_event = publish_state_event,
};

static const struct neuro_unit_update_service_ctx g_update_service_ctx = {
	.update_manager = &g_update_manager,
	.artifact_store = &g_artifact_store,
	.recovery_seed_store = &g_recovery_seed_store,
};

static const struct neuro_unit_update_service_ops g_update_service_ops = {
	.node_id = NEUROLINK_NODE_ID,
	.reply_error = reply_context_reply_error,
	.require_resource_lease_or_reply =
		reply_context_require_resource_lease_or_reply,
	.query_reply_json = reply_context_query_reply_json,
	.publish_update_event = publish_update_event,
	.publish_state_event = publish_state_event,
	.runtime_app_is_loaded = runtime_app_is_loaded,
	.register_app_callback_command = neuro_register_app_callback_command,
	.log_transaction = log_update_transaction,
};

const char *neuro_unit_get_zenoh_connect(void)
{
	return neuro_unit_zenoh_get_connect(&g_demo);
}

int neuro_unit_set_zenoh_connect_override(const char *endpoint)
{
	return neuro_unit_zenoh_set_connect_override(&g_demo, endpoint);
}

int neuro_unit_clear_zenoh_connect_override(void)
{
	return neuro_unit_zenoh_clear_connect_override(&g_demo);
}

static void neuro_register_app_callback_command(const char *app_id)
{
	struct neuro_app_command_desc desc;
	int ret;

	if (!app_runtime_supports_command_callback(app_id)) {
		return;
	}

	memset(&desc, 0, sizeof(desc));
	snprintk(desc.app_id, sizeof(desc.app_id), "%s", app_id);
	snprintk(desc.command_name, sizeof(desc.command_name), "%s",
		NEURO_APP_CMD_DEFAULT_NAME);
	desc.visibility = 1U;
	desc.lease_required = true;
	desc.idempotent = false;
	desc.timeout_ms = NEURO_APP_CMD_DEFAULT_TIMEOUT_MS;
	desc.state = NEURO_APPCMD_STATE_REGISTERING;

	ret = neuro_app_command_registry_register(&desc);
	if (ret) {
		LOG_ERR("app command register failed: app=%s cmd=%s ret=%d",
			app_id, desc.command_name, ret);
		return;
	}

	ret = neuro_app_command_registry_set_app_enabled(app_id, true);
	if (ret) {
		LOG_ERR("app command enable failed: app=%s ret=%d", app_id,
			ret);
	}
}

static bool json_extract_string(
	const char *json, const char *key, char *out, size_t out_len)
{
	return neuro_json_extract_string(json, key, out, out_len);
}

static int json_extract_int(
	const char *json, const char *key, int default_value)
{
	return neuro_json_extract_int(json, key, default_value);
}

static bool validate_request_metadata_or_reply(const z_loaned_query_t *query,
	const char *payload, struct neuro_request_metadata *metadata,
	uint32_t required_fields)
{
	char error[96];

	if (!neuro_unit_validate_request_metadata_payload(payload, metadata,
		    required_fields, NEUROLINK_NODE_ID, error, sizeof(error))) {
		reply_error(query, metadata->request_id, error, 400);
		return false;
	}

	return true;
}

static void reply_error(const z_loaned_query_t *query, const char *request_id,
	const char *message, int status_code)
{
	char json[256];
	int ret;

	LOG_WRN("%s: request_id=%s status_code=%d message=%s", __func__,
		request_id ? request_id : "", status_code,
		message ? message : "error");
	ret = neuro_unit_build_error_response(json, sizeof(json), request_id,
		NEUROLINK_NODE_ID, status_code, message);
	if (ret != 0) {
		snprintk(json, sizeof(json),
			"{\"status\":\"error\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"status_code\":500,\"message\":\"error response encode failed\"}",
			request_id ? request_id : "", NEUROLINK_NODE_ID);
	}
	query_reply_json(query, json);
}

static void query_reply_json(const z_loaned_query_t *query, const char *json)
{
	neuro_unit_zenoh_query_reply_json(&g_demo, query, json);
}

static bool zenoh_transport_healthy(void)
{
	return neuro_unit_zenoh_transport_healthy(&g_demo);
}

static void log_transport_health_snapshot(
	const char *tag, const char *key, const char *request_id)
{
	neuro_unit_zenoh_log_transport_health_snapshot(
		&g_demo, tag, key, request_id);
}

static int neuro_unit_publish_event_json(
	const char *keyexpr, const char *json, void *ctx)
{
	return neuro_unit_zenoh_publish_event_json(keyexpr, json, ctx);
}

static void publish_state_event(void)
{
	char key[NEURO_UNIT_EVENT_KEY_LEN];
	char json[NEURO_UNIT_EVENT_JSON_LEN];
	struct app_runtime_status status;
	struct neuro_network_status network_status;

	memset(&status, 0, sizeof(status));
	(void)neuro_network_manager_collect_status(
		neuro_unit_get_zenoh_connect(), &network_status);
	app_runtime_get_status(&status);
	if (neuro_unit_event_build_key(
		    key, sizeof(key), NEUROLINK_NODE_ID, "state") != 0) {
		return;
	}
	snprintk(json, sizeof(json),
		"{\"node_id\":\"%s\",\"apps\":%u,\"running\":%u,\"network_state\":\"%s\"}",
		NEUROLINK_NODE_ID, (unsigned int)status.app_count,
		(unsigned int)status.running_count,
		neuro_network_state_to_str(network_status.state));
	(void)neuro_unit_event_publish(key, json);
}

static void publish_update_event(const char *app_id, const char *stage,
	const char *status, const char *message)
{
	char key[NEURO_UNIT_EVENT_KEY_LEN];
	char json[NEURO_UNIT_EVENT_JSON_LEN];

	if (neuro_unit_event_build_key(
		    key, sizeof(key), NEUROLINK_NODE_ID, "update") != 0) {
		return;
	}
	snprintk(json, sizeof(json),
		"{\"node_id\":\"%s\",\"app_id\":\"%s\",\"stage\":\"%s\",\"status\":\"%s\",\"message\":\"%s\"}",
		NEUROLINK_NODE_ID, app_id, stage, status,
		message ? message : "-");
	(void)neuro_unit_event_publish(key, json);
}

static void log_update_transaction(const char *app_id, const char *action,
	const char *request_id, const char *phase, int code, const char *detail)
{
	neuro_unit_diag_update_transaction(
		app_id, action, request_id, phase, code, detail);
}

static int ensure_recovery_seed_initialized(void)
{
	return neuro_unit_update_service_ensure_recovery_seed_initialized(
		&g_update_service);
}

static bool runtime_app_is_loaded(const char *app_id)
{
	struct app_runtime_status status;
	size_t listed_count;
	size_t i;

	if (app_id == NULL || app_id[0] == '\0') {
		return false;
	}

	memset(&status, 0, sizeof(status));
	app_runtime_get_status(&status);
	listed_count = app_runtime_status_listed_count(&status);
	if (listed_count > ARRAY_SIZE(status.apps)) {
		listed_count = ARRAY_SIZE(status.apps);
	}

	for (i = 0; i < listed_count; i++) {
		if (strcmp(status.apps[i].name, app_id) == 0) {
			return true;
		}
	}

	return false;
}

static void publish_lease_event(
	const struct neuro_lease_entry *lease, const char *action)
{
	char key[NEURO_UNIT_EVENT_KEY_LEN];
	char suffix[64];
	char json[NEURO_UNIT_EVENT_JSON_LEN];

	snprintk(suffix, sizeof(suffix), "lease/%s", lease->lease_id);
	if (neuro_unit_event_build_key(
		    key, sizeof(key), NEUROLINK_NODE_ID, suffix) != 0) {
		return;
	}
	snprintk(json, sizeof(json),
		"{\"node_id\":\"%s\",\"action\":\"%s\",\"lease_id\":\"%s\",\"resource\":\"%s\",\"source_core\":\"%s\",\"source_agent\":\"%s\",\"priority\":%d}",
		NEUROLINK_NODE_ID, action, lease->lease_id, lease->resource,
		lease->source_core, lease->source_agent, lease->priority);
	(void)neuro_unit_event_publish(key, json);
}

static bool require_resource_lease_or_reply(const z_loaned_query_t *query,
	const char *request_id, const char *resource,
	const struct neuro_request_metadata *metadata)
{
	int ret;

	k_mutex_lock(&g_demo.lock, K_FOREVER);
	ret = neuro_lease_manager_require_resource(
		&g_lease_manager, resource, metadata, k_uptime_get());
	k_mutex_unlock(&g_demo.lock);

	if (ret == -EPERM) {
		reply_error(query, request_id, "lease not held", 403);
		return false;
	}

	if (ret == -EACCES) {
		reply_error(query, request_id, "lease holder mismatch", 403);
		return false;
	}

	if (ret) {
		reply_error(query, request_id, "lease check failed", 500);
		return false;
	}

	return true;
}

static const z_loaned_query_t *query_from_reply_context(
	const struct neuro_unit_reply_context *reply_ctx)
{
	return reply_ctx != NULL
		       ? (const z_loaned_query_t *)reply_ctx->transport_query
		       : NULL;
}

static void reply_context_reply_error(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *message, int status_code)
{
	reply_error(query_from_reply_context(reply_ctx), request_id, message,
		status_code);
}

static bool reply_context_require_resource_lease_or_reply(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *resource,
	const struct neuro_request_metadata *metadata)
{
	return require_resource_lease_or_reply(
		query_from_reply_context(reply_ctx), request_id, resource,
		metadata);
}

static void reply_context_query_reply_json(
	const struct neuro_unit_reply_context *reply_ctx, const char *json)
{
	query_reply_json(query_from_reply_context(reply_ctx), json);
}

static void handle_lease_acquire(const z_loaned_query_t *query,
	const char *payload, const char *request_id)
{
	struct neuro_request_metadata metadata;
	struct neuro_lease_acquire_result result;
	char resource[48] = "";
	char json[384];
	int ttl_ms;
	int64_t now_ms;
	int ret;

	neuro_unit_parse_request_metadata(payload, &metadata);
	(void)json_extract_string(
		payload, "resource", resource, sizeof(resource));
	if (resource[0] == '\0') {
		reply_error(query, request_id, "resource missing", 400);
		return;
	}

	ttl_ms =
		json_extract_int(payload, "ttl_ms", NEURO_DEFAULT_LEASE_TTL_MS);
	if (ttl_ms <= 0) {
		ttl_ms = NEURO_DEFAULT_LEASE_TTL_MS;
	}

	now_ms = k_uptime_get();
	k_mutex_lock(&g_demo.lock, K_FOREVER);
	neuro_lease_manager_prune_expired(&g_lease_manager, now_ms);
	ret = neuro_lease_manager_acquire(
		&g_lease_manager, resource, &metadata, ttl_ms, now_ms, &result);
	k_mutex_unlock(&g_demo.lock);
	if (ret == -EACCES) {
		reply_error(query, request_id, "lease holder mismatch", 403);
		return;
	}

	if (ret == -EEXIST) {
		reply_error(query, request_id, "lease conflict", 409);
		return;
	}

	if (ret == -ENOSPC) {
		reply_error(query, request_id, "lease table full", 409);
		return;
	}

	if (ret) {
		reply_error(query, request_id, "lease acquire failed", 500);
		return;
	}

	if (result.preempted) {
		publish_lease_event(&result.preempted_entry, "preempted");
	}
	publish_lease_event(&result.acquired, "acquired");
	if (neuro_unit_build_lease_acquire_response(json, sizeof(json),
		    request_id, NEUROLINK_NODE_ID, &result.acquired) != 0) {
		reply_error(query, request_id,
			"lease acquire reply build failed", 500);
		return;
	}
	query_reply_json(query, json);
}

static void handle_lease_release(const z_loaned_query_t *query,
	const char *payload, const char *request_id)
{
	struct neuro_request_metadata metadata;
	struct neuro_lease_entry released;
	char json[320];
	int ret;

	neuro_unit_parse_request_metadata(payload, &metadata);
	k_mutex_lock(&g_demo.lock, K_FOREVER);
	ret = neuro_lease_manager_release(
		&g_lease_manager, &metadata, k_uptime_get(), &released);
	k_mutex_unlock(&g_demo.lock);
	if (ret == -ENOENT) {
		reply_error(query, request_id, "lease not found", 404);
		return;
	}

	if (ret == -EACCES) {
		reply_error(query, request_id, "lease holder mismatch", 403);
		return;
	}

	if (ret) {
		reply_error(query, request_id, "lease release failed", 500);
		return;
	}

	publish_lease_event(&released, "released");
	if (neuro_unit_build_lease_release_response(json, sizeof(json),
		    request_id, NEUROLINK_NODE_ID, &released) != 0) {
		reply_error(query, request_id,
			"lease release reply build failed", 500);
		return;
	}
	query_reply_json(query, json);
}

static void handle_app_action(const z_loaned_query_t *query, const char *app_id,
	const char *action, const char *payload, const char *request_id)
{
	const struct neuro_unit_reply_context reply_ctx = {
		.transport_query = query,
	};

	neuro_unit_handle_app_command(&reply_ctx, app_id, action, payload,
		request_id, &g_app_command_ops);
}

static void handle_update_action(const z_loaned_query_t *query,
	const char *app_id, const char *action, const char *payload,
	const char *request_id)
{
	const struct neuro_unit_reply_context reply_ctx = {
		.transport_query = query,
	};

	neuro_unit_update_service_handle_action(&g_update_service, &reply_ctx,
		app_id, action, payload, request_id);
}

static void handle_query_device(
	const z_loaned_query_t *query, const char *request_id)
{
	char json[256];
	struct neuro_network_status network_status;

	(void)neuro_network_manager_collect_status(
		neuro_unit_get_zenoh_connect(), &network_status);
	if (neuro_unit_build_query_device_response(json, sizeof(json),
		    request_id, NEUROLINK_NODE_ID, CONFIG_BOARD,
		    NEUROLINK_ZENOH_MODE, g_demo.session_ready,
		    &network_status) != 0) {
		reply_error(query, request_id,
			"query device reply build failed", 500);
		return;
	}
	query_reply_json(query, json);
}

static void handle_query_apps(
	const z_loaned_query_t *query, const char *request_id)
{
	char json[NEURO_MAX_JSON_LEN];
	struct app_runtime_status status;

	memset(&status, 0, sizeof(status));
	app_runtime_get_status(&status);
	if (neuro_unit_build_query_apps_response(json, sizeof(json), request_id,
		    NEUROLINK_NODE_ID, &status, &g_artifact_store,
		    &g_update_manager) != 0) {
		reply_error(query, request_id, "query apps reply build failed",
			500);
		return;
	}
	query_reply_json(query, json);
}

static void handle_query_leases(
	const z_loaned_query_t *query, const char *request_id)
{
	char json[NEURO_MAX_JSON_LEN];
	struct neuro_lease_entry entries[NEURO_LEASE_MANAGER_MAX_ENTRIES];
	size_t entry_count = 0U;
	size_t i;

	k_mutex_lock(&g_demo.lock, K_FOREVER);
	neuro_lease_manager_prune_expired(&g_lease_manager, k_uptime_get());
	for (i = 0; i < NEURO_LEASE_MANAGER_MAX_ENTRIES; i++) {
		const struct neuro_lease_entry *entry =
			neuro_lease_manager_entry_at(&g_lease_manager, i);

		if (entry != NULL && entry->active) {
			entries[entry_count++] = *entry;
		}
	}
	k_mutex_unlock(&g_demo.lock);
	if (neuro_unit_build_query_leases_response(json, sizeof(json),
		    request_id, NEUROLINK_NODE_ID, entries, entry_count) != 0) {
		reply_error(query, request_id,
			"query leases reply build failed", 500);
		return;
	}
	query_reply_json(query, json);
}

static const struct neuro_unit_dispatch_ops g_dispatch_ops = {
	.node_id = NEUROLINK_NODE_ID,
	.transport_healthy = zenoh_transport_healthy,
	.log_transport_health_snapshot = log_transport_health_snapshot,
	.validate_request_metadata_or_reply =
		validate_request_metadata_or_reply,
	.ensure_recovery_seed_initialized = ensure_recovery_seed_initialized,
	.reply_error = reply_error,
	.handle_lease_acquire = handle_lease_acquire,
	.handle_lease_release = handle_lease_release,
	.handle_app_action = handle_app_action,
	.handle_query_device = handle_query_device,
	.handle_query_apps = handle_query_apps,
	.handle_query_leases = handle_query_leases,
	.handle_update_action = handle_update_action,
};

static void command_query_handler(z_loaned_query_t *query, void *ctx)
{
	char key[NEURO_MAX_KEY_LEN];
	char payload[NEURO_MAX_JSON_LEN];
	struct neuro_request_metadata metadata;

	ARG_UNUSED(ctx);
	neuro_unit_zenoh_query_key_to_cstr(query, key, sizeof(key));
	neuro_unit_zenoh_query_payload_to_cstr(query, payload, sizeof(payload));
	neuro_unit_parse_request_metadata(payload, &metadata);
	neuro_unit_dispatch_command_query(
		query, key, payload, &metadata, &g_dispatch_ops);
}

static void query_query_handler(z_loaned_query_t *query, void *ctx)
{
	char key[NEURO_MAX_KEY_LEN];
	char payload[NEURO_MAX_JSON_LEN];
	struct neuro_request_metadata metadata;

	ARG_UNUSED(ctx);
	neuro_unit_zenoh_query_key_to_cstr(query, key, sizeof(key));
	neuro_unit_zenoh_query_payload_to_cstr(query, payload, sizeof(payload));
	neuro_unit_parse_request_metadata(payload, &metadata);
	neuro_unit_dispatch_query_query(
		query, key, payload, &metadata, &g_dispatch_ops);
}

static void update_query_handler(z_loaned_query_t *query, void *ctx)
{
	char key[NEURO_MAX_KEY_LEN];
	char payload[NEURO_MAX_JSON_LEN];
	struct neuro_request_metadata metadata;

	ARG_UNUSED(ctx);
	neuro_unit_zenoh_query_key_to_cstr(query, key, sizeof(key));
	neuro_unit_zenoh_query_payload_to_cstr(query, payload, sizeof(payload));
	neuro_unit_parse_request_metadata(payload, &metadata);
	neuro_unit_dispatch_update_query(
		query, key, payload, &metadata, &g_dispatch_ops);
}

static const struct neuro_unit_zenoh_handlers g_zenoh_handlers = {
	.command_query_handler = command_query_handler,
	.query_query_handler = query_query_handler,
	.update_query_handler = update_query_handler,
	.publish_state_event = publish_state_event,
	.publish_update_event = publish_update_event,
};

int neuro_unit_start(void)
{
	int ret;
	const char *connect;

	neuro_unit_zenoh_init(&g_demo, &g_zenoh_handlers);
	connect = neuro_unit_get_zenoh_connect();
	neuro_unit_event_reset();
	ret = neuro_unit_event_configure(
		NEUROLINK_NODE_ID, neuro_unit_publish_event_json, &g_demo);
	if (ret) {
		LOG_ERR("unit event module init failed: %d", ret);
		return ret;
	}
	neuro_lease_manager_init(&g_lease_manager);
	neuro_update_manager_init(&g_update_manager);
	neuro_artifact_store_init(&g_artifact_store);
	{
		const struct app_runtime_cmd_config *rt_cfg =
			app_runtime_cmd_get_config();
		const char *seed_p =
			(rt_cfg->seed_path && rt_cfg->seed_path[0] != '\0')
				? rt_cfg->seed_path
				: NEURO_RECOVERY_SEED_PATH_DEFAULT;

		neuro_recovery_seed_store_init(&g_recovery_seed_store, seed_p);
	}
	ret = neuro_unit_update_service_init(&g_update_service,
		&g_update_service_ctx, &g_update_service_ops);
	if (ret) {
		LOG_ERR("update service init failed: %d", ret);
		return ret;
	}

	ret = neuro_app_command_registry_init();
	if (ret) {
		LOG_ERR("app command registry init failed: %d", ret);
		return ret;
	}

	LOG_INF("recovery seed init deferred until SD mount is available");

	k_thread_create(&g_neuro_connect_thread, g_neuro_connect_stack,
		K_THREAD_STACK_SIZEOF(g_neuro_connect_stack),
		neuro_unit_zenoh_connect_thread, &g_demo, NULL, NULL,
		NEURO_CONNECT_THREAD_PRIO, 0, K_NO_WAIT);
	k_thread_name_set(&g_neuro_connect_thread, "neuro_zenoh");
	LOG_INF("NeuroLink zenoh bootstrap started; mode=%s connect=%s node=%s",
		NEUROLINK_ZENOH_MODE,
		strlen(connect) > 0U ? connect : "<scouting>",
		NEUROLINK_NODE_ID);
	return 0;
}
