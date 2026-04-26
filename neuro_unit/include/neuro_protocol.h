/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_PROTOCOL_H
#define NEURO_PROTOCOL_H

#include <zephyr/sys/printk.h>

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_PROTOCOL_VERSION_MAJOR 2U
#define NEURO_PROTOCOL_VERSION_MINOR 0U

#define NEURO_PROTOCOL_FIELD_STATUS "status"
#define NEURO_PROTOCOL_FIELD_REQUEST_ID "request_id"
#define NEURO_PROTOCOL_FIELD_NODE_ID "node_id"
#define NEURO_PROTOCOL_FIELD_SOURCE_CORE "source_core"
#define NEURO_PROTOCOL_FIELD_SOURCE_AGENT "source_agent"
#define NEURO_PROTOCOL_FIELD_TARGET_NODE "target_node"
#define NEURO_PROTOCOL_FIELD_TIMEOUT_MS "timeout_ms"
#define NEURO_PROTOCOL_FIELD_PRIORITY "priority"
#define NEURO_PROTOCOL_FIELD_IDEMPOTENCY_KEY "idempotency_key"
#define NEURO_PROTOCOL_FIELD_LEASE_ID "lease_id"
#define NEURO_PROTOCOL_FIELD_STATUS_CODE "status_code"
#define NEURO_PROTOCOL_FIELD_MESSAGE "message"
#define NEURO_PROTOCOL_FIELD_FORWARDED "forwarded"
#define NEURO_PROTOCOL_FIELD_CALLBACK_ENABLED "callback_enabled"
#define NEURO_PROTOCOL_FIELD_TRIGGER_EVERY "trigger_every"
#define NEURO_PROTOCOL_FIELD_EVENT_NAME "event_name"

#define NEURO_PROTOCOL_ROUTE_LEN 128
#define NEURO_PROTOCOL_TOKEN_LEN 32
#define NEURO_PROTOCOL_EVENT_NAME_LEN 32

enum neuro_protocol_wire_encoding {
	NEURO_PROTOCOL_WIRE_JSON_V2 = 1,
	NEURO_PROTOCOL_WIRE_CBOR_V2 = 2,
};

enum neuro_protocol_status {
	NEURO_PROTOCOL_STATUS_OK = 0,
	NEURO_PROTOCOL_STATUS_ERROR,
	NEURO_PROTOCOL_STATUS_NOT_IMPLEMENTED,
	NEURO_PROTOCOL_STATUS_NO_REPLY,
	NEURO_PROTOCOL_STATUS_DECODE_ERROR,
};

enum neuro_protocol_error_class {
	NEURO_PROTOCOL_ERROR_BAD_REQUEST = 400,
	NEURO_PROTOCOL_ERROR_FORBIDDEN = 403,
	NEURO_PROTOCOL_ERROR_NOT_FOUND = 404,
	NEURO_PROTOCOL_ERROR_CONFLICT = 409,
	NEURO_PROTOCOL_ERROR_INTERNAL = 500,
	NEURO_PROTOCOL_ERROR_UNAVAILABLE = 503,
};

enum neuro_protocol_query_kind {
	NEURO_PROTOCOL_QUERY_DEVICE = 0,
	NEURO_PROTOCOL_QUERY_APPS,
	NEURO_PROTOCOL_QUERY_LEASES,
};

enum neuro_protocol_lease_action {
	NEURO_PROTOCOL_LEASE_ACQUIRE = 0,
	NEURO_PROTOCOL_LEASE_RELEASE,
};

enum neuro_protocol_update_action {
	NEURO_PROTOCOL_UPDATE_PREPARE = 0,
	NEURO_PROTOCOL_UPDATE_VERIFY,
	NEURO_PROTOCOL_UPDATE_ACTIVATE,
	NEURO_PROTOCOL_UPDATE_ROLLBACK,
	NEURO_PROTOCOL_UPDATE_RECOVER,
};

static inline const char *neuro_protocol_wire_encoding_to_str(
	enum neuro_protocol_wire_encoding encoding)
{
	switch (encoding) {
	case NEURO_PROTOCOL_WIRE_JSON_V2:
		return "json-v2";
	case NEURO_PROTOCOL_WIRE_CBOR_V2:
		return "cbor-v2";
	default:
		return "unknown";
	}
}

static inline const char *neuro_protocol_status_to_str(
	enum neuro_protocol_status status)
{
	switch (status) {
	case NEURO_PROTOCOL_STATUS_OK:
		return "ok";
	case NEURO_PROTOCOL_STATUS_ERROR:
		return "error";
	case NEURO_PROTOCOL_STATUS_NOT_IMPLEMENTED:
		return "not_implemented";
	case NEURO_PROTOCOL_STATUS_NO_REPLY:
		return "no_reply";
	case NEURO_PROTOCOL_STATUS_DECODE_ERROR:
		return "decode_error";
	default:
		return "unknown";
	}
}

static inline const char *neuro_protocol_query_kind_to_segment(
	enum neuro_protocol_query_kind kind)
{
	switch (kind) {
	case NEURO_PROTOCOL_QUERY_DEVICE:
		return "device";
	case NEURO_PROTOCOL_QUERY_APPS:
		return "apps";
	case NEURO_PROTOCOL_QUERY_LEASES:
		return "leases";
	default:
		return NULL;
	}
}

static inline const char *neuro_protocol_lease_action_to_segment(
	enum neuro_protocol_lease_action action)
{
	switch (action) {
	case NEURO_PROTOCOL_LEASE_ACQUIRE:
		return "acquire";
	case NEURO_PROTOCOL_LEASE_RELEASE:
		return "release";
	default:
		return NULL;
	}
}

static inline const char *neuro_protocol_update_action_to_segment(
	enum neuro_protocol_update_action action)
{
	switch (action) {
	case NEURO_PROTOCOL_UPDATE_PREPARE:
		return "prepare";
	case NEURO_PROTOCOL_UPDATE_VERIFY:
		return "verify";
	case NEURO_PROTOCOL_UPDATE_ACTIVATE:
		return "activate";
	case NEURO_PROTOCOL_UPDATE_ROLLBACK:
		return "rollback";
	case NEURO_PROTOCOL_UPDATE_RECOVER:
		return "recover";
	default:
		return NULL;
	}
}

static inline bool neuro_protocol_token_is_valid(const char *token)
{
	if (token == NULL || token[0] == '\0') {
		return false;
	}

	for (; *token != '\0'; token++) {
		if (*token == '/') {
			return false;
		}
	}

	return true;
}

static inline int neuro_protocol_format_route(char *out, size_t out_len,
	const char *fmt, const char *node, const char *segment_a,
	const char *segment_b)
{
	int ret;

	if (out == NULL || out_len == 0U || fmt == NULL ||
		!neuro_protocol_token_is_valid(node)) {
		return -EINVAL;
	}

	ret = snprintk(out, out_len, fmt, node,
		segment_a != NULL ? segment_a : "",
		segment_b != NULL ? segment_b : "");
	if (ret < 0 || (size_t)ret >= out_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

static inline int neuro_protocol_build_query_route(char *out, size_t out_len,
	const char *node, enum neuro_protocol_query_kind kind)
{
	const char *segment = neuro_protocol_query_kind_to_segment(kind);

	if (segment == NULL) {
		return -EINVAL;
	}

	return neuro_protocol_format_route(
		out, out_len, "neuro/%s/query/%s%s", node, segment, NULL);
}

static inline int neuro_protocol_build_lease_route(char *out, size_t out_len,
	const char *node, enum neuro_protocol_lease_action action)
{
	const char *segment = neuro_protocol_lease_action_to_segment(action);

	if (segment == NULL) {
		return -EINVAL;
	}

	return neuro_protocol_format_route(
		out, out_len, "neuro/%s/cmd/lease/%s%s", node, segment, NULL);
}

static inline int neuro_protocol_build_app_command_route(char *out,
	size_t out_len, const char *node, const char *app_id,
	const char *command)
{
	int ret;

	if (out == NULL || out_len == 0U ||
		!neuro_protocol_token_is_valid(node) ||
		!neuro_protocol_token_is_valid(app_id) ||
		!neuro_protocol_token_is_valid(command)) {
		return -EINVAL;
	}

	ret = snprintk(
		out, out_len, "neuro/%s/cmd/app/%s/%s", node, app_id, command);
	if (ret < 0 || (size_t)ret >= out_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

static inline int neuro_protocol_build_update_route(char *out, size_t out_len,
	const char *node, const char *app_id,
	enum neuro_protocol_update_action action)
{
	const char *segment = neuro_protocol_update_action_to_segment(action);
	int ret;

	if (segment == NULL || out == NULL || out_len == 0U ||
		!neuro_protocol_token_is_valid(node) ||
		!neuro_protocol_token_is_valid(app_id)) {
		return -EINVAL;
	}

	ret = snprintk(out, out_len, "neuro/%s/update/app/%s/%s", node, app_id,
		segment);
	if (ret < 0 || (size_t)ret >= out_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

static inline int neuro_protocol_build_event_route(
	char *out, size_t out_len, const char *node, const char *suffix)
{
	int ret;

	if (out == NULL || out_len == 0U ||
		!neuro_protocol_token_is_valid(node) || suffix == NULL ||
		suffix[0] == '\0') {
		return -EINVAL;
	}

	ret = snprintk(out, out_len, "neuro/%s/event/%s", node, suffix);
	if (ret < 0 || (size_t)ret >= out_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

static inline int neuro_protocol_build_app_event_route(char *out,
	size_t out_len, const char *node, const char *app_id,
	const char *event_name)
{
	int ret;

	if (out == NULL || out_len == 0U ||
		!neuro_protocol_token_is_valid(node) ||
		!neuro_protocol_token_is_valid(app_id) ||
		!neuro_protocol_token_is_valid(event_name)) {
		return -EINVAL;
	}

	ret = snprintk(out, out_len, "neuro/%s/event/app/%s/%s", node, app_id,
		event_name);
	if (ret < 0 || (size_t)ret >= out_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

#ifdef __cplusplus
}
#endif

#endif