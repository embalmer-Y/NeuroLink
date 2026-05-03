/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/llext/symbol.h>
#include <zephyr/sys/printk.h>

#include <stdbool.h>
#include <stddef.h>

#include "app_runtime_manifest.h"
#include "neuro_unit_app_api.h"

static bool app_initialized;
static bool app_running;
static unsigned int publish_count;

static const char app_command_name[] = "invoke";
static const char app_id[] = "neuro_demo_net_event";
static const char app_version[] = "1.1.10";
static const char app_build_id[] = "neuro_demo_net_event-1.1.10-cbor-v1";
static const char default_event_name[] = "demo_event";
static const char default_message[] = "event_bridge_ready";

int app_runtime_priority = 88;

static bool str_eq(const char *lhs, const char *rhs)
{
	while (lhs != NULL && rhs != NULL) {
		if (*lhs != *rhs) {
			return false;
		}

		if (*lhs == '\0') {
			return true;
		}

		lhs++;
		rhs++;
	}

	return lhs == rhs;
}

static void write_capability_reply(char *reply_buf, size_t reply_buf_len)
{
	const neuro_unit_app_capability_report_t report = {
		.capability = "event_bridge",
		.available = true,
		.interface_name = "app_event_bridge",
		.detail = "publish_ready",
	};

	(void)neuro_unit_write_capability_report_json(
		reply_buf, reply_buf_len, &report);
}

static void write_publish_reply(char *reply_buf, size_t reply_buf_len,
	const char *event_name, int publish_ret)
{
	const struct neuro_unit_app_command_reply reply = {
		.command_name = app_command_name,
		.invoke_count = publish_count,
		.callback_enabled = false,
		.trigger_every = 0,
		.event_name = event_name,
		.config_changed = false,
		.publish_ret = publish_ret,
		.echo = app_build_id,
	};

	(void)neuro_unit_write_command_reply_json(
		reply_buf, reply_buf_len, &reply);
}

static void write_unsupported_reply(char *reply_buf, size_t reply_buf_len,
	const char *detail)
{
	const neuro_unit_app_unsupported_result_t result = {
		.status = "unsupported",
		.command_name = app_command_name,
		.capability = "event_bridge",
		.detail = detail,
	};

	(void)neuro_unit_write_unsupported_result_json(
		reply_buf, reply_buf_len, &result);
}

static int publish_demo_event(const char *event_name, const char *message)
{
	char payload_json[NEURO_UNIT_EVENT_JSON_LEN];

	if (snprintk(payload_json, sizeof(payload_json),
		"{\"app_id\":\"%s\",\"event_name\":\"%s\",\"publish_count\":%u,"
		"\"message\":\"%s\",\"echo\":\"%s\"}",
		app_id, event_name, publish_count, message, app_build_id) >=
		(int)sizeof(payload_json)) {
		return -12;
	}

	return neuro_unit_publish_app_event(app_id, event_name, payload_json);
}

const struct app_runtime_manifest app_runtime_manifest = {
	.abi_major = APP_RT_MANIFEST_ABI_MAJOR,
	.abi_minor = APP_RT_MANIFEST_ABI_MINOR,
	.version = {
		.major = 1,
		.minor = 1,
		.patch = 10,
	},
	.capability_flags = APP_RT_CAP_NETWORK,
	.resource = {
		.ram_bytes = 16U * 1024U,
		.stack_bytes = 4U * 1024U,
		.cpu_budget_percent = 20U,
	},
	.app_name = "neuro_demo_net_event",
	.dependency = "none",
};

int app_init(void)
{
	app_initialized = true;
	app_running = false;
	publish_count = 0U;
	(void)app_version;
	return 0;
}

int app_start(const char *args)
{
	(void)args;

	if (!app_initialized) {
		return -1;
	}

	app_running = true;
	return 0;
}

int app_suspend(void)
{
	if (!app_running) {
		return -1;
	}

	app_running = false;
	return 0;
}

int app_resume(void)
{
	if (!app_initialized || app_running) {
		return -1;
	}

	app_running = true;
	return 0;
}

int app_stop(void)
{
	if (!app_initialized) {
		return -1;
	}

	app_running = false;
	return 0;
}

int app_deinit(void)
{
	app_initialized = false;
	app_running = false;
	publish_count = 0U;
	return 0;
}

int app_on_command(const char *command_name, const char *request_json,
	char *reply_buf, size_t reply_buf_len)
{
	char action[24] = { 0 };
	char event_name[NEURO_UNIT_APP_EVENT_NAME_LEN] = { 0 };
	char message[48] = { 0 };
	int publish_ret;

	if (!app_initialized || !app_running) {
		return -1;
	}

	if (!str_eq(command_name, app_command_name)) {
		return -2;
	}

	if (!neuro_json_extract_string(request_json, "action", action,
		    sizeof(action))) {
		snprintk(action, sizeof(action), "%s", "publish");
	}

	if (str_eq(action, "capability")) {
		write_capability_reply(reply_buf, reply_buf_len);
		return 0;
	}

	if (!str_eq(action, "publish") && !str_eq(action, "selftest")) {
		write_unsupported_reply(reply_buf, reply_buf_len,
			"unknown_action");
		return 0;
	}

	if (!neuro_json_extract_string(request_json, "event_name", event_name,
		    sizeof(event_name))) {
		snprintk(event_name, sizeof(event_name), "%s", default_event_name);
	}
	if (!neuro_json_extract_string(request_json, "message", message,
		    sizeof(message))) {
		snprintk(message, sizeof(message), "%s", default_message);
	}

	publish_count++;
	publish_ret = publish_demo_event(event_name, message);
	write_publish_reply(reply_buf, reply_buf_len, event_name, publish_ret);
	return 0;
}

LL_EXTENSION_SYMBOL(app_init);
LL_EXTENSION_SYMBOL(app_start);
LL_EXTENSION_SYMBOL(app_suspend);
LL_EXTENSION_SYMBOL(app_resume);
LL_EXTENSION_SYMBOL(app_stop);
LL_EXTENSION_SYMBOL(app_deinit);
LL_EXTENSION_SYMBOL(app_on_command);
LL_EXTENSION_SYMBOL(app_command_name);
LL_EXTENSION_SYMBOL(app_runtime_priority);
LL_EXTENSION_SYMBOL(app_runtime_manifest);