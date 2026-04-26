#ifndef NEURO_UNIT_UPDATE_SERVICE_H
#define NEURO_UNIT_UPDATE_SERVICE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "neuro_artifact_store.h"
#include "neuro_recovery_seed_store.h"
#include "neuro_request_envelope.h"
#include "neuro_unit_reply_context.h"
#include "neuro_update_manager.h"

/** Mutable dependencies owned by the Unit runtime and borrowed by service. */
struct neuro_unit_update_service_ctx {
	struct neuro_update_manager *update_manager;
	struct neuro_artifact_store *artifact_store;
	struct neuro_recovery_seed_store *recovery_seed_store;
};

/**
 * Callback table for update lifecycle side effects.
 *
 * Callbacks are borrowed and invoked synchronously. Reply callbacks own the
 * transport-specific response mechanics; update service code owns only the
 * lifecycle decision, event contents, and transaction phase classification.
 */
struct neuro_unit_update_service_ops {
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
	void (*publish_update_event)(const char *app_id, const char *stage,
		const char *status, const char *message);
	void (*publish_state_event)(void);
	bool (*runtime_app_is_loaded)(const char *app_id);
	int (*download_artifact)(const char *app_id, const char *artifact_key,
		size_t total_size, size_t chunk_size, const char *dst_path);
	void (*register_app_callback_command)(const char *app_id);
	void (*log_transaction)(const char *app_id, const char *action,
		const char *request_id, const char *phase, int code,
		const char *detail);
};

/** Update lifecycle service instance. Initialize before first use. */
struct neuro_unit_update_service {
	struct neuro_unit_update_service_ctx ctx;
	const struct neuro_unit_update_service_ops *ops;
	bool recovery_seed_initialized;
};

/** Initialize the update service. Returns 0 or -EINVAL for invalid contracts.
 */
int neuro_unit_update_service_init(struct neuro_unit_update_service *service,
	const struct neuro_unit_update_service_ctx *ctx,
	const struct neuro_unit_update_service_ops *ops);

/** Ensure persistent recovery seed state is ready. Returns 0 or storage errno.
 */
int neuro_unit_update_service_ensure_recovery_seed_initialized(
	struct neuro_unit_update_service *service);

/**
 * Handle one update lifecycle action.
 *
 * Strings and reply context are borrowed for the call. Decoded request fields
 * and metadata from `reply_ctx` are preferred over legacy JSON payload fields.
 */
void neuro_unit_update_service_handle_action(
	struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id);

#endif
