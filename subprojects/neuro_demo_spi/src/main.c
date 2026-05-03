/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/llext/symbol.h>
#include <zephyr/devicetree.h>
#include <zephyr/device.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/sys/printk.h>

#include <stdbool.h>
#include <stddef.h>

#include "app_runtime_manifest.h"
#include "neuro_unit_app_api.h"

#define SPI_DEMO_NODE DT_NODELABEL(spi3)

#if DT_NODE_HAS_STATUS(SPI_DEMO_NODE, okay)
static const struct device *const spi_device = DEVICE_DT_GET(SPI_DEMO_NODE);
#define SPI_DEMO_HAS_DEVICE 1
#else
static const struct device *const spi_device;
#define SPI_DEMO_HAS_DEVICE 0
#endif

static bool app_initialized;
static bool app_running;
static bool spi_ready;
static int start_count;
static bool callback_enabled;
static int callback_trigger_every;
static unsigned int command_count;
static char callback_event_name[NEURO_UNIT_APP_EVENT_NAME_LEN] = "callback";

static const char app_command_name[] = "invoke";
static const char app_id[] = "neuro_demo_spi";
static const char app_version[] = "1.1.10";
static const char app_build_id[] = "neuro_demo_spi-1.1.10-cbor-v1";
static const char default_event_name[] = "spi_probe";
static const char capability_name[] = "spi";

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

static bool extract_args_object(const char *request_json, char *args_json,
	size_t args_json_len)
{
	const char pattern[] = { '"', 'a', 'r', 'g', 's', '"', ':', '\0' };
	const char *key = NULL;
	const char *cursor;
	bool in_string = false;
	bool escaped = false;
	int depth = 0;
	size_t len;

	if (request_json == NULL || args_json == NULL || args_json_len == 0U) {
		return false;
	}

	for (const char *candidate = request_json; *candidate != '\0';
		candidate++) {
		size_t index = 0U;

		while (pattern[index] != '\0' &&
		       candidate[index] == pattern[index]) {
			index++;
		}

		if (pattern[index] == '\0') {
			key = candidate;
			break;
		}
	}

	if (key == NULL) {
		return false;
	}

	cursor = key + 7;
	while (*cursor == ' ' || *cursor == '\t' || *cursor == '\r' ||
	       *cursor == '\n') {
		cursor++;
	}

	if (*cursor != '{') {
		return false;
	}

	for (const char *end = cursor; *end != '\0'; end++) {
		char ch = *end;

		if (escaped) {
			escaped = false;
			continue;
		}

		if (ch == '\\') {
			escaped = in_string;
			continue;
		}

		if (ch == '"') {
			in_string = !in_string;
			continue;
		}

		if (in_string) {
			continue;
		}

		if (ch == '{') {
			depth++;
		} else if (ch == '}') {
			depth--;
			if (depth == 0) {
				len = (size_t)(end - cursor + 1);
				if (len >= args_json_len) {
					return false;
				}
				for (size_t index = 0U; index < len; index++) {
					args_json[index] = cursor[index];
				}
				args_json[len] = '\0';
				return true;
			}
		}
	}

	return false;
}

static const char *command_args_json(const char *request_json, char *args_json,
	size_t args_json_len)
{
	if (extract_args_object(request_json, args_json, args_json_len)) {
		return args_json;
	}

	return request_json;
}

static const char *spi_interface_name(void)
{
	if (SPI_DEMO_HAS_DEVICE) {
		return "spi3";
	}

	return "none";
}

static const char *spi_detail(void)
{
	if (!SPI_DEMO_HAS_DEVICE) {
		return "spi3_missing";
	}

	if (!spi_ready) {
		return "spi3_not_ready";
	}

	return "shared_sd_spi_probe_only";
}

static bool command_updates_callback_config(const char *request_json)
{
	struct neuro_unit_app_callback_config config;
	bool changed = false;

	if (request_json == NULL) {
		return false;
	}

	if (neuro_unit_read_callback_config_json(request_json, &config) != 0) {
		return false;
	}

	if (config.has_callback_enabled &&
	    config.callback_enabled != callback_enabled) {
		callback_enabled = config.callback_enabled;
		changed = true;
	}

	if (config.has_trigger_every) {
		if (config.trigger_every < 0) {
			config.trigger_every = 0;
		}
		if (config.trigger_every != callback_trigger_every) {
			callback_trigger_every = config.trigger_every;
			changed = true;
		}
	}

	if (config.has_event_name) {
		snprintk(callback_event_name, sizeof(callback_event_name), "%s",
			config.event_name);
		changed = true;
	}

	return changed;
}

static int maybe_publish_callback_event(void)
{
	const struct neuro_unit_app_callback_event event = {
		.app_id = app_id,
		.event_name = callback_event_name,
		.invoke_count = command_count,
		.start_count = start_count,
	};

	if (!callback_enabled || callback_trigger_every <= 0) {
		return 0;
	}

	if ((command_count % (unsigned int)callback_trigger_every) != 0U) {
		return 0;
	}

	return neuro_unit_publish_callback_event(&event);
}

static void write_capability_reply(char *reply_buf, size_t reply_buf_len)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"ok\",\"command\":\"capability\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"ready\":%s,\"detail\":\"%s\"," \
		"\"invoke_count\":%u,\"callback_enabled\":%s," \
		"\"trigger_every\":%d,\"event_name\":\"%s\"," \
		"\"config_changed\":false,\"publish_ret\":0," \
		"\"echo\":\"%s\"}",
		capability_name, spi_interface_name(),
		spi_ready ? "true" : "false", spi_detail(), command_count,
		callback_enabled ? "true" : "false", callback_trigger_every,
		callback_event_name, app_build_id);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static void write_unsupported_reply(char *reply_buf, size_t reply_buf_len,
	const char *command_name, const char *detail)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"capability_missing\"," \
		"\"command\":\"%s\",\"capability\":\"%s\"," \
		"\"interface\":\"%s\",\"detail\":\"%s\"," \
		"\"invoke_count\":%u,\"callback_enabled\":%s," \
		"\"trigger_every\":%d,\"event_name\":\"%s\"," \
		"\"config_changed\":false,\"publish_ret\":0," \
		"\"echo\":\"%s\"}",
		command_name, capability_name, spi_interface_name(), detail,
		command_count, callback_enabled ? "true" : "false",
		callback_trigger_every, callback_event_name, detail);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static int publish_spi_probe_event(const char *command_name)
{
	char payload_json[NEURO_UNIT_EVENT_JSON_LEN];

	if (snprintk(payload_json, sizeof(payload_json),
		"{\"app_id\":\"%s\",\"event_name\":\"%s\"," \
		"\"command\":\"%s\",\"interface\":\"%s\"," \
		"\"ready\":%s,\"probe_only\":true," \
		"\"invoke_count\":%u,\"echo\":\"%s\"}",
		app_id, default_event_name, command_name, spi_interface_name(),
		spi_ready ? "true" : "false", command_count, app_build_id) >=
		(int)sizeof(payload_json)) {
		return -12;
	}

	return neuro_unit_publish_app_event(app_id, default_event_name,
		payload_json);
}

static void write_probe_reply(char *reply_buf, size_t reply_buf_len,
	const char *command_name, bool config_changed, int publish_ret)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"ok\",\"command\":\"%s\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"ready\":%s,\"probe_only\":true," \
		"\"invoke_count\":%u,\"callback_enabled\":%s," \
		"\"trigger_every\":%d,\"event_name\":\"%s\"," \
		"\"config_changed\":%s,\"publish_ret\":%d," \
		"\"echo\":\"%s\"}",
		command_name, capability_name, spi_interface_name(),
		spi_ready ? "true" : "false", command_count,
		callback_enabled ? "true" : "false", callback_trigger_every,
		callback_event_name, config_changed ? "true" : "false",
		publish_ret, app_build_id);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static int handle_probe(char *reply_buf, size_t reply_buf_len,
	bool config_changed)
{
	int callback_ret;
	int event_ret;
	int publish_ret;

	if (!spi_ready) {
		write_unsupported_reply(reply_buf, reply_buf_len, "probe",
			spi_detail());
		return 0;
	}

	command_count++;
	callback_ret = maybe_publish_callback_event();
	event_ret = publish_spi_probe_event("probe");
	publish_ret = callback_ret != 0 ? callback_ret : event_ret;
	write_probe_reply(reply_buf, reply_buf_len, "probe", config_changed,
		publish_ret);
	return 0;
}

const struct app_runtime_manifest app_runtime_manifest = {
	.abi_major = APP_RT_MANIFEST_ABI_MAJOR,
	.abi_minor = APP_RT_MANIFEST_ABI_MINOR,
	.version = {
		.major = 1,
		.minor = 1,
		.patch = 10,
	},
	.capability_flags = APP_RT_CAP_SENSOR | APP_RT_CAP_ACTUATOR,
	.resource = {
		.ram_bytes = 16U * 1024U,
		.stack_bytes = 4U * 1024U,
		.cpu_budget_percent = 20U,
	},
	.app_name = "neuro_demo_spi",
	.dependency = "none",
};

int app_init(void)
{
	app_initialized = true;
	app_running = false;
	spi_ready = false;
	start_count = 0;
	callback_enabled = false;
	callback_trigger_every = 0;
	command_count = 0U;
	snprintk(callback_event_name, sizeof(callback_event_name), "%s",
		"callback");
	(void)app_version;
	return 0;
}

int app_start(const char *args)
{
	(void)args;

	if (!app_initialized) {
		return -1;
	}

	spi_ready = SPI_DEMO_HAS_DEVICE && spi_device != NULL &&
		device_is_ready(spi_device);
	app_running = true;
	start_count++;
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
	spi_ready = false;
	start_count = 0;
	callback_enabled = false;
	callback_trigger_every = 0;
	command_count = 0U;
	return 0;
}

int app_on_command(const char *command_name, const char *request_json,
	char *reply_buf, size_t reply_buf_len)
{
	char action[24] = { 0 };
	char args_json[256];
	const char *command_json;
	bool config_changed;

	if (!app_initialized || !app_running) {
		return -1;
	}

	if (!str_eq(command_name, app_command_name)) {
		return -2;
	}

	config_changed = command_updates_callback_config(request_json);
	command_json = command_args_json(request_json, args_json,
		sizeof(args_json));
	if (!neuro_json_extract_string(command_json, "action", action,
		    sizeof(action))) {
		snprintk(action, sizeof(action), "%s", "capability");
	}

	if (str_eq(action, "capability")) {
		command_count++;
		(void)maybe_publish_callback_event();
		write_capability_reply(reply_buf, reply_buf_len);
		return 0;
	}

	if (str_eq(action, "probe")) {
		return handle_probe(reply_buf, reply_buf_len, config_changed);
	}

	if (str_eq(action, "transfer")) {
		write_unsupported_reply(reply_buf, reply_buf_len, "transfer",
			"shared_sd_spi_no_loopback_target");
		return 0;
	}

	write_unsupported_reply(reply_buf, reply_buf_len, action,
		"unknown_action");
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