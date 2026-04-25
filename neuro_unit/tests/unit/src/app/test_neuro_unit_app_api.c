#include <zephyr/ztest.h>

#include <string.h>

#include "app_runtime_manifest.h"
#include "neuro_unit_app_api.h"
#include "neuro_unit_event.h"

static char g_last_keyexpr[NEURO_UNIT_EVENT_KEY_LEN];
static char g_last_payload[NEURO_UNIT_EVENT_JSON_LEN];
static int g_publish_calls;
static int g_publish_ret;

static int mock_publish(
	const char *keyexpr, const char *payload_json, void *ctx)
{
	ARG_UNUSED(ctx);

	g_publish_calls++;
	snprintk(g_last_keyexpr, sizeof(g_last_keyexpr), "%s", keyexpr);
	snprintk(g_last_payload, sizeof(g_last_payload), "%s", payload_json);
	return g_publish_ret;
}

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	memset(g_last_keyexpr, 0, sizeof(g_last_keyexpr));
	memset(g_last_payload, 0, sizeof(g_last_payload));
	g_publish_calls = 0;
	g_publish_ret = 0;
	neuro_unit_event_reset();
}

ZTEST(neuro_unit_app_api, test_public_header_json_helpers_extract_values)
{
	char event_name[NEURO_UNIT_APP_EVENT_NAME_LEN] = { 0 };
	const char *json =
		"{\"event_name\":\"callback\",\"trigger_every\":3,\"enabled\":true}";

	zassert_true(neuro_json_extract_string(json, "event_name", event_name,
			     sizeof(event_name)),
		"public string helper must extract app event name");
	zassert_equal(strcmp(event_name, "callback"), 0,
		"event name must round-trip through the public helper");
	zassert_equal(neuro_json_extract_int(json, "trigger_every", -1), 3,
		"public int helper must extract integer values");
	zassert_true(neuro_json_extract_bool(json, "enabled", false),
		"public bool helper must extract boolean values");
}

ZTEST(neuro_unit_app_api, test_public_header_publish_function_forwards_event)
{
	int ret;

	ret = neuro_unit_event_configure("unit-01", mock_publish, NULL);
	zassert_equal(ret, 0, "event configure should succeed");

	ret = neuro_unit_publish_app_event(
		"demo_app", "callback", "{\"invoke_count\":2}");
	zassert_equal(
		ret, 0, "public app event publish function should succeed");
	zassert_equal(g_publish_calls, 1,
		"public publish helper must forward to configured publisher");
	zassert_true(strcmp(g_last_keyexpr,
			     "neuro/unit-01/event/app/demo_app/callback") == 0,
		"public publish helper must build the expected keyexpr");
	zassert_true(strcmp(g_last_payload, "{\"invoke_count\":2}") == 0,
		"public publish helper must preserve payload bytes");
}

ZTEST(neuro_unit_app_api, test_callback_publish_helper_builds_payload)
{
	const struct neuro_unit_app_callback_event event = {
		.app_id = "demo_app",
		.event_name = "callback",
		.invoke_count = 7U,
		.start_count = 2,
	};
	int ret;

	ret = neuro_unit_event_configure("unit-01", mock_publish, NULL);
	zassert_equal(ret, 0, "event configure should succeed");

	ret = neuro_unit_publish_callback_event(&event);
	zassert_equal(ret, 0,
		"callback event helper should publish through the configured event path");
	zassert_equal(g_publish_calls, 1,
		"callback event helper must invoke publisher once");
	zassert_true(strcmp(g_last_keyexpr,
			     "neuro/unit-01/event/app/demo_app/callback") == 0,
		"callback event helper must build the expected keyexpr");
	zassert_true(
		strcmp(g_last_payload,
			"{\"app_id\":\"demo_app\",\"event_name\":\"callback\",\"invoke_count\":7,\"start_count\":2}") ==
			0,
		"callback event helper must serialize the standard payload contract");
}

ZTEST(neuro_unit_app_api, test_command_reply_helper_writes_standard_json)
{
	const struct neuro_unit_app_command_reply reply = {
		.command_name = "invoke",
		.invoke_count = 5U,
		.callback_enabled = true,
		.trigger_every = 3,
		.event_name = "callback",
		.config_changed = true,
		.publish_ret = 0,
		.echo = "ok",
	};
	char reply_buf[NEURO_UNIT_EVENT_JSON_LEN];
	int ret;

	memset(reply_buf, 0, sizeof(reply_buf));
	ret = neuro_unit_write_command_reply_json(
		reply_buf, sizeof(reply_buf), &reply);
	zassert_equal(ret, 0,
		"command reply helper should serialize the standard reply contract");
	zassert_true(
		strcmp(reply_buf,
			"{\"echo\":\"ok\",\"command\":\"invoke\",\"invoke_count\":5,\"callback_enabled\":true,\"trigger_every\":3,\"event_name\":\"callback\",\"config_changed\":true,\"publish_ret\":0}") ==
			0,
		"command reply helper must preserve the shared reply JSON shape");
}

ZTEST(neuro_unit_app_api, test_manifest_header_exposes_runtime_contract)
{
	const struct app_runtime_manifest manifest = {
		.abi_major = APP_RT_MANIFEST_ABI_MAJOR,
		.abi_minor = APP_RT_MANIFEST_ABI_MINOR,
		.version = {
			.major = 1,
			.minor = 2,
			.patch = 3,
		},
		.capability_flags = APP_RT_CAP_STORAGE | APP_RT_CAP_NETWORK,
		.resource = {
			.ram_bytes = 4096,
			.stack_bytes = 1024,
			.cpu_budget_percent = 20,
		},
		.app_name = "demo_app",
		.dependency = "none",
	};

	zassert_equal(sizeof(manifest.app_name),
		APP_RT_MANIFEST_NAME_MAX_LEN + 1,
		"manifest header must expose stable app_name sizing");
	zassert_equal(sizeof(manifest.dependency),
		APP_RT_MANIFEST_DEPENDENCY_MAX_LEN + 1,
		"manifest header must expose stable dependency sizing");
	zassert_equal(strcmp(manifest.app_name, "demo_app"), 0,
		"manifest app_name must be assignable through the public header");
	zassert_equal(strcmp(manifest.dependency, "none"), 0,
		"manifest dependency must be assignable through the public header");
}

ZTEST_SUITE(neuro_unit_app_api, NULL, NULL, test_reset, NULL, NULL);
