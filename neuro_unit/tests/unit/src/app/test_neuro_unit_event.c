#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

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

ZTEST_SUITE(neuro_unit_event, NULL, NULL, test_reset, NULL, NULL);
