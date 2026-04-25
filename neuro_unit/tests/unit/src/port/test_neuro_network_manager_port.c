#include <zephyr/ztest.h>

#include <errno.h>
#include <string.h>

#include "neuro_network_manager.h"
#include "neuro_unit_port.h"

static struct neuro_unit_port_network_status g_port_status;
static int g_get_status_ret;
static int g_get_status_calls;
static int g_probe_endpoint_calls;
static const char *g_probe_endpoint_arg;

static int mock_get_status(struct neuro_unit_port_network_status *status)
{
	g_get_status_calls++;
	if (g_get_status_ret != 0) {
		return g_get_status_ret;
	}

	zassert_not_null(status, "status must be provided");
	*status = g_port_status;
	return 0;
}

static int mock_probe_endpoint(const char *endpoint)
{
	g_probe_endpoint_calls++;
	g_probe_endpoint_arg = endpoint;
	return 0;
}

static void network_manager_port_reset(void *fixture)
{
	ARG_UNUSED(fixture);
	memset(&g_port_status, 0, sizeof(g_port_status));
	g_get_status_ret = 0;
	g_get_status_calls = 0;
	g_probe_endpoint_calls = 0;
	g_probe_endpoint_arg = NULL;
	(void)neuro_unit_port_set_network_ops(NULL);
}

ZTEST(neuro_network_manager_port, test_collect_status_uses_port_ready_state)
{
	const struct neuro_unit_port_network_ops network_ops = {
		.get_status = mock_get_status,
	};
	struct neuro_network_status status;
	int ret;

	g_port_status.iface_up = true;
	g_port_status.link_ready = true;
	g_port_status.ifindex = 3;
	snprintk(g_port_status.iface_name, sizeof(g_port_status.iface_name),
		"wifi3");
	snprintk(g_port_status.ipv4_addr, sizeof(g_port_status.ipv4_addr),
		"192.0.2.10");

	zassert_equal(neuro_unit_port_set_network_ops(&network_ops), 0,
		"set network ops should succeed");
	ret = neuro_network_manager_collect_status(
		"tcp/192.0.2.1:7447", &status);

	zassert_equal(ret, 0, "collect status should succeed");
	zassert_equal(
		g_get_status_calls, 1, "port get_status should be called once");
	zassert_equal(status.state, NEURO_NETWORK_READY,
		"ready port status should become network ready");
	zassert_true(status.iface_present, "interface should be present");
	zassert_true(status.iface_up, "interface should be up");
	zassert_true(status.address_ready, "address should be ready");
	zassert_true(status.transport_ready, "transport should be ready");
	zassert_equal(status.ifindex, 3, "ifindex should be forwarded");
	zassert_equal(strcmp(status.ipv4_addr, "192.0.2.10"), 0,
		"IPv4 address should be forwarded");
}

ZTEST(neuro_network_manager_port, test_collect_status_rejects_bad_transport)
{
	const struct neuro_unit_port_network_ops network_ops = {
		.get_status = mock_get_status,
	};
	struct neuro_network_status status;
	int ret;

	g_port_status.iface_up = true;
	g_port_status.link_ready = true;
	g_port_status.ifindex = 4;
	snprintk(g_port_status.ipv4_addr, sizeof(g_port_status.ipv4_addr),
		"198.51.100.20");

	zassert_equal(neuro_unit_port_set_network_ops(&network_ops), 0,
		"set network ops should succeed");
	ret = neuro_network_manager_collect_status(
		"udp/198.51.100.1:7447", &status);

	zassert_equal(ret, 0, "bad transport should not be syscall failure");
	zassert_equal(status.state, NEURO_NETWORK_FAILED,
		"unsupported transport should mark network failed");
	zassert_false(status.transport_ready,
		"unsupported transport must not be ready");
}

ZTEST(neuro_network_manager_port, test_collect_status_propagates_port_error)
{
	const struct neuro_unit_port_network_ops network_ops = {
		.get_status = mock_get_status,
	};
	struct neuro_network_status status;
	int ret;

	g_get_status_ret = -EIO;
	zassert_equal(neuro_unit_port_set_network_ops(&network_ops), 0,
		"set network ops should succeed");
	ret = neuro_network_manager_collect_status(
		"tcp/192.0.2.1:7447", &status);

	zassert_equal(ret, -EIO, "port status error should propagate");
	zassert_equal(
		g_get_status_calls, 1, "port get_status should be called once");
	zassert_equal(status.state, NEURO_NETWORK_DOWN,
		"failed status collection should leave down state");
	zassert_equal(strcmp(status.ipv4_addr, "no-ipv4"), 0,
		"failed status collection should keep default IPv4 text");
}

ZTEST(neuro_network_manager_port, test_network_ops_forward_probe_endpoint)
{
	const struct neuro_unit_port_network_ops network_ops = {
		.probe_endpoint = mock_probe_endpoint,
	};
	const struct neuro_unit_port_network_ops *active_ops;
	const char *endpoint = "tcp/192.0.2.1:7447";

	zassert_equal(neuro_unit_port_set_network_ops(&network_ops), 0,
		"set network ops should succeed");
	active_ops = neuro_unit_port_get_network_ops();
	zassert_equal(active_ops, &network_ops,
		"active network ops should be caller-provided table");
	zassert_not_null(active_ops->probe_endpoint,
		"probe endpoint hook should be present");
	zassert_equal(active_ops->probe_endpoint(endpoint), 0,
		"probe endpoint callback should run");
	zassert_equal(g_probe_endpoint_calls, 1,
		"probe endpoint should be called once");
	zassert_equal(g_probe_endpoint_arg, endpoint,
		"probe endpoint argument should be forwarded");
}

ZTEST_SUITE(neuro_network_manager_port, NULL, NULL, network_manager_port_reset,
	NULL, NULL);
