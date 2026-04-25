#ifndef NEURO_REQUEST_POLICY_H
#define NEURO_REQUEST_POLICY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

uint32_t neuro_request_policy_required_fields_for_command(const char *key);
uint32_t neuro_request_policy_required_fields_for_query(const char *key);
uint32_t neuro_request_policy_required_fields_for_update_action(
	const char *action);

#ifdef __cplusplus
}
#endif

#endif
