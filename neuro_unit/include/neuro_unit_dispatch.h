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

struct neuro_unit_request_fields;

#define NEURO_UNIT_DISPATCH_APP_ID_LEN 32

/** Route class selected from a transport key expression. */
enum neuro_unit_dispatch_route_kind {
	NEURO_UNIT_DISPATCH_ROUTE_INVALID = 0,
	NEURO_UNIT_DISPATCH_ROUTE_LEASE_ACQUIRE,
	NEURO_UNIT_DISPATCH_ROUTE_LEASE_RELEASE,
	NEURO_UNIT_DISPATCH_ROUTE_APP_ACTION,
	NEURO_UNIT_DISPATCH_ROUTE_QUERY_DEVICE,
	NEURO_UNIT_DISPATCH_ROUTE_QUERY_APPS,
	NEURO_UNIT_DISPATCH_ROUTE_QUERY_LEASES,
	NEURO_UNIT_DISPATCH_ROUTE_UPDATE_ACTION,
};

/** Parsed dispatch route. `action` points into the input key. */
struct neuro_unit_dispatch_route {
	enum neuro_unit_dispatch_route_kind kind;
	char app_id[NEURO_UNIT_DISPATCH_APP_ID_LEN];
	const char *action;
};

/**
 * Transport-route adapter boundary.
 *
 * This module is intentionally allowed to carry z_loaned_query_t because it
 * sits between neuro_unit.c's Zenoh query handlers and the application service
 * entry points. Application services must receive parsed app/action/request
 * data or neuro_unit_reply_context, not this dispatch ops surface directly.
 *
 * All function pointers are borrowed for the duration of a dispatch call. Reply
 * callbacks must be non-blocking with respect to service-owned locks. Handlers
 * receive borrowed strings and request metadata valid only until they return.
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
		const char *request_id,
		const struct neuro_request_metadata *metadata,
		const struct neuro_unit_request_fields *request_fields);

	void (*handle_query_device)(
		const z_loaned_query_t *query, const char *request_id);
	void (*handle_query_apps)(
		const z_loaned_query_t *query, const char *request_id);
	void (*handle_query_leases)(
		const z_loaned_query_t *query, const char *request_id);

	void (*handle_update_action)(const z_loaned_query_t *query,
		const char *app_id, const char *action, const char *payload,
		const char *request_id,
		const struct neuro_request_metadata *metadata,
		const struct neuro_unit_request_fields *request_fields);
};

/** Extract `<app_id>/<action>` from a route prefix. */
bool neuro_unit_dispatch_extract_app_route(const char *key, const char *prefix,
	char *app_id, size_t app_id_len, const char **action);
/** Classify command routes for lease and app command handlers. */
bool neuro_unit_dispatch_classify_command_route(const char *key,
	const char *node_id, struct neuro_unit_dispatch_route *route);
/** Classify query routes for device, app, and lease state handlers. */
bool neuro_unit_dispatch_classify_query_route(const char *key,
	const char *node_id, struct neuro_unit_dispatch_route *route);
/** Classify update routes for app lifecycle handlers. */
bool neuro_unit_dispatch_classify_update_route(const char *key,
	const char *node_id, struct neuro_unit_dispatch_route *route);

/** Validate, classify, and dispatch a command query. */
void neuro_unit_dispatch_command_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_request_fields *request_fields,
	const struct neuro_unit_dispatch_ops *ops);

/** Validate, classify, and dispatch a state query. */
void neuro_unit_dispatch_query_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_dispatch_ops *ops);

/** Validate, classify, recovery-gate, and dispatch an update query. */
void neuro_unit_dispatch_update_query(const z_loaned_query_t *query,
	const char *key, const char *payload,
	struct neuro_request_metadata *metadata,
	const struct neuro_unit_request_fields *request_fields,
	const struct neuro_unit_dispatch_ops *ops);

#endif
