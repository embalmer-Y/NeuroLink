#include "neuro_protocol_codec.h"

#include <zephyr/sys/printk.h>

#include <errno.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

#include "neuro_protocol.h"

static const char *safe_str(const char *value)
{
	if (value == NULL) {
		return "";
	}

	return value;
}

static int checked_snprintk(char *json, size_t json_len, const char *fmt, ...)
{
	va_list args;
	int ret;

	if (json == NULL || json_len == 0U || fmt == NULL) {
		return -EINVAL;
	}

	va_start(args, fmt);
	ret = vsnprintk(json, json_len, fmt, args);
	va_end(args);
	if (ret < 0 || (size_t)ret >= json_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

static const char *skip_json_ws(const char *ptr)
{
	while (ptr != NULL &&
		(*ptr == ' ' || *ptr == '\t' || *ptr == '\r' || *ptr == '\n')) {
		ptr++;
	}

	return ptr;
}

static const char *json_value_for_key(const char *json, const char *key)
{
	char pattern[48];
	const char *pos;
	int ret;

	if (json == NULL || key == NULL) {
		return NULL;
	}

	ret = snprintk(pattern, sizeof(pattern), "\"%s\"", key);
	if (ret < 0 || (size_t)ret >= sizeof(pattern)) {
		return NULL;
	}

	pos = strstr(json, pattern);
	if (pos == NULL) {
		return NULL;
	}

	pos = strchr(pos + strlen(pattern), ':');
	if (pos == NULL) {
		return NULL;
	}

	return skip_json_ws(pos + 1);
}

static bool json_extract_string(
	const char *json, const char *key, char *out, size_t out_len)
{
	const char *pos;
	const char *end;
	size_t len;

	if (out == NULL || out_len == 0U) {
		return false;
	}

	pos = json_value_for_key(json, key);
	if (pos == NULL || *pos != '"') {
		return false;
	}

	pos++;
	end = strchr(pos, '"');
	if (end == NULL) {
		return false;
	}

	len = (size_t)(end - pos);
	if (len >= out_len) {
		len = out_len - 1U;
	}

	memcpy(out, pos, len);
	out[len] = '\0';
	return true;
}

static bool json_extract_int(const char *json, const char *key, int *out)
{
	const char *pos;
	char *endptr;
	long value;

	if (out == NULL) {
		return false;
	}

	pos = json_value_for_key(json, key);
	if (pos == NULL) {
		return false;
	}

	value = strtol(pos, &endptr, 10);
	if (endptr == pos) {
		return false;
	}

	*out = (int)value;
	return true;
}

static bool json_extract_bool(const char *json, const char *key, bool *out)
{
	const char *pos;

	if (out == NULL) {
		return false;
	}

	pos = json_value_for_key(json, key);
	if (pos == NULL) {
		return false;
	}

	if (strncmp(pos, "true", 4) == 0) {
		*out = true;
		return true;
	}

	if (strncmp(pos, "false", 5) == 0) {
		*out = false;
		return true;
	}

	return false;
}

int neuro_protocol_encode_error_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_error_reply *reply)
{
	if (reply == NULL) {
		return -EINVAL;
	}

	return checked_snprintk(json, json_len,
		"{\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":%d,\"%s\":\"%s\"}",
		NEURO_PROTOCOL_FIELD_STATUS,
		neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_ERROR),
		NEURO_PROTOCOL_FIELD_REQUEST_ID, safe_str(reply->request_id),
		NEURO_PROTOCOL_FIELD_NODE_ID, safe_str(reply->node_id),
		NEURO_PROTOCOL_FIELD_STATUS_CODE, reply->status_code,
		NEURO_PROTOCOL_FIELD_MESSAGE, safe_str(reply->message));
}

int neuro_protocol_encode_lease_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_lease_reply *reply)
{
	if (reply == NULL) {
		return -EINVAL;
	}

	if (reply->include_expires_at_ms) {
		return checked_snprintk(json, json_len,
			"{\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":\"%s\",\"resource\":\"%s\",\"expires_at_ms\":%lld}",
			NEURO_PROTOCOL_FIELD_STATUS,
			neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK),
			NEURO_PROTOCOL_FIELD_REQUEST_ID,
			safe_str(reply->request_id),
			NEURO_PROTOCOL_FIELD_NODE_ID, safe_str(reply->node_id),
			NEURO_PROTOCOL_FIELD_LEASE_ID,
			safe_str(reply->lease_id), safe_str(reply->resource),
			(long long)reply->expires_at_ms);
	}

	return checked_snprintk(json, json_len,
		"{\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":\"%s\",\"resource\":\"%s\"}",
		NEURO_PROTOCOL_FIELD_STATUS,
		neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK),
		NEURO_PROTOCOL_FIELD_REQUEST_ID, safe_str(reply->request_id),
		NEURO_PROTOCOL_FIELD_NODE_ID, safe_str(reply->node_id),
		NEURO_PROTOCOL_FIELD_LEASE_ID, safe_str(reply->lease_id),
		safe_str(reply->resource));
}

int neuro_protocol_encode_query_device_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_query_device_reply *reply)
{
	if (reply == NULL) {
		return -EINVAL;
	}

	return checked_snprintk(json, json_len,
		"{\"%s\":\"%s\",\"%s\":\"%s\",\"%s\":\"%s\",\"board\":\"%s\",\"zenoh_mode\":\"%s\",\"session_ready\":%s,\"network_state\":\"%s\",\"ipv4\":\"%s\"}",
		NEURO_PROTOCOL_FIELD_STATUS,
		neuro_protocol_status_to_str(NEURO_PROTOCOL_STATUS_OK),
		NEURO_PROTOCOL_FIELD_REQUEST_ID, safe_str(reply->request_id),
		NEURO_PROTOCOL_FIELD_NODE_ID, safe_str(reply->node_id),
		safe_str(reply->board), safe_str(reply->zenoh_mode),
		reply->session_ready ? "true" : "false",
		safe_str(reply->network_state), safe_str(reply->ipv4));
}

int neuro_protocol_encode_callback_event_json(char *json, size_t json_len,
	const struct neuro_protocol_callback_event *event)
{
	if (event == NULL) {
		return -EINVAL;
	}

	return checked_snprintk(json, json_len,
		"{\"app_id\":\"%s\",\"event_name\":\"%s\",\"invoke_count\":%u,\"start_count\":%d}",
		safe_str(event->app_id), safe_str(event->event_name),
		event->invoke_count, event->start_count);
}

int neuro_protocol_encode_app_command_reply_json(char *json, size_t json_len,
	const struct neuro_protocol_app_command_reply *reply)
{
	if (reply == NULL) {
		return -EINVAL;
	}

	return checked_snprintk(json, json_len,
		"{\"echo\":\"%s\",\"command\":\"%s\",\"invoke_count\":%u,\"callback_enabled\":%s,\"trigger_every\":%d,\"event_name\":\"%s\",\"config_changed\":%s,\"publish_ret\":%d}",
		safe_str(reply->echo), safe_str(reply->command_name),
		reply->invoke_count, reply->callback_enabled ? "true" : "false",
		reply->trigger_every, safe_str(reply->event_name),
		reply->config_changed ? "true" : "false", reply->publish_ret);
}

int neuro_protocol_decode_request_metadata_json(
	const char *json, struct neuro_protocol_request_metadata *metadata)
{
	int value;

	if (json == NULL || metadata == NULL) {
		return -EINVAL;
	}

	memset(metadata, 0, sizeof(*metadata));
	metadata->priority = -1;

	(void)json_extract_string(json, NEURO_PROTOCOL_FIELD_REQUEST_ID,
		metadata->request_id, sizeof(metadata->request_id));
	(void)json_extract_string(json, NEURO_PROTOCOL_FIELD_SOURCE_CORE,
		metadata->source_core, sizeof(metadata->source_core));
	(void)json_extract_string(json, NEURO_PROTOCOL_FIELD_SOURCE_AGENT,
		metadata->source_agent, sizeof(metadata->source_agent));
	(void)json_extract_string(json, NEURO_PROTOCOL_FIELD_TARGET_NODE,
		metadata->target_node, sizeof(metadata->target_node));
	(void)json_extract_string(json, NEURO_PROTOCOL_FIELD_LEASE_ID,
		metadata->lease_id, sizeof(metadata->lease_id));
	(void)json_extract_string(json, NEURO_PROTOCOL_FIELD_IDEMPOTENCY_KEY,
		metadata->idempotency_key, sizeof(metadata->idempotency_key));
	if (json_extract_int(json, NEURO_PROTOCOL_FIELD_TIMEOUT_MS, &value)) {
		metadata->timeout_ms = (uint32_t)value;
	}
	if (json_extract_int(json, NEURO_PROTOCOL_FIELD_PRIORITY, &value)) {
		metadata->priority = value;
	}
	(void)json_extract_bool(
		json, NEURO_PROTOCOL_FIELD_FORWARDED, &metadata->forwarded);

	return 0;
}

int neuro_protocol_decode_callback_config_json(
	const char *json, struct neuro_protocol_callback_config *config)
{
	if (json == NULL || config == NULL) {
		return -EINVAL;
	}

	memset(config, 0, sizeof(*config));
	config->has_callback_enabled =
		json_extract_bool(json, NEURO_PROTOCOL_FIELD_CALLBACK_ENABLED,
			&config->callback_enabled);
	config->has_trigger_every = json_extract_int(json,
		NEURO_PROTOCOL_FIELD_TRIGGER_EVERY, &config->trigger_every);
	config->has_event_name =
		json_extract_string(json, NEURO_PROTOCOL_FIELD_EVENT_NAME,
			config->event_name, sizeof(config->event_name));

	return 0;
}