#ifndef APP_RUNTIME_EXCEPTION_H
#define APP_RUNTIME_EXCEPTION_H

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum app_rt_exception_code {
	APP_RT_EX_NONE = 0,
	APP_RT_EX_INVALID_ARGUMENT,
	APP_RT_EX_NOT_FOUND,
	APP_RT_EX_NOT_SUPPORTED,
	APP_RT_EX_STATE_CONFLICT,
	APP_RT_EX_ALREADY_EXISTS,
	APP_RT_EX_RESOURCE_LIMIT,
	APP_RT_EX_IO_FAILURE,
	APP_RT_EX_NETWORK_FAILURE,
	APP_RT_EX_SYMBOL_MISSING,
	APP_RT_EX_LOAD_FAILURE,
	APP_RT_EX_APP_CALLBACK_FAILURE,
	APP_RT_EX_INTERNAL,
};

struct app_rt_exception {
	enum app_rt_exception_code code;
	int cause;
	char component[16];
	char operation[24];
};

int app_rt_raise(const char *component, const char *operation,
	enum app_rt_exception_code code, int cause);
int app_rt_raise_errno(
	const char *component, const char *operation, int errno_value);

void app_rt_clear_last_exception(void);
void app_rt_get_last_exception(struct app_rt_exception *out_exc);

const char *app_rt_exception_code_str(enum app_rt_exception_code code);
const char *app_rt_strerror(int err, char *buf, size_t buf_len);
enum app_rt_exception_code app_rt_exception_from_errno(int errno_value);
bool app_rt_is_framework_error(int err);

#ifdef __cplusplus
}
#endif

#endif
