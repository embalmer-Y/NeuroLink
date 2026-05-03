/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/llext/symbol.h>
#include <zephyr/devicetree.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/printk.h>

#include <stdbool.h>
#include <stddef.h>

#include "app_runtime_manifest.h"
#include "neuro_unit_app_api.h"

#if DT_HAS_CHOSEN(neurolink_uart_loopback)
#define UART_DEMO_NODE DT_CHOSEN(neurolink_uart_loopback)
#define UART_DEMO_INTERFACE_NAME "j3_uart1_gpio5_tx_gpio6_rx"
#define UART_DEMO_DETAIL_READY "j3_loopback_ready"
#define UART_DEMO_PHYSICAL_LOOPBACK 1
#else
#define UART_DEMO_NODE DT_CHOSEN(zephyr_shell_uart)
#define UART_DEMO_INTERFACE_NAME "zephyr_shell_uart"
#define UART_DEMO_DETAIL_READY "probe_ready_read_only"
#define UART_DEMO_PHYSICAL_LOOPBACK 0
#endif

#if DT_NODE_HAS_STATUS(UART_DEMO_NODE, okay)
static const struct device *const uart_device = DEVICE_DT_GET(UART_DEMO_NODE);
#define UART_DEMO_HAS_DEVICE 1
#else
static const struct device *const uart_device;
#define UART_DEMO_HAS_DEVICE 0
#endif

static bool app_initialized;
static bool app_running;
static bool uart_ready;
static int start_count;
static bool callback_enabled;
static int callback_trigger_every;
static unsigned int command_count;
static char callback_event_name[NEURO_UNIT_APP_EVENT_NAME_LEN] = "callback";

static const char app_command_name[] = "invoke";
static const char app_id[] = "neuro_demo_uart";
static const char app_version[] = "1.1.10";
static const char app_build_id[] = "neuro_demo_uart-1.1.10-cbor-v1";
static const char default_event_name[] = "uart_probe";
static const char capability_name[] = "uart";
static const char default_loopback_message[] = "J3-UART-LOOPBACK";

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

static size_t bounded_string_len(const char *value, size_t max_len)
{
	size_t len = 0U;

	if (value == NULL) {
		return 0U;
	}

	while (len < max_len && value[len] != '\0') {
		len++;
	}

	return len;
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

static const char *uart_interface_name(void)
{
	if (UART_DEMO_HAS_DEVICE) {
		return UART_DEMO_INTERFACE_NAME;
	}

	return "none";
}

static const char *uart_detail(void)
{
	if (!UART_DEMO_HAS_DEVICE) {
		return "chosen_uart_missing";
	}

	if (!uart_ready) {
		return "chosen_uart_not_ready";
	}

	return UART_DEMO_DETAIL_READY;
}

static int uart_drain_input(void)
{
	unsigned char received_char;
	int drained = 0;

	if (!uart_ready) {
		return 0;
	}

	for (int attempt = 0; attempt < 32; attempt++) {
		if (uart_poll_in(uart_device, &received_char) != 0) {
			break;
		}
		drained++;
	}

	return drained;
}

static int uart_receive_one(unsigned char *received_char)
{
	if (received_char == NULL) {
		return -1;
	}

	for (int attempt = 0; attempt < 60000; attempt++) {
		if (uart_poll_in(uart_device, received_char) == 0) {
			return 0;
		}
	}

	return -1;
}

static int uart_run_loopback(const char *message, char *received,
	size_t received_len, size_t *sent_len, size_t *received_count,
	int *first_mismatch)
{
	const size_t max_message_len = 47U;
	unsigned char received_char;
	size_t message_len;

	if (received == NULL || received_len == 0U || sent_len == NULL ||
	    received_count == NULL || first_mismatch == NULL) {
		return -1;
	}

	received[0] = '\0';
	*sent_len = 0U;
	*received_count = 0U;
	*first_mismatch = -1;

	if (!uart_ready || !UART_DEMO_PHYSICAL_LOOPBACK) {
		return -1;
	}

	message_len = bounded_string_len(message, max_message_len);
	if (message_len == 0U || message_len >= received_len) {
		return -1;
	}

	(void)uart_drain_input();
	*sent_len = message_len;
	for (size_t index = 0U; index < message_len; index++) {
		uart_poll_out(uart_device, (unsigned char)message[index]);
		if (uart_receive_one(&received_char) != 0) {
			break;
		}

		received[index] = (char)received_char;
		*received_count = index + 1U;
		if (received_char != (unsigned char)message[index] &&
		    *first_mismatch < 0) {
			*first_mismatch = (int)index;
		}
	}
	received[*received_count] = '\0';

	return *received_count == message_len && *first_mismatch < 0 ? 0 : -1;
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
	const neuro_unit_app_capability_report_t report = {
		.capability = capability_name,
		.available = uart_ready,
		.interface_name = uart_interface_name(),
		.detail = uart_detail(),
	};

	(void)neuro_unit_write_capability_report_json(
		reply_buf, reply_buf_len, &report);
}

static void write_unsupported_reply(char *reply_buf, size_t reply_buf_len,
	const char *command_name, const char *detail)
{
	const neuro_unit_app_unsupported_result_t result = {
		.status = "capability_missing",
		.command_name = command_name,
		.capability = capability_name,
		.detail = detail,
	};

	(void)neuro_unit_write_unsupported_result_json(
		reply_buf, reply_buf_len, &result);
}

static int publish_uart_probe_event(const char *command_name,
	const char *message)
{
	char payload_json[NEURO_UNIT_EVENT_JSON_LEN];

	if (snprintk(payload_json, sizeof(payload_json),
		"{\"app_id\":\"%s\",\"event_name\":\"%s\"," \
		"\"command\":\"%s\",\"interface\":\"%s\"," \
		"\"ready\":%s,\"invoke_count\":%u," \
		"\"message\":\"%s\",\"echo\":\"%s\"}",
		app_id, default_event_name, command_name, uart_interface_name(),
		uart_ready ? "true" : "false", command_count, message,
		app_build_id) >= (int)sizeof(payload_json)) {
		return -12;
	}

	return neuro_unit_publish_app_event(app_id, default_event_name,
		payload_json);
}

static int publish_uart_loopback_event(const char *message,
	const char *received, size_t sent_len, size_t received_count,
	int first_mismatch, int loopback_ret)
{
	char payload_json[NEURO_UNIT_EVENT_JSON_LEN];

	if (snprintk(payload_json, sizeof(payload_json),
		"{\"app_id\":\"%s\",\"event_name\":\"%s\"," \
		"\"command\":\"loopback\",\"interface\":\"%s\"," \
		"\"ok\":%s,\"tx\":%u,\"rx\":%u," \
		"\"mm\":%d,\"message\":\"%s\",\"received\":\"%s\"," \
		"\"invoke_count\":%u}",
		app_id, default_event_name, uart_interface_name(),
		loopback_ret == 0 ? "true" : "false", (unsigned int)sent_len,
		(unsigned int)received_count, first_mismatch, message, received,
		command_count) >= (int)sizeof(payload_json)) {
		return -12;
	}

	return neuro_unit_publish_app_event(app_id, default_event_name,
		payload_json);
}

static void write_probe_reply(char *reply_buf, size_t reply_buf_len,
	const char *command_name, const char *message, bool config_changed,
	int publish_ret)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"ok\",\"command\":\"%s\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"ready\":%s,\"invoke_count\":%u," \
		"\"callback_enabled\":%s,\"trigger_every\":%d," \
		"\"event_name\":\"%s\",\"config_changed\":%s," \
		"\"publish_ret\":%d,\"message\":\"%s\",\"echo\":\"%s\"}",
		command_name, capability_name, uart_interface_name(),
		uart_ready ? "true" : "false", command_count,
		callback_enabled ? "true" : "false", callback_trigger_every,
		callback_event_name, config_changed ? "true" : "false",
		publish_ret, message, app_build_id);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static void write_loopback_reply(char *reply_buf, size_t reply_buf_len,
	const char *message, const char *received, size_t sent_len,
	size_t received_count, int first_mismatch, bool config_changed,
	int loopback_ret, int publish_ret)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"%s\",\"command\":\"loopback\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"success\":%s,\"bytes_sent\":%u," \
		"\"bytes_received\":%u,\"first_mismatch\":%d," \
		"\"callback_enabled\":%s,\"trigger_every\":%d," \
		"\"event_name\":\"%s\",\"config_changed\":%s," \
		"\"publish_ret\":%d,\"message\":\"%s\"," \
		"\"received\":\"%s\",\"echo\":\"%s\"}",
		loopback_ret == 0 ? "ok" : "loopback_failed", capability_name,
		uart_interface_name(), loopback_ret == 0 ? "true" : "false",
		(unsigned int)sent_len,
		(unsigned int)received_count, first_mismatch,
		callback_enabled ? "true" : "false", callback_trigger_every,
		callback_event_name, config_changed ? "true" : "false",
		publish_ret, message, received, app_build_id);
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

	if (!uart_ready) {
		write_unsupported_reply(reply_buf, reply_buf_len, "probe",
			uart_detail());
		return 0;
	}

	command_count++;
	callback_ret = maybe_publish_callback_event();
	event_ret = publish_uart_probe_event("probe", "uart_ready");
	publish_ret = callback_ret != 0 ? callback_ret : event_ret;
	write_probe_reply(reply_buf, reply_buf_len, "probe", "uart_ready",
		config_changed, publish_ret);
	return 0;
}

static int handle_echo(const char *command_json, char *reply_buf,
	size_t reply_buf_len, bool config_changed)
{
	char message[48] = "read_only_echo";
	int callback_ret;
	int event_ret;
	int publish_ret;

	if (!uart_ready) {
		write_unsupported_reply(reply_buf, reply_buf_len, "echo",
			uart_detail());
		return 0;
	}

	(void)neuro_json_extract_string(command_json, "message", message,
		sizeof(message));
	command_count++;
	callback_ret = maybe_publish_callback_event();
	event_ret = publish_uart_probe_event("echo", message);
	publish_ret = callback_ret != 0 ? callback_ret : event_ret;
	write_probe_reply(reply_buf, reply_buf_len, "echo", message,
		config_changed, publish_ret);
	return 0;
}

static int handle_loopback(const char *command_json, char *reply_buf,
	size_t reply_buf_len, bool config_changed)
{
	char message[48];
	char received[48];
	size_t sent_len;
	size_t received_count;
	int first_mismatch;
	int callback_ret;
	int event_ret;
	int publish_ret;
	int loopback_ret;

	if (!uart_ready) {
		write_unsupported_reply(reply_buf, reply_buf_len, "loopback",
			uart_detail());
		return 0;
	}

	if (!UART_DEMO_PHYSICAL_LOOPBACK) {
		write_unsupported_reply(reply_buf, reply_buf_len, "loopback",
			"physical_loopback_not_configured");
		return 0;
	}

	snprintk(message, sizeof(message), "%s", default_loopback_message);
	(void)neuro_json_extract_string(command_json, "message", message,
		sizeof(message));
	command_count++;
	loopback_ret = uart_run_loopback(message, received, sizeof(received),
		&sent_len, &received_count, &first_mismatch);
	callback_ret = maybe_publish_callback_event();
	event_ret = publish_uart_loopback_event(message, received, sent_len,
		received_count, first_mismatch, loopback_ret);
	publish_ret = callback_ret != 0 ? callback_ret : event_ret;
	write_loopback_reply(reply_buf, reply_buf_len, message, received,
		sent_len, received_count, first_mismatch, config_changed,
		loopback_ret, publish_ret);
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
	.capability_flags = APP_RT_CAP_SENSOR,
	.resource = {
		.ram_bytes = 16U * 1024U,
		.stack_bytes = 4U * 1024U,
		.cpu_budget_percent = 20U,
	},
	.app_name = "neuro_demo_uart",
	.dependency = "none",
};

int app_init(void)
{
	app_initialized = true;
	app_running = false;
	uart_ready = false;
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

	uart_ready = UART_DEMO_HAS_DEVICE && uart_device != NULL &&
		device_is_ready(uart_device);
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
	uart_ready = false;
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

	if (str_eq(action, "echo")) {
		return handle_echo(command_json, reply_buf, reply_buf_len,
			config_changed);
	}

	if (str_eq(action, "loopback")) {
		return handle_loopback(command_json, reply_buf, reply_buf_len,
			config_changed);
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