/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_PROTOCOL_CODEC_CBOR_H
#define NEURO_PROTOCOL_CODEC_CBOR_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "neuro_protocol.h"
#include "neuro_protocol_codec.h"

#ifdef __cplusplus
extern "C" {
#endif

struct neuro_protocol_cbor_envelope {
	uint32_t schema_version;
	enum neuro_protocol_cbor_message_kind message_kind;
};

struct neuro_protocol_query_app_cbor {
	const char *app_id;
	const char *runtime_state;
	const char *path;
	uint32_t priority;
	bool manifest_present;
	const char *update_state;
	const char *artifact_state;
	const char *stable_ref;
	const char *last_error;
	const char *rollback_reason;
};

struct neuro_protocol_query_apps_reply_cbor {
	const char *request_id;
	const char *node_id;
	uint32_t app_count;
	uint32_t running_count;
	uint32_t suspended_count;
	const struct neuro_protocol_query_app_cbor *apps;
	size_t app_count_listed;
};

struct neuro_protocol_query_lease_cbor {
	const char *lease_id;
	const char *resource;
	const char *source_core;
	const char *source_agent;
	int32_t priority;
	int64_t expires_at_ms;
};

struct neuro_protocol_query_leases_reply_cbor {
	const char *request_id;
	const char *node_id;
	const struct neuro_protocol_query_lease_cbor *leases;
	size_t lease_count;
};

struct neuro_protocol_update_prepare_request_cbor {
	char transport[32];
	char artifact_key[96];
	uint32_t size;
	uint32_t chunk_size;
};

struct neuro_protocol_request_fields_cbor {
	char resource[64];
	char args_json[256];
	uint32_t ttl_ms;
	char start_args[96];
	char reason[64];
	char transport[32];
	char artifact_key[96];
	uint32_t size;
	uint32_t chunk_size;
	bool has_callback_enabled;
	bool callback_enabled;
	bool has_trigger_every;
	int32_t trigger_every;
	bool has_event_name;
	char event_name[32];
};

struct neuro_protocol_update_reply_cbor {
	const char *request_id;
	const char *node_id;
	const char *app_id;
	const char *path;
	const char *transport;
	uint32_t size;
	const char *reason;
};

struct neuro_protocol_update_event_cbor {
	const char *node_id;
	const char *app_id;
	const char *stage;
	const char *status;
	const char *detail;
};

struct neuro_protocol_state_event_cbor {
	const char *node_id;
	uint32_t app_count;
	uint32_t running_count;
	const char *network_state;
};

struct neuro_protocol_lease_event_cbor {
	const char *node_id;
	const char *action;
	const char *lease_id;
	const char *resource;
	const char *source_core;
	const char *source_agent;
	int32_t priority;
};

bool neuro_protocol_cbor_message_kind_is_valid(uint32_t message_kind);
int neuro_protocol_cbor_encode_envelope_header(uint8_t *payload,
	size_t payload_len, enum neuro_protocol_cbor_message_kind message_kind,
	size_t *encoded_len);
int neuro_protocol_cbor_decode_envelope_header(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_cbor_envelope *envelope);
int neuro_protocol_encode_error_reply_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_error_reply *reply, size_t *encoded_len);
int neuro_protocol_encode_lease_reply_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_lease_reply *reply, size_t *encoded_len);
int neuro_protocol_encode_query_device_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_query_device_reply *reply,
	size_t *encoded_len);
int neuro_protocol_encode_callback_event_cbor(uint8_t *payload,
	size_t payload_len, const struct neuro_protocol_callback_event *event,
	size_t *encoded_len);
int neuro_protocol_encode_app_command_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_app_command_reply *reply,
	size_t *encoded_len);
int neuro_protocol_decode_request_metadata_cbor(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_request_metadata *metadata,
	enum neuro_protocol_cbor_message_kind *message_kind);
int neuro_protocol_decode_callback_config_cbor(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_callback_config *config);
int neuro_protocol_decode_update_prepare_request_cbor(const uint8_t *payload,
	size_t payload_len,
	struct neuro_protocol_update_prepare_request_cbor *request);
int neuro_protocol_decode_request_fields_cbor(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_request_fields_cbor *fields);
int neuro_protocol_encode_query_apps_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_query_apps_reply_cbor *reply,
	size_t *encoded_len);
int neuro_protocol_encode_query_leases_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_query_leases_reply_cbor *reply,
	size_t *encoded_len);
int neuro_protocol_encode_update_prepare_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len);
int neuro_protocol_encode_update_verify_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len);
int neuro_protocol_encode_update_activate_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len);
int neuro_protocol_encode_update_rollback_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len);
int neuro_protocol_encode_update_event_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_event_cbor *event,
	size_t *encoded_len);
int neuro_protocol_encode_state_event_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_state_event_cbor *event,
	size_t *encoded_len);
int neuro_protocol_encode_lease_event_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_lease_event_cbor *event,
	size_t *encoded_len);

#ifdef __cplusplus
}
#endif

#endif
