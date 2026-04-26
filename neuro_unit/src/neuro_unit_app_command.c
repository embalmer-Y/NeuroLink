#include <zephyr/sys/printk.h>

#include <string.h>

#include "app_runtime.h"
#include "neuro_app_callback_bridge.h"
#include "neuro_app_command_registry.h"
#include "neuro_protocol_codec_cbor.h"
#include "neuro_request_envelope.h"
#include "neuro_unit_app_command.h"

#define NEURO_UNIT_APP_COMMAND_JSON_LEN 1024

static void query_reply_app_command(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *node_id, const char *app_id,
	const char *action, const char *json, const char *app_reply_json,
	const struct neuro_unit_app_command_ops *ops)
{
	char command_name[32];
	char event_name[NEURO_UNIT_APP_EVENT_NAME_LEN];
	char echo[64];
	int value;
	struct neuro_protocol_app_command_reply reply = {
		.command_name = action,
		.invoke_count = 0U,
		.callback_enabled = false,
		.trigger_every = 0,
		.event_name = "callback",
		.config_changed = false,
		.publish_ret = 0,
		.echo = app_id,
	};
	uint8_t cbor[256];
	size_t encoded_len = 0U;

	ARG_UNUSED(request_id);
	ARG_UNUSED(node_id);
	if (app_reply_json != NULL && app_reply_json[0] != '\0') {
		if (neuro_json_extract_string(app_reply_json, "command",
			    command_name, sizeof(command_name))) {
			reply.command_name = command_name;
		}

		value = neuro_json_extract_int(
			app_reply_json, "invoke_count", 0);
		if (value > 0) {
			reply.invoke_count = (unsigned int)value;
		}

		reply.callback_enabled = neuro_json_extract_bool(app_reply_json,
			"callback_enabled", reply.callback_enabled);
		reply.trigger_every = neuro_json_extract_int(
			app_reply_json, "trigger_every", 0);
		if (neuro_json_extract_string(app_reply_json, "event_name",
			    event_name, sizeof(event_name))) {
			reply.event_name = event_name;
		}
		reply.config_changed = neuro_json_extract_bool(
			app_reply_json, "config_changed", reply.config_changed);
		reply.publish_ret = neuro_json_extract_int(
			app_reply_json, "publish_ret", 0);
		if (neuro_json_extract_string(
			    app_reply_json, "echo", echo, sizeof(echo))) {
			reply.echo = echo;
		}
	}

	if (ops->query_reply_cbor != NULL &&
		neuro_protocol_encode_app_command_reply_cbor(
			cbor, sizeof(cbor), &reply, &encoded_len) == 0) {
		ops->query_reply_cbor(reply_ctx, cbor, encoded_len);
		return;
	}

	ops->query_reply_json(reply_ctx, json);
}

void neuro_unit_handle_app_command(
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id,
	const struct neuro_unit_app_command_ops *ops)
{
	struct neuro_request_metadata metadata;
	const struct neuro_request_metadata *request_metadata;
	const struct neuro_unit_request_fields *request_fields;
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

	request_metadata = neuro_unit_reply_context_metadata(reply_ctx);
	request_fields = neuro_unit_reply_context_request_fields(reply_ctx);
	if (request_metadata == NULL) {
		neuro_request_metadata_init(&metadata);
		(void)neuro_request_metadata_parse(payload, &metadata);
		request_metadata = &metadata;
	}

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
				    request_id, resource, request_metadata)) {
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
		query_reply_app_command(reply_ctx, request_id, ops->node_id,
			app_id, action, json, callback_reply, ops);
		return;
	}

	snprintk(resource, sizeof(resource), "app/%s/control", app_id);
	if (!ops->require_resource_lease_or_reply(
		    reply_ctx, request_id, resource, request_metadata)) {
		return;
	}

	if (strcmp(action, "start") == 0) {
		if (request_fields != NULL &&
			request_fields->start_args[0] != '\0') {
			snprintk(start_args, sizeof(start_args), "%s",
				request_fields->start_args);
		} else {
			(void)neuro_json_extract_string(payload, "start_args",
				start_args, sizeof(start_args));
		}
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
	query_reply_app_command(reply_ctx, request_id, ops->node_id, app_id,
		action, json, NULL, ops);
}
