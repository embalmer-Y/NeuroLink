#include <zephyr/sys/printk.h>

#include <string.h>

#include "app_runtime.h"
#include "neuro_app_callback_bridge.h"
#include "neuro_app_command_registry.h"
#include "neuro_request_envelope.h"
#include "neuro_unit_app_command.h"

#define NEURO_UNIT_APP_COMMAND_JSON_LEN 1024

void neuro_unit_handle_app_command(
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id,
	const struct neuro_unit_app_command_ops *ops)
{
	struct neuro_request_metadata metadata;
	struct neuro_app_command_desc app_cmd;
	char start_args[96] = "";
	char resource[64];
	char json[NEURO_UNIT_APP_COMMAND_JSON_LEN];
	char callback_reply[160];
	int ret;

	if (reply_ctx == NULL || app_id == NULL || action == NULL ||
		payload == NULL || request_id == NULL || ops == NULL ||
		ops->node_id == NULL || ops->reply_error == NULL ||
		ops->require_resource_lease_or_reply == NULL ||
		ops->query_reply_json == NULL ||
		ops->publish_state_event == NULL) {
		return;
	}

	neuro_request_metadata_init(&metadata);
	(void)neuro_request_metadata_parse(payload, &metadata);

	ret = neuro_app_command_registry_find(app_id, action, &app_cmd);
	if (ret == 0) {
		if (app_cmd.state != NEURO_APPCMD_STATE_ENABLED) {
			ops->reply_error(reply_ctx, request_id,
				"app command disabled", 409);
			return;
		}

		if (app_cmd.lease_required) {
			snprintk(resource, sizeof(resource), "app/%s/control",
				app_id);
			if (!ops->require_resource_lease_or_reply(reply_ctx,
				    request_id, resource, &metadata)) {
				return;
			}
		}

		ret = neuro_app_callback_bridge_dispatch(app_id, action,
			payload, callback_reply, sizeof(callback_reply));
		if (ret) {
			ops->reply_error(reply_ctx, request_id,
				"app callback dispatch failed", 500);
			return;
		}

		snprintk(json, sizeof(json),
			"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_id\":\"%s\",\"action\":\"%s\",\"dispatch\":\"callback\",\"reply\":%s}",
			request_id, ops->node_id, app_id, action,
			callback_reply[0] ? callback_reply : "{}");
		ops->query_reply_json(reply_ctx, json);
		return;
	}

	snprintk(resource, sizeof(resource), "app/%s/control", app_id);
	if (!ops->require_resource_lease_or_reply(
		    reply_ctx, request_id, resource, &metadata)) {
		return;
	}

	if (strcmp(action, "start") == 0) {
		(void)neuro_json_extract_string(
			payload, "start_args", start_args, sizeof(start_args));
		ret = app_runtime_start(
			app_id, start_args[0] ? start_args : NULL);
		if (!ret) {
			(void)neuro_app_command_registry_set_app_enabled(
				app_id, true);
		}
	} else if (strcmp(action, "stop") == 0) {
		ret = app_runtime_stop(app_id);
		if (!ret) {
			(void)neuro_app_command_registry_set_app_enabled(
				app_id, false);
		}
	} else {
		ops->reply_error(
			reply_ctx, request_id, "unsupported app command", 404);
		return;
	}

	if (ret) {
		ops->reply_error(reply_ctx, request_id,
			"app runtime command failed", 500);
		return;
	}

	ops->publish_state_event();
	snprintk(json, sizeof(json),
		"{\"status\":\"ok\",\"request_id\":\"%s\",\"node_id\":\"%s\",\"app_id\":\"%s\",\"action\":\"%s\"}",
		request_id, ops->node_id, app_id, action);
	ops->query_reply_json(reply_ctx, json);
}
