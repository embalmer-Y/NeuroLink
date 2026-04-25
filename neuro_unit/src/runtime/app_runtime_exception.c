#include <zephyr/kernel.h>

#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "app_runtime_exception.h"

#define APP_RT_ERR_BASE 0x5000

static struct app_rt_exception g_last_exception;
static struct k_mutex g_exc_lock;
static bool g_exc_ready;

static int app_rt_error_from_code(enum app_rt_exception_code code)
{
	if (code == APP_RT_EX_NONE) {
		return 0;
	}

	return -(APP_RT_ERR_BASE + (int)code);
}

static enum app_rt_exception_code app_rt_code_from_error(int err)
{
	if (err >= 0) {
		return APP_RT_EX_NONE;
	}

	if (err <= -APP_RT_ERR_BASE) {
		int v = -err - APP_RT_ERR_BASE;

		if (v >= (int)APP_RT_EX_NONE && v <= (int)APP_RT_EX_INTERNAL) {
			return (enum app_rt_exception_code)v;
		}
	}

	return APP_RT_EX_INTERNAL;
}

static void app_rt_copy_text(char *dst, size_t dst_len, const char *src)
{
	if (dst_len == 0) {
		return;
	}

	if (src == NULL) {
		dst[0] = '\0';
		return;
	}

	snprintk(dst, dst_len, "%s", src);
}

static void app_rt_set_last_exception_locked(const char *component,
	const char *operation, enum app_rt_exception_code code, int cause)
{
	g_last_exception.code = code;
	g_last_exception.cause = cause;
	app_rt_copy_text(g_last_exception.component,
		sizeof(g_last_exception.component), component);
	app_rt_copy_text(g_last_exception.operation,
		sizeof(g_last_exception.operation), operation);
}

static void app_rt_ensure_ready(void)
{
	if (g_exc_ready) {
		return;
	}

	k_mutex_init(&g_exc_lock);
	memset(&g_last_exception, 0, sizeof(g_last_exception));
	g_exc_ready = true;
}

enum app_rt_exception_code app_rt_exception_from_errno(int errno_value)
{
	switch (-errno_value) {
	case EINVAL:
		return APP_RT_EX_INVALID_ARGUMENT;
	case ENOENT:
		return APP_RT_EX_NOT_FOUND;
	case ENOTSUP:
		return APP_RT_EX_NOT_SUPPORTED;
	case EALREADY:
		return APP_RT_EX_ALREADY_EXISTS;
	case EBUSY:
	case EAGAIN:
		return APP_RT_EX_STATE_CONFLICT;
	case ENOMEM:
	case ENOSPC:
		return APP_RT_EX_RESOURCE_LIMIT;
	case EHOSTUNREACH:
	case ECONNABORTED:
	case ECONNRESET:
	case ECONNREFUSED:
	case ETIMEDOUT:
		return APP_RT_EX_NETWORK_FAILURE;
	case EIO:
	case EBADMSG:
		return APP_RT_EX_IO_FAILURE;
	default:
		return APP_RT_EX_INTERNAL;
	}
}

int app_rt_raise(const char *component, const char *operation,
	enum app_rt_exception_code code, int cause)
{
	int err = app_rt_error_from_code(code);

	app_rt_ensure_ready();
	k_mutex_lock(&g_exc_lock, K_FOREVER);
	app_rt_set_last_exception_locked(component, operation, code, cause);
	k_mutex_unlock(&g_exc_lock);

	return err;
}

int app_rt_raise_errno(
	const char *component, const char *operation, int errno_value)
{
	enum app_rt_exception_code code;

	if (errno_value >= 0) {
		errno_value = -errno_value;
	}

	code = app_rt_exception_from_errno(errno_value);
	return app_rt_raise(component, operation, code, errno_value);
}

void app_rt_clear_last_exception(void)
{
	app_rt_ensure_ready();
	k_mutex_lock(&g_exc_lock, K_FOREVER);
	memset(&g_last_exception, 0, sizeof(g_last_exception));
	k_mutex_unlock(&g_exc_lock);
}

void app_rt_get_last_exception(struct app_rt_exception *out_exc)
{
	if (out_exc == NULL) {
		return;
	}

	app_rt_ensure_ready();
	k_mutex_lock(&g_exc_lock, K_FOREVER);
	*out_exc = g_last_exception;
	k_mutex_unlock(&g_exc_lock);
}

const char *app_rt_exception_code_str(enum app_rt_exception_code code)
{
	switch (code) {
	case APP_RT_EX_NONE:
		return "NONE";
	case APP_RT_EX_INVALID_ARGUMENT:
		return "INVALID_ARGUMENT";
	case APP_RT_EX_NOT_FOUND:
		return "NOT_FOUND";
	case APP_RT_EX_NOT_SUPPORTED:
		return "NOT_SUPPORTED";
	case APP_RT_EX_STATE_CONFLICT:
		return "STATE_CONFLICT";
	case APP_RT_EX_ALREADY_EXISTS:
		return "ALREADY_EXISTS";
	case APP_RT_EX_RESOURCE_LIMIT:
		return "RESOURCE_LIMIT";
	case APP_RT_EX_IO_FAILURE:
		return "IO_FAILURE";
	case APP_RT_EX_NETWORK_FAILURE:
		return "NETWORK_FAILURE";
	case APP_RT_EX_SYMBOL_MISSING:
		return "SYMBOL_MISSING";
	case APP_RT_EX_LOAD_FAILURE:
		return "LOAD_FAILURE";
	case APP_RT_EX_APP_CALLBACK_FAILURE:
		return "APP_CALLBACK_FAILURE";
	case APP_RT_EX_INTERNAL:
		return "INTERNAL";
	default:
		return "UNKNOWN";
	}
}

bool app_rt_is_framework_error(int err) { return err <= -APP_RT_ERR_BASE; }

const char *app_rt_strerror(int err, char *buf, size_t buf_len)
{
	enum app_rt_exception_code code;

	if (buf == NULL || buf_len == 0) {
		return "";
	}

	if (!app_rt_is_framework_error(err)) {
		snprintk(buf, buf_len, "errno(%d)", err);
		return buf;
	}

	code = app_rt_code_from_error(err);
	snprintk(buf, buf_len, "%s", app_rt_exception_code_str(code));
	return buf;
}
