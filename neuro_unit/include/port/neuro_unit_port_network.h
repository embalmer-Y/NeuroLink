#ifndef NEURO_UNIT_PORT_NETWORK_H
#define NEURO_UNIT_PORT_NETWORK_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum neuro_unit_port_network_type {
	NEURO_UNIT_PORT_NETWORK_UNSPEC = 0,
	NEURO_UNIT_PORT_NETWORK_WIFI,
	NEURO_UNIT_PORT_NETWORK_ETHERNET,
	NEURO_UNIT_PORT_NETWORK_CELLULAR,
};

struct neuro_unit_port_network_connect_params {
	enum neuro_unit_port_network_type type;
	const char *endpoint;
	const char *credential;
	const char *identity;
	uint32_t timeout_ms;
};

struct neuro_unit_port_network_status {
	bool iface_up;
	bool link_ready;
	int ifindex;
	char iface_name[16];
	char ipv4_addr[48];
};

struct neuro_unit_port_network_ops {
	int (*connect)(
		const struct neuro_unit_port_network_connect_params *params);
	int (*disconnect)(void);
	int (*get_status)(struct neuro_unit_port_network_status *status);
	int (*probe_endpoint)(const char *endpoint);
};

#ifdef __cplusplus
}
#endif

#endif
