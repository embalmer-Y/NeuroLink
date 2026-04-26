#include "neuro_unit_response.h"

#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stdarg.h>
#include <string.h>

#include "neuro_protocol_codec.h"

#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_MODE) &&                               \
	CONFIG_NEUROLINK_UNIT_DEBUG_MODE
#define NEURO_UNIT_RESPONSE_LOG_LEVEL LOG_LEVEL_DBG
#else
#define NEURO_UNIT_RESPONSE_LOG_LEVEL LOG_LEVEL_INF
#endif

LOG_MODULE_REGISTER(neuro_unit_response, NEURO_UNIT_RESPONSE_LOG_LEVEL);

static const char *safe_str(const char *value)
{
	if (value == NULL) {
		return "";
	}

	return value;
}

static void json_append(
	char *buf, size_t buf_len, size_t *pos, const char *fmt, ...)
{
	va_list args;
	int written;

	if (buf == NULL || pos == NULL || *pos >= buf_len) {
		return;
	}

	va_start(args, fmt);
	written = vsnprintk(buf + *pos, buf_len - *pos, fmt, args);
	va_end(args);
	if (written < 0) {
		*pos = buf_len;
		return;
	}

	if ((size_t)written >= buf_len - *pos) {
		*pos = buf_len - 1U;
		return;
	}

	*pos += (size_t)written;
}

static const char *app_runtime_state_to_str(enum app_runtime_state state)
{
	switch (state) {
	case APP_RT_UNLOADED:
		return "UNLOADED";
	case APP_RT_LOADED:
		return "LOADED";
	case APP_RT_INITIALIZED:
		return "INITIALIZED";
	case APP_RT_RUNNING:
		return "RUNNING";
	case APP_RT_SUSPENDED:
		return "SUSPENDED";
	default:
		return "UNKNOWN";
	}
}

static const char *artifact_state_to_str(enum neuro_artifact_state state)
{
	switch (state) {
	case NEURO_ARTIFACT_NONE:
		return "NONE";
	case NEURO_ARTIFACT_STAGED:
		return "STAGED";
	case NEURO_ARTIFACT_VERIFIED:
		return "VERIFIED";
	case NEURO_ARTIFACT_ACTIVE:
		return "ACTIVE";
	case NEURO_ARTIFACT_INVALID:
		return "INVALID";
	default:
		return "UNKNOWN";
	}
}

static const char *network_state_to_str(enum neuro_network_state state)
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

void neuro_unit_parse_request_metadata(
	const char *payload, struct neuro_request_metadata *metadata)
{
	neuro_request_metadata_init(metadata);
	(void)neuro_request_metadata_parse(payload, metadata);
}

bool neuro_unit_validate_request_metadata_payload(const char *payload,
	struct neuro_request_metadata *metadata, uint32_t required_fields,
	const char *expected_target_node, char *error_buf, size_t error_buf_len)
{
	if (metadata == NULL) {
		if (error_buf != NULL && error_buf_len > 0U) {
			snprintk(error_buf, error_buf_len, "metadata missing");
		}
		return false;
	}

	neuro_unit_parse_request_metadata(payload, metadata);
	return neuro_request_metadata_validate(metadata, required_fields,
		expected_target_node, error_buf, error_buf_len);
}

int neuro_unit_build_error_response(char *json, size_t json_len,
	const char *request_id, const char *node_id, int status_code,
	const char *message)
{
	const struct neuro_protocol_error_reply reply = {
		.request_id = request_id,
		.node_id = node_id,
		.status_code = status_code,
		.message = message,
	};

	if (json == NULL || json_len == 0U) {
		return -EINVAL;
	}

	return neuro_protocol_encode_error_reply_json(json, json_len, &reply);
}

int neuro_unit_build_lease_acquire_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_lease_entry *lease)
{
	struct neuro_protocol_lease_reply reply;

	if (json == NULL || json_len == 0U || lease == NULL) {
		return -EINVAL;
	}

	reply.request_id = request_id;
	reply.node_id = node_id;
	reply.lease_id = lease->lease_id;
	reply.resource = lease->resource;
	reply.expires_at_ms = lease->expires_at_ms;
	reply.include_expires_at_ms = true;

	return neuro_protocol_encode_lease_reply_json(json, json_len, &reply);
}

int neuro_unit_build_lease_release_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_lease_entry *lease)
{
	struct neuro_protocol_lease_reply reply;

	if (json == NULL || json_len == 0U || lease == NULL) {
		return -EINVAL;
	}

	reply.request_id = request_id;
	reply.node_id = node_id;
	reply.lease_id = lease->lease_id;
	reply.resource = lease->resource;
	reply.expires_at_ms = 0;
	reply.include_expires_at_ms = false;

	return neuro_protocol_encode_lease_reply_json(json, json_len, &reply);
}

int neuro_unit_build_query_device_response(char *json, size_t json_len,
	const char *request_id, const char *node_id, const char *board,
	const char *zenoh_mode, bool session_ready,
	const struct neuro_network_status *network_status)
{
	struct neuro_protocol_query_device_reply reply;

	if (json == NULL || json_len == 0U || network_status == NULL) {
		return -EINVAL;
	}

	reply.request_id = request_id;
	reply.node_id = node_id;
	reply.board = board;
	reply.zenoh_mode = zenoh_mode;
	reply.session_ready = session_ready;
	reply.network_state = network_state_to_str(network_status->state);
	reply.ipv4 = network_status->ipv4_addr;

	return neuro_protocol_encode_query_device_reply_json(
		json, json_len, &reply);
}

int neuro_unit_build_query_apps_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct app_runtime_status *status,
	const struct neuro_artifact_store *artifact_store,
	const struct neuro_update_manager *update_manager)
{
	struct neuro_unit_query_app_snapshot
		app_snapshots[APP_RT_STATUS_SNAPSHOT_CAPACITY];
	struct neuro_unit_query_apps_snapshot snapshot;
	size_t listed_count;
	size_t i;

	if (json == NULL || json_len == 0U || status == NULL ||
		artifact_store == NULL || update_manager == NULL) {
		return -EINVAL;
	}

	listed_count = app_runtime_status_listed_count(status);
	if (listed_count > ARRAY_SIZE(status->apps)) {
		listed_count = ARRAY_SIZE(status->apps);
	}

	for (i = 0; i < listed_count; i++) {
		const struct neuro_artifact_meta *artifact;

		artifact = neuro_artifact_store_get(
			artifact_store, status->apps[i].name);
		app_snapshots[i].app_id = status->apps[i].name;
		app_snapshots[i].runtime_state = status->apps[i].state;
		app_snapshots[i].path = status->apps[i].path;
		app_snapshots[i].priority = status->apps[i].priority;
		app_snapshots[i].manifest_present =
			status->apps[i].manifest_present;
		app_snapshots[i].update_state =
			neuro_update_manager_state_to_str(
				neuro_update_manager_state_for(
					update_manager, status->apps[i].name));
		app_snapshots[i].artifact_state = artifact != NULL
							  ? artifact->state
							  : NEURO_ARTIFACT_NONE;
		app_snapshots[i].stable_ref =
			neuro_update_manager_stable_ref_for(
				update_manager, status->apps[i].name);
		app_snapshots[i].last_error =
			neuro_update_manager_last_error_for(
				update_manager, status->apps[i].name);
		app_snapshots[i].rollback_reason =
			neuro_update_manager_rollback_reason_for(
				update_manager, status->apps[i].name);
	}

	snapshot.app_count = status->app_count;
	snapshot.running_count = status->running_count;
	snapshot.suspended_count = status->suspended_count;
	snapshot.apps = app_snapshots;
	snapshot.app_snapshot_count = listed_count;

	return neuro_unit_build_query_apps_snapshot_response(
		json, json_len, request_id, node_id, &snapshot);
}

int neuro_unit_build_query_apps_snapshot_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_unit_query_apps_snapshot *snapshot)
{
	size_t pos = 0U;
	size_t i;

	if (json == NULL || json_len == 0U || snapshot == NULL ||
		(snapshot->apps == NULL && snapshot->app_snapshot_count > 0U)) {
		return -EINVAL;
	}

	json_append(json, json_len, &pos,
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_count\":%u,\"running_count\":%u,\"suspended_count\":%u,\"apps\":[",
		safe_str(request_id), safe_str(node_id),
		(unsigned int)snapshot->app_count,
		(unsigned int)snapshot->running_count,
		(unsigned int)snapshot->suspended_count);
	for (i = 0; i < snapshot->app_snapshot_count; i++) {
		const struct neuro_unit_query_app_snapshot *app =
			&snapshot->apps[i];

		if (i > 0U) {
			json_append(json, json_len, &pos, ",");
		}
		json_append(json, json_len, &pos,
			"{\"app_id\":\"%s\",\"state\":\"%s\",\"path\":\"%s\",\"priority\":%u,\"manifest_present\":%s,\"update_state\":\"%s\",\"artifact_state\":\"%s\",\"stable_ref\":\"%s\",\"last_error\":\"%s\",\"rollback_reason\":\"%s\"}",
			safe_str(app->app_id),
			app_runtime_state_to_str(app->runtime_state),
			safe_str(app->path), app->priority,
			app->manifest_present ? "true" : "false",
			app->update_state != NULL ? app->update_state : "NONE",
			artifact_state_to_str(app->artifact_state),
			safe_str(app->stable_ref), safe_str(app->last_error),
			safe_str(app->rollback_reason));
	}
	json_append(json, json_len, &pos, "]}");

	if (pos >= json_len - 1U) {
		return -ENAMETOOLONG;
	}

	return 0;
}

int neuro_unit_build_query_leases_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_lease_entry *entries, size_t entry_count)
{
	size_t pos = 0U;
	size_t i;

	if (json == NULL || json_len == 0U ||
		(entries == NULL && entry_count > 0U)) {
		return -EINVAL;
	}

	json_append(json, json_len, &pos,
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"leases\":[",
		safe_str(request_id), safe_str(node_id));
	for (i = 0; i < entry_count; i++) {
		if (i > 0U) {
			json_append(json, json_len, &pos, ",");
		}
		json_append(json, json_len, &pos,
			"{\"lease_id\":\"%s\",\"resource\":\"%s\",\"source_core\":\"%s\",\"source_agent\":\"%s\",\"priority\":%d,\"expires_at_ms\":%lld}",
			entries[i].lease_id, entries[i].resource,
			entries[i].source_core, entries[i].source_agent,
			entries[i].priority,
			(long long)entries[i].expires_at_ms);
	}
	json_append(json, json_len, &pos, "]}");

	if (pos >= json_len - 1U) {
		return -ENAMETOOLONG;
	}

	return 0;
}
