#include <zephyr/llext/symbol.h>
#include <zephyr/sys/printk.h>

#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "neuro_request_envelope.h"

static const char *skip_json_ws(const char *ptr)
{
	while (ptr != NULL &&
		(*ptr == ' ' || *ptr == '\t' || *ptr == '\r' || *ptr == '\n')) {
		ptr++;
	}

	return ptr;
}

bool neuro_json_extract_string(
	const char *json, const char *key, char *out, size_t out_len)
{
	char pattern[32];
	const char *pos;
	const char *end;
	size_t len;

	if (json == NULL || key == NULL || out == NULL || out_len == 0U) {
		return false;
	}

	snprintk(pattern, sizeof(pattern), "\"%s\"", key);
	pos = strstr(json, pattern);
	if (pos == NULL) {
		return false;
	}

	pos = strchr(pos + strlen(pattern), ':');
	if (pos == NULL) {
		return false;
	}

	pos = skip_json_ws(pos + 1);
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

int neuro_json_extract_int(const char *json, const char *key, int default_value)
{
	char pattern[32];
	const char *pos;
	char *endptr;
	long value;

	if (json == NULL || key == NULL) {
		return default_value;
	}

	snprintk(pattern, sizeof(pattern), "\"%s\"", key);
	pos = strstr(json, pattern);
	if (pos == NULL) {
		return default_value;
	}

	pos = strchr(pos + strlen(pattern), ':');
	if (pos == NULL) {
		return default_value;
	}

	pos = skip_json_ws(pos + 1);
	if (pos == NULL) {
		return default_value;
	}

	value = strtol(pos, &endptr, 10);
	if (endptr == pos) {
		return default_value;
	}

	return (int)value;
}

bool neuro_json_extract_bool(
	const char *json, const char *key, bool default_value)
{
	char pattern[32];
	const char *pos;

	if (json == NULL || key == NULL) {
		return default_value;
	}

	snprintk(pattern, sizeof(pattern), "\"%s\"", key);
	pos = strstr(json, pattern);
	if (pos == NULL) {
		return default_value;
	}

	pos = strchr(pos + strlen(pattern), ':');
	if (pos == NULL) {
		return default_value;
	}

	pos = skip_json_ws(pos + 1);
	if (pos == NULL) {
		return default_value;
	}

	if (strncmp(pos, "true", 4) == 0) {
		return true;
	}

	if (strncmp(pos, "false", 5) == 0) {
		return false;
	}

	return default_value;
}

EXPORT_SYMBOL(neuro_json_extract_string);
EXPORT_SYMBOL(neuro_json_extract_int);
EXPORT_SYMBOL(neuro_json_extract_bool);

void neuro_request_metadata_init(struct neuro_request_metadata *metadata)
{
	if (metadata == NULL) {
		return;
	}

	memset(metadata, 0, sizeof(*metadata));
	metadata->priority = -1;
}

static bool neuro_request_field_present(const char *value)
{
	return value != NULL && value[0] != '\0';
}

static bool neuro_request_validation_fail(
	char *error_buf, size_t error_buf_len, const char *message)
{
	if (error_buf != NULL && error_buf_len > 0U) {
		snprintk(error_buf, error_buf_len, "%s",
			message ? message : "invalid request");
	}

	return false;
}

bool neuro_request_metadata_parse(
	const char *json, struct neuro_request_metadata *metadata)
{
	if (metadata == NULL) {
		return false;
	}

	neuro_request_metadata_init(metadata);
	if (json == NULL) {
		return false;
	}

	(void)neuro_json_extract_string(json, "request_id",
		metadata->request_id, sizeof(metadata->request_id));
	(void)neuro_json_extract_string(json, "source_core",
		metadata->source_core, sizeof(metadata->source_core));
	(void)neuro_json_extract_string(json, "source_agent",
		metadata->source_agent, sizeof(metadata->source_agent));
	(void)neuro_json_extract_string(json, "target_node",
		metadata->target_node, sizeof(metadata->target_node));
	(void)neuro_json_extract_string(json, "lease_id", metadata->lease_id,
		sizeof(metadata->lease_id));
	(void)neuro_json_extract_string(json, "idempotency_key",
		metadata->idempotency_key, sizeof(metadata->idempotency_key));
	metadata->timeout_ms =
		(uint32_t)neuro_json_extract_int(json, "timeout_ms", 0);
	metadata->priority =
		neuro_json_extract_int(json, "priority", metadata->priority);
	metadata->forwarded = neuro_json_extract_bool(json, "forwarded", false);
	return true;
}

bool neuro_request_metadata_validate(
	const struct neuro_request_metadata *metadata, uint32_t required_fields,
	const char *expected_target_node, char *error_buf, size_t error_buf_len)
{
	if (metadata == NULL) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "request metadata missing");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_REQUEST_ID) != 0U &&
		!neuro_request_field_present(metadata->request_id)) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "request_id is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_SOURCE_CORE) != 0U &&
		!neuro_request_field_present(metadata->source_core)) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "source_core is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_SOURCE_AGENT) != 0U &&
		!neuro_request_field_present(metadata->source_agent)) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "source_agent is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_TARGET_NODE) != 0U &&
		!neuro_request_field_present(metadata->target_node)) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "target_node is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_TIMEOUT_MS) != 0U &&
		metadata->timeout_ms == 0U) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "timeout_ms is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_LEASE_ID) != 0U &&
		!neuro_request_field_present(metadata->lease_id)) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "lease_id is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_PRIORITY) != 0U &&
		metadata->priority < 0) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "priority is required");
	}

	if ((required_fields & NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY) != 0U &&
		!neuro_request_field_present(metadata->idempotency_key)) {
		return neuro_request_validation_fail(error_buf, error_buf_len,
			"idempotency_key is required");
	}

	if (expected_target_node != NULL && expected_target_node[0] != '\0' &&
		neuro_request_field_present(metadata->target_node) &&
		strcmp(metadata->target_node, expected_target_node) != 0) {
		return neuro_request_validation_fail(
			error_buf, error_buf_len, "target_node mismatch");
	}

	if (error_buf != NULL && error_buf_len > 0U) {
		error_buf[0] = '\0';
	}

	return true;
}
