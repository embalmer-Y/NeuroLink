#ifndef NEURO_APP_CALLBACK_BRIDGE_H
#define NEURO_APP_CALLBACK_BRIDGE_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Runtime callback adapter boundary.
 *
 * App command service owns registry lookup, lease policy, reply shaping, and
 * service-level error mapping. This bridge owns only the call into app_runtime
 * and the runtime callback reply-buffer normalization contract.
 */
int neuro_app_callback_bridge_dispatch(const char *app_id,
	const char *command_name, const char *request_json, char *reply_buf,
	size_t reply_buf_len);

#ifdef __cplusplus
}
#endif

#endif
