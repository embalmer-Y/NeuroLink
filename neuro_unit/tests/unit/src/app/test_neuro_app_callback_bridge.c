#include <zephyr/ztest.h>
#include <zephyr/sys/printk.h>

#include <string.h>

#include "neuro_app_callback_bridge.h"
#include "test_app_runtime_dispatch_mock.h"

static const char *g_last_app_id;
static const char *g_last_command;
static const char *g_last_request_json;
static int g_dispatch_ret;
static const char *g_dispatch_reply;

int app_runtime_dispatch_command(const char *name, const char *command_name,
	const char *request_json, char *reply_buf, size_t reply_buf_len)
{
	g_last_app_id = name;
	g_last_command = command_name;
	g_last_request_json = request_json;

	if (reply_buf != NULL && reply_buf_len > 0U &&
		g_dispatch_reply != NULL) {
		snprintk(reply_buf, reply_buf_len, "%s", g_dispatch_reply);
	}

	return g_dispatch_ret;
}

void test_app_runtime_dispatch_reset(void)
{
	g_last_app_id = NULL;
	g_last_command = NULL;
	g_last_request_json = NULL;
	g_dispatch_ret = 0;
	g_dispatch_reply = NULL;
}

void test_app_runtime_dispatch_set_result(int ret, const char *reply)
{
	g_dispatch_ret = ret;
	g_dispatch_reply = reply;
}

ZTEST(neuro_app_callback_bridge, test_dispatch_forwards_arguments)
{
	char reply[32] = "prefill";
	int ret;

	test_app_runtime_dispatch_reset();
	test_app_runtime_dispatch_set_result(7, "ok");

	ret = neuro_app_callback_bridge_dispatch(
		"app_a", "invoke", "{\"k\":1}", reply, sizeof(reply));
	zassert_equal(ret, 7, "dispatch return must pass through");
	zassert_equal(
		strcmp(g_last_app_id, "app_a"), 0, "app id must be forwarded");
	zassert_equal(strcmp(g_last_command, "invoke"), 0,
		"command name must be forwarded");
	zassert_equal(strcmp(g_last_request_json, "{\"k\":1}"), 0,
		"request json must be forwarded");
	zassert_equal(strcmp(reply, "ok"), 0, "reply must be writable");
}

ZTEST(neuro_app_callback_bridge, test_dispatch_uses_default_json_when_null)
{
	int ret;

	test_app_runtime_dispatch_reset();
	test_app_runtime_dispatch_set_result(0, NULL);

	ret = neuro_app_callback_bridge_dispatch(
		"app_b", "status", NULL, NULL, 0U);
	zassert_equal(ret, 0, "dispatch should succeed");
	zassert_equal(strcmp(g_last_request_json, "{}"), 0,
		"null request must map to empty object json");
}

ZTEST(neuro_app_callback_bridge,
	test_dispatch_clears_reply_buffer_before_runtime)
{
	char reply[32] = "stale";

	test_app_runtime_dispatch_reset();
	test_app_runtime_dispatch_set_result(0, NULL);

	zassert_equal(neuro_app_callback_bridge_dispatch(
			      "app_c", "invoke", "{}", reply, sizeof(reply)),
		0, "dispatch should succeed");
	zassert_equal(strcmp(reply, "{}"), 0,
		"reply buffer must default to an empty json object");
}

ZTEST_SUITE(neuro_app_callback_bridge, NULL, NULL, NULL, NULL, NULL);
