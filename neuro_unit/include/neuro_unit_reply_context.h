#ifndef NEURO_UNIT_REPLY_CONTEXT_H
#define NEURO_UNIT_REPLY_CONTEXT_H

#include <stdbool.h>
#include <stdint.h>

#include "neuro_request_envelope.h"

/**
 * Decoded action-specific fields carried beside the canonical request
 * metadata.
 *
 * The buffers are owned by the caller that creates the reply context and must
 * remain valid until the service handler returns. Empty strings and unset
 * `has_*` flags mean the field was absent on the wire. Lengths mirror the CBOR
 * DTO facade so services can prefer these fields without reparsing payloads.
 */
struct neuro_unit_request_fields {
	char resource[64];
	uint32_t ttl_ms;
	char start_args[96];
	char reason[64];
	char transport[32];
	char artifact_key[96];
	uint32_t size;
	uint32_t chunk_size;
	bool has_callback_enabled;
	bool callback_enabled;
	bool has_trigger_every;
	int32_t trigger_every;
	bool has_event_name;
	char event_name[32];
};

/**
 * Request/reply context shared by transport adapters and Unit services.
 *
 * `transport_query` is an opaque transport-owned query pointer. Services must
 * pass it back through callbacks only and must not dereference it.
 * `request_id`, `metadata`, and `request_fields` are borrowed references that
 * remain valid for the duration of the current dispatch call.
 */
struct neuro_unit_reply_context {
	const void *transport_query;
	const char *request_id;
	const struct neuro_request_metadata *metadata;
	const struct neuro_unit_request_fields *request_fields;
};

/** Return the context request id when present, otherwise `fallback`. */
static inline const char *neuro_unit_reply_context_request_id(
	const struct neuro_unit_reply_context *reply_ctx, const char *fallback)
{
	if (reply_ctx != NULL && reply_ctx->request_id != NULL &&
		reply_ctx->request_id[0] != '\0') {
		return reply_ctx->request_id;
	}

	return fallback;
}

/** Return decoded metadata borrowed from the current request context. */
static inline const struct neuro_request_metadata *
neuro_unit_reply_context_metadata(
	const struct neuro_unit_reply_context *reply_ctx)
{
	return reply_ctx != NULL ? reply_ctx->metadata : NULL;
}

/** Return decoded action fields borrowed from the current request context. */
static inline const struct neuro_unit_request_fields *
neuro_unit_reply_context_request_fields(
	const struct neuro_unit_reply_context *reply_ctx)
{
	return reply_ctx != NULL ? reply_ctx->request_fields : NULL;
}

#endif
