/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_PROTOCOL_CODEC_H
#define NEURO_PROTOCOL_CODEC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct neuro_protocol_error_reply {
	const char *request_id;
	const char *node_id;
	int status_code;
	const char *message;
};

struct neuro_protocol_lease_reply {
	const char *request_id;
	const char *node_id;
	const char *lease_id;
	const char *resource;
	int64_t expires_at_ms;
	bool include_expires_at_ms;
};

struct neuro_protocol_query_device_reply {
	const char *request_id;
	const char *node_id;
	const char *board;
	const char *zenoh_mode;
	bool session_ready;
	const char *network_state;
	const char *ipv4;
};

struct neuro_protocol_callback_event {
	const char *app_id;
	const char *event_name;
	unsigned int invoke_count;
	int start_count;
};

struct neuro_protocol_app_command_reply {
	const char *command_name;
	unsigned int invoke_count;
	bool callback_enabled;
	int trigger_every;
	const char *event_name;
	bool config_changed;
	int publish_ret;
	const char *echo;
};

struct neuro_protocol_request_metadata {
	char request_id[32];
	char source_core[32];
	char source_agent[24];
	char target_node[32];
	char lease_id[32];
	char idempotency_key[32];
	uint32_t timeout_ms;
	int priority;
	bool forwarded;
};

struct neuro_protocol_callback_config {
	bool has_callback_enabled;
	bool callback_enabled;
	bool has_trigger_every;
	int trigger_every;
	bool has_event_name;
	char event_name[32];
};

int neuro_protocol_encode_error_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_error_reply *reply);
int neuro_protocol_encode_lease_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_lease_reply *reply);
int neuro_protocol_encode_query_device_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_query_device_reply *reply);
int neuro_protocol_encode_callback_event_json(char *json, size_t json_len,
	const struct neuro_protocol_callback_event *event);
int neuro_protocol_encode_app_command_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_app_command_reply *reply);
int neuro_protocol_decode_request_metadata_json(
	const char *json, struct neuro_protocol_request_metadata *metadata);
int neuro_protocol_decode_callback_config_json(
	const char *json, struct neuro_protocol_callback_config *config);

#ifdef __cplusplus
}
#endif

#endif
