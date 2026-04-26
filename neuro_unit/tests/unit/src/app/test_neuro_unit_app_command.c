#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <string.h>

#include "neuro_app_command_registry.h"
#include "neuro_protocol_codec_cbor.h"
#include "neuro_unit_app_command.h"
#include "test_app_runtime_dispatch_mock.h"

static struct neuro_unit_reply_context g_reply_ctx;
static uint8_t g_dummy_query_storage;
static int g_reply_error_calls;
static int g_reply_error_status;
static int g_query_reply_calls;
static int g_query_reply_cbor_calls;
static int g_require_lease_calls;
static int g_publish_state_calls;
static bool g_require_lease_result;
static char g_last_error_message[64];
static char g_last_reply_json[256];
static uint8_t g_last_reply_cbor[256];
static size_t g_last_reply_cbor_len;
static char g_last_lease_id[32];
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
	g_require_lease_calls++;
	g_last_reply_ctx = reply_ctx;
	snprintk(g_last_lease_id, sizeof(g_last_lease_id), "%s",
		metadata != NULL ? metadata->lease_id : "");
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

static void mock_query_reply_cbor(
	const struct neuro_unit_reply_context *reply_ctx, const uint8_t *bytes,
	size_t bytes_len)
{
	g_query_reply_cbor_calls++;
	g_last_reply_ctx = reply_ctx;
	g_last_reply_cbor_len = MIN(bytes_len, sizeof(g_last_reply_cbor));
	if (bytes != NULL && g_last_reply_cbor_len > 0U) {
		memcpy(g_last_reply_cbor, bytes, g_last_reply_cbor_len);
	}
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
	g_reply_ctx.request_id = NULL;
	g_reply_ctx.metadata = NULL;
	g_reply_ctx.request_fields = NULL;
	g_reply_error_calls = 0;
	g_reply_error_status = 0;
	g_query_reply_calls = 0;
	g_query_reply_cbor_calls = 0;
	g_require_lease_calls = 0;
	g_publish_state_calls = 0;
	g_require_lease_result = true;
	g_last_reply_ctx = NULL;
	memset(g_last_error_message, 0, sizeof(g_last_error_message));
	memset(g_last_reply_json, 0, sizeof(g_last_reply_json));
	memset(g_last_reply_cbor, 0, sizeof(g_last_reply_cbor));
	g_last_reply_cbor_len = 0U;
	memset(g_last_lease_id, 0, sizeof(g_last_lease_id));
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
	test_registered_callback_command_cbor_reply_preserves_app_fields)
{
	struct neuro_unit_app_command_ops ops = g_ops;
	struct neuro_protocol_app_command_reply expected_reply = {
		.command_name = "invoke",
		.invoke_count = 7U,
		.callback_enabled = true,
		.trigger_every = 2,
		.event_name = "notify",
		.config_changed = true,
		.publish_ret = 0,
		.echo = "ok",
	};
	uint8_t expected_cbor[256];
	size_t expected_len = 0U;

	ops.query_reply_cbor = mock_query_reply_cbor;
	register_callback_command("demo_app", "invoke", true, true);
	test_app_runtime_dispatch_set_result(0,
		"{\"echo\":\"ok\",\"command\":\"invoke\",\"invoke_count\":7,\"callback_enabled\":true,\"trigger_every\":2,\"event_name\":\"notify\",\"config_changed\":true,\"publish_ret\":0}");

	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "invoke",
		"{\"lease_id\":\"lease-1\"}", "req-app-cbor", &ops);

	zassert_equal(g_reply_error_calls, 0,
		"CBOR callback command should not emit reply_error");
	zassert_equal(g_query_reply_cbor_calls, 1,
		"CBOR callback command should emit one CBOR reply");
	zassert_equal(
		neuro_protocol_encode_app_command_reply_cbor(expected_cbor,
			sizeof(expected_cbor), &expected_reply, &expected_len),
		0, "expected CBOR reply should encode");
	zassert_equal(g_last_reply_cbor_len, expected_len,
		"CBOR reply length should preserve app callback fields");
	zassert_equal(memcmp(g_last_reply_cbor, expected_cbor, expected_len), 0,
		"CBOR reply should match app callback reply fields");
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

ZTEST(neuro_unit_app_command, test_lease_check_prefers_context_metadata)
{
	struct neuro_request_metadata metadata;

	neuro_request_metadata_init(&metadata);
	snprintk(metadata.lease_id, sizeof(metadata.lease_id),
		"lease-from-context");
	g_reply_ctx.metadata = &metadata;

	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "start",
		"{\"lease_id\":\"lease-from-payload\"}", "req-app-context",
		&g_ops);

	zassert_equal(
		g_require_lease_calls, 1, "start action should require lease");
	zassert_true(strcmp(g_last_lease_id, "lease-from-context") == 0,
		"lease check should use decoded context metadata first");
}

ZTEST(neuro_unit_app_command, test_start_prefers_context_request_fields)
{
	struct neuro_unit_request_fields request_fields = { 0 };

	snprintk(request_fields.start_args, sizeof(request_fields.start_args),
		"--context-start");
	g_reply_ctx.request_fields = &request_fields;

	neuro_unit_handle_app_command(&g_reply_ctx, "demo_app", "start",
		"{\"start_args\":\"--payload-start\"}", "req-app-fields",
		&g_ops);

	zassert_equal(g_reply_error_calls, 0,
		"context request fields should not break start command");
	zassert_equal(g_query_reply_calls, 1,
		"start command should still emit success reply");
}

ZTEST_SUITE(neuro_unit_app_command, NULL, NULL, test_reset, NULL, NULL);
