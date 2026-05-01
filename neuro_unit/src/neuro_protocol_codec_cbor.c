#include "neuro_protocol_codec_cbor.h"

#include <errno.h>
#include <string.h>

#include <zcbor_decode.h>
#include <zcbor_encode.h>

static const char *safe_str(const char *value)
{
	if (value == NULL) {
		return "";
	}

	return value;
}

static int cbor_finish_encode(
	uint8_t *payload, zcbor_state_t *state, bool ok, size_t *encoded_len)
{
	if (!ok) {
		return -ENAMETOOLONG;
	}

	*encoded_len = (size_t)(state->payload - payload);
	return 0;
}

static bool cbor_put_key_u32(
	zcbor_state_t *state, enum neuro_protocol_cbor_key key, uint32_t value)
{
	return zcbor_uint32_put(state, key) && zcbor_uint32_put(state, value);
}

static bool cbor_put_key_i32(
	zcbor_state_t *state, enum neuro_protocol_cbor_key key, int32_t value)
{
	return zcbor_uint32_put(state, key) && zcbor_int32_put(state, value);
}

static bool cbor_put_key_i64(
	zcbor_state_t *state, enum neuro_protocol_cbor_key key, int64_t value)
{
	return zcbor_uint32_put(state, key) && zcbor_int64_put(state, value);
}

static bool cbor_put_key_bool(
	zcbor_state_t *state, enum neuro_protocol_cbor_key key, bool value)
{
	return zcbor_uint32_put(state, key) && zcbor_bool_put(state, value);
}

static bool cbor_put_key_tstr(zcbor_state_t *state,
	enum neuro_protocol_cbor_key key, const char *value)
{
	const char *safe_value = safe_str(value);

	return zcbor_uint32_put(state, key) &&
	       zcbor_tstr_put_term(state, safe_value, strlen(safe_value) + 1U);
}

static bool cbor_put_envelope(zcbor_state_t *state,
	enum neuro_protocol_cbor_message_kind message_kind)
{
	return cbor_put_key_u32(state, NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION,
		       NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) &&
	       cbor_put_key_u32(state, NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND,
		       message_kind);
}

static bool cbor_decode_tstr_to_buf(
	zcbor_state_t *state, char *buf, size_t buf_len)
{
	struct zcbor_string value;

	if (buf == NULL || buf_len == 0U) {
		return false;
	}

	if (!zcbor_tstr_decode(state, &value) || value.len >= buf_len) {
		return false;
	}

	memcpy(buf, value.value, value.len);
	buf[value.len] = '\0';
	return true;
}

bool neuro_protocol_cbor_message_kind_is_valid(uint32_t message_kind)
{
	switch (message_kind) {
	case NEURO_PROTOCOL_CBOR_MSG_QUERY_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_LEASE_ACQUIRE_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_LEASE_RELEASE_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_APP_COMMAND_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_CALLBACK_CONFIG_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_PREPARE_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_VERIFY_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_ACTIVATE_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_ROLLBACK_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_DELETE_REQUEST:
	case NEURO_PROTOCOL_CBOR_MSG_ERROR_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_LEASE_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_QUERY_DEVICE_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_QUERY_APPS_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_QUERY_LEASES_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_PREPARE_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_VERIFY_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_ACTIVATE_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_ROLLBACK_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_APP_COMMAND_REPLY:
	case NEURO_PROTOCOL_CBOR_MSG_CALLBACK_EVENT:
	case NEURO_PROTOCOL_CBOR_MSG_UPDATE_EVENT:
	case NEURO_PROTOCOL_CBOR_MSG_STATE_EVENT:
	case NEURO_PROTOCOL_CBOR_MSG_LEASE_EVENT:
		return true;
	default:
		return false;
	}
}

int neuro_protocol_cbor_encode_envelope_header(uint8_t *payload,
	size_t payload_len, enum neuro_protocol_cbor_message_kind message_kind,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || encoded_len == NULL) {
		return -EINVAL;
	}

	if (!neuro_protocol_cbor_message_kind_is_valid(message_kind)) {
		return -ENOTSUP;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	if (!(zcbor_map_start_encode(state, 2) &&
		    zcbor_uint32_put(
			    state, NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION) &&
		    zcbor_uint32_put(
			    state, NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) &&
		    zcbor_uint32_put(
			    state, NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND) &&
		    zcbor_uint32_put(state, (uint32_t)message_kind) &&
		    zcbor_map_end_encode(state, 2))) {
		return -ENAMETOOLONG;
	}

	*encoded_len = (size_t)(state->payload - payload);
	return 0;
}

int neuro_protocol_cbor_decode_envelope_header(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_cbor_envelope *envelope)
{
	uint32_t schema_version = 0U;
	uint32_t message_kind = 0U;

	if (payload == NULL || payload_len == 0U || envelope == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_D(state, 1, payload, payload_len, 1, 0);
	if (!zcbor_map_start_decode(state)) {
		return -EBADMSG;
	}

	while (state->elem_count > 0U) {
		uint32_t key;

		if (!zcbor_uint32_decode(state, &key)) {
			return -EBADMSG;
		}

		switch (key) {
		case NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION:
			if (!zcbor_uint32_decode(state, &schema_version)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND:
			if (!zcbor_uint32_decode(state, &message_kind)) {
				return -EBADMSG;
			}
			break;
		default:
			if (!zcbor_any_skip(state, NULL)) {
				return -EBADMSG;
			}
			break;
		}
	}

	if (!zcbor_map_end_decode(state)) {
		return -EBADMSG;
	}

	if (schema_version != NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) {
		return -ENOTSUP;
	}

	if (!neuro_protocol_cbor_message_kind_is_valid(message_kind)) {
		return -ENOTSUP;
	}

	envelope->schema_version = schema_version;
	envelope->message_kind =
		(enum neuro_protocol_cbor_message_kind)message_kind;
	return 0;
}

int neuro_protocol_encode_error_reply_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_error_reply *reply, size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 7) &&
			cbor_put_envelope(
				state, NEURO_PROTOCOL_CBOR_MSG_ERROR_REPLY) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
				neuro_protocol_status_to_str(
					NEURO_PROTOCOL_STATUS_ERROR)) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID,
				reply->request_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NODE_ID,
				reply->node_id) &&
			cbor_put_key_i32(state,
				NEURO_PROTOCOL_CBOR_KEY_STATUS_CODE,
				reply->status_code) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_MESSAGE,
				reply->message) &&
			zcbor_map_end_encode(state, 7),
		encoded_len);
}

int neuro_protocol_encode_lease_reply_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_lease_reply *reply, size_t *encoded_len)
{
	size_t map_pairs;

	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	map_pairs = reply->include_expires_at_ms ? 8U : 7U;
	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, map_pairs) &&
			cbor_put_envelope(
				state, NEURO_PROTOCOL_CBOR_MSG_LEASE_REPLY) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
				neuro_protocol_status_to_str(
					NEURO_PROTOCOL_STATUS_OK)) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID,
				reply->request_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NODE_ID,
				reply->node_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_LEASE_ID,
				reply->lease_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_RESOURCE,
				reply->resource) &&
			(!reply->include_expires_at_ms ||
				cbor_put_key_i64(state,
					NEURO_PROTOCOL_CBOR_KEY_EXPIRES_AT_MS,
					reply->expires_at_ms)) &&
			zcbor_map_end_encode(state, map_pairs),
		encoded_len);
}

int neuro_protocol_encode_query_device_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_query_device_reply *reply,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 9) &&
			cbor_put_envelope(state,
				NEURO_PROTOCOL_CBOR_MSG_QUERY_DEVICE_REPLY) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
				neuro_protocol_status_to_str(
					NEURO_PROTOCOL_STATUS_OK)) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID,
				reply->request_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NODE_ID,
				reply->node_id) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_BOARD,
				reply->board) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_ZENOH_MODE,
				reply->zenoh_mode) &&
			cbor_put_key_bool(state,
				NEURO_PROTOCOL_CBOR_KEY_SESSION_READY,
				reply->session_ready) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NETWORK_STATE,
				reply->network_state) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_IPV4,
				reply->ipv4) &&
			zcbor_map_end_encode(state, 9),
		encoded_len);
}

int neuro_protocol_encode_callback_event_cbor(uint8_t *payload,
	size_t payload_len, const struct neuro_protocol_callback_event *event,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || event == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 6) &&
			cbor_put_envelope(state,
				NEURO_PROTOCOL_CBOR_MSG_CALLBACK_EVENT) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_APP_ID,
				event->app_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_EVENT_NAME,
				event->event_name) &&
			cbor_put_key_u32(state,
				NEURO_PROTOCOL_CBOR_KEY_INVOKE_COUNT,
				event->invoke_count) &&
			cbor_put_key_i32(state,
				NEURO_PROTOCOL_CBOR_KEY_START_COUNT,
				event->start_count) &&
			zcbor_map_end_encode(state, 6),
		encoded_len);
}

int neuro_protocol_encode_app_command_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_app_command_reply *reply,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 10) &&
			cbor_put_envelope(state,
				NEURO_PROTOCOL_CBOR_MSG_APP_COMMAND_REPLY) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_COMMAND,
				reply->command_name) &&
			cbor_put_key_bool(state,
				NEURO_PROTOCOL_CBOR_KEY_CALLBACK_ENABLED,
				reply->callback_enabled) &&
			cbor_put_key_i32(state,
				NEURO_PROTOCOL_CBOR_KEY_TRIGGER_EVERY,
				reply->trigger_every) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_EVENT_NAME,
				reply->event_name) &&
			cbor_put_key_u32(state,
				NEURO_PROTOCOL_CBOR_KEY_INVOKE_COUNT,
				reply->invoke_count) &&
			cbor_put_key_bool(state,
				NEURO_PROTOCOL_CBOR_KEY_CONFIG_CHANGED,
				reply->config_changed) &&
			cbor_put_key_i32(state,
				NEURO_PROTOCOL_CBOR_KEY_PUBLISH_RET,
				reply->publish_ret) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_ECHO,
				reply->echo) &&
			zcbor_map_end_encode(state, 10),
		encoded_len);
}

static bool cbor_put_query_app(
	zcbor_state_t *state, const struct neuro_protocol_query_app_cbor *app)
{
	return zcbor_map_start_encode(state, 10) &&
	       cbor_put_key_u32(state, NEURO_PROTOCOL_CBOR_KEY_PRIORITY,
		       app->priority) &&
	       cbor_put_key_tstr(
		       state, NEURO_PROTOCOL_CBOR_KEY_APP_ID, app->app_id) &&
	       cbor_put_key_tstr(
		       state, NEURO_PROTOCOL_CBOR_KEY_PATH, app->path) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_RUNTIME_STATE,
		       app->runtime_state) &&
	       cbor_put_key_bool(state,
		       NEURO_PROTOCOL_CBOR_KEY_MANIFEST_PRESENT,
		       app->manifest_present) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_UPDATE_STATE,
		       app->update_state) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_ARTIFACT_STATE,
		       app->artifact_state) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STABLE_REF,
		       app->stable_ref) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_LAST_ERROR,
		       app->last_error) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_ROLLBACK_REASON,
		       app->rollback_reason) &&
	       zcbor_map_end_encode(state, 10);
}

static bool cbor_put_query_lease(zcbor_state_t *state,
	const struct neuro_protocol_query_lease_cbor *lease)
{
	return zcbor_map_start_encode(state, 6) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_SOURCE_CORE,
		       lease->source_core) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_SOURCE_AGENT,
		       lease->source_agent) &&
	       cbor_put_key_i32(state, NEURO_PROTOCOL_CBOR_KEY_PRIORITY,
		       lease->priority) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_LEASE_ID,
		       lease->lease_id) &&
	       cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_RESOURCE,
		       lease->resource) &&
	       cbor_put_key_i64(state, NEURO_PROTOCOL_CBOR_KEY_EXPIRES_AT_MS,
		       lease->expires_at_ms) &&
	       zcbor_map_end_encode(state, 6);
}

int neuro_protocol_encode_query_apps_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_query_apps_reply_cbor *reply,
	size_t *encoded_len)
{
	bool ok;
	size_t i;

	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL ||
		(reply->apps == NULL && reply->app_count_listed > 0U)) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 4, payload, payload_len, 1);
	ok = zcbor_map_start_encode(state, 9) &&
	     cbor_put_envelope(
		     state, NEURO_PROTOCOL_CBOR_MSG_QUERY_APPS_REPLY) &&
	     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
		     neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK)) &&
	     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID,
		     reply->request_id) &&
	     cbor_put_key_tstr(
		     state, NEURO_PROTOCOL_CBOR_KEY_NODE_ID, reply->node_id) &&
	     cbor_put_key_u32(state, NEURO_PROTOCOL_CBOR_KEY_APP_COUNT,
		     reply->app_count) &&
	     cbor_put_key_u32(state, NEURO_PROTOCOL_CBOR_KEY_RUNNING_COUNT,
		     reply->running_count) &&
	     cbor_put_key_u32(state, NEURO_PROTOCOL_CBOR_KEY_SUSPENDED_COUNT,
		     reply->suspended_count) &&
	     zcbor_uint32_put(state, NEURO_PROTOCOL_CBOR_KEY_APPS) &&
	     zcbor_list_start_encode(state, reply->app_count_listed);
	for (i = 0; ok && i < reply->app_count_listed; i++) {
		ok = cbor_put_query_app(state, &reply->apps[i]);
	}
	ok = ok && zcbor_list_end_encode(state, reply->app_count_listed) &&
	     zcbor_map_end_encode(state, 9);

	return cbor_finish_encode(payload, state, ok, encoded_len);
}

int neuro_protocol_encode_query_leases_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_query_leases_reply_cbor *reply,
	size_t *encoded_len)
{
	bool ok;
	size_t i;

	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL ||
		(reply->leases == NULL && reply->lease_count > 0U)) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 4, payload, payload_len, 1);
	ok = zcbor_map_start_encode(state, 6) &&
	     cbor_put_envelope(
		     state, NEURO_PROTOCOL_CBOR_MSG_QUERY_LEASES_REPLY) &&
	     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
		     neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK)) &&
	     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID,
		     reply->request_id) &&
	     cbor_put_key_tstr(
		     state, NEURO_PROTOCOL_CBOR_KEY_NODE_ID, reply->node_id) &&
	     zcbor_uint32_put(state, NEURO_PROTOCOL_CBOR_KEY_LEASES) &&
	     zcbor_list_start_encode(state, reply->lease_count);
	for (i = 0; ok && i < reply->lease_count; i++) {
		ok = cbor_put_query_lease(state, &reply->leases[i]);
	}
	ok = ok && zcbor_list_end_encode(state, reply->lease_count) &&
	     zcbor_map_end_encode(state, 6);

	return cbor_finish_encode(payload, state, ok, encoded_len);
}

static int encode_update_reply_cbor(uint8_t *payload, size_t payload_len,
	enum neuro_protocol_cbor_message_kind message_kind,
	const struct neuro_protocol_update_reply_cbor *reply, size_t map_pairs,
	size_t *encoded_len)
{
	bool ok;

	if (payload == NULL || payload_len == 0U || reply == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	ok = zcbor_map_start_encode(state, map_pairs) &&
	     cbor_put_envelope(state, message_kind) &&
	     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
		     neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK)) &&
	     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID,
		     reply->request_id) &&
	     cbor_put_key_tstr(
		     state, NEURO_PROTOCOL_CBOR_KEY_NODE_ID, reply->node_id) &&
	     cbor_put_key_tstr(
		     state, NEURO_PROTOCOL_CBOR_KEY_APP_ID, reply->app_id);

	if (ok &&
		message_kind == NEURO_PROTOCOL_CBOR_MSG_UPDATE_ROLLBACK_REPLY) {
		ok = cbor_put_key_tstr(
			state, NEURO_PROTOCOL_CBOR_KEY_REASON, reply->reason);
	} else if (ok && message_kind ==
				 NEURO_PROTOCOL_CBOR_MSG_UPDATE_VERIFY_REPLY) {
		ok = cbor_put_key_u32(
			state, NEURO_PROTOCOL_CBOR_KEY_SIZE, reply->size);
	} else if (ok && message_kind ==
				 NEURO_PROTOCOL_CBOR_MSG_UPDATE_PREPARE_REPLY) {
		ok = cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_PATH,
			     reply->path) &&
		     cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_TRANSPORT,
			     reply->transport);
	} else if (ok &&
		   message_kind ==
			   NEURO_PROTOCOL_CBOR_MSG_UPDATE_ACTIVATE_REPLY) {
		ok = cbor_put_key_tstr(
			state, NEURO_PROTOCOL_CBOR_KEY_PATH, reply->path);
	}

	ok = ok && zcbor_map_end_encode(state, map_pairs);
	return cbor_finish_encode(payload, state, ok, encoded_len);
}

int neuro_protocol_encode_update_prepare_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len)
{
	return encode_update_reply_cbor(payload, payload_len,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_PREPARE_REPLY, reply, 8,
		encoded_len);
}

int neuro_protocol_encode_update_verify_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len)
{
	return encode_update_reply_cbor(payload, payload_len,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_VERIFY_REPLY, reply, 7,
		encoded_len);
}

int neuro_protocol_encode_update_activate_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len)
{
	return encode_update_reply_cbor(payload, payload_len,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_ACTIVATE_REPLY, reply, 7,
		encoded_len);
}

int neuro_protocol_encode_update_rollback_reply_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_reply_cbor *reply,
	size_t *encoded_len)
{
	return encode_update_reply_cbor(payload, payload_len,
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_ROLLBACK_REPLY, reply, 7,
		encoded_len);
}

int neuro_protocol_encode_update_event_cbor(uint8_t *payload,
	size_t payload_len,
	const struct neuro_protocol_update_event_cbor *event,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || event == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 7) &&
			cbor_put_envelope(
				state, NEURO_PROTOCOL_CBOR_MSG_UPDATE_EVENT) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NODE_ID,
				event->node_id) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_APP_ID,
				event->app_id) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STAGE,
				event->stage) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_STATUS,
				event->status) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_DETAIL,
				event->detail) &&
			zcbor_map_end_encode(state, 7),
		encoded_len);
}

int neuro_protocol_encode_state_event_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_state_event_cbor *event,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || event == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 6) &&
			cbor_put_envelope(
				state, NEURO_PROTOCOL_CBOR_MSG_STATE_EVENT) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NODE_ID,
				event->node_id) &&
			cbor_put_key_u32(state,
				NEURO_PROTOCOL_CBOR_KEY_APP_COUNT,
				event->app_count) &&
			cbor_put_key_u32(state,
				NEURO_PROTOCOL_CBOR_KEY_RUNNING_COUNT,
				event->running_count) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NETWORK_STATE,
				event->network_state) &&
			zcbor_map_end_encode(state, 6),
		encoded_len);
}

int neuro_protocol_encode_lease_event_cbor(uint8_t *payload, size_t payload_len,
	const struct neuro_protocol_lease_event_cbor *event,
	size_t *encoded_len)
{
	if (payload == NULL || payload_len == 0U || event == NULL ||
		encoded_len == NULL) {
		return -EINVAL;
	}

	ZCBOR_STATE_E(state, 1, payload, payload_len, 1);
	return cbor_finish_encode(payload, state,
		zcbor_map_start_encode(state, 9) &&
			cbor_put_envelope(
				state, NEURO_PROTOCOL_CBOR_MSG_LEASE_EVENT) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_NODE_ID,
				event->node_id) &&
			cbor_put_key_tstr(state, NEURO_PROTOCOL_CBOR_KEY_ACTION,
				event->action) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_LEASE_ID,
				event->lease_id) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_RESOURCE,
				event->resource) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_SOURCE_CORE,
				event->source_core) &&
			cbor_put_key_tstr(state,
				NEURO_PROTOCOL_CBOR_KEY_SOURCE_AGENT,
				event->source_agent) &&
			cbor_put_key_i32(state,
				NEURO_PROTOCOL_CBOR_KEY_PRIORITY,
				event->priority) &&
			zcbor_map_end_encode(state, 9),
		encoded_len);
}

int neuro_protocol_decode_request_metadata_cbor(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_request_metadata *metadata,
	enum neuro_protocol_cbor_message_kind *message_kind)
{
	uint32_t decoded_schema_version = 0U;
	uint32_t decoded_message_kind = 0U;

	if (payload == NULL || payload_len == 0U || metadata == NULL ||
		message_kind == NULL) {
		return -EINVAL;
	}

	memset(metadata, 0, sizeof(*metadata));
	metadata->priority = -1;

	ZCBOR_STATE_D(state, 1, payload, payload_len, 1, 0);
	if (!zcbor_map_start_decode(state)) {
		return -EBADMSG;
	}

	while (state->elem_count > 0U) {
		uint32_t key;
		int32_t value_i32;

		if (!zcbor_uint32_decode(state, &key)) {
			return -EBADMSG;
		}

		switch (key) {
		case NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION:
			if (!zcbor_uint32_decode(
				    state, &decoded_schema_version)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND:
			if (!zcbor_uint32_decode(
				    state, &decoded_message_kind)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_REQUEST_ID:
			if (!cbor_decode_tstr_to_buf(state,
				    metadata->request_id,
				    sizeof(metadata->request_id))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_SOURCE_CORE:
			if (!cbor_decode_tstr_to_buf(state,
				    metadata->source_core,
				    sizeof(metadata->source_core))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_SOURCE_AGENT:
			if (!cbor_decode_tstr_to_buf(state,
				    metadata->source_agent,
				    sizeof(metadata->source_agent))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TARGET_NODE:
			if (!cbor_decode_tstr_to_buf(state,
				    metadata->target_node,
				    sizeof(metadata->target_node))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TIMEOUT_MS:
			if (!zcbor_uint32_decode(
				    state, &metadata->timeout_ms)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_PRIORITY:
			if (!zcbor_int32_decode(state, &value_i32)) {
				return -EBADMSG;
			}
			metadata->priority = value_i32;
			break;
		case NEURO_PROTOCOL_CBOR_KEY_IDEMPOTENCY_KEY:
			if (!cbor_decode_tstr_to_buf(state,
				    metadata->idempotency_key,
				    sizeof(metadata->idempotency_key))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_LEASE_ID:
			if (!cbor_decode_tstr_to_buf(state, metadata->lease_id,
				    sizeof(metadata->lease_id))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_FORWARDED:
			if (!zcbor_bool_decode(state, &metadata->forwarded)) {
				return -EBADMSG;
			}
			break;
		default:
			if (!zcbor_any_skip(state, NULL)) {
				return -EBADMSG;
			}
			break;
		}
	}

	if (!zcbor_map_end_decode(state)) {
		return -EBADMSG;
	}

	if (decoded_schema_version != NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) {
		return -ENOTSUP;
	}

	if (!neuro_protocol_cbor_message_kind_is_valid(decoded_message_kind)) {
		return -ENOTSUP;
	}

	if (decoded_message_kind >= NEURO_PROTOCOL_CBOR_MSG_ERROR_REPLY) {
		return -ENOTSUP;
	}

	*message_kind =
		(enum neuro_protocol_cbor_message_kind)decoded_message_kind;
	return 0;
}

int neuro_protocol_decode_callback_config_cbor(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_callback_config *config)
{
	uint32_t decoded_schema_version = 0U;
	uint32_t decoded_message_kind = 0U;

	if (payload == NULL || payload_len == 0U || config == NULL) {
		return -EINVAL;
	}

	memset(config, 0, sizeof(*config));

	ZCBOR_STATE_D(state, 1, payload, payload_len, 1, 0);
	if (!zcbor_map_start_decode(state)) {
		return -EBADMSG;
	}

	while (state->elem_count > 0U) {
		uint32_t key;

		if (!zcbor_uint32_decode(state, &key)) {
			return -EBADMSG;
		}

		switch (key) {
		case NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION:
			if (!zcbor_uint32_decode(
				    state, &decoded_schema_version)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND:
			if (!zcbor_uint32_decode(
				    state, &decoded_message_kind)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_CALLBACK_ENABLED:
			if (!zcbor_bool_decode(
				    state, &config->callback_enabled)) {
				return -EBADMSG;
			}
			config->has_callback_enabled = true;
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TRIGGER_EVERY:
			if (!zcbor_int32_decode(
				    state, &config->trigger_every)) {
				return -EBADMSG;
			}
			config->has_trigger_every = true;
			break;
		case NEURO_PROTOCOL_CBOR_KEY_EVENT_NAME:
			if (!cbor_decode_tstr_to_buf(state, config->event_name,
				    sizeof(config->event_name))) {
				return -EBADMSG;
			}
			config->has_event_name = true;
			break;
		default:
			if (!zcbor_any_skip(state, NULL)) {
				return -EBADMSG;
			}
			break;
		}
	}

	if (!zcbor_map_end_decode(state)) {
		return -EBADMSG;
	}

	if (decoded_schema_version != NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) {
		return -ENOTSUP;
	}

	if (decoded_message_kind !=
		NEURO_PROTOCOL_CBOR_MSG_CALLBACK_CONFIG_REQUEST) {
		return -ENOTSUP;
	}

	return 0;
}

int neuro_protocol_decode_update_prepare_request_cbor(const uint8_t *payload,
	size_t payload_len,
	struct neuro_protocol_update_prepare_request_cbor *request)
{
	uint32_t decoded_schema_version = 0U;
	uint32_t decoded_message_kind = 0U;

	if (payload == NULL || payload_len == 0U || request == NULL) {
		return -EINVAL;
	}

	memset(request, 0, sizeof(*request));

	ZCBOR_STATE_D(state, 1, payload, payload_len, 1, 0);
	if (!zcbor_map_start_decode(state)) {
		return -EBADMSG;
	}

	while (state->elem_count > 0U) {
		uint32_t key;

		if (!zcbor_uint32_decode(state, &key)) {
			return -EBADMSG;
		}

		switch (key) {
		case NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION:
			if (!zcbor_uint32_decode(
				    state, &decoded_schema_version)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND:
			if (!zcbor_uint32_decode(
				    state, &decoded_message_kind)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TRANSPORT:
			if (!cbor_decode_tstr_to_buf(state, request->transport,
				    sizeof(request->transport))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_ARTIFACT_KEY:
			if (!cbor_decode_tstr_to_buf(state,
				    request->artifact_key,
				    sizeof(request->artifact_key))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_SIZE:
			if (!zcbor_uint32_decode(state, &request->size)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_CHUNK_SIZE:
			if (!zcbor_uint32_decode(state, &request->chunk_size)) {
				return -EBADMSG;
			}
			break;
		default:
			if (!zcbor_any_skip(state, NULL)) {
				return -EBADMSG;
			}
			break;
		}
	}

	if (!zcbor_map_end_decode(state)) {
		return -EBADMSG;
	}

	if (decoded_schema_version != NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) {
		return -ENOTSUP;
	}

	if (decoded_message_kind !=
		NEURO_PROTOCOL_CBOR_MSG_UPDATE_PREPARE_REQUEST) {
		return -ENOTSUP;
	}

	return 0;
}

int neuro_protocol_decode_request_fields_cbor(const uint8_t *payload,
	size_t payload_len, struct neuro_protocol_request_fields_cbor *fields)
{
	uint32_t decoded_schema_version = 0U;
	uint32_t decoded_message_kind = 0U;

	if (payload == NULL || payload_len == 0U || fields == NULL) {
		return -EINVAL;
	}

	memset(fields, 0, sizeof(*fields));

	ZCBOR_STATE_D(state, 1, payload, payload_len, 1, 0);
	if (!zcbor_map_start_decode(state)) {
		return -EBADMSG;
	}

	while (state->elem_count > 0U) {
		uint32_t key;

		if (!zcbor_uint32_decode(state, &key)) {
			return -EBADMSG;
		}

		switch (key) {
		case NEURO_PROTOCOL_CBOR_KEY_SCHEMA_VERSION:
			if (!zcbor_uint32_decode(
				    state, &decoded_schema_version)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_MESSAGE_KIND:
			if (!zcbor_uint32_decode(
				    state, &decoded_message_kind)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_RESOURCE:
			if (!cbor_decode_tstr_to_buf(state, fields->resource,
				    sizeof(fields->resource))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TTL_MS:
			if (!zcbor_uint32_decode(state, &fields->ttl_ms)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_START_ARGS:
			if (!cbor_decode_tstr_to_buf(state, fields->start_args,
				    sizeof(fields->start_args))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_REASON:
			if (!cbor_decode_tstr_to_buf(state, fields->reason,
				    sizeof(fields->reason))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TRANSPORT:
			if (!cbor_decode_tstr_to_buf(state, fields->transport,
				    sizeof(fields->transport))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_ARTIFACT_KEY:
			if (!cbor_decode_tstr_to_buf(state,
				    fields->artifact_key,
				    sizeof(fields->artifact_key))) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_SIZE:
			if (!zcbor_uint32_decode(state, &fields->size)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_CHUNK_SIZE:
			if (!zcbor_uint32_decode(state, &fields->chunk_size)) {
				return -EBADMSG;
			}
			break;
		case NEURO_PROTOCOL_CBOR_KEY_CALLBACK_ENABLED:
			if (!zcbor_bool_decode(
				    state, &fields->callback_enabled)) {
				return -EBADMSG;
			}
			fields->has_callback_enabled = true;
			break;
		case NEURO_PROTOCOL_CBOR_KEY_TRIGGER_EVERY:
			if (!zcbor_int32_decode(
				    state, &fields->trigger_every)) {
				return -EBADMSG;
			}
			fields->has_trigger_every = true;
			break;
		case NEURO_PROTOCOL_CBOR_KEY_EVENT_NAME:
			if (!cbor_decode_tstr_to_buf(state, fields->event_name,
				    sizeof(fields->event_name))) {
				return -EBADMSG;
			}
			fields->has_event_name = true;
			break;
		default:
			if (!zcbor_any_skip(state, NULL)) {
				return -EBADMSG;
			}
			break;
		}
	}

	if (!zcbor_map_end_decode(state)) {
		return -EBADMSG;
	}

	if (decoded_schema_version != NEURO_PROTOCOL_CBOR_SCHEMA_VERSION) {
		return -ENOTSUP;
	}

	if (!neuro_protocol_cbor_message_kind_is_valid(decoded_message_kind) ||
		decoded_message_kind >= NEURO_PROTOCOL_CBOR_MSG_ERROR_REPLY) {
		return -ENOTSUP;
	}

	return 0;
}
