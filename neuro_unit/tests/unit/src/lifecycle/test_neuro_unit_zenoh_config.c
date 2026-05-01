#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_unit_zenoh.h"

static int g_disconnect_calls;
static char g_last_disconnect_reason[64];

void neuro_unit_zenoh_disconnect_locked(
	struct neuro_unit_zenoh_transport *transport, const char *reason)
{
	g_disconnect_calls++;
	snprintk(g_last_disconnect_reason, sizeof(g_last_disconnect_reason),
		"%s", reason != NULL ? reason : "");
	if (transport != NULL) {
		transport->session_ready = false;
	}
}

static void reset_disconnect_probe(void)
{
	g_disconnect_calls = 0;
	g_last_disconnect_reason[0] = '\0';
}

static void init_transport(struct neuro_unit_zenoh_transport *transport)
{
	neuro_unit_zenoh_init(transport, NULL);
	reset_disconnect_probe();
}

ZTEST(neuro_unit_zenoh_config, test_get_connect_uses_default_without_override)
{
	struct neuro_unit_zenoh_transport transport;

	init_transport(&transport);

	zassert_equal_ptr(neuro_unit_zenoh_get_connect(NULL),
		CONFIG_NEUROLINK_ZENOH_CONNECT);
	zassert_equal_ptr(neuro_unit_zenoh_get_connect(&transport),
		CONFIG_NEUROLINK_ZENOH_CONNECT);
}

ZTEST(neuro_unit_zenoh_config, test_set_override_idle_does_not_disconnect)
{
	struct neuro_unit_zenoh_transport transport;

	init_transport(&transport);

	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.94:7447"),
		0);
	zassert_equal(g_disconnect_calls, 0);
	zassert_equal(strcmp(neuro_unit_zenoh_get_connect(&transport),
			      "tcp/192.168.2.94:7447"),
		0);
}

ZTEST(neuro_unit_zenoh_config, test_set_same_override_keeps_ready_session)
{
	struct neuro_unit_zenoh_transport transport;

	init_transport(&transport);
	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.94:7447"),
		0);
	transport.session_ready = true;
	reset_disconnect_probe();

	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.94:7447"),
		0);
	zassert_true(transport.session_ready);
	zassert_equal(g_disconnect_calls, 0);
}

ZTEST(neuro_unit_zenoh_config,
	test_set_changed_override_disconnects_ready_session)
{
	struct neuro_unit_zenoh_transport transport;

	init_transport(&transport);
	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.94:7447"),
		0);
	transport.session_ready = true;
	reset_disconnect_probe();

	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.95:7447"),
		0);
	zassert_false(transport.session_ready);
	zassert_equal(g_disconnect_calls, 1);
	zassert_equal(strcmp(g_last_disconnect_reason,
			      "zenoh endpoint override updated"),
		0);
	zassert_equal(strcmp(neuro_unit_zenoh_get_connect(&transport),
			      "tcp/192.168.2.95:7447"),
		0);
}

ZTEST(neuro_unit_zenoh_config, test_clear_override_disconnects_ready_session)
{
	struct neuro_unit_zenoh_transport transport;

	init_transport(&transport);
	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.94:7447"),
		0);
	transport.session_ready = true;
	reset_disconnect_probe();

	zassert_equal(neuro_unit_zenoh_clear_connect_override(&transport), 0);
	zassert_false(transport.session_ready);
	zassert_equal(g_disconnect_calls, 1);
	zassert_equal(strcmp(g_last_disconnect_reason,
			      "zenoh endpoint override cleared"),
		0);
	zassert_equal_ptr(neuro_unit_zenoh_get_connect(&transport),
		CONFIG_NEUROLINK_ZENOH_CONNECT);
}

ZTEST(neuro_unit_zenoh_config, test_clear_empty_override_does_not_disconnect)
{
	struct neuro_unit_zenoh_transport transport;

	init_transport(&transport);
	transport.session_ready = true;

	zassert_equal(neuro_unit_zenoh_clear_connect_override(&transport), 0);
	zassert_true(transport.session_ready);
	zassert_equal(g_disconnect_calls, 0);
}

ZTEST(neuro_unit_zenoh_config, test_rejects_invalid_or_oversized_endpoint)
{
	struct neuro_unit_zenoh_transport transport;
	char oversized[NEURO_UNIT_ZENOH_CONNECT_MAX_LEN + 1];

	init_transport(&transport);
	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      &transport, "tcp/192.168.2.94:7447"),
		0);
	memset(oversized, 'x', sizeof(oversized) - 1);
	oversized[sizeof(oversized) - 1] = '\0';

	zassert_equal(neuro_unit_zenoh_set_connect_override(
			      NULL, "tcp/192.168.2.95:7447"),
		-EINVAL);
	zassert_equal(neuro_unit_zenoh_set_connect_override(&transport, NULL),
		-EINVAL);
	zassert_equal(
		neuro_unit_zenoh_set_connect_override(&transport, ""), -EINVAL);
	zassert_equal(
		neuro_unit_zenoh_set_connect_override(&transport, oversized),
		-ENAMETOOLONG);
	zassert_equal(strcmp(neuro_unit_zenoh_get_connect(&transport),
			      "tcp/192.168.2.94:7447"),
		0);
}

ZTEST(neuro_unit_zenoh_config, test_clear_rejects_null_transport)
{
	zassert_equal(neuro_unit_zenoh_clear_connect_override(NULL), -EINVAL);
}

ZTEST_SUITE(neuro_unit_zenoh_config, NULL, NULL, NULL, NULL, NULL);
