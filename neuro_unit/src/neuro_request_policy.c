#include <stdbool.h>
#include <string.h>

#include "neuro_request_envelope.h"
#include "neuro_request_policy.h"

#define NEURO_REQ_FLAGS_WRITE                                                  \
	(NEURO_REQ_META_REQUIRE_COMMON | NEURO_REQ_META_REQUIRE_PRIORITY |     \
		NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY)
#define NEURO_REQ_FLAGS_PROTECTED_WRITE                                        \
	(NEURO_REQ_FLAGS_WRITE | NEURO_REQ_META_REQUIRE_LEASE_ID)

static bool has_suffix(const char *value, const char *suffix)
{
	size_t value_len;
	size_t suffix_len;

	if (value == NULL || suffix == NULL) {
		return false;
	}

	value_len = strlen(value);
	suffix_len = strlen(suffix);
	if (value_len < suffix_len) {
		return false;
	}

	return strcmp(value + value_len - suffix_len, suffix) == 0;
}

uint32_t neuro_request_policy_required_fields_for_command(const char *key)
{
	if (key == NULL) {
		return 0U;
	}

	if (has_suffix(key, "/cmd/lease/acquire")) {
		return NEURO_REQ_FLAGS_WRITE;
	}

	if (has_suffix(key, "/cmd/lease/release") ||
		strstr(key, "/cmd/app/") != NULL) {
		return NEURO_REQ_FLAGS_PROTECTED_WRITE;
	}

	return 0U;
}

uint32_t neuro_request_policy_required_fields_for_query(const char *key)
{
	if (key == NULL) {
		return 0U;
	}

	if (has_suffix(key, "/query/device") ||
		has_suffix(key, "/query/apps") ||
		has_suffix(key, "/query/leases")) {
		return NEURO_REQ_META_REQUIRE_COMMON;
	}

	return 0U;
}

uint32_t neuro_request_policy_required_fields_for_update_action(
	const char *action)
{
	if (action == NULL) {
		return 0U;
	}

	if (strcmp(action, "prepare") == 0) {
		return NEURO_REQ_FLAGS_WRITE;
	}

	if (strcmp(action, "verify") == 0) {
		return NEURO_REQ_META_REQUIRE_COMMON;
	}

	if (strcmp(action, "activate") == 0) {
		return NEURO_REQ_FLAGS_PROTECTED_WRITE;
	}

	if (strcmp(action, "rollback") == 0) {
		return NEURO_REQ_FLAGS_PROTECTED_WRITE;
	}

	if (strcmp(action, "recover") == 0) {
		return NEURO_REQ_FLAGS_PROTECTED_WRITE;
	}

	return 0U;
}
