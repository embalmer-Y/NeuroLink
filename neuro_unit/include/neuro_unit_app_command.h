#ifndef NEURO_UNIT_APP_COMMAND_H
#define NEURO_UNIT_APP_COMMAND_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "neuro_request_envelope.h"
#include "neuro_unit_reply_context.h"

/**
 * Callback table required by the app command service.
 *
 * The service never owns this structure. All callbacks are invoked
 * synchronously during `neuro_unit_handle_app_command()`. Reply callbacks
 * receive the same borrowed reply context passed to the service, allowing
 * transports to preserve their query lifetime rules.
 */
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
	void (*query_reply_cbor)(
		const struct neuro_unit_reply_context *reply_ctx,
		const uint8_t *payload, size_t payload_len);
	void (*publish_state_event)(void);
};

/**
 * Handle one app command action.
 *
 * `app_id`, `action`, `payload`, and `request_id` are borrowed for the call.
 * The service prefers decoded metadata and request fields from `reply_ctx`, but
 * keeps JSON payload fallback for compatibility. Errors are reported through
 * `ops->reply_error()`; this function does not return a status code.
 */
void neuro_unit_handle_app_command(
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id,
	const struct neuro_unit_app_command_ops *ops);

#endif
