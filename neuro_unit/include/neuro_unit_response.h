#ifndef NEURO_UNIT_RESPONSE_H
#define NEURO_UNIT_RESPONSE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "app_runtime.h"
#include "neuro_artifact_store.h"
#include "neuro_lease_manager.h"
#include "neuro_network_manager.h"
#include "neuro_request_envelope.h"
#include "neuro_update_manager.h"

#ifdef __cplusplus
extern "C" {
#endif

struct neuro_unit_query_app_snapshot {
	const char *app_id;
	enum app_runtime_state runtime_state;
	const char *path;
	unsigned int priority;
	bool manifest_present;
	const char *update_state;
	enum neuro_artifact_state artifact_state;
	const char *stable_ref;
	const char *last_error;
	const char *rollback_reason;
};

struct neuro_unit_query_apps_snapshot {
	size_t app_count;
	size_t running_count;
	size_t suspended_count;
	const struct neuro_unit_query_app_snapshot *apps;
	size_t app_snapshot_count;
};

void neuro_unit_parse_request_metadata(
	const char *payload, struct neuro_request_metadata *metadata);

bool neuro_unit_validate_request_metadata_payload(const char *payload,
	struct neuro_request_metadata *metadata, uint32_t required_fields,
	const char *expected_target_node, char *error_buf,
	size_t error_buf_len);

int neuro_unit_build_error_response(char *json, size_t json_len,
	const char *request_id, const char *node_id, int status_code,
	const char *message);

int neuro_unit_build_lease_acquire_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_lease_entry *lease);

int neuro_unit_build_lease_release_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_lease_entry *lease);

int neuro_unit_build_query_device_response(char *json, size_t json_len,
	const char *request_id, const char *node_id, const char *board,
	const char *zenoh_mode, bool session_ready,
	const struct neuro_network_status *network_status);

int neuro_unit_build_query_apps_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct app_runtime_status *status,
	const struct neuro_artifact_store *artifact_store,
	const struct neuro_update_manager *update_manager);

int neuro_unit_build_query_apps_snapshot_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_unit_query_apps_snapshot *snapshot);

int neuro_unit_build_query_leases_response(char *json, size_t json_len,
	const char *request_id, const char *node_id,
	const struct neuro_lease_entry *entries, size_t entry_count);

#ifdef __cplusplus
}
#endif

#endif
