#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_protocol_codec_cbor.h"
#include "neuro_unit_event.h"

static char g_last_keyexpr[NEURO_UNIT_EVENT_KEY_LEN];
static char g_last_payload[NEURO_UNIT_EVENT_JSON_LEN];
static uint8_t g_last_bytes[NEURO_UNIT_EVENT_JSON_LEN];
static size_t g_last_bytes_len;
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

static int mock_publish_bytes(const char *keyexpr, const uint8_t *payload,
	size_t payload_len, void *ctx)
{
	ARG_UNUSED(ctx);

	g_publish_calls++;
	snprintk(g_last_keyexpr, sizeof(g_last_keyexpr), "%s", keyexpr);
	zassert_true(payload_len <= sizeof(g_last_bytes),
		"test payload buffer should be large enough");
	memcpy(g_last_bytes, payload, payload_len);
	g_last_bytes_len = payload_len;
	return g_publish_ret;
}

static void test_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	memset(g_last_keyexpr, 0, sizeof(g_last_keyexpr));
	memset(g_last_payload, 0, sizeof(g_last_payload));
	memset(g_last_bytes, 0, sizeof(g_last_bytes));
	g_last_bytes_len = 0U;
	g_publish_calls = 0;
	g_publish_ret = 0;
	neuro_unit_event_reset();
}

ZTEST(neuro_unit_event, test_publish_app_event_forwards_topic_and_payload)
{
	int ret;

	ret = neuro_unit_event_configure("unit-01", mock_publish, NULL);
	zassert_equal(ret, 0, "event configure should succeed");

	ret = neuro_unit_publish_app_event(
		"demo_app", "callback", "{\"value\":1}");
	zassert_equal(ret, 0, "app event publish should succeed");
	zassert_equal(g_publish_calls, 1, "publish callback should run once");
	zassert_true(strcmp(g_last_keyexpr,
			     "neuro/unit-01/event/app/demo_app/callback") == 0,
		"unexpected app event keyexpr");
	zassert_true(strcmp(g_last_payload, "{\"value\":1}") == 0,
		"unexpected payload forwarded to publisher");
}

ZTEST(neuro_unit_event,
	test_publish_app_event_forwards_json_payload_through_binary_sink)
{
	int ret;

	ret = neuro_unit_event_configure_bytes(
		"unit-01", mock_publish_bytes, NULL);
	zassert_equal(ret, 0, "binary event configure should succeed");

	ret = neuro_unit_publish_app_event(
		"demo_app", "gpio_state", "{\"value\":1}");
	zassert_equal(ret, 0, "app event publish should succeed through bytes");
	zassert_equal(g_publish_calls, 1, "publish callback should run once");
	zassert_true(
		strcmp(g_last_keyexpr,
			"neuro/unit-01/event/app/demo_app/gpio_state") == 0,
		"unexpected app event keyexpr");
	zassert_equal(g_last_bytes_len, strlen("{\"value\":1}"),
		"JSON payload byte length should be preserved");
	zassert_equal(memcmp(g_last_bytes, "{\"value\":1}", g_last_bytes_len),
		0, "JSON payload bytes should be forwarded unchanged");
}

ZTEST(neuro_unit_event, test_publish_app_event_requires_valid_contract)
{
	int ret;

	ret = neuro_unit_publish_app_event("demo_app", "callback", "{}");
	zassert_equal(ret, -ENOSYS,
		"publish must fail until event module is configured");

	ret = neuro_unit_event_configure("unit-01", mock_publish, NULL);
	zassert_equal(ret, 0, "event configure should succeed");

	ret = neuro_unit_publish_app_event("demo_app", "bad/topic", "{}");
	zassert_equal(ret, -EINVAL, "invalid event names must be rejected");
	zassert_equal(g_publish_calls, 0,
		"publisher must not run when contract validation fails");
}

ZTEST(neuro_unit_event, test_build_key_accepts_framework_suffixes)
{
	char keyexpr[NEURO_UNIT_EVENT_KEY_LEN];

	zassert_equal(neuro_unit_event_build_key(keyexpr, sizeof(keyexpr),
			      "unit-01", "lease/acquired"),
		0, "framework key build should succeed");
	zassert_true(strcmp(keyexpr, "neuro/unit-01/event/lease/acquired") == 0,
		"unexpected framework keyexpr");
}

ZTEST(neuro_unit_event, test_build_app_key_contract)
{
	char keyexpr[NEURO_UNIT_EVENT_KEY_LEN];

	zassert_equal(neuro_unit_event_build_app_key(keyexpr, sizeof(keyexpr),
			      "unit-01", "neuro_unit_app", "callback"),
		0, "app key build should succeed");
	zassert_true(
		strcmp(keyexpr,
			"neuro/unit-01/event/app/neuro_unit_app/callback") == 0,
		"unexpected app event keyexpr");
}

ZTEST(neuro_unit_event, test_publish_callback_event_contract)
{
	const struct neuro_unit_app_callback_event event = {
		.app_id = "neuro_unit_app",
		.event_name = "callback-test",
		.invoke_count = 3U,
		.start_count = 1,
	};
	int ret;

	ret = neuro_unit_event_configure("unit-01", mock_publish, NULL);
	zassert_equal(ret, 0, "event configure should succeed");

	ret = neuro_unit_publish_callback_event(&event);
	zassert_equal(ret, 0, "callback event publish should succeed");
	k_sleep(K_MSEC(20));
	zassert_equal(g_publish_calls, 1, "publish callback should run once");
	zassert_true(
		strcmp(g_last_keyexpr,
			"neuro/unit-01/event/app/neuro_unit_app/callback-test") ==
			0,
		"callback event keyexpr contract changed");
	zassert_true(
		strcmp(g_last_payload,
			"{\"app_id\":\"neuro_unit_app\",\"event_name\":\"callback-test\",\"invoke_count\":3,\"start_count\":1}") ==
			0,
		"callback event payload contract changed");
}

ZTEST(neuro_unit_event, test_publish_callback_event_binary_contract)
{
	const struct neuro_unit_app_callback_event event = {
		.app_id = "neuro_unit_app",
		.event_name = "callback-test",
		.invoke_count = 3U,
		.start_count = 1,
	};
	struct neuro_protocol_cbor_envelope envelope;
	int ret;

	ret = neuro_unit_event_configure_bytes(
		"unit-01", mock_publish_bytes, NULL);
	zassert_equal(ret, 0, "binary event configure should succeed");

	ret = neuro_unit_publish_callback_event(&event);
	zassert_equal(ret, 0, "callback event publish should succeed");
	k_sleep(K_MSEC(50));
	zassert_equal(g_publish_calls, 1, "publish callback should run once");
	zassert_true(
		strcmp(g_last_keyexpr,
			"neuro/unit-01/event/app/neuro_unit_app/callback-test") ==
			0,
		"callback event keyexpr contract changed");
	zassert_true(g_last_bytes_len > 0U, "CBOR payload should be captured");
	zassert_equal(neuro_protocol_cbor_decode_envelope_header(
			      g_last_bytes, g_last_bytes_len, &envelope),
		0, "callback event CBOR envelope should decode");
	zassert_equal(envelope.message_kind,
		NEURO_PROTOCOL_CBOR_MSG_CALLBACK_EVENT,
		"callback event kind should decode");
}

ZTEST(neuro_unit_event, test_write_command_reply_json_contract)
{
	const struct neuro_unit_app_command_reply reply = {
		.command_name = "invoke",
		.invoke_count = 4U,
		.callback_enabled = true,
		.trigger_every = 2,
		.event_name = "callback-test",
		.config_changed = true,
		.publish_ret = 0,
		.echo = "hello",
	};
	char json[NEURO_UNIT_EVENT_JSON_LEN];
	int ret;

	ret = neuro_unit_write_command_reply_json(json, sizeof(json), &reply);
	zassert_equal(ret, 0, "command reply JSON should build");
	zassert_true(
		strcmp(json,
			"{\"echo\":\"hello\",\"command\":\"invoke\",\"invoke_count\":4,\"callback_enabled\":true,\"trigger_every\":2,\"event_name\":\"callback-test\",\"config_changed\":true,\"publish_ret\":0}") ==
			0,
		"command reply JSON contract changed");
}

ZTEST_SUITE(neuro_unit_event, NULL, NULL, test_reset, NULL, NULL);
