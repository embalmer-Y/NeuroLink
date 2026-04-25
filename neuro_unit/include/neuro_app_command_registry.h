#ifndef NEURO_APP_COMMAND_REGISTRY_H
#define NEURO_APP_COMMAND_REGISTRY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_APP_ID_MAX_LEN 31
#define NEURO_APP_COMMAND_NAME_MAX_LEN 31

enum neuro_app_command_state {
	NEURO_APPCMD_STATE_UNREGISTERED = 0,
	NEURO_APPCMD_STATE_REGISTERING,
	NEURO_APPCMD_STATE_REGISTERED,
	NEURO_APPCMD_STATE_ENABLED,
	NEURO_APPCMD_STATE_DISABLED,
	NEURO_APPCMD_STATE_FAILED,
	NEURO_APPCMD_STATE_REMOVED,
};

struct neuro_app_command_desc {
	char app_id[NEURO_APP_ID_MAX_LEN + 1];
	char command_name[NEURO_APP_COMMAND_NAME_MAX_LEN + 1];
	uint8_t visibility;
	bool lease_required;
	bool idempotent;
	uint32_t timeout_ms;
	uint8_t state;
};

int neuro_app_command_registry_init(void);
int neuro_app_command_registry_register(
	const struct neuro_app_command_desc *desc);
int neuro_app_command_registry_register_descriptors(const char *app_id,
	const struct neuro_app_command_desc *descs, size_t desc_count);
int neuro_app_command_registry_set_enabled(
	const char *app_id, const char *command_name, bool enabled);
int neuro_app_command_registry_set_app_enabled(
	const char *app_id, bool enabled);
int neuro_app_command_registry_remove_app(const char *app_id);
int neuro_app_command_registry_find(const char *app_id,
	const char *command_name, struct neuro_app_command_desc *out);

#ifdef __cplusplus
}
#endif

#endif
