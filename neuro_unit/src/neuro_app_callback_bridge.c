#include <errno.h>

#include <zephyr/sys/printk.h>

#include "app_runtime.h"
#include "neuro_app_callback_bridge.h"

int neuro_app_callback_bridge_dispatch(const char *app_id,
	const char *command_name, const char *request_json, char *reply_buf,
	size_t reply_buf_len)
{
	int ret;

	if (reply_buf != NULL && reply_buf_len > 0U) {
		reply_buf[0] = '\0';
	}

	ret = app_runtime_dispatch_command(app_id, command_name,
		request_json ? request_json : "{}", reply_buf, reply_buf_len);

	if (ret == 0 && reply_buf != NULL && reply_buf_len > 0U &&
		reply_buf[0] == '\0') {
		snprintk(reply_buf, reply_buf_len, "{}");
	}

	return ret;
}
