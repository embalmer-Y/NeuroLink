/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_UNIT_EVENT_H
#define NEURO_UNIT_EVENT_H

#include <stddef.h>
#include <stdint.h>

#include "neuro_unit_app_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_UNIT_EVENT_KEY_LEN 128
#define NEURO_UNIT_EVENT_NODE_ID_LEN 32

/** Publish a UTF-8 JSON event payload for legacy hosts. */
typedef int (*neuro_unit_event_publish_fn)(
	const char *keyexpr, const char *payload_json, void *ctx);
/** Publish a binary event payload such as CBOR-v2. */
typedef int (*neuro_unit_event_publish_bytes_fn)(const char *keyexpr,
	const uint8_t *payload, size_t payload_len, void *ctx);

/** Configure JSON event publishing. Returns 0, -EINVAL, or -ENAMETOOLONG. */
int neuro_unit_event_configure(
	const char *node_id, neuro_unit_event_publish_fn publish_fn, void *ctx);
/** Configure binary event publishing. Returns 0, -EINVAL, or -ENAMETOOLONG. */
int neuro_unit_event_configure_bytes(const char *node_id,
	neuro_unit_event_publish_bytes_fn publish_fn, void *ctx);
/** Clear event module state; safe to call before reconfiguration. */
void neuro_unit_event_reset(void);
/** Build `neuro/<node_id>/event/<suffix>` into caller-owned storage. */
int neuro_unit_event_build_key(
	char *out, size_t out_len, const char *node_id, const char *suffix);
/** Build an app event key into caller-owned storage. */
int neuro_unit_event_build_app_key(char *out, size_t out_len,
	const char *node_id, const char *app_id, const char *event_name);
/** Publish JSON through the configured event sink. */
int neuro_unit_event_publish(const char *keyexpr, const char *payload_json);
/** Publish bytes through the configured event sink. */
int neuro_unit_event_publish_bytes(
	const char *keyexpr, const uint8_t *payload, size_t payload_len);
/** Publish a binary app event using the configured node id. */
int neuro_unit_publish_app_event_bytes(const char *app_id,
	const char *event_name, const uint8_t *payload, size_t payload_len);

#ifdef __cplusplus
}
#endif

#endif
