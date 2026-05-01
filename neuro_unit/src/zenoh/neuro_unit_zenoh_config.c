#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <errno.h>
#include <string.h>

#include "neuro_unit_zenoh.h"

#define NEUROLINK_ZENOH_CONNECT_DEFAULT CONFIG_NEUROLINK_ZENOH_CONNECT

void neuro_unit_zenoh_init(struct neuro_unit_zenoh_transport *transport,
	const struct neuro_unit_zenoh_handlers *handlers)
{
	if (transport == NULL) {
		return;
	}

	memset(transport, 0, sizeof(*transport));
	k_mutex_init(&transport->lock);
	transport->lock_ready = true;
	if (handlers != NULL) {
		transport->handlers = *handlers;
	}
}

const char *neuro_unit_zenoh_get_connect(
	const struct neuro_unit_zenoh_transport *transport)
{
	if (transport != NULL && transport->connect_override[0] != '\0') {
		return transport->connect_override;
	}

	return NEUROLINK_ZENOH_CONNECT_DEFAULT;
}

int neuro_unit_zenoh_set_connect_override(
	struct neuro_unit_zenoh_transport *transport, const char *endpoint)
{
	size_t len;

	if (transport == NULL || endpoint == NULL || endpoint[0] == '\0') {
		return -EINVAL;
	}

	len = strlen(endpoint);
	if (len >= sizeof(transport->connect_override)) {
		return -ENAMETOOLONG;
	}

	if (transport->lock_ready) {
		k_mutex_lock(&transport->lock, K_FOREVER);
	}

	if (strcmp(transport->connect_override, endpoint) != 0) {
		snprintk(transport->connect_override,
			sizeof(transport->connect_override), "%s", endpoint);
		if (transport->session_ready) {
			neuro_unit_zenoh_disconnect_locked(
				transport, "zenoh endpoint override updated");
		}
	}

	if (transport->lock_ready) {
		k_mutex_unlock(&transport->lock);
	}

	return 0;
}

int neuro_unit_zenoh_clear_connect_override(
	struct neuro_unit_zenoh_transport *transport)
{
	if (transport == NULL) {
		return -EINVAL;
	}

	if (transport->lock_ready) {
		k_mutex_lock(&transport->lock, K_FOREVER);
	}

	if (transport->connect_override[0] != '\0') {
		transport->connect_override[0] = '\0';
		if (transport->session_ready) {
			neuro_unit_zenoh_disconnect_locked(
				transport, "zenoh endpoint override cleared");
		}
	}

	if (transport->lock_ready) {
		k_mutex_unlock(&transport->lock);
	}

	return 0;
}
