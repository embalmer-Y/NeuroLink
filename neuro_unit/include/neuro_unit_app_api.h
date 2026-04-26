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

struct neuro_unit_app_callback_config {
	bool has_callback_enabled;
	bool callback_enabled;
	bool has_trigger_every;
	int trigger_every;
	bool has_event_name;
	char event_name[NEURO_UNIT_APP_EVENT_NAME_LEN];
};

struct neuro_unit_app_callback_event {
	const char *app_id;
	const char *event_name;
	unsigned int invoke_count;
	int start_count;
};

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

int neuro_unit_publish_callback_event(
	const struct neuro_unit_app_callback_event *event);
int neuro_unit_write_command_reply_json(char *reply_buf, size_t reply_buf_len,
	const struct neuro_unit_app_command_reply *reply);
int neuro_unit_publish_app_event(
	const char *app_id, const char *event_name, const char *payload_json);
bool neuro_json_extract_string(
	const char *json, const char *key, char *out, size_t out_len);
int neuro_json_extract_int(
	const char *json, const char *key, int default_value);
bool neuro_json_extract_bool(
	const char *json, const char *key, bool default_value);
int neuro_unit_read_callback_config_json(
	const char *json, struct neuro_unit_app_callback_config *config);

#ifdef __cplusplus
}
#endif

#endif
