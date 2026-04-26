#ifndef NEURO_UNIT_DIAG_H
#define NEURO_UNIT_DIAG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_UNIT_DIAG_CONTEXT_MAX_LEN 160

struct neuro_unit_diag_context {
	const char *request_id;
	const char *app_id;
	const char *route;
	const char *stage;
	int ret;
};

/** Format a bounded diagnostic context string into caller-owned storage. */
int neuro_unit_diag_format_context(
	char *out, size_t out_len, const struct neuro_unit_diag_context *ctx);
/** Log a generic operation result with request/app/route/stage context. */
void neuro_unit_diag_log_result(
	const char *operation, const struct neuro_unit_diag_context *ctx);

/** Log a bounded CBOR/protocol failure without dumping binary payload bytes. */
void neuro_unit_diag_protocol_failure(const char *route, const char *stage,
	const char *request_id, int ret, size_t payload_len);
/** Log route classification or dispatch outcomes without logging payloads. */
void neuro_unit_diag_dispatch_result(const char *family, const char *key,
	const char *request_id, const char *result, int code);
/** Log app callback command registration stages. */
void neuro_unit_diag_callback_registration(const char *app_id,
	const char *command_name, const char *stage, int ret);

void neuro_unit_diag_update_transaction(const char *app_id, const char *action,
	const char *request_id, const char *phase, int code,
	const char *detail);

void neuro_unit_diag_contract_error(
	const char *component, const char *field, int ret);
void neuro_unit_diag_event_attempt(const char *keyexpr, size_t payload_len);
void neuro_unit_diag_event_result(const char *keyexpr, int ret);

void neuro_unit_diag_state_transition_bool(
	const char *field, bool old_val, bool new_val, uint64_t version);
void neuro_unit_diag_state_transition_size(
	const char *field, size_t old_val, size_t new_val, uint64_t version);
void neuro_unit_diag_state_transition_text(const char *field,
	const char *old_val, const char *new_val, uint64_t version);
void neuro_unit_diag_state_transition_enum(const char *field,
	const char *old_val, const char *new_val, uint64_t version);
void neuro_unit_diag_state_snapshot(const char *reason, const char *node_id,
	uint64_t version, bool session_ready, const char *network_state,
	const char *health);

#ifdef __cplusplus
}
#endif

#endif
