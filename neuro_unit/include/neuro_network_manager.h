#ifndef NEURO_NETWORK_MANAGER_H
#define NEURO_NETWORK_MANAGER_H

#include <stdbool.h>

#include <zephyr/net/net_ip.h>

#ifdef __cplusplus
extern "C" {
#endif

enum neuro_network_state {
	NEURO_NETWORK_DOWN = 0,
	NEURO_NETWORK_ADAPTER_READY,
	NEURO_NETWORK_LINK_READY,
	NEURO_NETWORK_ADDRESS_READY,
	NEURO_NETWORK_TRANSPORT_READY,
	NEURO_NETWORK_READY,
	NEURO_NETWORK_DEGRADED,
	NEURO_NETWORK_FAILED,
};

struct neuro_network_status {
	enum neuro_network_state state;
	bool iface_present;
	bool iface_up;
	bool address_ready;
	bool transport_ready;
	int ifindex;
	char ipv4_addr[NET_IPV4_ADDR_LEN];
};

int neuro_network_manager_collect_status(
	const char *transport_endpoint, struct neuro_network_status *status);
bool neuro_network_manager_is_ready(const struct neuro_network_status *status);
const char *neuro_network_state_to_str(enum neuro_network_state state);

#ifdef __cplusplus
}
#endif

#endif
