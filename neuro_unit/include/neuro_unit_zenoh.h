#ifndef NEURO_UNIT_ZENOH_H
#define NEURO_UNIT_ZENOH_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <zephyr/kernel.h>

#include <zenoh-pico.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NEURO_UNIT_ZENOH_CONNECT_MAX_LEN 128

struct neuro_unit_zenoh_handlers {
	void (*command_query_handler)(z_loaned_query_t *query, void *ctx);
	void (*query_query_handler)(z_loaned_query_t *query, void *ctx);
	void (*update_query_handler)(z_loaned_query_t *query, void *ctx);
	void (*publish_state_event)(void);
	void (*publish_update_event)(const char *app_id, const char *stage,
		const char *status, const char *message);
};

struct neuro_unit_zenoh_transport {
	struct k_mutex lock;
	bool lock_ready;
	bool session_ready;
	z_owned_session_t session;
	z_owned_queryable_t cmd_queryable;
	z_owned_queryable_t query_queryable;
	z_owned_queryable_t update_queryable;
	char connect_override[NEURO_UNIT_ZENOH_CONNECT_MAX_LEN];
	struct neuro_unit_zenoh_handlers handlers;
};

void neuro_unit_zenoh_init(struct neuro_unit_zenoh_transport *transport,
	const struct neuro_unit_zenoh_handlers *handlers);
const char *neuro_unit_zenoh_get_connect(
	const struct neuro_unit_zenoh_transport *transport);
int neuro_unit_zenoh_set_connect_override(
	struct neuro_unit_zenoh_transport *transport, const char *endpoint);
int neuro_unit_zenoh_clear_connect_override(
	struct neuro_unit_zenoh_transport *transport);
bool neuro_unit_zenoh_transport_healthy(
	struct neuro_unit_zenoh_transport *transport);
void neuro_unit_zenoh_log_transport_health_snapshot(
	struct neuro_unit_zenoh_transport *transport, const char *tag,
	const char *key, const char *request_id);
void neuro_unit_zenoh_disconnect_locked(
	struct neuro_unit_zenoh_transport *transport, const char *reason);
void neuro_unit_zenoh_query_reply_json(
	struct neuro_unit_zenoh_transport *transport,
	const z_loaned_query_t *query, const char *json);
int neuro_unit_zenoh_publish_event_json(
	const char *keyexpr, const char *json, void *ctx);
void neuro_unit_zenoh_query_key_to_cstr(
	const z_loaned_query_t *query, char *buf, size_t buf_len);
void neuro_unit_zenoh_query_payload_to_cstr(
	const z_loaned_query_t *query, char *buf, size_t buf_len);
int neuro_unit_zenoh_open_aux_session(
	struct neuro_unit_zenoh_transport *transport,
	z_owned_session_t *session);
int neuro_unit_zenoh_fetch_chunk(z_owned_session_t *session,
	const char *artifact_key, size_t offset, size_t chunk_size,
	uint8_t *buf, size_t *out_received);
int neuro_unit_zenoh_download_artifact(z_owned_session_t *session,
	const char *app_id, const char *artifact_key, size_t total_size,
	size_t chunk_size, const char *dst_path,
	void (*log_memory_snapshot)(const char *stage));
int neuro_unit_zenoh_probe_tcp_endpoint(const char *endpoint);
void neuro_unit_zenoh_connect_thread(void *arg1, void *arg2, void *arg3);

#ifdef __cplusplus
}
#endif

#endif
