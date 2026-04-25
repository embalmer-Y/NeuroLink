#ifndef NEURO_UNIT_DISPATCH_H
#define NEURO_UNIT_DISPATCH_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef NEURO_UNIT_OPAQUE_ZENOH_TYPES
typedef struct z_loaned_query_t z_loaned_query_t;
#else
#include <zenoh-pico.h>
#endif

#include "neuro_request_envelope.h"

/*
 * Transport-route adapter boundary.
 *
 * This module is intentionally allowed to carry z_loaned_query_t because it
 * sits between neuro_unit.c's Zenoh query handlers and the application service
 * entry points. Application services must receive parsed app/action/request
 * data or neuro_unit_reply_context, not this dispatch ops surface directly.
 */
struct neuro_unit_dispatch_ops {
	const char *node_id;
	bool (*transport_healthy)(void);
	void (*log_transport_health_snapshot)(
		const char *stage, const char *key, const char *request_id);
	bool (*validate_request_metadata_or_reply)(
		const z_loaned_query_t *query, const char *payload,
		struct neuro_request_metadata *metadata,
		uint32_t required_fields);
	int (*ensure_recovery_seed_initialized)(void);
	void (*reply_error)(const z_loaned_query_t *query,
		const char *request_id, const char *message, int status_code);

	void (*handle_lease_acquire)(const z_loaned_query_t *query,
		const char *payload, const char *request_id);
	void (*handle_lease_release)(const z_loaned_query_t *query,
		const char *payload, const char *request_id);
	void (*handle_app_action)(const z_loaned_query_t *query,
		const char *app_id, const char *action, const char *payload,
		const char *request_id);

	void (*handle_query_device)(
		const z_loaned_query_t *query, const char *request_id);
	void (*handle_query_apps)(
		const z_loaned_query_t *query, const char *request_id);
	void (*handle_query_leases)(
		const z_loaned_query_t *query, const char *request_id);

	void (*handle_update_action)(const z_loaned_query_t *query,
		const char *app_id, const char *action, const char *payload,
		const char *request_id);
};

bool neuro_unit_dispatch_extract_app_route(const char *key, const char *prefix,
	char *app_id, size_t app_id_len, const char **action);

void neuro_unit_dispatch_command_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops);

void neuro_unit_dispatch_query_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops);

void neuro_unit_dispatch_update_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops);

#endif
