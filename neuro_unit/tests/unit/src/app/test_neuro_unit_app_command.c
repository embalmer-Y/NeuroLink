#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <string.h>

#include "neuro_app_command_registry.h"
#include "neuro_unit_app_command.h"
#include "test_app_runtime_dispatch_mock.h"

static struct neuro_unit_reply_context g_reply_ctx;
static uint8_t g_dummy_query_storage;
static int g_reply_error_calls;
static int g_reply_error_status;
static int g_query_reply_calls;
static int g_require_lease_calls;
static int g_publish_state_calls;
static bool g_require_lease_result;
static char g_last_error_message[64];
static char g_last_reply_json[256];
static const struct neuro_unit_reply_context *g_last_reply_ctx;

static void mock_reply_error(const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *message, int status_code)
{
	ARG_UNUSED(request_id);

	g_reply_error_calls++;
	g_reply_error_status = status_code;
	g_last_reply_ctx = reply_ctx;
	snprintk(g_last_error_message, sizeof(g_last_error_message), "%s",
		message != NULL ? message : "");
}

static bool mock_require_resource_lease_or_reply(
	const struct neuro_unit_reply_context *reply_ctx,
	const char *request_id, const char *resource,
	const struct neuro_request_metadata *metadata)
{
	ARG_UNUSED(request_id);
	ARG_UNUSED(resource);
	ARG_UNUSED(metadata);

	g_require_lease_calls++;
	g_last_reply_ctx = reply_ctx;
	return g_require_lease_result;
}

static void mock_query_reply_json(
	const struct neuro_unit_reply_context *reply_ctx, const char *json)
{
	g_query_reply_calls++;
	g_last_reply_ctx = reply_ctx;
	snprintk(g_last_reply_json, sizeof(g_last_reply_json), "%s",
		json != NULL ? json : "");
}

static void mock_publish_state_event(void) { g_publish_state_calls++; }

static const struct neuro_unit_app_command_ops g_ops = {
	.node_id = "unit-01",
	.reply_error = mock_reply_error,
	.require_resource_lease_or_reply = mock_require_resource_lease_or_reply,
	.query_reply_json = mock_query_reply_json,
	.publish_state_event = mock_publish_state_event,
};

static void register_callback_command(const char *app_id,
	const char *command_name, bool lease_required, bool enabled)
{
	struct neuro_app_command_desc desc = { 0 };

	snprintk(desc.app_id, sizeof(desc.app_id), "%s", app_id);
	snprintk(desc.command_name, sizeof(desc.command_name), "%s",
		command_name);
	desc.visibility = 1U;
	desc.lease_required = lease_required;
	desc.idempotent = false;
	desc.timeout_ms = 1000U;
	desc.state = NEURO_APPCMD_STATE_REGISTERING;
	zassert_equal(neuro_app_command_registry_register(&desc), 0,
		"callback command register must succeed");
	zassert_equal(neuro_app_command_registry_set_enabled(
			      app_id, command_name, enabled),
		0, "callback command enable/disable must succeed");
}

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);

	neuro_app_command_registry_init();
	test_app_runtime_dispatch_reset();
	g_reply_ctx.transport_query = &g_dummy_query_storage;
	g_reply_error_calls = 0;
	g_reply_error_status = 0;
	g_query_reply_calls = 0;
	g_require_lease_calls = 0;
	g_publish_state_calls = 0;
	g_require_lease_result = true;
	g_last_reply_ctx = NULL;
	memset(g_last_error_message, 0, sizeof(g_last_error_message));
	memset(g_last_reply_json, 0, sizeof(g_last_reply_json));
}

ZTEST(neuro_unit_app_command,
	test_registered_callback_command_dispatches_through_bridge)
{
	register_callback_command("demo_app", "invoke", true, true);
	test_app_runtime_dispatch_set_result(0, "{\"app_status\":\"ok\"}");

	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "invoke",
		"{\"lease_id\":\"lease-1\"}", "req-app-cb", &g_ops);

	zassert_equal(g_reply_error_calls, 0,
		"callback command should not emit reply_error");
	zassert_equal(g_require_lease_calls, 1,
		"lease-required callback command should require lease");
	zassert_equal(g_publish_state_calls, 0,
		"callback command dispatch should not publish runtime state event");
	zassert_equal(g_query_reply_calls, 1,
		"callback command should emit one success reply");
	zassert_true(
		strstr(g_last_reply_json, "\"dispatch\":\"callback\"") != NULL,
		"callback command reply should identify callback dispatch");
	zassert_true(strstr(g_last_reply_json,
			     "\"reply\":{\"app_status\":\"ok\"}") != NULL,
		"callback command reply should embed runtime callback reply");
	zassert_true(g_last_reply_ctx == &g_reply_ctx,
		"reply context should be forwarded to callback success reply");
}

ZTEST(neuro_unit_app_command,
	test_registered_callback_command_dispatch_failure_replies_500)
{
	register_callback_command("demo_app", "invoke", false, true);
	test_app_runtime_dispatch_set_result(-5, NULL);

	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "invoke", "{}",
		"req-app-cb-fail", &g_ops);

	zassert_equal(g_require_lease_calls, 0,
		"non-lease callback command should not require lease");
	zassert_equal(g_query_reply_calls, 0,
		"failed callback dispatch must not emit success reply");
	zassert_equal(g_reply_error_calls, 1,
		"failed callback dispatch should emit one error");
	zassert_equal(g_reply_error_status, 500,
		"failed callback dispatch should map to 500");
	zassert_true(strcmp(g_last_error_message,
			     "app callback dispatch failed") == 0,
		"callback dispatch failure message mismatch");
}

ZTEST(neuro_unit_app_command,
	test_disabled_registered_callback_command_replies_409)
{
	register_callback_command("demo_app", "invoke", true, false);
	test_app_runtime_dispatch_set_result(0, "{\"app_status\":\"ok\"}");

	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "invoke", "{}",
		"req-app-cb-off", &g_ops);

	zassert_equal(g_require_lease_calls, 0,
		"disabled callback command should fail before lease check");
	zassert_equal(g_query_reply_calls, 0,
		"disabled callback command must not emit success reply");
	zassert_equal(g_reply_error_calls, 1,
		"disabled callback command should emit one error");
	zassert_equal(g_reply_error_status, 409,
		"disabled callback command should map to 409");
	zassert_true(strcmp(g_last_error_message, "app command disabled") == 0,
		"disabled callback command message mismatch");
}

ZTEST(neuro_unit_app_command,
	test_unsupported_action_replies_404_through_reply_context)
{
	neuro_unit_handle_app_command(
		&g_reply_ctx, "demo_app", "pause", "{}", "req-app-1", &g_ops);

	zassert_equal(g_require_lease_calls, 1,
		"unsupported runtime app command should still require lease");
	zassert_equal(g_reply_error_calls, 1,
		"unsupported runtime app command should emit one error");
	zassert_equal(g_reply_error_status, 404,
		"unsupported runtime app command should map to 404");
	zassert_true(
		strcmp(g_last_error_message, "unsupported app command") == 0,
		"unexpected unsupported action message");
	zassert_true(g_last_reply_ctx == &g_reply_ctx,
		"reply context should be forwarded to error callback");
}

ZTEST(neuro_unit_app_command,
	test_start_action_replies_ok_through_reply_context)
{
	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "start",
		"{\"start_args\":\"--demo\"}", "req-app-2", &g_ops);

	zassert_equal(g_reply_error_calls, 0,
		"start action should not emit reply_error");
	zassert_equal(
		g_require_lease_calls, 1, "start action should require lease");
	zassert_equal(g_publish_state_calls, 1,
		"start action should publish one state event");
	zassert_equal(g_query_reply_calls, 1,
		"start action should emit one success reply");
	zassert_true(strstr(g_last_reply_json, "\"status\":\"ok\"") != NULL,
		"start action should emit ok status");
	zassert_true(strstr(g_last_reply_json, "\"action\":\"start\"") != NULL,
		"start action should preserve action in reply");
	zassert_true(g_last_reply_ctx == &g_reply_ctx,
		"reply context should be forwarded to success callback");
}

ZTEST_SUITE(neuro_unit_app_command, NULL, NULL, test_reset, NULL, NULL);
