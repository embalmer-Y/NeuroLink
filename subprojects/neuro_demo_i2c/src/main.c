/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/llext/symbol.h>
#include <zephyr/devicetree.h>
#include <zephyr/device.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "app_runtime_manifest.h"
#include "neuro_unit_app_api.h"

#define I2C_DEMO_NODE DT_NODELABEL(i2c0)

#if DT_NODE_HAS_STATUS(I2C_DEMO_NODE, okay)
#define I2C_DEMO_HAS_BUS 1
static const struct device *const i2c_bus = DEVICE_DT_GET(I2C_DEMO_NODE);
#else
#define I2C_DEMO_HAS_BUS 0
static const struct device *const i2c_bus;
#endif

#define AP3216C_ADDR 0x1e
#define AP3216C_REG_SYS_CONFIG 0x00
#define AP3216C_REG_IR_L 0x0a
#define AP3216C_RESET 0x04
#define AP3216C_ENABLE_ALS_PS_IR 0x03
#define AP3216C_RESET_DELAY_MS 10
#define AP3216C_CONVERSION_DELAY_MS 120

static bool app_initialized;
static bool app_running;
static bool i2c_ready;
static int ap3216c_enable_ret;
static int start_count;
static bool callback_enabled;
static int callback_trigger_every;
static unsigned int command_count;
static char callback_event_name[NEURO_UNIT_APP_EVENT_NAME_LEN] = "callback";

static const char app_command_name[] = "invoke";
static const char app_id[] = "neuro_demo_i2c";
static const char app_version[] = "1.1.10";
static const char app_build_id[] = "neuro_demo_i2c-1.1.10-cbor-v1";
static const char scan_event_name[] = "scan_result";
static const char sample_event_name[] = "ap3216c_sample";
static const char capability_name[] = "i2c";

int app_runtime_priority = 88;

struct scan_result {
	int scan_ret;
	int found_count;
	bool found_ap3216c;
	bool found_xl9555;
};

struct ap3216c_sample {
	int enable_ret;
	int read_ret;
	uint8_t sys_config;
	uint16_t ir_raw;
	uint16_t als_raw;
	uint16_t ps_raw;
	bool ir_valid;
	bool ps_valid;
	bool ps_near;
};

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

static const char *i2c_interface_name(void)
{
	if (I2C_DEMO_HAS_BUS) {
		return "i2c0_gpio45_scl_gpio48_sda";
	}

	return "none";
}

static const char *i2c_detail(void)
{
	if (!I2C_DEMO_HAS_BUS) {
		return "i2c0_missing";
	}

	if (!i2c_ready) {
		return "i2c0_not_ready";
	}

	if (ap3216c_enable_ret != 0) {
		return "ap3216c_enable_failed";
	}

	return "ap3216c_i2c_ready";
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

static int ap3216c_write_mode(uint8_t mode)
{
	uint8_t payload[2] = {
		AP3216C_REG_SYS_CONFIG,
		mode,
	};

	if (!i2c_ready) {
		return -19;
	}

	return i2c_write(i2c_bus, payload, sizeof(payload), AP3216C_ADDR);
}

static int ap3216c_configure(void)
{
	int ret;

	ret = ap3216c_write_mode(AP3216C_RESET);
	if (ret != 0) {
		return ret;
	}

	k_msleep(AP3216C_RESET_DELAY_MS);
	return ap3216c_write_mode(AP3216C_ENABLE_ALS_PS_IR);
}

static int i2c_probe_addr(uint16_t addr)
{
	return i2c_write(i2c_bus, NULL, 0U, addr);
}

static void run_scan(struct scan_result *result)
{
	if (result == NULL) {
		return;
	}

	result->scan_ret = 0;
	result->found_count = 0;
	result->found_ap3216c = false;
	result->found_xl9555 = false;

	if (!i2c_ready) {
		result->scan_ret = -19;
		return;
	}

	for (uint16_t addr = 0x03U; addr <= 0x77U; addr++) {
		if (i2c_probe_addr(addr) == 0) {
			result->found_count++;
			if (addr == AP3216C_ADDR) {
				result->found_ap3216c = true;
			}
			if (addr == 0x20U) {
				result->found_xl9555 = true;
			}
		}
	}
}

static int ap3216c_read_sample(struct ap3216c_sample *sample)
{
	uint8_t start_reg = AP3216C_REG_IR_L;
	uint8_t data[6];
	uint8_t sys_config = 0U;
	int ret;

	if (sample == NULL) {
		return -22;
	}

	sample->enable_ret = ap3216c_configure();
	sample->read_ret = 0;
	sample->sys_config = 0U;
	sample->ir_raw = 0U;
	sample->als_raw = 0U;
	sample->ps_raw = 0U;
	sample->ir_valid = false;
	sample->ps_valid = false;
	sample->ps_near = false;
	if (sample->enable_ret != 0) {
		return sample->enable_ret;
	}
	k_msleep(AP3216C_CONVERSION_DELAY_MS);

	ret = i2c_write_read(i2c_bus, AP3216C_ADDR, &start_reg, 1U, data,
		sizeof(data));
	if (ret != 0) {
		sample->read_ret = ret;
		return ret;
	}

	start_reg = AP3216C_REG_SYS_CONFIG;
	ret = i2c_write_read(i2c_bus, AP3216C_ADDR, &start_reg, 1U,
		&sys_config, 1U);
	if (ret != 0) {
		sample->read_ret = ret;
		return ret;
	}

	sample->sys_config = sys_config;
	sample->ir_valid = (data[0] & 0x80U) == 0U;
	sample->ps_valid = ((data[4] | data[5]) & 0x40U) == 0U;
	sample->ps_near = ((data[4] | data[5]) & 0x80U) != 0U;
	sample->ir_raw = (uint16_t)(((uint16_t)(data[1] & 0x03U) << 8) |
		data[0]);
	sample->als_raw = (uint16_t)(((uint16_t)data[3] << 8) | data[2]);
	sample->ps_raw = (uint16_t)(((uint16_t)(data[5] & 0x3fU) << 4) |
		(data[4] & 0x0fU));
	return 0;
}

static int publish_scan_event(const struct scan_result *result)
{
	char payload_json[NEURO_UNIT_EVENT_JSON_LEN];

	if (result == NULL) {
		return -22;
	}

	if (snprintk(payload_json, sizeof(payload_json),
		"{\"app_id\":\"%s\",\"event_name\":\"%s\"," \
		"\"bus\":\"%s\",\"count\":%d,\"ap3216c\":%s," \
		"\"xl9555\":%s,\"scan_ret\":%d,\"invoke_count\":%u}",
		app_id, scan_event_name, i2c_interface_name(), result->found_count,
		result->found_ap3216c ? "true" : "false",
		result->found_xl9555 ? "true" : "false", result->scan_ret,
		command_count) >= (int)sizeof(payload_json)) {
		return -12;
	}

	return neuro_unit_publish_app_event(app_id, scan_event_name,
		payload_json);
}

static int publish_sample_event(const struct ap3216c_sample *sample)
{
	char payload_json[NEURO_UNIT_EVENT_JSON_LEN];

	if (sample == NULL) {
		return -22;
	}

	if (snprintk(payload_json, sizeof(payload_json),
		"{\"app_id\":\"%s\",\"event_name\":\"%s\"," \
		"\"addr\":30,\"sys\":%u,\"ir\":%u,\"als\":%u," \
		"\"ps\":%u,\"ir_valid\":%s,\"ps_valid\":%s," \
		"\"ps_near\":%s," \
		"\"invoke_count\":%u}",
		app_id, sample_event_name, sample->sys_config, sample->ir_raw,
		sample->als_raw, sample->ps_raw,
		sample->ir_valid ? "true" : "false",
		sample->ps_valid ? "true" : "false",
		sample->ps_near ? "true" : "false", command_count) >=
		(int)sizeof(payload_json)) {
		return -12;
	}

	return neuro_unit_publish_app_event(app_id, sample_event_name,
		payload_json);
}

static void write_capability_reply(char *reply_buf, size_t reply_buf_len)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"ok\",\"command\":\"capability\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"ready\":%s,\"detail\":\"%s\",\"addr\":30," \
		"\"enable_ret\":%d,\"invoke_count\":%u," \
		"\"callback_enabled\":%s,\"trigger_every\":%d," \
		"\"event_name\":\"%s\",\"config_changed\":false," \
		"\"publish_ret\":0,\"echo\":\"%s\"}",
		capability_name, i2c_interface_name(), i2c_ready ? "true" : "false",
		i2c_detail(), ap3216c_enable_ret, command_count,
		callback_enabled ? "true" : "false", callback_trigger_every,
		callback_event_name, app_build_id);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static void write_scan_reply(char *reply_buf, size_t reply_buf_len,
	const struct scan_result *result, bool config_changed, int publish_ret)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"ok\",\"command\":\"scan\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"found_count\":%d,\"ap3216c\":%s,\"xl9555\":%s," \
		"\"scan_ret\":%d,\"invoke_count\":%u," \
		"\"callback_enabled\":%s,\"trigger_every\":%d," \
		"\"event_name\":\"%s\",\"config_changed\":%s," \
		"\"publish_ret\":%d,\"echo\":\"i2c0_scan\"}",
		capability_name, i2c_interface_name(), result->found_count,
		result->found_ap3216c ? "true" : "false",
		result->found_xl9555 ? "true" : "false", result->scan_ret,
		command_count, callback_enabled ? "true" : "false",
		callback_trigger_every, callback_event_name,
		config_changed ? "true" : "false", publish_ret);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static void write_sample_reply(char *reply_buf, size_t reply_buf_len,
	const struct ap3216c_sample *sample, bool config_changed, int publish_ret)
{
	int written;

	written = snprintk(reply_buf, reply_buf_len,
		"{\"status\":\"ok\",\"command\":\"ap3216c_read\"," \
		"\"capability\":\"%s\",\"interface\":\"%s\"," \
		"\"addr\":30,\"sys_config\":%u,\"ir\":%u," \
		"\"als\":%u,\"ps\":%u,\"ir_valid\":%s," \
		"\"ps_valid\":%s,\"ps_near\":%s,\"read_ret\":%d," \
		"\"enable_ret\":%d," \
		"\"invoke_count\":%u,\"callback_enabled\":%s," \
		"\"trigger_every\":%d,\"event_name\":\"%s\"," \
		"\"config_changed\":%s,\"publish_ret\":%d," \
		"\"echo\":\"ap3216c\"}",
		capability_name, i2c_interface_name(), sample->sys_config,
		sample->ir_raw, sample->als_raw, sample->ps_raw,
		sample->ir_valid ? "true" : "false",
		sample->ps_valid ? "true" : "false",
		sample->ps_near ? "true" : "false", sample->read_ret,
		sample->enable_ret, command_count,
		callback_enabled ? "true" : "false", callback_trigger_every,
		callback_event_name, config_changed ? "true" : "false",
		publish_ret);
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
		command_name, capability_name, i2c_interface_name(), detail,
		command_count, callback_enabled ? "true" : "false",
		callback_trigger_every, callback_event_name, detail);
	if (written < 0 || written >= (int)reply_buf_len) {
		if (reply_buf_len > 0U) {
			reply_buf[0] = '\0';
		}
	}
}

static int handle_scan(char *reply_buf, size_t reply_buf_len,
	bool config_changed)
{
	struct scan_result result;
	int callback_ret;
	int event_ret;
	int publish_ret;

	if (!i2c_ready) {
		write_unsupported_reply(reply_buf, reply_buf_len, "scan",
			i2c_detail());
		return 0;
	}

	command_count++;
	run_scan(&result);
	callback_ret = maybe_publish_callback_event();
	event_ret = publish_scan_event(&result);
	publish_ret = callback_ret != 0 ? callback_ret : event_ret;
	write_scan_reply(reply_buf, reply_buf_len, &result, config_changed,
		publish_ret);
	return 0;
}

static int handle_ap3216c_read(char *reply_buf, size_t reply_buf_len,
	bool config_changed)
{
	struct ap3216c_sample sample;
	int callback_ret;
	int event_ret;
	int publish_ret;

	if (!i2c_ready) {
		write_unsupported_reply(reply_buf, reply_buf_len, "ap3216c_read",
			i2c_detail());
		return 0;
	}

	command_count++;
	if (ap3216c_read_sample(&sample) != 0) {
		write_unsupported_reply(reply_buf, reply_buf_len, "ap3216c_read",
			"ap3216c_read_failed");
		return 0;
	}

	callback_ret = maybe_publish_callback_event();
	event_ret = publish_sample_event(&sample);
	publish_ret = callback_ret != 0 ? callback_ret : event_ret;
	write_sample_reply(reply_buf, reply_buf_len, &sample, config_changed,
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
	.capability_flags = APP_RT_CAP_SENSOR,
	.resource = {
		.ram_bytes = 16U * 1024U,
		.stack_bytes = 4U * 1024U,
		.cpu_budget_percent = 20U,
	},
	.app_name = "neuro_demo_i2c",
	.dependency = "none",
};

int app_init(void)
{
	app_initialized = true;
	app_running = false;
	i2c_ready = false;
	ap3216c_enable_ret = 0;
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

	i2c_ready = I2C_DEMO_HAS_BUS && i2c_bus != NULL &&
		device_is_ready(i2c_bus);
	ap3216c_enable_ret = ap3216c_configure();
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
	i2c_ready = false;
	ap3216c_enable_ret = 0;
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

	if (str_eq(action, "scan")) {
		return handle_scan(reply_buf, reply_buf_len, config_changed);
	}

	if (str_eq(action, "ap3216c_read")) {
		return handle_ap3216c_read(reply_buf, reply_buf_len,
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