#include <zephyr/llext/symbol.h>
#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <stdbool.h>
#include <string.h>

#include "neuro_unit_diag.h"
#include "neuro_unit_event.h"
#include "neuro_protocol.h"
#include "neuro_protocol_codec.h"
#include "neuro_protocol_codec_cbor.h"

#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_MODE) &&                               \
	CONFIG_NEUROLINK_UNIT_DEBUG_MODE
#define NEURO_UNIT_EVENT_LOG_LEVEL LOG_LEVEL_DBG
#else
#define NEURO_UNIT_EVENT_LOG_LEVEL LOG_LEVEL_INF
#endif

#define NEURO_UNIT_EVENT_ASYNC_QUEUE_DEPTH 8

LOG_MODULE_REGISTER(neuro_unit_event, NEURO_UNIT_EVENT_LOG_LEVEL);

struct neuro_unit_pending_event_bytes {
	char keyexpr[NEURO_UNIT_EVENT_KEY_LEN];
	uint8_t payload[NEURO_UNIT_EVENT_JSON_LEN];
	size_t payload_len;
};

struct neuro_unit_event_ctx {
	char node_id[NEURO_UNIT_EVENT_NODE_ID_LEN];
	neuro_unit_event_publish_fn publish_fn;
	neuro_unit_event_publish_bytes_fn publish_bytes_fn;
	void *publish_ctx;
};

static struct neuro_unit_event_ctx g_event_ctx;

K_MSGQ_DEFINE(g_event_bytes_msgq, sizeof(struct neuro_unit_pending_event_bytes),
	NEURO_UNIT_EVENT_ASYNC_QUEUE_DEPTH, 4);

static int neuro_unit_event_publish_bytes_now(
	const char *keyexpr, const uint8_t *payload, size_t payload_len);

static void neuro_unit_event_work_handler(struct k_work *work)
{
	struct neuro_unit_pending_event_bytes event;

	ARG_UNUSED(work);

	while (k_msgq_get(&g_event_bytes_msgq, &event, K_NO_WAIT) == 0) {
		(void)neuro_unit_event_publish_bytes_now(
			event.keyexpr, event.payload, event.payload_len);
	}
}

K_WORK_DEFINE(g_event_bytes_work, neuro_unit_event_work_handler);

static bool token_is_valid(const char *token)
{
	if (token == NULL || token[0] == '\0') {
		return false;
	}

	for (; *token != '\0'; token++) {
		if (*token == '/') {
			return false;
		}
	}

	return true;
}

static bool reply_contract_is_valid(
	const struct neuro_unit_app_command_reply *reply)
{
	return reply != NULL && token_is_valid(reply->command_name) &&
	       token_is_valid(reply->event_name) && token_is_valid(reply->echo);
}

int neuro_unit_event_configure(
	const char *node_id, neuro_unit_event_publish_fn publish_fn, void *ctx)
{
	if (!token_is_valid(node_id) || publish_fn == NULL) {
		neuro_unit_diag_contract_error(
			"event.configure", "node_id/publish_fn", -EINVAL);
		return -EINVAL;
	}

	if (snprintk(g_event_ctx.node_id, sizeof(g_event_ctx.node_id), "%s",
		    node_id) >= (int)sizeof(g_event_ctx.node_id)) {
		neuro_unit_diag_contract_error(
			"event.configure", "node_id", -ENAMETOOLONG);
		return -ENAMETOOLONG;
	}

	g_event_ctx.publish_fn = publish_fn;
	g_event_ctx.publish_bytes_fn = NULL;
	g_event_ctx.publish_ctx = ctx;
	LOG_INF("event module configured: node=%s", g_event_ctx.node_id);
	return 0;
}

int neuro_unit_event_configure_bytes(const char *node_id,
	neuro_unit_event_publish_bytes_fn publish_fn, void *ctx)
{
	if (!token_is_valid(node_id) || publish_fn == NULL) {
		neuro_unit_diag_contract_error(
			"event.configure_bytes", "node_id/publish_fn", -EINVAL);
		return -EINVAL;
	}

	if (snprintk(g_event_ctx.node_id, sizeof(g_event_ctx.node_id), "%s",
		    node_id) >= (int)sizeof(g_event_ctx.node_id)) {
		neuro_unit_diag_contract_error(
			"event.configure_bytes", "node_id", -ENAMETOOLONG);
		return -ENAMETOOLONG;
	}

	g_event_ctx.publish_fn = NULL;
	g_event_ctx.publish_bytes_fn = publish_fn;
	g_event_ctx.publish_ctx = ctx;
	LOG_INF("event module configured for binary payloads: node=%s",
		g_event_ctx.node_id);
	return 0;
}

void neuro_unit_event_reset(void)
{
	memset(&g_event_ctx, 0, sizeof(g_event_ctx));
	k_msgq_purge(&g_event_bytes_msgq);
	LOG_DBG("event module context reset");
}

int neuro_unit_event_build_key(
	char *out, size_t out_len, const char *node_id, const char *suffix)
{
	int ret;

	ret = neuro_protocol_build_event_route(out, out_len, node_id, suffix);
	if (ret == -EINVAL) {
		neuro_unit_diag_contract_error(
			"event.build_key", "out/node_id/suffix", -EINVAL);
		return -EINVAL;
	}

	if (ret == -ENAMETOOLONG) {
		neuro_unit_diag_contract_error(
			"event.build_key", "out_len", -ENAMETOOLONG);
		return -ENAMETOOLONG;
	}

	return ret;
}

int neuro_unit_event_build_app_key(char *out, size_t out_len,
	const char *node_id, const char *app_id, const char *event_name)
{
	int ret;

	ret = neuro_protocol_build_app_event_route(
		out, out_len, node_id, app_id, event_name);
	if (ret == -EINVAL) {
		neuro_unit_diag_contract_error("event.build_app_key",
			"out/node_id/app_id/event_name", -EINVAL);
		return -EINVAL;
	}

	if (ret == -ENAMETOOLONG) {
		neuro_unit_diag_contract_error(
			"event.build_app_key", "out_len", -ENAMETOOLONG);
		return -ENAMETOOLONG;
	}

	return ret;
}

int neuro_unit_event_publish(const char *keyexpr, const char *payload_json)
{
	int ret;

	if (g_event_ctx.publish_fn == NULL) {
		neuro_unit_diag_contract_error(
			"event.publish", "publish_fn", -ENOSYS);
		return -ENOSYS;
	}

	if (keyexpr == NULL || keyexpr[0] == '\0' || payload_json == NULL ||
		payload_json[0] == '\0') {
		neuro_unit_diag_contract_error(
			"event.publish", "keyexpr/payload_json", -EINVAL);
		return -EINVAL;
	}

	neuro_unit_diag_event_attempt(keyexpr, strlen(payload_json));
	ret = g_event_ctx.publish_fn(
		keyexpr, payload_json, g_event_ctx.publish_ctx);
	neuro_unit_diag_event_result(keyexpr, ret);

	return ret;
}

static int neuro_unit_event_publish_bytes_now(
	const char *keyexpr, const uint8_t *payload, size_t payload_len)
{
	int ret;

	if (g_event_ctx.publish_bytes_fn == NULL) {
		neuro_unit_diag_contract_error(
			"event.publish_bytes", "publish_fn", -ENOSYS);
		return -ENOSYS;
	}

	if (keyexpr == NULL || keyexpr[0] == '\0' ||
		(payload == NULL && payload_len > 0U) || payload_len == 0U) {
		neuro_unit_diag_contract_error(
			"event.publish_bytes", "keyexpr/payload", -EINVAL);
		return -EINVAL;
	}

	neuro_unit_diag_event_attempt(keyexpr, payload_len);
	ret = g_event_ctx.publish_bytes_fn(
		keyexpr, payload, payload_len, g_event_ctx.publish_ctx);
	neuro_unit_diag_event_result(keyexpr, ret);

	return ret;
}

int neuro_unit_event_publish_bytes(
	const char *keyexpr, const uint8_t *payload, size_t payload_len)
{
	return neuro_unit_event_publish_bytes_now(
		keyexpr, payload, payload_len);
}

int neuro_unit_publish_app_event(
	const char *app_id, const char *event_name, const char *payload_json)
{
	char keyexpr[NEURO_UNIT_EVENT_KEY_LEN];
	int ret;

	if (g_event_ctx.node_id[0] == '\0') {
		neuro_unit_diag_contract_error(
			"event.publish_app_event", "node_id", -ENOSYS);
		return -ENOSYS;
	}

	ret = neuro_unit_event_build_app_key(keyexpr, sizeof(keyexpr),
		g_event_ctx.node_id, app_id, event_name);
	if (ret != 0) {
		LOG_ERR("app event key build failed: app=%s event=%s ret=%d",
			app_id, event_name, ret);
		return ret;
	}

	return neuro_unit_event_publish(keyexpr, payload_json);
}

int neuro_unit_publish_app_event_bytes(const char *app_id,
	const char *event_name, const uint8_t *payload, size_t payload_len)
{
	char keyexpr[NEURO_UNIT_EVENT_KEY_LEN];
	struct neuro_unit_pending_event_bytes pending;
	int ret;

	if (g_event_ctx.node_id[0] == '\0') {
		neuro_unit_diag_contract_error(
			"event.publish_app_event_bytes", "node_id", -ENOSYS);
		return -ENOSYS;
	}

	ret = neuro_unit_event_build_app_key(keyexpr, sizeof(keyexpr),
		g_event_ctx.node_id, app_id, event_name);
	if (ret != 0) {
		LOG_ERR("app event key build failed: app=%s event=%s ret=%d",
			app_id, event_name, ret);
		return ret;
	}

	if (payload == NULL || payload_len == 0U ||
		payload_len > sizeof(pending.payload)) {
		neuro_unit_diag_contract_error(
			"event.publish_app_event_bytes", "payload", -EINVAL);
		return -EINVAL;
	}

	memset(&pending, 0, sizeof(pending));
	snprintk(pending.keyexpr, sizeof(pending.keyexpr), "%s", keyexpr);
	memcpy(pending.payload, payload, payload_len);
	pending.payload_len = payload_len;
	ret = k_msgq_put(&g_event_bytes_msgq, &pending, K_NO_WAIT);
	if (ret != 0) {
		neuro_unit_diag_contract_error(
			"event.publish_app_event_bytes", "queue", ret);
		return ret;
	}

	(void)k_work_submit(&g_event_bytes_work);
	return 0;
}

int neuro_unit_publish_callback_event(
	const struct neuro_unit_app_callback_event *event)
{
	struct neuro_protocol_callback_event dto;
	uint8_t cbor_payload[NEURO_UNIT_EVENT_JSON_LEN];
	size_t encoded_len = 0U;
	char payload[NEURO_UNIT_EVENT_JSON_LEN];
	int ret;

	if (event == NULL || !token_is_valid(event->app_id) ||
		!token_is_valid(event->event_name)) {
		neuro_unit_diag_contract_error("event.publish_callback",
			"event/app_id/event_name", -EINVAL);
		return -EINVAL;
	}

	dto.app_id = event->app_id;
	dto.event_name = event->event_name;
	dto.invoke_count = event->invoke_count;
	dto.start_count = event->start_count;

	if (g_event_ctx.publish_bytes_fn != NULL) {
		ret = neuro_protocol_encode_callback_event_cbor(
			cbor_payload, sizeof(cbor_payload), &dto, &encoded_len);
		if (ret != 0) {
			neuro_unit_diag_contract_error(
				"event.publish_callback", "payload", ret);
			return ret;
		}

		return neuro_unit_publish_app_event_bytes(event->app_id,
			event->event_name, cbor_payload, encoded_len);
	}

	ret = neuro_protocol_encode_callback_event_json(
		payload, sizeof(payload), &dto);
	if (ret != 0) {
		neuro_unit_diag_contract_error(
			"event.publish_callback", "payload", ret);
		return ret;
	}
	return neuro_unit_publish_app_event(
		event->app_id, event->event_name, payload);
}

int neuro_unit_write_command_reply_json(char *reply_buf, size_t reply_buf_len,
	const struct neuro_unit_app_command_reply *reply)
{
	struct neuro_protocol_app_command_reply dto;
	int ret;

	if (reply_buf == NULL || reply_buf_len == 0U) {
		return 0;
	}

	if (!reply_contract_is_valid(reply)) {
		neuro_unit_diag_contract_error(
			"event.write_command_reply", "reply_contract", -EINVAL);
		return -EINVAL;
	}

	dto.command_name = reply->command_name;
	dto.invoke_count = reply->invoke_count;
	dto.callback_enabled = reply->callback_enabled;
	dto.trigger_every = reply->trigger_every;
	dto.event_name = reply->event_name;
	dto.config_changed = reply->config_changed;
	dto.publish_ret = reply->publish_ret;
	dto.echo = reply->echo;

	ret = neuro_protocol_encode_app_command_reply_json(
		reply_buf, reply_buf_len, &dto);
	if (ret != 0) {
		neuro_unit_diag_contract_error(
			"event.write_command_reply", "reply_buf_len", ret);
		return ret;
	}

	return 0;
}

EXPORT_SYMBOL(neuro_unit_publish_callback_event);
EXPORT_SYMBOL(neuro_unit_write_command_reply_json);
EXPORT_SYMBOL(neuro_unit_publish_app_event);
EXPORT_SYMBOL(neuro_unit_publish_app_event_bytes);
EXPORT_SYMBOL(neuro_unit_event_configure_bytes);
EXPORT_SYMBOL(neuro_unit_event_publish_bytes);
