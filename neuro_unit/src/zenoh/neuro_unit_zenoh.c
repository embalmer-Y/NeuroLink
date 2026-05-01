#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/socket.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "neuro_network_manager.h"
#include "neuro_unit_port.h"
#include "neuro_unit_zenoh.h"

LOG_MODULE_DECLARE(neurolink_unit, LOG_LEVEL_INF);

#define NEURO_CONNECT_RETRY_MS 5000
#define NEURO_CONNECT_LOG_INTERVAL 6
#define NEURO_DOWNLOAD_PROGRESS_INTERVAL 8
#define NEURO_PREPARE_DEFAULT_CHUNK_SIZE 1024
#define NEURO_PREPARE_MAX_CHUNK_SIZE 4096
#define NEURO_QUERY_TIMEOUT_MS 10000
#define NEUROLINK_NODE_ID CONFIG_NEUROLINK_NODE_ID
#define NEUROLINK_ZENOH_MODE CONFIG_NEUROLINK_ZENOH_MODE

struct neuro_fetch_reply_ctx {
	struct k_sem done;
	uint8_t *buf;
	size_t buf_capacity;
	size_t received;
	int result;
	bool replied;
	atomic_t refs;
};

static void neuro_fetch_ctx_put(struct neuro_fetch_reply_ctx *fetch)
{
	if (fetch != NULL && atomic_dec(&fetch->refs) == 1) {
		free(fetch);
	}
}

static void fetch_reply_dropper(void *ctx)
{
	struct neuro_fetch_reply_ctx *fetch = ctx;

	if (fetch == NULL) {
		return;
	}

	if (!fetch->replied && fetch->result == 0) {
		fetch->result = -ENODATA;
		k_sem_give(&fetch->done);
	}

	neuro_fetch_ctx_put(fetch);
}

static void fetch_reply_handler(z_loaned_reply_t *reply, void *ctx)
{
	struct neuro_fetch_reply_ctx *fetch = ctx;
	const z_loaned_sample_t *sample;
	z_owned_slice_t slice;
	size_t data_len;

	if (fetch == NULL || fetch->replied) {
		return;
	}

	if (!z_reply_is_ok(reply)) {
		fetch->result = -EIO;
		fetch->replied = true;
		k_sem_give(&fetch->done);
		return;
	}

	sample = z_reply_ok(reply);
	if (z_bytes_to_slice(z_sample_payload(sample), &slice) != Z_OK) {
		fetch->result = -EBADMSG;
		fetch->replied = true;
		k_sem_give(&fetch->done);
		return;
	}

	data_len = z_slice_len(z_loan(slice));
	if (data_len > fetch->buf_capacity) {
		fetch->result = -EMSGSIZE;
		z_drop(z_move(slice));
		fetch->replied = true;
		k_sem_give(&fetch->done);
		return;
	}

	if (data_len > 0U) {
		memcpy(fetch->buf, z_slice_data(z_loan(slice)), data_len);
	}
	fetch->received = data_len;
	fetch->result = 0;
	fetch->replied = true;
	z_drop(z_move(slice));
	k_sem_give(&fetch->done);
}

int neuro_unit_zenoh_fetch_chunk(z_owned_session_t *session,
	const char *artifact_key, size_t offset, size_t chunk_size,
	uint8_t *buf, size_t *out_received)
{
	char payload[160];
	z_view_keyexpr_t keyexpr;
	z_get_options_t opts;
	z_owned_bytes_t request_payload;
	z_owned_closure_reply_t callback;
	struct neuro_fetch_reply_ctx *fetch;
	int ret;

	if (session == NULL || artifact_key == NULL || buf == NULL ||
		out_received == NULL) {
		return -EINVAL;
	}

	fetch = calloc(1, sizeof(*fetch));
	if (fetch == NULL) {
		return -ENOMEM;
	}

	fetch->buf = buf;
	fetch->buf_capacity = chunk_size;
	fetch->received = 0U;
	fetch->result = 0;
	fetch->replied = false;
	atomic_set(&fetch->refs, 2);
	k_sem_init(&fetch->done, 0, 1);
	z_get_options_default(&opts);
	snprintk(payload, sizeof(payload),
		"{\"offset\":%zu,\"chunk_size\":%zu}", offset, chunk_size);
	z_bytes_copy_from_str(&request_payload, payload);
	opts.payload = z_move(request_payload);
	z_closure(&callback, fetch_reply_handler, fetch_reply_dropper, fetch);
	z_view_keyexpr_from_str_unchecked(&keyexpr, artifact_key);
	ret = z_get(
		z_loan(*session), z_loan(keyexpr), "", z_move(callback), &opts);
	if (ret < 0) {
		free(fetch);
		return -EIO;
	}

	if (k_sem_take(&fetch->done, K_MSEC(NEURO_QUERY_TIMEOUT_MS)) != 0) {
		neuro_fetch_ctx_put(fetch);
		return -ETIMEDOUT;
	}

	ret = fetch->result;
	*out_received = fetch->received;
	neuro_fetch_ctx_put(fetch);

	if (ret != 0) {
		return ret;
	}

	return 0;
}

int neuro_unit_zenoh_download_artifact(z_owned_session_t *session,
	const char *app_id, const char *artifact_key, size_t total_size,
	size_t chunk_size, const char *dst_path,
	void (*log_memory_snapshot)(const char *stage))
{
	struct fs_file_t file;
	const struct neuro_unit_port_fs_ops *fs_ops =
		neuro_unit_port_get_fs_ops();
	uint8_t *chunk_buf;
	size_t offset = 0U;
	size_t received;
	int ret;
	unsigned int chunk_index = 0U;
	char stage[64];

	if (session == NULL || artifact_key == NULL ||
		artifact_key[0] == '\0' || dst_path == NULL ||
		total_size == 0U) {
		return -EINVAL;
	}
	if (fs_ops == NULL || fs_ops->open == NULL || fs_ops->write == NULL ||
		fs_ops->close == NULL) {
		return -ENOTSUP;
	}

	if (chunk_size == 0U) {
		chunk_size = NEURO_PREPARE_DEFAULT_CHUNK_SIZE;
	}
	if (chunk_size > NEURO_PREPARE_MAX_CHUNK_SIZE) {
		chunk_size = NEURO_PREPARE_MAX_CHUNK_SIZE;
	}

	chunk_buf = malloc(chunk_size);
	if (chunk_buf == NULL) {
		return -ENOMEM;
	}

	fs_file_t_init(&file);
	ret = fs_ops->open(
		&file, dst_path, FS_O_CREATE | FS_O_WRITE | FS_O_TRUNC);
	if (ret < 0) {
		free(chunk_buf);
		return ret;
	}

	if (log_memory_snapshot != NULL) {
		snprintk(stage, sizeof(stage), "prepare:%s:start", app_id);
		log_memory_snapshot(stage);
	}

	while (offset < total_size) {
		size_t request_size = total_size - offset;
		ssize_t written;

		if (request_size > chunk_size) {
			request_size = chunk_size;
		}

		ret = neuro_unit_zenoh_fetch_chunk(session, artifact_key,
			offset, request_size, chunk_buf, &received);
		if (ret) {
			goto out;
		}

		if (received == 0U || received > request_size) {
			ret = -EIO;
			goto out;
		}

		written = fs_ops->write(&file, chunk_buf, received);
		if (written < 0 || (size_t)written != received) {
			ret = written < 0 ? (int)written : -EIO;
			goto out;
		}

		offset += received;
		chunk_index++;
		if (log_memory_snapshot != NULL &&
			(chunk_index == 1U ||
				(chunk_index %
					NEURO_DOWNLOAD_PROGRESS_INTERVAL) ==
					0U ||
				offset == total_size)) {
			snprintk(stage, sizeof(stage), "prepare:%s:%zu/%zu",
				app_id, offset, total_size);
			log_memory_snapshot(stage);
		}
	}

	ret = 0;

out: {
	int close_ret = fs_ops->close(&file);

	if (ret == 0 && close_ret < 0) {
		ret = close_ret;
	}
}
	if (ret != 0 && fs_ops->remove != NULL) {
		(void)fs_ops->remove(dst_path);
	}
	free(chunk_buf);
	return ret;
}

int neuro_unit_zenoh_open_aux_session(
	struct neuro_unit_zenoh_transport *transport,
	z_owned_session_t *session)
{
	z_owned_config_t config;
	const char *connect = neuro_unit_zenoh_get_connect(transport);
	int ret;

	if (session == NULL) {
		return -EINVAL;
	}

	z_config_default(&config);
	zp_config_insert(
		z_loan_mut(config), Z_CONFIG_MODE_KEY, NEUROLINK_ZENOH_MODE);
	if (strlen(connect) > 0U) {
		zp_config_insert(
			z_loan_mut(config), Z_CONFIG_CONNECT_KEY, connect);
	}

	ret = neuro_unit_zenoh_probe_tcp_endpoint(connect);
	if (ret < 0) {
		z_drop(z_move(config));
		return ret;
	}

	if (z_open(session, z_move(config), NULL) < 0) {
		return -EIO;
	}

	return 0;
}

void neuro_unit_zenoh_query_key_to_cstr(
	const z_loaned_query_t *query, char *buf, size_t buf_len)
{
	z_view_string_t keystr;
	size_t key_len;

	if (buf_len == 0U) {
		return;
	}

	z_keyexpr_as_view_string(z_query_keyexpr(query), &keystr);
	key_len = z_string_len(z_loan(keystr));
	if (key_len >= buf_len) {
		key_len = buf_len - 1U;
	}

	memcpy(buf, z_string_data(z_loan(keystr)), key_len);
	buf[key_len] = '\0';
}

void neuro_unit_zenoh_query_payload_to_cstr(
	const z_loaned_query_t *query, char *buf, size_t buf_len)
{
	z_owned_string_t payload_string;
	size_t payload_len;

	if (buf_len == 0U) {
		return;
	}

	z_bytes_to_string(z_query_payload(query), &payload_string);
	payload_len = z_string_len(z_loan(payload_string));
	if (payload_len >= buf_len) {
		payload_len = buf_len - 1U;
	}

	memcpy(buf, z_string_data(z_loan(payload_string)), payload_len);
	buf[payload_len] = '\0';
	z_drop(z_move(payload_string));
}

int neuro_unit_zenoh_query_payload_to_buf(const z_loaned_query_t *query,
	uint8_t *buf, size_t buf_len, size_t *out_len)
{
	z_owned_slice_t slice;
	size_t payload_len;

	if (query == NULL || buf == NULL || out_len == NULL) {
		return -EINVAL;
	}

	if (z_bytes_to_slice(z_query_payload(query), &slice) != Z_OK) {
		return -EBADMSG;
	}

	payload_len = z_slice_len(z_loan(slice));
	if (payload_len > buf_len) {
		z_drop(z_move(slice));
		return -EMSGSIZE;
	}

	if (payload_len > 0U) {
		memcpy(buf, z_slice_data(z_loan(slice)), payload_len);
	}
	*out_len = payload_len;
	z_drop(z_move(slice));
	return 0;
}

void neuro_unit_zenoh_query_reply_json(
	struct neuro_unit_zenoh_transport *transport,
	const z_loaned_query_t *query, const char *json)
{
	z_owned_bytes_t payload;
	z_result_t ret;

	if (transport == NULL || query == NULL || json == NULL) {
		return;
	}

	z_bytes_copy_from_str(&payload, json);
	ret = z_query_reply(
		query, z_query_keyexpr(query), z_move(payload), NULL);
	if (ret < 0) {
		LOG_ERR("query_reply failed: ret=%d session_ready=%d read_task=%d lease_task=%d",
			ret, transport->session_ready ? 1 : 0,
			zp_read_task_is_running(z_loan(transport->session)) ? 1
									    : 0,
			zp_lease_task_is_running(z_loan(transport->session))
				? 1
				: 0);
	}
}

void neuro_unit_zenoh_query_reply_bytes(
	struct neuro_unit_zenoh_transport *transport,
	const z_loaned_query_t *query, const uint8_t *bytes, size_t bytes_len)
{
	z_owned_bytes_t payload;
	z_result_t ret;

	if (transport == NULL || query == NULL ||
		(bytes == NULL && bytes_len > 0U)) {
		return;
	}

	if (z_bytes_copy_from_buf(&payload, bytes, bytes_len) != Z_OK) {
		LOG_ERR("query_reply CBOR payload copy failed: len=%zu",
			bytes_len);
		return;
	}

	ret = z_query_reply(
		query, z_query_keyexpr(query), z_move(payload), NULL);
	if (ret < 0) {
		LOG_ERR("query_reply CBOR failed: ret=%d session_ready=%d read_task=%d lease_task=%d",
			ret, transport->session_ready ? 1 : 0,
			zp_read_task_is_running(z_loan(transport->session)) ? 1
									    : 0,
			zp_lease_task_is_running(z_loan(transport->session))
				? 1
				: 0);
	}
}

bool neuro_unit_zenoh_transport_healthy(
	struct neuro_unit_zenoh_transport *transport)
{
	if (transport == NULL || !transport->session_ready) {
		return false;
	}

	return zp_read_task_is_running(z_loan(transport->session)) &&
	       zp_lease_task_is_running(z_loan(transport->session));
}

void neuro_unit_zenoh_log_transport_health_snapshot(
	struct neuro_unit_zenoh_transport *transport, const char *tag,
	const char *key, const char *request_id)
{
	bool session_ready = transport != NULL && transport->session_ready;
	bool read_task_running = false;
	bool lease_task_running = false;

	if (session_ready) {
		read_task_running =
			zp_read_task_is_running(z_loan(transport->session));
		lease_task_running =
			zp_lease_task_is_running(z_loan(transport->session));
	}

	LOG_WRN("transport[%s]: key=%s request_id=%s session_ready=%d read_task=%d lease_task=%d",
		tag != NULL ? tag : "-", key != NULL ? key : "-",
		request_id != NULL ? request_id : "", session_ready ? 1 : 0,
		read_task_running ? 1 : 0, lease_task_running ? 1 : 0);
}

void neuro_unit_zenoh_disconnect_locked(
	struct neuro_unit_zenoh_transport *transport, const char *reason)
{
	if (transport == NULL || !transport->session_ready) {
		return;
	}

	LOG_WRN("tearing down zenoh session: reason=%s",
		reason != NULL ? reason : "-");
	z_undeclare_queryable(z_move(transport->update_queryable));
	z_undeclare_queryable(z_move(transport->query_queryable));
	z_undeclare_queryable(z_move(transport->cmd_queryable));
	z_close(z_loan_mut(transport->session), NULL);
	z_drop(z_move(transport->session));
	memset(&transport->cmd_queryable, 0, sizeof(transport->cmd_queryable));
	memset(&transport->query_queryable, 0,
		sizeof(transport->query_queryable));
	memset(&transport->update_queryable, 0,
		sizeof(transport->update_queryable));
	memset(&transport->session, 0, sizeof(transport->session));
	transport->session_ready = false;
}

int neuro_unit_zenoh_publish_event_json(
	const char *keyexpr, const char *json, void *ctx)
{
	struct neuro_unit_zenoh_transport *transport = ctx;
	z_owned_bytes_t payload;
	z_view_keyexpr_t key;

	if (transport == NULL || !transport->session_ready) {
		return -ENOTCONN;
	}

	z_view_keyexpr_from_str_unchecked(&key, keyexpr);
	z_bytes_copy_from_str(&payload, json);
	if (z_put(z_loan(transport->session), z_loan(key), z_move(payload),
		    NULL) < 0) {
		LOG_WRN("event publish failed: %s", keyexpr);
		return -EIO;
	}

	return 0;
}

int neuro_unit_zenoh_publish_event_bytes(
	const char *keyexpr, const uint8_t *bytes, size_t bytes_len, void *ctx)
{
	struct neuro_unit_zenoh_transport *transport = ctx;
	z_owned_bytes_t payload;
	z_view_keyexpr_t key;

	if (transport == NULL || !transport->session_ready) {
		return -ENOTCONN;
	}

	if (keyexpr == NULL || keyexpr[0] == '\0' ||
		(bytes == NULL && bytes_len > 0U)) {
		return -EINVAL;
	}

	z_view_keyexpr_from_str_unchecked(&key, keyexpr);
	if (z_bytes_copy_from_buf(&payload, bytes, bytes_len) != Z_OK) {
		return -ENOMEM;
	}

	if (z_put(z_loan(transport->session), z_loan(key), z_move(payload),
		    NULL) < 0) {
		LOG_WRN("CBOR event publish failed: %s", keyexpr);
		return -EIO;
	}

	return 0;
}

static int declare_queryable(struct neuro_unit_zenoh_transport *transport,
	z_owned_queryable_t *queryable, const char *expr,
	void (*handler)(z_loaned_query_t *query, void *ctx))
{
	z_owned_closure_query_t closure;
	z_view_keyexpr_t keyexpr;

	if (transport == NULL || queryable == NULL || handler == NULL) {
		return -EINVAL;
	}

	z_closure(&closure, handler, NULL, NULL);
	z_view_keyexpr_from_str_unchecked(&keyexpr, expr);
	if (z_declare_queryable(z_loan(transport->session), queryable,
		    z_loan(keyexpr), z_move(closure), NULL) < 0) {
		return -EIO;
	}

	return 0;
}

static const char *neuro_unit_ipv4_addr_str(char *buf, size_t buf_len)
{
	struct net_if *iface = net_if_get_default();
	struct net_in_addr *addr;

	if (buf_len == 0U) {
		return "";
	}

	buf[0] = '\0';
	if (iface == NULL) {
		snprintk(buf, buf_len, "no-iface");
		return buf;
	}

	addr = net_if_ipv4_get_global_addr(iface, NET_ADDR_PREFERRED);
	if (addr == NULL) {
		snprintk(buf, buf_len, "no-ipv4");
		return buf;
	}

	if (net_addr_ntop(AF_INET, addr, buf, buf_len) == NULL) {
		snprintk(buf, buf_len, "<format-failed>");
	}

	return buf;
}

static int neuro_unit_parse_tcp_endpoint(
	const char *endpoint, char *host, size_t host_len, uint16_t *port)
{
	const char *prefix = "tcp/";
	const char *host_begin;
	const char *port_sep;
	unsigned long parsed_port;
	size_t host_part_len;
	char port_buf[8];
	char *endptr = NULL;

	if (endpoint == NULL || host == NULL || port == NULL) {
		return -EINVAL;
	}

	if (strncmp(endpoint, prefix, strlen(prefix)) != 0) {
		return -ENOTSUP;
	}

	host_begin = endpoint + strlen(prefix);
	port_sep = strrchr(host_begin, ':');
	if (port_sep == NULL) {
		return -EINVAL;
	}

	host_part_len = (size_t)(port_sep - host_begin);
	if (host_part_len == 0U || host_part_len >= host_len) {
		return -EINVAL;
	}

	memcpy(host, host_begin, host_part_len);
	host[host_part_len] = '\0';

	if (strlen(port_sep + 1) == 0U ||
		strlen(port_sep + 1) >= sizeof(port_buf)) {
		return -EINVAL;
	}

	snprintk(port_buf, sizeof(port_buf), "%s", port_sep + 1);
	parsed_port = strtoul(port_buf, &endptr, 10);
	if (endptr == NULL || *endptr != '\0' || parsed_port == 0UL ||
		parsed_port > 65535UL) {
		return -EINVAL;
	}

	*port = (uint16_t)parsed_port;
	return 0;
}

int neuro_unit_zenoh_probe_tcp_endpoint(const char *endpoint)
{
	const struct neuro_unit_port_network_ops *network_ops;
	struct zsock_addrinfo hints = { 0 };
	struct zsock_addrinfo *res = NULL;
	char host[64];
	char port_str[8];
	uint16_t port;
	int sock;
	int ret;

	if (endpoint == NULL || strlen(endpoint) == 0U) {
		return 0;
	}

	network_ops = neuro_unit_port_get_network_ops();
	if (network_ops != NULL && network_ops->probe_endpoint != NULL) {
		return network_ops->probe_endpoint(endpoint);
	}

	ret = neuro_unit_parse_tcp_endpoint(
		endpoint, host, sizeof(host), &port);
	if (ret) {
		LOG_WRN("tcp probe skipped, unsupported endpoint format: %s (%d)",
			endpoint, ret);
		return ret;
	}

	hints.ai_family = AF_INET;
	hints.ai_socktype = SOCK_STREAM;
	hints.ai_protocol = IPPROTO_TCP;

	snprintk(port_str, sizeof(port_str), "%u", port);
	ret = zsock_getaddrinfo(host, port_str, &hints, &res);
	if (ret != 0) {
		LOG_WRN("tcp probe DNS/addr lookup failed: host=%s port=%s ret=%d",
			host, port_str, ret);
		return -EHOSTUNREACH;
	}

	sock = zsock_socket(res->ai_family, res->ai_socktype, res->ai_protocol);
	if (sock < 0) {
		ret = -errno;
		LOG_WRN("tcp probe socket create failed: endpoint=%s errno=%d",
			endpoint, errno);
		zsock_freeaddrinfo(res);
		return ret;
	}

	ret = zsock_connect(sock, res->ai_addr, res->ai_addrlen);
	if (ret < 0) {
		ret = -errno;
		LOG_WRN("tcp probe connect failed: endpoint=%s errno=%d",
			endpoint, errno);
		zsock_close(sock);
		zsock_freeaddrinfo(res);
		return ret;
	}

	LOG_INF("tcp probe succeeded: endpoint=%s", endpoint);
	zsock_close(sock);
	zsock_freeaddrinfo(res);
	return 0;
}

static int neuro_unit_connect_once(struct neuro_unit_zenoh_transport *transport)
{
	z_owned_config_t config;
	const char *connect = neuro_unit_zenoh_get_connect(transport);
	char cmd_expr[64];
	char query_expr[64];
	char update_expr[64];
	char ipv4_addr[NET_IPV4_ADDR_LEN];
	int ret;

	if (transport == NULL) {
		return -EINVAL;
	}

	z_config_default(&config);
	zp_config_insert(
		z_loan_mut(config), Z_CONFIG_MODE_KEY, NEUROLINK_ZENOH_MODE);
	if (strlen(connect) > 0U) {
		zp_config_insert(
			z_loan_mut(config), Z_CONFIG_CONNECT_KEY, connect);
	}

	LOG_INF("opening zenoh session: mode=%s connect=%s local_ipv4=%s",
		NEUROLINK_ZENOH_MODE,
		strlen(connect) > 0U ? connect : "<scouting>",
		neuro_unit_ipv4_addr_str(ipv4_addr, sizeof(ipv4_addr)));

	ret = neuro_unit_zenoh_probe_tcp_endpoint(connect);
	if (ret < 0) {
		z_drop(z_move(config));
		return ret;
	}

	if (z_open(&transport->session, z_move(config), NULL) < 0) {
		LOG_WRN("z_open failed: mode=%s connect=%s local_ipv4=%s",
			NEUROLINK_ZENOH_MODE,
			strlen(connect) > 0U ? connect : "<scouting>",
			neuro_unit_ipv4_addr_str(ipv4_addr, sizeof(ipv4_addr)));
		return -EIO;
	}

	LOG_INF("zenoh session opened, declaring queryables");

	snprintk(cmd_expr, sizeof(cmd_expr), "neuro/%s/cmd/**",
		NEUROLINK_NODE_ID);
	snprintk(query_expr, sizeof(query_expr), "neuro/%s/query/**",
		NEUROLINK_NODE_ID);
	snprintk(update_expr, sizeof(update_expr), "neuro/%s/update/**",
		NEUROLINK_NODE_ID);

	ret = declare_queryable(transport, &transport->cmd_queryable, cmd_expr,
		transport->handlers.command_query_handler);
	if (ret) {
		LOG_ERR("declare cmd queryable failed: %d expr=%s", ret,
			cmd_expr);
		z_close(z_loan_mut(transport->session), NULL);
		z_drop(z_move(transport->session));
		return ret;
	}

	ret = declare_queryable(transport, &transport->query_queryable,
		query_expr, transport->handlers.query_query_handler);
	if (ret) {
		LOG_ERR("declare query queryable failed: %d expr=%s", ret,
			query_expr);
		z_undeclare_queryable(z_move(transport->cmd_queryable));
		z_close(z_loan_mut(transport->session), NULL);
		z_drop(z_move(transport->session));
		return ret;
	}

	ret = declare_queryable(transport, &transport->update_queryable,
		update_expr, transport->handlers.update_query_handler);
	if (ret) {
		LOG_ERR("declare update queryable failed: %d expr=%s", ret,
			update_expr);
		z_undeclare_queryable(z_move(transport->query_queryable));
		z_undeclare_queryable(z_move(transport->cmd_queryable));
		z_close(z_loan_mut(transport->session), NULL);
		z_drop(z_move(transport->session));
		return ret;
	}

	k_mutex_lock(&transport->lock, K_FOREVER);
	transport->session_ready = true;
	k_mutex_unlock(&transport->lock);
	if (transport->handlers.publish_state_event != NULL) {
		transport->handlers.publish_state_event();
	}
	if (transport->handlers.publish_update_event != NULL) {
		transport->handlers.publish_update_event(
			"system", "boot", "ok", "queryables ready");
	}
	LOG_INF("NeuroLink zenoh queryables ready on node '%s'",
		NEUROLINK_NODE_ID);
	return 0;
}

void neuro_unit_zenoh_connect_thread(void *arg1, void *arg2, void *arg3)
{
	struct neuro_unit_zenoh_transport *transport = arg1;
	uint32_t attempt = 0U;
	uint32_t wait_logs = 0U;
	struct neuro_network_status network_status;
	int ret;

	ARG_UNUSED(arg2);
	ARG_UNUSED(arg3);

	if (transport == NULL) {
		return;
	}

	while (true) {
		const char *connect = neuro_unit_zenoh_get_connect(transport);

		if (transport->session_ready &&
			!neuro_unit_zenoh_transport_healthy(transport)) {
			neuro_unit_zenoh_log_transport_health_snapshot(
				transport, "connect_monitor", "-", NULL);
			k_mutex_lock(&transport->lock, K_FOREVER);
			neuro_unit_zenoh_disconnect_locked(
				transport, "transport unhealthy");
			k_mutex_unlock(&transport->lock);
			attempt = 0U;
		}

		(void)neuro_network_manager_collect_status(
			connect, &network_status);
		if (!neuro_network_manager_is_ready(&network_status)) {
			if (transport->session_ready) {
				k_mutex_lock(&transport->lock, K_FOREVER);
				neuro_unit_zenoh_disconnect_locked(
					transport, "network not ready");
				k_mutex_unlock(&transport->lock);
			}

			wait_logs++;
			if (wait_logs == 1U ||
				(wait_logs % NEURO_CONNECT_LOG_INTERVAL) ==
					0U) {
				LOG_INF("network not ready yet: state=%s ifindex=%d iface_up=%d ipv4=%s",
					neuro_network_state_to_str(
						network_status.state),
					network_status.ifindex,
					network_status.iface_up,
					network_status.ipv4_addr);
			}

			k_sleep(K_MSEC(NEURO_CONNECT_RETRY_MS));
			continue;
		}

		if (transport->session_ready) {
			k_sleep(K_MSEC(NEURO_CONNECT_RETRY_MS));
			continue;
		}

		wait_logs = 0U;
		LOG_INF("network ready: state=%s ifindex=%d ipv4=%s, attempting zenoh session",
			neuro_network_state_to_str(network_status.state),
			network_status.ifindex, network_status.ipv4_addr);
		ret = neuro_unit_connect_once(transport);
		if (ret == 0) {
			attempt = 0U;
			k_sleep(K_MSEC(NEURO_CONNECT_RETRY_MS));
			continue;
		}

		attempt++;
		if (attempt == 1U ||
			(attempt % NEURO_CONNECT_LOG_INTERVAL) == 0U) {
			LOG_WRN("zenoh session not ready yet, retrying in %u ms (attempt=%u connect=%s local_ipv4=%s)",
				NEURO_CONNECT_RETRY_MS, attempt,
				strlen(connect) > 0U ? connect : "<scouting>",
				network_status.ipv4_addr);
		}

		k_sleep(K_MSEC(NEURO_CONNECT_RETRY_MS));
	}
}
