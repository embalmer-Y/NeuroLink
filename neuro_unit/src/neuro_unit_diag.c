#include "neuro_unit_diag.h"

#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include <errno.h>

#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_MODE) &&                               \
	CONFIG_NEUROLINK_UNIT_DEBUG_MODE
#define NEURO_UNIT_DIAG_LOG_LEVEL LOG_LEVEL_DBG
#else
#define NEURO_UNIT_DIAG_LOG_LEVEL LOG_LEVEL_INF
#endif

LOG_MODULE_REGISTER(neuro_unit_diag, NEURO_UNIT_DIAG_LOG_LEVEL);

static const char *safe_token(const char *value)
{
	if (value == NULL || value[0] == '\0') {
		return "-";
	}

	return value;
}

int neuro_unit_diag_format_context(
	char *out, size_t out_len, const struct neuro_unit_diag_context *ctx)
{
	int written;

	if (out == NULL || out_len == 0U) {
		return -EINVAL;
	}

	if (ctx == NULL) {
		written = snprintk(out, out_len,
			"request_id=- app_id=- route=- stage=- ret=0");
	} else {
		written = snprintk(out, out_len,
			"request_id=%s app_id=%s route=%s stage=%s ret=%d",
			safe_token(ctx->request_id), safe_token(ctx->app_id),
			safe_token(ctx->route), safe_token(ctx->stage),
			ctx->ret);
	}

	if (written < 0 || (size_t)written >= out_len) {
		return -ENAMETOOLONG;
	}

	return 0;
}

void neuro_unit_diag_log_result(
	const char *operation, const struct neuro_unit_diag_context *ctx)
{
	char context[NEURO_UNIT_DIAG_CONTEXT_MAX_LEN];
	int ret;

	ret = neuro_unit_diag_format_context(context, sizeof(context), ctx);
	if (ret != 0) {
		snprintk(context, sizeof(context), "context=<format-failed:%d>",
			ret);
	}

	if (ctx != NULL && ctx->ret < 0) {
		LOG_ERR("%s failed: %s", safe_token(operation), context);
		return;
	}

	LOG_INF("%s ok: %s", safe_token(operation), context);
}

void neuro_unit_diag_protocol_failure(const char *route, const char *stage,
	const char *request_id, int ret, size_t payload_len)
{
	LOG_WRN("protocol failure: route=%s stage=%s request_id=%s ret=%d payload_len=%zu",
		safe_token(route), safe_token(stage), safe_token(request_id),
		ret, payload_len);
}

void neuro_unit_diag_dispatch_result(const char *family, const char *key,
	const char *request_id, const char *result, int code)
{
	if (code == 0) {
		LOG_DBG("dispatch route: family=%s key=%s request_id=%s result=%s",
			safe_token(family), safe_token(key),
			safe_token(request_id), safe_token(result));
		return;
	}

	LOG_WRN("dispatch route rejected: family=%s key=%s request_id=%s result=%s code=%d",
		safe_token(family), safe_token(key), safe_token(request_id),
		safe_token(result), code);
}

void neuro_unit_diag_callback_registration(const char *app_id,
	const char *command_name, const char *stage, int ret)
{
	if (ret == 0) {
		LOG_INF("callback registration: app=%s command=%s stage=%s ret=0",
			safe_token(app_id), safe_token(command_name),
			safe_token(stage));
		return;
	}

	LOG_WRN("callback registration: app=%s command=%s stage=%s ret=%d",
		safe_token(app_id), safe_token(command_name), safe_token(stage),
		ret);
}

void neuro_unit_diag_update_transaction(const char *app_id, const char *action,
	const char *request_id, const char *phase, int code, const char *detail)
{
	if (code == 0) {
		LOG_INF("update txn app=%s action=%s phase=%s request_id=%s detail=%s",
			safe_token(app_id), safe_token(action),
			safe_token(phase), safe_token(request_id),
			safe_token(detail));
		return;
	}

	LOG_WRN("update txn app=%s action=%s phase=%s request_id=%s code=%d detail=%s",
		safe_token(app_id), safe_token(action), safe_token(phase),
		safe_token(request_id), code, safe_token(detail));
}

void neuro_unit_diag_contract_error(
	const char *component, const char *field, int ret)
{
	LOG_ERR("contract violation: component=%s field=%s ret=%d",
		safe_token(component), safe_token(field), ret);
}

void neuro_unit_diag_event_attempt(const char *keyexpr, size_t payload_len)
{
#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_VERBOSE_EVENTS) &&                     \
	CONFIG_NEUROLINK_UNIT_DEBUG_VERBOSE_EVENTS
	LOG_DBG("event attempt: key=%s payload_len=%zu", safe_token(keyexpr),
		payload_len);
#else
	ARG_UNUSED(keyexpr);
	ARG_UNUSED(payload_len);
#endif
}

void neuro_unit_diag_event_result(const char *keyexpr, int ret)
{
	if (ret == 0) {
		LOG_INF("event publish ok: key=%s", safe_token(keyexpr));
		return;
	}

	LOG_ERR("event publish failed: key=%s ret=%d", safe_token(keyexpr),
		ret);
}

void neuro_unit_diag_state_transition_bool(
	const char *field, bool old_val, bool new_val, uint64_t version)
{
	LOG_INF("state transition: field=%s old=%d new=%d version=%llu",
		safe_token(field), old_val, new_val,
		(unsigned long long)version);
}

void neuro_unit_diag_state_transition_size(
	const char *field, size_t old_val, size_t new_val, uint64_t version)
{
	LOG_INF("state transition: field=%s old=%zu new=%zu version=%llu",
		safe_token(field), old_val, new_val,
		(unsigned long long)version);
}

void neuro_unit_diag_state_transition_text(const char *field,
	const char *old_val, const char *new_val, uint64_t version)
{
	LOG_INF("state transition: field=%s old=%s new=%s version=%llu",
		safe_token(field), safe_token(old_val), safe_token(new_val),
		(unsigned long long)version);
}

void neuro_unit_diag_state_transition_enum(const char *field,
	const char *old_val, const char *new_val, uint64_t version)
{
	LOG_INF("state transition: field=%s old=%s new=%s version=%llu",
		safe_token(field), safe_token(old_val), safe_token(new_val),
		(unsigned long long)version);
}

void neuro_unit_diag_state_snapshot(const char *reason, const char *node_id,
	uint64_t version, bool session_ready, const char *network_state,
	const char *health)
{
#if defined(CONFIG_NEUROLINK_UNIT_DEBUG_VERBOSE_STATE) &&                      \
	CONFIG_NEUROLINK_UNIT_DEBUG_VERBOSE_STATE
	LOG_DBG("state snapshot: reason=%s node=%s version=%llu session_ready=%d network=%s health=%s",
		safe_token(reason), safe_token(node_id),
		(unsigned long long)version, session_ready,
		safe_token(network_state), safe_token(health));
#else
	ARG_UNUSED(reason);
	ARG_UNUSED(node_id);
	ARG_UNUSED(version);
	ARG_UNUSED(session_ready);
	ARG_UNUSED(network_state);
	ARG_UNUSED(health);
#endif
}
