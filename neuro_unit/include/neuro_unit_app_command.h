#ifndef NEURO_UNIT_APP_COMMAND_H
#define NEURO_UNIT_APP_COMMAND_H

#include <stdbool.h>

#include "neuro_request_envelope.h"
#include "neuro_unit_reply_context.h"

struct neuro_unit_app_command_ops {
	const char *node_id;
	void (*reply_error)(const struct neuro_unit_reply_context *reply_ctx,
		const char *request_id, const char *message, int status_code);
	bool (*require_resource_lease_or_reply)(
		const struct neuro_unit_reply_context *reply_ctx,
		const char *request_id, const char *resource,
		const struct neuro_request_metadata *metadata);
	void (*query_reply_json)(
		const struct neuro_unit_reply_context *reply_ctx,
		const char *json);
	void (*publish_state_event)(void);
};

void neuro_unit_handle_app_command(
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id,
	const struct neuro_unit_app_command_ops *ops);

#endif
