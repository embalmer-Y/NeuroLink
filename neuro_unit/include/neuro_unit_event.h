/* SPDX-License-Identifier: Apache-2.0 */

#ifndef NEURO_UNIT_EVENT_H
#define NEURO_UNIT_EVENT_H

#include <stddef.h>

#include "neuro_unit_app_api.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_UNIT_EVENT_KEY_LEN 128
#define NEURO_UNIT_EVENT_NODE_ID_LEN 32

typedef int (*neuro_unit_event_publish_fn)(
	const char *keyexpr, const char *payload_json, void *ctx);

int neuro_unit_event_configure(
	const char *node_id, neuro_unit_event_publish_fn publish_fn, void *ctx);
void neuro_unit_event_reset(void);
int neuro_unit_event_build_key(
	char *out, size_t out_len, const char *node_id, const char *suffix);
int neuro_unit_event_build_app_key(char *out, size_t out_len,
	const char *node_id, const char *app_id, const char *event_name);
int neuro_unit_event_publish(const char *keyexpr, const char *payload_json);

#ifdef __cplusplus
}
#endif

#endif
