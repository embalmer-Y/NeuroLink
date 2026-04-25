#ifndef APP_RUNTIME_H
#define APP_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>

#include "app_runtime_exception.h"
#include "app_runtime_manifest.h"

#ifdef __cplusplus
extern "C" {
#endif

#define APP_RT_STATUS_SNAPSHOT_CAPACITY 4
#define APP_RT_MAX_APPS APP_RT_STATUS_SNAPSHOT_CAPACITY
#define APP_RT_POLICY_NO_LIMIT ((size_t)-1)
#define APP_RT_MAX_START_ARG_PAIRS 8
#define APP_RT_START_ARG_KEY_MAX_LEN 23
#define APP_RT_START_ARG_VAL_MAX_LEN 63

enum app_runtime_state {
	APP_RT_UNLOADED = 0,
	APP_RT_LOADED,
	APP_RT_INITIALIZED,
	APP_RT_RUNNING,
	APP_RT_SUSPENDED,
};

struct app_runtime_start_arg_pair {
	char key[APP_RT_START_ARG_KEY_MAX_LEN + 1];
	char value[APP_RT_START_ARG_VAL_MAX_LEN + 1];
};

struct app_runtime_start_args {
	const char *raw;
	size_t pair_count;
	struct app_runtime_start_arg_pair pairs[APP_RT_MAX_START_ARG_PAIRS];
};

struct app_runtime_policy {
	size_t max_loaded_apps;
	size_t max_running_apps;
	bool allow_preemptive_suspend;
};

struct app_runtime_app_status {
	enum app_runtime_state state;
	char name[32];
	char path[128];
	unsigned int priority;
	bool auto_suspended;
	bool manifest_present;
	struct app_runtime_manifest manifest;
};

struct app_runtime_capacity_status {
	size_t max_loaded_apps;
	size_t max_running_apps;
	bool allow_preemptive_suspend;
};

struct app_runtime_status {
	size_t app_count;
	size_t listed_app_count;
	size_t running_count;
	size_t suspended_count;
	bool listed_app_count_truncated;
	struct app_runtime_capacity_status capacity;
	struct app_rt_exception last_exception;
	struct app_runtime_app_status apps[APP_RT_STATUS_SNAPSHOT_CAPACITY];
};

static inline size_t app_runtime_status_listed_count(
	const struct app_runtime_status *status)
{
	if (status == NULL) {
		return 0U;
	}

	return status->listed_app_count;
}

static inline bool app_runtime_policy_limit_is_unbounded(size_t limit)
{
	return limit == APP_RT_POLICY_NO_LIMIT;
}

int app_runtime_init(void);
int app_runtime_set_policy(const struct app_runtime_policy *policy);
void app_runtime_get_policy(struct app_runtime_policy *policy);
int app_runtime_load(const char *name, const char *path);
int app_runtime_start(const char *name, const char *start_args);
int app_runtime_suspend(const char *name);
int app_runtime_resume(const char *name);
int app_runtime_stop(const char *name);
int app_runtime_unload(const char *name);
bool app_runtime_supports_command_callback(const char *name);
int app_runtime_dispatch_command(const char *name, const char *command_name,
	const char *request_json, char *reply_buf, size_t reply_buf_len);
void app_runtime_get_status(struct app_runtime_status *status);

#ifdef __cplusplus
}
#endif

#endif
