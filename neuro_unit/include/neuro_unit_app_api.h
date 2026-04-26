/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_UNIT_APP_API_H
#define NEURO_UNIT_APP_API_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Stable helpers intentionally exposed to standalone LLEXT apps. */
#define NEURO_UNIT_EVENT_JSON_LEN 256
#define NEURO_UNIT_APP_EVENT_NAME_LEN 32

/**
 * Optional callback behavior decoded from an app command payload.
 *
 * `has_*` flags distinguish absent fields from explicit false or zero values.
 * The event name buffer is owned by the caller and always NUL-terminated after
 * a successful decode.
 */
struct neuro_unit_app_callback_config {
	bool has_callback_enabled;
	bool callback_enabled;
	bool has_trigger_every;
	int trigger_every;
	bool has_event_name;
	char event_name[NEURO_UNIT_APP_EVENT_NAME_LEN];
};

/** Callback event DTO published by an app through the Unit event bridge. */
struct neuro_unit_app_callback_event {
	const char *app_id;
	const char *event_name;
	unsigned int invoke_count;
	int start_count;
};

/**
 * App command reply DTO for app-owned command handlers.
 *
 * String pointers are borrowed for the duration of the helper call. The writer
 * copies them into caller-owned JSON output storage and returns a negative
 * errno when the contract is invalid or the output buffer is too small.
 */
struct neuro_unit_app_command_reply {
	const char *command_name;
	unsigned int invoke_count;
	bool callback_enabled;
	int trigger_every;
	const char *event_name;
	bool config_changed;
	int publish_ret;
	const char *echo;
};

/** Publish a typed callback event through the configured Unit event bridge. */
int neuro_unit_publish_callback_event(
	const struct neuro_unit_app_callback_event *event);
/** Serialize an app command reply into caller-owned JSON storage. */
int neuro_unit_write_command_reply_json(char *reply_buf, size_t reply_buf_len,
	const struct neuro_unit_app_command_reply *reply);
/** Publish an app-owned JSON event payload. */
int neuro_unit_publish_app_event(
	const char *app_id, const char *event_name, const char *payload_json);
/** Extract a JSON string field into caller-owned storage. */
bool neuro_json_extract_string(
	const char *json, const char *key, char *out, size_t out_len);
/** Extract a JSON integer field or return `default_value` when absent. */
int neuro_json_extract_int(
	const char *json, const char *key, int default_value);
/** Extract a JSON boolean field or return `default_value` when absent. */
bool neuro_json_extract_bool(
	const char *json, const char *key, bool default_value);
/** Decode callback config JSON into caller-owned config storage. */
int neuro_unit_read_callback_config_json(
	const char *json, struct neuro_unit_app_callback_config *config);

#ifdef __cplusplus
}
#endif

#endif
