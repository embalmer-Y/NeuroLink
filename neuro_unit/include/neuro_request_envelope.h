/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_REQUEST_ENVELOPE_H
#define NEURO_REQUEST_ENVELOPE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "neuro_unit_app_api.h"

#ifdef __cplusplus
extern "C" {
#endif

struct neuro_request_metadata {
	char request_id[32];
	char source_core[32];
	char source_agent[24];
	char target_node[32];
	char lease_id[32];
	char idempotency_key[32];
	uint32_t timeout_ms;
	int priority;
	bool forwarded;
};

enum neuro_request_metadata_requirements {
	NEURO_REQ_META_REQUIRE_REQUEST_ID = 1U << 0,
	NEURO_REQ_META_REQUIRE_SOURCE_CORE = 1U << 1,
	NEURO_REQ_META_REQUIRE_SOURCE_AGENT = 1U << 2,
	NEURO_REQ_META_REQUIRE_TARGET_NODE = 1U << 3,
	NEURO_REQ_META_REQUIRE_TIMEOUT_MS = 1U << 4,
	NEURO_REQ_META_REQUIRE_LEASE_ID = 1U << 5,
	NEURO_REQ_META_REQUIRE_IDEMPOTENCY_KEY = 1U << 6,
	NEURO_REQ_META_REQUIRE_PRIORITY = 1U << 7,
};

#define NEURO_REQ_META_REQUIRE_COMMON                                          \
	(NEURO_REQ_META_REQUIRE_REQUEST_ID |                                   \
		NEURO_REQ_META_REQUIRE_SOURCE_CORE |                           \
		NEURO_REQ_META_REQUIRE_SOURCE_AGENT |                          \
		NEURO_REQ_META_REQUIRE_TARGET_NODE |                           \
		NEURO_REQ_META_REQUIRE_TIMEOUT_MS)

void neuro_request_metadata_init(struct neuro_request_metadata *metadata);
bool neuro_request_metadata_parse(
	const char *json, struct neuro_request_metadata *metadata);
bool neuro_request_metadata_validate(
	const struct neuro_request_metadata *metadata, uint32_t required_fields,
	const char *expected_target_node, char *error_buf,
	size_t error_buf_len);
#ifdef __cplusplus
}
#endif

#endif
