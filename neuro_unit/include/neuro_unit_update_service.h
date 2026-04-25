#ifndef NEURO_UNIT_UPDATE_SERVICE_H
#define NEURO_UNIT_UPDATE_SERVICE_H

#include <stdbool.h>

#include "neuro_artifact_store.h"
#include "neuro_recovery_seed_store.h"
#include "neuro_request_envelope.h"
#include "neuro_unit_reply_context.h"
#include "neuro_update_manager.h"

struct neuro_unit_update_service_ctx {
	struct neuro_update_manager *update_manager;
	struct neuro_artifact_store *artifact_store;
	struct neuro_recovery_seed_store *recovery_seed_store;
};

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
	void (*publish_update_event)(const char *app_id, const char *stage,
		const char *status, const char *message);
	void (*publish_state_event)(void);
	bool (*runtime_app_is_loaded)(const char *app_id);
	void (*register_app_callback_command)(const char *app_id);
	void (*log_transaction)(const char *app_id, const char *action,
		const char *request_id, const char *phase, int code,
		const char *detail);
};

struct neuro_unit_update_service {
	struct neuro_unit_update_service_ctx ctx;
	const struct neuro_unit_update_service_ops *ops;
	bool recovery_seed_initialized;
};

int neuro_unit_update_service_init(struct neuro_unit_update_service *service,
	const struct neuro_unit_update_service_ctx *ctx,
	const struct neuro_unit_update_service_ops *ops);

int neuro_unit_update_service_ensure_recovery_seed_initialized(
	struct neuro_unit_update_service *service);

void neuro_unit_update_service_handle_action(
	struct neuro_unit_update_service *service,
	const struct neuro_unit_reply_context *reply_ctx, const char *app_id,
	const char *action, const char *payload, const char *request_id);

#endif
