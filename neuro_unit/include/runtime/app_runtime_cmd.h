#ifndef APP_RUNTIME_CMD_H
#define APP_RUNTIME_CMD_H

#include <stdbool.h>

#include "app_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

enum app_runtime_cmd_id {
	APP_RT_CMD_STORAGE_MOUNT = 0,
	APP_RT_CMD_STORAGE_UNMOUNT,
	APP_RT_CMD_NETWORK_CONNECT,
	APP_RT_CMD_NETWORK_DISCONNECT,
	APP_RT_CMD_LOAD,
	APP_RT_CMD_START,
	APP_RT_CMD_SUSPEND,
	APP_RT_CMD_RESUME,
	APP_RT_CMD_STOP,
	APP_RT_CMD_UNLOAD,
};

/*
 * Runtime-visible capability gate. Disabled items must return NOT_SUPPORTED
 * instead of attempting best-effort execution.
 */
struct app_runtime_cmd_support {
	struct {
		bool mount;
		bool unmount;
	} storage;
	struct {
		bool connect;
		bool disconnect;
	} network;
};

/* Generic runtime lifecycle operations for loaded applications. */
struct app_runtime_ops {
	int (*load)(const char *name, const char *path);
	int (*start)(const char *name, const char *start_args);
	int (*suspend)(const char *name);
	int (*resume)(const char *name);
	int (*stop)(const char *name);
	int (*unload)(const char *name);
	void (*get_status)(struct app_runtime_status *status);
};

/*
 * Unified command configuration assembled by the port layer during init.
 * apps_dir/seed_path define board-specific persistence locations.
 */
struct app_runtime_cmd_config {
	struct app_runtime_cmd_support support;
	struct app_runtime_ops runtime_ops;
	const char *apps_dir;
	const char *seed_path;
};

int app_runtime_cmd_set_config(const struct app_runtime_cmd_config *cfg);
const struct app_runtime_cmd_config *app_runtime_cmd_get_config(void);

int app_runtime_cmd_get_status(struct app_runtime_status *status);
int app_runtime_cmd_exec(
	enum app_runtime_cmd_id cmd, const char *arg1, const char *arg2);

#ifdef __cplusplus
}
#endif

#endif
