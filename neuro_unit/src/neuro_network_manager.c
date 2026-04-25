#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <stdbool.h>
#include <string.h>

#include "neuro_network_manager.h"
#include "neuro_unit_port.h"

#define NEURO_NETWORK_NO_IPV4 "no-ipv4"

static bool transport_prereq_ready(const char *transport_endpoint)
{
	if (transport_endpoint == NULL || transport_endpoint[0] == '\0') {
		return true;
	}

	return strncmp(transport_endpoint, "tcp/", 4) == 0;
}

static bool port_status_has_ipv4(
	const struct neuro_unit_port_network_status *port_status)
{
	return port_status->ipv4_addr[0] != '\0' &&
	       strcmp(port_status->ipv4_addr, NEURO_NETWORK_NO_IPV4) != 0;
}

static void status_init_empty(struct neuro_network_status *status)
{
	memset(status, 0, sizeof(*status));
	status->state = NEURO_NETWORK_DOWN;
	snprintk(status->ipv4_addr, sizeof(status->ipv4_addr), "%s",
		NEURO_NETWORK_NO_IPV4);
}

static int collect_status_from_port(const char *transport_endpoint,
	struct neuro_network_status *status,
	const struct neuro_unit_port_network_ops *network_ops)
{
	struct neuro_unit_port_network_status port_status;
	int ret;

	if (network_ops == NULL || network_ops->get_status == NULL) {
		return -ENOTSUP;
	}

	status_init_empty(status);
	memset(&port_status, 0, sizeof(port_status));
	ret = network_ops->get_status(&port_status);
	if (ret != 0) {
		return ret;
	}

	status->iface_present =
		port_status.ifindex > 0 || port_status.iface_up ||
		port_status.link_ready || port_status.iface_name[0] != '\0' ||
		port_status_has_ipv4(&port_status);
	status->ifindex = port_status.ifindex;

	if (!status->iface_present) {
		return 0;
	}

	status->state = NEURO_NETWORK_ADAPTER_READY;
	if (!port_status.iface_up) {
		return 0;
	}

	status->iface_up = true;
	status->state = NEURO_NETWORK_LINK_READY;
	if (!port_status.link_ready || !port_status_has_ipv4(&port_status)) {
		return 0;
	}

	status->address_ready = true;
	status->state = NEURO_NETWORK_ADDRESS_READY;
	strncpy(status->ipv4_addr, port_status.ipv4_addr,
		sizeof(status->ipv4_addr) - 1U);
	status->ipv4_addr[sizeof(status->ipv4_addr) - 1U] = '\0';

	if (!transport_prereq_ready(transport_endpoint)) {
		status->state = NEURO_NETWORK_FAILED;
		return 0;
	}

	status->transport_ready = true;
	status->state = NEURO_NETWORK_TRANSPORT_READY;
	status->state = NEURO_NETWORK_READY;
	return 0;
}

const char *neuro_network_state_to_str(enum neuro_network_state state)
{
	switch (state) {
	case NEURO_NETWORK_DOWN:
		return "DOWN";
	case NEURO_NETWORK_ADAPTER_READY:
		return "ADAPTER_READY";
	case NEURO_NETWORK_LINK_READY:
		return "LINK_READY";
	case NEURO_NETWORK_ADDRESS_READY:
		return "ADDRESS_READY";
	case NEURO_NETWORK_TRANSPORT_READY:
		return "TRANSPORT_READY";
	case NEURO_NETWORK_READY:
		return "NETWORK_READY";
	case NEURO_NETWORK_DEGRADED:
		return "DEGRADED";
	case NEURO_NETWORK_FAILED:
		return "FAILED";
	default:
		return "UNKNOWN";
	}
}

bool neuro_network_manager_is_ready(const struct neuro_network_status *status)
{
	return status != NULL && status->state == NEURO_NETWORK_READY;
}

int neuro_network_manager_collect_status(
	const char *transport_endpoint, struct neuro_network_status *status)
{
#if defined(CONFIG_NETWORKING)
	struct net_if *iface;
	struct net_in_addr *addr;
#endif

	if (status == NULL) {
		return -EINVAL;
	}

	{
		const struct neuro_unit_port_network_ops *network_ops =
			neuro_unit_port_get_network_ops();

		if (network_ops != NULL && network_ops->get_status != NULL) {
			return collect_status_from_port(
				transport_endpoint, status, network_ops);
		}
	}

	status_init_empty(status);

#if !defined(CONFIG_NETWORKING)
	ARG_UNUSED(transport_endpoint);
	return 0;
#else

	iface = net_if_get_default();
	if (iface == NULL) {
		return 0;
	}

	status->iface_present = true;
	status->ifindex = net_if_get_by_iface(iface);
	status->state = NEURO_NETWORK_ADAPTER_READY;

	if (!net_if_is_up(iface)) {
		return 0;
	}

	status->iface_up = true;
	status->state = NEURO_NETWORK_LINK_READY;

	addr = net_if_ipv4_get_global_addr(iface, NET_ADDR_PREFERRED);
	if (addr == NULL) {
		return 0;
	}

	status->address_ready = true;
	status->state = NEURO_NETWORK_ADDRESS_READY;
	if (net_addr_ntop(NET_AF_INET, addr, status->ipv4_addr,
		    sizeof(status->ipv4_addr)) == NULL) {
		snprintk(status->ipv4_addr, sizeof(status->ipv4_addr),
			"<format-failed>");
	}

	if (!transport_prereq_ready(transport_endpoint)) {
		status->state = NEURO_NETWORK_FAILED;
		return 0;
	}

	status->transport_ready = true;
	status->state = NEURO_NETWORK_TRANSPORT_READY;
	status->state = NEURO_NETWORK_READY;
	return 0;
#endif
}
